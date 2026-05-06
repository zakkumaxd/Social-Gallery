// ========================
// DOM Ready
// ========================
document.addEventListener('DOMContentLoaded', function() {
    initEventListeners();
    initGifAndVideoPlayers();
    // Update notification badge
    if (typeof currentUserId !== 'undefined' && currentUserId) {
        fetch('/api/unread_notifications')
            .then(res => res.json())
            .then(data => {
                const badge = document.getElementById('notificationBadge');
                if (badge && data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline-flex';
                }
            });
    }
});

// Re-initialize event listeners for dynamically loaded content
function initEventListeners() {
    // Like buttons
    document.querySelectorAll('.like-btn').forEach(btn => {
        btn.removeEventListener('click', handleLike);
        btn.addEventListener('click', handleLike);
    });
    
    // Save buttons
    document.querySelectorAll('.save-btn').forEach(btn => {
        btn.removeEventListener('click', handleSave);
        btn.addEventListener('click', handleSave);
    });
    
    // Comment toggle
    document.querySelectorAll('.comment-toggle').forEach(btn => {
        btn.removeEventListener('click', handleCommentToggle);
        btn.addEventListener('click', handleCommentToggle);
    });
    
    // Edit comment buttons
    document.querySelectorAll('.edit-comment-btn').forEach(btn => {
        btn.removeEventListener('click', handleEditComment);
        btn.addEventListener('click', handleEditComment);
    });
    
    // Cancel edit comment
    document.querySelectorAll('.cancel-edit').forEach(btn => {
        btn.removeEventListener('click', handleCancelEdit);
        btn.addEventListener('click', handleCancelEdit);
    });
    
    // Delete post buttons
    document.querySelectorAll('.delete-post-btn').forEach(btn => {
        btn.removeEventListener('click', handleDeletePost);
        btn.addEventListener('click', handleDeletePost);
    });
    
    // Delete comment buttons
    document.querySelectorAll('.delete-comment-btn').forEach(btn => {
        btn.removeEventListener('click', handleDeleteComment);
        btn.addEventListener('click', handleDeleteComment);
    });
    
    // Edit post triggers
    document.querySelectorAll('.edit-post-trigger').forEach(btn => {
        btn.removeEventListener('click', handleEditPostTrigger);
        btn.addEventListener('click', handleEditPostTrigger);
    });
    
    // Unsave buttons (saved page)
    document.querySelectorAll('.unsave-btn').forEach(btn => {
        btn.removeEventListener('click', handleUnsave);
        btn.addEventListener('click', handleUnsave);
    });
}

// ========================
// Event Handlers
// ========================
function handleLike(e) {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    btn.disabled = true;
    const icon = btn.querySelector('i');
    const originalClass = icon.className;
    icon.className = 'fas fa-spinner fa-spin';
    
    const postId = btn.dataset.id;
    fetch(`/like/${postId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            const likeCount = data.like_count;
            const text = btn.querySelector('.like-count');
            
            if (data.liked) {
                btn.classList.add('liked');
                if (text) text.textContent = likeCount;
                if (icon) icon.className = 'fas fa-heart';
            } else {
                btn.classList.remove('liked');
                if (text) text.textContent = likeCount;
                if (icon) icon.className = 'far fa-heart';
            }
            btn.disabled = false;
        })
        .catch(() => {
            icon.className = originalClass;
            btn.disabled = false;
        });
}

function handleSave(e) {
    const btn = e.currentTarget;
    if (btn.disabled) return;
    btn.disabled = true;
    const icon = btn.querySelector('i');
    const originalClass = icon.className;
    icon.className = 'fas fa-spinner fa-spin';
    
    const postId = btn.dataset.id;
    fetch(`/save/${postId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            const text = btn.querySelector('span');
            
            if (data.saved) {
                btn.classList.add('saved');
                if (text) text.textContent = 'Saved';
                if (icon) icon.className = 'fas fa-bookmark';
            } else {
                btn.classList.remove('saved');
                if (text) text.textContent = 'Save';
                if (icon) icon.className = 'far fa-bookmark';
            }
            btn.disabled = false;
        })
        .catch(() => {
            icon.className = originalClass;
            btn.disabled = false;
        });
}

