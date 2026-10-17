import functools

from flask import (
    Blueprint, abort, flash, g, redirect, render_template, request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db

bp = Blueprint("auth", __name__)

HOME_BY_ROLE = {
    "admin": "admin.dashboard",
    "technician": "tech.queue",
    "customer": "customer.my_devices",
}


def hash_password(password):
    return generate_password_hash(password)


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)
        ).fetchone()
        if g.user is None:
            session.clear()


def login_required(*roles):
    """Require a logged-in user, optionally with one of the given roles."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.path))
            if roles and g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)
        return wrapped
    return decorator


@bp.route("/")
def index():
    if g.user is None:
        return redirect(url_for("auth.login"))
    return redirect(url_for(HOME_BY_ROLE[g.user["role"]]))


@bp.route("/login", methods=("GET", "POST"))
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("שם משתמש או סיסמה שגויים", "error")
        else:
            session.clear()
            session["user_id"] = user["id"]
            next_url = request.args.get("next")
            # Only follow local paths, never another site.
            if next_url and next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("auth.index"))
    return render_template("login.html")


@bp.route("/logout", methods=("POST",))
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
