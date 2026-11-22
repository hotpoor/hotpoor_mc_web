// Distant and crowded NPCs share a handful of instanced draws.
import * as THREE from './vendor/three.module.js';
export class CrowdRenderer {
  constructor(scene){this.scene=scene;this.capacity=0;this.meshes=[];this.dummy=new THREE.Object3D();this.color=new THREE.Color();}
  reserve(count){
    if(count<=this.capacity)return;
    for(const mesh of this.meshes){this.scene.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();}
    this.capacity=Math.max(64,2**Math.ceil(Math.log2(count)));this.meshes=[];
    for(let i=0;i<7;i++){
      const mesh=new THREE.InstancedMesh(new THREE.BoxGeometry(1,1,1),new THREE.MeshLambertMaterial({color:0xffffff}),this.capacity);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);mesh.frustumCulled=false;this.meshes.push(mesh);this.scene.add(mesh);
    }
  }
  sync(actors,time){
    this.reserve(actors.length);this.count=actors.length;
    for(let i=0;i<this.meshes.length;i++){this.meshes[i].count=actors.length;this.meshes[i].visible=!!actors.length;}
    for(let index=0;index<actors.length;index++){
      const o=actors[index],yaw=o.yaw||0,scale=o.boss?1.2:1;
      const tint=o.team==='red'?0xd95757:o.team==='blue'?0x5684c9:o.color||0x8e8057;
      const swing=o.moving?Math.sin(time*7+index)*.35:0;
      const parts=[[0,1.08,0,.62,.75,.42,tint,0],[0,1.72,0,.52,.52,.5,0xcda17f,0],[-.18,.4,0,.25,.75,.3,0x44443e,swing],[.18,.4,0,.25,.75,.3,0x44443e,-swing],[-.44,1.18,0,.23,.65,.25,tint,-swing],[.44,1.18,0,.23,.65,.25,tint,o.attacking?-1.3:swing],[.44,.85,.35,.08,.8,.09,0xbcc9c5,o.attacking?-1.3:0]];
      for(let part=0;part<parts.length;part++){
        const [x,y,z,w,h,d,color,rx]=parts[part],m=this.meshes[part],dummy=this.dummy;
        dummy.position.set(o.x+(Math.cos(yaw)*x+Math.sin(yaw)*z)*scale,(o.y||0)+y*scale,o.z+(-Math.sin(yaw)*x+Math.cos(yaw)*z)*scale);
        dummy.rotation.set(rx,yaw,0);dummy.scale.set(w*scale,h*scale,d*scale);dummy.updateMatrix();m.setMatrixAt(index,dummy.matrix);
        this.color.set(o.hurt?0xffe1d8:color);m.setColorAt(index,this.color);
      }
    }
    for(const mesh of this.meshes){mesh.instanceMatrix.needsUpdate=true;if(mesh.instanceColor)mesh.instanceColor.needsUpdate=true;}
  }
}
