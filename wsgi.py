"""WSGI entry for gunicorn / production."""
from app import create_app

app = create_app()
