import ast
import pandas as pd
import json
from app import app
from app import db
from app.models import User, Post, Book
import math
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

def sentimentAnalysis(stringToBeAnnotated):

    analyzer = SentimentIntensityAnalyzer()
    result = analyzer.polarity_scores(stringToBeAnnotated)
    return result




with app.app_context():
    with open('datasets/genre.json') as f:
        data = json.load(f)

    genre = pd.DataFrame(data)

    #selecting categories
    genre = genre[~ ((pd.to_numeric(genre.category_id) < 2) |
                     ((pd.to_numeric(genre.category_id) > 2) &
                      (pd.to_numeric(genre.category_id) < 15)) |
                     ((pd.to_numeric(genre.category_id) > 15) &
                      (pd.to_numeric(genre.category_id) < 17)) |
                     ((pd.to_numeric(genre.category_id) > 17) &
                      (pd.to_numeric(genre.category_id) < 21)) |
                     ((pd.to_numeric(genre.category_id) > 22) &
                      (pd.to_numeric(genre.category_id) < 24)) |
                     (pd.to_numeric(genre.category_id) > 24))]


    for index, row in genre.iterrows():
        if not Book.query.filter_by(title=row['title']).first():
            b = Book(title=row['title'], author=row['author'],
                     imUrl=row['imUrl'], genre=row['category'])
            db.session.add(b)
            db.session.commit()



    with open('datasets/reviews_Books.json') as f:
        for i in range(0, 22507155):

            review = json.loads(f.readline())

                if (review['overall'] != '3' and len(review['reviewText']) < 500):

                    genre_item = genre.index.where(
                        genre.filename == (review['asin']+".jpg")).max()

                    if not (math.isnan(genre_item)):

                        if not Book.query.filter_by(
                                title=genre.title[genre_item]).first():
                            b = Book(title=genre.title[genre_item],
                                     author=genre.author[genre_item],
                                     imUrl=genre.imUrl[genre_item],
                                     genre=genre.category[genre_item],
                                     asin = review['asin'])
                            db.session.add(b)
                            db.session.commit()

                        if 'reviewerName' in review:
                            if not User.query.filter_by(
                                    username=review['reviewerName']).first():
                                u = User(username=review['reviewerName'],
                                         email=(review['reviewerName'] +
                                                '@example.com'),
                                         fake = True)
                                db.session.add(u)
                                db.session.commit()

                        if ('reviewerName' in review) and genre.title[genre_item]:
                            user = User.query.filter_by(
                                username=review['reviewerName']).first()
                            book = Book.query.filter_by(
                                title=genre.title[genre_item]).first()
                            book.asin = review['asin']
                            db.session.commit()

                            #Calculate polarity based on overall score and
                            # sentiment analysis score

                            polarity = True

                            #Sentiment analysis score
                            sentiment = sentimentAnalysis(review['reviewText'])
                            sentiment = sentiment['compound']
                            if (sentiment < 0): sentiment = False
                            elif (sentiment > 0): sentiment = True

                            #Overall score
                            overall = int(review['overall'])
                            if (overall < 3): overall = False
                            elif (sentiment > 3): overall = True

                            #Relatedness
                            if (overall == sentiment):
                                polarity = sentiment

                                p = Post(body=review['reviewText'],
                                         level=1,
                                         summary=review['summary'],
                                         overall=float(review['overall']),
                                         polarity=polarity,
                                         timestamp=datetime.fromtimestamp(
                                             review['unixReviewTime']), user=user,
                                         book=book)

                                db.session.add(p)
                                db.session.commit()

    with open('datasets/meta_Books.json') as f:
        for i in range(1, 2370585):

            line = f.readline()
            json_data = ast.literal_eval(line)
            description = json.loads(json.dumps(json_data))
            book = Book.query.filter_by(asin=description['asin']).first()

            if book is not None :
                if 'description' in description:
                    book.description = description['description']
                    db.session.commit()
