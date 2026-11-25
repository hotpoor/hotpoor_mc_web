"""Crystal armor uses the existing damage absorption and shared loot rules."""
import time
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
import workbench

def main():
 for cls in (Game,OpenWorldGame):
  g=cls(Database(':memory:'));b=next(o for o in g.objects if o['kind']=='workbench');p=Player('p','护甲测试','red',None,b['x']-1,b['z']);q=Player('q','敌人','blue',None,b['x'],b['z']);g.players={p.id:p,q.id:q}
  p.resources={'iron':4,'crystal':5};workbench.craft(g,p,'crystal_armor');assert not p.armor and p.resources['iron']==4
  p.resources['crystal']=6;weapon=p.weapon;workbench.craft(g,p,'crystal_armor');assert p.armor['durability']==p.armor['max_durability']==180 and p.weapon==weapon and not any(p.resources.values())
  p.resources={'iron':4,'crystal':6};workbench.craft(g,p,'crystal_armor');assert p.resources['crystal']==6
  p.invuln_until=0;g.damage(q,p,50,time.monotonic());assert p.hp==80 and p.armor['durability']==150
  g.drop_armor(p,time.monotonic());assert not p.armor
  loot=next(o for o in g.objects if o['kind']=='armor_pickup' and o['armor_kind']=='crystal');assert loot['durability']==150
  q.x,q.z=loot['x'],loot['z'];g.interact(q,time.monotonic());assert q.armor['durability']==150 and q.armor['max_durability']==180
  q.hp=1000;q.invuln_until=0;g.damage(p,q,300,time.monotonic());assert not q.armor and q.hp==850
 print('CRYSTAL ARMOR PASSED: both modes, 180 durability, 60% absorption, material validation, full armor guard, remaining-durability shared pickup and breakage')
if __name__=='__main__':main()
