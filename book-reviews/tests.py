from datetime import datetime, timedelta
import unittest
from app import app, db
from app.models import User, Post, Book
from elasticsearch import Elasticsearch
from config import Config

with app.app_context():
    class PasswordandAvatarCase(unittest.TestCase):

        def setUp(self):
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
            app.config['ELASTICSEARCH_URL'] = 'http://localhost:9200'
            app.elasticsearch = Elasticsearch([app.config['ELASTICSEARCH_URL']])
            db.create_all()

        def tearDown(self):
            db.session.remove()
            db.drop_all()

        def test_password_hashing(self):
            u = User(username='susan')
            u.set_password('cat')
            self.assertFalse(u.check_password('dog'))
            self.assertTrue(u.check_password('cat'))

        def test_avatar(self):
            u = User(username='john', email='john@example.com')
            self.assertEqual(u.avatar(128), ('https://www.gravatar.com/avatar/'
                                             'd4c74594d841139328695756648b6bd6'
                                             '?d=identicon&s=128'))


    class FollowBooksCase(unittest.TestCase):

        def setUp(self):
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
            app.config['ELASTICSEARCH_URL'] = 'http://localhost:9200'
            app.elasticsearch = Elasticsearch([app.config['ELASTICSEARCH_URL']])
            db.create_all()

        def tearDown(self):
            db.session.remove()
            db.drop_all()

        def test_password_hashing(self):
            u = User(username='susan')
            u.set_password('cat')
            self.assertFalse(u.check_password('dog'))
            self.assertTrue(u.check_password('cat'))

        def test_avatar(self):
            u = User(username='john', email='john@example.com')
            self.assertEqual(u.avatar(128), ('https://www.gravatar.com/avatar/'
                                             'd4c74594d841139328695756648b6bd6'
                                             '?d=identicon&s=128'))

        def test_follow(self):
            u1 = User(username='john', email='john@example.com')
            b1 = Book(title='Gone with the wind', author='Margaret Mitchell')

            db.session.add(u1)
            db.session.add(b1)

            db.session.commit()

            self.assertEqual(u1.books.all(), [])
            self.assertEqual(b1.users.all(), [])

            u1.follow(b1)
            db.session.commit()
            self.assertTrue(u1.is_following(b1))
            self.assertEqual(u1.books.count(), 1)
            self.assertEqual(u1.books.first().title, 'Gone with the wind')
            self.assertEqual(b1.users.count(), 1)
            self.assertEqual(b1.users.first().username, 'john')

            u1.unfollow(b1)
            db.session.commit()
            self.assertFalse(u1.is_following(b1))
            self.assertEqual(u1.books.count(), 0)
            self.assertEqual(b1.users.count(), 0)

        def test_follow_posts(self):
            # create users and books
            u1 = User(username='john', email='john@example.com')
            u2 = User(username='susan', email='susan@example.com')
            u3 = User(username='mary', email='mary@example.com')
            u4 = User(username='david', email='david@example.com')
            b1 = Book(title='Gone with the wind', author='Margaret Mitchell')
            b2 = Book(title='A tale of 2 cities', author='Charles Dickens')
            b3 = Book(title='Conspiration', author='Dan Brown')

            db.session.add(u1)
            db.session.add(u2)
            db.session.add(u3)
            db.session.add(u4)
            db.session.add(b1)
            db.session.add(b2)
            db.session.add(b3)

            db.session.commit()

            # create four posts
            now = datetime.utcnow()
            p1 = Post(body="post from john", user=u1, book=b1,
                      timestamp=now + timedelta(seconds=1), level=1)
            p2 = Post(body="post from susan", user=u2, book=b2,
                      timestamp=now + timedelta(seconds=4), level=1)
            p3 = Post(body="post from mary", user=u3, book=b2,
                      timestamp=now + timedelta(seconds=3), level=1)
            p4 = Post(body="post from david", user=u4, book=b3,
                      timestamp=now + timedelta(seconds=2), level=1)
            db.session.add_all([p1, p2, p3, p4])
            db.session.commit()

            # setup the followers
            u1.follow(b1)
            u1.follow(b2)
            u1.follow(b3)
            u2.follow(b1)
            db.session.commit()

            # check the followed posts of each user
            f1 = u1.followed_posts().all()
            f2 = u2.followed_posts().all()

            self.assertEqual(f1, [p2, p3, p4, p1])
            self.assertEqual(f2, [p1])

    class AnnotatePostsCase(unittest.TestCase):

        def setUp(self):
            app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
            app.config['ELASTICSEARCH_URL'] = 'http://localhost:9200'
            app.elasticsearch = Elasticsearch([app.config['ELASTICSEARCH_URL']])
            db.create_all()

        def tearDown(self):
            db.session.remove()
            db.drop_all()

        def testSupport(self):
            u1 = User(username='john', email='john@example.com')
            u2 = User(username='susan', email='susan@example.com')
            b1 = Book(title='Gone with the wind', author='Margaret Mitchell')
            p1 = Post(body="post from john", user=u1, book=b1, polarity=True)

            db.session.add(u1)
            db.session.add(u2)


            db.session.add(p1)

            db.session.commit()

            p1.supported_by(u2)
            db.session.commit()

            self.assertTrue(p1.was_answered_by(u2))
            self.assertEqual(p1.nr_of_supports, 1)

    if __name__ == '__main__':
        unittest.main(verbosity=2)
