"""Server-authoritative wildlife, food, individual dog trust and companions."""
import json
import heapq
import math
import random
import time
import uuid
from world import collides


def initialize(game):
    try:
        saved = json.loads(game.db.get_setting('dog_companions_v1') or '{}')
    except (ValueError, TypeError):
        saved = {}
    for obj in game.objects:
        if obj['kind'] != 'animal':
            continue
        hp = {'dog': 100, 'wolf': 80, 'tiger': 180}[obj['animal']]
        obj.update(hp=hp, max_hp=hp, last_attack=0, last_fed=time.monotonic(),
                   owner='', favor={}, angry_at='', angry_until=0, hunger=70, next_poop=time.monotonic() + random.uniform(30, 60))
        if obj['animal'] == 'dog':
            record = saved.get(obj['id'], {})
            obj['owner'] = record.get('owner', '')
            obj['favor'] = record.get('favor', {})
            obj['hunger'] = record.get('hunger', 70)
    for village in game.world['villages']:
        game.objects.append({'id': 'food-' + village['id'], 'kind': 'food_pickup', 'amount': 3,
                             'text': '狗粮 / 兽肉 · 3份', 'x': village['x'] - 2.5, 'z': village['z'],
                             'hp': 1, 'max_hp': 1, 'ready': 0})
    game.last_dog_save = time.monotonic()
    game.next_animal_item = time.monotonic() + 15
    for village in game.world['villages']:
        spawn_item(game, village, 'food_pickup', time.monotonic())
        spawn_item(game, village, 'poop_pickup', time.monotonic())


def save(game):
    game.db.set_setting('dog_companions_v1', json.dumps({
        o['id']: {'owner': o['owner'], 'favor': o['favor'], 'hunger': o['hunger']}
        for o in game.objects if o['kind'] == 'animal' and o['animal'] == 'dog'}, ensure_ascii=False))


def feed(game, player, now, poop=False):
    if not player.alive or player.recall_until or now - player.last_feed < .8:
        return
    dog = min((o for o in game.objects if o['kind'] == 'animal' and o['animal'] == 'dog'
               and o['hp'] > 0 and math.hypot(o['x'] - player.x, o['z'] - player.z) <= 2.6
               and player.jump < 1.4 and not game.blocked(player.x, player.z, o['x'], o['z'])),
              key=lambda o: math.hypot(o['x'] - player.x, o['z'] - player.z), default=None)
    if not dog:
        game.emit({'k': 'story', 'id': player.id, 'text': '靠近村犬后按 F 喂食。'})
        return
    if (player.poop if poop else player.food) <= 0:
        game.emit({'k': 'story', 'id': player.id, 'text': '没有狗屎。' if poop else '没有狗粮，村镇和野兽掉落的食物可按 E 拾取。'})
        return
    player.last_feed = now
    dog['feeding_until'] = now + 8
    if poop:
        player.poop -= 1
        hunger = dog['hunger']
        delta = -5 if hunger < 25 else -20 if hunger < 70 else -40
        reaction = '极饿，勉强吃下，但好感仍下降' if hunger < 25 else '嫌弃狗屎，好感下降' if hunger < 70 else '吃饱时拒绝狗屎，非常生气'
        if hunger < 70:
            dog['hunger'] = min(100, hunger + 8)
    else:
        player.food -= 1
        delta, reaction = 35, '喂食狗粮成功'
        dog['hp'] = min(dog['max_hp'], dog['hp'] + 30)
        dog['hunger'] = min(100, dog['hunger'] + 35)
        dog['last_fed'] = now
    dog['favor'][player.name] = max(-100, min(100, dog['favor'].get(player.name, 0) + delta))
    if dog['favor'][player.name] <= -25:
        dog['angry_at'], dog['angry_until'] = player.name, now + 30
        if dog['owner'] == player.name:
            dog['owner'] = ''
    if dog['angry_at'] == player.name and dog['favor'][player.name] > -25:
        dog['angry_at'], dog['angry_until'] = '', 0
    if dog['favor'][player.name] >= 100 and not dog['owner']:
        dog['owner'] = player.name
    save(game)
    game.emit({'k': 'animal_feed', 'id': player.id, 'animal_id': dog['id'],
               'text': ('驯服成功！村犬会跟随你并协助战斗。' if dog['owner'] == player.name
                        else ('村犬已有主人：' + dog['owner'] if dog['owner'] else '村犬回应'))
                       + ' · ' + reaction + ' · 好感 ' + str(round(dog['favor'][player.name])) + '/100'})


