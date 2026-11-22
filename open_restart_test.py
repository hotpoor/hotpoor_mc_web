"""Full open-world restart, stale-confirm protection and mode-isolated persistence."""
import json,time,tempfile
from pathlib import Path
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
import farm_system,animal_system
class WS:
 def __init__(self):self.messages=[]
 def write_message(self,payload):self.messages.append(json.loads(payload))
def main():
 with tempfile.TemporaryDirectory() as d:
  db=Database(str(Path(d)/'reset.db'))
  legacy={'conquest_v1':'legacy-progress','militia_farms_v1':'{}','dog_companions_v1':'{}','craft_modes':'text'}
  for key,value in legacy.items():db.set_setting(key,value)
  g=OpenWorldGame(db);a,b=WS(),WS();p=Player('p','红主公','red',a,0,0,skin='alex',score=1234,kills=7);q=Player('q','蓝主公','blue',b,10,10,skin='lu-bu')
  g.players={p.id:p,q.id:q};g.sockets={a:p.id,b:q.id}
  city=g.world['cities'][0];g.city_owners[city['id']]='red';general=next(o for o in g.objects if o.get('is_general'))
  g.general_owners[general['id']]={'owner':p.name,'team':'red'};general.update(kind='villager',role='soldier',owner=p.name,team='red',favor={p.name:100},guard=False)
  soldier=next(o for o in g.objects if o['kind']=='villager' and not o.get('is_general'));soldier.update(role='soldier',owner=p.name,team='red',favor={p.name:100})
  farm=next(o for o in g.objects if o['kind']=='farm');farm.update(stage=2,grow_until=time.monotonic()+20)
  g.db.set_setting('dog_companions_v1',json.dumps({'saved-dog':{'owner':p.name,'favor':{p.name:100},'hunger':70}}))
  farm_system.save(g);g._save_conquest()
  old=g.snapshot();stream={'objects':{},'initialized':False};g.stream_state(old,p,stream);g.object_streams[a]=stream
  g.team_score['red']=200;p.session_score=200;p.hp=10;p.crystal_source='fake';p.recall_until=time.monotonic()+3;p.draw_started=time.monotonic();p.syllables=['fake'];p.weapons={'halberd':40}
  q.alive=False;q.respawn_at=time.monotonic()+5;g.arrows[1]={'owner':p.id};g._marches[p.id]={'city':city['id']}
  g.objects.append({'id':'temporary','kind':'weapon_pickup','weapon':'sword','x':0,'z':0,'hp':1,'max_hp':1,'ready':0,'expires':time.monotonic()+180})
  generation=g.generation
  for packet in ({'t':'open_restart'},{'t':'open_restart','confirmed':True,'generation':generation+1},{'t':'open_restart','confirmed':True,'generation':True}):
   g.handle(a,json.dumps(packet));assert g.generation==generation and g.city_owners[city['id']]=='red'
  packet={'t':'open_restart','confirmed':True,'generation':generation};g.handle(a,json.dumps(packet))
  assert g.generation==generation+1 and all(g.city_owners[c['id']]==c['faction'] for c in g.world['cities']) and not g.general_owners
  generals=[o for o in g.objects if o.get('is_general')];assert len(generals)==72 and all(o['kind']=='enemy' and o['hp']==o['max_hp'] and not o.get('owner') for o in generals)
  assert not g.arrows and not g._marches and g.team_score=={'red':0,'blue':0} and not any(o['id']=='temporary' for o in g.objects)
  assert all(o['role']=='farmer' and not o['owner'] for o in g.objects if o['kind']=='villager')
  assert all(not o['owner'] and not o['favor'] for o in g.objects if o['kind']=='animal' and o['animal']=='dog')
  assert all(o['stage']==0 for o in g.objects if o['kind']=='farm')
  for actor in (p,q):
   assert actor.alive and actor.hp==100 and (actor.x,actor.z)==tuple(g.world['teams'][actor.team]['spawn'])
   assert actor.weapons=={'sword':50,'bow':50,'axe':30} and actor.armor['durability']==80 and not actor.crystal_source and not actor.recall_until and actor.draw_started is None and not actor.syllables
  assert p.score==1234 and p.kills==7 and p.skin=='alex' and q.skin=='lu-bu' and p.session_score==0
  assert not stream['initialized'] and stream['objects']=={}
  state=g.snapshot();assert [e['k'] for e in state['events']]==['open_restarted'];assert not g.stream_state(state,p,stream)['object_delta']
  g.handle(a,json.dumps(packet));assert g.generation==generation+1
  restored=OpenWorldGame(db);assert restored.generation==g.generation and restored.city_owners==g.city_owners and not restored.general_owners
  assert all(o['kind']=='enemy' for o in restored.objects if o.get('is_general'))
  assert all(db.get_setting(k)==v for k,v in legacy.items()) and db.get_player(p.name)['score']==1234
  campaign=Game(db);campaign.handle(a,json.dumps({'t':'open_restart','confirmed':True,'generation':0}));assert campaign.world.get('mode')!='open'
  print('OPEN RESTART PASSED: 24 initial cities, 72 restored generals, army/dog/farm reset, both players revived, loadouts reset, scores/skins preserved, streams reset, persistent, isolated, stale confirms rejected')
if __name__=='__main__':main()
