"""A China-geography schematic for a free-conquest Three Kingdoms world.

City spacing is adjusted for playable streets and large fortifications. This is a
historical-fiction game board, not a surveyed boundary or a single-year atlas.
"""
import copy
import math
from campaign import NAME_SKINS
from world import BlockList, RULES

HALF = 2500
SCALE = 65
RADIUS = 36
FACTIONS = {
    'cao': {'name':'曹氏势力','leader':'曹操','color':'#537ebd'},
    'liu': {'name':'刘备势力','leader':'刘备','color':'#57965d'},
    'sun': {'name':'孙氏势力','leader':'孙权','color':'#b95745'},
    'yuan': {'name':'袁绍势力','leader':'袁绍','color':'#9376b1'},
    'dong': {'name':'董卓势力','leader':'董卓','color':'#7c4f57'},
    'biao': {'name':'荆州刘表','leader':'刘表','color':'#4f9190'},
    'zhang': {'name':'益州刘璋','leader':'刘璋','color':'#99904b'},
    'frontier': {'name':'边郡群雄','leader':'边郡诸侯','color':'#8a8a7b'},
}
# id, city, longitude, latitude, original holder, three unique named officers.
CITY_DATA = [
 ('changan','长安',108.94,34.26,'dong', [('董卓','hammer'),('华雄','blade'),('李儒','beam')]),
 ('luoyang','洛阳',112.45,34.62,'dong',[('吕布','halberd'),('貂蝉','dual'),('陈宫','sword')]),
 ('xuchang','许昌',113.85,34.03,'cao',[('曹操','sword'),('曹丕','sword'),('荀彧','beam')]),
 ('chenliu','陈留',114.35,34.78,'cao',[('夏侯惇','axe'),('夏侯渊','bow'),('典韦','dual')]),
 ('puyang','濮阳',115.03,35.76,'cao',[('张辽','halberd'),('张郃','spear'),('于禁','spear')]),
 ('jinyang','晋阳',112.55,37.87,'cao',[('徐晃','axe'),('乐进','sword'),('李典','spear')]),
 ('pingyuan','平原',116.44,37.17,'liu',[('刘备','dual'),('关平','blade'),('简雍','sword')]),
 ('xuzhou','徐州',117.28,34.20,'liu',[('张飞','spear'),('刘封','spear'),('孙乾','sword')]),
 ('yongan','永安',109.46,31.01,'liu',[('赵云','silver_spear'),('诸葛亮','beam'),('庞统','beam')]),
 ('jianye','建业',118.78,32.06,'sun',[('孙权','sword'),('鲁肃','sword'),('陆逊','sword')]),
 ('chaisang','柴桑',115.98,29.71,'sun',[('周瑜','sword'),('太史慈','bow'),('黄盖','mace')]),
 ('kuaiji','会稽',120.58,30.00,'sun',[('甘宁','dual'),('周泰','blade'),('程普','spear')]),
 ('ye','邺',114.62,36.34,'yuan',[('袁绍','sword'),('田丰','beam'),('沮授','sword')]),
 ('nanpi','南皮',116.70,38.04,'yuan',[('颜良','blade'),('高览','spear'),('审配','sword')]),
 ('beihai','北海',119.10,36.71,'yuan',[('文丑','mace'),('孔融','sword'),('管亥','axe')]),
 ('xiangyang','襄阳',112.14,32.04,'biao',[('刘表','sword'),('蔡瑁','sword'),('蒯良','beam')]),
 ('jiangling','江陵',112.24,30.34,'biao',[('关羽','blade'),('关兴','blade'),('周仓','mace')]),
 ('jiangxia','江夏',114.30,30.60,'biao',[('黄忠','bow'),('魏延','blade'),('韩玄','sword')]),
 ('chengdu','成都',104.07,30.67,'zhang',[('刘璋','sword'),('法正','beam'),('张松','sword')]),
 ('zitong','梓潼',105.16,31.64,'zhang',[('张任','spear'),('冷苞','spear'),('邓贤','sword')]),
 ('jiangzhou','江州',106.55,29.56,'zhang',[('严颜','blade'),('吴懿','sword'),('李严','spear')]),
 ('hanzhong','汉中',107.02,33.07,'frontier',[('张鲁','beam'),('庞德','mace'),('杨松','sword')]),
 ('wuwei','武威',102.64,37.93,'frontier',[('马超','tiger_spear'),('马岱','spear'),('马腾','blade')]),
 ('xiangping','襄平',123.17,41.27,'frontier',[('公孙度','spear'),('公孙瓒','spear'),('田豫','bow')]),
]


