"""Durable admission, conservative reservations, and opaque login sessions."""
import hashlib
import hmac
import math
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class LimitReached(Exception):
    pass


def day():
    return datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d')


def local_time():
    return datetime.now(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %I:%M:%S %p %Z')


def positive(name, default):
    value = float(os.getenv(name, default))
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{name} must be positive and finite')
    return value


class Control:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.meeting_limit = round(positive('MEETING_BUDGET_USD', '1.50') * 1_000_000)
        self.daily_limit = round(positive('DAILY_BUDGET_USD', '10') * 1_000_000)
        self.max_sessions = int(positive('MAX_CONCURRENT_MEETINGS', '3'))
        self.max_attendees = min(4, int(positive('MAX_ATTENDEES', '4')))
        self.max_seconds = positive('MAX_MEETING_MINUTES', '30') * 60
        self.idle_seconds = positive('IDLE_TIMEOUT_MINUTES', '5') * 60
        with self.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meetings (
              id TEXT PRIMARY KEY, started TEXT, ended TEXT, status TEXT,
              attendees INTEGER, duration_ms INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
              latency_total REAL DEFAULT 0, latency_count INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS charges (
              id INTEGER PRIMARY KEY, meeting TEXT, day TEXT, stage TEXT,
              amount INTEGER NOT NULL, basis TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS charge_day ON charges(day);
            CREATE INDEX IF NOT EXISTS charge_meeting ON charges(meeting);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE IF NOT EXISTS logins (token TEXT PRIMARY KEY, role TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, at REAL, bucket TEXT);
            ''')
            if 'bucket' not in {row[1] for row in db.execute('PRAGMA table_info(attempts)')}:
                db.execute("ALTER TABLE attempts ADD COLUMN bucket TEXT DEFAULT 'legacy'")
            # Single process owns active sessions. A restart cannot revive provider work.
            db.execute("UPDATE meetings SET status='restart', ended=? WHERE status='active'", (local_time(),))

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def limits(self):
        return dict(meeting_usd=self.meeting_limit / 1e6, daily_usd=self.daily_limit / 1e6,
                    max_attendees=self.max_attendees, max_concurrent=self.max_sessions,
                    max_minutes=self.max_seconds / 60, idle_minutes=self.idle_seconds / 60)

    def admit(self, sid, count):
        with self.db() as db:
            paused = db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
            active = db.execute("SELECT count(*) FROM meetings WHERE status='active'").fetchone()[0]
            spent = db.execute('SELECT coalesce(sum(amount),0) FROM charges WHERE day=?', (day(),)).fetchone()[0]
            if paused and paused[0] == 'true':
                raise LimitReached('New meetings are paused by the administrator.')
            if active >= self.max_sessions:
                raise LimitReached('All meeting slots are occupied. Try again later.')
            if spent >= self.daily_limit:
                raise LimitReached('The daily allowance has been reached.')
            if not 1 <= count <= self.max_attendees:
                raise LimitReached('Attendee limit exceeded.')
            db.execute('INSERT INTO meetings(id,started,status,attendees) VALUES (?,?,?,?)',
                       (sid, local_time(), 'active', count))

    def reserve(self, sid, stage, usd):
        if not math.isfinite(usd) or usd < 0:
            raise ValueError('Invalid reservation')
        amount = math.ceil(usd * 1e6)
        with self.db() as db:
            meeting = db.execute('SELECT status FROM meetings WHERE id=?', (sid,)).fetchone()
            if not meeting or meeting[0] != 'active':
                raise LimitReached('Meeting is closed.')
            daily = db.execute('SELECT coalesce(sum(amount),0) FROM charges WHERE day=?', (day(),)).fetchone()[0]
            total = db.execute('SELECT coalesce(sum(amount),0) FROM charges WHERE meeting=?', (sid,)).fetchone()[0]
            if total + amount > self.meeting_limit or daily + amount > self.daily_limit:
                raise LimitReached('Spending allowance reached. Your session review is available.')
            return db.execute('INSERT INTO charges(meeting,day,stage,amount,basis) VALUES (?,?,?,?,?)',
                              (sid, day(), stage, amount, 'conservative reservation')).lastrowid

    def reconcile(self, charge, usd):
        # Retain the reservation when usage is absent or invalid. Never release on cancellation.
        if not math.isfinite(usd) or usd < 0:
            return
        with self.db() as db:
            db.execute("UPDATE charges SET amount=?,basis='reported usage plus margin' WHERE id=?",
                       (math.ceil(usd * 1e6), charge))

    def finish(self, sid, duration, status):
        with self.db() as db:
            db.execute("UPDATE meetings SET ended=?,status=?,duration_ms=? WHERE id=? AND status='active'",
                       (local_time(), status, duration, sid))

    def event(self, sid, event):
        with self.db() as db:
            if event['type'] == 'error':
                db.execute('UPDATE meetings SET errors=errors+1 WHERE id=?', (sid,))
            if event['type'] == 'metric' and event.get('stage') == 'response_first_audio_sent':
                db.execute('UPDATE meetings SET latency_total=latency_total+?,latency_count=latency_count+1 WHERE id=?',
                           (event['value_ms'], sid))

    def usage(self, sid):
        with self.db() as db:
            total = db.execute('SELECT coalesce(sum(amount),0) FROM charges WHERE meeting=?', (sid,)).fetchone()[0]
            daily = db.execute('SELECT coalesce(sum(amount),0) FROM charges WHERE day=?', (day(),)).fetchone()[0]
        return dict(meeting_usd=total/1e6, daily_usd=daily/1e6,
                    warning=total >= .8*self.meeting_limit or daily >= .8*self.daily_limit)

    def stats(self):
        with self.db() as db:
            rows = db.execute('''SELECT m.*, coalesce(sum(c.amount),0)/1000000.0 AS estimated_usd
                FROM meetings m LEFT JOIN charges c ON c.meeting=m.id GROUP BY m.id ORDER BY (m.status='active') DESC,m.rowid DESC LIMIT 100''').fetchall()
            stages = db.execute('SELECT stage,sum(amount)/1000000.0 AS usd FROM charges WHERE day=? GROUP BY stage', (day(),)).fetchall()
            paused = db.execute("SELECT value FROM settings WHERE key='paused'").fetchone()
        return dict(meetings=[dict(r) for r in rows], today=day(), timezone='America/Chicago',
                    daily_by_stage=[dict(r) for r in stages], limits=self.limits(), paused=bool(paused and paused[0]=='true'))

    def pause(self, paused):
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES ('paused',?)", ('true' if paused else 'false',))

    def login(self, role, password, client='local'):
        expected = os.getenv(f'{role.upper()}_PASSWORD', '')
        other = os.getenv('ADMIN_PASSWORD' if role=='meeting' else 'MEETING_PASSWORD', '')
        bucket = self.digest(role+':'+client)
        with self.db() as db:
            db.execute('DELETE FROM attempts WHERE at<?', (time.time()-60,))
            if db.execute('SELECT count(*) FROM attempts WHERE bucket=?', (bucket,)).fetchone()[0] >= 20:
                raise LimitReached('Too many login attempts. Wait a minute.')
            if len(expected) < 12 or expected == other or not hmac.compare_digest(password.encode(), expected.encode()):
                db.execute('INSERT INTO attempts(at,bucket) VALUES (?,?)', (time.time(), bucket))
                return None
            token = secrets.token_urlsafe(32)
            db.execute('DELETE FROM logins WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO logins VALUES (?,?,?)', (self.digest(token), role, time.time()+8*3600))
        return token

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def authorized(self, token, role):
        if not token:
            return False
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM logins WHERE token=? AND role=? AND expires>?',
                                   (self.digest(token), role, time.time())).fetchone())

    def logout(self, token):
        with self.db() as db:
            db.execute('DELETE FROM logins WHERE token=?', (self.digest(token or ''),))
