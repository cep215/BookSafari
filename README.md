# BookSafari

BookSafari is a research web app for collecting **book reviews** and turning them into **structured argumentative dialogues** to support **argument mining** / NLP dataset creation.

This repo is associated with the BookSafari paper:
- https://spiral.imperial.ac.uk/entities/publication/a5c8a7ef-4ca0-4ee5-a2d3-f0d4cd0c183c

---

## What this repo contains

- A **Flask** web app for browsing/creating content (book reviews, posts, users)
- **Elasticsearch** indexing for search
- A relational DB via Flask-Migrate (Alembic)

> Note: The original setup uses Elasticsearch 6.x (based on the install commands in the existing README).

---

## Architecture (high level)

**Browser → Flask app → DB**  
**Flask app → Elasticsearch** (for indexing + search)

---

## Quickstart (local dev)

### 1) Create a virtualenv + install deps

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=book-reviews.py
