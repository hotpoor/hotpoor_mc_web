// Zero-dependency top-down fallback renderer, used only if WebGL / three.js
// cannot start. Implements the exact same interface as Renderer3D.
const TEAM_CSS = { red: '#ef4f4f', blue: '#4c86f0' };
const BLOCK_CSS = { stone: '#8d9497', brick: '#b1684a', tree: '#6b4a2f' };

export class Renderer2D {
  constructor(canvas, world) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.world = world;
    this.zoom = 1;
    this.is2D = true;
    this.viewMode = 'third';
    this.players = [];
    this.me = null;
    this.time = 0;
    this.swings = [];
    this.center = { x: 0, z: 0 };
    this.resize();
  }

  get scale() { return Math.min(this.w, this.h) / 46 / this.zoom; }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.w = this.canvas.clientWidth || window.innerWidth;
    this.h = this.canvas.clientHeight || window.innerHeight;
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  setZoom(delta) { this.zoom = Math.max(0.62, Math.min(1.65, this.zoom + delta)); }

  sync(players, me, dt) {
    this.players = players;
    this.me = me;
    this.time += dt;
    const k = Math.min(1, dt * 6);
    this.center.x += ((me ? me.rx : 0) - this.center.x) * k;
    this.center.z += ((me ? me.rz : 0) - this.center.z) * k;
    this.swings = this.swings.filter(s => (s.life -= dt) > 0);
  }

  spawnSwing(id) { this.swings.push({ id, life: 0.24 }); }

  // The 2D fallback is always top-down; keep the renderer API compatible.
  getViewMode() { return 'third'; }
  setViewMode() {}
  setYaw() {}
  getYaw() { return 0; }
  applyLook() {}

  toScreen(x, z) {
    const s = this.scale;
    return { x: this.w / 2 + (x - this.center.x) * s,
             y: this.h / 2 + (z - this.center.z) * s };
  }

  screenToGround(clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    const s = this.scale;
    return {
      x: this.center.x + (clientX - r.left - this.w / 2) / s,
      z: this.center.z + (clientY - r.top - this.h / 2) / s,
    };
  }

  syncObjectives(objects) {
    this.oreSites = objects.filter(obj => ['ore', 'syllable', 'forge', 'dummy'].includes(obj.kind));
  }

  project(x, y, z) {
    const p = this.toScreen(x, z);
    const r = this.canvas.getBoundingClientRect();
    return { x: r.left + p.x, y: r.top + p.y - y * this.scale * 0.45, visible: true };
  }

  draw() {
    const ctx = this.ctx, s = this.scale, w = this.w, h = this.h;
    ctx.fillStyle = '#4f8541';
    ctx.fillRect(0, 0, w, h);
    const o = this.toScreen(0, 0);
    ctx.strokeStyle = 'rgba(255,255,255,0.055)';
    ctx.lineWidth = 1;
    for (let i = -32; i <= 32; i += 2) {
      ctx.beginPath(); ctx.moveTo(o.x + i * s, 0); ctx.lineTo(o.x + i * s, h); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(0, o.y + i * s); ctx.lineTo(w, o.y + i * s); ctx.stroke();
    }

    const a = this.toScreen(-32, -32), b = this.toScreen(32, 32);
    ctx.fillStyle = '#3e6b34';
    ctx.fillRect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.strokeStyle = '#6b716d'; ctx.lineWidth = 7;
    ctx.strokeRect(a.x, a.y, b.x - a.x, b.y - a.y);

    for (const t of Object.values(this.world.teams)) {
      const [x0, x1, z0, z1] = t.zone;
      const p0 = this.toScreen(x0, z0), p1 = this.toScreen(x1, z1);
      ctx.fillStyle = TEAM_CSS[t.key] + '55';
      ctx.fillRect(p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
      ctx.strokeStyle = TEAM_CSS[t.key]; ctx.lineWidth = 3;
      ctx.strokeRect(p0.x, p0.y, p1.x - p0.x, p1.y - p0.y);
      const sp = this.toScreen(t.spawn[0], t.spawn[1]);
      ctx.beginPath(); ctx.arc(sp.x, sp.y, 1.6 * s, 0, Math.PI * 2);
      ctx.fillStyle = TEAM_CSS[t.key]; ctx.fill();
      ctx.fillStyle = '#fff'; ctx.font = '700 12px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText(t.name, (p0.x + p1.x) / 2, p0.y - 6);
    }

    for (const pool of this.world.pools) {
      const p = this.toScreen(pool.x, pool.z);
      const pulse = 1 + Math.sin(this.time * 2) * 0.05;
      ctx.beginPath(); ctx.arc(p.x, p.y, pool.r * s * pulse, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(70,220,200,0.45)'; ctx.fill();
      ctx.strokeStyle = '#bafff2'; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = '#d9fff7'; ctx.font = '600 10px sans-serif'; ctx.textAlign = 'center';
      ctx.fillText('✚ ' + pool.name, p.x, p.y + 3);
    }

    for (const b of this.world.blocks) {
      const p = this.toScreen(b.x, b.z);
      const half = 0.5 * s;
      ctx.fillStyle = BLOCK_CSS[b.type] || BLOCK_CSS.stone;
      ctx.fillRect(p.x - half, p.y - half, s, s);
      ctx.fillStyle = 'rgba(255,255,255,0.16)';
      ctx.fillRect(p.x - half, p.y - half, s, s * 0.35);
      ctx.strokeStyle = 'rgba(0,0,0,0.35)'; ctx.lineWidth = 1;
      ctx.strokeRect(p.x - half, p.y - half, s, s);
    }

    for (const ore of this.oreSites || []) {
      const p = this.toScreen(ore.x, ore.z);
      if (ore.kind !== 'ore') {
        if (ore.hp) {
          ctx.font = '600 11px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillStyle = ore.kind === 'forge' ? '#d5adff' : '#ffdd75';
          ctx.fillText(ore.text || (ore.kind === 'dummy' ? '假人 ' + ore.hp + '/' + ore.max_hp : '拼音法阵'), p.x, p.y);
        }
        continue;
      }
      ctx.fillStyle = ore.hp ? '#54ffee' : '#41747a';
      ctx.fillRect(p.x - 4, p.y - 4, 8, 8);
      if (!ore.hp) {
        ctx.font = '600 11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillStyle = '#d5fffb';
        ctx.fillText(ore.cooldown > 0 ? ore.cooldown + ' 秒刷新' : '水晶已搬走', p.x, p.y - 7);
      }
    }

    for (const sw of this.swings) {
      const p = this.players.find(pl => pl.id === sw.id);
      if (!p) continue;
      const c = this.toScreen(p.rx, p.rz);
      const arc = Math.PI * 65 / 180;
      const center = Math.PI / 2 - p.yaw;
      ctx.beginPath();
      ctx.moveTo(c.x, c.y);
      ctx.arc(c.x, c.y, this.world.rules.attack_range * s,
              center - arc / 2, center + arc / 2);
      ctx.closePath();
      ctx.fillStyle = `rgba(255,242,196,${0.5 * (sw.life / 0.24)})`;
      ctx.fill();
    }

    for (const p of this.players) {
      if (!p.alive) continue;
      if (p.invuln && Math.floor(this.time * 9) % 2 === 0) continue;
      const c = this.toScreen(p.rx, p.rz);
      const r = 0.45 * s;
      ctx.fillStyle = TEAM_CSS[p.team] || '#ccc';
      ctx.fillRect(c.x - r, c.y - r, r * 2, r * 2);
      ctx.strokeStyle = p.id === (this.me && this.me.id) ? '#fff' : '#17201a';
      ctx.lineWidth = p.id === (this.me && this.me.id) ? 3 : 2;
      ctx.strokeRect(c.x - r, c.y - r, r * 2, r * 2);
      ctx.save();
      ctx.translate(c.x, c.y);
      ctx.rotate(Math.PI - p.yaw);
      ctx.beginPath();
      ctx.moveTo(0, -r - 7); ctx.lineTo(-5, -r + 1); ctx.lineTo(5, -r + 1);
      ctx.closePath(); ctx.fillStyle = '#fff8d0'; ctx.fill();
      ctx.restore();
      ctx.fillStyle = 'rgba(0,0,0,.6)';
      ctx.fillRect(c.x - r, c.y - r - 7, r * 2, 4);
      ctx.fillStyle = '#7bdc6a';
      ctx.fillRect(c.x - r, c.y - r - 7, r * 2 * (p.hp / 100), 4);
    }
  }
}
