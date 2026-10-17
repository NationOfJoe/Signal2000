import os
import secrets

from flask import Flask, abort, render_template, request, session

from . import constants


def _load_secret_key(instance_path):
    """Keep one random key per installation so sessions survive restarts."""
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    app.config.from_mapping(
        DATABASE=os.path.join(app.instance_path, "signal2000.sqlite"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config is not None:
        app.config.update(test_config)
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("SIGNAL2000_SECRET_KEY") or _load_secret_key(
            app.instance_path
        )

    from . import db
    db.init_app(app)

    from . import auth, admin, tech, customer, cli
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(tech.bp)
    app.register_blueprint(customer.bp)
    cli.init_app(app)

    @app.before_request
    def check_csrf():
        if request.method == "POST" and not app.config.get("TESTING_SKIP_CSRF"):
            token = session.get("csrf_token")
            if not token or token != request.form.get("csrf_token"):
                abort(400)

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return session["csrf_token"]

    # Globals (not a context processor) so imported macros can use them too.
    app.jinja_env.globals.update(
        csrf_token=csrf_token,
        STATUSES=constants.STATUSES,
        STATUS_COLORS=constants.STATUS_COLORS,
        ROLES=constants.ROLES,
    )

    @app.template_filter("money")
    def money(value):
        if value is None or value == "":
            return "—"
        return "₪{:,.0f}".format(value)

    @app.template_filter("dt")
    def dt(value):
        # Stored as 'YYYY-MM-DD HH:MM:SS'; show as 'DD/MM/YYYY HH:MM'.
        if not value:
            return "—"
        date, _, time = value.partition(" ")
        y, m, d = date.split("-")
        return "{}/{}/{} {}".format(d, m, y, time[:5]).strip()

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", message="אין לך הרשאה לדף הזה"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", message="הדף לא נמצא"), 404

    @app.errorhandler(400)
    def bad_request(e):
        return render_template("error.html", message="הבקשה לא תקינה. רענן את הדף ונסה שוב."), 400

    return app