def project(lon, lat):
    return [(lon - 108) * SCALE, (35 - lat) * SCALE]


def _cities():
    cities=[]
    for index,(cid,name,lon,lat,faction,generals) in enumerate(CITY_DATA):
        x,z=project(lon,lat)
        cities.append({'id':cid,'name':name,'x':x,'z':z,'radius':RADIUS,'faction':faction,
                       'gates':['north','south','east','west'],'chapter':index+1,
                       'generals':[{'name':n,'skin':NAME_SKINS.get(n,'ranger'),'weapon':w,'recruitable':True} for n,w in generals],
                       'bosses':[n for n,_ in generals],'allies':[],'loot':[w for _,w in generals]})
    # Deliberately spread the densely populated Central Plain to fit walkable large cities.
    for _ in range(100):
        changed=False
        for i,a in enumerate(cities):
            for b in cities[i+1:]:
                dx,dz=b['x']-a['x'],b['z']-a['z'];distance=math.hypot(dx,dz)
                if distance<116:
                    dx,dz=(dx or .5),(dz or .5);distance=math.hypot(dx,dz)
                    push=(116-distance)*.51
                    a['x']-=dx/distance*push;a['z']-=dz/distance*push
                    b['x']+=dx/distance*push;b['z']+=dz/distance*push;changed=True
        if not changed:break
    for c in cities:
        c['x'],c['z']=round(c['x']),round(c['z'])
        x,z=c['x'],c['z']
        c['capture']=c['yamen']=[x,z-15]
        c['spawn']=c['safe_spawn']=c['travel_spawn']=[x+4,z+52]
        c['guard_spawns']=[[x+dx,z+dz] for dx,dz in [(-5,25),(5,25),(0,19),(-18,0),(18,0),(-5,-7),(5,-7),(0,6)]]
        c['general_spawns']=[[x+dx,z+dz] for dx,dz in [(-5,-15),(0,-18),(5,-15)]]
        c['markets']=[{'x':x+24,'z':z+dz} for dz in (-5,5)]
        c['houses']=[{'x':x+dx,'z':z+dz,'w':5,'d':5} for dx in (-25,-13,13,25) for dz in (-25,-12,12,25)]
        c['story']='群雄割据 · 自由攻城，击败守军后进入府衙占领。'
    return cities


def _city_blocks(city):
    x,z=city['x'],city['z'];items={}
    def put(dx,dz,h,kind='brick'):
        key=(x+dx,z+dz)
        if h>items.get(key,{}).get('h',0):items[key]={'x':x+dx,'z':z+dz,'h':h,'type':kind}
    for offset in range(-36,37):
        for dx,dz in ((offset,-36),(offset,36),(-36,offset),(36,offset)):
            if (abs(dx)==36 and abs(dz)<=4) or (abs(dz)==36 and abs(dx)<=4):continue
            put(dx,dz,6)
    # Four solid corner towers, independent simple collision proxies.
    for cx in (-35,35):
        for cz in (-35,35):
            for dx in range(-2,3):
                for dz in range(-2,3):put(cx+dx,cz+dz,9,'stone')
    # South gate barbican: offset outer gate makes the approach a defensible courtyard.
    for dz in range(36,49):
        put(-10,dz,5);put(10,dz,5)
    for dx in range(-10,11):
        if not 1<=dx<=7:put(dx,48,5)
    # Gatehouse pillars stop players clipping through the towers but leave a broad central passage.
    for cx,cz in ((-6,-36),(6,-36),(-6,36),(6,36),(-36,-6),(-36,6),(36,-6),(36,6)):
        for dx in (-1,0,1):
            for dz in (-1,0,1):put(cx+dx,cz+dz,8,'stone')
    # Yamen outer court with five-block front entrance, office walls and raised rear dais.
    for dz in range(-33,-10):put(-11,dz,3,'stone');put(11,dz,3,'stone')
    for dx in range(-11,12):
        put(dx,-33,3,'stone')
        if abs(dx)>3:put(dx,-11,3,'stone')
    for dx in range(-9,10):
        put(dx,-32,4,'bark')
        if abs(dx)>2:put(dx,-22,4,'bark')
    for dz in range(-32,-21):put(-9,dz,4,'bark');put(9,dz,4,'bark')
    for dx in range(-4,5):put(dx,-30,1,'stone')
    # Walk-in homes with an actual open doorway, and streets between every row.
    for home in city['houses']:
        hx,hz=home['x']-x,home['z']-z
        for dx in range(-2,3):
            for dz in range(-2,3):
                if abs(dx)!=2 and abs(dz)!=2:continue
                if dz==2 and dx==0:continue
                put(hx+dx,hz+dz,3,'bark')
    for market in city['markets']:
        for dx in (-1,0,1):put(market['x']-x+dx,market['z']-z,1,'bark')
    return list(items.values())


