import os
import re
import tempfile
import unittest

from signal2000 import create_app
from signal2000.db import get_db


class RepairFlowTest(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        self.app = create_app({"TESTING": True, "DATABASE": self.db_path, "SECRET_KEY": "test"})
        self.app.test_cli_runner().invoke(args=["seed-demo"])
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def csrf(self):
        page = self.client.get("/login").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)

    def post(self, url, data):
        data = dict(data, csrf_token=self.csrf())
        return self.client.post(url, data=data, follow_redirects=True)

    def login(self, username, password="demo1234"):
        self.client.post("/logout", data={"csrf_token": self.csrf()})
        return self.post("/login", {"username": username, "password": password})

    def query(self, sql, params=()):
        with self.app.app_context():
            return get_db().execute(sql, params).fetchall()

    def test_post_without_csrf_is_rejected(self):
        resp = self.client.post("/login", data={"username": "admin", "password": "demo1234"})
        self.assertEqual(resp.status_code, 400)

    def test_roles_are_enforced(self):
        self.login("tech")
        self.assertEqual(self.client.get("/admin/").status_code, 403)
        self.assertEqual(self.client.get("/my/").status_code, 403)
        self.login("0521234567")
        self.assertEqual(self.client.get("/tech/").status_code, 403)
        self.assertEqual(self.client.get("/admin/customers").status_code, 403)

    def test_customer_sees_only_own_repairs(self):
        self.login("0547654321")  # Avi
        rina_repair = self.query(
            "SELECT r.id FROM repairs r JOIN devices d ON d.id = r.device_id"
            " JOIN customers c ON c.id = d.customer_id WHERE c.phone = '0521234567'"
        )[0]["id"]
        self.assertEqual(self.client.get("/my/repairs/{}".format(rina_repair)).status_code, 404)
        page = self.client.get("/my/").get_data(as_text=True)
        self.assertIn("Panasonic", page)
        self.assertNotIn("Sony", page)

    def test_customer_does_not_see_internal_notes(self):
        self.login("0521234567")
        repair_id = self.query("SELECT id FROM repairs WHERE status = 'waiting_approval'")[0]["id"]
        page = self.client.get("/my/repairs/{}".format(repair_id)).get_data(as_text=True)
        self.assertIn("הצעת מחיר", page)
        self.assertNotIn("אחרי 16:00", page)

    def test_full_repair_flow(self):
        # Admin receives a new device from a new customer.
        self.login("admin")
        page = self.post("/admin/intake", {
            "phone": "050-999-8888", "full_name": "לקוח חדש", "device_id": "new",
            "device_type": "טלוויזיה", "brand": "Philips", "reported_issue": "לא נדלקת",
        }).get_data(as_text=True)
        self.assertIn("נפתח", page)
        repair = self.query(
            "SELECT r.* FROM repairs r JOIN devices d ON d.id = r.device_id"
            " JOIN customers c ON c.id = d.customer_id WHERE c.phone = '0509998888'"
        )[0]
        self.assertEqual(repair["status"], "received")
        rid = repair["id"]

        # Same customer, second visit: no duplicate customer is created.
        self.post("/admin/intake", {
            "customer_id": self.query("SELECT id FROM customers WHERE phone = '0509998888'")[0]["id"],
            "device_id": "new", "device_type": "רדיו", "reported_issue": "שקט",
        })
        self.assertEqual(len(self.query("SELECT id FROM customers WHERE phone = '0509998888'")), 1)

        # Admin gives the customer a portal login.
        customer_id = self.query("SELECT id FROM customers WHERE phone = '0509998888'")[0]["id"]
        self.post("/admin/customers/{}/account".format(customer_id), {"password": "secret1"})

        # Technician sees it in the queue, claims it and asks for approval.
        self.login("tech")
        self.assertIn("לא נדלקת", self.client.get("/tech/").get_data(as_text=True))
        self.post("/tech/repairs/{}/claim".format(rid), {})
        self.post("/tech/repairs/{}/update".format(rid), {
            "status": "waiting_approval", "diagnosis": "ספק כוח שרוף", "estimated_cost": "350",
        })
        self.assertEqual(self.query("SELECT status FROM repairs WHERE id = ?", (rid,))[0][0],
                         "waiting_approval")

        # A different technician cannot change it.
        self.login("tech2")
        resp = self.client.post("/tech/repairs/{}/update".format(rid),
                                data={"status": "ready", "csrf_token": self.csrf()})
        self.assertEqual(resp.status_code, 403)

        # Customer approves the quote.
        self.login("0509998888", "secret1")
        self.post("/my/repairs/{}/decision".format(rid), {"decision": "approve"})
        self.assertEqual(self.query("SELECT status FROM repairs WHERE id = ?", (rid,))[0][0], "approved")

        # Technician finishes; admin hands it over.
        self.login("tech")
        self.post("/tech/repairs/{}/update".format(rid), {"status": "ready", "estimated_cost": "350"})
        self.login("admin")
        tech_id = self.query("SELECT technician_id FROM repairs WHERE id = ?", (rid,))[0][0]
        self.post("/admin/repairs/{}/update".format(rid), {
            "status": "delivered", "final_cost": "350", "technician_id": tech_id,
        })
        row = self.query("SELECT status, final_cost, closed_at FROM repairs WHERE id = ?", (rid,))[0]
        self.assertEqual(row["status"], "delivered")
        self.assertEqual(row["final_cost"], 350)
        self.assertIsNotNone(row["closed_at"])

        statuses = [r["status"] for r in self.query(
            "SELECT status FROM repair_events WHERE repair_id = ? AND status IS NOT NULL ORDER BY id",
            (rid,))]
        self.assertEqual(statuses, [
            "received", "diagnosing", "waiting_approval", "approved", "ready", "delivered",
        ])


if __name__ == "__main__":
    unittest.main()
