from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import User

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        login_val = request.form.get('login', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(login=login_val).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            session.pop('recent_books', None)
            session.pop('_id', None)
            next_page = request.args.get('next') or url_for('index')
            return redirect(next_page)
        flash('Невозможно аутентифицироваться с указанными логином и паролем', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('recent_books', None)
    session.pop('_id', None)
    return redirect(request.referrer or url_for('index'))
