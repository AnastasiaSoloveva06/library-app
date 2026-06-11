import bleach
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash)
from flask_login import login_required, current_user

from extensions import db
from models import Book, Review

reviews_bp = Blueprint('reviews', __name__, url_prefix='/reviews')

ALLOWED_TAGS = list(bleach.sanitizer.ALLOWED_TAGS) + [
    'p','br','h1','h2','h3','h4','h5','h6',
    'pre','code','blockquote','ul','ol','li',
    'strong','em','a','table','thead','tbody','tr','th','td'
]
ALLOWED_ATTRS = {**bleach.sanitizer.ALLOWED_ATTRIBUTES, 'a': ['href','title']}

RATING_CHOICES = [(5,'Отлично'),(4,'Хорошо'),(3,'Удовлетворительно'),
                  (2,'Неудовлетворительно'),(1,'Плохо'),(0,'Ужасно')]


def sanitize(text):
    return bleach.clean(text, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS)


@reviews_bp.route('/book/<int:book_id>/add', methods=['GET', 'POST'])
@login_required
def add(book_id):
    book = Book.query.get_or_404(book_id)
    existing = Review.query.filter_by(book_id=book_id, user_id=current_user.id).first()
    if existing:
        flash('Вы уже оставляли рецензию на эту книгу', 'warning')
        return redirect(url_for('books.view', book_id=book_id))

    if request.method == 'POST':
        rating = request.form.get('rating')
        text = request.form.get('text', '').strip()

        if rating is None or not text:
            flash('Все поля обязательны', 'danger')
            return render_template('reviews/form.html', book=book,
                                   rating_choices=RATING_CHOICES,
                                   form_data=request.form)
        try:
            rating_int = int(rating)
            if rating_int not in range(0, 6):
                raise ValueError
        except ValueError:
            flash('Некорректная оценка', 'danger')
            return render_template('reviews/form.html', book=book,
                                   rating_choices=RATING_CHOICES,
                                   form_data=request.form)

        try:
            review = Review(book_id=book_id, user_id=current_user.id,
                            rating=rating_int, text=sanitize(text))
            db.session.add(review)
            db.session.commit()
            flash('Рецензия успешно добавлена', 'success')
            return redirect(url_for('books.view', book_id=book_id))
        except Exception:
            db.session.rollback()
            flash('При сохранении рецензии возникла ошибка', 'danger')

    return render_template('reviews/form.html', book=book,
                           rating_choices=RATING_CHOICES, form_data={})

@reviews_bp.route('/<int:review_id>/delete', methods=['POST'])
@login_required
def delete(review_id):
    if not current_user.is_moderator():
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    review = Review.query.get_or_404(review_id)
    book_id = review.book_id
    try:
        db.session.delete(review)
        db.session.commit()
        flash('Рецензия успешно удалена', 'success')
    except Exception:
        db.session.rollback()
        flash('Ошибка при удалении рецензии', 'danger')
    return redirect(url_for('books.view', book_id=book_id))
