# -*- coding: utf-8 -*-
"""Static world definition.

The exact same world dict is generated on the server and sent to every client
in the `welcome` message, so collision detection and rendering never disagree.
Coordinates: X/Z is the ground plane, Y is up. One unit == one block.
"""

import math
import random
from campaign import CITIES

HALF = 140.0
SIZE = 280.0
SEED = 20261114

TEAMS = {
    "red": {
        "key": "red",
        "name": "赤焰营地",
        "short": "赤焰",
        "spawn": [-24.0, 0.0],
        "zone": [-30.0, -18.0, -7.0, 7.0],
        "color": "#ef4f4f",
        "accent": "#ffb08a",
    },
    "blue": {
        "key": "blue",
        "name": "苍蓝营地",
        "short": "苍蓝",
        "spawn": [24.0, 0.0],
        "zone": [18.0, 30.0, -7.0, 7.0],
        "color": "#4c86f0",
        "accent": "#a5d4ff",
    },
}

# Healing pools are the contested objectives of the map.
HEAL_POOLS = [
    {"x": 0.0, "z": 0.0, "r": 3.6, "power": 18, "name": "中央圣泉"},
    {"x": 0.0, "z": -19.0, "r": 3.0, "power": 15, "name": "北泉"},
    {"x": 0.0, "z": 19.0, "r": 3.0, "power": 15, "name": "南泉"},
    {"x": -13.0, "z": -13.0, "r": 2.8, "power": 14, "name": "西泉"},
    {"x": 13.0, "z": 13.0, "r": 2.8, "power": 14, "name": "东泉"},
    {"x": -13.0, "z": 13.0, "r": 2.8, "power": 14, "name": "林间泉"},
    {"x": 13.0, "z": -13.0, "r": 2.8, "power": 14, "name": "岩间泉"},
]

# Campaign cities surround the original multiplayer arena; wide gates face every road.



def city_blocks():
    blocks = []
    for city in CITIES:
        rings = (18, 8)
        for radius in rings:
            used = set()
            for offset in range(-radius, radius + 1):
                for side, x, z in (("north", offset, -radius), ("south", offset, radius),
                                   ("west", -radius, offset), ("east", radius, offset)):
                    if abs(offset) <= 3 and side in city["gates"]:
                        continue
                    if (x, z) in used:
                        continue
                    used.add((x, z))
                    blocks.append({"x": city["x"] + x, "z": city["z"] + z,
                                   "h": 4 if radius == 18 else 3, "type": "brick"})
        # Houses flank the roads, leaving the centre and the gates free.
        for dx, dz in ((-12, -10), (12, -10), (-12, 10), (12, 10)):
            for ox in range(-1, 2):
                for oz in range(-1, 2):
                    blocks.append({"x": city["x"] + dx + ox, "z": city["z"] + dz + oz,
                                   "h": 3 if abs(ox) == 1 or abs(oz) == 1 else 4, "type": "stone"})
    return blocks


ROUTES = []
VILLAGES = []
MOATS = []
for index, city in enumerate(CITIES):
    previous = CITIES[index - 1] if index else {"id": "arena", "x": 0, "z": 0}
    dx, dz = city["x"] - previous["x"], city["z"] - previous["z"]
    cx, cz = (city["x"] + previous["x"]) / 2, (city["z"] + previous["z"]) / 2
    axis = "x" if dx else "z"
    route = {"id": "road-" + city["id"], "city": city["id"], "axis": axis,
             "x": cx, "z": cz, "length": abs(dx or dz)}
    ROUTES.append(route)
    village = {"id": "village-" + city["id"], "name": ["桃园村", "会盟驿", "乌巢村", "当阳村", "江畔镇",
                  "荆南村", "蜀道驿", "定军村", "襄水镇", "三国驿"][index],
               "x": cx, "z": cz, "axis": axis, "city": city["id"]}
    VILLAGES.append(village)
    HEAL_POOLS.append({"x": cx, "z": cz, "r": 1.8, "power": 16, "name": village["name"] + "回血泉"})
    # Moats span between city walls; both banks enclose a broad road and village shoulders.
    start = 18 if index else 22
    length = max(1, route["length"] - start - 18)
    middle_x = (previous["x"] + (dx and (1 if dx > 0 else -1) * (start + length / 2))) if dx else cx
    middle_z = (previous["z"] + (dz and (1 if dz > 0 else -1) * (start + length / 2))) if dz else cz
    for side in [-1, 1]:
        mx, mz = middle_x + (side * 10.5 if axis == "z" else 0), middle_z + (side * 10.5 if axis == "x" else 0)
        width, depth = (length, 3) if axis == "x" else (3, length)
        MOATS.append({"x0": mx - width / 2, "x1": mx + width / 2,
                      "z0": mz - depth / 2, "z1": mz + depth / 2})


