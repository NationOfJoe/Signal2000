from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .db import get_db
from .repairs import get_events, get_repair, list_repairs, set_status

bp = Blueprint("customer", __name__, url_prefix="/my")


def _own_repair(repair_id):
    repair = get_repair(repair_id)
    if repair["customer_id"] != g.user["customer_id"]:
        abort(404)
    return repair


@bp.route("/")
@login_required("customer")
def my_devices():
    customer_id = g.user["customer_id"]
    devices = get_db().execute(
        "SELECT * FROM devices WHERE customer_id = ? ORDER BY created_at DESC", (customer_id,)
    ).fetchall()
    repairs_by_device = {}
    for repair in list_repairs("d.customer_id = ?", (customer_id,)):
        repairs_by_device.setdefault(repair["device_id"], []).append(repair)
    return render_template(
        "customer/devices.html", devices=devices, repairs_by_device=repairs_by_device,
    )


@bp.route("/repairs/<int:repair_id>")
@login_required("customer")
def repair_detail(repair_id):
    repair = _own_repair(repair_id)
    return render_template(
        "customer/repair_detail.html", repair=repair,
        events=get_events(repair_id, customer_view=True),
    )


@bp.route("/repairs/<int:repair_id>/decision", methods=("POST",))
@login_required("customer")
def decision(repair_id):
    """The customer approves or declines the technician's quote."""
    repair = _own_repair(repair_id)
    if repair["status"] != "waiting_approval":
        flash("התיקון כבר לא ממתין לאישור", "error")
    elif request.form.get("decision") == "approve":
        set_status(repair_id, g.user["id"], "approved", "הלקוח אישר את הצעת המחיר")
        get_db().commit()
        flash("תודה! התיקון אושר ונמשיך בעבודה", "success")
    elif request.form.get("decision") == "decline":
        set_status(repair_id, g.user["id"], "declined", "הלקוח סירב להצעת המחיר")
        get_db().commit()
        flash("קיבלנו. אפשר לבוא לאסוף את המכשיר", "success")
    else:
        abort(400)
    return redirect(url_for("customer.repair_detail", repair_id=repair_id))


@bp.route("/shop")
@login_required("customer")
def shop():
    return render_template("customer/shop.html")
