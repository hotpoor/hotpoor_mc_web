"""Large army smoke/benchmark: keep every soldier, reconstruct object deltas."""
import json,statistics,time
from db import Database
from game import Player
from conquest import OpenWorldGame

def main():
 g=OpenWorldGame(Database(':memory:'));p=Player('p','军阵测试','red',None,*g.world['teams']['red']['spawn']);g.players[p.id]=p
 template=next(o for o in g.objects if o['kind']=='villager')
 for i in range(120):g.objects.append({**template,'id':'stress-'+str(i),'name':'军士'+str(i),'role':'soldier','owner':p.name,'team':p.team,'x':p.x+(i%12-5)*1.3,'z':p.z+(i//12-5)*1.3,'favor':{p.name:100}})
 stream={'objects':{},'initialized':False};client={};times=[];full_sizes=[];delta_sizes=[]
 for i in range(30):
  g.last_tick=time.monotonic()-.05;start=time.perf_counter();g.tick();times.append((time.perf_counter()-start)*1000)
  state=g.snapshot();packet=g.stream_state(state,p,stream)
  if not packet['object_delta']:client.clear()
  for oid in packet['objects_removed']:client.pop(oid,None)
  for obj in packet['objects']:client[obj['id']]=dict(obj)
  for patch in packet['object_patches']:client[patch['id']].update(patch)
  assert client==stream['objects']
  full_sizes.append(len(json.dumps(state,ensure_ascii=False).encode()));delta_sizes.append(len(json.dumps(packet,ensure_ascii=False).encode()))
 soldiers=[o for o in g.objects if o['id'].startswith('stress-')]
 assert len(soldiers)==120 and all(o['hp']>0 for o in soldiers)
 assert statistics.median(delta_sizes[2:])<statistics.median(full_sizes)*.6
 print('120 SOLDIERS PASSED; tick median %.2fms; full %.0fB -> delta %.0fB (before compression)'%(statistics.median(times),statistics.median(full_sizes),statistics.median(delta_sizes[2:])))
if __name__=='__main__':main()
