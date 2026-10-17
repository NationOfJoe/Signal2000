"""Queries and actions on repairs, shared by the admin, technician and customer views."""
import re

from flask import abort

from .constants import CLOSED_STATUSES
from .db import get_db

REPAIR_SELECT = """
    SELECT r.*,
           d.device_type, d.brand, d.model, d.serial_number, d.customer_id,
           c.full_name AS customer_name, c.phone AS customer_phone,
           t.full_name AS technician_name
    FROM repairs r
    JOIN devices d ON d.id = r.device_id
    JOIN customers c ON c.id = d.customer_id
    LEFT JOIN users t ON t.id = r.technician_id
"""


def normalize_phone(phone):
    return re.sub(r"\D", "", phone or "")


def parse_money(value):
    value = (value or "").strip().replace(",", "").replace("₪", "")
    if not value:
        return None
    try:
        amount = float(value)
    except ValueError:
        return None
    return amount if amount >= 0 else None


def list_repairs(where="1=1", params=(), order="r.received_at DESC"):
    return get_db().execute(
        REPAIR_SELECT + " WHERE " + where + " ORDER BY " + order, params
    ).fetchall()


def get_repair(repair_id):
    repair = get_db().execute(REPAIR_SELECT + " WHERE r.id = ?", (repair_id,)).fetchone()
    if repair is None:
        abort(404)
    return repair


def get_events(repair_id, customer_view=False):
    sql = """
        SELECT e.*, u.full_name AS user_name, u.role AS user_role
        FROM repair_events e LEFT JOIN users u ON u.id = e.user_id
        WHERE e.repair_id = ?
    """
    if customer_view:
        sql += " AND e.visible_to_customer = 1"
    return get_db().execute(sql + " ORDER BY e.created_at, e.id", (repair_id,)).fetchall()


def add_event(repair_id, user_id, status=None, note=None, visible_to_customer=True):
    get_db().execute(
        "INSERT INTO repair_events (repair_id, user_id, status, note, visible_to_customer)"
        " VALUES (?, ?, ?, ?, ?)",
        (repair_id, user_id, status, note or None, 1 if visible_to_customer else 0),
    )


def set_status(repair_id, user_id, status, note=None, visible_to_customer=True):
    """Move a repair to a new status and record it in the history."""
    closed = status in CLOSED_STATUSES
    get_db().execute(
        "UPDATE repairs SET status = ?, updated_at = datetime('now', 'localtime'),"
        " closed_at = CASE WHEN ? THEN datetime('now', 'localtime') ELSE NULL END"
        " WHERE id = ?",
        (status, 1 if closed else 0, repair_id),
    )
    add_event(repair_id, user_id, status, note, visible_to_customer)


def create_repair(device_id, user_id, reported_issue, accessories=None, estimated_cost=None):
    db = get_db()
    cur = db.execute(
        "INSERT INTO repairs (device_id, reported_issue, accessories, estimated_cost)"
        " VALUES (?, ?, ?, ?)",
        (device_id, reported_issue, accessories or None, estimated_cost),
    )
    add_event(cur.lastrowid, user_id, "received", "המכשיר התקבל במעבדה")
    return cur.lastrowid
