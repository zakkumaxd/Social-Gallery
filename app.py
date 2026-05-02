import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user, UserMixin
)
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, FileField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime
import bcrypt

# ========================
# Config
# ========================
class Config:
    SECRET_KEY = 'cherry_waves'
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024   # 16MB

# ========================
# App Setup
# ========================
app = Flask(__name__)
app.config.from_object(Config)

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs('instance', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please login or register to interact with posts'

# ========================
# Database and Models
# ========================
DB_PATH = 'instance/gallery.db'

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_filename TEXT NOT NULL,
                caption TEXT,
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
        print("Initialized database")

class User(UserMixin):
    def __init__(self, id, username, email, bio=None):
        self.id = id
        self.username = username
        self.email = email
        self.bio = bio

# ========================
# Utils
# ========================
def allowed_file(filename):
    return (
        '.' in filename and
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']
    )

def compress_to_webp(input_path, output_path, quality=75, max_width=1200):
    img = Image.open(input_path)
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
        img = background
    img.save(output_path, 'webp', quality=quality, optimize=True)
    return output_path

# ========================
# Forms
# ========================
class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField(
        'Confirm Password', validators=[DataRequired(), EqualTo('password')]
    )

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class EditProfileForm(FlaskForm):
    bio = TextAreaField('Bio')

class UploadForm(FlaskForm):
    image = FileField('Image', validators=[DataRequired()])
    caption = StringField('Caption')

class CommentForm(FlaskForm):
    content = StringField('Content', validators=[DataRequired()])

# ========================
# Routes
# ========================
@login_manager.user_loader
def load_user(user_id):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        if user:
            return User(user['id'], user['username'], user['email'], user['bio'])
    return None

@app.route('/')
def index():
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username, users.id as owner_id,
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) as comment_count
            FROM posts 
            JOIN users ON posts.user_id = users.id 
            ORDER BY posts.created_at DESC
        ''').fetchall()
        liked_posts = set()
        saved_posts = set()
        if current_user.is_authenticated:
            liked = conn.execute('SELECT post_id FROM likes WHERE user_id = ?', (current_user.id,)).fetchall()
            liked_posts = {row['post_id'] for row in liked}
            saved = conn.execute('SELECT post_id FROM saved_posts WHERE user_id = ?', (current_user.id,)).fetchall()
            saved_posts = {row['post_id'] for row in saved}
    return render_template('index.html', 
                         posts=posts, 
                         liked_posts=liked_posts,
                         saved_posts=saved_posts)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Passwords do not match!', 'error')
            return redirect(url_for('register'))
        if len(password) < 6:
            flash('Password must be at least 6 characters!', 'error')
            return redirect(url_for('register'))
        password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        try:
            with get_db() as conn:
                conn.execute(
                    'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                    (username, email, password_hash)
                )
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception: # Can use sqlite3.IntegrityError if imported
            flash('Username or email already exists!', 'error')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
                user_obj = User(user['id'], user['username'], user['email'], user['bio'])
                login_user(user_obj)
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

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'image' not in request.files:
        flash('No file selected!', 'error')
        return redirect(url_for('index'))
    file = request.files['image']
    if file.filename == '':
        flash('No file selected!', 'error')
        return redirect(url_for('index'))
    if file and allowed_file(file.filename):
        temp_filename = secure_filename(file.filename)
        temp_path = os.path.join(app.config['UPLOAD_FOLDER'], f"temp_{temp_filename}")
        file.save(temp_path)
        webp_filename = f"{datetime.now().timestamp()}.webp"
        webp_path = os.path.join(app.config['UPLOAD_FOLDER'], webp_filename)
        compress_to_webp(temp_path, webp_path)
        os.remove(temp_path)
        caption = request.form.get('caption', '')
        with get_db() as conn:
            conn.execute(
                'INSERT INTO posts (image_filename, caption, user_id) VALUES (?, ?, ?)',
                (webp_filename, caption, current_user.id)
            )
        flash('Image uploaded successfully!', 'success')
    else:
        flash('File type not allowed! Use PNG, JPG, JPEG, or WEBP.', 'error')
    return redirect(url_for('index'))

@app.route('/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    with get_db() as conn:
        existing = conn.execute(
            'SELECT id FROM likes WHERE user_id = ? AND post_id = ?',
            (current_user.id, post_id)
        ).fetchone()
        if existing:
            conn.execute('DELETE FROM likes WHERE id = ?', (existing['id'],))
            liked = False
        else:
            conn.execute(
                'INSERT INTO likes (user_id, post_id) VALUES (?, ?)',
                (current_user.id, post_id)
            )
            liked = True
        like_count = conn.execute(
            'SELECT COUNT(*) as count FROM likes WHERE post_id = ?',
            (post_id,)
        ).fetchone()['count']
    return jsonify({'liked': liked, 'like_count': like_count})

@app.route('/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('Comment cannot be empty!', 'error')
        return redirect(url_for('index'))
    with get_db() as conn:
        conn.execute(
            'INSERT INTO comments (content, user_id, post_id) VALUES (?, ?, ?)',
            (content, current_user.id, post_id)
        )
    flash('Comment added!', 'success')
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/save/<int:post_id>', methods=['POST'])
@login_required
def save_post(post_id):
    with get_db() as conn:
        existing = conn.execute(
            'SELECT id FROM saved_posts WHERE user_id = ? AND post_id = ?',
            (current_user.id, post_id)
        ).fetchone()
        if existing:
            conn.execute('DELETE FROM saved_posts WHERE id = ?', (existing['id'],))
            saved = False
        else:
            conn.execute(
                'INSERT INTO saved_posts (user_id, post_id) VALUES (?, ?)',
                (current_user.id, post_id)
            )
            saved = True
    return jsonify({'saved': saved})

@app.route('/profile/<username>')
def profile(username):
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            flash('User not found!', 'error')
            return redirect(url_for('index'))
        posts = conn.execute('''
            SELECT posts.*, 
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) as comment_count
            FROM posts 
            WHERE posts.user_id = ?
            ORDER BY posts.created_at DESC
        ''', (user['id'],)).fetchall()
        post_count = len(posts)
        follower_count = 0
        is_own_profile = current_user.is_authenticated and current_user.id == user['id']
    return render_template('profile.html', 
                         profile_user=user, 
                         posts=posts, 
                         post_count=post_count,
                         follower_count=follower_count,
                         is_own_profile=is_own_profile)

@app.route('/my_posts')
@login_required
def my_posts():
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, 
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) as comment_count
            FROM posts 
            WHERE posts.user_id = ?
            ORDER BY posts.created_at DESC
        ''', (current_user.id,)).fetchall()
    return render_template('my_post.html', posts=posts)

