# -*- coding: utf-8 -*-
"""Authoritative game server.

Everything that matters (position, HP, damage, scores) is decided here at
20 ticks/s. Clients only send intent (movement vector + facing + attacks) and
render interpolated snapshots. That keeps PvP fair even with a modified client.
"""

import json
import math
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from tornado.ioloop import PeriodicCallback

from world import (RULES, TEAMS, build_world, collides, in_own_base,
                   pool_at)

MAX_HP = RULES["max_hp"]
MOVE_SPEED = RULES["speed"]
SPRINT_SPEED = RULES["sprint"]
ATTACK_RANGE = RULES["attack_range"]
ATTACK_ARC_COS = math.cos(math.radians(RULES["attack_arc"]))
ATTACK_DAMAGE = RULES["attack_damage"]
ATTACK_CD = RULES["attack_cooldown"]
RESPAWN_DELAY = RULES["respawn"]
INVULN = RULES["invulnerable"]
KILL_SCORE = RULES["kill_score"]
DEATH_PENALTY = RULES["death_penalty"]
TICK_MS = 1000 // RULES["tick_rate"]


@dataclass
class Player:
    id: str
    name: str
    team: str
    ws: object
    x: float
    z: float
    yaw: float = 0.0
    hp: float = MAX_HP
    alive: bool = True
    score: int = 0                 # cumulative, persisted in SQLite
    kills: int = 0                 # cumulative
    deaths: int = 0                # cumulative
    damage: int = 0                # cumulative damage dealt
    games: int = 0                 # cumulative sessions
    session_kills: int = 0
    session_deaths: int = 0
    session_score: int = 0
    mx: float = 0.0
    mz: float = 0.0
    sprint: bool = False
    last_input: float = 0.0
    last_attack: float = 0.0
    weapon: str = "sword"
    draw_started: float | None = None
    jump: float = 0.0
    jump_speed: float = 0.0
    grounded: bool = True
    wave_ready: float = 0.0
    beam_ready: float = 0.0
    rocket_ready: float = 0.0
    gun_ready: float = 0.0
    recall_until: float = 0.0
    recall_ready: float = 0.0
    next_round: float = 0.0
    ammo: int = 30
    last_damage_at: float = 0.0
    respawn_at: float = 0.0
    invuln_until: float = 0.0
    heal_rate: float = 0.0
    pool_name: str = ""
    joined_at: float = field(default_factory=time.time)


ARROW_GRAVITY = 18.0


def segment_box(start, delta, bounds):
    entry, exit = 0.0, 1.0
    for origin, step, (low, high) in zip(start, delta, bounds):
        if abs(step) < 1e-9:
            if not low <= origin <= high:
                return None
            continue
        a, b = (low - origin) / step, (high - origin) / step
        entry, exit = max(entry, min(a, b)), min(exit, max(a, b))
        if entry > exit:
            return None
    return entry


def clean_name(raw):
    name = re.sub(r"[^\w\u4e00-\u9fff\-]", "", str(raw or "")).strip()
    return name[:14] or ("玩家" + uuid.uuid4().hex[:4])


