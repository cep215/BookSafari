from flask_uploads import UploadSet, configure_uploads, IMAGES, patch_request_class

from app.forms import LoginForm, RegistrationForm, EditProfileForm, LikeBookForm, DislikeBookForm, \
    AgreePostForm, DisagreePostForm, SearchBookForm, ResetPasswordRequestForm, ResetPasswordForm, \
    AdminRegistrationForm, AnnotateForm, PhotoFormChoose, FilterPostsForm, PredictForm
from flask import render_template, flash, redirect, url_for, request, g, current_app
from flask_login import current_user, login_user, login_required, logout_user
from app.email import send_password_reset_email, send_admin_request_mail, send_admin_credentials_mail
from app.models import User, Book, Post
from werkzeug.urls import url_parse
from werkzeug.utils import secure_filename
from scipy.sparse import hstack
from app import app, db
import string
import random
import os

import pandas as pd, numpy as np

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.tree import DecisionTreeClassifier
from sklearn.svm import LinearSVC
from sklearn.svm import NuSVC

from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report
from sklearn.metrics import f1_score
from sklearn.metrics import accuracy_score

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

def sentimentAnalysis(stringToBeAnnotated):

    analyzer = SentimentIntensityAnalyzer()
    result = analyzer.polarity_scores(stringToBeAnnotated)
    return result

def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


@app.before_request
def before_request():
    if current_user.is_authenticated:
        g.search_form = SearchBookForm()


def post_form_action(form, level, polarity, user, book, parent):
    post = Post(body=form.post.data, level=level, polarity=polarity, user=user, book=book, parent=parent)
    db.session.add(post)
    db.session.commit()
    flash('Your post is now live!')
    return redirect(url_for('book', book_title=book.title))




#----------------------------------------------------------Index--------------------------------------------------------
@app.route('/')
@app.route('/index', methods=['GET', 'POST'])
@login_required

def index():

    script=""

    page = request.args.get('page', 1, type=int)

    followed_posts = current_user.followed_posts().order_by(Post.timestamp.desc()).\
        paginate(page, app.config['POSTS_PER_PAGE'], False)

    next_url = url_for('index', page=followed_posts.next_num) \
        if followed_posts.has_next else None
    prev_url = url_for('index', page=followed_posts.prev_num) \
        if followed_posts.has_prev else None

    form_agree = AgreePostForm()

    if form_agree.submit_agree.data and form_agree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_agree, parent.level + 1, True, current_user, parent.book, parent)
        script = "window.location.hash = \"jump_to_post_" + str(post_id) + "\";"

    form_disagree = DisagreePostForm()

    if form_disagree.submit_disagree.data and form_disagree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_agree, parent.level + 1, True, current_user, parent.book, parent)
        script = "window.location.hash = \"jump_to_post_" + str(post_id) + "\";"

    form_annotate = AnnotateForm()

    if form_annotate.submit_yes.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.supported_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_" + str(post_id) + "\";"

    if form_annotate.submit_no.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.attacked_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_" + str(post_id) + "\";"

    if form_annotate.submit_notsure.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.neither_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_" + str(post_id) + "\";"

    return render_template('index.html', title='Home Page', followed_posts=followed_posts.items,
                           books=books, form_agree=form_agree, form_disagree=form_disagree,
                           form_annotate=form_annotate,
                           next_url=next_url, prev_url=prev_url,
                           script = script)



#-----------------------------------------------------------------------------------------------------------------------

#-------------------------------------------------------Books_List------------------------------------------------------
@app.route('/books')
def books():

    page = request.args.get('page', 1, type=int)

    books = Book.query.outerjoin(Post).group_by(Book.id).order_by(db.func.count(Post.id).desc())\
        .paginate(page, app.config['POSTS_PER_PAGE'], False)

    next_url = url_for('books', page=books.next_num) \
        if books.has_next else None
    prev_url = url_for('books', page=books.prev_num) \
        if books.has_prev else None

    return render_template('books_list.html', title='Books List', books=books.items, next_url=next_url, prev_url=prev_url)
#-----------------------------------------------------------------------------------------------------------------------

