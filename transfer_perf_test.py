"""Team channel transfer and spatial collision parity."""
import json,math,random,time
from db import Database
from game import Game,Player
from world import collides,BlockList
class WS:
 def write_message(self,_):pass

def main():
 g=Game(Database(':memory:'));ws=WS();p=Player('p','甲','red',ws,-24,0);q=Player('q','乙','red',None,0,-43);foe=Player('f','敌','blue',None,24,0)
 g.players={p.id:p,q.id:q,foe.id:foe};g.sockets={ws:p.id};now=time.monotonic()
 for obj in (p,q,foe):obj.invuln_until=now+1000
 for target in ('p','f','missing'):
  g.handle(ws,json.dumps({'t':'team_transfer','target':target}));assert not p.recall_until
 g.handle(ws,json.dumps({'t':'team_transfer','target':'q'}));assert p.recall_until>now and p.transfer_target=='q'
 g.handle(ws,json.dumps({'t':'input','mx':1}));assert not p.recall_until
 p.mx=0;g.handle(ws,json.dumps({'t':'team_transfer','target':'q'}));g.damage(foe,p,1,time.monotonic());assert not p.recall_until
 p.x,p.z=-24,0;g.handle(ws,json.dumps({'t':'team_transfer','target':'q'}));p.recall_until=time.monotonic()-1
 g.last_tick=time.monotonic();g.tick()
 assert .85<math.hypot(p.x-q.x,p.z-q.z)<4 and not collides(p.x,p.z,g.blocks)
 assert p.transfer_ready>time.monotonic()+28 and p.recall_ready==0
 g.handle(ws,json.dumps({'t':'team_transfer','target':'q'}));assert not p.recall_until
 p.transfer_ready=0;g.handle(ws,json.dumps({'t':'team_transfer','target':'q'}));q.alive=False;q.respawn_at=time.monotonic()+100;p.recall_until=time.monotonic()-1;position=(p.x,p.z);g.tick();assert (p.x,p.z)==position and p.transfer_ready==0
 q.alive=True;p.recall_until=0;p.transfer_target='';g.handle(ws,json.dumps({'t':'recall'}));p.recall_until=time.monotonic()-1;g.tick();assert (p.x,p.z)==(-24,0) and p.recall_ready>time.monotonic()+28
 rng=random.Random(54);plain=list(g.blocks)
 for _ in range(2000):
  x,z=rng.uniform(-140,140),rng.uniform(-140,140);feet=rng.choice((0,1,2,4));radius=rng.choice((.3,.36,.5))
  assert collides(x,z,g.blocks,radius,feet)==collides(x,z,plain,radius,feet)
 b=BlockList();wall={'x':0,'z':0,'h':3};assert not collides(0,0,b);b.append(wall);assert collides(0,0,b);b.remove(wall);assert not collides(0,0,b)
 b.extend([wall]);assert collides(0,0,b);b[:]=[];assert not collides(0,0,b);b+=[wall];assert collides(0,0,b);b.clear();assert not collides(0,0,b)
 print('TRANSFER/INDEX PASSED: team validation, channel/interruption, safe arrival, cooldown, dead target, independent recall, 2000 spatial parity cases and mutation invalidation')
if __name__=='__main__':main()
