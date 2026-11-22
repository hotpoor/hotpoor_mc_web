"""Village farming, individual goodwill and recruitable militia."""
import json
import math
import time
import animal_system
from world import collides


def initialize(game):
    try:
        saved = json.loads(game.db.get_setting('militia_farms_v1') or '{}')
    except (ValueError, TypeError):
        saved = {}
    for vi, village in enumerate(game.world['villages']):
        for index, side in enumerate((-1, 1)):
            x = village['x'] + (side * 5.5 if village['axis'] == 'z' else -4)
            z = village['z'] + (side * 5.5 if village['axis'] == 'x' else -4)
            npc_id = 'farmer-' + village['id'] + '-' + str(index)
            plot_id = 'farm-' + village['id'] + '-' + str(index)
            record = saved.get(npc_id, {})
            home_x = x + (0 if village['axis'] == 'z' else -2)
            home_z = z + (0 if village['axis'] == 'x' else -2)
            game.objects.append({'id': npc_id, 'kind': 'villager', 'village': village['id'],
                                 'name': village['name'] + ('阿禾' if index == 0 else '阿田'),
                                 'home_x': home_x, 'home_z': home_z, 'x': home_x, 'z': home_z,
                                 'hp': 120, 'max_hp': 120, 'ready': 0, 'yaw': 0, 'last_attack': 0,
                                 'role': record.get('role', 'farmer'), 'owner': record.get('owner', ''),
                                 'team': record.get('team', ''), 'favor': record.get('favor', {}), 'moving': False})
            field = saved.get(plot_id, {})
            game.objects.append({'id': plot_id, 'kind': 'farm', 'farmer_id': npc_id,
                                 'name': village['name'] + '军屯田', 'x': x, 'z': z,
                                 'hp': 1, 'max_hp': 1, 'ready': 0, 'stage': field.get('stage', 0),
                                 'grow_until': time.monotonic() + max(0, field.get('grow_epoch', 0) - time.time())})
    game.last_militia_save = time.monotonic()


def save(game):
    data = {}
    for obj in game.objects:
        if obj['kind'] == 'villager':
            data[obj['id']] = {key: obj[key] for key in ('role', 'owner', 'team', 'favor')}
        elif obj['kind'] == 'farm':
            data[obj['id']] = {'stage': obj['stage'], 'grow_epoch': time.time() + max(0, obj['grow_until'] - time.monotonic())}
    game.db.set_setting('militia_farms_v1', json.dumps(data, ensure_ascii=False))


def message(game, p, text):
    game.emit({'k': 'story', 'id': p.id, 'text': text})


def work(game, p, plot, now):
    if now - p.last_farm < .7:
        return
    p.last_farm = now
    farmer = next(o for o in game.objects if o['id'] == plot['farmer_id'])
    if plot['stage'] == 2 and now >= plot['grow_until']:
        plot['stage'] = 3
    if plot['stage'] == 2:
        message(game, p, '庄稼生长中 · 还有 %d 秒' % max(1, math.ceil(plot['grow_until'] - now)))
        return
    stage = plot['stage']
    gain = 20 if stage == 3 else 10
    farmer['favor'][p.name] = min(100, farmer['favor'].get(p.name, 0) + gain)
    if stage == 0:
        plot['stage'], action = 1, '耕地完成，再按 E 播种'
    elif stage == 1:
        plot['stage'], plot['grow_until'], action = 2, now + 30, '播种完成，30 秒后成熟'
    else:
        plot['stage'], action = 0, '收获完成 · 粮食 +3，可继续耕种'
        overflow = max(0, p.food + 3 - 20)
        p.food = min(20, p.food + 3)
        if overflow:
            game.objects.append({'id': 'grain-' + plot['id'] + '-' + str(now), 'kind': 'food_pickup',
                                 'text': '军屯粮食', 'amount': overflow, 'x': plot['x'], 'z': plot['z'],
                                 'hp': 1, 'max_hp': 1, 'ready': 0, 'expires': now + 180})
    farmer['working_until'] = now + .7
    save(game)
    detail = '已追随 ' + farmer['owner'] + '，本田仍可产粮' if farmer['owner'] and farmer['owner'] != p.name else farmer['name'] + '好感 +%d（%d/80）' % (gain, farmer['favor'][p.name])
    message(game, p, action + ' · ' + detail)
    game.emit({'k': 'farm_work', 'id': p.id, 'x': plot['x'], 'z': plot['z'], 'harvest': stage == 3})