#-----------------------------------------------------Books Search------------------------------------------------------
@app.route('/search')
@login_required
def search():
    if not g.search_form.validate():
        return redirect(url_for('books'))
    page = request.args.get('page', 1, type=int)
    books, total = Book.search(g.search_form.q.data, page, current_app.config['POSTS_PER_PAGE'])
    next_url = url_for('search', q=g.search_form.q.data, page=page + 1) \
        if total > page * current_app.config['POSTS_PER_PAGE'] else None
    prev_url = url_for('search', q=g.search_form.q.data, page=page - 1) \
        if page > 1 else None
    return render_template('search.html', title='Search', books=books,
                           next_url=next_url, prev_url=prev_url)
#-----------------------------------------------------------------------------------------------------------------------

#----------------------------------------------------------Books--------------------------------------------------------
@app.route('/books/<book_title>', methods=['GET', 'POST'])
@login_required
def book(book_title):

    script=""

    book = Book.query.filter_by(title=book_title).first_or_404()

    book.title = book.title.replace("\uFFFD", "")
    db.session.commit()

    likes    = len(Post.query.filter(Post.book == book).filter(Post.level == 1).filter(Post.polarity == True).all())
    dislikes = len(Post.query.filter(Post.book == book).filter(Post.level == 1).filter(Post.polarity == False).all())

    page = request.args.get('page', 1, type=int)

    book_posts = book.posts.filter_by(level=1).order_by(Post.timestamp.desc()).paginate(
        page, app.config['POSTS_PER_PAGE'], False)


    next_url = url_for('book', book_title=book_title, page=book_posts.next_num) \
        if book_posts.has_next else None
    prev_url = url_for('book', book_title=book_title, page=book_posts.prev_num) \
        if book_posts.has_prev else None

    form_like = LikeBookForm()

    if form_like.submit_like.data and form_like.validate():
        post_form_action(form_like, 1, True, current_user, book, None)
        return redirect(url_for('book', book_title=book.title))


    form_dislike = DislikeBookForm()

    if form_dislike.submit_dislike.data and form_dislike.validate():
        post_form_action(form_dislike, 1, False, current_user, book, None)
        return redirect(url_for('book', book_title=book.title))

    form_agree = AgreePostForm()

    if form_agree.submit_agree.data and form_agree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_agree, parent.level+1, True, current_user, parent.book, parent)
        script = "window.location.hash = \"jump_to_post_"+ str(post_id) +"\";"

    form_disagree = DisagreePostForm()

    if form_disagree.submit_disagree.data and form_disagree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_disagree, parent.level + 1, False, current_user, parent.book, parent)
        script = "window.location.hash = \"jump_to_post_"+ str(post_id) +"\";"

    form_annotate = AnnotateForm()

    if form_annotate.submit_yes.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.supported_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_"+ str(post_id) +"\";"

    if form_annotate.submit_no.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.attacked_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_"+ str(post_id) +"\";"

    if form_annotate.submit_notsure.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.neither_by(current_user)
        db.session.commit()
        flash('You answered yes !')
        script = "window.location.hash = \"jump_to_post_"+ str(post_id) +"\";"

    form_filter = FilterPostsForm()

    if form_filter.submit_all.data and form_filter.validate():
        book_posts = book.posts.filter_by(level=1).order_by(Post.timestamp.desc()).paginate(
            page, app.config['POSTS_PER_PAGE'], False)
        return render_template('book.html', title=book_title, book=book,
                               book_posts=book_posts.items,
                               form_like=form_like, form_dislike=form_dislike,
                               form_agree=form_agree, form_disagree=form_disagree,
                               form_annotate=form_annotate, form_filter=form_filter,
                               next_url=next_url, prev_url=prev_url,
                               likes=likes, dislikes=dislikes,
                               script=script)

    if form_filter.submit_positive.data and form_filter.validate():
        book_posts = book.posts.filter(Post.level == 1).filter(Post.polarity == True)\
            .order_by(Post.timestamp.desc()).paginate(
            page, app.config['POSTS_PER_PAGE'], False)
        return render_template('book.html', title=book_title, book=book,
                               book_posts=book_posts.items,
                               form_like=form_like, form_dislike=form_dislike,
                               form_agree=form_agree, form_disagree=form_disagree,
                               form_annotate=form_annotate, form_filter=form_filter,
                               next_url=next_url, prev_url=prev_url,
                               likes=likes, dislikes=dislikes,
                               script=script)

    if form_filter.submit_negative.data and form_filter.validate():
        book_posts = book.posts.filter(Post.level == 1).filter(Post.polarity == False) \
            .order_by(Post.timestamp.desc()).paginate(
            page, app.config['POSTS_PER_PAGE'], False)
        return render_template('book.html', title=book_title, book=book,
                               book_posts=book_posts.items,
                               form_like=form_like, form_dislike=form_dislike,
                               form_agree=form_agree, form_disagree=form_disagree,
                               form_annotate=form_annotate, form_filter=form_filter,
                               next_url=next_url, prev_url=prev_url,
                               likes=likes, dislikes=dislikes,
                               script=script)

    if form_filter.submit_debates.data and form_filter.validate():
        book_posts = book.posts.filter(Post.level == 1).order_by(Post.timestamp.desc()).paginate(
            page, app.config['POSTS_PER_PAGE'], False)
        book_posts_items = []
        for p in book_posts.items:
            if p.children:
                book_posts_items.append(p)

        return render_template('book.html', title=book_title, book=book,
                               book_posts=book_posts_items,
                               form_like=form_like, form_dislike=form_dislike,
                               form_agree=form_agree, form_disagree=form_disagree,
                               form_annotate=form_annotate, form_filter=form_filter,
                               next_url=next_url, prev_url=prev_url,
                               likes=likes, dislikes=dislikes,
                               script=script)

    return render_template('book.html', title=book_title, book=book,
                           book_posts=book_posts.items,
                           form_like=form_like, form_dislike=form_dislike,
                           form_agree=form_agree, form_disagree=form_disagree,
                           form_annotate = form_annotate, form_filter=form_filter,
                           next_url=next_url, prev_url=prev_url,
                           likes=likes, dislikes=dislikes,
                           script=script)
