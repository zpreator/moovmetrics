import logging
import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from requests.adapters import HTTPAdapter
from stravalib import Client

logger = logging.getLogger("moovmetrics")

# Quick dictionary for getting common race names and distances
RACES = [
    {'name': '1/2 mile', 'distance': 804.67},
    {'name': '1k', 'distance': 1000},
    {'name': '1 mile', 'distance': 1609.34},
    {'name': '2 mile', 'distance': 1609.34*2},
    {'name': '5k', 'distance': 5000},
    {'name': '10k', 'distance': 10000},
    {'name': '15k', 'distance': 15000},
    {'name': '10 mile', 'distance': 1609.34*10},
    {'name': 'half marathon', 'distance': 21097.5},
    {'name': 'marathon', 'distance': 21097.5*2}
]

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
db_dir = os.path.join(basedir,"db", "site.db")
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_dir}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # Disable track modifications to save resources


# Initialize sqlite DB
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Initialize Strava client with a 30-second timeout on all API calls
class _TimeoutAdapter(HTTPAdapter):
    def send(self, request, **kwargs):
        kwargs.setdefault("timeout", 30)
        return super().send(request, **kwargs)

client = Client()
_adapter = _TimeoutAdapter()
client.protocol.rsession.mount("https://", _adapter)
client.protocol.rsession.mount("http://", _adapter)

from app import routes  # noqa
from app.models import *

# Ensure all model tables exist (safe to call even on an existing DB).
# db.create_all() is idempotent: it only creates tables that are missing,
# and never drops or modifies existing ones.
def create_db_if_not_exists():
    os.makedirs(os.path.dirname(db_dir), exist_ok=True)
    with app.app_context():
        db.create_all()

create_db_if_not_exists()