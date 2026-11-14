# -*- coding: utf-8 -*-
"""SQLite persistence: cumulative player scores + a chronological event log."""

import os
import sqlite3
import threading
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    name         TEXT PRIMARY KEY,
    team         TEXT NOT NULL,
    score        INTEGER NOT NULL DEFAULT 0,
    kills        INTEGER NOT NULL DEFAULT 0,
    deaths       INTEGER NOT NULL DEFAULT 0,
    damage       INTEGER NOT NULL DEFAULT 0,
    games        INTEGER NOT NULL DEFAULT 0,
    first_seen   TEXT,
    last_seen    TEXT
);

CREATE TABLE IF NOT EXISTS history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    type         TEXT NOT NULL,
    actor        TEXT,
    target       TEXT,
    team         TEXT,
    detail       TEXT,
    score_delta  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_history_ts ON history(id DESC);
CREATE INDEX IF NOT EXISTS idx_players_score ON players(score DESC);
"""


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Database:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def get_player(self, name):
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM players WHERE name = ?", (name,)
            ).fetchone()
            return dict(row) if row else None

    def upsert_player(self, p):
        """Write a full snapshot of a player's cumulative stats."""
        ts = _now()
        with self._lock:
            self.conn.execute(
                """INSERT INTO players
                   (name, team, score, kills, deaths, damage, games, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     team=excluded.team, score=excluded.score,
                     kills=excluded.kills, deaths=excluded.deaths,
                     damage=excluded.damage, games=excluded.games,
                     last_seen=excluded.last_seen""",
                (p.name, p.team, int(p.score), p.kills, p.deaths,
                 int(p.damage), p.games, ts, ts),
            )
            self.conn.commit()

    def add_history(self, event_type, actor=None, target=None, team=None,
                    detail="", score_delta=0):
        with self._lock:
            self.conn.execute(
                """INSERT INTO history (ts, type, actor, target, team, detail, score_delta)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_now(), event_type, actor, target, team, detail, int(score_delta)),
            )
            self.conn.commit()

    def leaderboard(self, limit=20):
        with self._lock:
            rows = self.conn.execute(
                """SELECT name, team, score, kills, deaths, games, last_seen
                   FROM players ORDER BY score DESC, kills DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def history(self, limit=60):
        with self._lock:
            rows = self.conn.execute(
                """SELECT id, ts, type, actor, target, team, detail, score_delta
                   FROM history ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def close(self):
        with self._lock:
            self.conn.close()

    def stats(self):
        with self._lock:
            row = self.conn.execute(
                """SELECT COUNT(*) AS players, COALESCE(SUM(kills),0) AS kills,
                          COALESCE(SUM(games),0) AS games
                   FROM players"""
            ).fetchone()
            events = self.conn.execute("SELECT COUNT(*) AS c FROM history").fetchone()["c"]
            result = dict(row)
            result["events"] = events
            return result