def hurt(game, animal, amount, now, player=None):
    if animal['hp'] <= 0:
        return
    if animal['animal'] == 'dog' and player:
        favor = max(-100, animal['favor'].get(player.name, 0) - 35)
        animal['favor'][player.name] = favor
        if favor <= -25:
            animal['angry_at'], animal['angry_until'] = player.name, now + 30
            if animal['owner'] == player.name:
                animal['owner'] = ''
            game.emit({'k': 'story', 'id': player.id, 'text': '村犬好感降至 ' + str(round(favor)) + '，正在反击你！'})
        save(game)
    animal['hp'] = max(0, animal['hp'] - amount)
    animal['hurt_until'] = now + .45
    game.emit({'k': 'object_hit', 'id': animal['id'], 'x': animal['x'], 'y': .9, 'z': animal['z'], 'dmg': amount, 'hp': animal['hp']})
    if animal['hp']:
        return
    animal['ready'] = now + 60
    animal['angry_at'], animal['angry_until'] = '', 0
    if animal['animal'] != 'dog':
        tiger = animal['animal'] == 'tiger'
        game.objects.append({'id': 'meat-' + uuid.uuid4().hex, 'kind': 'food_pickup',
                             'text': '兽肉', 'amount': 4 if tiger else 2, 'x': animal['x'], 'z': animal['z'],
                             'hp': 1, 'max_hp': 1, 'ready': 0, 'expires': now + 180})
        game.objects.append({'id': 'hide-' + uuid.uuid4().hex, 'kind': 'armor_pickup', 'armor_kind': 'iron',
                             'durability': 80 if tiger else 40, 'x': animal['x'] + .7, 'z': animal['z'],
                             'hp': 1, 'max_hp': 1, 'ready': 0, 'expires': now + 180})
    game.emit({'k': 'animal_down', 'name': animal['name'], 'animal_id': animal['id'],
               'x': animal['x'], 'z': animal['z']})


def navigation_grid(game):
    key = len(game.blocks), tuple(sorted(game.cleared_cities))
    if getattr(game, 'animal_nav_key', None) == key:
        return game.animal_nav_blocked
    blocked = set()
    for b in game.blocks:
        for x in range(math.floor(b['x'] - .8), math.ceil(b['x'] + .8) + 1):
            for z in range(math.floor(b['z'] - .8), math.ceil(b['z'] + .8) + 1):
                if abs(x - b['x']) < .8 and abs(z - b['z']) < .8:
                    blocked.add((x, z))
    for m in game.world['moats']:
        for x in range(math.ceil(m['x0'] - .3), math.floor(m['x1'] + .3) + 1):
            for z in range(math.ceil(m['z0'] - .3), math.floor(m['z1'] + .3) + 1):
                blocked.add((x, z))
    for c in game.world['cities']:
        if not game.city_unlocked(c['id']):
            blocked.update((x, z) for x in range(c['x'] - 17, c['x'] + 18) for z in range(c['z'] - 17, c['z'] + 18))
    game.animal_nav_key, game.animal_nav_blocked = key, blocked
    return blocked


def steer(game, animal, tx, tz):
    blocked = navigation_grid(game)
    start, goal = (round(animal['x']), round(animal['z'])), (round(tx), round(tz))
    steps = max(1, math.ceil(math.hypot(tx - animal['x'], tz - animal['z']) * 2))
    if all((round(animal['x'] + (tx - animal['x']) * i / steps), round(animal['z'] + (tz - animal['z']) * i / steps)) not in blocked for i in range(1, steps + 1)):
        animal.pop('_path', None)
        return tx, tz
    now = game.last_tick
    if now >= animal.get('_path_ready', 0) and (animal.get('_path_goal') != goal or not animal.get('_path')):
        animal['_path_ready'], animal['_path_goal'] = now + .7, goal
        if goal in blocked:
            nearby = [(goal[0] + x, goal[1] + z) for x in range(-2, 3) for z in range(-2, 3) if (goal[0] + x, goal[1] + z) not in blocked]
            goal = min(nearby, key=lambda n: math.hypot(n[0] - tx, n[1] - tz), default=goal)
        animal['_path'] = []
        frontier, costs, parent = [(0, start)], {start: 0}, {}
        limit = game.world['half'] - 1.3
        for _ in range(3000):
            if not frontier:
                break
            _, node = heapq.heappop(frontier)
            if node == goal:
                path = []
                while node != start:
                    path.append(node); node = parent[node]
                animal['_path'] = path[::-1]
                break
            for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = node[0] + dx, node[1] + dz
                if nxt in blocked or abs(nxt[0]) > limit or abs(nxt[1]) > limit:
                    continue
                cost = costs[node] + 1
                if cost < costs.get(nxt, math.inf):
                    costs[nxt], parent[nxt] = cost, node
                    heapq.heappush(frontier, (cost + abs(nxt[0] - goal[0]) + abs(nxt[1] - goal[1]), nxt))
    path = animal.get('_path', [])
    while path and math.hypot(path[0][0] - animal['x'], path[0][1] - animal['z']) < .25:
        path.pop(0)
    return path[0] if path else (tx, tz)


