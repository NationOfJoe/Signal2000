import sqlite3

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import hash_password, login_required
from .constants import CLOSED_STATUSES, DEVICE_TYPES, QUEUE_STATUSES, STATUSES, WAITING_STATUSES
from .db import get_db
from .repairs import (
    add_event, create_repair, get_events, get_repair, list_repairs, normalize_phone,
    parse_money, set_status,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _placeholders(items):
    return ",".join("?" * len(items))


def _get_customer(customer_id):
    customer = get_db().execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
    if customer is None:
        abort(404)
    return customer


# ---------- Dashboard ----------

@bp.route("/")
@login_required("admin")
def dashboard():
    status = request.args.get("status", "open")
    if status == "open":
        statuses = QUEUE_STATUSES + WAITING_STATUSES
    elif status == "closed":
        statuses = CLOSED_STATUSES
    elif status in STATUSES:
        statuses = [status]
    else:
        statuses = list(STATUSES)
    repairs = list_repairs(
        "r.status IN ({})".format(_placeholders(statuses)), statuses,
        order="r.received_at ASC" if status != "closed" else "r.closed_at DESC",
    )
    counts = {
        row["status"]: row["n"]
        for row in get_db().execute("SELECT status, COUNT(*) AS n FROM repairs GROUP BY status")
    }
    return render_template(
        "admin/dashboard.html", repairs=repairs, counts=counts, current=status,
    )


# ---------- Intake: new repair ----------

@bp.route("/intake", methods=("GET", "POST"))
@login_required("admin")
def intake():
    db = get_db()
    form = request.form if request.method == "POST" else {}
    phone = normalize_phone(request.values.get("phone"))
    customer = None
    devices = []
    if request.values.get("customer_id"):
        customer = _get_customer(request.values["customer_id"])
    elif phone:
        customer = db.execute("SELECT * FROM customers WHERE phone = ?", (phone,)).fetchone()
    if customer is not None:
        devices = db.execute(
            "SELECT * FROM devices WHERE customer_id = ? ORDER BY created_at DESC",
            (customer["id"],),
        ).fetchall()

    if request.method == "POST":
        errors = []
        reported_issue = form.get("reported_issue", "").strip()
        if not reported_issue:
            errors.append("יש לתאר את התקלה")

        if customer is None:
            full_name = form.get("full_name", "").strip()
            if not full_name:
                errors.append("יש להזין שם לקוח")
            if len(phone) < 9:
                errors.append("מספר טלפון לא תקין")

        device_id = form.get("device_id") or "new"
        if device_id == "new":
            if form.get("device_type") not in DEVICE_TYPES:
                errors.append("יש לבחור סוג מכשיר")
        elif customer is None or not any(str(d["id"]) == device_id for d in devices):
            errors.append("המכשיר שנבחר לא שייך ללקוח")

        if not errors:
            if customer is None:
                customer_id = db.execute(
                    "INSERT INTO customers (full_name, phone, email, address) VALUES (?, ?, ?, ?)",
                    (form["full_name"].strip(), phone, form.get("email", "").strip() or None,
                     form.get("address", "").strip() or None),
                ).lastrowid
            else:
                customer_id = customer["id"]
            if device_id == "new":
                device_id = db.execute(
                    "INSERT INTO devices (customer_id, device_type, brand, model, serial_number)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (customer_id, form["device_type"], form.get("brand", "").strip() or None,
                     form.get("model", "").strip() or None,
                     form.get("serial_number", "").strip() or None),
                ).lastrowid
            repair_id = create_repair(
                int(device_id), g.user["id"], reported_issue,
                form.get("accessories", "").strip(), parse_money(form.get("estimated_cost")),
            )
            db.commit()
            flash("תיקון #{} נפתח".format(repair_id), "success")
            return redirect(url_for("admin.repair_detail", repair_id=repair_id))
        for error in errors:
            flash(error, "error")

    return render_template(
        "admin/intake.html", phone=phone, customer=customer, devices=devices,
        device_types=DEVICE_TYPES, form=form, looked_up=bool(phone or customer),
    )


# ---------- Customers ----------

