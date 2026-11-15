import { SKIN_NAMES, drawSkinFace } from './player-skins.js?v=22';

// mc-web client: networking, input, prediction, HUD and panels.
const BUILD = new URL(import.meta.url).searchParams.get('v');
const ROOT = new URL('../', import.meta.url);
console.info('[mc-web] client build', BUILD);
const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const TEAM_CSS = { red: '#ef4f4f', blue: '#4c86f0' };
let canvas = $('view');

const G = {
  ws: null, id: null, name: '', team: '', teamChoice: 'auto', skin: 'steve', world: null,
  players: new Map(), me: null, renderer: null, connected: false, joined: false,
  keys: new Set(), mouse: { cx: innerWidth / 2, cy: innerHeight / 2, wx: 0, wz: 0 },
  attacking: false, lastAttack: -Infinity, weapon: 'sword', drawStart: null, chatOpen: false, yaw: 0,
  viewMode: 'third', dragging: false,
  invertLook: localStorage.getItem('mc.invertLook') === '1',
  teamScore: { red: 0, blue: 0 }, online: 0,
  inputAcc: 0, hudAcc: 0, loopStarted: false,
  plates: new Map(), flashTimer: null, bannerTimer: null, reconnectTimer: null,
};

const randomName = () => '玩家' + Math.floor(1000 + Math.random() * 9000);
function send(obj) {
  if (G.ws && G.ws.readyState === WebSocket.OPEN) G.ws.send(JSON.stringify(obj));
}

// ---------------------------------------------------------------- connection
function setConn(ok, text) {
  G.connected = ok;
  $('conn-dot').className = 'conn-dot ' + (ok ? 'ok' : (text === '连接中' ? '' : 'bad'));
  $('conn-text').textContent = text || (ok ? '已连接' : '已断开');
}

let updating = false;

async function checkUpdate() {
  if (updating) return;
  try {
    const response = await fetch(new URL('static/index.html', ROOT), { cache: 'no-store' });
    if (!response.ok) return;
    const version = (await response.text()).match(/main\.js\?v=([0-9]+)/)?.[1];
    if (!version || Number(version) <= Number(BUILD) || updating) return;
    updating = true;
    if (G.joined) sessionStorage.setItem('mc.rejoin', JSON.stringify({ name: G.name, team: G.team }));
    $('offline-msg').textContent = '游戏已更新，即将自动刷新…';
    $('offline').classList.remove('hidden');
    setTimeout(() => location.reload(), 1200);
  } catch (_) { /* The server may be restarting. */ }
}

setInterval(checkUpdate, 15000);
window.addEventListener('focus', checkUpdate);

