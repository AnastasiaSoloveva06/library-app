import os
import hashlib
import csv
import io
from datetime import datetime, timedelta

import bleach
import markdown
from flask import Flask, render_template, request, redirect, url_for, flash, session

from extensions import db, login_manager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'covers')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'supersecretkey-library-2024'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(BASE_DIR, "library.db")}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

    db.init_app(app)
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
        'p','br','h1','h2','h3','h4','h5','h6',
        'pre','code','blockquote','ul','ol','li',
        'strong','em','a','img','table','thead','tbody','tr','th','td'
    ]
    ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES,
                     'img': ['src','alt'], 'a': ['href','title']}

    def md_to_html(text):
        raw = markdown.markdown(text or '', extensions=['extra','nl2br'])
        return bleach.clean(raw, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)

    app.jinja_env.globals['md_to_html'] = md_to_html

    from blueprints.auth import auth_bp
    from blueprints.books import books_bp
    from blueprints.reviews import reviews_bp
    from blueprints.stats import stats_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(stats_bp)

    @app.route('/')
    def index():
        from models import Book, Review, ViewLog
        from sqlalchemy import func

        page = request.args.get('page', 1, type=int)
        per_page = 10

        books_q = (Book.query
                   .outerjoin(Review)
                   .group_by(Book.id)
                   .add_columns(
                       func.coalesce(func.avg(Review.rating), 0).label('avg_rating'),
                       func.count(Review.id).label('review_count')
                   )
                   .order_by(Book.year.desc(), Book.id.desc()))

        pagination = books_q.paginate(page=page, per_page=per_page, error_out=False)
        books = pagination.items

        three_months_ago = datetime.utcnow() - timedelta(days=90)
        popular = (db.session.query(Book, func.count(ViewLog.id).label('views'))
                   .join(ViewLog, ViewLog.book_id == Book.id)
                   .filter(ViewLog.viewed_at >= three_months_ago)
                   .group_by(Book.id)
                   .order_by(func.count(ViewLog.id).desc())
                   .limit(5)
                   .all())

        recent_ids = session.get('recent_books', [])
        recent_books = []
        if recent_ids:
            id_order = {v: i for i, v in enumerate(recent_ids)}
            recent_books = Book.query.filter(Book.id.in_(recent_ids)).all()
            recent_books.sort(key=lambda b: id_order.get(b.id, 999))

        return render_template('index.html',
                               books=books,
                               pagination=pagination,
                               popular=popular,
                               recent_books=recent_books)

    return app


def init_db(app):
    with app.app_context():
        from models import Role, User, Genre
        from werkzeug.security import generate_password_hash
        db.create_all()

        if not Role.query.first():
            roles = [
                Role(name='Администратор', description='Суперпользователь, имеет полный доступ к системе'),
                Role(name='Модератор', description='Может редактировать данные книг и производить модерацию рецензий'),
                Role(name='Пользователь', description='Может оставлять рецензии'),
            ]
            db.session.add_all(roles)
            db.session.commit()

        if not User.query.first():
            admin_role = Role.query.filter_by(name='Администратор').first()
            mod_role = Role.query.filter_by(name='Модератор').first()
            user_role = Role.query.filter_by(name='Пользователь').first()

            users = [
                User(login='admin', password_hash=generate_password_hash('admin123'),
                     last_name='Иванов', first_name='Иван', middle_name='Иванович',
                     role_id=admin_role.id),
                User(login='moderator', password_hash=generate_password_hash('mod123'),
                     last_name='Петров', first_name='Пётр', middle_name='Петрович',
                     role_id=mod_role.id),
                User(login='user', password_hash=generate_password_hash('user123'),
                     last_name='Сидорова', first_name='Мария', middle_name='Петровна',
                     role_id=user_role.id),
            ]
            db.session.add_all(users)
            db.session.commit()

        if not Genre.query.first():
            genres = ['Роман', 'Фантастика', 'Детектив', 'Поэзия',
                      'История', 'Биография', 'Приключения', 'Ужасы',
                      'Научная литература', 'Классика']
            db.session.add_all([Genre(name=g) for g in genres])
            db.session.commit()


if __name__ == '__main__':
    app = create_app()
    init_db(app)
    app.run(debug=True, port=5000)