Get Started
	$ pip install virtualenv
	$ virtualvenv venv
	$ source venv/bin/activate
	$ pip install -r requirements.txt
	$ export FLASK_APP=book-reviews.py

ELASTICSEARCH
    $ wget -qO - https://artifacts.elastic.co/GPG-KEY-elasticsearch | sudo apt-key add -
    $ sudo apt-get install apt-transport-https
    $ echo "deb https://artifacts.elastic.co/packages/6.x/apt stable main" | sudo tee -a /etc/apt/sources.list.d/elastic-6.x.list
    $ sudo apt-get update && sudo apt-get install elasticsearch
    $ sudo service elasticsearch start
    $ flask shell
        Book.reindex()

VM:
    $ flask run -h 0.0.0.0 -p 80

Supervisor:
    $ pip install gunicorn
    $ sudo apt-get supervisor
    $ echo "export FLASK_APP=book-reviews.py" >> ~/.profile
    $ vim /etc/supervisor/conf.d/book-reviews.conf

[program:book-reviews]
command=/book-reviews/venv/bin/gunicorn -b 0.0.0.0:80 -w 4 book-reviews:app
directory=/book-reviews
user=root
autostart=true
autorestart=true
stopasgroup=true
killasgroup=true

    $ sudo supervisord -c /etc/supervisor/supervisord.conf
    $ service supervisor start
    $ sudo supervisorctl -c /etc/supervisor/supervisord.conf
    $ sudo supervisorctl reload
    $ sudo unlink /var/run/supervisor.sock


DB
	$ flask db init
	$ flask db migrate -m "..."
	$ flask db upgrade

	Delete elements in DB
		>>> users = User.query.all()
		>>> for u in users:
		...     db.session.delete(u)
		...
		>>> posts = Post.query.all()
		>>> for p in posts:
		...     db.session.delete(p)
		...
		>>> db.session.commit()

# TravelportPredictiveAnalysisTool