#-----------------------------------------------------------------------------------------------------------------------

#-------------------------------------------------------Delete Post-----------------------------------------------------
@app.route('/books/<book_title>/delete_post_user/<post_id>', methods=['GET', 'POST'])
@login_required
def delete_post_user(book_title, post_id):

    book = Book.query.filter_by(title=book_title).first_or_404()
    post = Post.query.filter_by(id = post_id).first()

    db.session.delete(post)
    db.session.commit()
    flash('Your post is now deleted!')
    return redirect(url_for('book', book_title=book_title))

@app.route('/tree/delete_post_tree/<post_id>', methods=['GET', 'POST'])
@login_required
def delete_post_tree(post_id):

    post = Post.query.filter_by(id = post_id).first()

    db.session.delete(post)
    db.session.commit()
    flash('Your post is now deleted!')
    return redirect(url_for('tree_func', post_id=post_id))

@app.route('/user/<username>/delete_post_book/<post_id>', methods=['GET', 'POST'])
@login_required
def delete_post_book(username, post_id):

    user = User.query.filter_by(username=username).first_or_404()
    post = Post.query.filter_by(id = post_id).first()
    db.session.delete(post)
    db.session.commit()
    flash('Your post is now deleted!')
    return redirect(url_for('user', username=username))

@app.route('/index/delete_post_index/<post_id>', methods=['GET', 'POST'])
@login_required
def delete_post_index(post_id):

    post = Post.query.filter_by(id = post_id).first()

    db.session.delete(post)
    db.session.commit()
    flash('Your post is now deleted!')
    return redirect(url_for('index'))


#-----------------------------------------------------------------------------------------------------------------------

#------------------------------------------------------------Tree-------------------------------------------------------


def get_children(post, polarity):

    kids = []
    for child in post.children:
        if child.polarity is polarity :
            kids.append(child)
    return kids


