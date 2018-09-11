from app import app, db
from app.models import User, Book, Post

@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Book': Book, 'Post': Post}