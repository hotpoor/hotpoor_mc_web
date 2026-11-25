# -*- coding: utf-8 -*-
"""Authoritative game server.

Everything that matters (position, HP, damage, scores) is decided here at
20 ticks/s. Clients only send intent (movement vector + facing + attacks) and
render interpolated snapshots. That keeps PvP fair even with a modified client.
"""

import copy
import json
import hashlib
import hmac
import math
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations

from tornado.ioloop import PeriodicCallback
from campaign import CHARACTERS, NAME_SKINS
import animal_system
import workbench
import farm_system

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
ARMOR_TYPES = {
    "crystal": {"name": "灵晶甲", "max_durability": 180, "reduction": .6},
    "iron": {"name": "铁甲", "max_durability": 80, "reduction": .4},
    "elite": {"name": "精甲", "max_durability": 160, "reduction": .6},
}


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
    armor: dict = field(default_factory=dict)
    food: int = 3
    poop: int = 0
    last_feed: float = 0.0
    last_farm: float = 0.0
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
    weapon: str = ""
    weapons: dict = field(default_factory=dict)
    next_settings_attempt: float = 0.0
    next_team_change: float = 0.0
    syllable: str = ""
    syllables: list = field(default_factory=list)
    resources: dict = field(default_factory=dict)
    slam_pending: bool = False
    skin: str = "steve"
    crystal_source: str | None = None
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
    transfer_target: str = ""
    transfer_ready: float = 0.0
    next_round: float = 0.0
    ammo: int = 30
    last_damage_at: float = 0.0
    hurt_until: float = 0.0
    respawn_at: float = 0.0
    invuln_until: float = 0.0
    heal_rate: float = 0.0
    pool_name: str = ""
    joined_at: float = field(default_factory=time.time)


ARROW_GRAVITY = 18.0
RECIPES = {
    "sword": ("宝剑", ("bǎo", "jiàn")),
    "bow": ("弓箭", ("gōng", "jiàn")),
    "beam": ("龟派气功", ("guī", "pài")),
    "rocket": ("火箭筒", ("huǒ", "jiàn", "tǒng")),
    "gun": ("机关枪", ("jī", "qiāng")),
    "axe": ("斧子", ("zhàn", "fǔ")),
    "mace": ("狼牙棒", ("láng", "yá")),
    "hammer": ("重锤", ("zhòng", "chuí")),
    "dual": ("双股剑", ('shuāng', 'gǔ', 'jiàn')),
    "spear": ("丈八蛇矛", ('zhàng', 'bā', 'shé', 'máo')),
    "blade": ("青龙偃月刀", ('qīng', 'lóng', 'yǎn', 'yuè', 'dāo')),
    "halberd": ("方天画戟", ('fāng', 'tiān', 'huà', 'jǐ')),
    "silver_spear": ("亮银枪", ("liàng", "yín", "qiāng")),
    "tiger_spear": ("虎头湛金枪", ("hǔ", "tóu", "zhàn", "jīn", "qiāng")),
}
WEAPON_USES = {"pickup": 10, "text": 15, "whole": 20, "split": 30}

PINYIN = {
    "hǔ": ("虎", "h", "ǔ"), "tóu": ("头", "t", "óu"), "jīn": ("金", "j", "īn"),
    "liàng": ("亮", "l", "iàng"), "yín": ("银", "y", "ín"),
    "bǎo": ("宝", "b", "ǎo"), "jiàn": ("剑 / 箭", "j", "iàn"),
    "gōng": ("弓", "g", "ōng"), "guī": ("龟", "g", "uī"),
    "pài": ("派", "p", "ài"), "huǒ": ("火", "h", "uǒ"),
    "tǒng": ("筒", "t", "ǒng"), "jī": ("机", "j", "ī"), "qiāng": ("枪", "q", "iāng"),
    "zhàn": ("战 / 湛", "zh", "àn"), "fǔ": ("斧", "f", "ǔ"),
    "láng": ("狼", "l", "áng"), "yá": ("牙", "y", "á"),
    "zhòng": ("重", "zh", "òng"), "chuí": ("锤", "ch", "uí"),
    "shuāng": ("双", "sh", "uāng"), "gǔ": ("股", "g", "ǔ"),
    "zhàng": ("丈", "zh", "àng"), "bā": ("八", "b", "ā"),
    "shé": ("蛇", "sh", "é"), "máo": ("矛", "m", "áo"),
    "qīng": ("青", "q", "īng"), "lóng": ("龙", "l", "óng"),
    "yǎn": ("偃", "y", "ǎn"), "yuè": ("月", "y", "uè"),
    "dāo": ("刀", "d", "āo"), "fāng": ("方", "f", "āng"),
    "tiān": ("天", "t", "iān"), "huà": ("画", "h", "uà"),
    "jǐ": ("戟", "j", "ǐ"),
}

MATERIALS = {"text:" + weapon: word for weapon, (word, _) in RECIPES.items()}
for sound, (hanzi, initial, final) in PINYIN.items():
    # Spellings such as yá use y as the written syllable onset.
    MATERIALS["whole:" + sound] = f"{hanzi} · {sound}"
    MATERIALS["initial:" + initial] = f"声母 · {initial}"
    MATERIALS["final:" + final] = f"韵母 · {final}"


def recipe_materials(sounds, split):
    if not split:
        return ["whole:" + sound for sound in sounds]
    return [part for sound in sounds
            for part in ("initial:" + PINYIN[sound][1], "final:" + PINYIN[sound][2])]


