from functools import wraps
from flask import session, redirect, url_for, abort
from werkzeug.exceptions import Forbidden


def roles_required(*allowed_roles):
    """Generalized role gate. Usage: @roles_required('admin', 'worker')."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('main.login'))
            if session.get('mfa_pending'):
                return redirect(url_for('main.mfa_verify'))
            if session.get('role') not in allowed_roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('main.login'))
        if session.get('mfa_pending'):
            return redirect(url_for('main.mfa_verify'))
        return f(*args, **kwargs)
    return wrapped


def admin_required(f):
    return roles_required('admin')(f)


def worker_required(f):
    return roles_required('worker')(f)


def superadmin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('main.login'))
        from .models import User
        user = User.query.get(session['user_id'])
        if not user or not user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return wrapped
