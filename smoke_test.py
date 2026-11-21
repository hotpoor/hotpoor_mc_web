# -*- coding: utf-8 -*-
"""Self-contained smoke test.

    python smoke_test.py

Verifies combat / healing / respawn / SQLite persistence in-process, then
starts a temporary server on a free port and connects TWO real WebSocket
clients to verify multiplayer sync. Uses a throwaway database, so saved
scores from real games are never touched.
"""

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

from db import Database          # noqa: E402
from game import Game            # noqa: E402
from world import TEAMS          # noqa: E402


def check(condition, label):
    if not condition:
        raise AssertionError("FAILED: " + label)
    print("  [ok] " + label)


class FakeWS:
    def __init__(self):
        self.messages = []

    def write_message(self, msg):
        self.messages.append(msg)


def test_core():
    print("\n[1] Core game rules (in-process)")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = Database(os.path.join(tmp, "core.db"))
        game = Game(db)
        wa, wb = FakeWS(), FakeWS()
        game.register(wa)
        game.register(wb)
        game.handle(wa, json.dumps({"t": "join", "name": "红测", "team": "red"}))
        game.handle(wb, json.dumps({"t": "join", "name": "蓝测", "team": "blue"}))
        a = next(p for p in game.players.values() if p.team == "red")
        b = next(p for p in game.players.values() if p.team == "blue")

        welcome = json.loads(wa.messages[0])
        check(welcome["t"] == "welcome" and "world" in welcome,
              "join 返回 welcome 与完整世界配置")
        check(len(game.players) == 2 and a.team != b.team,
              "阵营分配与玩家注册")

        # Put them 1 block apart on the central plaza; yaw 0 faces +Z.
        a.x, a.z = 0.0, 0.0
        b.x, b.z = 0.0, 1.0
        a.invuln_until = b.invuln_until = 0
        t0 = time.monotonic()
        for i in range(4):
            game.attack(a, 0.0, t0 + i * 0.6)
            b.z = min(b.z, 1.0 + i * 0.6)   # undo knockback drift
        check(not b.alive and b.hp == 0, "4 次挥击（26 伤害）将敌人打死")
        check(a.kills == 1 and a.score == 100 and game.team_score["red"] == 100,
              "击杀 +100 分并计入阵营比分")
        check(b.deaths == 1 and b.score == 0, "阵亡记数与扣分")

        b.respawn_at = time.monotonic() - 0.01
        game.tick()
        spawn = TEAMS["blue"]["spawn"]
        check(b.alive and b.hp == 100 and abs(b.x - spawn[0]) < 2.5
              and abs(b.z - spawn[1]) < 3.5,
              "5 秒倒计时结束后回自己老家满血复活")
        check(abs(b.x - TEAMS["red"]["spawn"][0]) > 30,
              "复活点不是敌方老家")

        b.hp = 50
        b.x, b.z = 0.0, 0.0
        game.tick()
        check(b.heal_rate >= 18, "站在回血池里持续回血（中央圣泉 18 HP/s）")
        a.hp = 50
        a.x, a.z = TEAMS["red"]["spawn"]
        game.tick()
        check(a.heal_rate >= 24, "在自家营地回血更快（24 HP/s）")

        board = db.leaderboard()
        hist = db.history()
        check(any(r["name"] == "红测" and r["score"] == 100 for r in board),
              "累计得分写入 SQLite 排行榜")
        check({r["type"] for r in hist} >= {"join", "kill", "death", "respawn"},
              "历史记录表包含加入/击杀/阵亡/复活")
        db.close()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def start_server(port, db_path):
    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "server.py"),
         "--port=%d" % port, "--db=%s" % db_path],
        cwd=BASE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = "http://127.0.0.1:%d/api/stats" % port
    for _ in range(80):
        try:
            urllib.request.urlopen(url, timeout=0.4).read()
            return proc
        except Exception:
            if proc.poll() is not None:
                raise RuntimeError("server exited during startup")
            time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("server did not start in time")


async def network_test(port):
    import tornado.websocket

    url = "ws://127.0.0.1:%d/ws" % port
    a = await tornado.websocket.websocket_connect(url)
    b = await tornado.websocket.websocket_connect(url)
    await a.write_message(json.dumps({"t": "join", "name": "联机赤", "team": "red"}))
    await b.write_message(json.dumps({"t": "join", "name": "联机蓝", "team": "blue"}))
    wa = json.loads(await asyncio.wait_for(a.read_message(), 3))
    wb = json.loads(await asyncio.wait_for(b.read_message(), 3))
    check(wa["t"] == "welcome" and wb["t"] == "welcome",
          "两个 WebSocket 客户端各自收到 welcome")

    async def drain(conn, count=10):
        msg = None
        for _ in range(count):
            msg = json.loads(await asyncio.wait_for(conn.read_message(), 3))
        return msg

    s = await drain(a)
    check(s["t"] == "state" and len(s["players"]) == 2,
          "20Hz 快照把两名玩家同步给所有客户端")

    check(len(wa["world"].get("cities", [])) == 4
          and len([obj for obj in s["objects"] if obj["kind"] == "enemy"]) == 39,
          "城市地图与 39 名敌人通过真实 WebSocket 同步")
    start_x = next(p for p in s["players"] if p["id"] == wa["id"])["x"]
    for _ in range(12):
        await a.write_message(json.dumps(
            {"t": "input", "mx": 1, "mz": 0, "yaw": 1.57, "sprint": True}))
        await asyncio.sleep(0.05)
    s2 = await drain(a)
    end_x = next(p for p in s2["players"] if p["id"] == wa["id"])["x"]
    check(end_x > start_x + 0.5,
          "服务端权威移动生效 x %.2f -> %.2f" % (start_x, end_x))

    await b.write_message(json.dumps({"t": "chat", "text": "你好，赤焰"}))
    got = False
    for _ in range(12):
        msg = json.loads(await asyncio.wait_for(a.read_message(), 3))
        if any(e.get("k") == "chat" and e.get("text") == "你好，赤焰"
               for e in msg.get("events", [])):
            got = True
            break
    check(got, "跨客户端聊天事件广播")

    a.close()
    b.close()
    await asyncio.sleep(0.2)

    lb = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/leaderboard" % port, timeout=2).read())
    hs = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/history?limit=20" % port, timeout=2).read())
    st = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:%d/api/stats" % port, timeout=2).read())
    check(lb["ok"] and len(lb["players"]) >= 2 and hs["ok"] and st["ok"],
          "HTTP 排行榜 / 战报 / 统计接口可用")


def main():
    test_core()
    print("\n[2] Realtime multiplayer (temporary server + 2 WebSocket clients)")
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        port = free_port()
        proc = start_server(port, os.path.join(tmp, "net.db"))
        try:
            asyncio.run(network_test(port))
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    main()