@app.route('/saved')
@login_required
def saved_posts():
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username,
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) as comment_count
            FROM saved_posts
            JOIN posts ON saved_posts.post_id = posts.id
            JOIN users ON posts.user_id = users.id
            WHERE saved_posts.user_id = ?
            ORDER BY saved_posts.created_at DESC
        ''', (current_user.id,)).fetchall()
    return render_template('saved.html', posts=posts)

@app.route('/delete/<int:post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    with get_db() as conn:
        post = conn.execute('SELECT image_filename, user_id FROM posts WHERE id = ?', (post_id,)).fetchone()
        if post and post['user_id'] == current_user.id:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], post['image_filename'])
            if os.path.exists(file_path):
                os.remove(file_path)
            conn.execute('DELETE FROM posts WHERE id = ?', (post_id,))
            flash('Post deleted!', 'success')
        else:
            flash('You cannot delete this post!', 'error')
    return redirect(url_for('index'))

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('index'))
    with get_db() as conn:
        posts = conn.execute('''
            SELECT posts.*, users.username,
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count,
                   (SELECT COUNT(*) FROM comments WHERE comments.post_id = posts.id) as comment_count
            FROM posts 
            JOIN users ON posts.user_id = users.id
            WHERE posts.caption LIKE ? OR users.username LIKE ?
            ORDER BY posts.created_at DESC
        ''', (f'%{query}%', f'%{query}%')).fetchall()
    return render_template('search.html', posts=posts, query=query)

@app.route('/edit-profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        bio = request.form.get('bio', '')
        with get_db() as conn:
            conn.execute('UPDATE users SET bio = ? WHERE id = ?', (bio, current_user.id))
        flash('Profile updated!', 'success')
        return redirect(url_for('profile', username=current_user.username))
    return render_template('edit_profile.html')

@app.route('/post/<int:post_id>')
def view_post(post_id):
    with get_db() as conn:
        post = conn.execute('''
            SELECT posts.*, users.username, users.id as owner_id,
                   (SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) as like_count
            FROM posts 
            JOIN users ON posts.user_id = users.id
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
            ORDER BY comments.created_at DESC
        ''', (post_id,)).fetchall()
        liked = False
        saved = False
        if current_user.is_authenticated:
            liked_check = conn.execute('SELECT id FROM likes WHERE user_id = ? AND post_id = ?', 
                                       (current_user.id, post_id)).fetchone()
            liked = liked_check is not None
            saved_check = conn.execute('SELECT id FROM saved_posts WHERE user_id = ? AND post_id = ?',
                                       (current_user.id, post_id)).fetchone()
            saved = saved_check is not None
    return render_template('view_post.html', post=post, comments=comments, liked=liked, saved=saved)

# =======================
# Main Entry
# =======================
if __name__ == '__main__':
    init_db()
    app.run(debug=True)
