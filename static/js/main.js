document.addEventListener('DOMContentLoaded', function() {
    // Like buttons
    document.querySelectorAll('.like-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const postId = this.dataset.id;
            fetch(`/like/${postId}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    this.innerHTML = `Like ${data.like_count}`;
                    if (data.liked) this.style.color = 'red';
                    else this.style.color = '';
                });
        });
    });

    // Save buttons
    document.querySelectorAll('.save-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const postId = this.dataset.id;
            fetch(`/save/${postId}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    this.innerHTML = data.saved ? 'Saved' : 'Save';
                });
        });
    });

    // Comment toggle buttons
    document.querySelectorAll('.comment-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const postId = this.dataset.id;
            const section = document.getElementById(`comments-${postId}`);
            if (section) {
                section.style.display = section.style.display === 'none' ? 'block' : 'none';
            }
        });
    });
});