function handleCommentToggle(e) {
    const btn = e.currentTarget;
    const postId = btn.dataset.id;
    const section = document.getElementById(`comments-${postId}`);
    if (section) {
        section.classList.toggle('is-hidden');
        if (!section.classList.contains('is-hidden')) {
            loadRecentComments(postId);
        }
    }
}

function loadRecentComments(postId) {
    fetch(`/api/comments/${postId}/recent?limit=3`)
        .then(res => res.json())
        .then(comments => {
            const container = document.getElementById(`comments-list-${postId}`);
            if (container && comments.length) {
                container.innerHTML = comments.map(comment => {
                    const postOwnerId = parseInt(document.getElementById(`comments-${postId}`)?.dataset.owner);
                    const isOwner = (currentUserId && (comment.user_id == currentUserId || currentUserId == postOwnerId));
                    return `
                    <div class="comment" id="comment-${comment.id}">
                        <div class="comment-header">
                            <a href="/profile/${comment.username}" class="comment-author">@${comment.username}</a>
                            <small>${comment.created_at}</small>
                            ${isOwner ? `
                            <div class="comment-menu">
                                <button class="comment-menu-trigger" data-menu-id="comment-menu-${comment.id}" aria-label="Comment options">
                                    <i class="fas fa-ellipsis-v"></i>
                                </button>
                                <div class="comment-menu-dropdown" id="comment-menu-${comment.id}">
                                    <button type="button" class="edit-comment-btn" data-id="${comment.id}">
                                        <i class="fas fa-edit"></i> Edit
                                    </button>
                                    <form action="/comment/delete/${comment.id}" method="POST">
                                        <button type="button" class="delete-comment-btn">
                                            <i class="fas fa-trash"></i> Delete
                                        </button>
                                    </form>
                                </div>
                            </div>
                            ` : ''}
                        </div>
                        <div class="comment-content-wrapper">
                            <div id="comment-content-${comment.id}">
                                <p>${escapeHtml(comment.content)}</p>
                            </div>
                            ${isOwner ? `
                            <form class="edit-comment-form is-hidden" id="edit-form-${comment.id}" action="/comment/edit/${comment.id}" method="POST">
                                <input type="text" name="content" value="${escapeHtml(comment.content)}" required>
                                <button type="submit"><i class="fas fa-save"></i> Save</button>
                                <button type="button" class="cancel-edit" data-id="${comment.id}"><i class="fas fa-times"></i> Cancel</button>
                            </form>
                            ` : ''}
                        </div>
                    </div>
                    `;
                }).join('');

                // Add "View all" link
                container.insertAdjacentHTML('beforeend', `
                    <div style="text-align: center; margin-top: 8px;">
                        <a href="/post/${postId}" class="btn btn-outline" style="font-size:13px; padding:6px 12px;">
                            View all comments
                        </a>
                    </div>
                `);
                initEventListeners();
            } else if (container) {
                container.innerHTML = '<p class="text-muted" style="text-align: center; padding: 20px;">No comments yet.</p>';
            }
        });
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function handleEditComment(e) {
    const btn = e.currentTarget;
    const commentId = btn.dataset.id;
    const content = document.getElementById(`comment-content-${commentId}`);
    const editForm = document.getElementById(`edit-form-${commentId}`);
    
    if (content && editForm) {
        content.style.display = 'none';
        editForm.classList.remove('is-hidden');
    }
}

function handleCancelEdit(e) {
    const btn = e.currentTarget;
    const commentId = btn.dataset.id;
    const content = document.getElementById(`comment-content-${commentId}`);
    const editForm = document.getElementById(`edit-form-${commentId}`);
    
    if (content && editForm) {
        content.style.display = 'block';
        editForm.classList.add('is-hidden');
    }
}

function showModal(title, message, onConfirm) {
    const modal = document.getElementById('deleteModal');
    if (!modal) return;
    
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalMessage').textContent = message;
    
    const confirmBtn = document.getElementById('modalConfirm');
    const cancelBtn = document.getElementById('modalCancel');
    
    const handleConfirm = () => {
        if (onConfirm) onConfirm();
        modal.classList.remove('show');
        confirmBtn.removeEventListener('click', handleConfirm);
        cancelBtn.removeEventListener('click', handleCancel);
    };
    
    const handleCancel = () => {
        modal.classList.remove('show');
        confirmBtn.removeEventListener('click', handleConfirm);
        cancelBtn.removeEventListener('click', handleCancel);
    };
    
    confirmBtn.addEventListener('click', handleConfirm);
    cancelBtn.addEventListener('click', handleCancel);
    
    modal.classList.add('show');
}

function handleDeletePost(e) {
    e.preventDefault();
    const btn = e.currentTarget;
    const form = btn.closest('form');
    showModal('Delete Post', 'Are you sure you want to delete this post? This action cannot be undone.', () => {
        form.submit();
    });
}

function handleDeleteComment(e) {
    e.preventDefault();
    const btn = e.currentTarget;
    const form = btn.closest('form');
    showModal('Delete Comment', 'Are you sure you want to delete this comment?', () => {
        form.submit();
    });
}

function handleEditPostTrigger(e) {
    const btn = e.currentTarget;
    const postId = btn.dataset.id;
    const editForm = document.getElementById(`edit-post-form-${postId}`);
    const postContent = document.getElementById(`post-content-${postId}`);
    
    if (editForm && postContent) {
        editForm.classList.add('show');
        postContent.style.display = 'none';
        
        const cancelBtn = editForm.querySelector('.cancel-edit-post');
        if (cancelBtn) {
            cancelBtn.onclick = function() {
                editForm.classList.remove('show');
                postContent.style.display = 'block';
            };
        }
    }
}

function handleUnsave(e) {
    const btn = e.currentTarget;
    const postId = btn.dataset.id;
    fetch(`/save/${postId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            if (!data.saved) {
                location.reload();
            }
        });
}

// ========================
// GIF & Video Players
// ========================
function initGifAndVideoPlayers() {
    // GIF click-to-play – replace placeholder with real GIF on click
    document.querySelectorAll('.gif-container').forEach(container => {
        const btn = container.querySelector('.gif-play-btn');
        const img = container.querySelector('img');
        const gifUrl = container.dataset.gifUrl || img?.getAttribute('data-gif-src');
        if (btn && img && gifUrl && !btn.hasListener) {
            btn.hasListener = true;
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                // Replace the placeholder image with the real GIF
                const realImg = new Image();
                realImg.src = gifUrl;
                realImg.alt = 'GIF';
                realImg.loading = 'lazy';
                realImg.style.width = '100%';
                realImg.style.display = 'block';
                img.parentNode.replaceChild(realImg, img);
                btn.style.display = 'none';
            });
        }
    });
    
    // Video players (if any remain)
    document.querySelectorAll('.video-container').forEach(container => {
        const video = container.querySelector('video');
        const btn = container.querySelector('.play-btn');
        if (btn && !btn.hasListener) {
            btn.hasListener = true;
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                video.play();
                btn.style.display = 'none';
            });
        }
    });
}
// ========================
// Post Dropdown Menu
// ========================
function closeAllPostMenus() {
    document.querySelectorAll('.post-menu-dropdown.show').forEach(menu => {
        menu.classList.remove('show');
    });
}

function closeAllCommentMenus() {
    document.querySelectorAll('.comment-menu-dropdown.show').forEach(menu => {
        menu.classList.remove('show');
    });
}

document.addEventListener('click', function(e) {
    const postTrigger = e.target.closest('.post-menu-trigger');
    const insidePostMenu = e.target.closest('.post-menu-dropdown');
    
    if (insidePostMenu) return;
    
    if (!postTrigger) {
        closeAllPostMenus();
    } else {
        const menuId = postTrigger.getAttribute('data-menu-id');
        const menu = document.getElementById(menuId);
        if (menu) {
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            closeAllPostMenus();
            if (!isOpen) {
                menu.classList.add('show');
            }
        }
    }
});

document.addEventListener('click', function(e) {
    const commentTrigger = e.target.closest('.comment-menu-trigger');
    const insideCommentMenu = e.target.closest('.comment-menu-dropdown');
    
    if (insideCommentMenu) return;
    
    if (!commentTrigger) {
        closeAllCommentMenus();
    } else {
        const menuId = commentTrigger.getAttribute('data-menu-id');
        const menu = document.getElementById(menuId);
        if (menu) {
            e.stopPropagation();
            const isOpen = menu.classList.contains('show');
            closeAllCommentMenus();
            if (!isOpen) {
                menu.classList.add('show');
            }
        }
    }
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeAllPostMenus();
        closeAllCommentMenus();
    }
});

// ========================
// Create Post HTML Helper
// ========================

function createPostHTML(post) {
    const mediaHtml = post.media_filename ? `
        <div class="post-media">
            ${post.media_type === 'image' ? `<img src="/static/uploads/images/${post.media_filename}" alt="Post" loading="lazy">` : ''}
            ${post.media_type === 'video' ? `
                <div class="video-container">
                    <video preload="metadata" controls>
                        <source src="/static/uploads/videos/${post.media_filename}" type="video/webm">
                    </video>
                    <button class="play-btn"><i class="fas fa-play"></i></button>
                </div>
            ` : ''}
            ${post.media_type === 'gif' ? `
                <div class="gif-container">
                    <img src="/static/uploads/gifs/${post.media_filename}" alt="GIF" loading="lazy" style="filter: blur(4px);">
                    <button class="gif-play-btn"><i class="fas fa-play"></i> Click to play</button>
                </div>
            ` : ''}
        </div>
    ` : '';
    
    const editFormHtml = post.owner_id === currentUserId ? `
        <div class="edit-post-form" id="edit-post-form-${post.id}">
            <form action="/edit-post/${post.id}" method="POST">
                <textarea name="content" rows="6">${escapeHtml(post.content || '')}</textarea>
                <div class="edit-post-actions">
                    <button type="submit" class="save-edit-btn">Save changes</button>
                    <button type="button" class="cancel-edit-post">Cancel</button>
                </div>
            </form>
        </div>
    ` : '';
    
    return `
        <div class="card post-card" data-post-id="${post.id}">
            <div class="card-header">
                <div class="post-author">
                    <a href="/profile/${post.username}">
                        <div class="avatar">
                            ${post.avatar_filename ? `<img src="/static/uploads/avatars/${post.avatar_filename}" alt="${post.username}">` : '<div class="avatar-placeholder"></div>'}
                        </div>
                        <div class="post-author-info">
                            <h4>@${post.username}</h4>
                            <time>${post.created_at}</time>
                        </div>
                    </a>
                </div>
                <div class="post-menu">
                    <button type="button" class="post-menu-trigger" data-menu-id="post-menu-${post.id}">
                        <i class="fas fa-ellipsis-h"></i>
                    </button>
                    <div class="post-menu-dropdown" id="post-menu-${post.id}">
                        <a href="/post/${post.id}"><i class="fas fa-external-link-alt"></i> Open post</a>
                        <a href="/profile/${post.username}"><i class="fas fa-user"></i> View profile</a>
                        ${post.owner_id === currentUserId ? `
                            <button type="button" class="edit-post-trigger" data-id="${post.id}"><i class="fas fa-edit"></i> Edit post</button>
                            <form action="/delete/${post.id}" method="POST">
                                <button type="button" class="delete-post-btn danger"><i class="fas fa-trash"></i> Delete post</button>
                            </form>
                        ` : ''}
                    </div>
                </div>
            </div>
            ${editFormHtml}
            <a href="/post/${post.id}" class="post-content-link">
                <div class="post-content" id="post-content-${post.id}">
                    ${post.content ? `<div class="post-text">${post.content}</div>` : ''}
                    ${mediaHtml}
                </div>
            </a>
            <div class="post-actions">
                <button class="action-btn like-btn" data-id="${post.id}">
                    <i class="far fa-heart"></i>
                    <span class="like-count">${post.like_count || 0}</span>
                </button>
                <button class="action-btn comment-toggle" data-id="${post.id}">
                    <i class="far fa-comment"></i>
                    <span>${post.comment_count || 0}</span>
                </button>
                <button class="action-btn save-btn" data-id="${post.id}">
                    <i class="far fa-bookmark"></i>
                    <span>Save</span>
                </button>
            </div>
            <div class="comments-section is-hidden" id="comments-${post.id}">
                <form class="comment-form" action="/comment/${post.id}" method="POST">
                    <input type="text" name="content" placeholder="Write a comment..." required autocomplete="off">
                    <button type="submit">Post</button>
                </form>
                <div class="comments-list" id="comments-list-${post.id}"></div>
            </div>
        </div>
    `;
}

// ========================
// Load More Posts
// ========================
const loadMoreBtn = document.getElementById('loadMoreBtn');
if (loadMoreBtn) {
    let offset = 20;
    let loading = false;
    let hasMore = true;
    
    loadMoreBtn.addEventListener('click', async function() {
        if (loading || !hasMore) return;
        loading = true;
        loadMoreBtn.disabled = true;
        loadMoreBtn.innerHTML = '<i class="fas fa-spinner loading-spinner"></i> Loading...';
        
        try {
            const response = await fetch(`/api/posts?offset=${offset}`);
            const posts = await response.json();
            
            if (posts.length === 0) {
                hasMore = false;
                loadMoreBtn.style.display = 'none';
            } else {
                posts.forEach(post => {
                    const postHtml = createPostHTML(post);
                    document.querySelector('.feed').insertAdjacentHTML('beforeend', postHtml);
                });
                offset += posts.length;
                initEventListeners();
                initGifAndVideoPlayers();
                
                if (posts.length < 20) {
                    hasMore = false;
                    loadMoreBtn.style.display = 'none';
                }
            }
        } catch (error) {
            console.error('Error loading posts:', error);
        } finally {
            loading = false;
            loadMoreBtn.disabled = false;
            loadMoreBtn.innerHTML = 'Load more posts';
        }
    });
}

// ========================
// Profile Dropdown
// ========================
const profileTrigger = document.querySelector('.profile-trigger');
const profileMenu = document.getElementById('profileDropdown');

if (profileTrigger && profileMenu) {
    profileTrigger.addEventListener('click', function(e) {
        e.stopPropagation();
        profileMenu.classList.toggle('show');
    });
    
    document.addEventListener('click', function(e) {
        if (!profileTrigger.contains(e.target) && !profileMenu.contains(e.target)) {
            profileMenu.classList.remove('show');
        }
    });
}

// ========================
// Dark Mode Toggle
// ========================
const themeToggle = document.getElementById('darkModeToggle');
if (themeToggle) {
    const themeIcon = themeToggle.querySelector('i');
    const savedTheme = localStorage.getItem('theme');
    if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
        if (themeIcon) themeIcon.className = 'fas fa-sun';
    } else {
        if (themeIcon) themeIcon.className = 'fas fa-moon';
    }
    
    themeToggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        if (currentTheme === 'dark') {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'light');
            if (themeIcon) themeIcon.className = 'fas fa-moon';
        } else {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
            if (themeIcon) themeIcon.className = 'fas fa-sun';
        }
    });
}

// ========================
// Follow Button
// ========================
const followBtn = document.querySelector('.follow-btn');
if (followBtn) {
    followBtn.addEventListener('click', function() {
        if (this.disabled) return;
        this.disabled = true;
        const originalText = this.textContent;
        this.textContent = '…';
        
        const userId = this.dataset.userId;
        fetch(`/follow/${userId}`, { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                if (data.following) {
                    this.textContent = 'Unfollow';
                    this.style.background = 'var(--bg-tertiary)';
                } else {
                    this.textContent = 'Follow';
                    this.style.background = 'var(--brand)';
                }
                
                fetch(`/followers/${userId}`)
                    .then(res => res.json())
                    .then(counts => {
                        const followerCount = document.getElementById('follower-count');
                        if (followerCount) followerCount.textContent = counts.followers;
                    });
                this.disabled = false;
            })
            .catch(() => {
                this.textContent = originalText;
                this.disabled = false;
            });
    });
}

// ========================
// Media Preview
// ========================// Media preview for images & GIFs (shows live preview, GIF preview as muted autoplay video)
const mediaInput = document.getElementById('mediaInput');
const mediaPreview = document.getElementById('mediaPreview');
const fileNameSpan = document.getElementById('fileName');

if (mediaInput && mediaPreview) {
    mediaInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) {
            mediaPreview.innerHTML = '';
            mediaPreview.classList.add('is-hidden');
            if (fileNameSpan) fileNameSpan.textContent = '';
            return;
        }
        if (fileNameSpan) fileNameSpan.textContent = file.name;
        mediaPreview.classList.remove('is-hidden');
        mediaPreview.innerHTML = '';

        const isGif = file.type === 'image/gif';
        const isImage = file.type.startsWith('image/') && !isGif;

        if (isImage) {
            const img = document.createElement('img');
            img.src = URL.createObjectURL(file);
            img.style.maxWidth = '100%';
            img.style.maxHeight = '300px';
            img.style.borderRadius = '8px';
            mediaPreview.appendChild(img);
        } else if (isGif) {
            const video = document.createElement('video');
            video.src = URL.createObjectURL(file);
            video.muted = true;
            video.autoplay = true;
            video.loop = true;
            video.controls = false;
            video.style.maxWidth = '100%';
            video.style.maxHeight = '300px';
            video.style.borderRadius = '8px';
            mediaPreview.appendChild(video);
        }
    });
}

// ========================
// Quill Editor Setup
// ========================
if (typeof Quill !== 'undefined' && document.getElementById('editor-container')) {
    const quill = new Quill('#editor-container', {
        theme: 'snow',
        placeholder: 'Write something amazing... (max 500 characters)',
        modules: {
            toolbar: [
                [{ 'header': [1, 2, 3, false] }],
                ['bold', 'italic', 'underline', 'strike'],
                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                ['link', 'blockquote', 'code-block'],
                ['clean']
            ]
        },
        bounds: '#editor-container'
    });

    function checkPostRequirements() {
        const text = quill.getText().trim();
        const length = text.length;
        const counter = document.getElementById('charCounter');
        const submitBtn = document.querySelector('#createPostForm button[type="submit"]');
        const mediaInput = document.getElementById('mediaInput');
        const hasAttachment = mediaInput && mediaInput.files && mediaInput.files.length > 0 ? true : false;

        if (counter) {
            counter.textContent = `${length}/500`;
            counter.classList.remove('warning', 'danger');
            if (length > 450 && length <= 500) counter.classList.add('warning');
            if (length > 500) counter.classList.add('danger');
        }
        if (submitBtn) {
            if ((length === 0 && !hasAttachment) || length > 500) {
                submitBtn.disabled = true;
            } else {
                submitBtn.disabled = false;
            }
        }
    }

    quill.on('text-change', checkPostRequirements);

    // Listen for media input changes as well
    const mediaInput = document.getElementById('mediaInput');
    if (mediaInput) {
        mediaInput.addEventListener('change', checkPostRequirements);
    }

    // Initial check
    checkPostRequirements();

    const postForm = document.getElementById('createPostForm');
    if (postForm) {
        postForm.addEventListener('submit', function(e) {
            const contentInput = document.getElementById('postContent');
            if (contentInput) {
                contentInput.value = quill.root.innerHTML;
            }

            const text = quill.getText().trim();
            const contentLen = text.replace(/\u200B/g, '').length;
            const mediaInput = document.getElementById('mediaInput');
            const hasAttachment = mediaInput && mediaInput.files && mediaInput.files.length > 0 ? true : false;
            const submitBtn = this.querySelector('button[type="submit"]');

            if ((contentLen === 0 && !hasAttachment) || contentLen > 500) {
                e.preventDefault();
                // Just disable the button, do NOT show errors or reset, just disable
                if (submitBtn) submitBtn.disabled = true;
                return false;
            }

            // Button state/label for submitting
            if (submitBtn && !submitBtn.disabled) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<i class="fas fa-spinner loading-spinner"></i> Posting...';
                setTimeout(() => {
                    submitBtn.disabled = false;
                    submitBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Post';
                }, 30000);
            }
        });
    }
}