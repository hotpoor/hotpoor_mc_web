"""Physical material gathering and camp crafting, independent of spelling recipes."""
import json,math,random,time
from world import collides
RESOURCES={
 'wood':{'name':'木材','color':'#a77743','amount':3},
 'stone':{'name':'石料','color':'#929b9c','amount':3},
 'iron':{'name':'铁矿','color':'#d3a98a','amount':2},
 'crystal':{'name':'灵晶','color':'#79dce8','amount':2},
 'obsidian':{'name':'黑曜石','color':'#7045ab','amount':2},
}
RECIPES={
 'crystal_armor':{'name':'灵晶甲','cost':{'iron':4,'crystal':6},'armor_kind':'crystal','durability':180},
 'tiger_spear':{'name':'虎头湛金枪 · 马超','cost':{'wood':3,'iron':6,'crystal':3},'uses':30},
 'silver_spear':{'name':'亮银枪 · 赵云','cost':{'wood':3,'iron':6,'crystal':3},'uses':30},
 'sword':{'name':'宝剑','cost':{'wood':2,'iron':3},'uses':30},
 'bow':{'name':'弓箭','cost':{'wood':4,'stone':2},'uses':30},
 'axe':{'name':'斧子','cost':{'wood':2,'iron':3},'uses':30},
 'mace':{'name':'狼牙棒','cost':{'wood':3,'iron':4},'uses':30},
 'hammer':{'name':'重锤','cost':{'wood':2,'stone':5,'iron':3},'uses':30},
 'beam':{'name':'龟派气功护符','cost':{'obsidian':4,'crystal':2,'iron':1},'uses':-1},
 'rocket':{'name':'火箭筒','cost':{'iron':6,'stone':3,'crystal':2},'uses':30},
 'gun':{'name':'机关枪','cost':{'wood':2,'iron':6},'uses':30},
 'dual':{'name':'双股剑','cost':{'wood':2,'iron':6},'uses':30},
 'spear':{'name':'丈八蛇矛','cost':{'wood':4,'iron':5},'uses':30},
 'blade':{'name':'青龙偃月刀','cost':{'wood':3,'iron':6,'crystal':1},'uses':30},
 'halberd':{'name':'方天画戟','cost':{'wood':3,'iron':6,'obsidian':2},'uses':30},
}
def initialize(game):
 game.world['resources']=RESOURCES;game.world['workbench_recipes']=RECIPES
 try:game.resource_bags=json.loads(game.db.get_setting('workbench_bags_v1') or '{}')
 except (ValueError,TypeError):game.resource_bags={}
 if not isinstance(game.resource_bags,dict):game.resource_bags={}
 rng=random.Random(20261123);placed=[(o['x'],o['z']) for o in game.objects]
 def place(cx,cz,offsets):
  for dx,dz in offsets:
   x,z=cx+dx,cz+dz
   if not collides(x,z,game.blocks) and not game.locked_city_at(x,z) and all(math.hypot(x-a,z-b)>1.1 for a,b in placed):
    placed.append((x,z));return x,z
  return None
 for team,cfg in game.world['teams'].items():
  point=place(*cfg['spawn'],[(2,2),(-2,2),(2,-2),(-2,-2)])
  if point:game.objects.append(dict(id='workbench-'+team,kind='workbench',name='合成工作台',x=point[0],z=point[1],hp=1,max_hp=1,ready=0))
 # Supply every material near each start and several veins per town/city.
 sites=[(*cfg['spawn'],12,'camp-'+team) for team,cfg in game.world['teams'].items()]
 sites += [(v['x'],v['z'],10,v['id']) for v in game.world['villages']]
 sites += [(c['x'],c['z'],c.get('radius',18)+8,c['id']) for c in game.world['cities']]
 for cx,cz,radius,sid in sites:
  for ri,resource in enumerate(RESOURCES):
   offsets=[]
   for trial in range(80):
    angle=ri*math.tau/5+trial*.47;distance=radius+rng.uniform(-2,3)
    offsets.append((round(math.cos(angle)*distance,1),round(math.sin(angle)*distance,1)))
   point=place(cx,cz,offsets)
   if point:game.objects.append(dict(id='resource-'+sid+'-'+resource,kind='resource',resource=resource,
                                    text=RESOURCES[resource]['name'],x=point[0],z=point[1],hp=1,max_hp=1,ready=0))
def load_bag(game,p):
 saved=game.resource_bags.get(p.name,{})
 p.resources={key:min(99,max(0,int(saved.get(key,0)))) for key in RESOURCES} if isinstance(saved,dict) else {}
def save_bag(game,p):
 game.resource_bags[p.name]=dict(p.resources)
 game.db.set_setting('workbench_bags_v1',json.dumps(game.resource_bags,ensure_ascii=False))
def near(game,p):
 return p.jump<1.3 and any(o['kind']=='workbench' and math.hypot(p.x-o['x'],p.z-o['z'])<=3.5 and not game.blocked(p.x,p.z,o['x'],o['z']) for o in game.objects)
def collect(game,p,obj,now):
 resource=obj['resource'];amount=min(99-p.resources.get(resource,0),RESOURCES[resource]['amount'])
 if amount<=0:return
 p.resources[resource]=p.resources.get(resource,0)+amount;obj.update(hp=0,ready=now+20)
 save_bag(game,p);game.emit(dict(k='material_pickup',id=p.id,x=obj['x'],z=obj['z'],text=RESOURCES[resource]['name']+' +'+str(amount)))
def craft(game,p,weapon):
 if not isinstance(weapon,str) or weapon not in RECIPES or not p.alive or p.recall_until or not near(game,p):return
 recipe=RECIPES[weapon]
 if recipe.get('armor_kind'):
  kind=recipe['armor_kind'];cfg=game.world['armor_types'][kind]
  if p.armor.get('kind')==kind and p.armor.get('durability',0)>=cfg['max_durability']:return
  if any(p.resources.get(k,0)<v for k,v in recipe['cost'].items()):return
  for key,amount in recipe['cost'].items():p.resources[key]-=amount
  game.drop_armor(p,time.monotonic())
  p.armor={**cfg,'kind':kind,'durability':cfg['max_durability']}
  save_bag(game,p);game.emit(dict(k='workbench_crafted',id=p.id,text='已合成并穿戴灵晶甲，耐久180，减伤60%。'));return
 old=p.weapons.get(weapon,0);uses=recipe['uses']
 if old==-1 or uses!=-1 and old>=uses:return
 if any(p.resources.get(k,0)<v for k,v in recipe['cost'].items()):return
 for key,amount in recipe['cost'].items():p.resources[key]-=amount
 p.weapons[weapon]=uses;p.weapon=weapon;p.draw_started=None
 save_bag(game,p);game.emit(dict(k='workbench_crafted',id=p.id,text='已合成'+recipe['name']+'，已装备，可用数字键切换。'))