SKIN_NAMES = ("red", "blue", "steve", "alex", "miner", "ranger", "robot", "liu-bei", "zhang-fei", "guan-yu", "lu-bu") + tuple(CHARACTERS)


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
        self.settings_digest = os.environ.get("MC_SETTINGS_PASSWORD_SHA256", "")
        self.craft_modes = ("text", "whole", "split")
        if db and self.settings_digest:
            saved = db.get_setting("craft_modes")
            if saved is not None:
                self.craft_modes = tuple(mode for mode in self.craft_modes if mode in saved.split(","))
        self.world = build_world()
        saved_campaign = db.get_setting("campaign_cleared_v1") if db else None
        try:
            self.cleared_cities = set(json.loads(saved_campaign or '[]')) & {city["id"] for city in self.world["cities"]}
        except (ValueError, TypeError):
            self.cleared_cities = set()
        self.blocks = self.world["blocks"]
        self.pools = self.world["pools"]
        self.objects = [
            {"id": team, "kind": "crystal", "team": team, "x": cfg["spawn"][0], "z": -4,
             "hp": 500, "max_hp": 500, "ready": 0}
            for team, cfg in self.world["teams"].items()
        ]
        for team, cfg in self.world["teams"].items():
            self.objects.append({"id": "world-time-" + team, "kind": "time_stone", "global": True,
                                 "base_team": team, "name": "全图时光机 · 击碎恢复全场",
                                 "x": cfg["spawn"][0], "z": 4, "hp": 100, "max_hp": 100, "ready": 0})
        for x, z in ((-8, 0), (8, 0), (0, -8), (0, 8)):
            if not collides(x, z, self.blocks):
                self.objects.append({"id": f"bomb-{x}-{z}", "kind": "bomb", "x": x, "z": z,
                                     "hp": 1, "max_hp": 1, "ready": 0})

        for x, z in ((-12, -6), (-12, 6), (12, -6), (12, 6), (0, -13), (0, 13)):
            if not collides(x, z, self.blocks):
                self.objects.append({"id": f"ore-{x}-{z}", "kind": "ore", "x": x, "z": z,
                                     "hp": 1, "max_hp": 1, "ready": 0})
        fields = sorted(((x, z) for x in range(-20, 21, 4) for z in range(-20, 21, 4)
                         if not collides(x, z, self.blocks)
                         and all(math.hypot(x - obj["x"], z - obj["z"]) >= 2 for obj in self.objects)),
                        key=lambda pos: ((pos[0] * 73 + pos[1] * 109) % 127, pos))
        sites = iter(fields)
        for weapon, (word, _) in RECIPES.items():
            x, z = next(sites)
            self.objects.append({"id": "weapon-" + weapon, "kind": "weapon_pickup",
                                 "weapon": weapon, "text": word, "x": x, "z": z,
                                 "hp": 1, "max_hp": 1, "ready": 0})
        for i, (material, label) in enumerate(MATERIALS.items()):
            x, z = next(sites)
            self.objects.append({"id": f"syllable-{i}", "kind": "syllable", "text": label,
                                 "material": material, "x": x, "z": z, "hp": 1, "max_hp": 1, "ready": 0})
        for x in (-27, 27):
            for z in (-27, 27):
                self.objects.append({"id": f"forge-{x}-{z}", "kind": "forge", "x": x, "z": z,
                                     "hp": 1, "max_hp": 1, "ready": 0})
                inward_x = 1 if x < 0 else -1
                inward_z = 1 if z < 0 else -1
                for i, (dx, dz) in enumerate(((3, 0), (0, 3))):
                    self.objects.append({"id": f"dummy-{x}-{z}-{i}", "kind": "dummy",
                                         "x": x + dx * inward_x, "z": z + dz * inward_z,
                                         "hp": MAX_HP * 2, "max_hp": MAX_HP * 2, "ready": 0})
        for city in self.world["cities"]:
            cid, cx, cz = city["id"], city["x"], city["z"]
            self.objects.append({"id": "time-" + cid, "kind": "time_stone", "city": cid,
                                 "name": "时光机石头 · 击碎复活全城敌人", "x": cx + 15, "z": cz + 15,
                                 "hp": 100, "max_hp": 100, "ready": 0})
            for i, (dx, dz) in enumerate(((-4, 13), (4, 13), (0, 10), (-5, -13), (5, -13),
                                         (-13, -4), (-13, 4), (13, -4), (13, 4))):
                self.objects.append({"id": f"enemy-{cid}-{i}", "kind": "enemy", "city": cid,
                                     "name": "黄巾贼" if cid == "yellow" else "第%d章守军" % city["chapter"],
                                     "color": 0xb99540 if cid == "yellow" else (0x52728a if city["chapter"] % 2 else 0x88634c),
                                     "x": cx + dx, "z": cz + dz, "home_x": cx + dx, "home_z": cz + dz,
                                     "hp": 80, "max_hp": 80, "ready": 0, "yaw": 0, "last_attack": 0})
            for i, name in enumerate(city["bosses"]):
                dx, dz = ((0, -4), (-4, 1), (4, 1))[i]
                hp = 500 + (city["chapter"] - 1) * 50
                self.objects.append({"id": f"boss-{cid}-{i}", "kind": "enemy", "city": cid,
                                     "name": name, "skin": NAME_SKINS.get(name, "robot"), "boss": True,
                                     "loot": city["loot"][i], "color": 0xb58b36 if cid == "yellow" else 0x675b94,
                                     "x": cx + dx, "z": cz + dz, "home_x": cx + dx, "home_z": cz + dz,
                                     "hp": hp, "max_hp": hp, "ready": 0, "yaw": 0, "last_attack": 0})
            for i, name in enumerate(city["allies"]):
                self.objects.append({"id": f"ally-{cid}-{i}", "kind": "story_npc", "city": cid,
                                     "name": name, "skin": NAME_SKINS[name], "text": city["story"],
                                     "weapon": {"赵云":"silver_spear","马超":"tiger_spear"}.get(name,""),
                                     "x": cx - 10, "z": cz + i * 3 - 3, "hp": 1, "max_hp": 1, "ready": 0})
            index = city["chapter"] - 1
            for direction, dest in (("next", index + 1), ("prev", index - 1)):
                if 0 <= dest < len(self.world["cities"]):
                    destination = self.world["cities"][dest]
                    gx = (destination["x"] - cx) / max(1, abs(destination["x"] - cx)) if destination["x"] != cx else 0
                    gz = (destination["z"] - cz) / max(1, abs(destination["z"] - cz)) if destination["z"] != cz else 0
                    self.objects.append({"id": f"portal-{cid}-{direction}", "kind": "chapter_gate",
                                         "city": cid, "destination": destination["id"],
                                         "text": ("下一城 · " if direction == "next" else "上一城 · ") + destination["name"],
                                         "x": cx + gx * 16 + gz * 4.5, "z": cz + gz * 16 - gx * 4.5,
                                         "hp": 1, "max_hp": 1, "ready": 0})
        for enemy in self.objects:
            if enemy["kind"] == "enemy" and enemy["city"] in self.cleared_cities:
                enemy.update(hp=0, ready=None)
        for index, village in enumerate(self.world["villages"]):
            for offset, weapon in ((-4, "sword"), (4, "bow")):
                self.objects.append({"id": village["id"] + weapon, "kind": "weapon_pickup", "weapon": weapon,
                                     "text": village["name"] + "补给 · " + RECIPES[weapon][0],
                                     "x": village["x"] + (offset if village["axis"] == "x" else 2.5),
                                     "z": village["z"] + (offset if village["axis"] == "z" else 2.5),
                                     "hp": 1, "max_hp": 1, "ready": 0})
            for i, animal in enumerate(("dog", "tiger" if index % 3 == 1 else "wolf")):
                x = village["x"] + (-5 if village["axis"] == "z" else i * 3 - 2)
                z = village["z"] + (-5 if village["axis"] == "x" else i * 3 - 2)
                self.objects.append({"id": village["id"] + "-" + animal, "kind": "animal", "animal": animal,
                                     "name": {"dog": "村犬", "tiger": "山虎", "wolf": "灰狼"}[animal],
                                     "x": x, "z": z, "home_x": x, "home_z": z, "yaw": 0,
                                     "hp": 1, "max_hp": 1, "ready": 0})
        animal_system.initialize(self)
        farm_system.initialize(self)
        self.world["armor_types"] = ARMOR_TYPES
        self.world["materials"] = MATERIALS
        self.world["weapon_uses"] = WEAPON_USES
        self.world["recipes"] = {
            weapon: {"word": word, "text": ["text:" + weapon],
                     "whole": recipe_materials(sounds, False), "split": recipe_materials(sounds, True)}
            for weapon, (word, sounds) in RECIPES.items()
        }
        workbench.initialize(self)
        self.arrows = {}
        self.next_arrow_id = 0
        self.players = {}                 # id -> Player
        self.sockets = {}                 # ws -> player id or None
        self.object_streams = {}
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
        self.object_streams.pop(ws, None)
        pid = self.sockets.pop(ws, None)
        if not pid:
            return
        p = self.players.pop(pid, None)
        if not p:
            return
        self.drop_crystal(p, time.monotonic())
        self.db.upsert_player(p)
        self.db.add_history("leave", p.name, team=p.team, detail="离开世界")
        self.emit({"k": "leave", "id": p.id, "name": p.name, "team": p.team})

    def join(self, ws, raw_name, requested_team, skin=None):
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

        if requested_team in self.world["teams"]:
            team = requested_team
        else:
            red = sum(1 for p in self.players.values() if p.team == "red")
            blue = sum(1 for p in self.players.values() if p.team == "blue")
            self._auto_flip += 1
            team = "red" if red < blue else ("blue" if blue < red else
                                            ("red" if self._auto_flip % 2 else "blue"))

        saved = self.db.get_player(name) or {}
        pid = uuid.uuid4().hex[:8]
        spawn = self.world["teams"][team]["spawn"]
        now = time.monotonic()
        p = Player(
            id=pid, name=name, team=team, ws=ws,
            skin=skin if skin in SKIN_NAMES else "steve",
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
        workbench.load_bag(self,p)
        self.players[pid] = p
        self.sockets[ws] = pid
        self.db.upsert_player(p)
        self.db.add_history("join", p.name, team=team,
                            detail="加入" + self.world["teams"][team]["name"])
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
            self.join(ws, data.get("name"), data.get("team"), data.get("skin"))
            if data.get("object_deltas") is True and ws not in self.object_streams:
                self.object_streams[ws] = {"objects": {}, "initialized": False}
            return
        pid = self.sockets.get(ws)
        p = self.players.get(pid) if pid else None
        if not p:
            return
        now = time.monotonic()
        if kind in ("feed", "feed_poop"):
            animal_system.feed(self, p, now, poop=kind == "feed_poop")
            return
        if kind == "interact":
            self.interact(p, now)
            return
        if kind == "drop_weapon":
            if p.alive:
                self.drop_weapon(p, now)
            return
        if kind == "craft_modes":
            if now < p.next_settings_attempt:
                self.send(ws, {"t": "settings_result", "ok": False, "message": "请稍后再试"})
                return
            p.next_settings_attempt = now + 2
            password = data.get("password")
            modes = data.get("modes")
            valid = isinstance(password, str) and len(password) <= 256 and isinstance(modes, list)
            if (not valid or not self.settings_digest or not hmac.compare_digest(
                    hashlib.sha256(password.encode("utf-8", errors="replace")).hexdigest(), self.settings_digest)):
                self.send(ws, {"t": "settings_result", "ok": False, "message": "密码错误或全局设置未启用"})
                return
            selected = tuple(mode for mode in ("text", "whole", "split") if mode in modes)
            self.db.set_setting("craft_modes", ",".join(selected))
            self.craft_modes = selected
            self.send(ws, {"t": "settings_result", "ok": True, "message": "全局设置已同步"})
            return
        if kind == "workbench_craft":
            workbench.craft(self,p,data.get("weapon"))
            return
        if kind == "craft":
            self.craft(p, data.get("weapon"), data.get("mode"))
            return
        if kind == "change_team":
            self.change_team(p, data.get("team"), now)
            return
        if kind == "skin":
            skin = data.get("skin")
            if skin in SKIN_NAMES:
                p.skin = skin
            return
        if kind == "team_transfer":
            target = self.players.get(data.get("target")) if isinstance(data.get("target"), str) else None
            if (target and target.id != p.id and target.alive and target.team == p.team
                    and p.alive and p.grounded and not p.recall_until and now >= p.transfer_ready):
                p.mx = p.mz = 0.0
                p.draw_started = None
                p.transfer_target = target.id
                p.recall_until = now + 3
            return
        if kind == "recall":
            if p.alive and p.grounded and not p.recall_until and now >= p.recall_ready:
                p.mx = p.mz = 0.0
                p.draw_started = None
                p.transfer_target = ""
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
            if isinstance(weapon, str) and p.weapons.get(weapon, 0):
                if weapon != p.weapon:
                    p.draw_started = None
                p.weapon = weapon
        elif kind == "draw":
            ready = p.weapons.get(p.weapon, 0) and ((p.weapon == "bow" and now - p.last_attack >= ATTACK_CD)
                     or (p.weapon == "beam" and now >= p.beam_ready))
            if p.alive and ready and p.draw_started is None:
                p.draw_started = now
        elif kind == "cancel_draw":
            p.draw_started = None
        elif kind == "attack":
            if not p.alive or not p.weapons.get(p.weapon, 0):
                return
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
                    self.spend_weapon(p)
                    p.ammo -= 1
                    p.next_round = now + .12
                    if p.ammo == 0:
                        p.gun_ready = now + 10
                    self.wave(p, yaw, now, gun=True)
            elif p.weapon == "rocket":
                if p.alive and now >= p.rocket_ready:
                    self.spend_weapon(p)
                    p.rocket_ready = now + 10
                    self.shoot(p, yaw, 0, now, 1, rocket=True)
            elif p.weapon == "beam":
                started, p.draw_started = p.draw_started, None
                if started is not None and now - started >= 1 and now >= p.beam_ready:
                    self.spend_weapon(p)
                    self.wave(p, yaw, now, beam=True)
            elif p.weapon == "bow":
                started, p.draw_started = p.draw_started, None
                if started is not None and now - started >= 0.12:
                    try:
                        pitch = float(data.get("pitch", 0))
                    except (TypeError, ValueError):
                        pitch = 0
                    pitch = max(-1.15, min(1.15, pitch)) if math.isfinite(pitch) else 0
                    if now - p.last_attack >= ATTACK_CD:
                        self.spend_weapon(p)
                        self.shoot(p, yaw, pitch, now, min(1.0, now - started))
            else:
                cooldown = {"axe": .85, "mace": 1.1, "hammer": 1.5, "dual": 0.7, "spear": 1, "blade": 1.2, "halberd": 1.35, "silver_spear": 1.1, "tiger_spear": 1.1}.get(p.weapon, ATTACK_CD)
                if now - p.last_attack >= cooldown and not p.slam_pending:
                    self.spend_weapon(p)
                    if p.weapon == "hammer" and not p.grounded:
                        p.slam_pending = True
                        p.last_attack = now
                        p.jump_speed = min(p.jump_speed, -7)
                        self.emit({"k": "attack", "id": p.id, "yaw": yaw, "hits": []})
                    else:
                        self.attack(p, yaw, now)
            if not p.weapons.get(p.weapon, 0):
                p.weapons.pop(p.weapon, None)
                p.weapon = ""
        elif kind == "chat":
            text = str(data.get("text", ""))[:100].strip()
            if text:
                self.emit({"k": "chat", "id": p.id, "name": p.name,
                           "team": p.team, "text": text})
        elif kind == "ping":
            self.send(ws, {"t": "pong", "ts": data.get("ts")})

    def spend_weapon(self, p):
        if p.weapons[p.weapon] > 0:
            p.weapons[p.weapon] -= 1

    def forge_near(self, p):
        return any(obj["kind"] in ("forge","workbench") and math.hypot(p.x - obj["x"], p.z - obj["z"]) <= 3
                   for obj in self.objects)

    def craft(self, p, weapon, mode):
        if (not isinstance(weapon, str) or weapon not in RECIPES or mode not in self.craft_modes
                or not p.alive or not self.forge_near(p) or p.weapons.get(weapon, 0)==-1 or p.weapons.get(weapon, 0) >= WEAPON_USES[mode]):
            return
        recipe = self.world["recipes"][weapon]
        remaining = p.syllables.copy()
        for material in recipe[mode]:
            if material not in remaining:
                return
            remaining.remove(material)
        p.syllables = remaining
        p.weapons[weapon] = WEAPON_USES[mode]
        p.weapon = weapon
        p.draw_started = None

    def hammer_slam(self, p, now):
        self.emit({"k": "slam", "x": p.x, "y": p.jump, "z": p.z})
        for obj in self.targets(p):
            if (obj["kind"] in ("dummy", "enemy", "time_stone", "animal") and p.jump <= 1.2
                    and math.hypot(obj["x"] - p.x, obj["z"] - p.z) <= 3.6
                    and not self.blocked(p.x, p.z, obj["x"], obj["z"])):
                self.damage_object(p, obj, 55, now)
        for q in list(self.players.values()):
            if (q.alive and q.team != p.team and now >= q.invuln_until and abs(q.jump - p.jump) <= 1.2
                    and math.hypot(q.x - p.x, q.z - p.z) <= 3.6 and not self.blocked(p.x, p.z, q.x, q.z)):
                self.damage(p, q, 55, now)

    # ---------------------------------------------------------------- combat
    def attack(self, p, yaw, now):
        damage = {"axe": 36, "mace": 42, "hammer": 55, "dual": 38, "spear": 44, "blade": 49, "halberd": 52, "silver_spear": 65, "tiger_spear": 65}.get(p.weapon, ATTACK_DAMAGE)
        cooldown = {"axe": .85, "mace": 1.1, "hammer": 1.5, "dual": 0.7, "spear": 1, "blade": 1.2, "halberd": 1.35, "silver_spear": 1.1, "tiger_spear": 1.1}.get(p.weapon, ATTACK_CD)
        if not p.alive or now - p.last_attack < cooldown:
            return
        p.last_attack = now
        p.yaw = yaw
        fx, fz = math.sin(yaw), math.cos(yaw)
        for obj in self.targets(p):
            dx, dz = obj["x"] - p.x, obj["z"] - p.z
            distance = math.hypot(dx, dz)
            if (distance <= ATTACK_RANGE and dx * fx + dz * fz >= distance * ATTACK_ARC_COS
                    and abs(p.jump - .5) < 1.7 and not self.blocked(p.x, p.z, obj["x"], obj["z"])):
                self.damage_object(p, obj, damage, now)
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
            self.damage(p, q, damage, now, mace=p.weapon == "mace")
            hits.append(q.id)
            if len(hits) >= 3:
                break
        self.emit({"k": "attack", "id": p.id, "yaw": yaw, "hits": hits})

    @staticmethod
    def material_mode(material):
        prefix = material.split(":", 1)[0]
        return prefix if prefix in ("text", "whole") else "split"

    def city_unlocked(self, city_id):
        if self.cleared_cities != getattr(self, "_unlocked_state", None):
            self._unlocked_state = self.cleared_cities.copy()
            self._unlocked = set()
            for city in self.world["cities"]:
                self._unlocked.add(city["id"])
                if city["id"] not in self.cleared_cities:
                    break
        return city_id in self._unlocked

    def locked_city_at(self, x, z):
        return any(abs(x - c["x"]) < 18 and abs(z - c["z"]) < 18
                   and not self.city_unlocked(c["id"]) for c in self.world["cities"])

    def interact(self, player, now):
        if not player.alive or player.recall_until:
            return

        def nearby(obj, reach=2):
            return (math.hypot(player.x - obj["x"], player.z - obj["z"]) <= reach
                    and abs(player.jump - obj.get("y", 0)) <= 1.2
                    and not self.blocked(player.x, player.z, obj["x"], obj["z"]))

        if player.syllable:
            if self.forge_near(player):
                player.syllables.append(player.syllable)
                player.syllable = ""
            return

        if player.crystal_source:
            crystal = next(obj for obj in self.objects if obj["id"] == player.team)
            if 0 < crystal["hp"] < crystal["max_hp"] and nearby(crystal, 5):
                amount = min(100, crystal["max_hp"] - crystal["hp"])
                crystal["hp"] += amount
                self.emit({"k": "crystal_repair", "id": player.id, "amount": amount,
                           "start": [player.x, player.jump + 1.1, player.z],
                           "end": [crystal["x"], 1.4, crystal["z"]],
                           "hp": crystal["hp"], "max_hp": crystal["max_hp"]})
                self.release_crystal_source(player.crystal_source, now)
                player.crystal_source = None
            else:
                self.drop_crystal(player, now)
            return
        available = [obj for obj in self.objects
                     if obj["hp"] and nearby(obj,3.5 if obj["kind"]=="workbench" else 2) and (obj["kind"] in ("ore", "dropped_crystal")
                         or obj["kind"] == "workbench"
                         or obj["kind"] == "resource" and player.resources.get(obj["resource"],0)<99
                         or obj["kind"] in ("farm", "villager")
                         or (obj["kind"] == "food_pickup" and player.food < 20)
                         or (obj["kind"] == "poop_pickup" and player.poop < 10)
                         or (obj["kind"] == "armor_pickup" and (not player.armor or obj["durability"] > player.armor["durability"] or ARMOR_TYPES[obj["armor_kind"]]["reduction"] > player.armor["reduction"]))
                         or (obj["kind"] == "syllable" and self.material_mode(obj["material"]) in self.craft_modes)
                         or (obj["kind"] == "weapon_pickup" and self.weapon_upgrade(player,obj)))]
        ore = min(available, key=lambda obj: math.hypot(player.x - obj["x"], player.z - obj["z"]), default=None)
        if ore:
            if ore["kind"] == "workbench":
                self.emit({"k":"workbench_open","id":player.id})
                return
            if ore["kind"] == "resource":
                workbench.collect(self,player,ore,now)
                return
            if ore["kind"] == "farm":
                farm_system.work(self, player, ore, now)
                return
            if ore["kind"] == "villager":
                farm_system.recruit(self, player, ore, now)
                return
            if ore["kind"] == "poop_pickup":
                player.poop += 1
                self.objects.remove(ore)
                self.emit({"k": "story", "id": player.id, "text": "捡到狗屎 · %d/10 · R 单独喂给狗，可能降低好感并被咬" % player.poop})
                return
            if ore["kind"] == "food_pickup":
                amount = min(20 - player.food, ore["amount"])
                player.food += amount
                if "expires" in ore:
                    ore["amount"] -= amount
                    if ore["amount"] <= 0:
                        self.objects.remove(ore)
                else:
                    ore["hp"] = 0
                    ore["ready"] = now + 20
                self.emit({"k": "story", "id": player.id, "text": "食物 +%d · %d/20 · 靠近狗按 F 喂食" % (amount, player.food)})
                return
            if ore["kind"] == "armor_pickup":
                self.drop_armor(player, now)
                cfg = ARMOR_TYPES[ore["armor_kind"]]
                player.armor = {**cfg, "kind": ore["armor_kind"], "durability": ore["durability"]}
                self.objects.remove(ore)
                self.emit({"k": "armor_equip", "id": player.id, "name": cfg["name"]})
                return
            if ore["kind"] == "weapon_pickup":
                weapon = ore["weapon"]
                player.weapons[weapon] = ore.get("uses", WEAPON_USES["pickup"])
                player.weapon = weapon
                player.draw_started = None
                if "expires" in ore:
                    self.objects.remove(ore)
                else:
                    ore["hp"] = 0
                    ore["ready"] = now + 10
                return
            if ore["kind"] == "syllable":
                player.syllable = ore["material"]
                ore["hp"] = 0
                ore["ready"] = now + 10
                return
            if ore["kind"] == "dropped_crystal":
                player.crystal_source = ore["source"]
                self.objects.remove(ore)
            else:
                ore["hp"] = 0
                ore["ready"] = None
                player.crystal_source = ore["id"]

        if ore:
            return
        special = min((o for o in self.objects if o["kind"] in ("chapter_gate", "story_npc") and nearby(o, 2.5)),
                      key=lambda o: math.hypot(player.x - o["x"], player.z - o["z"]), default=None)
        if special and special["kind"] == "chapter_gate":
            destination = special["destination"]
            if not self.city_unlocked(destination):
                self.emit({"k": "story", "id": player.id, "text": "先击败本城全部守军与三名首领，才能前往下一城。"})
                return
            city = next(c for c in self.world["cities"] if c["id"] == destination)
            player.x, player.z = city["x"], city["z"] + 16
            player.jump = player.jump_speed = 0
            player.mx = player.mz = 0
            player.draw_started = None
            player.yaw = math.pi
            player.invuln_until = max(player.invuln_until, now + 2)
            self.emit({"k": "chapter_travel", "id": player.id, "city": destination,
                       "text": "第%d章 · %s · %s" % (city["chapter"], city["name"], city["story"])})
        elif special:
            self.emit({"k": "story", "id": player.id, "text": special["name"] + "：" + special["text"]})

    def release_crystal_source(self, source, now):
        ore = next(obj for obj in self.objects if obj["id"] == source)
        ore["ready"] = now + 10

    def drop_armor(self, player, now):
        if not player.armor:
            return
        floor = max((b["h"] for b in self.blocks if b["h"] <= player.jump
                     and abs(player.x - b["x"]) < .5 and abs(player.z - b["z"]) < .5), default=0)
        self.objects.append({"id": "armor-" + uuid.uuid4().hex, "kind": "armor_pickup",
                             "armor_kind": player.armor["kind"], "durability": player.armor["durability"],
                             "x": player.x, "y": floor, "z": player.z, "hp": 1, "max_hp": 1,
                             "ready": 0, "expires": now + 180})
        player.armor = {}

    @staticmethod
    def weapon_upgrade(player,obj):
        old=player.weapons.get(obj['weapon'],0);uses=obj.get('uses',WEAPON_USES['pickup'])
        return old!=-1 and (uses==-1 or old<uses)

    def drop_weapon(self, p, now):
        weapon = p.weapon
        if p.weapons.get(weapon, 0):
            uses = p.weapons.pop(weapon)
            p.weapon = ""
            p.draw_started = None
            floor = max((b["h"] for b in self.blocks if b["h"] <= p.jump
                         and abs(p.x - b["x"]) < .5 and abs(p.z - b["z"]) < .5), default=0)
            self.objects.append({"id": "drop-weapon-" + uuid.uuid4().hex, "kind": "weapon_pickup",
                                 "weapon": weapon, "text": RECIPES[weapon][0], "uses": uses,
                                 "x": p.x, "y": floor, "z": p.z,
                                 "hp": 1, "max_hp": 1, "ready": 0, "expires": now + 60})

    def drop_crystal(self, player, now):
        source = player.crystal_source
        if not source:
            return
        player.crystal_source = None
        floor = max((b["h"] for b in self.blocks if b["h"] <= player.jump
                     and abs(player.x - b["x"]) < .5 and abs(player.z - b["z"]) < .5), default=0)
        self.objects.append({"id": "drop-" + uuid.uuid4().hex, "kind": "dropped_crystal",
                             "x": player.x, "y": floor, "z": player.z,
                             "hp": 1, "max_hp": 1, "ready": 0, "source": source, "expires": now + 60})

    def friendly_pet(self, player, obj):
        if obj.get("animal") != "dog" or not obj.get("owner"):
            return False
        return obj["owner"] == player.name or any(p.name == obj["owner"] and p.team == player.team for p in self.players.values())

    def targets(self, player):
        return [obj for obj in self.objects if obj["hp"] > 0 and (obj["kind"] in ("crystal", "bomb", "dummy", "enemy", "time_stone", "animal") or obj["kind"] == "villager" and obj.get("role") == "soldier") and obj.get("team") != player.team and not self.friendly_pet(player, obj)
                and (not obj.get("city") or self.city_unlocked(obj["city"]))]

    @staticmethod
    def object_bounds(obj):
        x, z = obj["x"], obj["z"]
        return ((x - .48, x + .48), (0, 2 if obj["kind"] in ("crystal", "dummy", "enemy") else 1.7), (z - .48, z + .48))

    def restore_world(self, now, source):
        # Temporary loot is replaced by the original map sources, including carried crystals.
        self.objects[:] = [obj for obj in self.objects if "expires" not in obj]
        for player in self.players.values():
            player.crystal_source = None
        for obj in self.objects:
            obj.update(hp=obj["max_hp"], ready=0, hurt_until=0)
            if obj["kind"] in ("enemy", "animal", "villager"):
                obj.update(x=obj["home_x"], z=obj["home_z"], last_attack=now + 1)
            if obj["kind"] == "animal":
                obj.update(angry_at="", angry_until=0, hunger=100, last_fed=now, feeding_until=0, stuck=0)
                for key in ("_path", "_path_goal", "_path_ready", "prey"):
                    obj.pop(key, None)
            if obj.get("global"):
                obj.update(hp=0, ready=now + 10)
        for arrow_id, arrow in self.arrows.items():
            self.emit({"k": "arrow_stop", "arrow": arrow_id, "position": arrow["position"], "velocity": arrow["velocity"], "rocket": arrow["rocket"]})
        self.arrows.clear()
        for plot in self.objects:
            if plot["kind"] == "farm":
                plot.update(stage=0, grow_until=0)
        animal_system.save(self)
        farm_system.save(self)
        self.emit({"k": "world_reset", "x": source["x"], "z": source["z"]})

    def damage_object(self, player, obj, amount, now):
        if obj["hp"] <= 0 or (obj.get("city") and not self.city_unlocked(obj["city"])):
            return
        if obj["kind"] == "villager":
            if obj.get("team") != player.team and obj.get("role") == "soldier":
                farm_system.hurt(self, obj, amount, now)
            return
        if obj["kind"] == "animal":
            if self.friendly_pet(player, obj):
                return
            animal_system.hurt(self, obj, amount, now, player)
            return
        obj["hp"] = max(0, obj["hp"] - amount)
        obj["hurt_until"] = now + .45
        self.emit({"k": "object_hit", "id": obj["id"], "x": obj["x"], "y": 1.1, "z": obj["z"], "dmg": amount, "hp": obj["hp"]})
        if obj["hp"]:
            return
        if obj["kind"] == "enemy":
            obj["ready"] = None  # Only this city's time stone can revive enemies.
            weapon = obj.get("loot") or random.choice(("sword", "bow", "axe", "mace"))
            uses = 40 if obj.get("boss") else 10
            self.objects.append({"id": "loot-" + uuid.uuid4().hex, "kind": "weapon_pickup",
                                 "weapon": weapon, "text": ("首领珍品 · " if obj.get("boss") else "战利品 · ") + RECIPES[weapon][0],
                                 "rarity": "boss" if obj.get("boss") else "normal", "uses": uses,
                                 "x": obj["x"], "z": obj["z"], "hp": 1, "max_hp": 1,
                                 "ready": 0, "expires": now + 180})
            if obj.get("boss") or random.random() < .3:
                kind = "elite" if obj.get("boss") else "iron"
                self.objects.append({"id": "armor-" + uuid.uuid4().hex, "kind": "armor_pickup",
                                     "armor_kind": kind, "durability": ARMOR_TYPES[kind]["max_durability"],
                                     "x": obj["x"] + .7, "z": obj["z"], "hp": 1, "max_hp": 1,
                                     "ready": 0, "expires": now + 180})
            if (obj["city"] not in self.cleared_cities and
                    not any(o["kind"] == "enemy" and o["city"] == obj["city"] and o["hp"] > 0 for o in self.objects)):
                self.cleared_cities.add(obj["city"])
                self.db.set_setting("campaign_cleared_v1", json.dumps(sorted(self.cleared_cities)))
                city = next(c for c in self.world["cities"] if c["id"] == obj["city"])
                self.emit({"k": "chapter_clear", "city": obj["city"], "text": city["name"] + "已通关！" +
                           ("下一城入口已开启。" if city["chapter"] < len(self.world["cities"]) else "十章完成，三分天下！")})
            reward = 100 if obj.get("boss") else 15
            player.score += reward
            player.session_score += reward
            self.team_score[player.team] += reward
            self.db.upsert_player(player)
            self.emit({"k": "enemy_down", "x": obj["x"], "z": obj["z"], "name": obj["name"]})
            return
        if obj["kind"] == "time_stone":
            if obj.get("global"):
                self.restore_world(now, obj)
                return
            obj["ready"] = now + 10
            for enemy in self.objects:
                if enemy["kind"] == "enemy" and enemy["city"] == obj["city"]:
                    enemy.update(hp=enemy["max_hp"], x=enemy["home_x"], z=enemy["home_z"],
                                 ready=0, last_attack=now + 1, hurt_until=0)
            self.emit({"k": "city_reset", "x": obj["x"], "z": obj["z"], "city": obj["city"]})
            return
        obj["ready"] = now + {"crystal": 30, "bomb": 20, "dummy": 5}[obj["kind"]]
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
        for block in self.blocks.nearby(p.x+delta[0]/2,p.z+delta[2]/2,max(abs(delta[0]),abs(delta[2]))/2+.5):
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
            if arrow_id not in self.arrows:
                continue
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

            for block in self.blocks.nearby(x+delta[0]/2,z+delta[2]/2,max(abs(delta[0]),abs(delta[2]))/2+.5):
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
            for b in self.blocks.nearby(x, z, .5):
                if abs(x - b["x"]) < 0.5 and abs(z - b["z"]) < 0.5:
                    return True
        return False

    def damage(self, attacker, victim, amount, now, mace=False):
        victim.recall_until = 0.0
        absorbed = 0
        if victim.armor:
            absorbed = min(victim.armor["durability"], round(amount * victim.armor["reduction"]))
            victim.armor["durability"] -= absorbed
            amount -= absorbed
            if victim.armor["durability"] <= 0:
                victim.armor = {}
                self.emit({"k": "armor_break", "id": victim.id})
        victim.hp -= amount
        victim.last_damage_at = now
        if amount > 0:
            victim.hurt_until = now + .45
        attacker.damage += int(amount)
        fx, fz = math.sin(attacker.yaw), math.cos(attacker.yaw)
        if mace:
            dx, dz = victim.x - attacker.x, victim.z - attacker.z
            distance = math.hypot(dx, dz)
            if distance:
                fx, fz = dx / distance, dz / distance
            # Sweep the whole shove so it cannot skip over a one-block wall.
            for _ in range(24):
                nx, nz = victim.x + fx * .1, victim.z + fz * .1
                if collides(nx, nz, self.blocks, feet=victim.jump):
                    break
                victim.x, victim.z = nx, nz
        else:
            nx, nz = victim.x + fx * .65, victim.z + fz * .65
            if not collides(nx, victim.z, self.blocks, feet=victim.jump):
                victim.x = nx
            if not collides(victim.x, nz, self.blocks, feet=victim.jump):
                victim.z = nz
        self.emit({"k": "hit", "id": victim.id, "by": attacker.id,
                   "x": victim.x, "y": victim.jump + 1.1, "z": victim.z, "dmg": amount, "absorbed": absorbed, "hp": max(0, round(victim.hp))})
        if victim.hp <= 0:
            self.kill(attacker, victim, now)

    def kill(self, killer, victim, now):
        self.drop_armor(victim, now)
        self.drop_weapon(victim, now)
        self.drop_crystal(victim, now)
        victim.hp = 0
        victim.alive = False
        victim.slam_pending = False
        victim.jump = victim.jump_speed = 0.0
        victim.draw_started = None
        victim.deaths += 1
        victim.session_deaths += 1
        victim.score = max(0, victim.score - DEATH_PENALTY)
        victim.respawn_at = now + RESPAWN_DELAY
        victim.mx = victim.mz = 0.0

        if killer.team == "npc":
            self.db.upsert_player(victim)
            self.db.add_history("death", victim.name, killer.name, victim.team,
                                killer.name + " 击败了 " + victim.name, 0)
            self.emit({"k": "kill", "killer": killer.name, "victim": victim.name,
                       "team": victim.team, "id": killer.id, "victim_id": victim.id})
            return

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
        spawn = self.world["teams"][p.team]["spawn"]
        p.alive = True
        p.grounded = True
        p.hp = MAX_HP
        p.x = spawn[0] + random.uniform(-1.4, 1.4)
        p.z = spawn[1] + random.uniform(-2.4, 2.4)
        p.mx = p.mz = 0.0
        p.invuln_until = now + INVULN
        p.last_damage_at = now
        self.db.add_history("respawn", p.name, team=p.team,
                            detail="在" + self.world["teams"][p.team]["name"] + "复活")
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
    def advance_enemies(self, dt, now):
        cities = {city["id"]: city for city in self.world["cities"]}
        for enemy in self.objects:
            if enemy["kind"] != "enemy" or enemy["hp"] <= 0 or not self.city_unlocked(enemy["city"]):
                continue
            city = cities[enemy["city"]]
            pet = next((o for o in self.objects if (o["kind"] == "animal" and o["animal"] == "dog" or o["kind"] == "villager" and o["role"] == "soldier")
                        and o["owner"] and o["hp"] > 0 and math.hypot(o["x"] - enemy["x"], o["z"] - enemy["z"]) <= 1.9
                        and not self.blocked(enemy["x"], enemy["z"], o["x"], o["z"])), None)
            if pet and now - enemy["last_attack"] >= 1.1:
                enemy["last_attack"] = now
                if pet["kind"] == "villager":
                    farm_system.hurt(self, pet, 20 if enemy.get("boss") else 8, now)
                else:
                    animal_system.hurt(self, pet, 20 if enemy.get("boss") else 8, now)
                continue
            candidates = [p for p in self.players.values() if p.alive
                          and abs(p.x - city["x"]) < 17 and abs(p.z - city["z"]) < 17
                          and (not enemy.get("boss") or
                               (abs(p.x - city["x"]) < 7 and abs(p.z - city["z"]) < 7))]
            target = min(candidates, key=lambda p: math.hypot(p.x - enemy["x"], p.z - enemy["z"]), default=None)
            distance = math.hypot(target.x - enemy["x"], target.z - enemy["z"]) if target else math.inf
            chasing = distance < (11 if enemy.get("boss") else 9)
            if chasing:
                tx, tz = target.x, target.z
            else:
                # Small patrol around each guard post; return after the player leaves the city.
                phase = now * .35 + enemy["home_x"] + enemy["home_z"]
                tx = enemy["home_x"] + math.sin(phase) * 1.4
                tz = enemy["home_z"] + math.cos(phase) * 1.4
            dx, dz = tx - enemy["x"], tz - enemy["z"]
            length = math.hypot(dx, dz)
            if length > (1.45 if chasing else .15):
                enemy["yaw"] = math.atan2(dx, dz)
                step = min(length, (2.2 if chasing else .8) * dt)
                nx, nz = enemy["x"] + dx / length * step, enemy["z"] + dz / length * step
                if not collides(nx, enemy["z"], self.blocks):
                    enemy["x"] = nx
                if not collides(enemy["x"], nz, self.blocks):
                    enemy["z"] = nz
            if (chasing and distance <= 1.9 and target.jump < 1.4 and now >= target.invuln_until
                    and now - enemy["last_attack"] >= (1.4 if enemy.get("boss") else 1.1)
                    and not self.blocked(enemy["x"], enemy["z"], target.x, target.z)):
                enemy["last_attack"] = now
                attacker = Player(enemy["id"], enemy["name"], "npc", None,
                                  enemy["x"], enemy["z"], yaw=enemy["yaw"])
                self.damage(attacker, target, 20 if enemy.get("boss") else 8, now)

    def advance_animals(self, dt, now):
        animal_system.advance(self, dt, now)

    def finish_special_channel(self, player, now):
        return False

    def healing_rate(self, x, z, team):
        if not any(obj["kind"] == "crystal" and obj.get("team") == team and obj["hp"] > 0 for obj in self.objects):
            return 0.0
        pool = pool_at(x,z,self.pools)
        rate = float(pool["power"]) if pool else 0.0
        x0,x1,z0,z1 = self.world["teams"][team]["zone"]
        if x0<=x<=x1 and z0<=z<=z1:
            rate=max(rate,RULES["base_heal"])
        return rate

    def transfer_arrival(self, target):
        for radius in (1.6, 2.5, 3.5):
            for step in range(12):
                angle = step * math.pi / 6
                x, z = target.x + math.cos(angle)*radius, target.z + math.sin(angle)*radius
                if (not self.locked_city_at(x,z) and not collides(x,z,self.blocks)
                        and all(not p.alive or math.hypot(p.x-x,p.z-z)>.85 for p in self.players.values())):
                    return x,z
        return None

    def tick(self):
        now = time.monotonic()
        dt = min(0.10, max(0.0, now - self.last_tick))
        self.last_tick = now
        self.tick_no += 1

        for obj in self.objects[:]:
            if now >= obj.get("expires", math.inf):
                if obj["kind"] == "dropped_crystal":
                    self.release_crystal_source(obj["source"], now)
                self.objects.remove(obj)
        for obj in self.objects:
            if not obj["hp"] and obj["ready"] is not None and now >= obj["ready"]:
                obj["hp"] = obj["max_hp"]
                if obj["kind"] in ("animal", "villager"):
                    obj.update(x=obj["home_x"], z=obj["home_z"], last_attack=now,
                               angry_at="", angry_until=0)
        previous = {p.id: (p.x, p.z) for p in self.players.values() if p.alive}
        for p in list(self.players.values()):
            if not p.alive:
                if now >= p.respawn_at:
                    self.respawn(p, now)
                continue

            if self.locked_city_at(p.x, p.z):
                city = next(c for c in self.world["cities"] if abs(p.x - c["x"]) < 18 and abs(p.z - c["z"]) < 18)
                p.x, p.z = city["x"], city["z"] + 20
                p.mx = p.mz = 0
            if now - p.last_input > 0.6:
                p.mx = p.mz = 0.0
            speed = SPRINT_SPEED if p.sprint else MOVE_SPEED
            nx = p.x + p.mx * speed * dt
            nz = p.z + p.mz * speed * dt
            if not self.locked_city_at(nx, p.z) and not collides(nx, p.z, self.blocks, feet=p.jump):
                p.x = nx
            if not self.locked_city_at(p.x, nz) and not collides(p.x, nz, self.blocks, feet=p.jump):
                p.z = nz

            support = max((b["h"] for b in self.blocks.nearby(p.x,p.z,.86) if b["h"] <= p.jump
                           and abs(p.x - b["x"]) < .86 and abs(p.z - b["z"]) < .86), default=0)
            height = p.jump + (p.jump_speed - 8 * dt) * dt
            p.grounded = height <= support
            p.jump = support if p.grounded else height
            p.jump_speed = 0.0 if p.grounded else p.jump_speed - 16 * dt
            if p.grounded and p.slam_pending:
                p.slam_pending = False
                self.hammer_slam(p, now)

            pool = pool_at(p.x, p.z, self.pools)
            p.pool_name = pool["name"] if pool else ""
            rate = self.healing_rate(p.x, p.z, p.team)
            p.heal_rate = rate
            if rate and p.hp < MAX_HP:
                p.hp = min(MAX_HP, p.hp + rate * dt)

        self.push_players(previous)
        self.advance_arrows(dt, now)
        self.advance_enemies(dt, now)
        self.advance_animals(dt, now)
        farm_system.advance(self, dt, now)
        for p in self.players.values():
            if not p.recall_until:
                p.transfer_target = ""
                continue
            if not p.alive or not p.grounded or (p.x, p.z) != previous.get(p.id):
                p.recall_until = 0.0
            elif now >= p.recall_until:
                if self.finish_special_channel(p, now):
                    continue
                p.recall_until = 0.0
                if p.transfer_target:
                    target = self.players.get(p.transfer_target)
                    arrival = self.transfer_arrival(target) if target and target.alive and target.team == p.team else None
                    p.transfer_target = ""
                    if not arrival:
                        self.emit({"k":"story","id":p.id,"text":"传送取消：队友已离线、阵亡或附近没有安全位置。"})
                        continue
                    p.transfer_ready = now + 30
                    p.x,p.z = arrival
                    p.jump=p.jump_speed=0.0
                    self.emit({"k":"team_transfer","id":p.id,"target":target.name,"x":p.x,"z":p.z})
                    continue
                p.recall_ready = now + 30
                p.x, p.z = self.world["teams"][p.team]["spawn"]
                p.jump = p.jump_speed = 0.0
                self.emit({"k": "recall", "id": p.id})

        state = {"t": "state", **self.snapshot()}
        payload = None
        for ws, pid in list(self.sockets.items()):
            if not pid:
                continue
            stream=self.object_streams.get(ws)
            if stream is not None:
                pending=stream.get('pending')
                if pending is not None and not pending.done():
                    stream['events']=(stream.get('events',[])+state['events'])[-256:]
                    continue
                packet=self.stream_state(state,self.players[pid],stream)
                stream['pending']=self.send(ws,packet)
            else:
                if payload is None:
                    payload=json.dumps(state,ensure_ascii=False,separators=(',',':'))
                self.send(ws,payload)

    def stream_state(self,state,player,stream):
        # Keep global crystals and owned companions, stream everything else nearby.
        current={o['id']:o for o in state['objects'] if o['kind']=='crystal' or o.get('owner')==player.name or (o['x']-player.x)**2+(o['z']-player.z)**2<=380**2}
        previous=stream['objects']
        changed=[];patches=[]
        for oid,obj in current.items():
            old=previous.get(oid)
            if old==obj:continue
            if old is None or old.keys()!=obj.keys() or old.get('kind')!=obj.get('kind'):
                changed.append(obj)
            else:
                patches.append({'id':oid,**{key:value for key,value in obj.items() if old[key]!=value}})
        packet={**state,'object_patches':patches,'objects':changed,'object_delta':stream['initialized'],'objects_removed':list(previous.keys()-current.keys())}
        if stream.get('events'):
            packet['events']=stream.pop('events')+state['events']
        stream['objects']={oid:copy.deepcopy(o) if previous.get(oid)!=o else previous[oid] for oid,o in current.items()}
        stream['initialized']=True
        return packet

    def change_team(self,p,team,now):
        if not isinstance(team,str) or team not in self.world['teams'] or team==p.team:
            return
        if not p.alive or now<p.next_team_change:
            self.send(p.ws,{'t':'team_result','ok':False,'message':'复活后可以换阵营。' if not p.alive else '请稍候再换阵营。'})
            return
        old=p.team
        self.drop_crystal(p,now)
        p.team=team;p.next_team_change=now+3
        p.x,p.z=self.world['teams'][team]['spawn'];p.yaw=0 if team=='red' else math.pi
        p.mx=p.mz=p.jump=p.jump_speed=0;p.grounded=True
        p.draw_started=None;p.slam_pending=False;p.recall_until=0;p.transfer_target=''
        # Preserve HP, armor, inventory and all weapon cooldowns while relocating.
        for arrow_id,arrow in list(self.arrows.items()):
            if arrow.get('owner')==p.id:self.arrows.pop(arrow_id,None)
        for npc in self.objects:
            if npc['kind']=='villager' and npc.get('owner')==p.name:
                npc['team']=team
        farm_system.save(self)
        self.team_changed(p,old,now)
        self.db.upsert_player(p)
        self.db.add_history('team_change',p.name,team=team,detail='转投'+self.world['teams'][team]['name'])
        self.emit({'k':'team_changed','id':p.id,'name':p.name,'team':team,'old_team':old,'x':p.x,'z':p.z,'yaw':p.yaw})

    def team_changed(self,player,old_team,now):
        pass

    def snapshot(self):
        now = time.monotonic()
        players = []
        for p in self.players.values():
            players.append({
                "id": p.id, "name": p.name, "team": p.team,
                "x": round(p.x, 3), "z": round(p.z, 3),
                "yaw": round(p.yaw, 3), "hp": round(p.hp, 1),
                "alive": p.alive, "hurt": now < p.hurt_until, "armor": dict(p.armor), "weapon": p.weapon, "skin": p.skin, "carries_crystal": bool(p.crystal_source), "jump": round(p.jump, 3),
                "food": p.food, "poop": p.poop, "weapons": p.weapons, "syllable": p.syllable, "syllables": p.syllables,
                "forge_near": self.forge_near(p),
                "resources":dict(p.resources),"workbench_near":workbench.near(self,p),
                "wave_cd": round(max(0, p.wave_ready - now), 1),
                "beam_cd": round(max(0, p.beam_ready - now), 1),
                "rocket_cd": round(max(0, p.rocket_ready - now), 1),
                "recall": max(0, math.ceil((p.recall_until - now) * 10) / 10),
                "recall_cd": max(0, math.ceil(p.recall_ready - now)),
                "transfer_target": p.transfer_target if p.recall_until else "",
                "transfer_cd": max(0, math.ceil(p.transfer_ready - now)),
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
            "craft_modes": self.craft_modes,
            "campaign_cleared": sorted(self.cleared_cities),
            "objects": [{**{key: value for key, value in obj.items() if not key.startswith("_") and key not in {"home_x","home_z","last_attack","last_fed","next_poop","grow_until","working_until","hurt_until","angry_until","feeding_until","stuck","prey","ready","expires"}}, "locked": bool(obj.get("city") and not self.city_unlocked(obj.get("destination", obj["city"]))), "grow_cd": max(0, math.ceil(obj.get("grow_until", 0) - now)) if obj.get("stage") == 2 else 0, "working": now < obj.get("working_until", 0), "hurt": now < obj.get("hurt_until", 0), "attacking": now - obj.get("last_attack", -10) < .3, "cooldown": max(0, math.ceil((obj["ready"] or 0) - now))} for obj in self.objects],
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
            return ws.write_message(payload)
        except Exception:
            pass