def node(post, selected, visited, result):

    visited.append(post.id)

    if post in selected:
        if post.polarity:
            htmlclass = "HTMLclass: \"positive-selected popup\","
        else:
            htmlclass = "HTMLclass: \"negative-selected popup\","
    else:
        if post.polarity:
            htmlclass = "HTMLclass: \"positive popup\","
        else:
            htmlclass = "HTMLclass: \"negative popup\","

    onmouseover = "onmouseover: \"popup_toggler(\'" + str(post.id) + "-popup\')\","
    onmouseout = "onmouseout: \"popup_toggler(\'" + str(post.id) + "-popup\')\","

    if post.summary is not None:
        body_post = post.summary
    else:
        body_post = post.body
    body_post = body_post.replace("'", "\\\'")
    body_post = body_post.replace("\"", "\\\" ")
    innerHTML = "innerHTML: \'<span id=\"" + str(post.id) + "-popup\" class=\"popuptext\">"\
                + body_post[0:40] + "</span>\',"

    link = "link: {href: \"" + str(url_for('tree_func', post_id=post.id)) + "\"},"

    result += "{" + htmlclass + onmouseover + onmouseout + innerHTML + link

    children_negative = get_children(post, False)
    children_positive = get_children(post, True)

    if (children_negative is not None) or (children_positive is not None):
        result += "children: ["

        if children_negative is not None:

            for child in children_negative:
                if child.id not in visited:
                    result = node(child, selected, visited, result)

        if children_positive is not None:
            for child in children_positive:
                if child.id not in visited:
                    result = node(child, selected, visited, result)

        result += "],"

    if post in selected:
        if post.polarity is True:
            result += "connectors:{"\
                                "style: {"\
                                    "\'stroke\': \'#96BE5B\',"\
                                    "\'stroke-width\': 6,"\
                                "}"\
                            "},"
        else:
            result += "connectors:{" \
                      "style: {" \
                      "\'stroke\': \'#B84B46\'," \
                      "\'stroke-width\': 6," \
                      "}" \
                      "},"

    result += "},"

    return result



@app.route('/tree/<post_id>', methods=['GET', 'POST'])
@login_required
def tree_func(post_id):
    post = Post.query.filter_by(id=post_id).first()
    selected = [post]
    book_posts = [post]

    if post.parent is not None:
        while post.parent is not None:
            post = post.parent
            selected.append(post)

    book_title = post.book.title
    book_title = book_title.replace("'", "\\\'")
    book_title = book_title.replace("\"", "\\\" ")

    book_elem =\
        "{HTMLclass: \"neutral-selected popup\"," \
        "onmouseover: \"popup_toggler(\'" + str(post.book.id) + "-popup\')\"," \
        "onmouseout: \"popup_toggler(\'" + str(post.book.id) + "-popup\')\","\
        "innerHTML: \'<span id=\"" + str(post.book.id) + "-popup\" class=\"popuptext\">" + book_title[0:40] + "</span>\',"\
        "link: {href: \"" + str(url_for('book', book_title=post.book.title)) + "\"},"\
        "children: ["

    tree = \
        "function popup_toggler(id) {" \
        "var popup = document.getElementById(id);" \
        "popup.classList.toggle(\"show\");" \
        " }" \
        "var chart_config = {" \
           "chart: {" \
               "container:"+'"'+"#tree-container\"," \
               "connectors: {" \
                               "type: \"step\"," \
                               "style: {" \
                                       "\'stroke\': \'black\'," \
                                        "\'stroke-width\': 2," \
                               "}" \
               "}," \
           "}," \
           "nodeStructure: " + book_elem + node(post,selected, [], "") + "]}" + "};"

    form_agree = AgreePostForm()

    if form_agree.submit_agree.data and form_agree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_agree, parent.level + 1, True, current_user, parent.book, parent)

    form_disagree = DisagreePostForm()

    if form_disagree.submit_disagree.data and form_disagree.validate():
        post_id = int(request.form["post_id"])
        parent = Post.query.filter_by(id=post_id).first()
        post_form_action(form_agree, parent.level + 1, True, current_user, parent.book, parent)

    form_annotate = AnnotateForm()

    if form_annotate.submit_yes.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.supported_by(current_user)
        db.session.commit()
        flash('You answered yes !')

    if form_annotate.submit_no.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.attacked_by(current_user)
        db.session.commit()
        flash('You answered yes !')

    if form_annotate.submit_notsure.data and form_annotate.validate():
        post_id = int(request.form["post_id"])
        post = Post.query.filter_by(id=post_id).first()
        post.neither_by(current_user)
        db.session.commit()
        flash('You answered yes !')


    return render_template('tree.html', post=post, tree=tree, book_posts=book_posts,
                           form_agree=form_agree, form_disagree=form_disagree, form_annotate=form_annotate)
