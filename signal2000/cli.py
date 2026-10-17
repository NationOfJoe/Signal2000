import click
from flask.cli import with_appcontext

from .auth import hash_password
from .db import get_db, init_db
from .repairs import add_event, create_repair, set_status


@click.command("create-user")
@with_appcontext
@click.argument("username")
@click.option("--role", type=click.Choice(["admin", "technician"]), default="admin")
@click.option("--name", "full_name", prompt="שם מלא")
@click.password_option(prompt="סיסמה")
def create_user_command(username, role, full_name, password):
    """Create a staff account (admin or technician)."""
    db = get_db()
    db.execute(
        "INSERT INTO users (username, password_hash, role, full_name) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), role, full_name),
    )
    db.commit()
    click.echo("User {} created.".format(username))


@click.command("seed-demo")
@with_appcontext
def seed_demo_command():
    """Fill an empty database with demo users, customers and repairs."""
    init_db()
    db = get_db()
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
        raise click.ClickException("Database already has users; not seeding.")

    def user(username, role, name, customer_id=None):
        return db.execute(
            "INSERT INTO users (username, password_hash, role, full_name, customer_id)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, hash_password("demo1234"), role, name, customer_id),
        ).lastrowid

    admin = user("admin", "admin", "דנה מנהלת")
    tech1 = user("tech", "technician", "יוסי טכנאי")
    user("tech2", "technician", "מוחמד טכנאי")

    def customer(name, phone, address):
        return db.execute(
            "INSERT INTO customers (full_name, phone, address) VALUES (?, ?, ?)",
            (name, phone, address),
        ).lastrowid

    def device(customer_id, kind, brand, model, serial=None):
        return db.execute(
            "INSERT INTO devices (customer_id, device_type, brand, model, serial_number)"
            " VALUES (?, ?, ?, ?, ?)",
            (customer_id, kind, brand, model, serial),
        ).lastrowid

    rina = customer("רינה כהן", "0521234567", "רחוב הנביאים 12, חיפה")
    user("0521234567", "customer", "רינה כהן", rina)
    avi = customer("אבי לוי", "0547654321", "שדרות מוריה 40, חיפה")
    user("0547654321", "customer", "אבי לוי", avi)
    customer("סמיר חורי", "0501112233", "רחוב עבאס 8, חיפה")

    tv = device(rina, "טלוויזיה", "Sony", "Trinitron KV-29", "SN-88213")
    radio = device(rina, "רדיו", "Grundig", "Yacht Boy 400")
    vcr = device(avi, "וידאו", "Panasonic", "NV-HD620")

    r1 = create_repair(tv, admin, "אין תמונה, יש קול", "שלט")
    set_status(r1, tech1, "diagnosing", "התחלתי בדיקה")
    db.execute("UPDATE repairs SET technician_id = ? WHERE id = ?", (tech1, r1))

    create_repair(vcr, admin, "בולע קלטות", None)

    r3 = create_repair(radio, admin, "רעש חזק בכל התחנות", "מטען")
    db.execute(
        "UPDATE repairs SET technician_id = ?, diagnosis = ?, estimated_cost = 180 WHERE id = ?",
        (tech1, "קבל מנופח בספק הכוח", r3),
    )
    set_status(r3, tech1, "waiting_approval", "צריך להחליף קבלים. הצעת מחיר: 180 ש\"ח")
    add_event(r3, tech1, None, "הלקוחה ביקשה שיתקשרו אחרי 16:00", visible_to_customer=False)

    db.commit()
    click.echo("Demo data created. All demo passwords: demo1234")


def init_app(app):
    app.cli.add_command(create_user_command)
    app.cli.add_command(seed_demo_command)