@bp.route("/customers")
@login_required("admin")
def customers():
    q = request.args.get("q", "").strip()
    sql = """
        SELECT c.*,
               (SELECT COUNT(*) FROM devices d WHERE d.customer_id = c.id) AS device_count,
               (SELECT COUNT(*) FROM repairs r JOIN devices d ON d.id = r.device_id
                 WHERE d.customer_id = c.id) AS repair_count,
               (SELECT MAX(r.received_at) FROM repairs r JOIN devices d ON d.id = r.device_id
                 WHERE d.customer_id = c.id) AS last_visit
        FROM customers c
    """
    params = ()
    if q:
        like = "%" + q + "%"
        sql += " WHERE c.full_name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?"
        params = (like, "%" + (normalize_phone(q) or q) + "%", like)
    rows = get_db().execute(sql + " ORDER BY c.full_name", params).fetchall()
    return render_template("admin/customers.html", customers=rows, q=q)


@bp.route("/customers/<int:customer_id>")
@login_required("admin")
def customer_detail(customer_id):
    db = get_db()
    customer = _get_customer(customer_id)
    devices = db.execute(
        "SELECT * FROM devices WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)
    ).fetchall()
    repairs = list_repairs("d.customer_id = ?", (customer_id,))
    account = db.execute("SELECT * FROM users WHERE customer_id = ?", (customer_id,)).fetchone()
    return render_template(
        "admin/customer_detail.html", customer=customer, devices=devices, repairs=repairs,
        account=account, device_types=DEVICE_TYPES,
    )


@bp.route("/customers/<int:customer_id>/edit", methods=("POST",))
@login_required("admin")
def customer_edit(customer_id):
    _get_customer(customer_id)
    full_name = request.form.get("full_name", "").strip()
    phone = normalize_phone(request.form.get("phone"))
    if not full_name or len(phone) < 9:
        flash("שם וטלפון תקין הם שדות חובה", "error")
        return redirect(url_for("admin.customer_detail", customer_id=customer_id))
    db = get_db()
    try:
        db.execute(
            "UPDATE customers SET full_name = ?, phone = ?, email = ?, address = ?, notes = ?"
            " WHERE id = ?",
            (full_name, phone, request.form.get("email", "").strip() or None,
             request.form.get("address", "").strip() or None,
             request.form.get("notes", "").strip() or None, customer_id),
        )
        db.commit()
        flash("פרטי הלקוח עודכנו", "success")
    except sqlite3.IntegrityError:
        flash("מספר הטלפון כבר שייך ללקוח אחר", "error")
    return redirect(url_for("admin.customer_detail", customer_id=customer_id))


@bp.route("/customers/<int:customer_id>/account", methods=("POST",))
@login_required("admin")
def customer_account(customer_id):
    """Create the customer's portal login, or reset its password."""
    customer = _get_customer(customer_id)
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("הסיסמה צריכה להכיל לפחות 6 תווים", "error")
        return redirect(url_for("admin.customer_detail", customer_id=customer_id))
    db = get_db()
    account = db.execute("SELECT * FROM users WHERE customer_id = ?", (customer_id,)).fetchone()
    if account:
        db.execute(
            "UPDATE users SET password_hash = ?, active = 1 WHERE id = ?",
            (hash_password(password), account["id"]),
        )
        flash("הסיסמה של הלקוח עודכנה", "success")
    else:
        try:
            db.execute(
                "INSERT INTO users (username, password_hash, role, full_name, customer_id)"
                " VALUES (?, ?, 'customer', ?, ?)",
                (customer["phone"], hash_password(password), customer["full_name"], customer_id),
            )
        except sqlite3.IntegrityError:
            flash("שם המשתמש {} כבר תפוס".format(customer["phone"]), "error")
            return redirect(url_for("admin.customer_detail", customer_id=customer_id))
        flash("נוצר חשבון. שם המשתמש של הלקוח: {}".format(customer["phone"]), "success")
    db.commit()
    return redirect(url_for("admin.customer_detail", customer_id=customer_id))


# ---------- Devices ----------

@bp.route("/devices/<int:device_id>", methods=("GET", "POST"))
@login_required("admin")
def device_detail(device_id):
    db = get_db()
    device = db.execute(
        "SELECT d.*, c.full_name AS customer_name FROM devices d"
        " JOIN customers c ON c.id = d.customer_id WHERE d.id = ?",
        (device_id,),
    ).fetchone()
    if device is None:
        abort(404)
    if request.method == "POST":
        if request.form.get("device_type") not in DEVICE_TYPES:
            flash("יש לבחור סוג מכשיר", "error")
        else:
            db.execute(
                "UPDATE devices SET device_type = ?, brand = ?, model = ?, serial_number = ?,"
                " notes = ? WHERE id = ?",
                tuple(request.form.get(k, "").strip() or None
                      for k in ("device_type", "brand", "model", "serial_number", "notes"))
                + (device_id,),
            )
            db.commit()
            flash("פרטי המכשיר עודכנו", "success")
        return redirect(url_for("admin.device_detail", device_id=device_id))
    repairs = list_repairs("r.device_id = ?", (device_id,))
    return render_template(
        "admin/device_detail.html", device=device, repairs=repairs, device_types=DEVICE_TYPES,
    )