def village_blocks():
    blocks = []
    for village in VILLAGES:
        for side in [-1, 1]:
            # Small houses on the shoulders, outside the central seven-block road.
            hx = village["x"] + (side * 6 if village["axis"] == "z" else 4)
            hz = village["z"] + (side * 6 if village["axis"] == "x" else 4)
            for dx in [-1, 0, 1]:
                for dz in [-1, 0, 1]:
                    blocks.append({"x": hx + dx, "z": hz + dz, "h": 2 if abs(dx) + abs(dz) else 3,
                                   "type": "bark"})
    return blocks


RULES = {
    "max_hp": 100,
    "speed": 5.4,
    "sprint": 8.2,
    "attack_range": 3.3,
    "attack_arc": 65,
    "attack_damage": 26,
    "attack_cooldown": 0.5,
    "respawn": 5.0,
    "invulnerable": 1.5,
    "kill_score": 100,
    "death_penalty": 20,
    "base_heal": 24.0,
    "idle_regen": 2.5,
    "idle_regen_delay": 6.0,
    "tick_rate": 20,
}


def _generate_blocks():
    rng = random.Random(SEED)
    blocks = []
    used = set()

    def is_free(x, z):
        if abs(x) < 9 and z < -21:
            return False
        if abs(x) > 29 or abs(z) > 29:
            return False
        if (x, z) in used:
            return False
        for team in TEAMS.values():
            x0, x1, z0, z1 = team["zone"]
            if x0 - 1.5 <= x <= x1 + 1.5 and z0 - 1.5 <= z <= z1 + 1.5:
                return False
            if math.hypot(x - team["spawn"][0], z - team["spawn"][1]) < 5.0:
                return False
        for pool in HEAL_POOLS:
            if math.hypot(x - pool["x"], z - pool["z"]) < pool["r"] + 1.8:
                return False
        return True

    def put(x, z, height, kind):
        used.add((x, z))
        blocks.append({"x": x, "z": z, "h": height, "type": kind})

    clusters = 0
    guard = 0
    while clusters < 30 and guard < 4000:
        guard += 1
        cx, cz = rng.randint(-27, 27), rng.randint(-27, 27)
        if not is_free(cx, cz):
            continue
        kind = rng.choice(["stone", "stone", "brick", "tree", "tree"])
        height = 3 if kind == "tree" else rng.randint(1, 2)
        put(cx, cz, height, kind)
        for _ in range(rng.randint(0, 3)):
            nx, nz = cx + rng.choice([-1, 0, 1]), cz + rng.choice([-1, 0, 1])
            if (nx, nz) != (cx, cz) and is_free(nx, nz):
                put(nx, nz, 1 if kind != "tree" else 2, kind)
        clusters += 1

    # A few low cover walls near the middle arena, hand-placed for good fights.
    for x, z, h, kind in [
        (-6, -6, 1, "brick"), (-5, -6, 1, "brick"), (-4, -6, 1, "brick"),
        (6, 6, 1, "brick"), (5, 6, 1, "brick"), (4, 6, 1, "brick"),
        (-6, 6, 1, "stone"), (-6, 5, 2, "stone"),
        (6, -6, 1, "stone"), (6, -5, 2, "stone"),
    ]:
        if is_free(x, z):
            put(x, z, h, kind)

    return blocks


def collides(x, z, blocks, radius=0.36, feet=0):
    """Server-side wall collision. Blocks are 1x1 AABBs centred on integer x/z."""
    edge = HALF - 1.0 - radius
    if x < -edge or x > edge or z < -edge or z > edge:
        return True
    if any(m["x0"] - radius < x < m["x1"] + radius and m["z0"] - radius < z < m["z1"] + radius for m in MOATS):
        return True
    limit = 0.5 + radius
    for b in blocks:
        if feet < b["h"] and abs(x - b["x"]) < limit and abs(z - b["z"]) < limit:
            return True
    return False


def in_zone(x, z, zone):
    x0, x1, z0, z1 = zone
    return x0 <= x <= x1 and z0 <= z <= z1


def pool_at(x, z, pools=HEAL_POOLS):
    for pool in pools:
        if math.hypot(x - pool["x"], z - pool["z"]) <= pool["r"]:
            return pool
    return None


def in_own_base(x, z, team):
    return in_zone(x, z, TEAMS[team]["zone"])


def build_world():
    return {
        "size": SIZE,
        "half": HALF,
        "teams": TEAMS,
        "pools": HEAL_POOLS,
        "blocks": _generate_blocks() + city_blocks() + village_blocks(),
        "cities": CITIES,
        "routes": ROUTES, "villages": VILLAGES, "moats": MOATS,
        "rules": RULES,
    }
