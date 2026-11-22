"""Military farms: authoritative stages, goodwill, recruitment and allied combat."""
import tempfile
import time
from pathlib import Path
from db import Database
from game import Game, Player
import farm_system
from world import collides


def main():
    with tempfile.TemporaryDirectory() as directory:
        db=Database(str(Path(directory)/'farms.db'));g=Game(db);now=time.monotonic()
        fields=[o for o in g.objects if o['kind']=='farm'];farmers=[o for o in g.objects if o['kind']=='villager']
        assert len(fields)==len(farmers)==20
        assert all(not collides(o['x'],o['z'],g.blocks,radius=.3) for o in fields+farmers)
        plot=fields[0];farmer=next(o for o in farmers if o['id']==plot['farmer_id'])
        p=Player('p','军屯甲','red',None,plot['x'],plot['z']);q=Player('q','军屯乙','blue',None,-24,0)
        g.players={p.id:p,q.id:q}
        farm_system.recruit(g,p,farmer,now)
        assert farmer['role']=='farmer'
        # Actual shared E interaction performs each stage and prevents early harvest/spam.
        g.interact(p,now+1);assert plot['stage']==1 and farmer['favor'][p.name]==10
        g.interact(p,now+1.1);assert plot['stage']==1
        g.interact(p,now+2);assert plot['stage']==2 and farmer['favor'][p.name]==20
        g.interact(p,now+3);assert plot['stage']==2 and farmer['favor'][p.name]==20
        plot['grow_until']=now+3
        farm_system.advance(g,.05,now+4);assert plot['stage']==3
        g.interact(p,now+5);assert plot['stage']==0 and p.food==6 and farmer['favor'][p.name]==40
        assert farmer['favor'].get(q.name,0)==0
        # A second cycle reaches recruitment. Food capacity does not discard the excess.
        p.food=19
        for t in (6,7):g.interact(p,now+t)
        plot['grow_until']=now+7
        g.interact(p,now+8)
        assert p.food==20 and farmer['favor'][p.name]==80
        assert any(o['id'].startswith('grain-') and o['amount']==2 for o in g.objects)
        p.x,p.z=farmer['x'],farmer['z'];g.interact(p,now+9)
        assert farmer['owner']==p.name and farmer['role']=='soldier' and farmer['team']=='red'
        farm_system.recruit(g,q,farmer,now+10);assert farmer['owner']==p.name
        # Owner travel, battle and guard retaliation use existing shared collision/navigation.
        p.x,p.z=-24,0
        g.last_tick=now+11;farm_system.advance(g,.05,now+11)
        assert math_distance(farmer,p)<3 and not collides(farmer['x'],farmer['z'],g.blocks,radius=.3)
        guard=next(o for o in g.objects if o['kind']=='enemy' and o['city']=='yellow' and o['x']==0)
        farmer.update(x=guard['x'],z=guard['z']+1,last_attack=0)
        p.x,p.z=guard['x']+2,guard['z']+1
        hp=guard['hp'];g.last_tick=now+12;farm_system.advance(g,.05,now+12)
        assert guard['hp']==hp-14
        hp=farmer['hp'];guard['last_attack']=0;g.advance_enemies(.05,now+14);assert farmer['hp']<hp
        # Living soldiers heal at their own camp and fountains, capped by max HP.
        p.x,p.z=g.world['teams']['red']['spawn']
        farmer.update(x=p.x,z=p.z,hp=40)
        farm_system.advance(g,.05,now+15)
        assert farmer['hp']>40 and farmer['heal']==24
        farmer.update(x=p.x,z=p.z,hp=farmer['max_hp']-.1)
        farm_system.advance(g,.05,now+16)
        assert farmer['hp']==farmer['max_hp']
        pool=g.pools[0];p.x,p.z=pool['x'],pool['z']
        farmer.update(x=p.x,z=p.z,hp=40)
        farm_system.advance(g,.05,now+17)
        assert farmer['hp']>40 and farmer['heal']==pool['power']
        crystal=next(o for o in g.objects if o['kind']=='crystal' and o['team']=='red')
        crystal['hp']=0;farmer.update(x=p.x,z=p.z,hp=40)
        farm_system.advance(g,.05,now+18)
        assert farmer['hp']==40 and farmer['heal']==0
        crystal['hp']=500
        # Saved growing crops and recruited identity survive restart.
        plot.update(stage=2,grow_until=time.monotonic()+25)
        farm_system.save(g);restored=Game(db)
        soldier=next(o for o in restored.objects if o['id']==farmer['id'])
        crop=next(o for o in restored.objects if o['id']==plot['id'])
        assert soldier['owner']==p.name and soldier['role']=='soldier' and soldier['favor'][p.name]==80
        assert crop['stage']==2 and crop['grow_until']>time.monotonic()+20
        # All-map reset restores crops to new fields while preserving recruited militia.
        machine=next(o for o in g.objects if o.get('global'));g.restore_world(now+20,machine)
        assert plot['stage']==0 and farmer['owner']==p.name and farmer['hp']==120
        snap=g.snapshot();assert all('grow_cd' in o for o in snap['objects'] if o['kind']=='farm')
        print('FARMS PASSED: 20 safe plots/villagers, E stages/cooldown, growth, food/overflow, individual favor, 80-point recruitment, ownership, follow, combat/retaliation, persistence and global reset')


def math_distance(npc,p):
    return ((npc['x']-p.x)**2+(npc['z']-p.z)**2)**.5


if __name__=='__main__':main()
