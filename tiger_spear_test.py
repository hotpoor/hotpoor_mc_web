"""Ma Chao's 65-damage weapon across combat, recipes and shared loot."""
import json,time
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
import workbench,farm_system
class WS:
 def write_message(self,_):pass

def main():
 g=Game(Database(':memory:'));ws=WS();p=Player('p','虎头枪测试','red',ws,-24,0);q=Player('q','对手','blue',None,-24,1.6);g.players={p.id:p,q.id:q};g.sockets={ws:p.id}
 p.weapons={'tiger_spear':5};p.weapon='tiger_spear';q.armor={};q.invuln_until=0
 g.handle(ws,json.dumps({'t':'attack','yaw':0}));assert q.hp==35 and p.weapons['tiger_spear']==4
 g.handle(ws,json.dumps({'t':'attack','yaw':0}));assert q.hp==35 and p.weapons['tiger_spear']==4
 p.last_attack-=2;g.handle(ws,json.dumps({'t':'attack','yaw':0}));assert not q.alive
 dummy=next(o for o in g.objects if o['kind']=='dummy');p.x,p.z=dummy['x'],dummy['z']-1.6;p.last_attack=0;g.attack(p,0,time.monotonic());assert dummy['hp']==135
 # The same ID supports E pickups, all three spelling forms and the workbench.
 source=next(o for o in g.objects if o['kind']=='weapon_pickup' and o['weapon']=='tiger_spear');p.weapons={};p.x,p.z=source['x'],source['z'];g.interact(p,time.monotonic());assert p.weapon=='tiger_spear'
 forge=next(o for o in g.objects if o['kind']=='forge');p.x,p.z=forge['x'],forge['z']
 for mode in ('text','whole','split'):
  p.weapons={};p.syllables=list(g.world['recipes']['tiger_spear'][mode]);g.craft(p,'tiger_spear',mode);assert p.weapon=='tiger_spear' and not p.syllables
 bench=next(o for o in g.objects if o['kind']=='workbench');p.x,p.z=bench['x']-1,bench['z'];p.weapons={};p.resources={'wood':3,'iron':6,'crystal':3}
 workbench.craft(g,p,'tiger_spear');assert p.weapons['tiger_spear']==30 and not any(p.resources.values())
 p.weapons['tiger_spear']=17;g.drop_weapon(p,time.monotonic());q.alive=True;q.x,q.z=p.x,p.z;g.interact(q,time.monotonic());assert q.weapons['tiger_spear']==17
 assert all(o['weapon']=='tiger_spear' for o in g.objects if o.get('name')=='马超')
 # Ma Chao drops the silver spear and retains it after recruitment.
 world=OpenWorldGame(Database(':memory:'));zhao=next(o for o in world.objects if o.get('is_general') and o['name']=='马超')
 assert zhao['weapon']=='tiger_spear' and zhao['attack_damage']==65
 p2=Player('r','马超主公','red',None,zhao['x'],zhao['z']);world.players[p2.id]=p2
 p2.armor={};p2.invuln_until=0;world.advance_enemies(0,time.monotonic());assert p2.hp==35
 soldier=next(o for o in world.objects if o['kind']=='villager');soldier.update(role='soldier',team='red',owner=p2.name,x=zhao['x'],z=zhao['z'],hp=120);zhao['last_attack']=0
 world.advance_enemies(0,time.monotonic());assert soldier['hp']==55
 soldier['hp']=0
 world.damage_object(p2,zhao,10000,time.monotonic());assert any(o['kind']=='weapon_pickup' and o['weapon']=='tiger_spear' and o.get('uses')==40 for o in world.objects)
 world.city_owners[zhao['city']]='red';world._sync_city_objects();world.interact(p2,time.monotonic());assert zhao['kind']=='villager' and zhao['weapon']=='tiger_spear' and zhao['attack_damage']==65
 target=Player('enemy','靶','blue',None,zhao['x'],zhao['z']+1);world.players[target.id]=target;zhao['last_attack']=0;farm_system.advance(world,0,time.monotonic()+2);assert target.hp==35
 print('TIGER SPEAR PASSED: 65 raw PvP/dummy damage, cooldown, pickups, 3 spelling recipes, workbench, 17-use shared drop, Ma Chao 40-use drop and recruitment')
if __name__=='__main__':main()
