import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-key")

from main import create_app
from src.config import TestConfig
from src.models.user import db


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