# ---------- Repairs ----------

@bp.route("/repairs/<int:repair_id>")
@login_required("admin")
def repair_detail(repair_id):
    repair = get_repair(repair_id)
    technicians = get_db().execute(
        "SELECT id, full_name FROM users WHERE role = 'technician' AND active = 1 ORDER BY full_name"
    ).fetchall()
    return render_template(
        "admin/repair_detail.html", repair=repair, events=get_events(repair_id),
        technicians=technicians,
    )


@bp.route("/repairs/<int:repair_id>/update", methods=("POST",))
@login_required("admin")
def repair_update(repair_id):
    repair = get_repair(repair_id)
    db = get_db()
    form = request.form

    technician_id = form.get("technician_id") or None
    if str(technician_id or "") != str(repair["technician_id"] or ""):
        name = "ללא"
        if technician_id:
            tech = db.execute(
                "SELECT full_name FROM users WHERE id = ? AND role = 'technician'", (technician_id,)
            ).fetchone()
            if tech is None:
                abort(400)
            name = tech["full_name"]
        db.execute("UPDATE repairs SET technician_id = ? WHERE id = ?", (technician_id, repair_id))
        add_event(repair_id, g.user["id"], None, "שויך לטכנאי: " + name, visible_to_customer=False)

    db.execute(
        "UPDATE repairs SET estimated_cost = ?, final_cost = ?, updated_at = datetime('now', 'localtime')"
        " WHERE id = ?",
        (parse_money(form.get("estimated_cost")), parse_money(form.get("final_cost")), repair_id),
    )

    note = form.get("note", "").strip()
    visible = form.get("visible_to_customer") == "1"
    status = form.get("status")
    if status and status != repair["status"]:
        if status not in STATUSES:
            abort(400)
        set_status(repair_id, g.user["id"], status, note, visible)
    elif note:
        add_event(repair_id, g.user["id"], None, note, visible)

    db.commit()
    flash("התיקון עודכן", "success")
    return redirect(url_for("admin.repair_detail", repair_id=repair_id))


@bp.route("/repairs/<int:repair_id>/receipt")
@login_required("admin")
def repair_receipt(repair_id):
    return render_template("admin/receipt.html", repair=get_repair(repair_id))


# ---------- Staff users ----------

@bp.route("/users", methods=("GET", "POST"))
@login_required("admin")
def users():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role")
        password = request.form.get("password", "")
        if not username or not full_name or role not in ("admin", "technician") or len(password) < 6:
            flash("יש למלא את כל השדות (סיסמה של 6 תווים לפחות)", "error")
        else:
            try:
                db.execute(
                    "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
                    (username, hash_password(password), role, full_name),
                )
                db.commit()
                flash("המשתמש {} נוצר".format(username), "success")
            except sqlite3.IntegrityError:
                flash("שם המשתמש כבר קיים", "error")
        return redirect(url_for("admin.users"))
    staff = db.execute(
        "SELECT * FROM users WHERE role != 'customer' ORDER BY role, full_name"
    ).fetchall()
    return render_template("admin/users.html", staff=staff)


@bp.route("/users/<int:user_id>/toggle", methods=("POST",))
@login_required("admin")
def user_toggle(user_id):
    if user_id == g.user["id"]:
        flash("אי אפשר להשבית את החשבון שלך", "error")
        return redirect(url_for("admin.users"))
    db = get_db()
    db.execute(
        "UPDATE users SET active = 1 - active WHERE id = ? AND role != 'customer'", (user_id,)
    )
    db.commit()
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/password", methods=("POST",))
@login_required("admin")
def user_password(user_id):
    password = request.form.get("password", "")
    if len(password) < 6:
        flash("הסיסמה צריכה להכיל לפחות 6 תווים", "error")
    else:
        db = get_db()
        db.execute(
            "UPDATE users SET password_hash = ? WHERE id = ? AND role != 'customer'",
            (hash_password(password), user_id),
        )
        db.commit()
        flash("הסיסמה עודכנה", "success")
    return redirect(url_for("admin.users"))
