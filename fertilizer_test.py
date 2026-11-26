import json,time
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
import farm_system
class WS:
 def write_message(self,_):pass
for cls in (Game,OpenWorldGame):
 db=Database(':memory:');g=cls(db);plot=next(o for o in g.objects if o['kind']=='farm');ws=WS();p=Player('p','施肥','red',ws,plot['x'],plot['z']);g.players[p.id]=p;g.sockets[ws]=p.id;p.poop=8;now=time.monotonic();plot.update(stage=2,grow_until=now+30)
 g.handle(ws,json.dumps({'t':'feed_poop'}));assert p.poop==7 and abs(plot['grow_until']-(now+25))<.01
 g.handle(ws,json.dumps({'t':'feed_poop'}));assert p.poop==7
 p.last_feed=0;plot['grow_until']=time.monotonic()+3;g.handle(ws,json.dumps({'t':'feed_poop'}));assert p.poop==6 and plot['stage']==3
 p.last_feed=0;g.handle(ws,json.dumps({'t':'feed_poop'}));assert p.poop==6
 for stage in (0,1):plot['stage']=stage;assert farm_system.fertilize(g,p,time.monotonic());assert p.poop==6
 plot.update(stage=2,grow_until=time.monotonic()+30);p.poop=0;farm_system.fertilize(g,p,time.monotonic());assert p.poop==0
 p.poop=2;p.x+=100;deadline=plot['grow_until'];assert not farm_system.fertilize(g,p,time.monotonic());assert plot['grow_until']==deadline
 p.x=plot['x'];p.alive=False;farm_system.fertilize(g,p,time.monotonic());assert p.poop==2
 assert json.loads(g.db.get_setting('militia_farms_v1'))[plot['id']]['stage']==3
print('FERTILIZER PASSED: both modes, real R message, 5-second reduction, cooldown, immediate maturity, no waste, distance/death validation, persisted state')
