import os
import hashlib
import uuid
from datetime import datetime

import bleach
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, current_app, session)
from flask_login import login_required, current_user

from extensions import db
from models import Book, Genre, Cover, ViewLog

books_bp = Blueprint('books', __name__, url_prefix='/books')

ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p','br','h1','h2','h3','h4','h5','h6',
    'pre','code','blockquote','ul','ol','li',
    'strong','em','a','img','table','thead','tbody','tr','th','td'
]
# Разрешённые атрибуты для тегов
ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES,
                 'img': ['src','alt'], 'a': ['href','title']}
# Допустимые MIME-типы для загружаемых обложек книг
ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp'}


def sanitize(text):
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


def _record_view(book_id):
    today = datetime.utcnow().date()
    start = datetime(today.year, today.month, today.day)
    end = start.replace(hour=23, minute=59, second=59)

    if current_user.is_authenticated:
        count = ViewLog.query.filter(
            ViewLog.book_id == book_id,
            ViewLog.user_id == current_user.id,
            ViewLog.viewed_at >= start,
            ViewLog.viewed_at <= end
        ).count()
        if count < 10:
            db.session.add(ViewLog(book_id=book_id, user_id=current_user.id,
                                   viewed_at=datetime.utcnow()))
    else:
        sid = session.get('_id')
        if not sid:
            sid = str(uuid.uuid4())
            session['_id'] = sid
        count = ViewLog.query.filter(
            ViewLog.book_id == book_id,
            ViewLog.session_id == sid,
            ViewLog.viewed_at >= start,
            ViewLog.viewed_at <= end
        ).count()
        if count < 10:
            db.session.add(ViewLog(book_id=book_id, session_id=sid,
                                   viewed_at=datetime.utcnow()))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

    recent = session.get('recent_books', [])
    if book_id in recent:
        recent.remove(book_id)
    recent.insert(0, book_id)
    session['recent_books'] = recent[:5]
    session.modified = True


@books_bp.route('/<int:book_id>')
def view(book_id):
    book = Book.query.get_or_404(book_id)
    _record_view(book_id)

    from models import Review
    user_review = None
    can_review = False
    if current_user.is_authenticated:
        user_review = Review.query.filter_by(
            book_id=book_id, user_id=current_user.id).first()
        can_review = not user_review

    reviews = Review.query.filter_by(book_id=book_id).order_by(Review.created_at.desc()).all()

    return render_template('books/view.html', book=book,
                           reviews=reviews, user_review=user_review,
                           can_review=can_review)


@books_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    if not current_user.is_admin():
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    genres = Genre.query.order_by(Genre.name).all()
    if request.method == 'POST':
        return _save_book(None, genres)
    return render_template('books/form.html', book=None, genres=genres,
                           mode='add', form_data={})


@books_bp.route('/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(book_id):
    if not current_user.is_moderator():
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    book = Book.query.get_or_404(book_id)
    genres = Genre.query.order_by(Genre.name).all()
    if request.method == 'POST':
        return _save_book(book, genres)
    return render_template('books/form.html', book=book, genres=genres,
                           mode='edit', form_data={})


def _save_book(book, genres):
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    year_str = request.form.get('year', '').strip()
    publisher = request.form.get('publisher', '').strip()
    author = request.form.get('author', '').strip()
    pages_str = request.form.get('pages', '').strip()
    genre_ids = request.form.getlist('genres')
    is_new = book is None

    errors = []
    if not title: errors.append('Название обязательно')
    if not description: errors.append('Описание обязательно')
    if not year_str or not year_str.lstrip('-').isdigit(): errors.append('Год должен быть числом')
    if not publisher: errors.append('Издательство обязательно')
    if not author: errors.append('Автор обязателен')
    if not pages_str or not pages_str.isdigit(): errors.append('Объём должен быть числом')
    if not genre_ids: errors.append('Выберите хотя бы один жанр')

    cover_file = request.files.get('cover')
    if is_new and (not cover_file or cover_file.filename == ''):
        errors.append('Обложка обязательна при добавлении книги')

    if errors:
        flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')
        for e in errors:
            flash(e, 'warning')
        return render_template('books/form.html', book=book, genres=genres,
                               mode='add' if is_new else 'edit',
                               form_data=request.form)

    clean_desc = sanitize(description)

    try:
        if is_new:
            book = Book(title=title, description=clean_desc,
                        year=int(year_str), publisher=publisher,
                        author=author, pages=int(pages_str))
            db.session.add(book)
            db.session.flush()
        else:
            book.title = title
            book.description = clean_desc
            book.year = int(year_str)
            book.publisher = publisher
            book.author = author
            book.pages = int(pages_str)

        selected_genres = Genre.query.filter(Genre.id.in_(genre_ids)).all()
        book.genres = selected_genres

        if is_new and cover_file and cover_file.filename:
            mime = cover_file.mimetype
            if mime not in ALLOWED_MIMES:
                raise ValueError('Недопустимый тип файла')
            file_data = cover_file.read()
            md5 = hashlib.md5(file_data).hexdigest()

            existing = Cover.query.filter_by(md5_hash=md5).first()
            if existing:
                cover = Cover(filename=existing.filename, mime_type=mime,
                              md5_hash=md5, book_id=book.id)
                db.session.add(cover)
            else:
                cover = Cover(filename='', mime_type=mime, md5_hash=md5, book_id=book.id)
                db.session.add(cover)
                db.session.flush()
                ext = mime.split('/')[-1].replace('jpeg', 'jpg')
                filename = f'{cover.id}.{ext}'
                cover.filename = filename
                upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                with open(upload_path, 'wb') as f:
                    f.write(file_data)

            book.cover = cover

        db.session.commit()
        flash(f'Книга «{book.title}» успешно сохранена', 'success')
        return redirect(url_for('books.view', book_id=book.id))

    except Exception as e:
        db.session.rollback()
        flash('При сохранении данных возникла ошибка. Проверьте корректность введённых данных.', 'danger')
        return render_template('books/form.html', book=book, genres=genres,
                               mode='add' if is_new else 'edit',
                               form_data=request.form)


@books_bp.route('/<int:book_id>/delete', methods=['POST'])
@login_required
def delete(book_id):
    if not current_user.is_admin():
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    book = Book.query.get_or_404(book_id)
    title = book.title

    if book.cover:
        path = os.path.join(current_app.config['UPLOAD_FOLDER'], book.cover.filename)
        if os.path.exists(path):
            os.remove(path)

    try:
        db.session.delete(book)
        db.session.commit()
        flash(f'Книга «{title}» успешно удалена', 'success')
    except Exception:
        db.session.rollback()
        flash('Ошибка при удалении книги', 'danger')

    return redirect(url_for('index'))
