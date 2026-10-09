"""SQLite: schemat, połączenie i ustawienia (klucz-wartość)."""
import os
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS contacts(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE,
    note TEXT NOT NULL DEFAULT '', surname TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS grp(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS contact_grp(
    contact_id INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    grp_id INTEGER NOT NULL REFERENCES grp(id) ON DELETE CASCADE,
    PRIMARY KEY(contact_id, grp_id));
-- numery, które zrezygnowały (STOP) - także spoza kontaktów
CREATE TABLE IF NOT EXISTS blocked(phone TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS templates(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaigns(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, body TEXT NOT NULL, nonce TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'running',  -- running | paused | cancelled
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(
    id INTEGER PRIMARY KEY,
    direction TEXT NOT NULL,                 -- out | in
    phone TEXT NOT NULL, body TEXT NOT NULL,
    status TEXT NOT NULL,                    -- out: queued|sending|accepted|sent|delivered|failed|cancelled; in: received
    gateway_id TEXT UNIQUE,                  -- id w SMSGate (dla przychodzących z prefiksem "in:")
    campaign_id INTEGER REFERENCES campaigns(id),
    error TEXT, read INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL, sent_at TEXT,
    segments INTEGER NOT NULL DEFAULT 1);     -- ile SMS-ów zajmuje (do limitu Androida)
CREATE INDEX IF NOT EXISTS messages_phone ON messages(phone);
CREATE INDEX IF NOT EXISTS messages_status ON messages(status);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir(demo: bool = False) -> Path:
    name = "SmsPanel-demo" if demo else "SmsPanel"
    if os.environ.get("SMSPANEL_DATA"):
        d = Path(os.environ["SMSPANEL_DATA"])
    elif sys.platform == "win32":
        d = Path(os.environ.get("APPDATA") or Path.home()) / name
    elif sys.platform == "darwin":
        d = Path.home() / "Library" / "Application Support" / name
    else:
        d = Path.home() / ".local" / "share" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


class DB:
    # ponytail: jedno połączenie + globalna blokada; przy jednym użytkowniku wystarcza,
    # przy większym ruchu - połączenie na wątek.
    def __init__(self, path):
        self.con = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.con.executescript(SCHEMA)
        for col in ("surname", "email"):  # bazy sprzed dodania nazwiska i e-maila
            try:
                self.con.execute(f"ALTER TABLE contacts ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
            except sqlite3.OperationalError:
                pass
        try:  # bazy sprzed pilnowania limitu Androida
            self.con.execute("ALTER TABLE messages ADD COLUMN segments INTEGER NOT NULL DEFAULT 1")
        except sqlite3.OperationalError:
            pass

    def x(self, sql, *args):
        with self.lock:
            return self.con.execute(sql, args)

    def q(self, sql, *args):
        with self.lock:
            return self.con.execute(sql, args).fetchall()

    def one(self, sql, *args):
        rows = self.q(sql, *args)
        return rows[0] if rows else None

    def get(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", key)
        return row["value"] if row else default

    def set(self, key, value):
        self.x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               key, str(value))