#-----------------------------------------------------------------------------------------------------------------------



#-------------------------------------------------------User------------------------------------------------------------
@app.route('/user/<username>', methods=['GET', 'POST'])
@login_required
def user(username):
    user = User.query.filter_by(username=username).first_or_404()
    books = [book for book in Book.query.all()]

    page = request.args.get('page', 1, type=int)
    user_posts = user.posts.order_by(Post.timestamp.desc()).paginate(
        page, app.config['POSTS_PER_PAGE'], False)
    next_url = url_for('user', username=user.username, page=user_posts.next_num) \
        if user_posts.has_next else None
    prev_url = url_for('user', username=user.username, page=user_posts.prev_num) \
        if user_posts.has_prev else None

    form = PhotoFormChoose()

    images = UploadSet('photos', IMAGES)
    configure_uploads(app, images)
    patch_request_class(app)

    if form.validate_on_submit():
        file = form.photo.data
        filename = str(secure_filename(file.filename))
        file.save(os.path.join(app.config['UPLOADED_PHOTOS_DEST'], file.filename))
        extension=filename.split(".")
        extension = str(extension[1])
        source = app.config['UPLOADED_PHOTOS_DEST'] + "/" + filename
        destination = app.config['UPLOADED_PHOTOS_DEST'] + "/" + str(user.id) + "." + extension
        os.rename(source, destination)
        user.img = "/static/images/profile/" + str(user.id) + "." + extension
        db.session.commit()
        return redirect(url_for('user', username=username))


    return render_template('user.html', title='Profile', user=user, books=books, user_posts=user_posts.items,
                           next_url=next_url, prev_url=prev_url, form=form)
#-----------------------------------------------------------------------------------------------------------------------


#----------------------------------------------------Edit Profile-------------------------------------------------------
@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(current_user.username)
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.about_me = form.about_me.data
        db.session.commit()
        flash('Your changes have been saved.')
        return redirect(url_for('user', username=current_user.username))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.about_me.data = current_user.about_me
    return render_template('edit_profile.html', title='Edit Profile',
                           form=form)
#-----------------------------------------------------------------------------------------------------------------------

#-----------------------------------------------------------Login-------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        next_page = request.args.get('next')
        if not next_page or url_parse(next_page).netloc != '':
            next_page = url_for('index')
        return redirect(next_page)
    return render_template('login.html', title='Sign In', form=form)
#-----------------------------------------------------------------------------------------------------------------------


#------------------------------------------------------------Logout-----------------------------------------------------
@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))
#-----------------------------------------------------------------------------------------------------------------------


#-----------------------------------------------------------Register----------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data, fake = False)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)
#-----------------------------------------------------------------------------------------------------------------------


#------------------------------------------------------Admin Register---------------------------------------------------
@app.route('/admin_register', methods=['GET', 'POST'])
def admin_register():
    if current_user.is_authenticated and current_user.admin:
        return redirect(url_for('index')) # should be admin
    form = AdminRegistrationForm()
    if form.validate_on_submit():
        send_admin_request_mail(form.username.data, form.email.data)
        flash('We will send you an email within a week with the instructions to access your admin request if you get approved')
        return redirect(url_for('login'))
    return render_template('admin_register_request.html', title = 'Request admin access', form=form)

