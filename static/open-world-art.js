// Large-city voxel kit. Repeated roofs, battlements and street details are
// batched per city so the renderer can cull whole distant settlements.
export function buildOpenWorldArt(renderer, labelSprite, box, THREE) {
  const scene=renderer.scene,world=renderer.world;
  renderer.openCityGroups=new Map();
  renderer.openCityFlags=new Map();
  const unit=new THREE.BoxGeometry(1,1,1);
  const roof=0x473c3c,roofEdge=0x796056,wood=0x69472f,stone=0xa39883,road=0xb9a581;
  function kit(parent){
    const batches=new Map();
    function block(w,h,d,color,x,y,z,rx=0,ry=0,rz=0){
      const key=String(color);if(!batches.has(key))batches.set(key,{color,transforms:[]});
      const matrix=new THREE.Matrix4();matrix.compose(new THREE.Vector3(x,y,z),new THREE.Quaternion().setFromEuler(new THREE.Euler(rx,ry,rz)),new THREE.Vector3(w,h,d));batches.get(key).transforms.push(matrix);
    }
    function finish(){
      const materials=new Map();
      for(const [key,batch] of batches){
        const material=new THREE.MeshLambertMaterial({color:batch.color});materials.set(key,material);
        const mesh=new THREE.InstancedMesh(unit,material,batch.transforms.length);batch.transforms.forEach((m,i)=>mesh.setMatrixAt(i,m));mesh.instanceMatrix.needsUpdate=true;mesh.computeBoundingSphere();parent.add(mesh);
      }
      return materials;
    }
    return {block,finish};
  }
  function steppedRoof(k,x,z,w,d,y,main=roof){
    const layers=Math.max(3,Math.min(5,Math.round(d/3)));
    for(let i=0;i<layers;i++)k.block(w-i*.9,.38,d-i*1.3,main,x,y+i*.36,z);
    k.block(Math.max(1,w-2),.25,.34,roofEdge,x,y+layers*.36,z);
    // Upturned corners and thick eaves read clearly even at a distance.
    for(const sx of [-1,1])for(const sz of [-1,1])k.block(1.1,.18,.25,roofEdge,x+sx*(w/2-.25),y+.18,z+sz*(d/2-.25),0,0,-sx*.25);
  }
  function label(parent,text,x,y,z,w=7,color='#f8df9e'){
    const sprite=labelSprite(text,color,640,110,40);sprite.position.set(x,y,z);sprite.scale.set(w,w*.17,1);sprite.material.depthTest=true;parent.add(sprite);return sprite;
  }
  function freeze(group){
    group.updateMatrixWorld(true);
    group.traverse(part=>{part.updateMatrix();part.matrixAutoUpdate=false;});
  }
  // A national land silhouette and shallow stylized river ribbons provide the
  // geographic setting; they are scenery, while city blocks own collisions.
  if(world.china_outline?.length){
    const shape=new THREE.Shape();world.china_outline.forEach(([x,z],i)=>i?shape.lineTo(x,-z):shape.moveTo(x,-z));shape.closePath();
    const land=new THREE.Mesh(new THREE.ShapeGeometry(shape),new THREE.MeshLambertMaterial({color:0x71915a,transparent:true,opacity:.22,depthWrite:false}));land.rotation.x=-Math.PI/2;land.position.y=.009;scene.add(land);
  }
  for(const river of world.rivers||[]){
    for(let i=1;i<river.points.length;i++){
      const a=river.points[i-1],b=river.points[i],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
      const water=box(7,.03,length,river.color||'#4a8eaa',.015);water.position.set((a[0]+b[0])/2,.015,(a[1]+b[1])/2);water.rotation.y=Math.atan2(b[0]-a[0],b[1]-a[1]);scene.add(water);
    }
  }
  // Roads start outside the barbicans; open fields remain freely traversable.
  const roadGroup=new THREE.Group(),rk=kit(roadGroup);
  for(const route of world.roads||[]){
    for(let i=1;i<route.points.length;i++){
      const a=route.points[i-1],b=route.points[i],length=Math.hypot(b[0]-a[0],b[1]-a[1]);
      if(length<.01)continue;
      rk.block(route.width||7,.045,length,road,(a[0]+b[0])/2,.023,(a[1]+b[1])/2,0,Math.atan2(b[0]-a[0],b[1]-a[1]),0);
    }
  }
  rk.finish();scene.add(roadGroup);freeze(roadGroup);
  for(const city of world.cities){
    const g=new THREE.Group();g.position.set(city.x,0,city.z);const k=kit(g);
    const factionColor=world.factions[city.faction]?.color||'#977b4c';
    // Cross streets, ring streets and narrow residential lanes form city blocks.
    k.block(12,.06,70,road,0,.03,0);k.block(70,.06,10,road,0,.03,0);
    for(const offset of [-19,19]){k.block(4,.065,69,0x9e957e,offset,.035,0);k.block(69,.065,4,0x9e957e,0,.035,offset);}
    k.block(19,.07,18,0xc1b69a,0,.04,0);
    // Yamen compound and ceremonial central approach.
    k.block(21,.07,21,0xb4a58b,0,.04,-22);
    k.block(5,.025,13,0x91644d,0,.09,-17);
    steppedRoof(k,0,-27,23,14,4.5,0x66433b);
    for(const x of [-8,-4,4,8])k.block(.3,4.1,.3,0x94503b,x,2.1,-21.7);
    k.block(7,.7,.22,0x312d29,0,3.3,-21.3);
    label(g,'府 衙',0,3.3,-21.08,5.5,'#ffd98d');
    label(g,city.name+' · 内城府衙',0,6.4,-13,9,'#ffe2a2');
    for(const side of [-1,1]){
      k.block(1.1,.6,1.1,stone,side*7,.3,-14);k.block(.5,1.4,.5,stone,side*7,1.25,-14);
      k.block(1.2,.14,1.2,0x6c6559,side*7,2,-14);
    }
    // Residential homes have walk-in doors and low stepped tile roofs.
    for(const home of city.houses){
      const hx=home.x-city.x,hz=home.z-city.z;
      k.block(4.8,.05,4.8,0xa88c65,hx,.025,hz);
      steppedRoof(k,hx,hz,6.2,6.1,3.3,roof);
      k.block(1.25,.18,.25,wood,hx,2.7,hz+2.55);
      for(const side of [-1,1])k.block(.8,.65,.09,0x3d352a,hx+side*1.3,1.8,hz+2.52);
    }
    // Street market awnings and counters, collision proxies supplied by Python.
    for(const stall of city.markets){
      const x=stall.x-city.x,z=stall.z-city.z;
      k.block(4,.16,2.4,factionColor,x,2.7,z);
      for(const side of [-1,1])k.block(.12,2.7,.12,wood,x+side*1.8,1.35,z);
      for(const side of [-1,0,1])k.block(.5,.4,.5,side===0?0x9ca64d:0xa87547,x+side,.7,z);
    }
    // Crenellated battlements wrap all walls except the four broad gates.
    for(let offset=-32;offset<=32;offset+=4){
      if(Math.abs(offset)<=5)continue;
      for(const [x,z,w,d] of [[offset,-36,2,1], [offset,36,2,1],[-36,offset,1,2],[36,offset,1,2]])k.block(w,.9,d,0x7c7770,x,6.4,z);
    }
    for(const x of [-35,35])for(const z of [-35,35]){
      k.block(6,.4,6,0x79716a,x,9.2,z);steppedRoof(k,x,z,7.5,7.5,9.6);
      for(const sx of [-1,1])k.block(.25,2,.25,wood,x+sx*1.8,8.1,z);
    }
    // Four gate towers, each open underneath. South gate opens into a barbican.
    for(const side of city.gates){
      const east=side==='east'||side==='west',x=side==='east'?36:side==='west'?-36:0,z=side==='south'?36:side==='north'?-36:0;
      k.block(east?5:13,.5,east?13:5,0x7a7067,x,5.3,z);
      k.block(east?4.4:11,2.1,east?11:4.4,0x6a4a34,x,6.55,z);
      steppedRoof(k,x,z,east?7:15,east?15:7,7.9);
      // City name and faction banner are readable at the active gate.
      label(g,city.name,x,4.1,z+(side==='south'?-.2:side==='north'?.2:0),7.5);
      k.block(.16,4,.16,wood,x+(east?0:5.2),10.5,z+(east?5.2:0));
      k.block(east?.15:2.7,1.8,east?2.7:.15,factionColor,x+(east?0:6.4),11,z+(east?6.4:0));
    }
    // Barbican walls, thick parapets and an offset approach gate.
    k.block(20,.25,12,0xb2a17d,0,.04,42);
    for(const x of [-10,10])k.block(.35,.3,13,0x8a8177,x,5.15,42);
    k.block(6,.45,3.2,0x817369,4,5.25,48);steppedRoof(k,4,48,8,5,5.7);
    label(g,'瓮 城 · '+city.name,4,7.4,49,7.5);
    // Quarter guide markers assist navigation without utility-dashboard panels.
    label(g,'街 市',23,3.7,0,4.5,'#ead7ad');
    const materials=k.finish();renderer.openCityFlags.set(city.id,[{material:materials.get(String(factionColor))}]);
    g.userData.cityId=city.id;scene.add(g);freeze(g);renderer.openCityGroups.set(city.id,g);
  }
  for(const village of world.villages||[]){
    const g=new THREE.Group();g.position.set(village.x,0,village.z);const k=kit(g);k.block(17,.06,15,road,0,.03,0);
    for(const side of [-1,1])steppedRoof(k,side*6,4,4.2,4.2,2.5,0x70513d);
    label(g,village.name+' · 驿站 / 军屯',0,4.2,-5,7,'#f2e0a9');k.finish();scene.add(g);freeze(g);
  }
  renderer.openRoadGroup=roadGroup;
}
