"""Mid-game allegiance/skins and lossless nearby object streaming."""
import asyncio,json,tempfile,time
from pathlib import Path
from tornado.httpserver import HTTPServer
from tornado.netutil import bind_sockets
from tornado.websocket import websocket_connect
from db import Database
from game import Game,Player
from conquest import OpenWorldGame
from server import make_app
class WS:
 def __init__(self):self.messages=[]
 def write_message(self,message):self.messages.append(json.loads(message) if isinstance(message,str) else message)

def rules():
 with tempfile.TemporaryDirectory() as directory:
  db=Database(str(Path(directory)/'teams.db'))
  for factory in (Game,OpenWorldGame):
   g=factory(db);ws=WS();p=Player('p','主公','red',ws,*g.world['teams']['red']['spawn']);g.players[p.id]=p;g.sockets[ws]=p.id
   npc=next(o for o in g.objects if o['kind']=='villager');npc.update(role='soldier',owner=p.name,team=p.team)
   if isinstance(g,OpenWorldGame):
    general=next(o for o in g.objects if o.get('is_general'));general.update(kind='villager',role='soldier',owner=p.name,team='red',favor={p.name:100})
    g.general_owners[general['id']]={'owner':p.name,'team':'red'}
    owners=dict(g.city_owners);g._marches[p.id]={'city':g.world['cities'][0]['id']}
   now=time.monotonic();p.hp=43;p.weapons={'sword':17};p.weapon='sword';p.rocket_ready=now+20;p.recall_until=now+3;p.draw_started=now;p.slam_pending=True
   ore=next((o for o in g.objects if o['kind']=='ore'),None)
   if ore:ore.update(hp=0,ready=None);p.crystal_source=ore['id']
   g.arrows[1]={'owner':p.id};g.change_team(p,[],now);assert p.team=='red'
   g.handle(ws,json.dumps({'t':'change_team','team':'blue'}))
   assert p.team=='blue' and (p.x,p.z)==tuple(g.world['teams']['blue']['spawn']) and p.hp==43
   assert p.weapons=={'sword':17} and p.rocket_ready==now+20 and not p.recall_until and p.draw_started is None and not p.slam_pending
   assert not p.crystal_source and not g.arrows and npc['team']=='blue'
   if ore:assert any(o['kind']=='dropped_crystal' and o['source']==ore['id'] for o in g.objects)
   if isinstance(g,OpenWorldGame):assert g.general_owners[general['id']]['team']=='blue' and g.city_owners==owners and p.id not in g._marches
   g.change_team(p,'red',now);assert p.team=='blue'
   p.next_team_change=0;p.alive=False;g.change_team(p,'red',now);assert p.team=='blue';p.alive=True
   g.handle(ws,json.dumps({'t':'skin','skin':'alex'}));assert p.skin=='alex'
   stream={'objects':{},'initialized':False};state=g.snapshot();first=g.stream_state(state,p,stream)
   assert not first['object_delta'] and len(first['objects'])>0
   same=g.stream_state(state,p,stream);assert same['object_delta'] and not same['objects'] and not same['object_patches']
   sample=next(o for o in state['objects'] if o['kind']=='crystal');sample['hp']-=1
   changed=g.stream_state(state,p,stream);assert [o['id'] for o in changed['object_patches']]==[sample['id']]
   # Nested maps must not alias old snapshots: feeding/recruitment remains visible.
   local={'id':'nested','kind':'villager','x':p.x,'z':p.z,'favor':{'主公':1}}
   state['objects'].append(local);g.stream_state(state,p,stream);local['favor']['主公']=2
   assert any(o['id']=='nested' for o in g.stream_state(state,p,stream)['object_patches'])
   local['x']+=1000;left=g.stream_state(state,p,stream);assert 'nested' in left['objects_removed']
   local['x']=p.x;assert any(o['id']=='nested' for o in g.stream_state(state,p,stream)['objects'])
   class Pending:
    complete=False
    def done(self):return self.complete
   pending=Pending();stream['pending']=pending;g.object_streams[ws]=stream
   g.emit({'k':'story','text':'slow-frame'});g.last_tick=time.monotonic();g.tick()
   assert any(e.get('text')=='slow-frame' for e in stream['events'])
   pending.complete=True;g.emit({'k':'story','text':'next-frame'});g.tick()
   packet=ws.messages[-1];assert any(e.get('text')=='slow-frame' for e in packet['events']) and any(e.get('text')=='next-frame' for e in packet['events'])
  print('TEAM/DELTA RULES PASSED: HP/items/CD preserved; crystal dropped; army and generals persist allegiance; cities unchanged; validation; skin; full/delta/nested/leave/re-enter')

async def network():
 db=Database(':memory:');g=Game(db);app=make_app(g,db);server=HTTPServer(app);sockets=bind_sockets(0,'127.0.0.1');port=sockets[0].getsockname()[1];server.add_sockets(sockets);g.start()
 ws=await websocket_connect(f'ws://127.0.0.1:{port}/ws?mode=open',compression_options={});ws.write_message(json.dumps({'t':'join','name':'联机换队','team':'red','object_deltas':True}))
 async def receive(test):
  for _ in range(100):
   row=json.loads(await asyncio.wait_for(ws.read_message(),5))
   if test(row):return row
  raise AssertionError('state not received')
 await receive(lambda m:m['t']=='welcome');first=await receive(lambda m:m['t']=='state');second=await receive(lambda m:m['t']=='state')
 assert not first['object_delta'] and second['object_delta'] and len(second['objects'])<len(first['objects'])
 ws.write_message(json.dumps({'t':'change_team','team':'blue'}));row=await receive(lambda m:m['t']=='state' and m['players'][0]['team']=='blue');assert any(e['k']=='team_changed' for e in row['events'])
 ws.write_message(json.dumps({'t':'skin','skin':'alex'}));await receive(lambda m:m['t']=='state' and m['players'][0]['skin']=='alex')
 ws.close();await asyncio.sleep(.05)
 for room in app.settings['games'].values():room._periodic.stop()
 server.stop();await server.close_all_connections();print('REAL WEBSOCKET PASSED: negotiated deltas, team and skin changes synchronized')
if __name__=='__main__':rules();asyncio.run(network())