def _roads(cities):
    connected={cities[0]['id']};roads=[]
    while len(connected)<len(cities):
        _,a,b=min(((math.hypot(a['x']-b['x'],a['z']-b['z']),a,b) for a in cities if a['id'] in connected for b in cities if b['id'] not in connected), key=lambda edge: edge[0])
        p,q=a['safe_spawn'],b['safe_spawn'];middle=(p[1]+q[1])/2
        roads.append({'id':a['id']+'-'+b['id'],'from':a['id'],'to':b['id'],'width':7,
                      'points':[p,[p[0],middle],[q[0],middle],q]})
        connected.add(b['id'])
    return roads


def build_open_world():
    cities=_cities();luoyang=next(c for c in cities if c['id']=='luoyang')
    camps={}
    for team,offset,name,color in [('red',-20,'赤焰义军营','#ef4f4f'),('blue',20,'苍蓝义军营','#4c86f0')]:
        x,z=luoyang['x']+offset,luoyang['z']+74
        camps[team]={'key':team,'name':name,'short':name[:2],'spawn':[x,z],
                     'zone':[x-8,x+8,z-7,z+7],'color':color,'accent':'#ffe0ac'}
    village_names=['关中驿','河洛镇','兖州村','徐州驿','江东镇','荆州村','益州驿','凉州村']
    anchors=[cities[i] for i in (0,1,3,7,9,15,18,22)]
    villages=[]
    for i,c in enumerate(anchors):
        candidates=[]
        for distance in (95,120,150,180):
            for step in range(16):
                angle=step*math.pi/8
                vx,vz=round(c['x']+math.cos(angle)*distance),round(c['z']+math.sin(angle)*distance)
                if (all(math.hypot(vx-other['x'],vz-other['z'])>80 for other in cities)
                    and all(math.hypot(vx-v['x'],vz-v['z'])>40 for v in villages)
                    and all(math.hypot(vx-t['spawn'][0],vz-t['spawn'][1])>28 for t in camps.values())):
                    candidates.append((vx,vz))
            if candidates:break
        vx,vz=candidates[0]
        villages.append({'id':'open-village-'+c['id'],'name':village_names[i], 'x':vx,'z':vz,'axis':'z','city':c['id']})
    pools=[{'x':c['x']+18,'z':c['z'],'r':2.2,'power':18,'name':c['name']+'城井','city':c['id']} for c in cities]
    pools += [{'x':v['x'],'z':v['z'],'r':2,'power':16,'name':v['name']+'泉'} for v in villages]
    pools += [{'x':t['spawn'][0],'z':t['spawn'][1]+3,'r':2,'power':18,'name':t['short']+'营泉'} for t in camps.values()]
    blocks=[b for c in cities for b in _city_blocks(c)]
    # Small village cottages keep their central well and agriculture shoulders open.
    for v in villages:
        for side in (-1,1):
            for dx in (-1,0,1):
                for dz in (-1,0,1):
                    blocks.append({'x':v['x']+side*6+dx,'z':v['z']+4+dz,'h':2 if abs(dx)+abs(dz) else 3,'type':'bark'})
    outline=[(73,39),(80,42),(87,49),(97,49),(110,44),(120,53),(128,49),(135,48),(131,43),(124,39),
             (122,35),(122,31),(121,28),(118,24),(113,22),(110,20),(108,21),(106,22),(100,22),(97,24),
             (95,28),(90,28),(86,28),(82,31),(79,35),(73,39)]
    rivers=[{'name':'黄河','color':'#bbab68','points':[project(*p) for p in [(98,35),(102,36),(104,38),(107,39),(111,39),(111,35),(114,35),(117,37),(119,37)]]},
            {'name':'长江','color':'#478f9e','points':[project(*p) for p in [(93,33),(99,29),(103,27),(105,29),(108,30),(112,30),(114,30),(117,31),(121,32)]]}]
    return {'mode':'open','name':'三国开放世界 · 群雄割据','size':HALF*2,'half':HALF,
            'teams':camps,'pools':pools,'blocks':BlockList(blocks,half=HALF,moats=[]),
            'rules':copy.deepcopy(RULES),'cities':cities,'villages':villages,'moats':[],
            'routes':[],'roads':_roads(cities),'factions':copy.deepcopy(FACTIONS),
            'china_outline':[project(*p) for p in outline],'rivers':rivers,
            'map_bounds':[-2350,1850,-1250,1180],
            'settlement_goal':len(cities)}
