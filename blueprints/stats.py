import csv
import io
from datetime import datetime

from flask import (Blueprint, render_template, request,
                   flash, redirect, url_for, make_response)
from flask_login import login_required, current_user
from sqlalchemy import func

from extensions import db
from models import Book, ViewLog, User

stats_bp = Blueprint('stats', __name__, url_prefix='/stats')


def _require_admin():
    if not current_user.is_authenticated or not current_user.is_admin():
        flash('У вас недостаточно прав для выполнения данного действия', 'danger')
        return redirect(url_for('index'))
    return None


@stats_bp.route('/')
@login_required
def index():
    guard = _require_admin()
    if guard: return guard

    tab = request.args.get('tab', 'log')
    log_page = request.args.get('log_page', 1, type=int)
    log_per_page = 10
    stats_page = request.args.get('stats_page', 1, type=int)
    stats_per_page = 10
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')

    log_q = (db.session.query(ViewLog, Book, User)
             .join(Book, Book.id == ViewLog.book_id)
             .outerjoin(User, User.id == ViewLog.user_id)
             .order_by(ViewLog.viewed_at.desc()))
    log_total = log_q.count()
    log_entries = log_q.offset((log_page-1)*log_per_page).limit(log_per_page).all()

    stats_q = (db.session.query(Book, func.count(ViewLog.id).label('views'))
               .join(ViewLog, ViewLog.book_id == Book.id)
               .filter(ViewLog.user_id.isnot(None)))
    if date_from_str:
        try:
            df = datetime.strptime(date_from_str, '%Y-%m-%d')
            stats_q = stats_q.filter(ViewLog.viewed_at >= df)
        except ValueError: pass
    if date_to_str:
        try:
            dt = datetime.strptime(date_to_str, '%Y-%m-%d').replace(hour=23,minute=59,second=59)
            stats_q = stats_q.filter(ViewLog.viewed_at <= dt)
        except ValueError: pass
    stats_q = stats_q.group_by(Book.id).order_by(func.count(ViewLog.id).desc())
    stats_total = stats_q.count()
    stats_entries = stats_q.offset((stats_page-1)*stats_per_page).limit(stats_per_page).all()

    return render_template('stats/index.html',
                           tab=tab,
                           log_entries=log_entries, log_page=log_page,
                           log_total=log_total, log_per_page=log_per_page,
                           stats_entries=stats_entries, stats_page=stats_page,
                           stats_total=stats_total, stats_per_page=stats_per_page,
                           date_from=date_from_str, date_to=date_to_str)


@stats_bp.route('/export/log')
@login_required
def export_log():
    guard = _require_admin()
    if guard: return guard
    entries = (db.session.query(ViewLog, Book, User)
               .join(Book, Book.id == ViewLog.book_id)
               .outerjoin(User, User.id == ViewLog.user_id)
               .order_by(ViewLog.viewed_at.desc()).all())
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['№','ФИО пользователя','Название книги','Дата и время просмотра'])
    for i,(log,book,user) in enumerate(entries,1):
        name = user.full_name if user else 'Неаутентифицированный пользователь'
        writer.writerow([i, name, book.title, log.viewed_at.strftime('%d.%m.%Y %H:%M:%S')])
    today = datetime.utcnow().strftime('%Y-%m-%d')
    resp = make_response('\ufeff' + output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=user_actions_log_{today}.csv'
    return resp


@stats_bp.route('/export/stats')
@login_required
def export_stats():
    guard = _require_admin()
    if guard: return guard
    date_from_str = request.args.get('date_from', '')
    date_to_str = request.args.get('date_to', '')
    stats_q = (db.session.query(Book, func.count(ViewLog.id).label('views'))
               .join(ViewLog, ViewLog.book_id == Book.id)
               .filter(ViewLog.user_id.isnot(None)))
    if date_from_str:
        try:
            df = datetime.strptime(date_from_str, '%Y-%m-%d')
            stats_q = stats_q.filter(ViewLog.viewed_at >= df)
        except ValueError: pass
    if date_to_str:
        try:
            dt = datetime.strptime(date_to_str, '%Y-%m-%d').replace(hour=23,minute=59,second=59)
            stats_q = stats_q.filter(ViewLog.viewed_at <= dt)
        except ValueError: pass
    entries = stats_q.group_by(Book.id).order_by(func.count(ViewLog.id).desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['№','Название книги','Количество просмотров'])
    for i,(book,views) in enumerate(entries,1):
        writer.writerow([i, book.title, views])
    today = datetime.utcnow().strftime('%Y-%m-%d')
    resp = make_response('\ufeff' + output.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename=book_views_stats_{today}.csv'
    return resp



