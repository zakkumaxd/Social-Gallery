import os
import uuid
import re
from datetime import datetime
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from PIL import Image
import filetype
import sqlite3
import bleach

# ========================
# App Configuration
# ========================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-this-in-production-' + str(uuid.uuid4()))
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB max (images + GIFs)

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['IMAGE_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'images')
app.config['GIF_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'gifs')
app.config['AVATAR_FOLDER'] = os.path.join(app.config['UPLOAD_FOLDER'], 'avatars')

for folder in [app.config['IMAGE_FOLDER'], app.config['GIF_FOLDER'], app.config['AVATAR_FOLDER']]:
    os.makedirs(folder, exist_ok=True)

# Image settings
IMAGE_MAX_WIDTH = 1000
IMAGE_QUALITY = 75

# GIF settings
GIF_MAX_SIZE = 10 * 1024 * 1024  # 10MB

ALLOWED_IMAGES = {'png', 'jpg', 'jpeg', 'webp'}
ALLOWED_GIFS = {'gif'}

# ========================
# Database Setup
# ========================
DB_PATH = os.path.join(BASE_DIR, 'instance', 'gallery.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                bio TEXT,
                avatar_filename TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT,
                media_filename TEXT,
                media_type TEXT CHECK(media_type IN ('image', 'gif')),
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS likes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id),
                UNIQUE(user_id, post_id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS saved_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                post_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id),
                UNIQUE(user_id, post_id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS follows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                follower_id INTEGER NOT NULL,
                following_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (follower_id) REFERENCES users (id),
                FOREIGN KEY (following_id) REFERENCES users (id),
                UNIQUE(follower_id, following_id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                actor_id INTEGER NOT NULL,
                notification_type TEXT NOT NULL,
                post_id INTEGER,
                is_read BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (actor_id) REFERENCES users (id),
                FOREIGN KEY (post_id) REFERENCES posts (id)
            )
        ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_user_id ON posts(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_created_at ON posts(created_at DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_likes_post_id ON likes(post_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id)')
    print("✅ Database initialized")

# ========================
# User Model
# ========================
class User(UserMixin):
    def __init__(self, id, username, email, bio=None, avatar_filename=None):
        self.id = id
        self.username = username
        self.email = email
        self.bio = bio
        self.avatar_filename = avatar_filename

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please login to interact with posts'

@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            return User(user['id'], user['username'], user['email'], user['bio'], user['avatar_filename'])
    return None

# ========================
# Helper Functions
# ========================

def sanitize_html(content):
    allowed_tags = [
        'p', 'br', 'strong', 'b', 'em', 'i', 'u', 's', 'strike',
        'a', 'ul', 'ol', 'li', 'blockquote', 'code', 'pre', 'h1', 'h2', 'h3'
    ]
    allowed_attrs = {'a': ['href', 'target', 'rel']}
    return bleach.clean(content, tags=allowed_tags, attributes=allowed_attrs, strip=True)

def compress_image(input_path, output_path):
    try:
        img = Image.open(input_path)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        if img.width > IMAGE_MAX_WIDTH:
            ratio = IMAGE_MAX_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((IMAGE_MAX_WIDTH, new_height), Image.Resampling.LANCZOS)
        img.save(output_path, 'webp', quality=IMAGE_QUALITY, optimize=True)
        return True
    except Exception as e:
        print(f"Image compression error: {e}")
        return False

def compress_gif(input_path, output_path):
    """Optimize GIF (lossless compression)"""
    try:
        img = Image.open(input_path)
        img.save(output_path, 'GIF', save_all=True, optimize=True, loop=0)
        return True
    except Exception as e:
        print(f"GIF compression error: {e}")
        return False

def generate_filename(original_filename):
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
    return f"{uuid.uuid4().hex}.{ext}"

def get_user_post_count(user_id):
    with get_db() as conn:
        count = conn.execute('SELECT COUNT(*) as count FROM posts WHERE user_id = ?', (user_id,)).fetchone()
        return count['count']

def get_post_preview(text, limit=150):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    if len(clean) > limit:
        return clean[:limit] + "..."
    return clean

def add_notification(user_id, actor_id, notif_type, post_id=None, conn=None):
    # check if exist if none then add
    if user_id == actor_id:
        return
    already_exists = False
    # Use existing connection if given
    search_sql = '''SELECT 1 FROM notifications WHERE user_id = ? AND actor_id = ? AND notification_type = ? AND (post_id = ? OR (post_id IS NULL AND ? IS NULL)) LIMIT 1'''
    search_params = (user_id, actor_id, notif_type, post_id, post_id)
    if conn is not None:
        existing = conn.execute(search_sql, search_params).fetchone()
        if not existing:
            conn.execute(
                'INSERT INTO notifications (user_id, actor_id, notification_type, post_id) VALUES (?, ?, ?, ?)',
                (user_id, actor_id, notif_type, post_id)
            )
    else:
        with get_db() as new_conn:
            existing = new_conn.execute(search_sql, search_params).fetchone()
            if not existing:
                new_conn.execute(
                    'INSERT INTO notifications (user_id, actor_id, notification_type, post_id) VALUES (?, ?, ?, ?)',
                    (user_id, actor_id, notif_type, post_id)
                )

@app.template_filter('timeago')
def timeago_filter(dt):
    if not dt:
        return ""
    now = datetime.utcnow()
    try:
        if isinstance(dt, str):
            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        diff = now - dt
    except:
        return str(dt)
    seconds = diff.total_seconds()
    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds // 86400)
        return f"{days}d ago"
    else:
        return dt.strftime('%b %d, %Y')

# ========================
# Routes
# ========================
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    offset = (page - 1) * per_page

    with get_db() as conn:
        total_posts = conn.execute('SELECT COUNT(*) as count FROM posts').fetchone()['count']
        total_pages = (total_posts + per_page - 1) // per_page if total_posts > 0 else 1

        posts = conn.execute('''
            SELECT posts.*, users.username, users.id as owner_id, users.avatar_filename,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            ORDER BY posts.created_at DESC
            LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()

        liked_posts = set()
        saved_posts = set()
        if current_user.is_authenticated:
            liked = conn.execute('SELECT post_id FROM likes WHERE user_id = ?', (current_user.id,)).fetchall()
            liked_posts = {row['post_id'] for row in liked}
            saved = conn.execute('SELECT post_id FROM saved_posts WHERE user_id = ?', (current_user.id,)).fetchall()
            saved_posts = {row['post_id'] for row in saved}

    return render_template('index.html', posts=posts, liked_posts=liked_posts,
                          saved_posts=saved_posts, page=page, total_pages=total_pages)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        confirm = request.form['confirm_password']

        errors = []
        if password != confirm:
            errors.append('Passwords do not match')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters')
        if len(username) < 3:
            errors.append('Username must be at least 3 characters')
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            errors.append('Username can only contain letters, numbers, and underscores')

        if errors:
            for error in errors:
                flash(error, 'error')
            return redirect(url_for('register'))

        password_hash = generate_password_hash(password)
        try:
            with get_db() as conn:
                conn.execute(
                    'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, password_hash)
                )
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username or email already exists!', 'error')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user and check_password_hash(user['password_hash'], password):
                user_obj = User(user['id'], user['username'], user['email'], user['bio'], user['avatar_filename'])
                login_user(user_obj)
                next_url = request.args.get('next')
                if next_url and next_url.startswith('/'):
                    return redirect(next_url)
                flash(f'Welcome back, {username}!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password!', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('index'))

@app.route('/create-post', methods=['POST'])
@login_required
def create_post():
    if get_user_post_count(current_user.id) >= 500:
        flash('You have reached the maximum limit of 500 posts.', 'error')
        return redirect(url_for('index'))

    content = request.form.get('content', '').strip()
    has_content = bool(content)
    if has_content:
        content = sanitize_html(content)
        if len(content) > 5000:
            flash('Post content is too long (max 5000 characters).', 'error')
            return redirect(url_for('index'))

    media_filename = None
    media_type = None

    if 'media' in request.files:
        file = request.files['media']
        if file and file.filename:
            original_filename = secure_filename(file.filename)
            data = file.read()
            file.seek(0)
            kind = filetype.guess(data)
            if kind is None:
                flash('Unrecognized file type.', 'error')
                return redirect(url_for('index'))

            mime = kind.mime
            ext = kind.extension
            is_image = mime.startswith('image/') and ext != 'gif'
            is_gif = mime == 'image/gif'

            if is_image and ext in ALLOWED_IMAGES:
                # Process image → convert to WebP
                new_filename = generate_filename(original_filename).replace(ext, 'webp')
                output_path = os.path.join(app.config['IMAGE_FOLDER'], new_filename)
                temp_path = os.path.join(app.config['IMAGE_FOLDER'], f"temp_{new_filename}")
                with open(temp_path, 'wb') as f:
                    f.write(data)
                if compress_image(temp_path, output_path):
                    media_filename = new_filename
                    media_type = 'image'
                    os.remove(temp_path)
                else:
                    os.remove(temp_path)
                    flash('Failed to process image.', 'error')
                    return redirect(url_for('index'))

            elif is_gif:
                # Compress GIF and save as .gif

                if len(data) > GIF_MAX_SIZE:
                    flash('GIF is too large (max 10MB).', 'error')
                    return redirect(url_for('index'))

                new_filename = generate_filename(original_filename)
                output_path = os.path.join(app.config['GIF_FOLDER'], new_filename)
                temp_path = os.path.join(app.config['GIF_FOLDER'], f"temp_{new_filename}")

                with open(temp_path, 'wb') as f:
                    f.write(data)

                if compress_gif(temp_path, output_path):
                    media_filename = new_filename
                    media_type = 'gif'
                    os.remove(temp_path)
                else:
                    os.remove(temp_path)
                    flash('Failed to compress GIF.', 'error')
                    return redirect(url_for('index'))

    if not has_content and not media_filename:
        flash('Please add text or an image/GIF to your post.', 'error')
        return redirect(url_for('index'))

    with get_db() as conn:
        conn.execute(
            'INSERT INTO posts (content, media_filename, media_type, user_id) VALUES (?, ?, ?, ?)',
            (content if has_content else None, media_filename, media_type, current_user.id)
        )
    flash('Post created successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM likes WHERE user_id = ? AND post_id = ?', (current_user.id, post_id)).fetchone()
        if existing:
            conn.execute('DELETE FROM likes WHERE id = ?', (existing['id'],))
            liked = False
        else:
            conn.execute('INSERT INTO likes (user_id, post_id) VALUES (?, ?)', (current_user.id, post_id))
            liked = True
            post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
            if post:
                add_notification(post['user_id'], current_user.id, 'like', post_id, conn=conn)
        like_count = conn.execute('SELECT COUNT(*) as count FROM likes WHERE post_id = ?', (post_id,)).fetchone()['count']
    return jsonify({'liked': liked, 'like_count': like_count})

@app.route('/save/<int:post_id>', methods=['POST'])
@login_required
def save_post(post_id):
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM saved_posts WHERE user_id = ? AND post_id = ?', (current_user.id, post_id)).fetchone()
        if existing:
            conn.execute('DELETE FROM saved_posts WHERE id = ?', (existing['id'],))
            saved = False
        else:
            conn.execute('INSERT INTO saved_posts (user_id, post_id) VALUES (?, ?)', (current_user.id, post_id))
            saved = True
            post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
            if post:
                add_notification(post['user_id'], current_user.id, 'save', post_id, conn=conn)
    return jsonify({'saved': saved})

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty!', 'error')
        return redirect(request.referrer or url_for('index'))
    content = sanitize_html(content)
    with get_db() as conn:
        conn.execute('INSERT INTO comments (content, user_id, post_id) VALUES (?, ?, ?)',
                     (content, current_user.id, post_id))
        post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
        if post:
            add_notification(post['user_id'], current_user.id, 'comment', post_id, conn=conn)
    flash('Comment added!', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/comment/edit/<int:comment_id>', methods=['POST'])
@login_required
def edit_comment(comment_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty', 'error')
        return redirect(request.referrer or url_for('index'))
    content = sanitize_html(content)
    with get_db() as conn:
        comment = conn.execute('SELECT user_id FROM comments WHERE id = ?', (comment_id,)).fetchone()
        if comment and comment['user_id'] == current_user.id:
            conn.execute('UPDATE comments SET content = ? WHERE id = ?', (content, comment_id))
            flash('Comment updated', 'success')
        else:
            flash('You cannot edit this comment', 'error')
    return redirect(request.referrer or url_for('index'))

@app.route('/comment/delete/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    with get_db() as conn:
        comment = conn.execute('SELECT user_id, post_id FROM comments WHERE id = ?', (comment_id,)).fetchone()
        if comment:
            post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (comment['post_id'],)).fetchone()
            if comment['user_id'] == current_user.id or (post and post['user_id'] == current_user.id):
                conn.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
                flash('Comment deleted', 'success')
            else:
                flash('You cannot delete this comment', 'error')
        else:
            flash('Comment not found', 'error')
    return redirect(request.referrer or url_for('index'))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    with get_db() as conn:
        post = conn.execute('''
            SELECT posts.*, users.username, users.id as owner_id, users.avatar_filename,
                   COALESCE(like_counts.count, 0) as like_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            WHERE posts.id = ?
        ''', (post_id,)).fetchone()
        if not post:
            flash('Post not found!', 'error')
            return redirect(url_for('index'))

        comments = conn.execute('''
            SELECT comments.*, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC
        ''', (post_id,)).fetchall()

        liked = saved = False
        if current_user.is_authenticated:
            liked = conn.execute('SELECT id FROM likes WHERE user_id = ? AND post_id = ?', (current_user.id, post_id)).fetchone() is not None
            saved = conn.execute('SELECT id FROM saved_posts WHERE user_id = ? AND post_id = ?', (current_user.id, post_id)).fetchone() is not None
    return render_template('view_post.html', post=post, comments=comments, liked=liked, saved=saved)

@app.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    with get_db() as conn:
        post = conn.execute('SELECT media_filename, media_type, user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
        if post and post['user_id'] == current_user.id:
            if post['media_filename']:
                folder_map = {'image': app.config['IMAGE_FOLDER'], 'gif': app.config['GIF_FOLDER']}
                folder = folder_map.get(post['media_type'])
                if folder:
                    file_path = os.path.join(folder, post['media_filename'])
                    if os.path.exists(file_path):
                        os.remove(file_path)
            conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
            conn.execute('DELETE FROM likes WHERE post_id = ?', (post_id,))
            conn.execute('DELETE FROM comments WHERE post_id = ?', (post_id,))
            conn.execute('DELETE FROM saved_posts WHERE post_id = ?', (post_id,))
            flash('Post deleted!', 'success')
        else:
            flash('You cannot delete this post!', 'error')
    return redirect(url_for('index'))

@app.route('/edit-post/<int:post_id>', methods=['POST'])
@login_required
def edit_post(post_id):
    with get_db() as conn:
        post = conn.execute('SELECT user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
        if not post or post['user_id'] != current_user.id:
            flash('You cannot edit this post', 'error')
            return redirect(request.referrer or url_for('index'))
        content = request.form.get('content', '').strip()
        if content:
            content = sanitize_html(content)
            if len(content) > 5000:
                flash('Post content is too long (max 5000 characters).', 'error')
                return redirect(request.referrer or url_for('index'))
        conn.execute('UPDATE posts SET content = ? WHERE id = ?', (content if content else None, post_id))
        flash('Post updated!', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/profile/<username>')
def profile(username):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            flash('User not found', 'error')
            return redirect(url_for('index'))

        posts = conn.execute('''
            SELECT posts.*, users.avatar_filename,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            WHERE posts.user_id = ?
            ORDER BY posts.created_at DESC
        ''', (user['id'],)).fetchall()

        follower_count = conn.execute('SELECT COUNT(*) as count FROM follows WHERE following_id = ?', (user['id'],)).fetchone()['count']
        following_count = conn.execute('SELECT COUNT(*) as count FROM follows WHERE follower_id = ?', (user['id'],)).fetchone()['count']

        is_own_profile = current_user.is_authenticated and current_user.id == user['id']
        is_following = False
        if current_user.is_authenticated and not is_own_profile:
            is_following = conn.execute('SELECT id FROM follows WHERE follower_id = ? AND following_id = ?', (current_user.id, user['id'])).fetchone() is not None

        posts_list = []
        for post in posts:
            pd = dict(post)
            pd['preview'] = get_post_preview(pd['content'], 100)
            posts_list.append(pd)

    return render_template('profile.html', profile_user=user, posts=posts_list,
                          follower_count=follower_count, following_count=following_count,
                          is_own_profile=is_own_profile, is_following=is_following)

@app.route('/my_posts')
@login_required
def my_posts():
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            WHERE posts.user_id = ?
            ORDER BY posts.created_at DESC
        ''', (current_user.id,)).fetchall()
        posts_list = []
        for post in posts:
            pd = dict(post)
            pd['preview'] = get_post_preview(pd['content'], 100)
            posts_list.append(pd)
    return render_template('my_post.html', posts=posts_list)

@app.route('/saved')
@login_required
def saved_posts():
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM saved_posts
            JOIN posts ON saved_posts.post_id = posts.id
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            WHERE saved_posts.user_id = ?
            ORDER BY saved_posts.created_at DESC
        ''', (current_user.id,)).fetchall()
        posts_list = []
        for post in posts:
            pd = dict(post)
            pd['preview'] = get_post_preview(pd['content'], 100)
            posts_list.append(pd)
    return render_template('saved.html', posts=posts_list)

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))

    sql_query = '%' + query.replace('%', '\\%').replace('_', '\\_') + '%'
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            WHERE posts.content LIKE ? ESCAPE '\\' OR users.username LIKE ? ESCAPE '\\'
            ORDER BY posts.created_at DESC
            LIMIT 50
        ''', (sql_query, sql_query)).fetchall()

        posts_list = []
        for post in posts:
            pd = dict(post)
            pd['preview'] = get_post_preview(pd['content'], 100)
            if pd['content']:
                escaped_query = re.escape(query)
                highlighted = re.sub(f'({escaped_query})', r'<mark>\1</mark>', pd['content'], flags=re.IGNORECASE)
                pd['content_highlighted'] = highlighted
            else:
                pd['content_highlighted'] = None
            posts_list.append(pd)
    return render_template('search.html', posts=posts_list, query=query)

@app.route('/tag/<tag_name>')
def tag_posts(tag_name):
    tag_pattern = f'%#{tag_name}%'
    clean_tag = tag_name.replace('%', '\\%').replace('_', '\\_')
    sql_pattern = f'%#{clean_tag}%'
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username, users.avatar_filename,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            WHERE posts.content LIKE ? ESCAPE '\\'
            ORDER BY posts.created_at DESC
            LIMIT 50
        ''', (sql_pattern,)).fetchall()
        posts_list = []
        for post in posts:
            pd = dict(post)
            pd['preview'] = get_post_preview(pd['content'], 100)
            posts_list.append(pd)
    return render_template('tag.html', tag_name=tag_name, posts=posts_list)

@app.route('/notifications')
@login_required
def notifications():
    with get_db() as conn:
        conn.execute('UPDATE notifications SET is_read = 1 WHERE user_id = ?', (current_user.id,))
        notifs = conn.execute('''
            SELECT notifications.*, users.username as actor_username, users.avatar_filename as actor_avatar,
                   posts.content as post_content, posts.id as post_id_ref
            FROM notifications
            JOIN users ON notifications.actor_id = users.id
            LEFT JOIN posts ON notifications.post_id = posts.id
            WHERE notifications.user_id = ?
            ORDER BY notifications.created_at DESC
            LIMIT 100
        ''', (current_user.id,)).fetchall()
        notifs_list = []
        for n in notifs:
            nd = dict(n)
            if nd['post_content']:
                nd['post_preview'] = get_post_preview(nd['post_content'], 80)
            else:
                nd['post_preview'] = None
            notifs_list.append(nd)
    return render_template('notifications.html', notifications=notifs_list)

@app.route('/api/posts')
def api_posts():
    offset = request.args.get('offset', 0, type=int)
    limit = 20
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username, users.id as owner_id, users.avatar_filename,
                   COALESCE(like_counts.count, 0) as like_count,
                   COALESCE(comment_counts.count, 0) as comment_count
            FROM posts
            JOIN users ON posts.user_id = users.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM likes GROUP BY post_id) as like_counts
                ON like_counts.post_id = posts.id
            LEFT JOIN (SELECT post_id, COUNT(*) as count FROM comments GROUP BY post_id) as comment_counts
                ON comment_counts.post_id = posts.id
            ORDER BY posts.created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset)).fetchall()
        posts_list = [dict(post) for post in posts]
    return jsonify(posts_list)

@app.route('/api/comments/<int:post_id>/recent')
def api_comments_recent(post_id):
    limit = request.args.get('limit', 3, type=int)
    with get_db() as conn:
        comments = conn.execute('''
            SELECT comments.*, users.username
            FROM comments
            JOIN users ON comments.user_id = users.id
            WHERE comments.post_id = ?
            ORDER BY comments.created_at ASC
            LIMIT ?
        ''', (post_id, limit)).fetchall()
        comments_list = [dict(c) for c in comments]
    return jsonify(comments_list)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        bio = request.form.get('bio', '')
        bio = sanitize_html(bio)

        avatar_filename = None
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename:
                header = file.read(1024)
                file.seek(0)
                kind = filetype.guess(header)
                if kind is None or not kind.mime.startswith('image/'):
                    flash('Avatar must be an image file', 'error')
                    return redirect(url_for('edit_profile'))
                ext = kind.extension
                if ext not in ALLOWED_IMAGES and ext != 'gif':
                    flash('Avatar must be a PNG, JPG, JPEG, WEBP or GIF', 'error')
                    return redirect(url_for('edit_profile'))

                temp_filename = generate_filename(file.filename)
                temp_path = os.path.join(app.config['AVATAR_FOLDER'], f"temp_{temp_filename}")
                file.save(temp_path)

                avatar_filename = generate_filename(file.filename).replace(ext, 'webp')
                output_path = os.path.join(app.config['AVATAR_FOLDER'], avatar_filename)
                img = Image.open(temp_path)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                img.save(output_path, 'webp', quality=70, optimize=True)
                os.remove(temp_path)

        with get_db() as conn:
            if avatar_filename:
                old = conn.execute('SELECT avatar_filename FROM users WHERE id = ?', (current_user.id,)).fetchone()
                if old and old['avatar_filename']:
                    old_path = os.path.join(app.config['AVATAR_FOLDER'], old['avatar_filename'])
                    if os.path.exists(old_path):
                        os.remove(old_path)
                conn.execute('UPDATE users SET bio = ?, avatar_filename = ? WHERE id = ?', (bio, avatar_filename, current_user.id))
            else:
                conn.execute('UPDATE users SET bio = ? WHERE id = ?', (bio, current_user.id))
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/follow/<int:user_id>', methods=['POST'])
@login_required
def follow_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot follow yourself'}), 400
    with get_db() as conn:
        existing = conn.execute('SELECT id FROM follows WHERE follower_id = ? AND following_id = ?', (current_user.id, user_id)).fetchone()
        if existing:
            conn.execute('DELETE FROM follows WHERE id = ?', (existing['id'],))
            following = False
        else:
            conn.execute('INSERT INTO follows (follower_id, following_id) VALUES (?, ?)', (current_user.id, user_id))
            following = True
            add_notification(user_id, current_user.id, 'follow', conn=conn)
    return jsonify({'following': following})

@app.route('/followers/<int:user_id>')
def get_followers(user_id):
    with get_db() as conn:
        follower_count = conn.execute('SELECT COUNT(*) as count FROM follows WHERE following_id = ?', (user_id,)).fetchone()['count']
        following_count = conn.execute('SELECT COUNT(*) as count FROM follows WHERE follower_id = ?', (user_id,)).fetchone()['count']
    return jsonify({'followers': follower_count, 'following': following_count})

@app.route('/api/unread_notifications')
@login_required
def unread_notifications():
    with get_db() as conn:
        count = conn.execute('SELECT COUNT(*) as count FROM notifications WHERE user_id = ? AND is_read = 0', (current_user.id,)).fetchone()['count']
    return jsonify({'count': count})

if __name__ == '__main__':
    init_db()
    app.run(debug=True)