@app.route('/approve_admin/<username>/<email>', methods=['GET', 'POST'])
def approve_admin(email, username):
    if current_user.is_authenticated and current_user.admin:
        return redirect(url_for('index')) # should be admin
    password = id_generator()
    user = User(username=username, email=email, fake = False, admin = True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash('Congratulations you have added {} as a new admin user!'.format(username))
    send_admin_credentials_mail(user, password)
    return redirect(url_for('login'))

#-----------------------------------------------------------------------------------------------------------------------

#------------------------------------------------------Change Password--------------------------------------------------
@app.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_password_reset_email(user)
        flash('Check your email for the instructions to reset your password')
        return redirect(url_for('login'))
    return render_template('reset_password_request.html',
                           title='Reset Password', form=form)

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    user = User.verify_reset_password_token(token)
    if not user:
        return redirect(url_for('index'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset.')
        return redirect(url_for('login'))
    return render_template('reset_password.html', form=form)
#-----------------------------------------------------------------------------------------------------------------------

#----------------------------------------------------Upload Photo-------------------------------------------------------
@app.route('/upload_photo', methods=['GET', 'POST'])
@login_required
def upload_photo():
    return  redirect(url_for('user', username=current_user.username))
#-----------------------------------------------------------------------------------------------------------------------

#----------------------------------------------------Follow&Unfollow----------------------------------------------------
@app.route('/follow/<book_id>')
@login_required
def follow(book_id):
    book = Book.query.filter_by(id=book_id).first()
    if book is None:
        flash('Book {} not found.'.format(book_id))
        return redirect(url_for('index'))
    current_user.follow(book)
    db.session.commit()
    flash('You are following {}!'.format(book.title))
    return redirect(url_for('book', book_title=book.title))

@app.route('/unfollow/<book_id>')
@login_required
def unfollow(book_id):
    book = Book.query.filter_by(id=book_id).first()
    if book is None:
        flash('Book {} not found.'.format(book_id))
        return redirect(url_for('index'))
    current_user.unfollow(book)
    db.session.commit()
    flash('You are not following {}.'.format(book.title))
    return redirect(url_for('book', book_title=book.title))
#-----------------------------------------------------------------------------------------------------------------------



#----------------------------------------------------Follow&Unfollow----------------------------------------------------
@app.route('/about')
def about():
    return render_template('about.html')
#-----------------------------------------------------------------------------------------------------------------------


#--------------------------------------------------------Predict--------------------------------------------------------


def tfidf(df_x, df_y):

    sent_diff = []

    if df_x:
        parent, child = df_x[0].split(" STOP ")
        sent_child = sentimentAnalysis(parent)['compound']
        sent_parent = sentimentAnalysis(child)['compound']
        if (sent_child < sent_parent):
            sent_diff.append(sent_parent - sent_child)
        else:
            sent_diff.append(sent_child - sent_parent)

    posts = Post.query.filter(Post.parent_id.isnot(None)).all()
    for p in posts:
        pair = p.parent.body + " STOP " + p.body
        df_x.append(pair)
        if (p.polarity is True):
            df_y.append(1)
        else:
            df_y.append(0)

        sent_child = sentimentAnalysis(p.parent.body)['compound']
        sent_parent = sentimentAnalysis(p.body)['compound']
        if (sent_child < sent_parent):
            sent_diff.append(sent_parent - sent_child)
        else:
            sent_diff.append(sent_child - sent_parent)

    sent_diff = pd.DataFrame(sent_diff)

    # posts = Post.query.filter(Post.overall == 5).order_by(func.random()).limit(
    #     1000).all()
    # for p in posts:
    #     pair = "The book" + p.book.title + "is good" + \
    #            " STOP " + p.body
    #     df_x.append(pair)
    #     df_y.append(1)
    #
    #     pair = "The book" + p.book.title + "is horrible" + \
    #            " STOP " + p.body
    #     df_x.append(pair)
    #     df_y.append(0)
    #
    # posts = Post.query.filter(Post.overall == 1).order_by(func.random()).limit(
    #     1000).all()
    # for p in posts:
    #     pair = "The book" + p.book.title + "is good" + \
    #            " STOP " + p.body
    #     df_x.append(pair)
    #     df_y.append(0)
    #     pair = "The book" + p.book.title + "is horrible" + \
    #            " STOP " + p.body
    #     df_x.append(pair)
    #     df_y.append(1)

    df_x = pd.DataFrame(df_x)[0]
    df_y = pd.DataFrame(df_y)[0]

    tfidf = TfidfVectorizer(min_df=1)
    DF_X = tfidf.fit_transform(df_x)

    # add sentiment feature to the sparse matrix of tfidf features
    DF_X = hstack((DF_X, np.array(sent_diff[0])[:, None]))
    DF_X = DF_X.tocsr()

    return df_x, df_y, DF_X

def prediction(parent_text, child_text, type):

    pair = parent_text + " STOP " + child_text

    df_x, df_y, model = tfidf([pair], [])

    if type is 'NuSMV':
        clf = NuSVC()
    elif type is 'LinearSMV':
        clf = LinearSVC()
    else:
        clf = DecisionTreeClassifier()

    clf.fit(model[1:], df_y)
    prediction = clf.predict(model[0]).tolist()
    if (prediction[0] is 0):
        return "Attack"
    else:
        return "Support"

def sentiment_predict(parent_text, child_text):

    sentiment_parent = sentimentAnalysis(parent_text)['compound']
    sentiment_child = sentimentAnalysis(child_text)['compound']

    if (sentiment_parent < 0 and sentiment_child < 0):
        return "Support"
    if (sentiment_parent > 0 and sentiment_child > 0):
        return "Support"
    else:
        return "Attack"

def cross_validation(type):

    f1 = 0
    acc = 0
    skf = StratifiedKFold(n_splits=8)

    df_x, df_y, model = tfidf([], [])
    df_x = model

    if type is 'NuSMV':
        clf = NuSVC()
    elif type is 'LinearSMV':
        clf = LinearSVC()
    else:
        clf = DecisionTreeClassifier()

    for train_index, test_index in skf.split(df_x, df_y):
        x_train, x_test = df_x[train_index], df_x[test_index]
        y_train, y_test = df_y[train_index], df_y[test_index]
        clf.fit(x_train, y_train)
        prediction = clf.predict(x_test)
        # print(classification_report(y_test, prediction))
        f1 += f1_score(y_test, prediction, average='weighted')
        acc += accuracy_score(y_test, prediction)

    return f1/8, acc/8


@app.route('/predict', methods=['GET', 'POST'])
def predict():
    result_LinearSVC = ""
    result_NuSVC = ""
    result_DecisionTree = ""
    result_sentiment = ""
    f1_LinearSVC, acc_LinearSVC = None, None
    f1_NuSVC, acc_NuSVC = None, None
    f1_DecisionTree, acc_DecisionTree = None, None


    form = PredictForm()

    if form.validate_on_submit():

        result_LinearSVC = prediction(form.parent_text.data,
                                   form.child_text.data,
                                   'LinearSVC')
        f1_LinearSVC, acc_LinearSVC = cross_validation('LinearSVC')

        result_NuSVC = prediction(form.parent_text.data,form.child_text.data,
                              'NuSVC')
        f1_NuSVC, acc_NuSVC = cross_validation('NuSVC')

        result_DecisionTree = prediction(form.parent_text.data,form.child_text.data,
                              'DecisionTree')
        f1_DecisionTree, acc_DecisionTree = cross_validation('DecisionTree')

        result_sentiment = sentiment_predict(form.parent_text.data,
                                      form.child_text.data)

        return render_template('predict.html',
                               result_LinearSVC=result_LinearSVC,
                               result_NuSVC=result_NuSVC,
                               result_DecisionTree=result_DecisionTree,
                               form=form,
                               f1_LinearSVC = f1_LinearSVC,
                               f1_DecisionTree = f1_DecisionTree,
                               f1_NuSVC = f1_NuSVC,
                               acc_LinearSVC =acc_LinearSVC,
                               acc_DecisionTree = acc_DecisionTree,
                               acc_NuSVC = acc_NuSVC,
                               result_sentiment = result_sentiment
                               )

    return render_template('predict.html',
                           result_LinearSVC = result_LinearSVC,
                           result_NuSVC=result_NuSVC,
                           result_DecisionTree = result_DecisionTree,
                           form = form,
                           f1_LinearSVC = f1_LinearSVC,
                           f1_DecisionTree = f1_DecisionTree,
                           f1_NuSVC = f1_NuSVC,
                           acc_LinearSVC =acc_LinearSVC,
                           acc_DecisionTree = acc_DecisionTree,
                           acc_NuSVC = acc_NuSVC,
                           result_sentiment = result_sentiment)


#-----------------------------------------------------------------------------------------------------------------------


