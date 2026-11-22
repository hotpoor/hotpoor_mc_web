// China strategic map, room selector and faction conquest HUD.
export function installOpenWorldUI({G,$,send,esc,banner,log,cancelDraw}) {
  let selected='',listKey='',mapPoints=[],restartGeneration=null;
  function chooseMode(mode){
    G.mode=mode==='open'?'open':'campaign';localStorage.setItem('mc.mode',G.mode);
    for(const b of document.querySelectorAll('.mode-choice'))b.classList.toggle('active',b.dataset.mode===G.mode);
    const url=new URL(location.href);url.searchParams.set('mode',G.mode);history.replaceState(null,'',url);
  }
  for(const b of document.querySelectorAll('.mode-choice'))b.onclick=()=>chooseMode(b.dataset.mode);
  chooseMode(G.mode);
  $('mode-switch-btn').onclick=()=>{const url=new URL(location.href);url.searchParams.set('mode',G.mode==='open'?'campaign':'open');url.searchParams.set('name',G.name);url.searchParams.set('team',G.team);url.searchParams.set('auto','1');location.href=url.href;};
  function ownerName(id){return id==='red'?'赤焰阵营':id==='blue'?'苍蓝阵营':G.world?.factions?.[id]?.name||id||'无主';}
  function ownerColor(id){return id==='red'?'#ef6464':id==='blue'?'#6ba0ff':G.world?.factions?.[id]?.color||'#c6b070';}
  function stateFor(id){return G.conquest?.cities?.find(c=>c.id===id);}
  function projection(canvas){
    const outline=G.world.china_outline||[],cities=G.world.cities||[];
    const points=[...outline,...cities.map(c=>[c.x,c.z])];
    const xs=points.map(p=>p[0]),zs=points.map(p=>p[1]);
    const minX=Math.min(...xs)-80,maxX=Math.max(...xs)+80,minZ=Math.min(...zs)-80,maxZ=Math.max(...zs)+80;
    const scale=Math.min((canvas.width-36)/(maxX-minX),(canvas.height-36)/(maxZ-minZ));
    return {x:v=>canvas.width/2+(v-(minX+maxX)/2)*scale,z:v=>canvas.height/2+(v-(minZ+maxZ)/2)*scale};
  }
  function drawMap(canvas,mini=false){
    if(!G.world?.cities)return;const ctx=canvas.getContext('2d'),p=projection(canvas);ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle=mini?'#183638':'#173c4a';ctx.fillRect(0,0,canvas.width,canvas.height);
    const outline=G.world.china_outline||[];
    if(outline.length){ctx.beginPath();outline.forEach((v,i)=>i?ctx.lineTo(p.x(v[0]),p.z(v[1])):ctx.moveTo(p.x(v[0]),p.z(v[1])));ctx.closePath();ctx.fillStyle='#a39668';ctx.fill();ctx.strokeStyle='#d4c493';ctx.lineWidth=mini?1:2;ctx.stroke();}
    for(const river of G.world.rivers||[]){const points=Array.isArray(river)?river:river.points||[];ctx.beginPath();points.forEach((v,i)=>i?ctx.lineTo(p.x(v[0]),p.z(v[1])):ctx.moveTo(p.x(v[0]),p.z(v[1])));ctx.strokeStyle='#78c7df';ctx.lineWidth=mini?1:2.5;ctx.stroke();}
    if(!mini){ctx.fillStyle='#f4e3b4';ctx.font='bold 17px sans-serif';ctx.fillText('山河为界 · 群雄逐鹿',22,30);ctx.font='12px sans-serif';ctx.fillText('点选城池，查看守军与所属势力',22,canvas.height-18);}
    mapPoints=[];
    G.world.cities.forEach((city,index)=>{const state=stateFor(city.id),owner=state?.owner||city.faction,x=p.x(city.x),z=p.z(city.z);ctx.beginPath();ctx.arc(x,z,mini?2.7:selected===city.id?8:5.5,0,Math.PI*2);ctx.fillStyle=ownerColor(owner);ctx.fill();ctx.strokeStyle=selected===city.id?'#ffffff':'#443c2b';ctx.lineWidth=selected===city.id?2:1;ctx.stroke();
      if(!mini){mapPoints.push({id:city.id,x,z});if(selected===city.id){ctx.font='bold 14px sans-serif';ctx.fillStyle='#fff5d1';ctx.textAlign='left';ctx.fillText(city.name,x+10,z-9);}else{ctx.font='9px sans-serif';ctx.fillStyle='#292a26';ctx.textAlign='center';ctx.fillText(index+1,x,z+3);}}
    });
    for(const actor of G.players.values()){if(!actor.alive)continue;ctx.beginPath();ctx.arc(p.x(actor.rx),p.z(actor.rz),actor.id===G.id?(mini?3:5):(mini?2:3),0,Math.PI*2);ctx.fillStyle=actor.id===G.id?'#fff':ownerColor(actor.team);ctx.fill();}
    ctx.textAlign='left';
  }
  function renderSelected(){
    const city=G.world.cities.find(c=>c.id===selected);if(!city){$('world-map-city-info').textContent='选择一座城池，决定下一步行军方向。';$('world-march-btn').disabled=true;return;}
    const state=stateFor(city.id),owner=state?.owner||city.faction;
    const names=(state?.generals||[]).map(g=>g.name+(g.recruited?'（已追随'+g.owner+'）':'')).join('、');
    $('world-map-city-info').innerHTML='<b>'+esc(city.name)+'</b> · '+esc(ownerName(owner))+'<br>守军剩余 '+(state?.defenders??'—')+' / '+(state?.total_defenders??'—')+' · '+(owner===G.team?'己方属城，可休整和招募降将':state?.capturable?'守军已清，前往府衙按 E 占领':'击败守军，再到府衙按 E 占领')+'<br>武将：'+esc(names||city.bosses?.join('、')||'待探索');
    $('world-march-btn').textContent=(owner===G.team?'前往己方属城外 · ':'行军至城外 · ')+city.name;
    $('world-march-btn').disabled=!G.me?.alive||!!G.me.recall||!!G.me.transferCd;
  }
  function render(){
    const conquest=G.conquest;if(!conquest)return;
    $('world-map-progress').textContent='赤焰 '+conquest.owned.red+' 城 · 苍蓝 '+conquest.owned.blue+' 城 · 天下共 '+conquest.total+' 城 · 红蓝可 PK、夺城，目标一统天下';
    const key=(conquest.cities||[]).map(c=>c.id+c.owner+c.defenders+(c.generals||[]).map(g=>g.owner).join(',')).join('|')+selected;
    if(key!==listKey){listKey=key;$('world-map-cities').innerHTML=G.world.cities.map((city,i)=>{const s=stateFor(city.id),owner=s?.owner||city.faction;return '<button class="world-city-row '+(selected===city.id?'active':'')+'" data-city="'+esc(city.id)+'"><b style="color:'+ownerColor(owner)+'">'+(i+1)+' · '+esc(city.name)+'</b><small>'+esc(ownerName(owner))+' · 守军 '+(s?.defenders??'—')+'</small></button>';}).join('');for(const button of $('world-map-cities').querySelectorAll('button'))button.onclick=()=>{selected=button.dataset.city;render();};}
    renderSelected();drawMap($('world-map-canvas'));
  }
  function openMap(){if(G.mode!=='open'||!G.joined)return;G.keys.clear();G.attacking=false;cancelDraw();if(document.pointerLockElement)document.exitPointerLock();if(!selected&&G.me)selected=G.world.cities.reduce((a,b)=>Math.hypot(a.x-G.me.rx,a.z-G.me.rz)<Math.hypot(b.x-G.me.rx,b.z-G.me.rz)?a:b).id;$('world-map-panel').classList.remove('hidden');render();}
  function closeMap(){$('world-restart-confirm').classList.add('hidden');restartGeneration=null;$('world-map-panel').classList.add('hidden');}
  $('world-restart-btn').onclick=()=>{openMap();restartGeneration=G.conquest?.generation;$('world-restart-confirm').classList.remove('hidden');$('world-restart-status').textContent='';$('world-restart-accept').disabled=false;$('world-restart-confirm').scrollIntoView({block:'nearest'});$('world-restart-cancel').focus();};
  $('world-restart-cancel').onclick=()=>{$('world-restart-confirm').classList.add('hidden');restartGeneration=null;};
  $('world-restart-accept').onclick=()=>{if(restartGeneration==null)return;$('world-restart-accept').disabled=true;send({t:'open_restart',confirmed:true,generation:restartGeneration});$('world-restart-status').textContent='正在重新开始大世界…';};
  $('world-map-btn').onclick=openMap;$('world-map-close').onclick=closeMap;
  $('world-map-canvas').onclick=event=>{const cv=$('world-map-canvas'),rect=cv.getBoundingClientRect(),x=(event.clientX-rect.left)/rect.width*cv.width,z=(event.clientY-rect.top)/rect.height*cv.height;const pick=mapPoints.reduce((best,c)=>Math.hypot(c.x-x,c.z-z)<Math.hypot(best.x-x,best.z-z)?c:best,{x:1e9,z:1e9});if(pick.id&&Math.hypot(pick.x-x,pick.z-z)<24){selected=pick.id;render();}};
  function march(city){if(!G.me?.alive||G.me.recall||G.me.transferCd)return;G.keys.clear();G.attacking=false;cancelDraw();send({t:'open_travel',city});closeMap();}
  $('world-march-btn').onclick=()=>march(selected);$('world-base-btn').onclick=()=>march('base');
  return {openMap,closeMap,isOpen:()=>$('world-map-panel')&&!$('world-map-panel').classList.contains('hidden'),
    onWelcome(){chooseMode(G.world.mode==='open'?'open':'campaign');const open=G.mode==='open';$('campaign-journal').classList.toggle('hidden',open);$('open-conquest-status').classList.toggle('hidden',!open);$('world-map-btn').classList.toggle('hidden',!open);$('world-restart-btn').classList.toggle('hidden',!open);$('mode-switch-btn').textContent=open?'切换到十章征战':'切换到开放世界';document.querySelector('.brand-sub').textContent=open?'三国开放世界 · 群雄割据 · 红蓝 PK':'MINECRAFT WEB · 多人实时对抗';},
    applyState(state){if(G.mode!=='open')return;G.conquest=state.conquest;const c=G.conquest;if(!c)return;$('open-conquest-status').textContent='我方占领 '+c.owned[G.team]+'/'+c.total+' 城 · 武将跟随 · M 天下图';const near=G.world.cities.find(city=>G.me&&Math.hypot(city.x-G.me.rx,city.z-G.me.rz)<city.radius+16);if(near){const s=stateFor(near.id);$('campaign-status').textContent=near.name+' · '+ownerName(s?.owner||near.faction)+' · 剩余守军 '+s?.defenders;}else $('campaign-status').textContent='自由行军 · 到府衙占领城池 · M 选择城池';if(G.me?.openTravel)$('campaign-status').textContent='行军引导中 · '+G.me.recall.toFixed(1)+'秒';if(this.isOpen())render();},
    restartResult(message){$('world-restart-status').textContent=message;$('world-restart-confirm').classList.add('hidden');restartGeneration=null;},
    drawMini:canvas=>drawMap(canvas,true),
    handleEvent(event){if(event.k==='open_restarted'){this.closeMap();listKey='';selected='';banner(event.text);log(event.text,'join');return true;}if(['city_captured','city_cleared','conquest_victory'].includes(event.k)){banner(event.text);log(event.text,'kill');return true;}if(event.k==='general_recruited'){if(event.id===G.id){banner(event.text);log(event.text,'join');}return true;}if(event.k==='open_travel'){this.closeMap();G.renderer?.spawnSlam?.({x:event.x,y:0,z:event.z});if(event.id===G.id){banner('已抵达 '+event.name+'，自由行军攻城');if(G.me)G.renderer?.camTarget?.set(G.me.rx,0,G.me.rz);}return true;}return false;}
  };
}
