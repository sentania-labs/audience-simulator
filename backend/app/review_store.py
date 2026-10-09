"""Opt-in review storage and immutable configuration revisions in the control DB."""
import json
import secrets
import time
from .control import local_time

RETENTION_DAYS = 30


class ReviewStore:
    def __init__(self, ctl):
        self.ctl = ctl
        with ctl.db() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS meeting_reviews (
              sid TEXT PRIMARY KEY, capability TEXT, context TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feedback (
              sid TEXT PRIMARY KEY, created TEXT NOT NULL, expires REAL NOT NULL,
              rating INTEGER NOT NULL, comment TEXT NOT NULL, transcript TEXT);
            CREATE TABLE IF NOT EXISTS runtime_revisions (
              id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT NOT NULL, config TEXT NOT NULL);
            ''')
        self.prune()

    def prune(self):
        with self.ctl.db() as db:
            db.execute('DELETE FROM feedback WHERE expires <= ?', (time.time(),))

    def register(self, sid, context):
        token = secrets.token_urlsafe(32)
        with self.ctl.db() as db:
            db.execute('INSERT INTO meeting_reviews VALUES (?,?,?)', (sid, self.ctl.digest(token), json.dumps(context)))
        return token

    def finish(self, sid, measurements):
        with self.ctl.db() as db:
            row = db.execute('SELECT context FROM meeting_reviews WHERE sid=?', (sid,)).fetchone()
            if row:
                context = json.loads(row['context'])
                context['timings'] = measurements
                db.execute('UPDATE meeting_reviews SET context=? WHERE sid=?', (json.dumps(context), sid))

    def owned(self, db, sid, token):
        row = db.execute('SELECT * FROM meeting_reviews WHERE sid=?', (sid,)).fetchone()
        if not row or not secrets.compare_digest(row['capability'], self.ctl.digest(token)):
            raise PermissionError('Review access required')
        return row

    def submit(self, sid, token, rating, comment, transcript):
        self.prune()
        with self.ctl.db() as db:
            self.owned(db, sid, token)
            meeting = db.execute('SELECT status FROM meetings WHERE id=?', (sid,)).fetchone()
            if not meeting or meeting['status'] == 'active':
                raise ValueError('End the meeting before submitting feedback')
            if db.execute('SELECT 1 FROM feedback WHERE sid=?', (sid,)).fetchone():
                raise ValueError('Feedback already submitted; withdraw it before submitting again')
            db.execute('INSERT INTO feedback VALUES (?,?,?,?,?,?)', (sid, local_time(), time.time()+RETENTION_DAYS*86400,
                       rating, comment, json.dumps(transcript) if transcript is not None else None))

    def delete(self, sid, token=None):
        with self.ctl.db() as db:
            if token is not None:
                self.owned(db, sid, token)
            db.execute('DELETE FROM feedback WHERE sid=?', (sid,))

    def list(self):
        self.prune()
        with self.ctl.db() as db:
            rows = db.execute('''SELECT f.sid,f.created,f.rating,f.comment,f.transcript,r.context,
                m.errors,m.latency_total,m.latency_count,m.duration_ms FROM feedback f
                JOIN meeting_reviews r ON r.sid=f.sid JOIN meetings m ON m.id=f.sid
                ORDER BY f.rowid DESC LIMIT 100''').fetchall()
        return [{**dict(r), 'context': json.loads(r['context']), 'transcript': json.loads(r['transcript']) if r['transcript'] else None} for r in rows]

    def current(self):
        with self.ctl.db() as db:
            row = db.execute('SELECT * FROM runtime_revisions ORDER BY id DESC LIMIT 1').fetchone()
        return (row['id'], json.loads(row['config'])) if row else (0, None)

    def history(self):
        with self.ctl.db() as db:
            return [{'id': r['id'], 'created': r['created'], 'config': json.loads(r['config'])} for r in db.execute('SELECT * FROM runtime_revisions ORDER BY id DESC LIMIT 50')]

    def save(self, value, expected):
        with self.ctl.db() as db:
            current = db.execute('SELECT coalesce(max(id),0) FROM runtime_revisions').fetchone()[0]
            if current != expected:
                raise ValueError('Settings changed in another tab; reload before saving')
            if not db.execute('SELECT 1 FROM runtime_revisions LIMIT 1').fetchone():
                from .runtime import defaults
                db.execute('INSERT INTO runtime_revisions(id,created,config) VALUES (0,?,?)', (local_time(), json.dumps(defaults())))
            return db.execute('INSERT INTO runtime_revisions(created,config) VALUES (?,?)', (local_time(), json.dumps(value))).lastrowid