function connect() {
  clearTimeout(G.reconnectTimer);
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${ROOT.host}${ROOT.pathname}ws`);
  G.ws = ws;
  setConn(false, '连接中');
  ws.onopen = () => {
    checkUpdate();
    setConn(true);
    $('offline').classList.add('hidden');
    send({ t: 'join', name: G.name, team: G.teamChoice === 'auto' ? null : G.teamChoice, skin: G.skin });
  };
  ws.onmessage = e => {
    let msg;
    try { msg = JSON.parse(e.data); } catch (_) { return; }
    if (msg.t === 'welcome') onWelcome(msg);
    else if (msg.t === 'state') applyState(msg);
  };
  ws.onclose = () => {
    G.drawStart = null;
    setConn(false);
    checkUpdate();
    if (!G.joined) {
      $('join-btn').disabled = false;
      $('login-msg').textContent = '连接失败，请确认服务端已启动后重试';
      return;
    }
    $('offline').classList.remove('hidden');
    $('offline-msg').textContent = '正在重连…（战绩已保存在服务端）';
    G.reconnectTimer = setTimeout(connect, 2000);
  };
  ws.onerror = () => {};
}

function onWelcome(msg) {
  if (Number(msg.world.client_build) > Number(BUILD)) checkUpdate();
  G.id = msg.id;
  G.name = msg.name;
  G.team = msg.team;
  G.world = msg.world;
  G.joined = true;
  updateSkinButton();
  equip(G.weapon);
  $('login').classList.add('hidden');
  $('hud-name').textContent = msg.name;
  $('hud-team').textContent = msg.world.teams[msg.team].name;
  $('hud-team').className = 'tag ' + msg.team;
  $('hud-avatar').style.setProperty('--gold', TEAM_CSS[msg.team]);
  renderRank(msg.leaderboard || []);
  renderHistory(msg.history || []);
  initRenderer();
  setInterval(refreshData, 5000);
}

async function initRenderer() {
  if (G.renderer) return;
  try {
    const mod = await import('./render3d.js?v=' + BUILD);
    G.renderer = new mod.Renderer3D(canvas, G.world);
  } catch (err) {
    console.warn('[mc-web] WebGL unavailable, using 2D fallback:', err);
    const fresh = canvas.cloneNode(false);
    canvas.parentNode.replaceChild(fresh, canvas);
    canvas = fresh;
    const mod = await import('./render2d.js?v=' + BUILD);
    G.renderer = new mod.Renderer2D(canvas, G.world);
  }
  canvas.addEventListener('mousedown', e => {
    if (!G.joined || G.chatOpen) return;
    if (e.button === 2) { G.dragging = true; return; }
    if (e.button !== 0) return;
    G.attacking = true;
    aimYaw();
    if (G.weapon === 'rocket') {
      if (G.me?.alive && !G.me.rocketCd) send({ t: 'attack', yaw: G.yaw });
    } else if (G.weapon === 'gun') {
      fireGun();
    } else if (!['sword', 'axe', 'mace', 'hammer'].includes(G.weapon)) {
      const now = performance.now();
      if (G.me?.alive && G.drawStart === null && (G.weapon === 'beam' ? !G.me.beamCd : now - G.lastAttack >= 470)) {
        G.drawStart = now;
        send({ t: 'draw' });
      }
    } else tryAttack();
    if (G.viewMode === 'first' && !document.pointerLockElement) {
      // Pointer lock gives full 360-degree look; right-drag is the fallback
      // when the browser refuses the request.
      try {
        const req = canvas.requestPointerLock && canvas.requestPointerLock();
        if (req && req.catch) req.catch(() => {});
      } catch (_) { /* right-drag still works */ }
    }
  });
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    G.renderer.setZoom(Math.sign(e.deltaY) * 0.08);
  }, { passive: false });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  window.addEventListener('resize', () => G.renderer.resize());
  window.addEventListener('mouseup', e => {
    if (e.button === 2) G.dragging = false;
    if (e.button !== 0) return;
    G.attacking = false;
    if (G.drawStart === null) return;
    const elapsed = performance.now() - G.drawStart;
    G.drawStart = null;
    if (elapsed >= (G.weapon === 'beam' ? 1000 : 120) && G.me?.alive && !G.chatOpen) {
      if (G.weapon === 'bow') G.lastAttack = performance.now();
      send({ t: 'attack', yaw: aimYaw(), pitch: G.viewMode === 'first' ? G.renderer.getPitch() : 0 });
      pulseCrosshair();
    } else send({ t: 'cancel_draw' });
  });
  if (!G.loopStarted) {
    G.loopStarted = true;
    requestAnimationFrame(frame);
  }
}

// ---------------------------------------------------------------- state
function applyState(s) {
  const seen = new Set();
  const recalled = new Set((s.events || []).filter(ev => ev.k === 'recall').map(ev => ev.id));
  for (const p of s.players) {
    seen.add(p.id);
    let o = G.players.get(p.id);
    if (!o) {
      o = { id: p.id, px: p.x, pz: p.z, rx: p.x, rz: p.z,
            lastX: p.x, lastZ: p.z, jump: p.jump || 0, targetJump: p.jump || 0, moving: 0 };
      G.players.set(p.id, o);
    }
    const justRespawned = !o.alive && p.alive;
    if (justRespawned || recalled.has(p.id)) { o.rx = p.x; o.rz = p.z; }
    if (p.id === G.id) {
      const dx = p.x - o.px, dz = p.z - o.pz;
      if (Math.hypot(dx, dz) > 4 || justRespawned || recalled.has(p.id)) { o.px = p.x; o.pz = p.z; }
      else { o.px += dx * 0.35; o.pz += dz * 0.35; }
    } else {
      o.moving = Math.min(1, Math.hypot(p.x - o.lastX, p.z - o.lastZ) / 0.3);
      o.px = p.x; o.pz = p.z;
    }
    o.lastX = p.x; o.lastZ = p.z;
    Object.assign(o, {
      name: p.name, team: p.team, skin: p.id === G.id ? G.skin : p.skin, weapon: p.id === G.id ? G.weapon : p.weapon, draw: p.draw, waveCd: p.wave_cd, beamCd: p.beam_cd, rocketCd: p.rocket_cd, gunCd: p.gun_cd, ammo: p.ammo, recall: p.recall, carriesCrystal: p.carries_crystal, recallCd: p.recall_cd, targetJump: p.jump || 0, yaw: p.yaw, hp: p.hp, alive: p.alive,
      respawn: p.respawn, score: p.score, kills: p.kills, deaths: p.deaths,
      heal: p.heal, pool: p.pool, invuln: p.invuln,
    });
    // Our own facing is decided locally every frame (mouse look), never let
    // the 20 Hz snapshot overwrite it and cause jitter.
    if (p.id === G.id) o.yaw = G.yaw;
  }
  for (const id of [...G.players.keys()]) {
    if (!seen.has(id)) {
      G.players.delete(id);
      const plate = G.plates.get(id);
      if (plate) { plate.remove(); G.plates.delete(id); }
    }
  }
  G.me = G.players.get(G.id) || null;
  if (!G.me?.alive) cancelDraw();
  G.online = s.players.length;
  G.teamScore = s.team_score || G.teamScore;
  $('online-count').textContent = G.online;
  $('score-red').textContent = G.teamScore.red || 0;
  $('score-blue').textContent = G.teamScore.blue || 0;
  const objects = s.objects || [];
  G.renderer?.syncObjectives?.(objects);
  for (const team of ['red', 'blue']) {
    const crystal = objects.find(obj => obj.id === team);
    if (crystal) $('crystal-' + team).textContent = crystal.hp
      ? G.world.teams[team].short + '水晶 ' + crystal.hp + '/' + crystal.max_hp
      : G.world.teams[team].short + '基地与泉水回血暂停 ' + crystal.cooldown + ' 秒';
  }
  for (const ev of (s.events || [])) handleEvent(ev);
  G.renderer?.syncArrows?.(s.arrows || []);
}

function handleEvent(ev) {
  switch (ev.k) {
    case 'join':
      log(`${ev.name} 加入了${G.world.teams[ev.team].short}阵营`, 'join');
      break;
    case 'leave':
      log(`${ev.name} 离开了世界`, 'join');
      break;
    case 'arrow':
      G.renderer?.spawnArrow?.(ev);
      break;
    case 'crystal_repair':
      G.renderer?.spawnRepair?.(ev);
      if (ev.id === G.id) log('水晶修复 +' + ev.amount + ' · ' + ev.hp + '/' + ev.max_hp, 'join');
      break;
    case 'crystal':
      log(G.world.teams[ev.team].name + '水晶被打碎，基地与泉水回血暂停 30 秒', 'join');
      break;
    case 'bomb':
      G.renderer?.spawnWave?.({ start: [ev.x, .65, ev.z], end: [ev.x, .65, ev.z], blast: true });
      break;
    case 'wave':
      G.renderer?.spawnWave?.(ev);
      pulseCrosshair();
      break;
    case 'arrow_stop':
      G.renderer?.stopArrow?.(ev);
      break;
    case 'attack':
      if (G.renderer && ev.id !== G.id) G.renderer.spawnSwing(ev.id);
      break;
    case 'hit': {
      const victim = G.players.get(ev.id);
      if (victim && G.renderer) floatText(victim, '-' + ev.dmg, '#ff8a7d');
      if (ev.id === G.id) flashDamage();
      break;
    }
    case 'kill':
      banner(`${ev.killer} ⚔ 击败了 ${ev.victim}`);
      log(`【击杀】${ev.killer} 击败了 ${ev.victim}（+100）`, 'kill');
      refreshData();
      break;
    case 'respawn':
      log(`${ev.name} 在老家复活了`, 'join');
      break;
    case 'chat':
      log(`${ev.name}：${ev.text}`, 'chat');
      break;
  }
}

// ---------------------------------------------------------------- input
function mapKey(key) {
  const k = key.toLowerCase();
  return ({ arrowup: 'w', arrowdown: 's', arrowleft: 'a', arrowright: 'd' })[k] || k;
}

window.addEventListener('keydown', e => {
  if (e.isComposing || e.target === $('name-input') || !G.joined) return;
  const k = mapKey(e.key);
  if (k === 'enter') {
    e.preventDefault();
    if (!G.chatOpen) openChat(); else { sendChat(); closeChat(); }
    return;
  }
  if (k === 'escape' && G.chatOpen) { closeChat(); return; }
  if (G.chatOpen || e.target === $('chat-input')) return;
  if (['1', '2', '3', '4', '5', '6', '7', '8'].includes(k) && G.joined && !e.repeat) {
    equip({ 1: 'sword', 2: 'bow', 3: 'beam', 4: 'rocket', 5: 'gun', 6: 'axe', 7: 'mace', 8: 'hammer' }[k]);
    return;
  }
  if (k === 'e' && !e.repeat) { e.preventDefault(); interactCrystal(); return; }
  if (k === 'h' && !e.repeat) { e.preventDefault(); recallHome(); return; }
  if (k === 'q' && !e.repeat) { castWave(); return; }
  if (k === 'v') { toggleView(); e.preventDefault(); return; }
  if (['w', 'a', 's', 'd', 'shift'].includes(k)) { G.keys.add(k); e.preventDefault(); }
  if (e.code === 'Space') {
    e.preventDefault();
    if (!e.repeat && G.me?.alive) send({ t: 'jump' });
  }
});
window.addEventListener('keyup', e => G.keys.delete(mapKey(e.key)));
window.addEventListener('blur', () => {
  cancelDraw();
  G.keys.clear(); G.attacking = false; G.dragging = false;
});
window.addEventListener('mousemove', e => {
  G.mouse.cx = e.clientX;
  G.mouse.cy = e.clientY;
  if (G.viewMode === 'first' && G.renderer &&
      (document.pointerLockElement === canvas || G.dragging)) {
    const sign = G.invertLook ? -1 : 1;
    G.renderer.applyLook(sign * (e.movementX || 0), e.movementY || 0);
  }
});

function openChat() {
  cancelDraw();
  G.chatOpen = true;
  G.keys.clear();
  G.attacking = false;
  G.dragging = false;
  if (document.pointerLockElement) document.exitPointerLock();
  $('chat-box').classList.remove('hidden');
  $('chat-input').focus();
}
function closeChat() {
  G.chatOpen = false;
  $('chat-input').value = '';
  $('chat-input').blur();
  $('chat-box').classList.add('hidden');
}
function sendChat() {
  const text = $('chat-input').value.trim();
  if (text) send({ t: 'chat', text });
}

function currentMove() {
  const forward = (G.keys.has('w') ? 1 : 0) - (G.keys.has('s') ? 1 : 0);
  const strafe = (G.keys.has('d') ? 1 : 0) - (G.keys.has('a') ? 1 : 0);
  let mx = 0, mz = 0;
  if (G.viewMode === 'first') {
    // W follows the camera heading (sin(yaw), cos(yaw)); screen-right in first
    // person is (-cos(yaw), sin(yaw)), so D must strafe along that vector.
    const fx = Math.sin(G.yaw), fz = Math.cos(G.yaw);
    mx = fx * forward - fz * strafe;
    mz = fz * forward + fx * strafe;
  } else {
    mx = strafe;
    mz = -forward;
  }
  const len = Math.hypot(mx, mz);
  if (len > 1) { mx /= len; mz /= len; }
  return { mx, mz, sprint: G.keys.has('shift') };
}

function clientCollides(x, z) {
  const half = G.world.half, edge = half - 1.36;
  if (Math.abs(x) > edge || Math.abs(z) > edge) return true;
  for (const b of G.world.blocks) {
    if (G.me.targetJump < b.h && Math.abs(x - b.x) < 0.86 && Math.abs(z - b.z) < 0.86) return true;
  }
  return false;
}

function aimYaw() {
  if (!G.renderer || !G.me) return G.yaw;
  if (G.viewMode === 'first') {
    G.yaw = G.renderer.getYaw();
  } else {
    const g = G.renderer.screenToGround(G.mouse.cx, G.mouse.cy);
    if (g) { G.mouse.wx = g.x; G.mouse.wz = g.z; }
    G.yaw = Math.atan2(G.mouse.wx - G.me.px, G.mouse.wz - G.me.pz) || 0;
  }
  G.me.yaw = G.yaw;
  return G.yaw;
}

let nextGunShot = 0;

function fireGun() {
  const now = performance.now();
  if (!G.me?.alive || G.me.gunCd || now < nextGunShot) return;
  nextGunShot = now + 130;
  send({ t: 'attack', yaw: G.yaw });
}

function updateSkinButton() {
  $('skin-toggle').textContent = '皮肤 · ' + SKIN_NAMES[G.skin];
  for (const button of document.querySelectorAll('[data-skin]')) {
    button.setAttribute('aria-pressed', String(button.dataset.skin === G.skin));
  }
}

function setupSkinList(list) {
  for (const [skin, label] of Object.entries(SKIN_NAMES)) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'skin-card';
    button.dataset.skin = skin;
    const portrait = document.createElement('canvas');
    portrait.setAttribute('aria-hidden', 'true');
    drawSkinFace(portrait, skin);
    button.append(portrait, label);
    button.addEventListener('click', () => {
      G.skin = skin;
      localStorage.setItem('mc.skin', skin);
      if (G.me) G.me.skin = skin;
      updateSkinButton();
      if (G.joined) send({ t: 'skin', skin });
    });
    list.append(button);
  }
}

$('skin-toggle').addEventListener('click', () => {
  const hidden = $('game-skins').classList.toggle('hidden');
  $('skin-toggle').setAttribute('aria-expanded', String(!hidden));
});

$('hammer-btn').addEventListener('click', () => { if (G.joined) equip('hammer'); });
$('mace-btn').addEventListener('click', () => { if (G.joined) equip('mace'); });
$('axe-btn').addEventListener('click', () => { if (G.joined) equip('axe'); });
$('gun-btn').addEventListener('click', () => { if (G.joined) equip('gun'); });

function interactCrystal() {
  if (G.me?.alive && !G.chatOpen) send({ t: 'interact' });
}

$('collect-btn').addEventListener('click', interactCrystal);

function recallHome() {
  if (!G.me?.alive || G.me.recall || G.me.recallCd || G.chatOpen) return;
  cancelDraw();
  G.attacking = false;
  send({ t: 'recall' });
}

$('recall-btn').addEventListener('click', recallHome);

function castWave() {
  if (G.me?.alive && !G.me.waveCd && !G.chatOpen) send({ t: 'wave', yaw: aimYaw() });
}

$('wave-btn').addEventListener('click', castWave);
$('rocket-btn').addEventListener('click', () => { if (G.joined) equip('rocket'); });
$('beam-btn').addEventListener('click', () => { if (G.joined) equip('beam'); });

function cancelDraw() {
  if (G.drawStart === null) return;
  G.drawStart = null;
  send({ t: 'cancel_draw' });
}

function equip(weapon) {
  if (weapon !== G.weapon) {
    cancelDraw();
    G.attacking = false;
  }
  G.weapon = weapon;
  if (G.me) G.me.weapon = weapon;
  $('weapon-toggle').textContent = ({ sword: '武器：剑 · 2 换弓', bow: '武器：弓 · 1 换剑', beam: '武器：龟派气功 · 1 换剑', rocket: '武器：火箭筒 · 1 换剑', gun: '武器：连射枪 · 1 换剑', axe: '武器：斧子 · 1 换剑', mace: '武器：狼牙棒 · 1 换剑', hammer: '武器：重锤 · 1 换剑' })[weapon];
  send({ t: 'equip', weapon });
}

$('weapon-toggle').addEventListener('click', () => {
  if (G.joined) equip(G.weapon === 'bow' ? 'sword' : 'bow');
});

function tryAttack() {
  const now = performance.now();
  if (!G.me || !G.me.alive || now - G.lastAttack < ({ axe: 850, mace: 1100, hammer: 1500 }[G.weapon] || 500)) return;
  G.lastAttack = now;
  // Play our own swing immediately so the weapon follows the click without
  // waiting a round-trip; other players' swings come from the server event.
  if (['sword', 'axe', 'mace', 'hammer'].includes(G.weapon) && G.renderer) G.renderer.spawnSwing(G.id);
  send({ t: 'attack', yaw: G.yaw });
  pulseCrosshair();
}

// ---------------------------------------------------------------- view mode
function setViewMode(mode) {
  if (!G.renderer || G.renderer.is2D) {
    log('当前是 2D 降级渲染，无法切换第一人称', 'join');
    return;
  }
  const next = mode === 'first' ? 'first' : 'third';
  if (G.viewMode === next) return;
  if (next === 'first') G.renderer.setYaw(G.yaw);
  G.viewMode = next;
  G.renderer.setViewMode(next, G.team);
  if (next === 'third' && document.pointerLockElement) document.exitPointerLock();
  G.dragging = false;
  document.body.classList.toggle('first-person', next === 'first');
  $('crosshair').classList.toggle('hidden', next !== 'first');
  $('view-hint').classList.toggle('hidden', next !== 'first');
  const btn = $('view-toggle');
  btn.textContent = next === 'first' ? '视角：第一人称 · 按 V 切换' : '视角：第三人称 · 按 V 切换';
  btn.classList.toggle('first', next === 'first');
  log(next === 'first' ? '已切换到第一人称视角' : '已切换到第三人称视角', 'join');
}

function toggleView() {
  setViewMode(G.viewMode === 'first' ? 'third' : 'first');
}

function pulseCrosshair() {
  if (G.viewMode !== 'first') return;
  const c = $('crosshair');
  c.classList.remove('pulse');
  void c.offsetWidth;
  c.classList.add('pulse');
}

// ---------------------------------------------------------------- frame
let lastFrame = performance.now();
function frame(now) {
  const dt = Math.min(0.05, Math.max(0, (now - lastFrame) / 1000));
  lastFrame = now;
  const r = G.renderer;
  if (!r) return requestAnimationFrame(frame);

  if (G.me && G.me.alive && !G.chatOpen) {
    const { mx, mz, sprint } = currentMove();
    const speed = sprint ? G.world.rules.sprint : G.world.rules.speed;
    const nx = G.me.px + mx * speed * dt, nz = G.me.pz + mz * speed * dt;
    if (!clientCollides(nx, G.me.pz)) G.me.px = nx;
    if (!clientCollides(G.me.px, nz)) G.me.pz = nz;
    if (mx || mz) G.me.moving = 1; else G.me.moving *= 0.6;

  }
  for (const o of G.players.values()) {
    const k = Math.min(1, dt * 13);
    o.rx += (o.px - o.rx) * k;
    o.rz += (o.pz - o.rz) * k;
    o.jump = o.alive ? o.jump + (o.targetJump - o.jump) * Math.min(1, dt * 25) : 0;
  }
  aimYaw();
  if (G.me) G.me.draw = G.drawStart === null ? null : Math.min(1, (now - G.drawStart) / 1000);
  if (G.attacking && !G.chatOpen) {
    if (['sword', 'axe', 'mace', 'hammer'].includes(G.weapon)) tryAttack();
    if (G.weapon === 'gun') fireGun();
  }

  G.inputAcc += dt;
  if (G.inputAcc >= 0.05) {
    G.inputAcc = 0;
    const { mx, mz, sprint } = currentMove();
    send({ t: 'input', mx, mz, yaw: G.yaw, sprint });
  }

  r.sync([...G.players.values()], G.me, dt);
  r.draw();
  updateNameplates();

  G.hudAcc += dt;
  if (G.hudAcc >= 0.08) {
    G.hudAcc = 0;
    updateHud();
    drawMinimap();
  }
  updateDeath();
  requestAnimationFrame(frame);
}

// ---------------------------------------------------------------- overlays
function updateNameplates() {
  for (const p of G.players.values()) {
    let n = G.plates.get(p.id);
    if (!n) {
      n = document.createElement('div');
      n.innerHTML = '<div class="np-name"></div><div class="np-bar"><div class="np-fill"></div></div><div class="np-status"></div>';
      $('nameplates').appendChild(n);
      G.plates.set(p.id, n);
    }
    if (!p.alive || !G.renderer || (p.id === G.id && G.viewMode === 'first')) {
      n.style.display = 'none'; continue;
    }
    const pr = G.renderer.project(p.rx, 2.35, p.rz);
    if (!pr.visible) { n.style.display = 'none'; continue; }
    n.style.display = 'block';
    n.style.left = pr.x + 'px';
    n.style.top = pr.y + 'px';
    n.className = 'nameplate ' + p.team + (p.id === G.id ? ' self' : '');
    n.querySelector('.np-name').textContent = p.name + (p.id === G.id ? '（你）' : '');
    const fill = n.querySelector('.np-fill');
    fill.style.width = Math.max(0, p.hp) + '%';
    fill.style.background = p.hp > 50 ? '#7bdc6a' : (p.hp > 25 ? '#ffd166' : '#e5484d');
    n.querySelector('.np-status').textContent = p.invuln ? '✦ 无敌' : (p.heal > 0 ? '✚ 回血' : '');
  }
}

function floatText(o, text, color) {
  const pr = G.renderer.project(o.rx, 2.0, o.rz);
  const d = document.createElement('div');
  d.className = 'floater';
  d.textContent = text;
  d.style.color = color;
  d.style.left = pr.x + 'px';
  d.style.top = pr.y + 'px';
  $('floaters').appendChild(d);
  setTimeout(() => d.remove(), 1000);
}

function flashDamage() {
  const f = $('damage-flash');
  f.style.opacity = '0.85';
  clearTimeout(G.flashTimer);
  G.flashTimer = setTimeout(() => { f.style.opacity = '0'; }, 90);
}

function banner(text) {
  const b = $('kill-banner');
  b.textContent = text;
  b.classList.add('show');
  clearTimeout(G.bannerTimer);
  G.bannerTimer = setTimeout(() => b.classList.remove('show'), 2600);
}

function log(text, cls = '') {
  const wrap = $('event-log');
  const line = document.createElement('div');
  line.className = 'log-line ' + cls;
  line.textContent = text;
  wrap.prepend(line);
  while (wrap.children.length > 6) wrap.lastChild.remove();
  setTimeout(() => { line.style.opacity = '0'; setTimeout(() => line.remove(), 400); }, 6500);
}

function updateHud() {
  const me = G.me;
  if (!me) return;
  $('hp-text').textContent = `${Math.ceil(Math.max(0, me.hp))} / 100`;
  $('hp-bar').style.width = Math.max(0, me.hp) + '%';
  $('stat-score').textContent = me.score ?? 0;
  $('stat-kills').textContent = me.kills ?? 0;
  $('stat-deaths').textContent = me.deaths ?? 0;
  $('wave-btn').textContent = me.waveCd > 0 ? '气功波 · ' + Math.ceil(me.waveCd) + ' 秒' : '气功波 · Q';
  const charge = G.weapon === 'beam' && me.draw != null ? ' · 蓄力 ' + Math.floor(me.draw * 100) + '%' : '';
  $('collect-btn').textContent = me.carriesCrystal ? '携带 1 颗 · E 修复或放下' : '采集水晶 · E';
  $('collect-btn').disabled = !me.alive || !!me.recall;
  $('recall-btn').textContent = me.recall ? '回城中 · ' + me.recall.toFixed(1) + ' 秒'
    : me.recallCd ? '回城 · ' + me.recallCd + ' 秒' : '回城 · H';
  $('recall-btn').disabled = !me.alive || !!me.recall || !!me.recallCd;
  $('gun-btn').textContent = '连射枪 · 5 · ' + (me.gunCd > 0 ? Math.ceil(me.gunCd) + ' 秒' : me.ammo + '/30');
  $('rocket-btn').textContent = '火箭筒 · 4' + (me.rocketCd > 0 ? ' · ' + Math.ceil(me.rocketCd) + ' 秒' : '');
  $('beam-btn').textContent = '龟派气功 · 3' + (me.beamCd > 0 ? ' · ' + Math.ceil(me.beamCd) + ' 秒' : charge);
  $('wave-btn').disabled = !me.alive || me.waveCd > 0;
  $('hud-status').textContent = !me.alive ? '阵亡 · 等待复活'
    : (me.invuln ? '✦ 复活保护中'
      : (me.heal > 0 ? `✚ 回血中 +${Math.round(me.heal)}/s${me.pool ? ' · ' + me.pool : ''}` : ''));
  $('heal-glow').style.opacity = me.alive && me.heal > 0 ? '0.7' : '0';
}

function updateDeath() {
  const me = G.me;
  const dying = !!(me && !me.alive);
  $('death-overlay').classList.toggle('hidden', !dying);
  if (!dying) return;
  $('death-seconds').textContent = Math.max(0, me.respawn).toFixed(1);
  $('death-bar-fill').style.width = Math.max(0, Math.min(100, me.respawn / 5 * 100)) + '%';
}

function drawMinimap() {
  const cv = $('minimap'), ctx = cv.getContext('2d');
  const size = cv.width, k = size / 64;
  const tx = x => (x + 32) * k, tz = z => (z + 32) * k;
  ctx.clearRect(0, 0, size, size);
  ctx.fillStyle = '#4e8240'; ctx.fillRect(0, 0, size, size);
  ctx.strokeStyle = 'rgba(255,255,255,.08)'; ctx.lineWidth = 1;
  for (let i = 8; i < 64; i += 8) {
    ctx.beginPath(); ctx.moveTo(i * k, 0); ctx.lineTo(i * k, size); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i * k); ctx.lineTo(size, i * k); ctx.stroke();
  }
  for (const t of Object.values(G.world.teams)) {
    const [x0, x1, z0, z1] = t.zone;
    ctx.fillStyle = TEAM_CSS[t.key] + 'aa';
    ctx.fillRect(tx(x0), tz(z0), (x1 - x0) * k, (z1 - z0) * k);
    ctx.fillStyle = '#fff';
    ctx.fillRect(tx(t.spawn[0]) - 3, tz(t.spawn[1]) - 3, 6, 6);
  }
  for (const pool of G.world.pools) {
    ctx.beginPath(); ctx.arc(tx(pool.x), tz(pool.z), pool.r * k, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(121,240,221,.65)'; ctx.fill();
    ctx.strokeStyle = '#d9fff7'; ctx.lineWidth = 1; ctx.stroke();
  }
  ctx.fillStyle = 'rgba(30,36,30,.55)';
  for (const b of G.world.blocks) ctx.fillRect(tx(b.x) - 1, tz(b.z) - 1, 2.5, 2.5);
  for (const p of G.players.values()) {
    if (!p.alive) continue;
    const x = tx(p.rx), z = tz(p.rz);
    ctx.beginPath(); ctx.arc(x, z, p.id === G.id ? 4 : 3, 0, Math.PI * 2);
    ctx.fillStyle = p.id === G.id ? '#ffffff' : (TEAM_CSS[p.team] || '#ccc');
    ctx.fill();
    if (p.id === G.id) {
      ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, z);
      ctx.lineTo(x + Math.sin(p.yaw) * 9, z + Math.cos(p.yaw) * 9);
      ctx.stroke();
    }
  }
  ctx.strokeStyle = '#59615c'; ctx.lineWidth = 3; ctx.strokeRect(1, 1, size - 2, size - 2);
  if (G.me) $('mini-pos').textContent = `${Math.round(G.me.rx)}, ${Math.round(G.me.rz)}`;
}

// ---------------------------------------------------------------- panels
async function refreshData() {
  try {
    const [lb, hs] = await Promise.all([
      fetch(new URL('api/leaderboard?limit=20', ROOT)).then(r => r.json()),
      fetch(new URL('api/history?limit=40', ROOT)).then(r => r.json()),
    ]);
    renderRank(lb.players || []);
    renderHistory(hs.history || []);
  } catch (_) { /* server may be restarting */ }
}

function renderRank(rows) {
  const box = $('tab-rank');
  if (!rows.length) {
    box.innerHTML = '<div class="empty-note">还没有战绩<br>第一个击杀就会出现在这里</div>';
    return;
  }
  box.innerHTML = rows.map((r, i) => `
    <div class="rank-row ${i < 3 ? 'top' : ''}">
      <span class="rank-no">${i + 1}</span>
      <span class="rank-team" style="background:${TEAM_CSS[r.team] || '#888'}"></span>
      <span class="rank-name">${esc(r.name)}</span>
      <span class="rank-score">${r.score}</span>
      <span class="rank-kd">${r.kills}K/${r.deaths}D</span>
    </div>`).join('');
}

function renderHistory(rows) {
  const box = $('tab-history');
  if (!rows.length) {
    box.innerHTML = '<div class="empty-note">暂无战斗记录</div>';
    return;
  }
  const label = { kill: '击杀', death: '阵亡', join: '加入', leave: '离开', respawn: '复活' };
  box.innerHTML = rows.map(r => `
    <div class="hist-row">
      <span class="hist-time">${esc((r.ts || '').slice(11))}</span>
      <span class="hist-${esc(r.type)}">[${label[r.type] || r.type}]</span>
      ${esc(r.detail || r.actor || '')}
    </div>`).join('');
}

// ---------------------------------------------------------------- login UI
document.querySelectorAll('.pick').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.pick').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    G.teamChoice = btn.dataset.team;
  });
});
$('join-btn').addEventListener('click', () => {
  G.name = $('name-input').value.trim() || randomName();
  localStorage.setItem('mc_name', G.name);
  $('join-btn').disabled = true;
  $('login-msg').textContent = '';
  connect();
});
$('name-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') $('join-btn').click();
});
$('view-toggle').addEventListener('click', toggleView);

function syncInvertBtn() {
  const b = $('invert-look');
  b.textContent = G.invertLook ? '水平视角：反转 · 点此恢复' : '水平视角：正常 · 点此反转';
  b.classList.toggle('on', G.invertLook);
}
$('invert-look').addEventListener('click', () => {
  if (G.renderer && G.renderer.is2D) {
    log('当前是 2D 降级渲染，没有第一人称视角', 'join');
    return;
  }
  G.invertLook = !G.invertLook;
  localStorage.setItem('mc.invertLook', G.invertLook ? '1' : '0');
  syncInvertBtn();
  log(G.invertLook ? '第一人称水平视角已反转' : '第一人称水平视角已恢复正常', 'join');
});
syncInvertBtn();
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-body').forEach(b => b.classList.remove('active'));
    tab.classList.add('active');
    $('tab-' + tab.dataset.tab).classList.add('active');
  });
});

const savedSkin = localStorage.getItem('mc.skin');
if (Object.hasOwn(SKIN_NAMES, savedSkin)) G.skin = savedSkin;
setupSkinList($('login-skins'));
setupSkinList($('game-skins'));
updateSkinButton();
const query = new URLSearchParams(location.search);
$('name-input').value = query.get('name') || localStorage.getItem('mc_name') || randomName();
if (['red', 'blue'].includes(query.get('team'))) {
  G.teamChoice = query.get('team');
  document.querySelectorAll('.pick').forEach(b => b.classList.toggle('active', b.dataset.team === G.teamChoice));
}
const rejoin = sessionStorage.getItem('mc.rejoin');
if (rejoin) {
  sessionStorage.removeItem('mc.rejoin');
  const saved = JSON.parse(rejoin);
  $('name-input').value = saved.name;
  G.teamChoice = saved.team;
}
if (rejoin || query.get('auto') === '1') setTimeout(() => $('join-btn').click(), 120);
