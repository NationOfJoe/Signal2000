"""Shared labels and the repair status workflow."""

ROLES = {
    "admin": "מנהל",
    "technician": "טכנאי",
    "customer": "לקוח",
}

DEVICE_TYPES = [
    "טלוויזיה",
    "רדיו",
    "וידאו",
    "מערכת שמע",
    "מגבר",
    "פטיפון",
    "רשמקול",
    "אחר",
]

# Ordered as the repair normally progresses.
STATUSES = {
    "received": "התקבל במעבדה",
    "diagnosing": "בבדיקה",
    "waiting_approval": "ממתין לאישור לקוח",
    "approved": "אושר לתיקון",
    "in_repair": "בתיקון",
    "waiting_parts": "ממתין לחלקים",
    "ready": "מוכן לאיסוף",
    "delivered": "נמסר ללקוח",
    "not_repairable": "לא ניתן לתיקון",
    "declined": "הלקוח סירב לתיקון",
}

# Work the technicians still have to do.
QUEUE_STATUSES = ["received", "diagnosing", "approved", "in_repair", "waiting_parts"]

# Waiting on the customer (approval or pickup); the device is still in the lab.
WAITING_STATUSES = ["waiting_approval", "ready", "not_repairable", "declined"]

# The device has left the lab.
CLOSED_STATUSES = ["delivered"]

# Statuses a technician may move a repair into.
TECH_STATUSES = [
    "diagnosing",
    "waiting_approval",
    "in_repair",
    "waiting_parts",
    "ready",
    "not_repairable",
]

STATUS_COLORS = {
    "received": "gray",
    "diagnosing": "blue",
    "waiting_approval": "amber",
    "approved": "blue",
    "in_repair": "blue",
    "waiting_parts": "amber",
    "ready": "green",
    "delivered": "muted",
    "not_repairable": "red",
    "declined": "red",
}
