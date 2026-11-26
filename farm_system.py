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


def fertilize(game, p, now):
    """Return whether a nearby field handled R; never feed a dog through a field."""
    if not p.alive or p.recall_until or p.jump >= 1.4 or now-p.last_feed < .8:
        return True
    plot = min((o for o in game.objects if o['kind']=='farm' and o['hp']>0
                and math.hypot(o['x']-p.x,o['z']-p.z)<=3.5
                and not game.blocked(p.x,p.z,o['x'],o['z'])),
               key=lambda o:math.hypot(o['x']-p.x,o['z']-p.z),default=None)
    if not plot:return False
    if plot['stage']!=2 or plot['grow_until']<=now:
        if plot['stage']==2:plot['stage']=3
        message(game,p,'只有生长中的庄稼可以施肥，未消耗狗屎。');return True
    if p.poop<=0:
        message(game,p,'没有狗屎，按 E 拾取后再来施肥。');return True
    p.poop-=1;p.last_feed=now
    plot['grow_until']=max(now,plot['grow_until']-5)
    if plot['grow_until']<=now:plot['stage']=3
    save(game)
    message(game,p,'施肥成功 · 生长时间缩短5秒 · '+('庄稼已成熟！' if plot['stage']==3 else '还有%d秒'%math.ceil(plot['grow_until']-now)))
    game.emit(dict(k='farm_work',id=p.id,x=plot['x'],z=plot['z'],fertilize=True,harvest=False))
    return True


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
    packs = {}
    for npc in villagers:
        if npc['owner']:
            packs.setdefault(npc['owner'], []).append(npc)
    slots = {npc['id']: i for pack in packs.values() for i,npc in enumerate(sorted(pack,key=lambda n:n['id']))}
    hostiles = [o for o in game.objects if o['hp']>0 and (o['kind']=='enemy' and game.city_unlocked(o['city']) or o['kind']=='animal' and o['animal']!='dog')]
    targets_by_owner = {name: [o for o in hostiles if o.get('team')!=owner.team and math.hypot(o['x']-owner.x,o['z']-owner.z)<8] for name,owner in players.items()}
    if game.world.get('mode')=='open':
        for name,owner in players.items():
            targets_by_owner[name].extend({'kind':'player','player_id':p.id,'hp':p.hp,'x':p.x,'z':p.z} for p in players.values() if p.team!=owner.team and now>=p.invuln_until and p.jump<1.4 and math.hypot(p.x-owner.x,p.z-owner.z)<8)
    for npc in villagers:
        owner = players.get(npc['owner'])
        rate = game.healing_rate(npc['x'],npc['z'],npc['team']) if npc['role']=='soldier' and npc['team'] in game.world['teams'] else 0
        npc['heal'] = rate
        if rate and npc['hp']<npc['max_hp']:
            npc['hp']=round(min(npc['max_hp'],npc['hp']+rate*dt),1)
        if npc['role'] != 'soldier' or not owner:
            phase = now * .3 + npc['home_x']
            animal_system.move(game, npc, npc['home_x'] + math.sin(phase), npc['home_z'] + math.cos(phase), .65, dt)
            continue
        if math.hypot(npc['x'] - owner.x, npc['z'] - owner.z) > 16:
            animal_system.catch_up(game, npc, owner)
        slot = slots[npc['id']]
        side = -1 if slot % 2 == 0 else 1
        candidates = sorted((o for o in targets_by_owner.get(npc['owner'],()) if o['hp']>0),key=lambda o:(o['x']-npc['x'])**2+(o['z']-npc['z'])**2)
        target = next((o for o in candidates if not game.blocked(npc['x'],npc['z'],o['x'],o['z'])),None)
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
            if target['kind']=='player':
                victim=game.players.get(target['player_id'])
                if victim and victim.alive and now>=victim.invuln_until:game.damage(owner,victim,npc.get('attack_damage',14),now)
            else:
                game.damage_object(owner,target,npc.get('attack_damage',14),now)
    # Nearby buckets replace all-pairs separation as armies grow.
    cells = {}
    for npc in villagers:
        cells.setdefault((math.floor(npc['x']/2),math.floor(npc['z']/2)),[]).append(npc)
    order={npc['id']:i for i,npc in enumerate(villagers)}
    pets={}
    for pet in game.objects:
        if pet['kind']=='animal' and pet['animal']=='dog' and pet['owner'] and pet['hp']>0:
            pets.setdefault((math.floor(pet['x']/2),math.floor(pet['z']/2)),[]).append(pet)
    for left in villagers:
        cx,cz=math.floor(left['x']/2),math.floor(left['z']/2)
        for bx in range(cx-1,cx+2):
            for bz in range(cz-1,cz+2):
                for right in cells.get((bx,bz),()):
                    if order[right['id']]<=order[left['id']]:continue
                    dx,dz=right['x']-left['x'],right['z']-left['z'];distance=math.hypot(dx,dz)
                    if distance>=1:continue
                    if distance<.001:dx,dz,distance=1,0,1
                    for npc,sign in ((left,-1),(right,1)):
                        x,z=npc['x']+sign*dx/distance*.12,npc['z']+sign*dz/distance*.12
                        if not game.locked_city_at(x,z) and not collides(x,z,game.blocks,radius=.3):npc['x'],npc['z']=x,z
                if left['role']!='soldier':continue
                for pet in pets.get((bx,bz),()):
                    dx,dz=left['x']-pet['x'],left['z']-pet['z'];distance=math.hypot(dx,dz)
                    if distance>=1.1:continue
                    if distance<.001:dx,dz,distance=1,0,1
                    x,z=left['x']+dx/distance*.15,left['z']+dz/distance*.15
                    if not game.locked_city_at(x,z) and not collides(x,z,game.blocks,radius=.3):left['x'],left['z']=x,z
    if now-game.last_militia_save>60:
        save(game);game.last_militia_save=now