def move(game, animal, tx, tz, speed, dt, stop=.15):
    distance = math.hypot(tx - animal['x'], tz - animal['z'])
    if distance > stop:
        sx, sz = steer(game, animal, tx, tz)
        if (sx, sz) != (tx, tz):
            tx, tz, stop = sx, sz, .05
    dx, dz = tx - animal['x'], tz - animal['z']
    length = math.hypot(dx, dz)
    animal['moving'] = length > stop
    if length <= stop:
        return False
    animal['yaw'] = math.atan2(dx, dz)
    step = min(length - stop, speed * dt)
    old = animal['x'], animal['z']
    nx, nz = animal['x'] + dx / length * step, animal['z'] + dz / length * step
    if not game.locked_city_at(nx, animal['z']) and not collides(nx, animal['z'], game.blocks, radius=.3):
        animal['x'] = nx
    if not game.locked_city_at(animal['x'], nz) and not collides(animal['x'], nz, game.blocks, radius=.3):
        animal['z'] = nz
    return math.hypot(animal['x'] - old[0], animal['z'] - old[1]) > .001


def catch_up(game, dog, owner):
    for dx, dz in ((1.6, 0), (-1.6, 0), (0, 1.6), (0, -1.6), (1.5, 1.5), (-1.5, -1.5)):
        x, z = owner.x + dx, owner.z + dz
        if not game.locked_city_at(x, z) and not collides(x, z, game.blocks, radius=.3):
            dog['x'], dog['z'] = x, z
            dog['stuck'] = 0
            return


def spawn_item(game, village, kind, now):
    if sum(o['kind'] in ('food_pickup', 'poop_pickup') and 'expires' in o for o in game.objects) >= 40:
        return
    for _ in range(16):
        x, z = village['x'] + random.uniform(-4, 4), village['z'] + random.uniform(-4, 4)
        if collides(x, z, game.blocks, radius=.25) or game.locked_city_at(x, z):
            continue
        game.objects.append({'id': 'random-' + uuid.uuid4().hex, 'kind': kind,
                             'text': '狗屎' if kind == 'poop_pickup' else '狗粮',
                             'amount': 1 if kind == 'poop_pickup' else random.randint(1, 3),
                             'x': x, 'z': z, 'hp': 1, 'max_hp': 1, 'ready': 0, 'expires': now + 120})
        return


