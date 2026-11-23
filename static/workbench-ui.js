export function installWorkbench({G,$,send,cancelDraw,banner,log}){
 let key='';
 const isOpen=()=>!$('workbench-panel').classList.contains('hidden');
 function close(){$('workbench-panel').classList.add('hidden');}
 function render(){
  if(!G.world)return;const bag=G.me?.resources||{},defs=G.world.resources||{};
  $('resource-bag').textContent='材料袋 · '+Object.entries(defs).map(([id,cfg])=>cfg.name+' '+(bag[id]||0)).join(' / ');
  $('workbench-btn').disabled=!G.me?.alive||!G.me?.workbenchNear||!!G.me?.recall;
  if(!isOpen())return;
  const near=G.me?.workbenchNear&&G.me?.alive&&!G.me?.recall;
  $('workbench-hint').textContent=near?'按配方合成后立即装备；材料按 E 拾取，20秒后刷新。':'请靠近营地的合成工作台（3.5格内）。';
  const next=JSON.stringify([bag,G.me?.weapons,near]);if(key===next)return;key=next;
  $('workbench-recipes').replaceChildren();
  for(const [weapon,recipe] of Object.entries(G.world.workbench_recipes||{})){
   const card=document.createElement('button');card.className='workbench-recipe';card.dataset.workbenchWeapon=weapon;
   const title=document.createElement('b');title.textContent=recipe.name;card.append(title);
   const cost=document.createElement('span');cost.textContent=Object.entries(recipe.cost).map(([id,count])=>defs[id].name+' '+(bag[id]||0)+'/'+count).join(' ＋ ');card.append(cost);
   const uses=document.createElement('small');uses.textContent=recipe.uses===-1?'无限使用 · 蓄力1秒 · 冷却5秒':'合成后 '+recipe.uses+' 次';card.append(uses);
   const old=G.me?.weapons?.[weapon]||0;card.disabled=!near||old===-1||(recipe.uses!==-1&&old>=recipe.uses)||Object.entries(recipe.cost).some(([id,count])=>(bag[id]||0)<count);
   card.onclick=()=>send({t:'workbench_craft',weapon});$('workbench-recipes').append(card);
  }
 }
 function open(){if(!G.joined)return;G.keys.clear();G.attacking=false;cancelDraw();if(document.pointerLockElement)document.exitPointerLock();$('workbench-panel').classList.remove('hidden');key='';render();$('workbench-close').focus();}
 $('workbench-btn').onclick=open;$('workbench-close').onclick=close;
 return {isOpen,close,render,handleEvent(ev){if(ev.id!==G.id)return false;if(ev.k==='workbench_open'){open();return true;}if(ev.k==='material_pickup'||ev.k==='workbench_crafted'){banner(ev.text);log(ev.text,'join');if(isOpen())render();return true;}return false;}};
}
