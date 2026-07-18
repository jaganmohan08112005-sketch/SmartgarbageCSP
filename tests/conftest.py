import sys
import os
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

@pytest.fixture
def app():
    from app import create_app, db
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{path}'
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
    os.remove(path)

@pytest.fixture
def client(app):
    return app.test_client()