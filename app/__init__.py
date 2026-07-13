
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'smartgarbage2024'
    
    # Check if running on Render production cloud vs local machine
    if os.environ.get('RENDER'):
        # Save SQLite db and image uploads directly to Render's persistent disk volume
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////data/garbage.db'
        app.config['UPLOAD_FOLDER'] = '/data/uploads'
    else:
        # Fallback local settings for development computer environment
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///garbage.db'
        app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
    
    # Ensure the target upload directory is systematically created
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    db.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    with app.app_context():
        db.create_all()

    return app