def advance(game, dt, now):
    from game import Player
    animals = [o for o in game.objects if o['kind'] == 'animal' and o['hp'] > 0]
    alive = [p for p in game.players.values() if p.alive]
    for animal in animals:
        if animal['hp'] <= 0:
            continue
        dog = animal['animal'] == 'dog'
        owner = next((p for p in alive if p.name == animal['owner']), None) if dog else None
        if dog:
            animal['hunger'] = max(0, animal['hunger'] - dt * .25)
            if now >= animal['next_poop']:
                if animal['hunger'] > 30:
                    spawn_item(game, {'x': animal['x'], 'z': animal['z']}, 'poop_pickup', now)
                animal['next_poop'] = now + random.uniform(30, 60)
        if dog and animal['hunger'] < 25:
            animal['favor'] = {name: max(0, value - dt * .25) if value > 0 else value
                               for name, value in animal['favor'].items()}
        victim = None
        if dog and now < animal['angry_until']:
            victim = next((p for p in alive if p.name == animal['angry_at']
                           and math.hypot(p.x - animal['x'], p.z - animal['z']) < 10), None)
        elif not dog:
            victim = next((p for p in alive if p.name == animal.get('prey') and math.hypot(p.x - animal['x'], p.z - animal['z']) < 35), None)
            if not victim:
                candidates = [p for p in alive if math.hypot(p.x - animal['x'], p.z - animal['z']) < (10 if animal['animal'] == 'tiger' else 8)]
                victim = min(candidates, key=lambda p: math.hypot(p.x - animal['x'], p.z - animal['z']), default=None)
            animal['prey'] = victim.name if victim else ''
        target = None
        if dog and owner and not victim:
            if math.hypot(owner.x - animal['x'], owner.z - animal['z']) > 14:
                catch_up(game, animal, owner)
            targets = [o for o in game.objects if o['hp'] > 0 and
                       (o['kind'] == 'enemy' and game.city_unlocked(o['city'])
                        or o['kind'] == 'animal' and o['animal'] != 'dog')
                       and math.hypot(o['x'] - owner.x, o['z'] - owner.z) < 7
                       and not game.blocked(animal['x'], animal['z'], o['x'], o['z'])]
            target = min(targets, key=lambda o: math.hypot(o['x'] - animal['x'], o['z'] - animal['z']), default=None)
        pack = sorted((o for o in animals if dog and o['animal'] == 'dog' and o['owner'] == animal['owner']), key=lambda o: o['id'])
        slot = pack.index(animal) if dog and owner else 0
        side = -1 if slot % 2 == 0 else 1
        if victim:
            tx, tz = victim.x, victim.z
        elif target:
            tx, tz = target['x'], target['z']
        elif owner:
            offset = side * (1.5 + (slot // 2) * .9)
            tx = owner.x - math.sin(owner.yaw) * 1.8 + math.cos(owner.yaw) * offset
            tz = owner.z - math.cos(owner.yaw) * 1.8 - math.sin(owner.yaw) * offset
        elif dog and now < animal.get('feeding_until', 0):
            tx, tz = animal['x'], animal['z']
        else:
            phase = now * .3 + animal['home_x']
            tx, tz = animal['home_x'] + math.sin(phase) * 1.5, animal['home_z'] + math.cos(phase) * 1.5
        combat = victim is not None or target is not None
        mx, mz = tx, tz
        if target and owner:
            dx, dz = target['x'] - owner.x, target['z'] - owner.z
            length = math.hypot(dx, dz) or 1
            mx, mz = tx - dz / length * side * 1.1, tz + dx / length * side * 1.1
        moved = move(game, animal, mx, mz, 3.5 if combat or owner else .75, dt,
                     .12 if target else 1.15 if victim else .3 if owner else .15)
        if owner and not combat:
            animal['stuck'] = 0 if moved else animal.get('stuck', 0) + dt
            if animal['stuck'] > 4 and math.hypot(owner.x - animal['x'], owner.z - animal['z']) > 5:
                catch_up(game, animal, owner)
        if (combat and math.hypot(tx - animal['x'], tz - animal['z']) <= 1.7
                and now - animal['last_attack'] >= 1.2 and not game.blocked(animal['x'], animal['z'], tx, tz)):
            animal['last_attack'] = now
            if victim and victim.jump < 1.4 and now >= victim.invuln_until:
                attacker = Player(animal['id'], animal['name'], 'npc', None, animal['x'], animal['z'], yaw=animal['yaw'])
                game.damage(attacker, victim, 24 if animal['animal'] == 'tiger' else 10, now)
            elif target and owner:
                game.damage_object(owner, target, 12, now)
        # Wild beasts also defend themselves against a biting companion.
        if not dog and now - animal['last_attack'] >= 1.2:
            pet = next((o for o in animals if o['animal'] == 'dog' and o['owner'] and o['hp'] > 0
                        and math.hypot(o['x'] - animal['x'], o['z'] - animal['z']) <= 1.7
                        and not game.blocked(animal['x'], animal['z'], o['x'], o['z'])), None)
            if pet:
                animal['last_attack'] = now
                hurt(game, pet, 24 if animal['animal'] == 'tiger' else 10, now)
    # Resolve dog/dog overlap with collision-safe, symmetric pushes.
    dogs = [o for o in animals if o['animal'] == 'dog' and o['hp'] > 0]
    for _ in range(3):
        for i, left in enumerate(dogs):
            for j, right in enumerate(dogs[i + 1:]):
                dx, dz = right['x'] - left['x'], right['z'] - left['z']
                distance = math.hypot(dx, dz)
                if distance >= 1.2:
                    continue
                if distance < .001:
                    dx, dz, distance = math.cos(i + j + 1), math.sin(i + j + 1), 1
                    push = .3
                else:
                    push = min(.2, (1.2 - distance) / 2)
                for obj, sign in ((left, -1), (right, 1)):
                    x, z = obj['x'] + sign * dx / distance * push, obj['z'] + sign * dz / distance * push
                    if not game.locked_city_at(x, z) and not collides(x, z, game.blocks, radius=.3):
                        obj['x'], obj['z'] = x, z
    if now >= game.next_animal_item:
        spawn_item(game, random.choice(game.world['villages']), random.choice(('food_pickup', 'poop_pickup')), now)
        game.next_animal_item = now + random.uniform(15, 25)
    if now - game.last_dog_save >= 60:
        save(game)
        game.last_dog_save = now
