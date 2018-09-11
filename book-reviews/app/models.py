from flask import redirect, url_for, request
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import select, func
from werkzeug.security import generate_password_hash, check_password_hash
from app.search import add_to_index, remove_from_index, query_index
from flask_admin.contrib.sqla import ModelView
from flask_admin import Admin, AdminIndexView
from flask_login import UserMixin, current_user
from app import db, login, app
from datetime import datetime
from hashlib import md5
from time import time
import jwt
from flask_admin.contrib.sqla import filters

@login.user_loader
def load_user(id):
    return User.query.get(int(id))


class SearchableMixin(object):
    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return cls.query.filter_by(id=0).outerjoin(Post).group_by(Book.id).\
                       order_by(db.func.count(Post.id).desc()), 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        return cls.query.filter(cls.id.in_(ids)).outerjoin(Post).group_by(Book.id).\
                   order_by(db.func.count(Post.id).desc()), total

    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': [obj for obj in session.new if isinstance(obj, cls)],
            'update': [obj for obj in session.dirty if isinstance(obj, cls)],
            'delete': [obj for obj in session.deleted if isinstance(obj, cls)]
        }

    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            add_to_index(cls.__tablename__, obj)
        for obj in session._changes['update']:
            add_to_index(cls.__tablename__, obj)
        for obj in session._changes['delete']:
            remove_from_index(cls.__tablename__, obj)
        session._changes = None

    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)

#------------------------------User - Book--------------------------------------
user_book = db.Table('user_book',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('book_id', db.Integer, db.ForeignKey('book.id'))
)
#-------------------------------------------------------------------------------

#-----------------------------User - Support------------------------------------
user_post_support = db.Table('user_support',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)
#-------------------------------------------------------------------------------

#----------------------------User - Attack--------------------------------------
user_post_attack = db.Table('user_attack',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)
#-------------------------------------------------------------------------------

#----------------------------User - Neither-------------------------------------
user_post_neither = db.Table('user_neither',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
)
#-------------------------------------------------------------------------------

#------------------------------Users DB-----------------------------------------

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password_hash = db.Column(db.String(128))
    about_me = db.Column(db.String(140))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    fake = db.Column(db.Boolean, default=True)
    admin = db.Column(db.Boolean, default=False)
    img = db.Column(db.String(50))

    posts = db.relationship('Post', backref='user', lazy='dynamic')
    books = db.relationship(
        'Book', secondary=user_book,
        backref=db.backref('users', lazy='dynamic'), lazy='dynamic')

    def __repr__(self):
        return '<User {}>'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def avatar(self, size):
        if self.img is not None:
            return self.img
        else:
            digest = md5(self.email.lower().encode('utf-8')).hexdigest()
            return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(
                digest, size)

    def follow(self, book):
        if not self.is_following(book):
            self.books.append(book)
            book.users.append(self)

    def unfollow(self, book):
        if self.is_following(book):
            self.books.remove(book)
            book.users.remove(self)

    def is_following(self, book):
        return self.books.filter(
            user_book.c.book_id == book.id).count() > 0

    def followed_posts(self):
        followed = Post.query.join(
            user_book, (user_book.c.book_id == Post.book_id)).filter(
                user_book.c.user_id == self.id).filter(Post.level == 1)
        return followed.order_by(Post.timestamp.desc())

    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            app.config['SECRET_KEY'], algorithm='HS256').decode('utf-8')

    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)



#-------------------------------------------------------------------------------

#---------------------------------Books DB--------------------------------------

class Book(SearchableMixin, db.Model):
    __searchable__ = ['author', 'title', 'genre']
    id = db.Column(db.Integer, primary_key=True)
    asin = db.Column(db.String(120), index=True, unique=True)
    title = db.Column(db.String(250), index=True)
    author = db.Column(db.String(120), index=True)
    imUrl = db.Column(db.String(520))
    genre = db.Column(db.String(120), index=True)
    description = db.Column(db.String(900))

    posts = db.relationship('Post', backref='book', lazy='dynamic')

    def __repr__(self):
        return '<Book {}>'.format(self.title)

db.event.listen(db.session, 'before_commit', Book.before_commit)
db.event.listen(db.session, 'after_commit', Book.after_commit)

#-------------------------------------------------------------------------------

