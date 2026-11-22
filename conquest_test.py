"""Independent conquest, recruitment, PvP and safe open-world travel regression checks."""
import json
import math
import tempfile
import time
from pathlib import Path

import farm_system
from conquest import OpenWorldGame
from db import Database
from game import Game, Player
from world import collides


def main():
    with tempfile.TemporaryDirectory() as directory:
        db=Database(str(Path(directory)/'open.db'))
        db.set_setting('conquest_v1','legacy-progress')
        g=OpenWorldGame(db);now=time.monotonic()
        p=Player('red-player','红方主公','red',None,*g.world['teams']['red']['spawn'])
        q=Player('blue-player','蓝方主公','blue',None,*g.world['teams']['blue']['spawn'])
        g.players={p.id:p,q.id:q};g.sockets={'red-socket':p.id,'blue-socket':q.id}
        assert len(g.city_by_id)==24 and all(g.city_unlocked(c) for c in g.city_by_id)
        assert not g.locked_city_at(0,0)
        assert all(not collides(o['x'],o['z'],g.blocks,radius=.3) for o in g.objects
                   if o['kind'] in ('city_banner','enemy','general_recruit'))
        city=g.world['cities'][0];cid=city['id'];banner=next(o for o in g.objects if o['id']=='banner-'+cid)
        p.x,p.z=banner['x'],banner['z'];initial=g.city_owners[cid]
        g.interact(p,now);assert g.city_owners[cid]==initial
        for defender in g._city_defenders(cid):g.damage_object(p,defender,10000,now)
        assert not any(o['hp'] for o in g._city_defenders(cid))
        q.x,q.z=banner['x']+1,banner['z']
        g.interact(p,now+.5);assert g.city_owners[cid]==initial
        q.x,q.z=g.world['teams']['blue']['spawn']
        g.interact(p,now+1);assert g.city_owners[cid]=='red'
        guards=[o for o in g._city_defenders(cid) if not o.get('is_general')]
        assert all(o['hp']==o['max_hp'] and o['team']=='red' for o in guards)
        hp=guards[0]['hp'];g.damage_object(p,guards[0],50,now);assert guards[0]['hp']==hp
        # The middle general is three units from the banner: E must reach recruitment.
        general=[o for o in g.objects if o.get('is_general') and o.get('origin_city')==cid][1]
        marker=next(o for o in g.objects if o['id']=='recruit-'+general['id'])
        assert marker['hp']==1
        p.x,p.z=marker['x'],marker['z'];g.interact(p,now+2)
        assert general['kind']=='villager' and general['owner']==p.name and general['team']=='red'
        assert general['attack_damage']==28 and marker['hp']==0
        q.x,q.z=p.x,p.z;g.interact(q,now+3);assert general['owner']==p.name
        q.x,q.z=g.world['teams']['blue']['spawn']
        # Follow long distances, recover health inside owned city, fight hostile players.
        p.x,p.z=city['travel_spawn'];farm_system.advance(g,.05,now+4)
        assert math.hypot(general['x']-p.x,general['z']-p.z)<5
        p.x,p.z=banner['x'],banner['z'];general.update(x=p.x+1,z=p.z,hp=100)
        farm_system.advance(g,.5,now+5);assert general['hp']>100 and general['heal']>0
        q.x,q.z=p.x+2,p.z;q.invuln_until=0;q.armor={};general['last_attack']=0
        general.update(x=q.x,z=q.z+1);hp=q.hp;farm_system.advance(g,.01,now+7);assert q.hp<hp
        # Direct player combat remains enabled and cancels channeled travel.
        q.recall_until=now+10;hp=q.hp;g.damage(p,q,5,now+8)
        assert q.hp<hp and not q.recall_until
        q.x,q.z=g.world['teams']['blue']['spawn']
        # Other camp can capture the same city; recruited generals retain their loyalty.
        for defender in g._city_defenders(cid):g.damage_object(q,defender,10000,now+9)
        p.x,p.z=g.world['teams']['red']['spawn'];q.x,q.z=banner['x'],banner['z']
        g.interact(q,now+10);assert g.city_owners[cid]=='blue' and general['team']=='red'
        assert g.healing_rate(banner['x'],banner['z'],'red')==0
        assert g.healing_rate(banner['x'],banner['z'],'blue')>0
        crystal=next(o for o in g.objects if o['kind']=='crystal' and o['team']=='blue')
        crystal['hp']=0;assert g.healing_rate(banner['x'],banner['z'],'blue')==0
        machine=next(o for o in g.objects if o.get('global'));g.restore_world(now+11,machine)
        assert g.city_owners[cid]=='blue' and general['owner']==p.name and general['hp']==general['max_hp']
        # Namespaced persistence protects the legacy mode and restores conquest identities.
        assert db.get_setting('conquest_v1')=='legacy-progress'
        restored=OpenWorldGame(db)
        restored_general=next(o for o in restored.objects if o['id']==general['id'])
        assert restored.city_owners[cid]=='blue' and restored_general['owner']==p.name
        assert Game(db).world.get('mode')!='open'
        # Any city can be visited, but arrival is outside its fortifications.
        p.transfer_ready=0;p.grounded=True;p.recall_until=0
        target=g.world['cities'][-1]
        g.handle('red-socket',json.dumps({'t':'open_travel','city':target['id']}))
        assert p.id in g._marches and p.recall_until>0
        until=p.recall_until;assert g.finish_special_channel(p,until+.01)
        assert not p.recall_until and p.id not in g._marches
        assert math.hypot(p.x-target['travel_spawn'][0],p.z-target['travel_spawn'][1])<4
        assert not collides(p.x,p.z,g.blocks) and p.transfer_ready>until+29
        previous=(p.x,p.z);g.handle('red-socket',json.dumps({'t':'open_travel','city':'base'}))
        assert p.id not in g._marches and (p.x,p.z)==previous
        p.transfer_ready=0;g.handle('red-socket',json.dumps({'t':'open_travel','city':'base'}))
        p.x+=.1;g._finish_marches(time.monotonic());assert not p.recall_until and p.id not in g._marches
        state=g.snapshot();assert state['conquest']['total']==24 and state['conquest']['owned']['blue']==1
        assert sum(len(c['generals']) for c in state['conquest']['cities'])==72
        print('CONQUEST PASSED: 24 free cities; 72 generals; safe spawns; blocked/contested capture; allied guards; recruitment; follow/heal/PvP; recapture; reset; isolated persistence; safe timed travel/cancel/cooldown; global snapshot')


if __name__=='__main__':main()
