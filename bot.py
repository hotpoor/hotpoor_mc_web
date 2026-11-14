# -*- coding: utf-8 -*-
"""Tiny AI companion bots, handy when you want a populated server alone.

    python bot.py --count 4              # 4 bots, balanced teams
    python bot.py --count 2 --team blue  # 2 blue attackers
    python bot.py --count 2 --duration 30
    python bot.py --url ws://127.0.0.1:8888/ws

Bots use the very same WebSocket protocol as the browser client: they read
20 Hz snapshots, chase the nearest enemy, swing when in range, and simply
wait for the 5 s respawn when killed.
"""

import argparse
import asyncio
import json
import math
import random
import time

import tornado.websocket

NAMES = ["史蒂夫", "苦力怕", "末影人", "铁傀儡", "村民", "僵尸",
         "骷髅", "蜘蛛", "小黑", "雪傀儡"]


async def bot_loop(url, name, team, deadline, max_kills=0):
    ws = await tornado.websocket.websocket_connect(url)
    await ws.write_message(json.dumps({"t": "join", "name": name, "team": team}))
    my_id = my_team = my_name = None
    kills = 0
    last_attack = 0.0
    last_pos = None
    stuck_since = 0.0
    sidestep = 1
    sidestep_until = 0.0
    try:
        while deadline == 0 or time.monotonic() < deadline:
            raw = await ws.read_message()
            if raw is None:
                break
            msg = json.loads(raw)
            if msg["t"] == "welcome":
                my_id, my_team, my_name = msg["id"], msg["team"], msg["name"]
                print("[bot] %s joined %s" % (my_name, my_team), flush=True)
                continue
            if msg["t"] != "state" or not my_id:
                continue
            for ev in msg.get("events", []):
                if ev.get("k") == "kill" and ev.get("killer") == my_name:
                    kills += 1
                    print("[bot] %s killed %s (%d)" % (my_name, ev.get("victim"), kills), flush=True)
                    if max_kills and kills >= max_kills:
                        return
            me = next((p for p in msg["players"] if p["id"] == my_id), None)
            if not me:
                continue
            now = time.monotonic()
            if not me["alive"]:
                await ws.write_message(json.dumps({"t": "input", "mx": 0, "mz": 0, "yaw": 0}))
                last_pos = None
                continue

            enemies = [p for p in msg["players"] if p["team"] != my_team and p["alive"]]
            if enemies:
                target = min(enemies, key=lambda p: math.hypot(p["x"] - me["x"], p["z"] - me["z"]))
                tx, tz = target["x"], target["z"]
            else:
                tx, tz = 0.0, 0.0  # patrol the central healing pool
            dx, dz = tx - me["x"], tz - me["z"]
            dist = math.hypot(dx, dz)
            yaw = math.atan2(dx, dz) if dist > 0.001 else 0.0

            if dist > 2.5:
                mx, mz = dx / dist, dz / dist
                if last_pos and math.hypot(me["x"] - last_pos[0], me["z"] - last_pos[1]) < 0.05:
                    if not stuck_since:
                        stuck_since = now
                    elif now - stuck_since > 0.6:
                        sidestep = random.choice([-1, 1])
                        sidestep_until = now + 0.9
                        stuck_since = 0.0
                else:
                    stuck_since = 0.0
                if now < sidestep_until:
                    mx, mz = -mz * sidestep, mx * sidestep
                await ws.write_message(json.dumps(
                    {"t": "input", "mx": mx, "mz": mz, "yaw": yaw, "sprint": True}))
            else:
                await ws.write_message(json.dumps(
                    {"t": "input", "mx": 0, "mz": 0, "yaw": yaw, "sprint": False}))
                if now - last_attack >= 0.52:
                    last_attack = now
                    await ws.write_message(json.dumps({"t": "attack", "yaw": yaw}))
            last_pos = (me["x"], me["z"])
    finally:
        ws.close()


async def run(args):
    deadline = time.monotonic() + args.duration if args.duration > 0 else 0
    tasks = []
    for i in range(args.count):
        name = NAMES[i % len(NAMES)] + ("" if i < len(NAMES) else str(i // len(NAMES) + 1))
        team = args.team
        if team == "auto" and args.count > 1:
            team = None  # let the server balance
        tasks.append(bot_loop(args.url, name, team, deadline, args.kills))
    try:
        if args.duration > 0:
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=args.duration + 1)
        else:
            await asyncio.gather(*tasks)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass


def main():
    p = argparse.ArgumentParser(description="mc-web companion bots")
    p.add_argument("--url", default="ws://127.0.0.1:8888/ws")
    p.add_argument("--count", type=int, default=2)
    p.add_argument("--team", choices=["auto", "red", "blue"], default="auto")
    p.add_argument("--duration", type=int, default=0, help="seconds, 0 = forever")
    p.add_argument("--kills", type=int, default=0, help="stop after N kills, 0 = never")
    args = p.parse_args()
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        print("\n[bot] stopped")


if __name__ == "__main__":
    main()
