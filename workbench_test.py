"""Material gathering, shared nodes, physical recipes and infinite talisman durability."""
import json,time,tempfile
from pathlib import Path
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
from world import collides
import workbench
class WS:
 def write_message(self,_):pass

def main():
 with tempfile.TemporaryDirectory() as directory:
  for cls in (Game,OpenWorldGame):
   db=Database(str(Path(directory)/(cls.__name__+'.db')));g=cls(db);ws=WS();now=time.monotonic()
   bench=next(o for o in g.objects if o['kind']=='workbench');p=Player('p','合成甲','red',ws,bench['x']-1,bench['z']);q=Player('q','合成乙','blue',None,p.x,p.z)
   g.players={p.id:p,q.id:q};g.sockets={ws:p.id}
   assert len([o for o in g.objects if o['kind']=='workbench'])==2
   nodes=[o for o in g.objects if o['kind']=='resource'];assert len(nodes)>=100 and {o['resource'] for o in nodes}==set(workbench.RESOURCES)
   assert all(not collides(o['x'],o['z'],g.blocks) for o in nodes+[bench])
   g.interact(p,now);assert any(e['k']=='workbench_open' for e in g.events)
   # Shared E pick-up, with no second-player duplication before the 20-second respawn.
   node=next(o for o in nodes if o['resource']=='obsidian');p.x,p.z=node['x'],node['z'];q.x,q.z=p.x,p.z
   g.interact(p,now+1);assert p.resources['obsidian']==2 and node['hp']==0 and node['ready']==now+21
   g.interact(q,now+1);assert not q.resources
   node['ready']=time.monotonic()-1;g.last_tick=time.monotonic();g.tick();assert node['hp']==1
   # Cannot craft remotely, with missing resources, while dead, or during a channel.
   p.weapons={};p.resources={'obsidian':4,'crystal':2,'iron':1};g.handle(ws,json.dumps({'t':'workbench_craft','weapon':'beam'}));assert not p.weapons
   p.x,p.z=bench['x']-1,bench['z'];p.resources={};g.handle(ws,json.dumps({'t':'workbench_craft','weapon':'beam'}));assert not p.weapons
   p.resources={'obsidian':4,'crystal':2,'iron':1};p.alive=False;workbench.craft(g,p,'beam');assert not p.weapons;p.alive=True
   p.recall_until=now+3;workbench.craft(g,p,'beam');assert not p.weapons;p.recall_until=0
   g.handle(ws,json.dumps({'t':'workbench_craft','weapon':'beam'}));assert p.weapons['beam']==-1 and p.weapon=='beam' and not any(p.resources.values())
   p.draw_started=time.monotonic()-1.1;p.beam_ready=0;g.handle(ws,json.dumps({'t':'attack','yaw':0}));assert p.weapons['beam']==-1 and p.beam_ready>time.monotonic()+4
   # Infinite talisman can be dropped and picked up, and is never downgraded by finite copies.
   finite={'weapon':'beam','uses':10};assert not g.weapon_upgrade(p,finite)
   g.drop_weapon(p,now+2);drop=next(o for o in g.objects if o['kind']=='weapon_pickup' and o.get('uses')==-1)
   assert 'beam' not in p.weapons;g.interact(p,now+3);assert p.weapons['beam']==-1 and drop not in g.objects
   p.resources={'wood':2,'iron':3};workbench.craft(g,p,'sword');assert p.weapon=='sword' and p.weapons['sword']==30 and not any(p.resources.values())
   p.resources={'wood':8};workbench.save_bag(g,p);restored=cls(db);copy=Player('c',p.name,'red',None,0,0);workbench.load_bag(restored,copy);assert copy.resources['wood']==8
   # Ordinary restoration refreshes nodes but keeps material inventory.
   machine=next(o for o in g.objects if o.get('global'));node['hp']=0;g.restore_world(now+4,machine);assert node['hp']==1 and p.resources['wood']==8
   if isinstance(g,OpenWorldGame):
    g.restart_world(p,now+5);assert not p.resources and not g.resource_bags
    restored=cls(db);workbench.load_bag(restored,copy);assert not any(copy.resources.values())
 print('WORKBENCH PASSED: both modes, safe start tables, five materials, shared E pickup/respawn, atomic recipes, validation, persistent bags, infinite charged talisman/CD/drop/pickup, restoration and restart')
if __name__=='__main__':main()
