# -*- coding: utf-8 -*-
"""mc-web entry point.

    python server.py --port=8888

HTTP  /                 static client
      /api/leaderboard  cumulative score ranking (SQLite)
      /api/history      kill / death / respawn / join log
      /api/stats        aggregate counters
      /api/world        world definition (debug)
WS    /ws               realtime game channel (20 snapshots/s)
"""

import json
import os
import re
from pathlib import Path

import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado.options import define, options, parse_command_line

from db import Database
from game import Game

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

define("port", default=8888, type=int, help="HTTP / WebSocket port")
define("host", default="0.0.0.0", type=str, help="bind address")
define("db", default=os.path.join(BASE, "data", "mc.db"), type=str,
       help="SQLite database file")


class ApiHandler(tornado.web.RequestHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.set_header("Cache-Control", "no-store")

    def json_response(self, obj):
        self.finish(json.dumps(obj, ensure_ascii=False))

    @property
    def db(self):
        return self.application.settings["db"]

    @staticmethod
    def limit(default, maximum):
        try:
            return min(maximum, max(1, int(default)))
        except (TypeError, ValueError):
            return 20


class LeaderboardHandler(ApiHandler):
    def get(self):
        rows = self.db.leaderboard(self.limit(self.get_argument("limit", "20"), 100))
        self.json_response({"ok": True, "players": rows})


class HistoryHandler(ApiHandler):
    def get(self):
        rows = self.db.history(self.limit(self.get_argument("limit", "60"), 200))
        self.json_response({"ok": True, "history": rows})


class StatsHandler(ApiHandler):
    def get(self):
        self.json_response({"ok": True, "stats": self.db.stats()})


class WorldHandler(ApiHandler):
    def get(self):
        self.json_response({"ok": True, "world": self.application.settings["game"].world})


class GameSocket(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        # LAN friends join from other hosts, so accept any origin for this
        # local game server.
        return True

    def open(self):
        self.game = self.application.settings["game"]
        self.game.register(self)

    def on_message(self, message):
        if isinstance(message, bytes):
            message = message.decode("utf-8", "ignore")
        self.game.handle(self, message)

    def on_close(self):
        if hasattr(self, "game"):
            self.game.unregister(self)


class StaticHandler(tornado.web.StaticFileHandler):
    """Our own HTML/JS/CSS must never be cached, otherwise a hot fix never
    reaches an already-open tab. Tornado normally sets a 10-year max-age for
    URLs carrying a ?v= argument, so kill that too and revalidate via ETag."""

    def set_default_headers(self):
        self.set_header("Cache-Control", "no-store")

    def set_extra_headers(self, path):
        self.set_header("Cache-Control", "no-store")

    def get_cache_time(self, path, modified, mime_type):
        return 0


def make_app(game, db):
    match = re.search(r'main\.js\?v=([0-9]+)', Path(STATIC, "index.html").read_text(encoding="utf-8"))
    if match:
        game.world["client_build"] = match[1]
    return tornado.web.Application(
        [
            (r"/", tornado.web.RedirectHandler, {"url": "/static/index.html"}),
            (r"/api/leaderboard", LeaderboardHandler),
            (r"/api/history", HistoryHandler),
            (r"/api/stats", StatsHandler),
            (r"/api/world", WorldHandler),
            (r"/ws", GameSocket),
            (r"/static/(.*)", StaticHandler, {"path": STATIC}),
        ],
        game=game,
        db=db,
        static_path=STATIC,
        # Tornado prepends its own /static/ route when static_path is set, so
        # the custom no-cache handler must be supplied here too.
        static_handler_class=StaticHandler,
        websocket_ping_interval=15,
        websocket_max_message_size=64 * 1024,
    )


def main():
    parse_command_line()
    db_path = options.db
    db = Database(db_path)
    ioloop = tornado.ioloop.IOLoop.current()
    game = Game(db)
    app = make_app(game, db)
    app.listen(options.port, address=options.host)
    game.start()
    print("mc-web server up: http://localhost:%d" % options.port)
    print("database: %s" % db_path)
    print("world blocks: %d | tick: 20 Hz | ws: /ws" % len(game.blocks))
    ioloop.start()


if __name__ == "__main__":
    main()
