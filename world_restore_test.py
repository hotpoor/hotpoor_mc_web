"""Global time machine and companion pursuit regressions."""
import math
import time
from db import Database
from game import Game, Player
from world import collides


def main():
    g = Game(Database(':memory:'))
    p = Player('qa', '测试将军', 'red', None, -24, 2)
    g.players[p.id] = p
    now = time.monotonic()
    machines = [o for o in g.objects if o.get('global')]
    assert len(machines) == 2 and machines[0] in g.targets(p)
    g.cleared_cities.add('yellow')
    dog = next(o for o in g.objects if o.get('animal') == 'dog')
    dog.update(owner=p.name, favor={p.name:100}, hp=0, ready=now+60, hunger=0)
    for o in g.objects:
        if o['kind'] in ('enemy', 'crystal', 'ore', 'weapon_pickup', 'bomb', 'dummy'):
            o.update(hp=0, ready=now+60)
    p.crystal_source = next(o['id'] for o in g.objects if o['kind'] == 'ore')
    g.objects.append(dict(id='temp',kind='dropped_crystal',source=p.crystal_source,x=0,z=0,hp=1,max_hp=1,ready=0,expires=now+50))
    g.damage_object(p, machines[0], 100, now)
    assert all(o['hp'] == o['max_hp'] for o in g.objects if not o.get('global'))
    assert all(o['hp'] == 0 and o['ready'] == now+10 for o in machines)
    assert not p.crystal_source and not any('expires' in o for o in g.objects)
    assert g.cleared_cities == {'yellow'} and dog['owner'] == p.name and dog['hunger'] == 100
    assert any(e['k'] == 'world_reset' for e in g.events)
    # A projectile-triggered reset clears other projectiles safely mid-update.
    machines[0]['hp'] = 1
    p.x,p.z = -24,1.5
    g.shoot(p,0,0,now+11,1);g.shoot(p,0,0,now+12,1)
    for i in range(8): g.advance_arrows(.025,now+12+i*.025)
    assert not g.arrows
    assert all('velocity' in e and 'arrow' in e for e in g.events if e['k']=='arrow_stop')
    # Pets never absorb friendly sword, gun, wave or arrow damage.
    dog.update(x=-24,z=2,hp=100,last_attack=now+100)
    p.x,p.z,p.last_attack,p.weapon=-24,0,0,'sword'
    g.attack(p,0,now+20);g.wave(p,0,now+21,gun=True);g.damage_object(p,dog,100,now+22)
    assert dog['hp']==100
    # Two coincident dogs split into distinct safe positions and side/rear formation.
    second = next(o for o in g.objects if o.get('animal')=='dog' and o is not dog)
    for d in (dog,second): d.update(owner=p.name,x=-24,z=0,hp=100,angry_at='',angry_until=0)
    g.advance_animals(0, now+30)
    assert math.hypot(dog['x']-second['x'],dog['z']-second['z']) > 1.15
    for i in range(40):
        g.last_tick=now+30+i*.05;g.advance_animals(.05,g.last_tick)
    assert math.hypot(dog['x']-second['x'],dog['z']-second['z'])>.75
    assert all(not collides(d['x'],d['z'],g.blocks,radius=.3) for d in (dog,second))
    assert dog['z'] < p.z and second['z'] < p.z
    # A beast keeps its target beyond the old 16-unit home leash and navigates city gates.
    wolf=next(o for o in g.objects if o.get('animal')=='wolf')
    wolf.update(x=5,z=-34,home_x=5,home_z=-26,prey=p.name,last_attack=now+1000)
    p.x,p.z,p.invuln_until = 0,-55,now+1000
    dog['hp']=second['hp']=0
    for i in range(400):
        g.last_tick=now+50+i*.05;g.advance_animals(.05,g.last_tick)
        assert not collides(wolf['x'],wolf['z'],g.blocks,radius=.3)
    assert wolf['z'] < -47 and math.hypot(wolf['x']-p.x,wolf['z']-p.z)<2, (wolf['x'],wolf['z'])
    g.damage(Player('hit','命中者','blue',None,p.x,p.z-1), p, 5, time.monotonic())
    assert next(v for v in g.snapshot()['players'] if v['id']==p.id)['hurt']
    g.damage_object(p, wolf, 1, time.monotonic())
    assert any(e['k']=='object_hit' and e['dmg']==1 for e in g.events)
    print('RESTORE/PETS PASSED: full restoration, shared cooldown, preserved progress/pets, arrows, friendly-fire protection, dog separation/formation, wolf pursuit through outer and inner gates')


if __name__=='__main__': main()
