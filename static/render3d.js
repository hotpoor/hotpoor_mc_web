// Three.js voxel renderer. Same interface as render2d.js so main.js can
// transparently fall back if WebGL / the local three.js module is unavailable.
import * as THREE from './vendor/three.module.js';

import { makeWeapon, poseBow, voxelMaterial } from './voxel-art.js?v=31';

import { makeSkin, SKIN_NAMES } from './player-skins.js?v=22';

const TEAM_HEX = { red: 0xef4f4f, blue: 0x4c86f0 };
const ARC = Math.PI * 65 / 180;

function labelSprite(text, color, width = 512, height = 128, fontSize = 46) {
  const cv = document.createElement('canvas');
  cv.width = width; cv.height = height;
  const ctx = cv.getContext('2d');
  ctx.fillStyle = 'rgba(18,24,18,0.72)';
  ctx.fillRect(0, 12, width, height - 24);
  ctx.strokeStyle = color;
  ctx.lineWidth = 6;
  ctx.strokeRect(3, 15, width - 6, height - 30);
  ctx.font = `900 ${fontSize}px "Microsoft YaHei", sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = '#ffffff';
  ctx.shadowColor = '#000'; ctx.shadowBlur = 8;
  ctx.fillText(text, width / 2, height / 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthTest: false,
  }));
  sprite.renderOrder = 5;
  return sprite;
}

function box(w, h, d, color, y = 0, basic = false) {
  const Mat = basic ? THREE.MeshBasicMaterial : THREE.MeshLambertMaterial;
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), new Mat({ color }));
  m.position.y = y;
  return m;
}

export class Renderer3D {
  constructor(canvas, world) {
    this.canvas = canvas;
    this.world = world;
    this.zoom = 1;
    this.time = 0;
    this.meshes = new Map();
    this.pools = [];
    this.beacons = [];
    this.particles = [];
    this.is2D = false;

    // Camera modes: 'third' = fixed 45-degree follow, 'first' = eye-level
    // free-look with a viewmodel sword. Only 'first' uses yaw/pitch.
    this.viewMode = 'third';
    this.yaw = 0;
    this.pitch = -0.12;
    this.myId = null;
    this.swingSelf = 0;
    this.arrows = new Map();
    this.waves = [];
    this.repairs = [];
    this.objectives = new Map();
    this.recallEffects = new Map();
    this.bowKick = 0;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0xb7dcf2);
    this.scene.fog = new THREE.Fog(0xb7dcf2, 48, 105);
    this.camera = new THREE.PerspectiveCamera(54, 1, 0.1, 220);
    this.camTarget = new THREE.Vector3(0, 0, 0);
    this.raycaster = new THREE.Raycaster();
    this.groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
    this._v = new THREE.Vector3();
    this._ndc = new THREE.Vector2();

    this.scene.add(new THREE.AmbientLight(0xffffff, 1.35));
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x5b7048, 1.1));
    const sun = new THREE.DirectionalLight(0xfff2d0, 1.5);
    sun.position.set(28, 60, 20);
    this.scene.add(sun);

    this.tiles = Object.fromEntries(
      ['grass', 'dirt', 'grassSide', 'stone', 'brick', 'bark', 'rings', 'leaves']
        .map(kind => [kind, voxelMaterial(kind)]),
    );
    this.skins = Object.fromEntries(Object.keys(SKIN_NAMES).map(name => [name, makeSkin(name)]));
    this.buildViewModel();
    this.buildGround();
    this.buildWalls();
    for (const key of Object.keys(world.teams)) this.buildBase(world.teams[key]);
    for (const pool of world.pools) this.buildPool(pool);
    this.buildBlocks(world.blocks);
    this.resize();
  }

  buildViewModel() {
    const vm = new THREE.Group();
    vm.rotation.y = Math.PI;
    vm.position.set(0, -0.34, -0.43);
    vm.scale.setScalar(0.76);
    this.viewRig = this.makeArmRig(vm, 0x6ab04c, true);
    vm.visible = false;
    this.camera.add(vm);
    this.scene.add(this.camera);
    this.viewModel = vm;
  }

  makeArmRig(parent, team, overlay = false) {
    const createArm = x => {
      const pivot = new THREE.Group();
      pivot.position.x = x;
      const sleeve = box(.24, .47, .24, team, -.23, overlay);
      const hand = box(.21, .23, .22, 0xf0c49b, -.56, overlay);
      for (const mesh of [sleeve, hand]) {
        if (overlay) {
          mesh.material.depthTest = false;
          mesh.material.depthWrite = false;
          mesh.material.fog = false;
          mesh.renderOrder = 998;
        }
        pivot.add(mesh);
      }
      parent.add(pivot);
      return { pivot, sleeve, hand };
    };
    const right = createArm(-.43);
    const left = createArm(.43);
    const weapons = {};
    for (const kind of ['sword', 'bow', 'rocket', 'gun', 'axe', 'mace', 'hammer']) {
      const weapon = makeWeapon(kind, overlay);
      weapon.position.set(0, -.58, .12);
      weapon.visible = kind === 'sword';
      right.pivot.add(weapon);
      weapons[kind] = weapon;
    }
    const charge = new THREE.Mesh(new THREE.IcosahedronGeometry(.19, 1),
      new THREE.MeshBasicMaterial({ color: 0x61eaff, depthTest: !overlay, depthWrite: false }));
    charge.position.set(0, -.5, .59);
    charge.renderOrder = 999;
    parent.add(charge);
    const crystal = new THREE.Mesh(new THREE.OctahedronGeometry(.22),
      new THREE.MeshBasicMaterial({ color: 0x54ffee, depthTest: !overlay, depthWrite: !overlay, fog: !overlay }));
    crystal.position.set(0, -.60, .19);
    crystal.scale.y = 1.35;
    crystal.renderOrder = overlay ? 999 : 0;
    crystal.visible = false;
    left.pivot.add(crystal);
    const rig = { right, left, weapons, charge, crystal };
    this.applyArmSkin(rig, 'steve');
    return rig;
  }

  applyArmSkin(rig, name) {
    if (rig.skin === name) return;
    const skin = this.skins[name] || this.skins.steve;
    for (const { sleeve, hand } of [rig.left, rig.right]) {
      sleeve.material.color.setHex(0xffffff);
      hand.material.color.setHex(0xffffff);
      sleeve.material.map = skin.sleeve;
      hand.material.map = skin.hand;
      sleeve.material.needsUpdate = hand.material.needsUpdate = true;
      sleeve.scale.x = hand.scale.x = name === 'alex' ? .78 : 1;
    }
    rig.skin = name;
  }

  poseArms(rig, weapon, draw, swing, walk, recoil, carriesCrystal = false) {
    const right = rig.right.pivot;
    const left = rig.left.pivot;
    const bow = weapon === 'bow';
    this.showWeapon(rig.weapons, weapon);
    left.visible = !this.viewModel || rig !== this.viewRig || (bow && draw !== null);
    rig.charge.visible = weapon === 'beam' && draw !== null;
    if (weapon === 'beam' || weapon === 'rocket' || weapon === 'gun') {
      const pull = draw ?? 0;
      left.visible = true;
      right.rotation.set(-1.24, 0, -.57);
      left.rotation.set(-1.24, 0, .57);
      rig.charge.scale.setScalar(.3 + pull);
    } else if (bow) {
      const pull = draw ?? 0;
      right.rotation.set(-1.10 - pull * .34 + recoil * 2.6, 0, -.19 - pull * .20);
      left.rotation.set(-.65 - pull * .78, 0, draw === null ? 0 : -.48 - pull * .50);
      rig.weapons.bow.rotation.set(-right.rotation.x, 0, .32);
      poseBow(rig.weapons.bow, draw);
    } else {
      right.rotation.set(-.38 + walk * .7 - swing * 1.45, swing * .62, swing * .56);
      left.rotation.set(-walk * .7, 0, 0);
      rig.weapons.sword.rotation.set(.28, 0, -.12);
      rig.weapons.axe.rotation.set(.28, 0, -.12);
      rig.weapons.mace.rotation.set(.28, 0, -.12);
      rig.weapons.hammer.rotation.set(.28, 0, -.12);
    }
    rig.crystal.visible = carriesCrystal;
    if (carriesCrystal) {
      left.visible = true;
      left.rotation.set(-1, 0, -.10);
      rig.crystal.rotation.y = this.time * 1.8;
    }
  }

  showWeapon(weapons, kind) {
    for (const [weapon, mesh] of Object.entries(weapons)) {
      mesh.visible = weapon === kind;
    }
  }

  buildGround() {
    // A larger plain below the playable map, so the camera never shows empty
    // sky when a player stands near the edge of the arena.
    const outer = new THREE.Mesh(
      new THREE.BoxGeometry(240, 0.6, 240),
      new THREE.MeshLambertMaterial({ color: 0x5b8b47 }),
    );
    outer.position.y = -1.15;
    this.scene.add(outer);

    const size = Math.round(this.world.size);
    const ground = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 0.8, 1),
      [this.tiles.grassSide, this.tiles.grassSide, this.tiles.grass,
        this.tiles.dirt, this.tiles.grassSide, this.tiles.grassSide],
      size * size,
    );
    const dummy = new THREE.Object3D();
    const color = new THREE.Color();
    const teams = Object.values(this.world.teams);
    let i = 0;
    for (let gx = 0; gx < size; gx++) {
      for (let gz = 0; gz < size; gz++) {
        const x = gx - size / 2 + 0.5;
        const z = gz - size / 2 + 0.5;
        dummy.position.set(x, -0.4, z);
        dummy.updateMatrix();
        ground.setMatrixAt(i, dummy.matrix);
        const n = ((gx * 73 + gz * 151) % 17) / 17;
        color.setScalar(0.79 + n * 0.21);
        for (const t of teams) {
          const [x0, x1, z0, z1] = t.zone;
          if (x >= x0 && x <= x1 && z >= z0 && z <= z1) {
            color.lerp(new THREE.Color(t.color), 0.32);
          }
        }
        for (const p of this.world.pools) {
          if (Math.hypot(x - p.x, z - p.z) <= p.r + 0.8) {
            color.lerp(new THREE.Color(0x5fd6c0), 0.45);
          }
        }
        ground.setColorAt(i, color);
        i++;
      }
    }
    ground.instanceMatrix.needsUpdate = true;
    if (ground.instanceColor) ground.instanceColor.needsUpdate = true;
    this.scene.add(ground);
  }

  buildWalls() {
    const half = this.world.half;
    const mat = this.tiles.brick;
    const capMat = this.tiles.stone;
    const span = this.world.size + 1;
    const defs = [
      [0, -half - 0.5, span, 1], [0, half + 0.5, span, 1],
      [-half - 0.5, 0, 1, span], [half + 0.5, 0, 1, span],
    ];
    for (const [x, z, w, d] of defs) {
      const wall = new THREE.Mesh(this.tiledBox(w, 2.2, d), mat);
      wall.position.set(x, 1.1, z);
      this.scene.add(wall);
      const cap = new THREE.Mesh(this.tiledBox(w + 0.1, 0.25, d + 0.1), capMat);
      cap.position.set(x, 2.3, z);
      this.scene.add(cap);
    }
  }

  buildBase(team) {
    const [x0, x1, z0, z1] = team.zone;
    const cx = (x0 + x1) / 2, cz = (z0 + z1) / 2;
    const w = x1 - x0, d = z1 - z0;
    const hex = TEAM_HEX[team.key];
    const g = new THREE.Group();

    const floor = new THREE.Mesh(
      new THREE.BoxGeometry(w, 0.1, d),
      new THREE.MeshBasicMaterial({ color: hex, transparent: true, opacity: 0.3 }),
    );
    floor.position.set(cx, 0.07, cz);
    g.add(floor);

    for (const [px, pz, pw, pd] of [
      [cx, z0, w, 0.3], [cx, z1, w, 0.3], [x0, cz, 0.3, d], [x1, cz, 0.3, d],
    ]) {
      const edge = box(pw, 0.3, pd, hex, 0.15, true);
      edge.position.x = px; edge.position.z = pz;
      g.add(edge);
    }
    for (const tx of [x0 + 0.6, x1 - 0.6]) {
      for (const tz of [z0 + 0.6, z1 - 0.6]) {
        const tower = box(1.2, 3.2, 1.2, hex, 1.6);
        tower.position.x = tx; tower.position.z = tz;
        g.add(tower);
        const top = box(1.5, 0.35, 1.5, 0x2b3130, 3.35);
        top.position.x = tx; top.position.z = tz;
        g.add(top);
      }
    }

    const [sx, sz] = team.spawn;
    const pad = new THREE.Mesh(
      new THREE.CylinderGeometry(1.7, 1.9, 0.3, 8),
      new THREE.MeshBasicMaterial({ color: hex }),
    );
    pad.position.set(sx, 0.15, sz);
    g.add(pad);
    const beacon = new THREE.Mesh(
      new THREE.TorusGeometry(2.1, 0.11, 8, 32),
      new THREE.MeshBasicMaterial({ color: 0xffe9a8, transparent: true, opacity: 0.85 }),
    );
    beacon.rotation.x = -Math.PI / 2;
    beacon.position.set(sx, 0.4, sz);
    g.add(beacon);
    this.beacons.push(beacon);

    // The base centre is the respawn point, so tall props near it fill the
    // screen in first person. Mount the flag on the outer rear corner tower.
    const poleX = x0 + 0.9, poleZ = z0 + 0.9;
    const pole = box(0.18, 5.0, 0.18, 0x5b4a38, 2.5);
    pole.position.set(poleX, 2.5, poleZ);
    g.add(pole);
    const flag = box(1.9, 1.05, 0.1, hex, 4.45, true);
    flag.position.set(poleX + 1, 4.45, poleZ);
    g.add(flag);

    const label = labelSprite(team.name, team.color, 640, 128, 52);
    label.position.set(cx, 6.1, cz);
    label.scale.set(7.2, 1.45, 1);
    g.add(label);

    this.scene.add(g);
  }

  buildPool(pool) {
    const g = new THREE.Group();
    g.position.set(pool.x, 0, pool.z);
    const disc = new THREE.Mesh(
      new THREE.CylinderGeometry(pool.r, pool.r, 0.18, 32),
      new THREE.MeshBasicMaterial({ color: 0x26b8a8, transparent: true, opacity: 0.62 }),
    );
    disc.position.y = 0.06;
    g.add(disc);
    const water = new THREE.Mesh(
      new THREE.CircleGeometry(pool.r * 0.88, 32),
      new THREE.MeshBasicMaterial({ color: 0xb9fff2, transparent: true, opacity: 0.32, side: THREE.DoubleSide }),
    );
    water.rotation.x = -Math.PI / 2;
    water.position.y = 0.17;
    g.add(water);
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(pool.r, 0.12, 8, 40),
      new THREE.MeshBasicMaterial({ color: 0xd6fff6 }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.18;
    g.add(ring);
    const column = new THREE.Mesh(
      new THREE.CylinderGeometry(pool.r * 0.62, pool.r * 0.62, 2.4, 24, 1, true),
      new THREE.MeshBasicMaterial({ color: 0x7ff0dd, transparent: true, opacity: 0.13, side: THREE.DoubleSide, depthWrite: false }),
    );
    column.position.y = 1.2;
    g.add(column);

    for (let i = 0; i < 9; i++) {
      const p = new THREE.Mesh(
        new THREE.BoxGeometry(0.16, 0.16, 0.16),
        new THREE.MeshBasicMaterial({ color: 0xd7fff5, transparent: true, opacity: 0.85 }),
      );
      const a = (i / 9) * Math.PI * 2;
      const r = pool.r * (0.25 + (i % 3) * 0.22);
      p.position.set(Math.cos(a) * r, 0.4, Math.sin(a) * r);
      p.userData = { a, r, phase: i * 0.8, speed: 0.7 + (i % 4) * 0.18 };
      this.particles.push(p);
      g.add(p);
    }
    const label = labelSprite('✚ ' + pool.name, '#79f0dd', 512, 110, 42);
    label.position.set(0, 3, 0);
    label.scale.set(4.6, 1, 1);
    g.add(label);
    this.pools.push({ group: g, ring, water });
    this.scene.add(g);
  }

  tiledBox(w, h, d) {
    const geometry = new THREE.BoxGeometry(w, h, d);
    const uv = geometry.attributes.uv;
    const sizes = [[d, h], [d, h], [w, d], [w, d], [w, h], [w, h]];
    sizes.forEach(([u, v], face) => {
      for (let i = face * 4; i < face * 4 + 4; i++) {
        uv.setXY(i, uv.getX(i) * u, uv.getY(i) * v);
      }
    });
    return geometry;
  }

  buildBlocks(blocks) {
    const dummy = new THREE.Object3D();
    const groups = { stone: [], brick: [], tree: [] };
    for (const b of blocks) (groups[b.type] || groups.stone).push(b);
    const { bark, rings } = this.tiles;
    for (const [type, list] of Object.entries(groups)) {
      if (!list.length) continue;
      const mesh = new THREE.InstancedMesh(
        new THREE.BoxGeometry(1, 1, 1),
        type === 'tree' ? [bark, bark, rings, rings, bark, bark] : this.tiles[type],
        list.length,
      );
      list.forEach((b, i) => {
        const thin = type === 'tree';
        dummy.position.set(b.x, b.h / 2, b.z);
        dummy.scale.set(thin ? 0.42 : 1, b.h, thin ? 0.42 : 1);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      this.scene.add(mesh);

      if (type === 'tree') {
        const leaves = new THREE.InstancedMesh(
          this.tiledBox(1, 1, 1), this.tiles.leaves, list.length * 2,
        );
        list.forEach((b, i) => {
          dummy.position.set(b.x, b.h + 0.55, b.z);
          dummy.scale.set(1.9, 1.5, 1.9);
          dummy.updateMatrix();
          leaves.setMatrixAt(i * 2, dummy.matrix);
          dummy.position.y += 0.83;
          dummy.scale.set(1.1, 0.65, 1.1);
          dummy.updateMatrix();
          leaves.setMatrixAt(i * 2 + 1, dummy.matrix);
        });
        leaves.instanceMatrix.needsUpdate = true;
        this.scene.add(leaves);
      }
    }
  }

  createPlayer(p) {
    const g = new THREE.Group();
    const hex = TEAM_HEX[p.team] || 0xcccccc;
    const skin = this.skins[p.skin] || this.skins.steve;
    const material = map => new THREE.MeshLambertMaterial({ map });
    const body = box(.62, .8, .34, 0xffffff, .95);
    body.material = material(skin.top);
    const head = box(.54, .54, .54, 0xffffff, 1.62);
    head.material = skin.head.map(material);
    g.add(body, head);
    const legL = box(.25, .62, .27, 0xffffff, .31);
    const legR = box(.25, .62, .27, 0xffffff, .31);
    legL.material = legR.material = material(skin.legs);
    legL.position.x = -0.16; legR.position.x = 0.16;
    g.add(legL, legR);

    const shoulders = new THREE.Group();
    shoulders.position.y = 1.32;
    g.add(shoulders);
    const rig = this.makeArmRig(shoulders, hex);
    this.applyArmSkin(rig, p.skin || 'steve');

    const halo = new THREE.Mesh(
      new THREE.RingGeometry(0.58, 0.74, 24),
      new THREE.MeshBasicMaterial({ color: hex, transparent: true, opacity: 0.8, side: THREE.DoubleSide }),
    );
    halo.rotation.x = -Math.PI / 2;
    halo.position.y = 0.03;
    g.add(halo);

    const swing = new THREE.Mesh(
      new THREE.RingGeometry(0.9, this.world.rules.attack_range, 24, 1, -Math.PI / 2 - ARC / 2, ARC),
      new THREE.MeshBasicMaterial({ color: 0xfff2c4, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false }),
    );
    swing.rotation.x = -Math.PI / 2;
    swing.position.y = 0.14;
    swing.visible = false;
    g.add(swing);

    g.userData = { skin: p.skin, body, head, rig, legL, legR, swing, swingLife: 0, walk: 0 };
    this.scene.add(g);
    this.meshes.set(p.id, g);
    return g;
  }

  syncRecall(players) {
    const active = new Set();
    for (const p of players) {
      if (!p.alive || !p.recall) continue;
      active.add(p.id);
      let effect = this.recallEffects.get(p.id);
      if (!effect) {
        effect = new THREE.Group();
        for (let i = 0; i < 4; i++) {
          const ring = new THREE.Mesh(new THREE.RingGeometry(.85, 1, 44),
            new THREE.MeshBasicMaterial({ color: i === 0 ? 0xadfcff : 0x46cfff,
              side: THREE.DoubleSide, transparent: true, depthWrite: false,
              blending: THREE.AdditiveBlending }));
          ring.rotation.x = -Math.PI / 2;
          effect.add(ring);
        }
        this.scene.add(effect);
        this.recallEffects.set(p.id, effect);
      }
      effect.position.set(p.rx, p.jump || 0, p.rz);
      const elapsed = Math.max(0, 3 - p.recall);
      effect.children.forEach((ring, i) => {
        const phase = (elapsed * (i ? .83 : 1.8) + i / 4) % 1;
        ring.position.y = i ? .13 + phase * 2.65 : .05;
        ring.scale.setScalar(i ? .75 + phase * .55 : .52 + phase * 1.45);
        ring.material.opacity = (1 - phase) * (i ? .68 : .92);
      });
    }
    for (const [id, effect] of this.recallEffects) {
      if (active.has(id)) continue;
      this.scene.remove(effect);
      for (const ring of effect.children) {
        ring.geometry.dispose();
        ring.material.dispose();
      }
      this.recallEffects.delete(id);
    }
  }

  sync(players, me, dt) {
    this.time += dt;
    this.syncRecall(players);
    this.myId = me ? me.id : null;
    const first = this.viewMode === 'first' && !!me?.alive;
    const seen = new Set();
    for (const p of players) {
      seen.add(p.id);
      let g = this.meshes.get(p.id);
      if (!g) g = this.createPlayer(p);
      const avatar = g.userData;
      if (avatar.skin !== p.skin) {
        const skin = this.skins[p.skin] || this.skins.steve;
        avatar.head.material.forEach((material, i) => { material.map = skin.head[i]; });
        avatar.body.material.map = skin.top;
        avatar.legL.material.map = skin.legs;
        this.applyArmSkin(avatar.rig, p.skin || 'steve');
        avatar.skin = p.skin;
      }
      const selfHidden = first && me && p.id === me.id;
      g.visible = !!p.alive && !selfHidden;
      if (!p.alive) {
        if (avatar.deathAge === undefined) {
          avatar.deathAge = 0;
          avatar.swing.visible = false;
          this.poseArms(avatar.rig, p.weapon, null, 0, 0, 0);
        }
        avatar.deathAge += dt;
        const age = avatar.deathAge;
        const fall = Math.min(1, age / .32);
        g.rotation.order = 'YXZ';
        g.rotation.x = -Math.PI / 2 * fall * (2 - fall);
        g.position.set(p.rx, (p.jump || 0) + fall * .29, p.rz);
        g.visible = age < 1.26 && (age < .42 || Math.floor((age - .42) * 8) % 2 === 0);
        continue;
      }
      avatar.deathAge = undefined;
      g.rotation.x = 0;
      g.position.set(p.rx, p.jump || 0, p.rz);
      const target = p.yaw;
      let diff = target - g.rotation.y;
      while (diff > Math.PI) diff -= Math.PI * 2;
      while (diff < -Math.PI) diff += Math.PI * 2;
      g.rotation.y += diff * Math.min(1, dt * 14);

      const ud = g.userData;
      ud.bowKick = Math.max(0, (ud.bowKick || 0) - dt);
      ud.walk += (p.moving || 0) * dt * 11;
      const sw = Math.sin(ud.walk) * 0.48 * Math.min(1, p.moving || 0);
      ud.legL.rotation.x = sw; ud.legR.rotation.x = -sw;
      let swingPose = 0;
      if (ud.swingLife > 0) {
        ud.swingLife -= dt;
        const t = 1 - Math.max(0, ud.swingLife) / 0.24;
        swingPose = Math.sin(t * Math.PI);
        ud.swing.visible = true;
        ud.swing.material.opacity = Math.max(0, 0.6 * (1 - t));
        ud.swing.scale.setScalar(0.7 + t * 0.55);
      } else {
        ud.swing.visible = false;
      }
      this.poseArms(ud.rig, p.weapon, p.draw ?? null, swingPose, sw, ud.bowKick, p.carriesCrystal);
      if (p.invuln && !selfHidden) g.visible = Math.floor(this.time * 9) % 2 === 0;
    }
    for (const [id, g] of this.meshes) {
      if (!seen.has(id)) { this.scene.remove(g); this.meshes.delete(id); }
    }

    for (const b of this.beacons) b.rotation.z = this.time * 0.8;
    for (const p of this.particles) {
      const u = p.userData;
      p.position.y = 0.5 + Math.sin(this.time * u.speed + u.phase) * 0.75 + 0.8;
      p.rotation.y = this.time * u.speed;
      p.position.x = Math.cos(u.a + this.time * 0.25) * u.r;
      p.position.z = Math.sin(u.a + this.time * 0.25) * u.r;
    }
    for (const pool of this.pools) {
      pool.ring.rotation.z = this.time * 0.35;
      pool.water.material.opacity = 0.24 + Math.sin(this.time * 2) * 0.08;
    }

    if (me) {
      const limit = this.world.half - 14;
      const clamp = (v) => Math.max(-limit, Math.min(limit, v));
      this.camTarget.x += (clamp(me.rx) - this.camTarget.x) * Math.min(1, dt * 6);
      this.camTarget.z += (clamp(me.rz) - this.camTarget.z) * Math.min(1, dt * 6);
      if (first) {
        const eye = 1.68 + (me.jump || 0);
        const cp = Math.cos(this.pitch);
        this.camera.position.set(me.rx, eye, me.rz);
        this.camera.lookAt(
          me.rx + Math.sin(this.yaw) * cp,
          eye + Math.sin(this.pitch),
          me.rz + Math.cos(this.yaw) * cp,
        );
        this.camTarget.set(me.rx, 0, me.rz);
      } else {
        const dist = 20 * this.zoom;
        this.camera.position.set(this.camTarget.x, 0.8 + dist, this.camTarget.z + dist);
        this.camera.lookAt(this.camTarget.x, 0.8, this.camTarget.z);
      }
    }

    this.viewModel.visible = first && !!me?.alive;
    for (const [id, arrow] of this.arrows) {
      arrow.age += dt;
      if (arrow.stopped && arrow.age > .25) {
        this.scene.remove(arrow.mesh);
        for (const part of arrow.mesh.children) {
          part.geometry.dispose();
          part.material.dispose();
        }
        this.arrows.delete(id);
      } else if (!arrow.stopped) {
        const t = Math.min(.05, arrow.age);
        arrow.mesh.position.copy(arrow.position).addScaledVector(arrow.velocity, t);
        if (!arrow.rocket) arrow.mesh.position.y -= 9 * t * t;
        const direction = arrow.velocity.clone();
        if (!arrow.rocket) direction.y -= 18 * t;
        arrow.mesh.quaternion.setFromUnitVectors(THREE.Object3D.DEFAULT_UP, direction.normalize());
      }
    }
    this.waves = this.waves.filter(wave => {
      wave.age += dt;
      const t = Math.min(1, wave.age / (wave.slam ? .48 : wave.gun ? .10 : .34));
      if (wave.beam) {
        wave.mesh.position.lerpVectors(wave.start, wave.end, t / 2);
        wave.mesh.scale.set(1, wave.length * t, 1);
      } else {
        wave.mesh.position.lerpVectors(wave.start, wave.end, t);
        wave.mesh.scale.setScalar(wave.slam ? .35 + t * 3.25 : wave.blast ? .8 + t * 5 : .75 + t * .7);
      }
      wave.mesh.material.opacity = 1 - t;
      if (t < 1) return true;
      this.scene.remove(wave.mesh);
      wave.mesh.geometry.dispose();
      wave.mesh.material.dispose();
      return false;
    });
    this.repairs = this.repairs.filter(effect => {
      effect.age += dt;
      const travel = Math.min(1, effect.age / .38);
      effect.orb.position.lerpVectors(effect.start, effect.end, travel);
      effect.orb.position.y += Math.sin(travel * Math.PI) * .65;
      effect.orb.visible = travel < 1;
      const pulse = Math.max(0, (effect.age - .38) / .9);
      effect.ring.visible = effect.label.visible = travel === 1;
      effect.ring.scale.setScalar(.45 + pulse * 2.2);
      effect.ring.material.opacity = Math.max(0, 1 - pulse);
      effect.label.position.y = 2.85 + pulse * .65;
      effect.label.material.opacity = Math.min(1, Math.max(0, (1 - pulse) * 2));
      if (pulse < 1) return true;
      for (const mesh of [effect.orb, effect.ring, effect.label]) {
        this.scene.remove(mesh);
        if (mesh !== effect.label) mesh.geometry.dispose();
        mesh.material.map?.dispose();
        mesh.material.dispose();
      }
      return false;
    });
    this.swingSelf = Math.max(0, this.swingSelf - dt);
    this.bowKick = Math.max(0, this.bowKick - dt);
    if (this.viewModel.visible) {
      const swing = Math.sin(Math.PI * this.swingSelf / .24);
      this.applyArmSkin(this.viewRig, me.skin || 'steve');
      this.poseArms(this.viewRig, me.weapon, me.draw ?? null, swing, 0, this.bowKick, me.carriesCrystal);
    }
  }

  syncObjectives(objects) {
    const active = new Set(objects.map(obj => obj.id));
    for (const [id, mesh] of this.objectives) {
      if (active.has(id)) continue;
      this.scene.remove(mesh);
      for (const child of mesh.children) {
        child.geometry?.dispose();
        child.material.map?.dispose();
        child.material.dispose();
      }
      this.objectives.delete(id);
    }
    for (const obj of objects) {
      let mesh = this.objectives.get(obj.id);
      if (!mesh) {
        const crystal = obj.kind === 'crystal';
        mesh = new THREE.Group();
        if (crystal || obj.kind === 'dummy') {
          if (crystal) {
            const gem = new THREE.Mesh(new THREE.OctahedronGeometry(.67),
              new THREE.MeshLambertMaterial({ color: TEAM_HEX[obj.team], emissive: TEAM_HEX[obj.team], emissiveIntensity: .35 }));
            gem.position.y = 1.1;
            gem.scale.y = 1.35;
            mesh.add(gem, box(1.1, .24, 1.1, 0x3b3849, .12));
          } else {
            mesh.add(box(.54, .52, .49, 0xc6a45f, 1.65),
              box(.63, .68, .37, 0x9e713e, 1.06),
              box(.92, .16, .23, 0xb88a54, 1.19),
              box(.15, .75, .15, 0x795a3c, .42),
              box(.68, .15, .63, 0x5e4c3d, .075));
          }
          const canvas = document.createElement('canvas');
          canvas.width = 192;
          canvas.height = 32;
          const map = new THREE.CanvasTexture(canvas);
          map.colorSpace = THREE.SRGBColorSpace;
          const bar = new THREE.Sprite(new THREE.SpriteMaterial({ map, depthWrite: false }));
          bar.position.y = 2.32;
          bar.scale.set(2.4, .4, 1);
          mesh.add(bar);
          mesh.userData.healthBar = { canvas, map };

        } else if (obj.kind === 'weapon_pickup') {
          const model = obj.weapon === 'beam'
            ? new THREE.Mesh(new THREE.OctahedronGeometry(.28), new THREE.MeshBasicMaterial({ color: 0x66ddff }))
            : makeWeapon(obj.weapon);
          model.position.y = .8;
          mesh.add(model);
          const label = labelSprite(obj.text + ' · E', '#ffe78b', 320, 100, 40);
          label.position.y = 2;
          label.scale.set(2.4, .75, 1);
          label.material.depthTest = true;
          mesh.add(label);
        } else if (obj.kind === 'syllable' || obj.kind === 'forge') {
          const forge = obj.kind === 'forge';
          const ring = new THREE.Mesh(new THREE.RingGeometry(forge ? 1.6 : .23, forge ? 2 : .35, 36),
            new THREE.MeshBasicMaterial({ color: forge ? 0xb885ff : 0xffdd75, side: THREE.DoubleSide }));
          ring.rotation.x = -Math.PI / 2;
          ring.position.y = .04;
          const label = labelSprite(forge ? '拼音法阵 · E' : obj.text, forge ? '#b885ff' : '#ffdd75', 448, 120, 49);
          label.scale.set(forge ? 3.4 : 2.75, .7, 1);
          label.position.y = forge ? 1.3 : .8;
          label.material.depthTest = true;
          mesh.add(ring, label);
        } else if (obj.kind === 'ore' || obj.kind === 'dropped_crystal') {
          const gem = new THREE.Mesh(new THREE.OctahedronGeometry(.42),
            new THREE.MeshLambertMaterial({ color: 0x54ffee, emissive: 0x078c81, emissiveIntensity: .7 }));
          gem.position.y = .68;
          gem.scale.y = 1.35;
          mesh.add(gem);
          if (obj.kind === 'ore') mesh.add(box(.8, .13, .8, 0x2f5558, .07));
        } else {
          mesh.add(box(.85, .85, .85, 0xb8372e, .43),
            box(.87, .22, .87, 0xf1dcb1, .43), box(.09, .23, .09, 0xffaf38, .95));
        }
        mesh.position.set(obj.x, obj.y || 0, obj.z);
        this.scene.add(mesh);
        this.objectives.set(obj.id, mesh);
      }
      mesh.visible = obj.kind === 'ore' || obj.hp > 0;
      if (obj.kind === 'weapon_pickup') mesh.children[0].rotation.y = this.time * .55;
      if (obj.kind === 'ore') {
        mesh.children[0].visible = obj.hp > 0;
        const text = obj.hp ? '' : obj.cooldown > 0 ? obj.cooldown + ' 秒刷新' : '水晶已搬走';
        if (mesh.userData.statusText !== text) {
          const old = mesh.userData.status;
          if (old) {
            mesh.remove(old);
            old.material.map.dispose();
            old.material.dispose();
          }
          const status = text ? labelSprite(text, '#70e5db', 320, 100, 42) : null;
          if (status) {
            status.position.y = 1.12;
            status.scale.set(2.45, .77, 1);
            status.material.depthTest = true;
            status.material.depthWrite = false;
            mesh.add(status);
          }
          mesh.userData.status = status;
          mesh.userData.statusText = text;
        }
      }
      if (obj.kind === 'ore' || obj.kind === 'dropped_crystal') mesh.children[0].rotation.y = this.time * 1.6;
      if (mesh.userData.healthBar) {
        if (obj.kind === 'crystal') mesh.children[0].rotation.y = this.time * 1.3;
        const bar = mesh.userData.healthBar;
        if (bar.hp !== obj.hp) {
          const ctx = bar.canvas.getContext('2d');
          ctx.fillStyle = '#171b28';
          ctx.fillRect(0, 0, 192, 32);
          ctx.fillStyle = obj.kind === 'dummy' ? '#95733e' : this.world.teams[obj.team].color;
          ctx.fillRect(3, 3, 186 * obj.hp / obj.max_hp, 26);
          ctx.fillStyle = '#ffffff';
          ctx.textAlign = 'center';
          ctx.textBaseline = 'middle';
          ctx.font = 'bold 20px sans-serif';
          ctx.fillText(obj.hp + ' / ' + obj.max_hp, 96, 17);
          bar.map.needsUpdate = true;
          bar.hp = obj.hp;
        }
      }
    }
  }

  spawnSlam(event) {
    const position = new THREE.Vector3(event.x, event.y + .07, event.z);
    const mesh = new THREE.Mesh(new THREE.RingGeometry(.77, 1, 48),
      new THREE.MeshBasicMaterial({ color: 0xffce80, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.copy(position);
    this.scene.add(mesh);
    this.waves.push({ mesh, start: position, end: position, age: 0, slam: true });
  }

  spawnRepair(event) {
    const start = new THREE.Vector3().fromArray(event.start);
    const end = new THREE.Vector3().fromArray(event.end);
    const orb = new THREE.Mesh(new THREE.OctahedronGeometry(.23), new THREE.MeshBasicMaterial({ color: 0x60ffda }));
    orb.position.copy(start);
    const ring = new THREE.Mesh(new THREE.RingGeometry(.85, 1, 40),
      new THREE.MeshBasicMaterial({ color: 0x60ffda, side: THREE.DoubleSide, transparent: true, depthWrite: false }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.set(end.x, .06, end.z);
    const label = labelSprite('+' + event.amount, '#60ffda', 192, 80, 48);
    label.position.set(end.x, 2.85, end.z);
    label.scale.set(1.65, .69, 1);
    ring.visible = label.visible = false;
    this.scene.add(orb, ring, label);
    this.repairs.push({ start, end, orb, ring, label, age: 0 });
  }

  spawnWave(event) {
    const mesh = new THREE.Mesh(event.gun ? new THREE.CylinderGeometry(.023, .023, 1, 6) : event.beam ? new THREE.CylinderGeometry(.45, .3, 1, 12)
      : new THREE.IcosahedronGeometry(.58, 1),
      new THREE.MeshBasicMaterial({ color: event.gun ? 0xffdb81 : event.blast ? 0xff8b39 : event.beam ? 0x91eaff : 0x43f4ff, transparent: true, depthWrite: false,
        blending: THREE.AdditiveBlending }));
    const start = new THREE.Vector3().fromArray(event.start);
    const end = new THREE.Vector3().fromArray(event.end);
    mesh.position.copy(start);
    this.scene.add(mesh);
    const direction = end.clone().sub(start);
    if (event.beam || event.gun) mesh.quaternion.setFromUnitVectors(THREE.Object3D.DEFAULT_UP, direction.clone().normalize());
    this.waves.push({ mesh, start, end, age: 0, beam: event.beam || event.gun, gun: event.gun, blast: event.blast, length: direction.length() });
  }

  spawnArrow(event) {
    const shooter = this.meshes.get(event.id);
    if (shooter) shooter.userData.bowKick = 0.18;
    if (event.id === this.myId) this.bowKick = 0.18;
  }

  updateArrow(id, position, velocity, rocket) {
    let arrow = this.arrows.get(id);
    if (!arrow) {
      arrow = { rocket, mesh: makeWeapon(rocket ? 'missile' : 'arrow'), position: new THREE.Vector3(), velocity: new THREE.Vector3() };
      this.scene.add(arrow.mesh);
      this.arrows.set(id, arrow);
    }
    arrow.position.fromArray(position);
    arrow.velocity.fromArray(velocity);
    arrow.mesh.position.copy(arrow.position);
    arrow.mesh.quaternion.setFromUnitVectors(THREE.Object3D.DEFAULT_UP, arrow.velocity.clone().normalize());
    arrow.age = 0;
    return arrow;
  }

  stopArrow(event) {
    this.updateArrow(event.arrow, event.position, event.velocity, event.rocket).stopped = true;
  }

  syncArrows(states) {
    const active = new Set();
    for (const state of states) {
      active.add(state.id);
      this.updateArrow(state.id, state.position, state.velocity, state.rocket).stopped = false;
    }
    for (const [id, arrow] of this.arrows) {
      if (!active.has(id)) arrow.stopped = true;
    }
  }

  spawnSwing(id) {
    const g = this.meshes.get(id);
    if (g) g.userData.swingLife = 0.24;
    if (id === this.myId) this.swingSelf = 0.24;
  }

  draw() { this.renderer.render(this.scene, this.camera); }

  resize() {
    const w = this.canvas.clientWidth || window.innerWidth;
    const h = this.canvas.clientHeight || window.innerHeight;
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(w, h, false);
  }

  setZoom(delta) {
    if (this.viewMode === 'first') return;
    this.zoom = Math.max(0.62, Math.min(1.65, this.zoom + delta));
  }

  getViewMode() { return this.viewMode; }
  getYaw() { return this.yaw; }
  getPitch() { return this.pitch; }
  setYaw(yaw) { this.yaw = yaw; }

  setViewMode(mode, team) {
    this.viewMode = mode === 'first' ? 'first' : 'third';
    const first = this.viewMode === 'first';
    this.viewModel.visible = first;
    this.camera.fov = first ? 76 : 54;
    this.camera.updateProjectionMatrix();

  }

  applyLook(dx, dy) {
    if (this.viewMode !== 'first') return;
    // The camera looks along (sin(yaw), cos(yaw)), so its screen-right vector
    // is (-cos(yaw), sin(yaw)). Turning right therefore DECREASES yaw.
    this.yaw -= dx * 0.0026;
    this.pitch = Math.max(-1.15, Math.min(1.15, this.pitch - dy * 0.0022));
  }

  screenToGround(clientX, clientY) {
    const r = this.canvas.getBoundingClientRect();
    this._ndc.set(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1);
    this.raycaster.setFromCamera(this._ndc, this.camera);
    const out = new THREE.Vector3();
    return this.raycaster.ray.intersectPlane(this.groundPlane, out)
      ? { x: out.x, z: out.z } : null;
  }

  project(x, y, z) {
    const v = this._v.set(x, y, z).project(this.camera);
    const r = this.canvas.getBoundingClientRect();
    return {
      x: r.left + (v.x * 0.5 + 0.5) * r.width,
      y: r.top + (-v.y * 0.5 + 0.5) * r.height,
      visible: v.z > -1 && v.z < 1,
    };
  }
}