def recruit(game, p, farmer, now):
    if farmer['owner']:
        message(game, p, farmer['name'] + ('已是你的小兵，会跟随并助战。' if farmer['owner'] == p.name else '已追随 ' + farmer['owner']))
        return
    favor = farmer['favor'].get(p.name, 0)
    if favor < 80:
        message(game, p, farmer['name'] + '：帮助我耕地、播种和收获，达到 80 好感就追随你。当前 %d/80。' % favor)
        return
    farmer.update(role='soldier', owner=p.name, team=p.team, hp=120, last_attack=now)
    save(game)
    message(game, p, farmer['name'] + '已被感化，加入军屯小兵！')
    game.emit({'k': 'militia_recruit', 'id': p.id, 'npc_id': farmer['id']})


def hurt(game, soldier, amount, now):
    if soldier['hp'] <= 0:
        return
    soldier['hp'] = max(0, soldier['hp'] - amount)
    soldier['hurt_until'] = now + .45
    game.emit({'k': 'object_hit', 'id': soldier['id'], 'x': soldier['x'], 'y': 1.1,
               'z': soldier['z'], 'dmg': amount, 'hp': soldier['hp']})
    if not soldier['hp']:
        soldier['ready'] = now + 60


def advance(game, dt, now):
    villagers = [o for o in game.objects if o['kind'] == 'villager' and o['hp'] > 0]
    players = {p.name: p for p in game.players.values() if p.alive}
    for plot in game.objects:
        if plot['kind'] == 'farm' and plot['stage'] == 2 and now >= plot['grow_until']:
            plot['stage'] = 3
    for npc in villagers:
        owner = players.get(npc['owner'])
        if npc['role'] != 'soldier' or not owner:
            phase = now * .3 + npc['home_x']
            animal_system.move(game, npc, npc['home_x'] + math.sin(phase), npc['home_z'] + math.cos(phase), .65, dt)
            continue
        if math.hypot(npc['x'] - owner.x, npc['z'] - owner.z) > 16:
            animal_system.catch_up(game, npc, owner)
        pack = sorted((n for n in villagers if n['owner'] == npc['owner']), key=lambda n:n['id'])
        slot = pack.index(npc)
        side = -1 if slot % 2 == 0 else 1
        targets = [o for o in game.objects if o['hp'] > 0 and
                   (o['kind'] == 'enemy' and game.city_unlocked(o['city']) or o['kind'] == 'animal' and o['animal'] != 'dog')
                   and math.hypot(o['x'] - owner.x, o['z'] - owner.z) < 8
                   and not game.blocked(npc['x'], npc['z'], o['x'], o['z'])]
        target = min(targets, key=lambda o: math.hypot(o['x'] - npc['x'], o['z'] - npc['z']), default=None)
        if target:
            dx,dz = target['x'] - owner.x, target['z'] - owner.z
            length = math.hypot(dx,dz) or 1
            tx,tz = target['x'] - dz/length*side*1.2,target['z'] + dx/length*side*1.2
        else:
            offset = side * (2.2 + slot//2)
            tx,tz = owner.x - math.sin(owner.yaw)*3 + math.cos(owner.yaw)*offset, owner.z - math.cos(owner.yaw)*3 - math.sin(owner.yaw)*offset
        animal_system.move(game,npc,tx,tz,3.7,dt,stop=.2)
        if target and math.hypot(target['x']-npc['x'],target['z']-npc['z'])<2 and now-npc['last_attack']>=1.1:
            npc['last_attack']=now
            game.damage_object(owner,target,14,now)
    # Idle villagers and militia keep enough space to avoid merging into a single figure.
    for i,left in enumerate(villagers):
        for right in villagers[i+1:]:
            dx,dz=right['x']-left['x'],right['z']-left['z']
            distance=math.hypot(dx,dz)
            if distance>=1:continue
            if distance<.001:dx,dz,distance=1,0,1
            push=.12
            for npc,sign in ((left,-1),(right,1)):
                x,z=npc['x']+sign*dx/distance*push,npc['z']+sign*dz/distance*push
                if not game.locked_city_at(x,z) and not collides(x,z,game.blocks,radius=.3):npc['x'],npc['z']=x,z
    for npc in villagers:
        if npc['role'] != 'soldier':
            continue
        for pet in game.objects:
            if pet['kind'] != 'animal' or pet['animal'] != 'dog' or not pet['owner'] or pet['hp'] <= 0:
                continue
            dx, dz = npc['x'] - pet['x'], npc['z'] - pet['z']
            distance = math.hypot(dx, dz)
            if distance >= 1.1:
                continue
            if distance < .001:
                dx, dz, distance = 1, 0, 1
            x, z = npc['x'] + dx / distance * .15, npc['z'] + dz / distance * .15
            if not game.locked_city_at(x, z) and not collides(x, z, game.blocks, radius=.3):
                npc['x'], npc['z'] = x, z
    if now-game.last_militia_save>60:
        save(game);game.last_militia_save=now
