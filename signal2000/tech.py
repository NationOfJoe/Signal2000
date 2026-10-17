from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .auth import login_required
from .constants import QUEUE_STATUSES, TECH_STATUSES
from .db import get_db
from .repairs import add_event, get_events, get_repair, list_repairs, parse_money, set_status

bp = Blueprint("tech", __name__, url_prefix="/tech")


@bp.route("/")
@login_required("technician", "admin")
def queue():
    mine_only = request.args.get("mine") == "1"
    where = "r.status IN ({})".format(",".join("?" * len(QUEUE_STATUSES)))
    params = list(QUEUE_STATUSES)
    if mine_only:
        where += " AND r.technician_id = ?"
        params.append(g.user["id"])
    # Oldest first: first in, first fixed.
    repairs = list_repairs(where, params, order="r.received_at ASC")
    waiting = list_repairs(
        "r.status = 'waiting_approval' AND r.technician_id = ?", (g.user["id"],),
        order="r.updated_at ASC",
    )
    return render_template("tech/queue.html", repairs=repairs, waiting=waiting, mine_only=mine_only)


@bp.route("/repairs/<int:repair_id>")
@login_required("technician", "admin")
def repair_detail(repair_id):
    repair = get_repair(repair_id)
    history = list_repairs(
        "r.device_id = ? AND r.id != ?", (repair["device_id"], repair_id)
    )
    return render_template(
        "tech/repair_detail.html", repair=repair, events=get_events(repair_id),
        history=history, tech_statuses=TECH_STATUSES,
    )


@bp.route("/repairs/<int:repair_id>/claim", methods=("POST",))
@login_required("technician")
def claim(repair_id):
    repair = get_repair(repair_id)
    if repair["technician_id"] not in (None, g.user["id"]):
        flash("התיקון כבר משויך ל{}".format(repair["technician_name"]), "error")
    else:
        db = get_db()
        db.execute("UPDATE repairs SET technician_id = ? WHERE id = ?", (g.user["id"], repair_id))
        if repair["status"] == "received":
            set_status(repair_id, g.user["id"], "diagnosing", "הטכנאי התחיל בבדיקה")
        else:
            add_event(repair_id, g.user["id"], None, "נלקח לטיפול", visible_to_customer=False)
        db.commit()
        flash("התיקון שלך", "success")
    return redirect(url_for("tech.repair_detail", repair_id=repair_id))


@bp.route("/repairs/<int:repair_id>/update", methods=("POST",))
@login_required("technician")
def update(repair_id):
    repair = get_repair(repair_id)
    if repair["technician_id"] != g.user["id"]:
        abort(403)
    db = get_db()
    form = request.form
    status = form.get("status") or repair["status"]
    if status != repair["status"] and status not in TECH_STATUSES:
        abort(400)
    estimated_cost = parse_money(form.get("estimated_cost"))
    if status == "waiting_approval" and estimated_cost is None:
        flash("כדי לבקש אישור מהלקוח צריך להזין הצעת מחיר", "error")
        return redirect(url_for("tech.repair_detail", repair_id=repair_id))

    db.execute(
        "UPDATE repairs SET diagnosis = ?, estimated_cost = ?, updated_at = datetime('now', 'localtime')"
        " WHERE id = ?",
        (form.get("diagnosis", "").strip() or None, estimated_cost, repair_id),
    )
    note = form.get("note", "").strip()
    visible = form.get("visible_to_customer") == "1"
    if status != repair["status"]:
        set_status(repair_id, g.user["id"], status, note, visible)
    elif note:
        add_event(repair_id, g.user["id"], None, note, visible)
    db.commit()
    flash("נשמר", "success")
    return redirect(url_for("tech.repair_detail", repair_id=repair_id))