class Game:
    def __init__(self, db):
        self.db = db
        self.world = build_world()
        self.blocks = self.world["blocks"]
        self.pools = self.world["pools"]
        self.objects = [
            {"id": team, "kind": "crystal", "team": team, "x": cfg["spawn"][0], "z": -4,
             "hp": 100, "max_hp": 100, "ready": 0}
            for team, cfg in self.world["teams"].items()
        ]
        for x, z in ((-8, 0), (8, 0), (0, -8), (0, 8)):
            if not collides(x, z, self.blocks):
                self.objects.append({"id": f"bomb-{x}-{z}", "kind": "bomb", "x": x, "z": z,
                                     "hp": 1, "max_hp": 1, "ready": 0})

        self.arrows = {}
        self.next_arrow_id = 0
        self.players = {}                 # id -> Player
        self.sockets = {}                 # ws -> player id or None
        self.team_score = {"red": 0, "blue": 0}
        self.events = []
        self.tick_no = 0
        self.last_tick = time.monotonic()
        self._auto_flip = 0
        self._periodic = None

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        self._periodic = PeriodicCallback(self.tick, TICK_MS)
        self._periodic.start()

    def register(self, ws):
        self.sockets[ws] = None

    def unregister(self, ws):
        pid = self.sockets.pop(ws, None)
        if not pid:
            return
        p = self.players.pop(pid, None)
        if not p:
            return
        self.db.upsert_player(p)
        self.db.add_history("leave", p.name, team=p.team, detail="离开世界")
        self.emit({"k": "leave", "id": p.id, "name": p.name, "team": p.team})

    def join(self, ws, raw_name, requested_team):
        if self.sockets.get(ws, "missing") == "missing":
            self.sockets[ws] = None
        if self.sockets.get(ws):
            return  # already joined

        base_name = clean_name(raw_name)
        taken = {p.name for p in self.players.values()}
        name = base_name
        suffix = 2
        while name in taken:
            name = "%s(%d)" % (base_name, suffix)
            suffix += 1

        if requested_team in TEAMS:
            team = requested_team
        else:
            red = sum(1 for p in self.players.values() if p.team == "red")
            blue = sum(1 for p in self.players.values() if p.team == "blue")
            self._auto_flip += 1
            team = "red" if red < blue else ("blue" if blue < red else
                                            ("red" if self._auto_flip % 2 else "blue"))

        saved = self.db.get_player(name) or {}
        pid = uuid.uuid4().hex[:8]
        spawn = TEAMS[team]["spawn"]
        now = time.monotonic()
        p = Player(
            id=pid, name=name, team=team, ws=ws,
            x=spawn[0] + random.uniform(-1.4, 1.4),
            z=spawn[1] + random.uniform(-2.4, 2.4),
            yaw=0.0 if team == "red" else math.pi,
            score=int(saved.get("score", 0)),
            kills=int(saved.get("kills", 0)),
            deaths=int(saved.get("deaths", 0)),
            damage=int(saved.get("damage", 0)),
            games=int(saved.get("games", 0)) + 1,
            last_input=now,
            invuln_until=now + INVULN,
        )
        self.players[pid] = p
        self.sockets[ws] = pid
        self.db.upsert_player(p)
        self.db.add_history("join", p.name, team=team,
                            detail="加入" + TEAMS[team]["name"])
        self.emit({"k": "join", "id": pid, "name": name, "team": team})

        self.send(ws, {
            "t": "welcome",
            "id": pid,
            "name": name,
            "team": team,
            "world": self.world,
            "leaderboard": self.db.leaderboard(10),
            "history": self.db.history(12),
        })
        # The next 20 Hz broadcast delivers the first full state; sending a
        # private snapshot here would consume the pending join event.

    def handle(self, ws, msg):
        try:
            data = json.loads(msg)
        except (ValueError, TypeError):
            return
        if not isinstance(data, dict):
            return
        kind = data.get("t")
        if kind == "join":
            self.join(ws, data.get("name"), data.get("team"))
            return
        pid = self.sockets.get(ws)
        p = self.players.get(pid) if pid else None
        if not p:
            return
        now = time.monotonic()
        if kind == "recall":
            if p.alive and p.grounded and not p.recall_until and now >= p.recall_ready:
                p.mx = p.mz = 0.0
                p.draw_started = None
                p.recall_until = now + 3
            return
        if p.recall_until and kind in ("attack", "draw", "wave", "jump"):
            p.recall_until = 0.0
        if kind == "input":
            mx = max(-1.0, min(1.0, float(data.get("mx", 0) or 0)))
            mz = max(-1.0, min(1.0, float(data.get("mz", 0) or 0)))
            length = math.hypot(mx, mz)
            if length > 1.0:
                mx, mz = mx / length, mz / length
            p.mx, p.mz = mx, mz
            if mx or mz:
                p.recall_until = 0.0
            try:
                yaw = float(data.get("yaw", p.yaw))
                if math.isfinite(yaw):
                    p.yaw = yaw
            except (TypeError, ValueError):
                pass
            p.sprint = bool(data.get("sprint"))
            p.last_input = now
        elif kind == "jump":
            if p.alive and p.grounded:
                p.grounded = False
                p.jump_speed = 6.6
        elif kind == "wave":
            try:
                yaw = float(data.get("yaw", p.yaw))
            except (TypeError, ValueError):
                return
            if math.isfinite(yaw):
                self.wave(p, yaw, now)
        elif kind == "equip":
            weapon = data.get("weapon")
            if weapon in ("sword", "bow", "beam", "rocket", "gun"):
                if weapon != p.weapon:
                    p.draw_started = None
                p.weapon = weapon
        elif kind == "draw":
            ready = ((p.weapon == "bow" and now - p.last_attack >= ATTACK_CD)
                     or (p.weapon == "beam" and now >= p.beam_ready))
            if p.alive and ready and p.draw_started is None:
                p.draw_started = now
        elif kind == "cancel_draw":
            p.draw_started = None
        elif kind == "attack":
            try:
                yaw = float(data.get("yaw", p.yaw))
            except (TypeError, ValueError):
                yaw = p.yaw
            if not math.isfinite(yaw):
                return
            if p.weapon == "gun":
                if p.alive and now >= max(p.gun_ready, p.next_round):
                    if p.ammo == 0:
                        p.ammo = 30
                    p.ammo -= 1
                    p.next_round = now + .12
                    if p.ammo == 0:
                        p.gun_ready = now + 10
                    self.wave(p, yaw, now, gun=True)
            elif p.weapon == "rocket":
                if p.alive and now >= p.rocket_ready:
                    p.rocket_ready = now + 10
                    self.shoot(p, yaw, 0, now, 1, rocket=True)
            elif p.weapon == "beam":
                started, p.draw_started = p.draw_started, None
                if started is not None and now - started >= 1:
                    self.wave(p, yaw, now, beam=True)
            elif p.weapon == "bow":
                started, p.draw_started = p.draw_started, None
                if started is not None and now - started >= 0.12:
                    try:
                        pitch = float(data.get("pitch", 0))
                    except (TypeError, ValueError):
                        pitch = 0
                    pitch = max(-1.15, min(1.15, pitch)) if math.isfinite(pitch) else 0
                    self.shoot(p, yaw, pitch, now, min(1.0, now - started))
            else:
                self.attack(p, yaw, now)
        elif kind == "chat":
            text = str(data.get("text", ""))[:100].strip()
            if text:
                self.emit({"k": "chat", "id": p.id, "name": p.name,
                           "team": p.team, "text": text})
        elif kind == "ping":
            self.send(ws, {"t": "pong", "ts": data.get("ts")})

    # ---------------------------------------------------------------- combat
    def attack(self, p, yaw, now):
        if not p.alive or now - p.last_attack < ATTACK_CD:
            return
        p.last_attack = now
        p.yaw = yaw
        fx, fz = math.sin(yaw), math.cos(yaw)
        for obj in self.targets(p):
            dx, dz = obj["x"] - p.x, obj["z"] - p.z
            distance = math.hypot(dx, dz)
            if (distance <= ATTACK_RANGE and dx * fx + dz * fz >= distance * ATTACK_ARC_COS
                    and abs(p.jump - .5) < 1.7 and not self.blocked(p.x, p.z, obj["x"], obj["z"])):
                self.damage_object(p, obj, ATTACK_DAMAGE, now)
        hits = []
        for q in list(self.players.values()):
            if q.id == p.id or not q.alive or q.team == p.team:
                continue
            if now < q.invuln_until:
                continue
            dx, dz = q.x - p.x, q.z - p.z
            dist = math.hypot(dx, dz)
            if dist > ATTACK_RANGE or dist < 0.001:
                continue
            if (dx * fx + dz * fz) / dist < ATTACK_ARC_COS:
                continue
            if self.blocked(p.x, p.z, q.x, q.z):
                continue
            self.damage(p, q, ATTACK_DAMAGE, now)
            hits.append(q.id)
            if len(hits) >= 3:
                break
        self.emit({"k": "attack", "id": p.id, "yaw": yaw, "hits": hits})

    def targets(self, player):
        return [obj for obj in self.objects if obj["hp"] > 0 and obj.get("team") != player.team]

    @staticmethod
    def object_bounds(obj):
        x, z = obj["x"], obj["z"]
        return ((x - .48, x + .48), (0, 2 if obj["kind"] == "crystal" else 1.7), (z - .48, z + .48))

    def damage_object(self, player, obj, amount, now):
        obj["hp"] = max(0, obj["hp"] - amount)
        if obj["hp"]:
            return
        obj["ready"] = now + (30 if obj["kind"] == "crystal" else 20)
        self.emit({"k": obj["kind"], "x": obj["x"], "z": obj["z"], "team": obj.get("team")})
        if obj["kind"] == "bomb":
            for target in list(self.players.values()):
                if (target.team != player.team and target.alive and now >= target.invuln_until
                        and math.hypot(target.x - obj["x"], target.z - obj["z"]) <= 3
                        and not self.blocked(obj["x"], obj["z"], target.x, target.z)):
                    self.damage(player, target, 24, now)

    def wave(self, p, yaw, now, beam=False, gun=False):
        ready = p.beam_ready if beam else p.wave_ready
        if not p.alive or (not gun and now < ready):
            return
        if beam:
            p.beam_ready = now + 5
        elif not gun:
            p.wave_ready = now + 1
        p.yaw = yaw
        fx, fz = math.sin(yaw), math.cos(yaw)
        y = p.jump + 0.9
        reach = 18 if beam else 12
        start, delta = (p.x, y, p.z), (fx * reach, 0, fz * reach)
        stop = 1.0
        for block in self.blocks:
            x, z = block["x"], block["z"]
            t = segment_box(start, delta, ((x - .5, x + .5), (0, block["h"]), (z - .5, z + .5)))
            if t is not None:
                stop = min(stop, t)
        self.emit({"k": "wave", "gun": gun, "beam": beam, "start": start, "end": (p.x + delta[0] * stop, y, p.z + delta[2] * stop)})
        if gun:
            hit = stop
            victim = None
            for obj in self.targets(p):
                t = segment_box(start, delta, self.object_bounds(obj))
                if t is not None and t < hit:
                    hit, victim = t, obj
            for q in self.players.values():
                if q.team == p.team or not q.alive or now < q.invuln_until:
                    continue
                t = segment_box(start, delta, ((q.x - .36, q.x + .36), (q.jump, q.jump + 2.03), (q.z - .36, q.z + .36)))
                if t is not None and t < hit:
                    hit, victim = t, q
            self.events[-1]["end"] = (p.x + delta[0] * hit, y, p.z + delta[2] * hit)
            if isinstance(victim, dict):
                self.damage_object(p, victim, 5, now)
            elif victim:
                self.damage(p, victim, 5, now)
            return
        for obj in self.targets(p):
            t = segment_box(start, delta, self.object_bounds(obj))
            if t is not None and t < stop:
                self.damage_object(p, obj, 50 if beam else 5, now)
        for q in list(self.players.values()):
            if q.team == p.team or not q.alive or now < q.invuln_until:
                continue
            t = segment_box(start, delta, ((q.x - .7, q.x + .7), (q.jump, q.jump + 2.03), (q.z - .7, q.z + .7)))
            if t is not None and t < stop:
                self.damage(p, q, 50 if beam else 5, now)

    def shoot(self, p, yaw, pitch, now, charge, rocket=False):
        if not p.alive or (not rocket and now - p.last_attack < ATTACK_CD):
            return
        if not rocket:
            p.last_attack = now
        p.yaw = yaw
        speed = 24 if rocket else 10 + 24 * charge
        horizontal = speed * math.cos(pitch)
        self.next_arrow_id += 1
        arrow_id = self.next_arrow_id
        self.arrows[arrow_id] = {
            "owner": p.id, "position": (p.x, 1.68 + p.jump, p.z),
            "velocity": (horizontal * math.sin(yaw), speed * math.sin(pitch), horizontal * math.cos(yaw)),
            "damage": 50 if rocket else round(4 + 18 * charge), "age": 0.0, "rocket": rocket,
        }
        self.emit({"k": "arrow", "id": p.id, "rocket": rocket})

    def advance_arrows(self, dt, now):
        half = self.world["half"]
        for arrow_id, arrow in list(self.arrows.items()):
            owner = self.players.get(arrow["owner"])
            if owner is None or arrow["age"] >= 5:
                del self.arrows[arrow_id]
                continue
            x, y, z = start = arrow["position"]
            vx, vy, vz = arrow["velocity"]
            gravity = 0 if arrow["rocket"] else ARROW_GRAVITY
            delta = (vx * dt, (vy - gravity * dt / 2) * dt, vz * dt)
            end = tuple(a + b for a, b in zip(start, delta))
            hit_at, victim, hit_object = math.inf, None, None

            for origin, step, low, high in ((y, delta[1], 0, math.inf),
                                           (x, delta[0], -half, half), (z, delta[2], -half, half)):
                if origin + step < low:
                    hit_at = min(hit_at, (low - origin) / step)
                elif origin + step > high:
                    hit_at = min(hit_at, (high - origin) / step)

            for block in self.blocks:
                bx, bz = block["x"], block["z"]
                if abs(bx - x) > abs(delta[0]) + 0.5 or abs(bz - z) > abs(delta[2]) + 0.5:
                    continue
                t = segment_box(start, delta, ((bx - .5, bx + .5), (0, block["h"]), (bz - .5, bz + .5)))
                if t is not None:
                    hit_at = min(hit_at, t)

            for q in self.players.values():
                if q.team == owner.team or not q.alive or now < q.invuln_until:
                    continue
                t = segment_box(start, delta, ((q.x - .43, q.x + .43), (q.jump, q.jump + 2.03), (q.z - .43, q.z + .43)))
                if t is not None and t < hit_at:
                    hit_at, victim = t, q

            for obj in self.targets(owner):
                t = segment_box(start, delta, self.object_bounds(obj))
                if t is not None and t < hit_at:
                    hit_at, hit_object, victim = t, obj, None

            if hit_at <= 1:
                impact = tuple(a + b * hit_at for a, b in zip(start, delta))
                self.emit({"k": "arrow_stop", "arrow": arrow_id, "position": impact, "rocket": arrow["rocket"],
                           "velocity": (vx, vy - gravity * dt * hit_at, vz)})
                del self.arrows[arrow_id]
                if hit_object:
                    self.damage_object(owner, hit_object, arrow["damage"], now)
                elif victim:
                    self.damage(owner, victim, arrow["damage"], now)
                continue

            arrow["position"] = end
            arrow["velocity"] = (vx, vy - gravity * dt, vz)
            arrow["age"] += dt

    def blocked(self, x0, z0, x1, z1):
        """Rough line-of-sight check so players cannot hit through walls."""
        steps = max(2, int(math.hypot(x1 - x0, z1 - z0) / 0.4))
        for i in range(1, steps):
            t = i / steps
            x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
            for b in self.blocks:
                if abs(x - b["x"]) < 0.5 and abs(z - b["z"]) < 0.5:
                    return True
        return False

    def damage(self, attacker, victim, amount, now):
        victim.recall_until = 0.0
        victim.hp -= amount
        victim.last_damage_at = now
        attacker.damage += int(amount)
        fx, fz = math.sin(attacker.yaw), math.cos(attacker.yaw)
        nx, nz = victim.x + fx * 0.65, victim.z + fz * 0.65
        if not collides(nx, victim.z, self.blocks, feet=victim.jump):
            victim.x = nx
        if not collides(victim.x, nz, self.blocks, feet=victim.jump):
            victim.z = nz
        self.emit({"k": "hit", "id": victim.id, "by": attacker.id,
                   "dmg": amount, "hp": max(0, round(victim.hp))})
        if victim.hp <= 0:
            self.kill(attacker, victim, now)

    def kill(self, killer, victim, now):
        victim.hp = 0
        victim.alive = False
        victim.jump = victim.jump_speed = 0.0
        victim.draw_started = None
        victim.deaths += 1
        victim.session_deaths += 1
        victim.score = max(0, victim.score - DEATH_PENALTY)
        victim.respawn_at = now + RESPAWN_DELAY
        victim.mx = victim.mz = 0.0

        killer.kills += 1
        killer.session_kills += 1
        killer.score += KILL_SCORE
        killer.session_score += KILL_SCORE
        self.team_score[killer.team] += KILL_SCORE

        self.db.upsert_player(killer)
        self.db.upsert_player(victim)
        detail = "%s 击败了 %s" % (killer.name, victim.name)
        self.db.add_history("kill", killer.name, victim.name, killer.team,
                            detail, KILL_SCORE)
        self.db.add_history("death", victim.name, killer.name, victim.team,
                            detail, 0)
        self.emit({"k": "kill", "killer": killer.name, "victim": victim.name,
                   "team": killer.team, "id": killer.id, "victim_id": victim.id})

    def respawn(self, p, now):
        spawn = TEAMS[p.team]["spawn"]
        p.alive = True
        p.grounded = True
        p.hp = MAX_HP
        p.x = spawn[0] + random.uniform(-1.4, 1.4)
        p.z = spawn[1] + random.uniform(-2.4, 2.4)
        p.mx = p.mz = 0.0
        p.invuln_until = now + INVULN
        p.last_damage_at = now
        self.db.add_history("respawn", p.name, team=p.team,
                            detail="在" + TEAMS[p.team]["name"] + "复活")
        self.emit({"k": "respawn", "id": p.id, "name": p.name, "team": p.team})

    def push_players(self, previous):
        players = [p for p in self.players.values() if p.alive and p.id in previous]
        diameter = .72
        for _ in range(2):
            for a, b in combinations(players, 2):
                if abs(a.jump - b.jump) >= 1.7:
                    continue
                dx, dz = b.x - a.x, b.z - a.z
                distance = math.hypot(dx, dz)
                if distance >= diameter:
                    continue
                ax, az = previous[a.id]
                bx, bz = previous[b.id]
                old_distance = math.hypot(bx - ax, bz - az)
                if old_distance > .001 and (distance < .001 or dx * (bx - ax) + dz * (bz - az) < 0):
                    nx, nz = (bx - ax) / old_distance, (bz - az) / old_distance
                elif distance > .001:
                    nx, nz = dx / distance, dz / distance
                else:
                    nx, nz = 1.0, 0.0
                half = (diameter - dx * nx - dz * nz) / 2
                move_a = not collides(a.x - nx * half, a.z - nz * half, self.blocks, feet=a.jump)
                move_b = not collides(b.x + nx * half, b.z + nz * half, self.blocks, feet=b.jump)
                for player, sign, can_move, other_can_move in ((a, -1, move_a, move_b), (b, 1, move_b, move_a)):
                    if not can_move:
                        continue
                    shift = sign * half * (1 if other_can_move else 2)
                    x, z = player.x + nx * shift, player.z + nz * shift
                    if not collides(x, z, self.blocks, feet=player.jump):
                        player.x, player.z = x, z

    # ---------------------------------------------------------------- tick
    def tick(self):
        now = time.monotonic()
        dt = min(0.10, max(0.0, now - self.last_tick))
        self.last_tick = now
        self.tick_no += 1

        for obj in self.objects:
            if not obj["hp"] and now >= obj["ready"]:
                obj["hp"] = obj["max_hp"]
        previous = {p.id: (p.x, p.z) for p in self.players.values() if p.alive}
        for p in list(self.players.values()):
            if not p.alive:
                if now >= p.respawn_at:
                    self.respawn(p, now)
                continue

            if now - p.last_input > 0.6:
                p.mx = p.mz = 0.0
            speed = SPRINT_SPEED if p.sprint else MOVE_SPEED
            nx = p.x + p.mx * speed * dt
            nz = p.z + p.mz * speed * dt
            if not collides(nx, p.z, self.blocks, feet=p.jump):
                p.x = nx
            if not collides(p.x, nz, self.blocks, feet=p.jump):
                p.z = nz

            support = max((b["h"] for b in self.blocks if b["h"] <= p.jump
                           and abs(p.x - b["x"]) < .86 and abs(p.z - b["z"]) < .86), default=0)
            height = p.jump + (p.jump_speed - 8 * dt) * dt
            p.grounded = height <= support
            p.jump = support if p.grounded else height
            p.jump_speed = 0.0 if p.grounded else p.jump_speed - 16 * dt

            rate = 0.0
            pool = pool_at(p.x, p.z, self.pools)
            p.pool_name = pool["name"] if pool else ""
            if pool:
                rate = float(pool["power"])
            if in_own_base(p.x, p.z, p.team) and any(obj["id"] == p.team and obj["hp"] for obj in self.objects):
                rate = max(rate, RULES["base_heal"])
            if now - p.last_damage_at > RULES["idle_regen_delay"]:
                rate = max(rate, RULES["idle_regen"])
            p.heal_rate = rate
            if rate and p.hp < MAX_HP:
                p.hp = min(MAX_HP, p.hp + rate * dt)

        self.push_players(previous)
        self.advance_arrows(dt, now)
        for p in self.players.values():
            if not p.recall_until:
                continue
            if not p.alive or not p.grounded or (p.x, p.z) != previous.get(p.id):
                p.recall_until = 0.0
            elif now >= p.recall_until:
                p.recall_until = 0.0
                p.recall_ready = now + 30
                p.x, p.z = TEAMS[p.team]["spawn"]
                p.jump = p.jump_speed = 0.0
                self.emit({"k": "recall", "id": p.id})

        state = {"t": "state", **self.snapshot()}
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        for ws, pid in list(self.sockets.items()):
            if pid:
                self.send(ws, payload)

    def snapshot(self):
        now = time.monotonic()
        players = []
        for p in self.players.values():
            players.append({
                "id": p.id, "name": p.name, "team": p.team,
                "x": round(p.x, 3), "z": round(p.z, 3),
                "yaw": round(p.yaw, 3), "hp": round(p.hp, 1),
                "alive": p.alive, "weapon": p.weapon, "jump": round(p.jump, 3),
                "wave_cd": round(max(0, p.wave_ready - now), 1),
                "beam_cd": round(max(0, p.beam_ready - now), 1),
                "rocket_cd": round(max(0, p.rocket_ready - now), 1),
                "recall": max(0, math.ceil((p.recall_until - now) * 10) / 10),
                "recall_cd": max(0, math.ceil(p.recall_ready - now)),
                "gun_cd": max(0, math.ceil((p.gun_ready - now) * 10) / 10),
                "ammo": p.ammo if now < p.gun_ready or p.ammo else 30,
                "draw": None if p.draw_started is None else min(1.0, now - p.draw_started),
                "respawn": round(max(0.0, p.respawn_at - now), 1) if not p.alive else 0,
                "kills": p.session_kills, "deaths": p.session_deaths,
                "score": p.score, "round_score": p.session_score,
                "heal": round(p.heal_rate, 1), "pool": p.pool_name,
                "invuln": now < p.invuln_until,
            })
        events = self.events
        self.events = []
        return {
            "tick": self.tick_no,
            "server_time": time.time(),
            "players": players,
            "arrows": [{"id": arrow_id, "position": arrow["position"], "velocity": arrow["velocity"], "rocket": arrow["rocket"]}
                       for arrow_id, arrow in self.arrows.items()],
            "team_score": self.team_score,
            "objects": [{**obj, "cooldown": max(0, math.ceil(obj["ready"] - now))} for obj in self.objects],
            "events": events,
        }

    # ---------------------------------------------------------------- io
    def emit(self, event):
        self.events.append(event)

    @staticmethod
    def send(ws, payload):
        if not isinstance(payload, str):
            payload = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            ws.write_message(payload)
        except Exception:
            pass
