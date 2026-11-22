"""Independent Three Kingdoms open-world room and persistent city conquest."""
import json
import math
import random
import time
import uuid

import animal_system
import farm_system
from campaign import NAME_SKINS
from game import Game, Player, ARMOR_TYPES, MATERIALS, RECIPES, WEAPON_USES
from world import collides


class NamespacedDB:
    """Keep mode progress independent while retaining the existing player account table."""
    def __init__(self, database, prefix='open:'):
        self.database = database
        self.prefix = prefix

    def get_setting(self, name):
        return self.database.get_setting(self.prefix + name)

    def set_setting(self, name, value):
        return self.database.set_setting(self.prefix + name, value)

    def __getattr__(self, name):
        return getattr(self.database, name)


class OpenWorldGame(Game):
    def __init__(self, db):
        from open_world import build_open_world
        scoped = NamespacedDB(db)
        super().__init__(scoped)
        legacy_rules = {key: self.world[key] for key in ('materials', 'weapon_uses', 'recipes', 'armor_types')}
        self.world = build_open_world()
        self.world.update(legacy_rules)
        self.world.update(mode='open', name='三国开放世界 · 群雄割据')
        self.blocks = self.world['blocks']
        self.pools = self.world['pools']
        self.cleared_cities = set()
        self.city_by_id = {city['id']: city for city in self.world['cities']}
        self._marches = {}
        try:
            saved = json.loads(scoped.get_setting('conquest_v1') or '{}')
        except (TypeError, ValueError):
            saved = {}
        self.city_owners = {
            city['id']: saved.get('owners', {}).get(city['id'], city['faction'])
            for city in self.world['cities']
        }
        valid_holders = set(self.world['factions']) | {'red', 'blue'}
        for city in self.world['cities']:
            if self.city_owners[city['id']] not in valid_holders:
                self.city_owners[city['id']] = city['faction']
        self.general_owners = saved.get('generals', {})
        self.objects = []
        self._build_objects()
        animal_system.initialize(self)
        farm_system.initialize(self)
        self._sync_city_objects()
        self.world['conquest_goal'] = len(self.world['cities'])

    @staticmethod
    def _point(city, key, fallback):
        point = city.get(key, fallback)
        if isinstance(point, dict):
            return point['x'], point['z']
        return tuple(point[:2])

    def _holder_color(self, holder):
        cfg = self.world['teams'].get(holder) or self.world['factions'].get(holder, {})
        color = cfg.get('color', '#9b8157')
        return int(color.lstrip('#'), 16) if isinstance(color, str) else color

    def _build_objects(self):
        for team, cfg in self.world['teams'].items():
            sx, sz = cfg['spawn']
            self.objects.extend([
                dict(id=team, kind='crystal', team=team, x=sx, z=sz-5,
                     hp=500, max_hp=500, ready=0),
                dict(id='world-time-'+team, kind='time_stone', base_team=team, **{'global': True},
                     name='全图时光机 · 恢复守军和补给', x=sx+6, z=sz+5,
                     hp=100, max_hp=100, ready=0),
                dict(id='forge-'+team, kind='forge', x=sx-6, z=sz+3,
                     hp=1, max_hp=1, ready=0),
            ])
            for index, (weapon, (word, _)) in enumerate(RECIPES.items()):
                self.objects.append(dict(id='supply-'+team+'-'+weapon, kind='weapon_pickup',
                                         weapon=weapon, text=word+' · 营地补给', uses=30,
                                         x=sx+(index%4)*2-3, z=sz+8+(index//4)*2,
                                         hp=1, max_hp=1, ready=0))
            for index, weapon in enumerate(('sword', 'bow', 'axe')):
                self.objects.append(dict(id='material-'+team+'-'+weapon, kind='syllable',
                                         text=RECIPES[weapon][0], material='text:'+weapon,
                                         x=sx-8, z=sz+index*2, hp=1, max_hp=1, ready=0))
        for city_index, city in enumerate(self.world['cities']):
            cid, cx, cz = city['id'], city['x'], city['z']
            owner = self.city_owners[cid]
            capture = self._point(city, 'capture', (cx, cz-15))
            self.objects.append(dict(id='banner-'+cid, kind='city_banner', city=cid,
                                     name=city['name']+'府衙 · 占领 E', owner=owner,
                                     x=capture[0], z=capture[1], hp=1, max_hp=1, ready=0))
            guard_spawns = city.get('guard_spawns') or [
                (cx-5,cz+25), (cx+5,cz+25), (cx,cz+19), (cx-18,cz),
                (cx+18,cz), (cx-5,cz-7), (cx+5,cz-7), (cx,cz+6)]
            for index, point in enumerate(guard_spawns):
                x,z = (point['x'],point['z']) if isinstance(point,dict) else point[:2]
                self.objects.append(dict(id='guard-'+cid+'-'+str(index), kind='enemy', city=cid,
                                         name=city['name']+'守军', team=owner, faction=owner,
                                         color=self._holder_color(owner), guard=True,
                                         x=x,z=z,home_x=x,home_z=z, hp=100,max_hp=100,
                                         ready=0,yaw=0,last_attack=0))
            generals = city.get('generals') or [
                dict(name=name,skin=NAME_SKINS.get(name,'ranger'),weapon='sword')
                for name in city['bosses']]
            points = city.get('general_spawns') or [(cx-5,cz-15),(cx,cz-18),(cx+5,cz-15)]
            for index, general in enumerate(generals):
                gid = 'general-'+cid+'-'+str(index)
                point=points[index%len(points)]
                x,z = (point['x'],point['z']) if isinstance(point,dict) else point[:2]
                name=general['name']
                weapon=general.get('weapon','spear')
                hp=420+index*40+(city_index%4)*20
                record=self.general_owners.get(gid,{})
                recruited=bool(record.get('owner') and record.get('team') in ('red','blue'))
                obj=dict(id=gid,general_id=gid,is_general=True,city=cid,origin_city=cid,
                         name=name,skin=general.get('skin',NAME_SKINS.get(name,'ranger')),
                         weapon=weapon,attack_damage=28,loot=weapon,boss=True,guard=True,color=self._holder_color(owner),
                         x=x,z=z,home_x=x,home_z=z,max_hp=hp,hp=hp,ready=0,yaw=0,last_attack=0,
                         team=owner,faction=owner)
                if recruited:
                    obj.update(kind='villager',role='soldier',owner=record['owner'],team=record['team'],
                               favor={record['owner']:100},guard=False)
                else:
                    obj.update(kind='enemy',hp=0 if owner in ('red','blue') else hp,
                               ready=None if owner in ('red','blue') else 0)
                self.objects.append(obj)
                self.objects.append(dict(id='recruit-'+gid,kind='general_recruit',city=cid,
                                         general_id=gid,name=name,skin=obj['skin'],weapon=weapon,
                                         x=x,z=z,owner=owner,hp=0,max_hp=1,ready=None))
            # A captured city has a practical supply cache beside its government courtyard.
            self.objects.append(dict(id='city-food-'+cid,kind='food_pickup',city=cid,
                                     amount=3,text=city['name']+'粮仓',x=cx+8,z=cz-12,
                                     hp=1,max_hp=1,ready=0))
            self.objects.append(dict(id='city-sword-'+cid,kind='weapon_pickup',city=cid,
                                     weapon='sword',uses=30,text=city['name']+'军械库 · 宝剑',
                                     x=cx+10,z=cz-12,hp=1,max_hp=1,ready=0))

    def _save_conquest(self):
        self.db.set_setting('conquest_v1', json.dumps(
            dict(owners=self.city_owners,generals=self.general_owners),ensure_ascii=False))

    def _sync_city_objects(self):
        by_id={o['id']:o for o in self.objects}
        for obj in self.objects:
            if obj['kind']=='city_banner':
                obj['owner']=self.city_owners[obj['city']]
            elif obj['kind']=='general_recruit':
                source=by_id.get(obj['general_id'])
                obj['owner']=self.city_owners[obj['city']]
                obj['hp']=int(bool(source and source['kind']=='enemy' and
                                   obj['owner'] in ('red','blue') and
                                   (source['hp']<=0 or source.get('team')==obj['owner'])))
                obj['ready']=None

    def city_unlocked(self, city_id):
        return True

    def locked_city_at(self, x, z):
        return False

    def join(self, ws, raw_name, requested_team, skin=None):
        was_joined=bool(self.sockets.get(ws))
        super().join(ws,raw_name,requested_team,skin)
        if was_joined:
            return
        p=self.players.get(self.sockets.get(ws))
        if not p:
            return
        p.weapons={'sword':50,'bow':50,'axe':30}
        p.weapon='sword'
        p.food=5
        p.armor={**ARMOR_TYPES['iron'],'kind':'iron','durability':80}
        self.emit(dict(k='story',id=p.id,text='群雄割据：按 M 查看中国城池，任意选城出征。击败守军，进入府衙按 E 占领，再招募武将。'))

    def healing_rate(self,x,z,team):
        crystal=next((o for o in self.objects if o['kind']=='crystal' and o['team']==team),None)
        if not crystal or crystal['hp']<=0:
            return 0.0
        rate=super().healing_rate(x,z,team)
        # City pools share the city's allegiance instead of healing its attackers.
        for pool in self.pools:
            if pool.get('city') and self.city_owners.get(pool['city'])!=team and math.hypot(x-pool['x'],z-pool['z'])<=pool['r']:
                rate=0.0
        for city in self.world['cities']:
            if self.city_owners[city['id']]==team and abs(x-city['x'])<city.get('radius',36)-3 and abs(z-city['z'])<city.get('radius',36)-3:
                px,pz=self._point(city,'capture',(city['x'],city['z']-15))
                rate=max(rate,24 if math.hypot(x-px,z-pz)<9 else 18)
        return rate

    def _city_defenders(self,cid):
        return [o for o in self.objects if o['kind']=='enemy' and o.get('city')==cid and o.get('guard')]

    def targets(self,player):
        return [o for o in super().targets(player) if o.get('team')!=player.team]

    def damage_object(self,player,obj,amount,now):
        if obj['hp']<=0 or obj.get('team')==player.team:
            return
        if obj['kind']!='enemy' or not obj.get('guard'):
            return super().damage_object(player,obj,amount,now)
        obj['hp']=max(0,obj['hp']-amount)
        obj['hurt_until']=now+.45
        self.emit(dict(k='object_hit',id=obj['id'],x=obj['x'],y=1.1,z=obj['z'],dmg=amount,hp=obj['hp']))
        if obj['hp']:
            return
        obj['ready']=None
        weapon=obj.get('loot') or random.choice(('sword','bow','axe','mace'))
        self.objects.append(dict(id='open-loot-'+uuid.uuid4().hex,kind='weapon_pickup',weapon=weapon,
                                 text=('名将珍品 · ' if obj.get('is_general') else '守军战利品 · ')+RECIPES[weapon][0],
                                 uses=40 if obj.get('is_general') else 15,rarity='boss' if obj.get('is_general') else 'normal',
                                 x=obj['x'],z=obj['z'],hp=1,max_hp=1,ready=0,expires=now+180))
        if obj.get('is_general'):
            self.objects.append(dict(id='open-armor-'+uuid.uuid4().hex,kind='armor_pickup',armor_kind='elite',
                                     durability=160,x=obj['x']+.7,z=obj['z'],hp=1,max_hp=1,ready=0,expires=now+180))
        reward=80 if obj.get('is_general') else 10
        player.score+=reward;player.session_score+=reward;self.team_score[player.team]+=reward
        self.db.upsert_player(player)
        self.emit(dict(k='enemy_down',x=obj['x'],z=obj['z'],name=obj['name']))
        self._sync_city_objects()
        if not any(o['hp']>0 for o in self._city_defenders(obj['city'])):
            self.emit(dict(k='city_cleared',city=obj['city'],text=self.city_by_id[obj['city']]['name']+'守军已肃清，前往府衙按 E 占领！'))

    def _near(self,p,obj,reach=3):
        return p.jump<1.3 and math.hypot(p.x-obj['x'],p.z-obj['z'])<=reach and not self.blocked(p.x,p.z,obj['x'],obj['z'])

    def interact(self,p,now):
        if not p.alive or p.recall_until:
            return
        banner=next((o for o in self.objects if o['kind']=='city_banner' and self._near(p,o,2.4)),None)
        if banner:
            cid=banner['city'];owner=self.city_owners[cid]
            if owner==p.team:
                self.emit(dict(k='story',id=p.id,text=self.city_by_id[cid]['name']+'已是己方城池，可休整、补给或招募武将。'))
            elif any(o['hp']>0 for o in self._city_defenders(cid)):
                self.emit(dict(k='story',id=p.id,text='府衙尚有守军，击败本城全部守军和主将后才能占领。'))
            elif any(q.alive and q.team!=p.team and math.hypot(q.x-banner['x'],q.z-banner['z'])<8 for q in self.players.values()):
                self.emit(dict(k='story',id=p.id,text='府衙正在争夺，先击退附近敌方玩家。'))
            else:
                self.city_owners[cid]=p.team
                for obj in self._city_defenders(cid):
                    obj.update(team=p.team,faction=p.team,color=self._holder_color(p.team))
                    if not obj.get('is_general'):
                        obj.update(hp=obj['max_hp'],ready=0,x=obj['home_x'],z=obj['home_z'],last_attack=now+1)
                self._save_conquest();self._sync_city_objects()
                p.score+=200;p.session_score+=200;self.team_score[p.team]+=200;self.db.upsert_player(p)
                self.emit(dict(k='city_captured',city=cid,team=p.team,by=p.name,text=p.name+'占领了'+self.city_by_id[cid]['name']+'！'))
                if all(holder==p.team for holder in self.city_owners.values()):
                    self.emit(dict(k='conquest_victory',team=p.team,text=self.world['teams'][p.team]['name']+'已统一全部城池！'))
            return
        marker=next((o for o in self.objects if o['kind']=='general_recruit' and o['hp']>0 and self._near(p,o,2.5)),None)
        if marker:
            if self.city_owners[marker['city']]!=p.team:
                self.emit(dict(k='story',id=p.id,text='占领这座城池后，才能招募城中的武将。'))
                return
            source=next(o for o in self.objects if o['id']==marker['general_id'])
            if source['kind']=='villager':
                return
            source.update(kind='villager',role='soldier',owner=p.name,team=p.team,guard=False,
                          hp=source['max_hp'],ready=0,last_attack=now,favor={p.name:100})
            self.general_owners[source['id']]=dict(owner=p.name,team=p.team)
            self._save_conquest();self._sync_city_objects()
            self.emit(dict(k='general_recruited',id=p.id,general=source['name'],general_id=source['id'],text=source['name']+'归附，开始跟随并协助战斗！'))
            return
        super().interact(p,now)

    def handle(self,ws,msg):
        try:
            data=json.loads(msg)
        except (ValueError,TypeError):
            return super().handle(ws,msg)
        if not isinstance(data,dict) or data.get('t')!='open_travel':
            return super().handle(ws,msg)
        p=self.players.get(self.sockets.get(ws))
        if not p or not p.alive or not p.grounded or p.recall_until or time.monotonic()<p.transfer_ready:
            return
        destination=data.get('city')
        if not isinstance(destination,str) or destination!='base' and destination not in self.city_by_id:
            return
        now=time.monotonic()
        p.mx=p.mz=0.0;p.draw_started=None;p.transfer_target='';p.recall_until=now+3
        self._marches[p.id]=dict(city=destination,start=(p.x,p.z))

    def _finish_marches(self,now):
        for pid,march in list(self._marches.items()):
            p=self.players.get(pid)
            if not p or not p.alive or not p.grounded or not p.recall_until or (p.x,p.z)!=march['start']:
                self._marches.pop(pid,None)
                if p:p.recall_until=0
                continue
            if now<p.recall_until:
                continue
            if march['city']=='base':
                x,z=self.world['teams'][p.team]['spawn'];name='己方营地'
            else:
                city=self.city_by_id[march['city']]
                x,z=self._point(city,'travel_spawn',city.get('safe_spawn',(city['x']+4,city['z']+52)))
                name=city['name']+'城外'
            destination=next(((x+dx,z+dz) for dx,dz in ((0,0),(1.5,0),(-1.5,0),(0,1.5),(0,-1.5),(3,0),(-3,0))
                              if not collides(x+dx,z+dz,self.blocks) and
                              all(q.id==p.id or not q.alive or math.hypot(q.x-x-dx,q.z-z-dz)>.85 for q in self.players.values())),None)
            p.recall_until=0;p.transfer_target='';self._marches.pop(pid,None)
            if not destination:
                self.emit(dict(k='story',id=p.id,text='驿路落点暂不可用，请稍后再试。'));continue
            p.x,p.z=destination;p.jump=p.jump_speed=0;p.mx=p.mz=0
            p.transfer_ready=now+30;p.invuln_until=max(p.invuln_until,now+1)
            self.emit(dict(k='open_travel',id=p.id,city=march['city'],name=name,x=p.x,z=p.z))

    def finish_special_channel(self,p,now):
        if p.id not in self._marches:
            return False
        self._finish_marches(now)
        return True

    def tick(self):
        self._finish_marches(time.monotonic())
        super().tick()

    def advance_enemies(self,dt,now):
        alive=[p for p in self.players.values() if p.alive]
        companions=[o for o in self.objects if o['kind']=='villager' and o.get('role')=='soldier' and o['hp']>0]
        for enemy in self.objects:
            if enemy['kind']!='enemy' or not enemy.get('guard') or enemy['hp']<=0:
                continue
            city=self.city_by_id[enemy['city']]
            nearby=[p for p in alive if p.team!=enemy['team'] and math.hypot(p.x-city['x'],p.z-city['z'])<city.get('radius',36)+18]
            if not nearby:
                continue
            pet=min((o for o in companions if o.get('team')!=enemy['team'] and math.hypot(o['x']-enemy['x'],o['z']-enemy['z'])<2
                     and not self.blocked(enemy['x'],enemy['z'],o['x'],o['z'])),key=lambda o:math.hypot(o['x']-enemy['x'],o['z']-enemy['z']),default=None)
            if pet and now-enemy['last_attack']>=1.2:
                enemy['last_attack']=now;farm_system.hurt(self,pet,20 if enemy.get('boss') else 9,now);continue
            target=min(nearby,key=lambda p:math.hypot(p.x-enemy['x'],p.z-enemy['z']))
            distance=math.hypot(target.x-enemy['x'],target.z-enemy['z'])
            chasing=distance<(20 if enemy.get('boss') else 16)
            if chasing:tx,tz=target.x,target.z
            else:tx,tz=enemy['home_x'],enemy['home_z']
            animal_system.move(self,enemy,tx,tz,2.6 if chasing else 1.5,dt,stop=1.45 if chasing else .2)
            if chasing and distance<2 and target.jump<1.4 and now>=target.invuln_until and now-enemy['last_attack']>=1.2 and not self.blocked(enemy['x'],enemy['z'],target.x,target.z):
                enemy['last_attack']=now
                attacker=Player(enemy['id'],enemy['name'],'npc',None,enemy['x'],enemy['z'],yaw=enemy['yaw'])
                self.damage(attacker,target,22 if enemy.get('boss') else 9,now)

    def restore_world(self,now,source):
        super().restore_world(now,source)
        for obj in self.objects:
            if obj['kind']=='enemy' and obj.get('guard'):
                owner=self.city_owners[obj['city']]
                obj.update(team=owner,faction=owner,color=self._holder_color(owner))
        self._sync_city_objects()
        self._save_conquest()

    def snapshot(self):
        self._sync_city_objects()
        state=super().snapshot()
        for row in state['players']:
            march=self._marches.get(row['id'])
            row['open_travel']=march['city'] if march and row['recall'] else ''
        cities=[]
        for city in self.world['cities']:
            defenders=self._city_defenders(city['id'])
            remaining=sum(o['hp']>0 for o in defenders)
            cities.append(dict(id=city['id'],name=city['name'],owner=self.city_owners[city['id']],
                               guards=remaining,defenders=remaining,total_defenders=len(defenders),capturable=remaining==0,
                               generals=[dict(id=o['id'],name=o['name'],owner=o.get('owner',''),team=o.get('team',''),
                                              recruited=o['kind']=='villager',hp=o['hp'])
                                         for o in self.objects if o.get('is_general') and o.get('origin_city')==city['id']]))
        owned={team:sum(holder==team for holder in self.city_owners.values()) for team in ('red','blue')}
        state['conquest']=dict(owners=dict(self.city_owners),cities=cities,total=len(cities),owned=owned,
                               factions=self.world['factions'],victory=next((team for team,count in owned.items() if count==len(cities)),None))
        return state