#-----------------------------------Posts DB------------------------------------

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(900))
    level = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    summary = db.Column(db.String(140))
    overall = db.Column(db.Float)
    polarity = db.Column(db.Boolean)

    support_users = db.relationship(
        'User', secondary=user_post_support,
        backref=db.backref('support_posts', lazy='dynamic'), lazy='dynamic')
    attack_users = db.relationship(
        'User', secondary=user_post_attack,
        backref=db.backref('attack_posts', lazy='dynamic'), lazy='dynamic')
    neither_users = db.relationship(
        'User', secondary=user_post_neither,
        backref=db.backref('neither_posts', lazy='dynamic'), lazy='dynamic')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('post.id'))

    parent = db.relationship('Post', backref='children', remote_side=[id])

    def was_answered_by(self, user):
        return self.support_users.filter(user_post_support.c.user_id == user.id).count() > 0 or \
               self.attack_users.filter(user_post_attack.c.user_id == user.id).count() > 0 or \
               self.neither_users.filter(user_post_neither.c.user_id == user.id).count() > 0


    def is_supported_by(self, user):
        return self.support_users.filter(user_post_support.c.user_id == user.id).count() > 0

    def is_attacked_by(self, user):
        return self.attack_users.filter(user_post_attack.c.user_id == user.id).count() > 0

    def is_neither_by(self, user):
        return self.neither_users.filter(user_post_neither.c.user_id == user.id).count() > 0

    def supported_by(self, user):
        if not self.is_supported_by(user):
            self.support_users.append(user)
            user.support_posts.append(self)

    def attacked_by(self, user):
        if not self.is_attacked_by(user):
            self.attack_users.append(user)
            user.attack_posts.append(self)

    def neither_by(self, user):
        if not self.is_neither_by(user):
            self.neither_users.append(user)
            user.neither_posts.append(self)

    @hybrid_property
    def nr_of_supports(self):
        return self.support_users.count()

    @nr_of_supports.expression
    def nr_of_supports(cls):
        return db.select([func.count(user_post_support.c.user_id)])\
            .where(user_post_support.c.post_id == cls.id).label('nr_of_supports')


    @hybrid_property
    def nr_of_attacks(self):
        return self.attack_users.count()

    @nr_of_attacks.expression
    def nr_of_attacks(cls):
        return db.select([func.count(user_post_attack.c.user_id)])\
            .where(user_post_attack.c.post_id == cls.id).label('nr_of_attacks')

    @hybrid_property
    def nr_of_neithers(self):
        return self.neither_users.count()

    @nr_of_neithers.expression
    def nr_of_neithers(cls):
        return db.select([func.count(user_post_neither.c.user_id)])\
            .where(user_post_neither.c.post_id == cls.id).label('nr_of_neithers')


    def __repr__(self):
        return self.body

#-------------------------------------------------------------------------------

#---------------------------Flask-Admin-----------------------------------------

class MyAdminIndexView(AdminIndexView):

    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        # redirect to login page if user doesn't have access
        return redirect(url_for('login', next=request.url))

class UserAdminModelView(ModelView):

    # Visible columns in the list view
    column_exclude_list = ['password_hash', 'img', 'about_me', 'book.asin']

    column_filters = ('fake', 'admin', 'username')

    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        # redirect to login page if user doesn't have access
        return redirect(url_for('login', next=request.url))

class PostAdminModelView(ModelView):

    can_export = True

    # Visible columns in the list view
    column_list = ('parent', 'body', 'timestamp', 'user.username', 'book.title', 'level', 'polarity',
                   'nr_of_supports', 'nr_of_attacks', 'nr_of_neithers')

    # Rename columns
    column_labels = {'body': 'Post',
                     'book.title': 'Book',
                     'user.username': 'Author',
                     'nr_of_supports': 'Supports',
                     'nr_of_attacks': 'Attacks',
                     'nr_of_neithers': 'Neutrals',
                     'polarity': 'Relationship'}

    # List of columns that can be sorted. For 'user' column, use User.username as
    # a column.
    column_sortable_list = ('parent', 'body', 'level', 'timestamp', 'polarity', 'user.username', 'book.title',
                            'nr_of_supports', 'nr_of_attacks', 'nr_of_neithers')

    column_searchable_list = (User.username, Book.title)


    column_filters = ('parent.parent_id',
                      'id',
                      'timestamp',
                      'book.title',
                      'book.author',
                      'book.genre',
                      'user.username',
                      'level',
                      'polarity',
                      'user.email',
                      'parent.user.username',
                      'parent.user.email',
                      'nr_of_supports',
                      'nr_of_attacks',
                      'nr_of_neithers'
                      )


    # column_filter_labels = {'parent.parent_id': 'Parent Post Id',
    #                         'id': 'Post Id',
    #                         'level': 'Depth Level of Post',
    #                         'polarity': 'Relationship between Parent Post and Child Post',
    #                         'user.username': 'Username of Author of Post',
    #                         'user.email': 'Email of Author of Post',
    #                         'book.title': 'Book Title',
    #                         'book.author': 'Book Author',
    #                         'book.genre': 'Book Genre',
    #                         'parent.user.username': 'Username of Author of Parent Post',
    #                         'parent.user.email': 'Email of Author of Parent Post'
    #                         }

    # def scaffold_filters(self, name):
    #     filters = super().scaffold_filters(name)
    #     if name in self.column_filter_labels:
    #         for f in filters:
    #             f.name = self.column_filter_labels[name]
    #     return filters
    #
    # form_ajax_refs = {
    #     'user': {
    #         'fields': (User.username, User.email)
    #     },
    #     'book': {
    #         'fields': (Book.title, Book.author)
    #     },
    #     'attack_users': {
    #         'fields': (User.username,)
    #     }
    # }


    def __init__(self, session):
        # Just call parent class with predefined model.
        super(PostAdminModelView, self).__init__(Post, session)

    def is_accessible(self):
        return current_user.is_authenticated and current_user.admin

    def inaccessible_callback(self, name, **kwargs):
        # redirect to login page if user doesn't have access
        return redirect(url_for('login', next=request.url))

#-------------------------------------------------------------------------------
