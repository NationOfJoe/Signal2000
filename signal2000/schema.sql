PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name   TEXT NOT NULL,
    phone       TEXT NOT NULL UNIQUE,
    email       TEXT,
    address     TEXT,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Staff accounts have customer_id NULL; customer accounts point to their customer record.
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('admin', 'technician', 'customer')),
    full_name     TEXT NOT NULL,
    customer_id   INTEGER UNIQUE REFERENCES customers(id) ON DELETE CASCADE,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ((role = 'customer') = (customer_id IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS devices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id   INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    device_type   TEXT NOT NULL,
    brand         TEXT,
    model         TEXT,
    serial_number TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_devices_customer ON devices(customer_id);

CREATE TABLE IF NOT EXISTS repairs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    status          TEXT NOT NULL DEFAULT 'received',
    reported_issue  TEXT NOT NULL,
    accessories     TEXT,
    diagnosis       TEXT,
    technician_id   INTEGER REFERENCES users(id),
    estimated_cost  REAL,
    final_cost      REAL,
    received_at     TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    closed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_repairs_device ON repairs(device_id);
CREATE INDEX IF NOT EXISTS idx_repairs_status ON repairs(status);

-- Full history of every repair: status changes and notes.
CREATE TABLE IF NOT EXISTS repair_events (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    repair_id           INTEGER NOT NULL REFERENCES repairs(id) ON DELETE CASCADE,
    user_id             INTEGER REFERENCES users(id),
    status              TEXT,
    note                TEXT,
    visible_to_customer INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_events_repair ON repair_events(repair_id);
