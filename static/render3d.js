// Three.js voxel renderer. Same interface as render2d.js so main.js can
// transparently fall back if WebGL / the local three.js module is unavailable.
import * as THREE from './vendor/three.module.js';
import { CrowdRenderer } from './crowd-renderer.js?v=56';
import { buildOpenWorldArt } from './open-world-art.js?v=55';

import { makeWeapon, poseBow, voxelMaterial } from './voxel-art.js?v=60';

import { makeSkin, SKIN_NAMES } from './player-skins.js?v=49';

const MELEE_WEAPONS = ['sword','axe','mace','hammer','dual','spear','blade','halberd','silver_spear'];
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
    this.hits = [];
    this.objectives = new Map();

    this.recallEffects = new Map();
    this.bowKick = 0;

    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.info.autoReset=false;
    this.maxDpr=Math.min(window.devicePixelRatio||1,1.5);
    this.renderer.setPixelRatio(this.maxDpr);
    this.qualityWindow={time:performance.now(),frames:0};
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.scene = new THREE.Scene();
    this.crowd = new CrowdRenderer(this.scene);
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
    for (const light of this.scene.children.filter(object => object.isLight)) light.layers.enable(1);
    this.buildGround();
    this.buildWalls();
    for (const key of Object.keys(world.teams)) this.buildBase(world.teams[key]);
    for (const pool of world.pools) this.buildPool(pool);
    this.buildBlocks(world.blocks);
    this.cityBarriers = new Map();
    if(world.mode==='open') { buildOpenWorldArt(this,labelSprite,box,THREE); this.scene.fog.near=70; this.scene.fog.far=180; }
    else { this.buildCities(); this.buildRoadside(); }
    this.resize();
    const owner=this;
    window.__THREE_GAME_DIAGNOSTICS__={get render(){return {...owner.renderer.info.render}},get memory(){return {...owner.renderer.info.memory}},get dpr(){return owner.renderer.getPixelRatio()},get objectiveMeshes(){return owner.objectives.size},get crowdActors(){return owner.crowd.count||0}};
  }

  buildViewModel() {
    const vm = new THREE.Group();
    vm.rotation.y = Math.PI;
    vm.position.set(0, -0.26, -0.50);
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
      const armor = box(.29, .24, .29, 0xd9e0e7, -.52, overlay);
      armor.visible = false; armor.material.fog = !overlay; pivot.add(armor);
      parent.add(pivot);
      return { pivot, sleeve, hand, armor };
    };
    const right = createArm(-.43);
    const left = createArm(.43);
    const weapons = {};
    for (const kind of ['sword', 'bow', 'rocket', 'gun', 'axe', 'mace', 'hammer', 'dual', 'spear', 'blade', 'halberd', 'silver_spear', 'beam']) {
      const weapon = makeWeapon(kind, overlay, false);
      if(kind==='silver_spear'&&overlay)weapon.scale.setScalar(.70);
      weapon.position.set(0, MELEE_WEAPONS.includes(kind) ? -.56 : -.58, MELEE_WEAPONS.includes(kind) ? .02 : .12);
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
    const secondSword = makeWeapon('dual', overlay, false);
    secondSword.position.set(0, -.56, .02);
    secondSword.visible = false;
    left.pivot.add(secondSword);
    const rig = { right, left, weapons, charge, crystal, secondSword };
    this.applyArmSkin(rig, 'steve');
    return rig;
  }

  applyArmArmor(rig, armor) {
    for (const arm of [rig.left, rig.right]) {
      arm.armor.visible = !!armor?.durability;
      arm.armor.material.color.setHex(armor?.kind === 'elite' ? 0xe2c87b : 0xd9e0e7);
    }
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
    rig.weapons[weapon]?.userData.loadModel?.();
    if(weapon==='dual')rig.secondSword.userData.loadModel?.();
    const right = rig.right.pivot;
    right.position.y = weapon === 'silver_spear' ? (rig === this.viewRig ? .10 : .05) : 0;
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
      if (weapon === 'rocket' || weapon === 'gun') {
        rig.weapons[weapon].quaternion.copy(right.quaternion).invert();
      }
    } else if (bow) {
      const pull = draw ?? 0;
      right.rotation.set(-1.10 - pull * .34 + recoil * 2.6, 0, -.19 - pull * .20);
      left.rotation.set(-.65 - pull * .78, 0, draw === null ? 0 : -.48 - pull * .50);
      rig.weapons.bow.rotation.set(-right.rotation.x, Math.PI, .32);
      poseBow(rig.weapons.bow, draw);
    } else {
      // Bend the forearm forward; the grip sits inside the palm. Counter-rotate
      // the weapon at rest so the shaft leaves the arm instead of entering it.
      right.rotation.set(-.95 + walk * .25 - swing * 1.15, swing * .45, -.08 + swing * .5);
      left.rotation.set(-walk * .7, 0, 0);
      for(const kind of MELEE_WEAPONS)rig.weapons[kind].rotation.set(.95,0,-.08);
    }
    rig.secondSword.visible = weapon === 'dual' && !carriesCrystal;
    if (rig.secondSword.visible) {
      left.visible = true;
      left.rotation.x = -.95 - swing;
      rig.secondSword.rotation.set(.95,0,.08);
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
      new THREE.BoxGeometry(this.world.size + 80, 0.6, this.world.size + 80),
      new THREE.MeshLambertMaterial({ color: 0x5b8b47 }),
    );
    outer.position.y = -1.15;
    this.scene.add(outer);

    const size = this.world.size;
    const geometry = new THREE.PlaneGeometry(size,size).rotateX(-Math.PI/2);
    const uv=geometry.attributes.uv;
    for(let i=0;i<uv.count;i++)uv.setXY(i,uv.getX(i)*size,uv.getY(i)*size);
    const material=this.tiles.grass.clone();material.color.setScalar(.89);
    this.scene.add(new THREE.Mesh(geometry,material));
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

  buildCities() {
    for (const [index, city] of (this.world.cities || []).entries()) {
      const g = new THREE.Group();
      g.position.set(city.x, 0, city.z);
      // Roads extend from the old battlefield through the four city gates.
      const prev = this.world.cities[index - 1] || { x: 0, z: 0 };
      const road = box(Math.abs(city.x - prev.x) + 5, .06, Math.abs(city.z - prev.z) + 5, 0xb49d77, .015);
      road.position.set((city.x + prev.x) / 2, .015, (city.z + prev.z) / 2);
      this.scene.add(road);
      for (const [w, d] of [[34, 5], [5, 34]]) g.add(box(w, .08, d, 0xc2aa80, .04));
      for (const x of [-18, 18]) for (const z of [-18, 18]) {
        const tower = box(3, 6, 3, 0x66666a, 3);
        tower.position.set(x, 3, z);
        const roof = box(4, .6, 4, 0x443e40, 6.25);
        roof.position.set(x, 6.25, z);
        g.add(tower, roof);
      }
      for (const side of city.gates) {
        const x = side === 'east' ? 18 : side === 'west' ? -18 : 0;
        const z = side === 'south' ? 18 : side === 'north' ? -18 : 0;
        const lintel = box(x ? 1.3 : 7, .75, z ? 1.3 : 7, 0x6e4a31, 4.5);
        lintel.position.set(x, 4.5, z); g.add(lintel);
        const name = labelSprite(city.chapter + ' · ' + city.name, '#ffeaa0', 640, 120, 46);
        name.scale.set(8, 1.5, 1); name.position.set(x, 5.6, z);
        name.material.depthTest = true; g.add(name);
      }
      {
        const inner = labelSprite('内城 · ' + city.bosses.join(' / '), '#ffcf66', 640, 100, 40);
        inner.position.set(0, 4.2, 8);
        inner.scale.set(7, 1.1, 1);
        inner.material.depthTest = true;
        g.add(inner);
      }
      const barriers = new THREE.Group();
      for (const [x, z, w, d] of [[0, -18, 7, .15], [0, 18, 7, .15], [-18, 0, .15, 7], [18, 0, .15, 7]]) {
        const seal = box(w, 4, d, 0x8d7fa7, 2);
        seal.position.x = x; seal.position.z = z;
        seal.material.transparent = true; seal.material.opacity = .5;
        barriers.add(seal);
      }
      g.add(barriers); this.cityBarriers.set(city.id, barriers);
      this.scene.add(g);
    }
    const sign = labelSprite('↑ 第一城 · 黄巾起义城（北）', '#ffe8a0', 640, 110, 42);
    sign.position.set(0, 3.2, -29);
    sign.scale.set(7, 1.2, 1);
    this.scene.add(sign);
  }

  buildRoadside() {
    for (const moat of this.world.moats || []) {
      const w = moat.x1 - moat.x0, d = moat.z1 - moat.z0;
      const x = (moat.x0 + moat.x1) / 2, z = (moat.z0 + moat.z1) / 2;
      const water = new THREE.Mesh(new THREE.PlaneGeometry(w, d).rotateX(-Math.PI / 2),
        new THREE.MeshLambertMaterial({ color: 0x267f9f, emissive: 0x103b4a, emissiveIntensity: .3 }));
      water.position.set(x, .045, z); this.scene.add(water);
      for (const side of [-1, 1]) {
        const rail = box(w > d ? w : .14, .7, d > w ? d : .14, 0x87765b, .35);
        rail.position.set(x + (d > w ? side * w / 2 : 0), .35, z + (w > d ? side * d / 2 : 0));
        this.scene.add(rail);
      }
    }
    for (const village of this.world.villages || []) {
      const floor = box(village.axis === 'x' ? 15 : 17, .04, village.axis === 'z' ? 15 : 17, 0xb8a47c, .02);
      floor.position.set(village.x, .02, village.z); this.scene.add(floor);
      for (const side of [-1, 1]) {
        const roof = new THREE.Mesh(new THREE.ConeGeometry(2.6, 1.5, 4), new THREE.MeshLambertMaterial({ color: 0x6d4435 }));
        roof.rotation.y = Math.PI / 4;
        roof.position.set(village.x + (village.axis === 'z' ? side * 6 : 4), 2.85,
          village.z + (village.axis === 'x' ? side * 6 : 4));
        this.scene.add(roof);
      }
      const name = labelSprite(village.name + ' · 回血 / 武器补给', '#f1e4bb', 640, 100, 38);
      name.position.set(village.x + (village.axis === 'z' ? -5 : 0), 4.2, village.z + (village.axis === 'x' ? -5 : 0));
      name.scale.set(5.5, .9, 1); name.material.depthTest = true; this.scene.add(name);
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

  buildBlocks(blocks, chunked = false) {
    if(this.world.mode==='open' && !chunked){
      const chunks=new Map();
      for(const b of blocks){const key=Math.floor(b.x/96)+','+Math.floor(b.z/96);if(!chunks.has(key))chunks.set(key,[]);chunks.get(key).push(b);}
      for(const chunk of chunks.values())this.buildBlocks(chunk,true);
      return;
    }
    const dummy = new THREE.Object3D();
    const groups = { stone: [], brick: [], tree: [], bark: [] };
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

    const armor = new THREE.Group();
    armor.add(box(.7, .62, .44, 0xd9e0e7, 1.02), box(.6, .15, .6, 0xd9e0e7, 1.94));
    armor.visible = false; g.add(armor);
    g.userData = { armor, skin: p.skin, body, head, rig, legL, legR, swing, swingLife: 0, walk: 0 };
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
    if(me)for(const [id,group] of this.openCityGroups||[]){const city=this.world.cities.find(c=>c.id===id);group.visible=Math.hypot(city.x-me.rx,city.z-me.rz)<(this.monocular?450:220);}
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
      this.applyHitFlash(g, !!p.hurt && Math.floor(this.time * 12) % 2 === 0);
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
      ud.armor.visible = !!p.armor?.durability;
      for (const part of ud.armor.children) part.material.color.setHex(p.armor?.kind === 'elite' ? 0xe2c87b : 0xd9e0e7);
      this.applyArmArmor(ud.rig, p.armor);
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
      if (!seen.has(id)) { this.scene.remove(g);const materials=new Set();g.traverse(part=>{if(!part.geometry?.userData.sharedWeapon)part.geometry?.dispose();for(const m of (Array.isArray(part.material)?part.material:[part.material]))if(m)materials.add(m)});for(const m of materials)m.dispose();this.meshes.delete(id); }
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

    this.viewModel.visible = first && !!me?.alive && !this.monocular;
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
    this.hits = this.hits.filter(hit => {
      hit.age += dt;
      for (const spark of hit.mesh.children) {
        spark.position.copy(spark.userData.velocity).multiplyScalar(hit.age);
        spark.position.y -= 2 * hit.age * hit.age;
        spark.material.opacity = Math.max(0, 1 - hit.age / .35);
      }
      if (hit.age < .35) return true;
      this.scene.remove(hit.mesh);
      for (const spark of hit.mesh.children) { spark.geometry.dispose(); spark.material.dispose(); }
      return false;
    });
    this.swingSelf = Math.max(0, this.swingSelf - dt);
    this.bowKick = Math.max(0, this.bowKick - dt);
    if (this.viewModel.visible) {
      const swing = Math.sin(Math.PI * this.swingSelf / .24);
      this.applyArmSkin(this.viewRig, me.skin || 'steve');
      this.applyArmArmor(this.viewRig, me.armor);
      this.applyHitFlash(this.viewModel, !!me.hurt && Math.floor(this.time * 12) % 2 === 0);
      this.poseArms(this.viewRig, me.weapon, me.draw ?? null, swing, 0, this.bowKick, me.carriesCrystal);
    }
  }

  disposeObjective(id, mesh) {
    this.scene.remove(mesh);
    const materials=new Set(),textures=new Set();
    mesh.traverse(part=>{part.userData.disposed=true;if(!part.isSprite&&!part.geometry?.userData.sharedWeapon)part.geometry?.dispose();
      for(const mat of (Array.isArray(part.material)?part.material:[part.material]))if(mat){materials.add(mat);if(part.isSprite&&mat.map)textures.add(mat.map);}});
    for(const texture of textures)texture.dispose();
    for(const material of materials)material.dispose();
    this.objectives.delete(id);
  }

  syncObjectives(objects, viewerName = '') {
    const actorRange=this.monocular?350:this.world.mode==='open'?90:54;
    const actors=objects.filter(o=>(o.kind==='enemy'||o.kind==='villager')&&o.hp>0&&Math.hypot(o.x-this.camTarget.x,o.z-this.camTarget.z)<actorRange);
    actors.sort((a,b)=>(Math.hypot(a.x-this.camTarget.x,a.z-this.camTarget.z)-(this.objectives.has(a.id)?.75:0))-(Math.hypot(b.x-this.camTarget.x,b.z-this.camTarget.z)-(this.objectives.has(b.id)?.75:0)));
    const detailed=new Set(actors.filter(o=>Math.hypot(o.x-this.camTarget.x,o.z-this.camTarget.z)<(this.monocular?90:22)).slice(0,16).map(o=>o.id));
    let created=0;const simple=[];
    const active = new Set(objects.map(obj => obj.id));
    for (const [id, mesh] of this.objectives) {
      if (active.has(id)) continue;
      this.disposeObjective(id, mesh);
    }
    for (const obj of objects) {
      const distance=Math.hypot(obj.x-this.camTarget.x,obj.z-this.camTarget.z);
      const range=this.world.mode==='open'?(this.monocular?350:90):(this.monocular?145:54);
      if(distance>range){const old=this.objectives.get(obj.id);if(old){if(distance>(this.world.mode==='open'?(this.monocular?400:180):(this.monocular?180:100)))this.disposeObjective(obj.id,old);else old.visible=false;}continue;}
      if (obj.kind === 'enemy' && this.cityBarriers?.has(obj.city)) this.cityBarriers.get(obj.city).visible = obj.locked;
      const actor=obj.kind==='enemy'||obj.kind==='villager';
      if(actor && obj.hp<=0){const old=this.objectives.get(obj.id);if(old)this.disposeObjective(obj.id,old);continue;}
      if(actor && (!detailed.has(obj.id)||!this.objectives.has(obj.id)&&created>=4)){
        const old=this.objectives.get(obj.id);if(old)this.disposeObjective(obj.id,old);simple.push(obj);continue;
      }
      let mesh = this.objectives.get(obj.id);
      if(mesh && mesh.userData.objectKind!==obj.kind){this.disposeObjective(obj.id,mesh);mesh=null;}
      if (!mesh) {
        if(actor)created++;
        const crystal = obj.kind === 'crystal';
        mesh = new THREE.Group();
        mesh.userData.objectKind=obj.kind;
        if (crystal || ['dummy', 'enemy', 'time_stone'].includes(obj.kind)) {
          if (crystal) {
            const gem = new THREE.Mesh(new THREE.OctahedronGeometry(.67),
              new THREE.MeshLambertMaterial({ color: TEAM_HEX[obj.team], emissive: TEAM_HEX[obj.team], emissiveIntensity: .35 }));
            gem.position.y = 1.1;
            gem.scale.y = 1.35;
            mesh.add(gem, box(1.1, .24, 1.1, 0x3b3849, .12));
          } else if (obj.kind === 'enemy') {
            const boss = obj.boss;
            const body = new THREE.Group();
            const robe = obj.color || (boss ? 0x9b7136 : 0x90734a);
            const head = box(.52, .52, .5, 0xdba77b, 1.77);
            if (boss && this.skins[obj.skin]) head.material = this.skins[obj.skin].head.map(map => new THREE.MeshLambertMaterial({ map }));
            body.add(box(.62, .72, .4, robe, 1.13), head,
              box(.57, .14, .55, 0xf5cc35, 1.97), box(.65, .12, .43, 0x4a3425, .88));
            for (const x of [-.13, .13]) {
              const eye = box(.07, .07, .02, 0x251b16, 1.82);
              eye.position.set(x, 1.82, .26); body.add(eye);
            }
            const legs = [], arms = [];
            for (const side of [-1, 1]) {
              const leg = new THREE.Group(); leg.position.set(side * .18, .8, 0);
              leg.add(box(.25, .7, .3, 0x40362c, -.35)); body.add(leg); legs.push(leg);
              const arm = new THREE.Group(); arm.position.set(side * .44, 1.45, 0);
              arm.add(box(.23, .65, .25, robe, -.25)); body.add(arm); arms.push(arm);
            }
            const blade = box(.1, .85, .12, 0xc9d0cc, -.22);
            blade.position.z = .3;
            if(obj.weapon==='silver_spear'){const silver=makeWeapon('silver_spear',false,false);silver.position.set(0,-.56,.02);silver.rotation.x=.95;arms[1].add(silver);mesh.userData.silverWeapon=silver;}else arms[1].add(blade);
            if (boss) {
              body.add(box(.22, .32, .19, 0x382923, 1.41));
              body.scale.setScalar(1.2);
            }
            mesh.add(body);
            mesh.userData.enemy = { body, legs, arms };
          } else if (obj.kind === 'time_stone') {
            mesh.add(box(1.2, 1.5, .8, 0x46546f, .75));
            const clock = new THREE.Mesh(new THREE.TorusGeometry(.36, .06, 8, 24),
              new THREE.MeshBasicMaterial({ color: obj.global ? 0xe7abff : 0x7ffff1 }));
            clock.position.set(0, .85, .43);
            mesh.add(clock);
            if (obj.global) {
              const halo = new THREE.Mesh(new THREE.TorusGeometry(1.1, .09, 8, 40),
                new THREE.MeshBasicMaterial({ color: 0xd1a1ff }));
              halo.position.y = 1.1; mesh.add(halo);
            }
            const hand = box(.05, .3, .04, 0x7ffff1, .95); hand.position.z = .44; mesh.add(hand);
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
          bar.position.y = obj.boss ? 3.05 : 2.32;
          bar.scale.set(2.4, .4, 1);
          mesh.add(bar);
          mesh.userData.healthBar = { canvas, map };
          if (obj.name) {
            const label = labelSprite(obj.name, obj.boss ? '#ffd06b' : '#fff1a8', 640, 100, 37);
            label.scale.set(obj.kind === 'time_stone' ? 4.8 : 3, .6, 1);
            label.position.y = obj.boss ? 3.5 : 2.8;
            label.material.depthTest = true;
            mesh.add(label);
          }

        } else if (obj.kind === 'farm') {
          const soil = box(2.4,.08,2.4,0x795939,.04);mesh.add(soil);
          const furrows = new THREE.Group();
          for(const x of [-.8,0,.8]) { const row=box(.08,.025,2.25,0x32251b,.095);row.position.x=x;furrows.add(row); }
          mesh.add(furrows);
          const crops=new THREE.Group(),heads=new THREE.Group();
          for(const x of [-.75,0,.75])for(const z of [-.65,.65]){
            const stem=box(.07,.6,.07,0x76a549,.4);stem.position.set(x,.4,z);crops.add(stem);
            const head=box(.2,.25,.16,0xe6c252,.77);head.position.set(x,.77,z);heads.add(head);
          }
          crops.add(heads);mesh.add(crops);mesh.userData.farm={soil,furrows,crops,heads};
          const label=labelSprite('军屯田 · E', '#e5da9c',448,100,38);label.position.y=1.45;label.scale.set(3,.65,1);label.material.depthTest=true;mesh.add(label);
          mesh.userData.farmLabel=label;
        } else if (obj.kind === 'city_banner' || obj.kind === 'general_recruit') {
          mesh.add(box(1.4,.2,1.4,0x77766c,.1));
          if(obj.kind==='city_banner'){
            mesh.add(box(.12,3,.12,0x76502e,1.6));
            const flag=box(1.1,.8,.06,0xd5b65e,2.6);flag.position.x=.55;mesh.add(flag);mesh.userData.cityFlag=flag;
          } else {
            mesh.add(box(.6,.9,.4,0x6f8154,.95),box(.52,.52,.52,0xcba286,1.65));
            const weapon=makeWeapon(obj.weapon||'sword',false,false);weapon.position.set(.6,.7,0);weapon.userData.loadModel?.();mesh.add(weapon);
          }
          const label=labelSprite(obj.name+' · E '+(obj.kind==='city_banner'?'占领':'招募'),'#ffe4a0',640,110,35);label.position.y=3.4;label.scale.set(5,.85,1);label.material.depthTest=true;mesh.add(label);
        } else if (obj.kind === 'villager') {
          const body=new THREE.Group();
          body.add(box(.6,.75,.4,0x8e724a,1.0),box(.52,.52,.52,0xd0a481,1.65));
          if(obj.is_general){const skin=this.skins[obj.skin]||this.skins.ranger;body.children[1].material=skin.head.map(map=>new THREE.MeshLambertMaterial({map}));body.children[0].material=new THREE.MeshLambertMaterial({map:skin.top});}
          const nose=box(.14,.17,.18,0xbd8e6b,1.58);nose.position.z=.34;body.add(nose);
          for(const x of [-.13,.13]){const eye=box(.065,.06,.02,0x252628,1.73);eye.position.set(x,1.73,.27);body.add(eye);}
          const hat=new THREE.Group();hat.add(box(.8,.09,.8,0xd2b66d,1.96),box(.55,.15,.55,0xb59552,2.05));body.add(hat);
          const armor=box(.65,.6,.45,0x81939b,1.03),helmet=box(.59,.17,.59,0x81939b,1.95);body.add(armor,helmet);
          const legs=[],arms=[];
          for(const side of [-1,1]){
            const leg=new THREE.Group();leg.position.set(side*.17,.65,0);leg.add(box(.24,.64,.3,0x504638,-.32));body.add(leg);legs.push(leg);
            const arm=new THREE.Group();arm.position.set(side*.43,1.35,0);arm.add(box(.22,.65,.24,0x9c8058,-.29));body.add(arm);arms.push(arm);
          }
          const hoe=new THREE.Group();hoe.add(box(.07,.85,.07,0x634a2f,-.45));const blade=box(.35,.09,.2,0x848b8a,-.02);hoe.add(blade);hoe.position.set(0,-.4,.25);arms[1].add(hoe);
          const sword=makeWeapon(obj.weapon||'sword',false,false);sword.position.set(0,-.56,.02);sword.rotation.x=.95;arms[1].add(sword);
          mesh.add(body);mesh.userData.villager={body,hat,armor,helmet,legs,arms,hoe,sword};
          const cv=document.createElement('canvas');cv.width=640;cv.height=120;const map=new THREE.CanvasTexture(cv);map.colorSpace=THREE.SRGBColorSpace;
          const status=new THREE.Sprite(new THREE.SpriteMaterial({map,depthTest:true,depthWrite:false}));status.position.y=2.6;status.scale.set(4.2,.8,1);mesh.add(status);mesh.userData.villagerStatus={cv,map,key:''};
        } else if (obj.kind === 'animal') {
          const tiger = obj.animal === 'tiger', dog = obj.animal === 'dog';
          const color = tiger ? 0xd89532 : dog ? 0x9b6745 : 0x8c949d;
          const body = new THREE.Group();
          body.add(box(.55, .46, 1, color, .68));
          const head = box(.46, .42, .48, color, 1.02); head.position.z = .62; body.add(head);
          for (const side of [-1, 1]) {
            const ear = box(.14, .22, .14, color, 1.3); ear.position.set(side * .17, 1.3, .59); body.add(ear);
            const eye = box(.07, .07, .02, 0x171d23, 1.08); eye.position.set(side * .14, 1.08, .87); body.add(eye);
          }
          const muzzle = box(.28, .17, .2, tiger ? 0xf0d6b0 : 0xc6beb0, .93); muzzle.position.z = .92; body.add(muzzle);
          const nose = box(.11, .08, .03, 0x29272a, .97); nose.position.z = 1.03; body.add(nose);
          const legs = [];
          for (const x of [-.2, .2]) for (const z of [-.34, .34]) {
            const pivot = new THREE.Group(); pivot.position.set(x, .55, z);
            pivot.add(box(.16, .5, .18, color, -.25)); body.add(pivot); legs.push(pivot);
          }
          const tail = box(.12, .14, .6, color, .88); tail.position.z = -.72; tail.rotation.x = dog ? -.7 : .35; body.add(tail);
          if (tiger) for (const side of [-1, 1]) for (const z of [-.3, 0, .3]) {
            const stripe = box(.035, .44, .11, 0x3a2d25, .7); stripe.position.set(side * .285, .7, z); body.add(stripe);
          }
          body.scale.setScalar(tiger ? 1.25 : dog ? .75 : .95);
          const collar = box(.6, .12, .18, 0xcf4545, .94); collar.position.z = .44; collar.visible = false; body.add(collar);
          mesh.add(body); mesh.userData.animal = { body, legs, collar };
          const cv = document.createElement('canvas'); cv.width = 640; cv.height = 120;
          const map = new THREE.CanvasTexture(cv); map.colorSpace = THREE.SRGBColorSpace;
          const status = new THREE.Sprite(new THREE.SpriteMaterial({ map, depthTest: true, depthWrite: false }));
          status.position.y = tiger ? 2.15 : 1.65; status.scale.set(3.6, .68, 1); mesh.add(status);
          mesh.userData.animalStatus = { cv, map, key: '' };
        } else if (obj.kind === 'food_pickup' || obj.kind === 'poop_pickup') {
          const poop = obj.kind === 'poop_pickup';
          if (poop) {
            for (let i = 0; i < 3; i++) {
              const pile = new THREE.Mesh(new THREE.SphereGeometry(.24 - i * .065, 6, 4), new THREE.MeshLambertMaterial({ color: 0x65422b }));
              pile.position.y = .12 + i * .14; mesh.add(pile);
            }
          } else {
            const bowl = new THREE.Mesh(new THREE.CylinderGeometry(.3, .24, .15, 10), new THREE.MeshLambertMaterial({ color: 0xc0a96d }));
            bowl.position.y = .1; mesh.add(bowl);
            for (const x of [-.12, 0, .12]) {
              const kibble = box(.13, .12, .14, 0x86582e, .21); kibble.position.x = x; mesh.add(kibble);
            }
          }
          const label = labelSprite((poop ? '狗屎' : '狗粮 / 兽肉') + ' · E', poop ? '#c3a47b' : '#e7dca3', 448, 100, 38);
          label.position.y = .9; label.scale.set(2.2, .5, 1); label.material.depthTest = true; mesh.add(label);
        } else if (obj.kind === 'armor_pickup') {
          const color = obj.armor_kind === 'elite' ? 0xe2c87b : 0xd9e0e7;
          const model = new THREE.Group();
          model.add(box(.65, .65, .35, color, .9));
          for (const side of [-1, 1]) {
            const shoulder = box(.28, .23, .4, color, 1.2); shoulder.position.x = side * .4; model.add(shoulder);
          }
          mesh.add(model);
          const name = this.world.armor_types[obj.armor_kind].name;
          const label = labelSprite(name + ' · 耐久 ' + obj.durability + ' · E', '#ffffff', 640, 100, 38);
          label.position.y = 1.8; label.scale.set(3.2, .6, 1); label.material.depthTest = true; mesh.add(label);
        } else if (obj.kind === 'story_npc') {
          const skin = this.skins[obj.skin] || this.skins.steve;
          const head = box(.54, .54, .54, 0xffffff, 1.7);
          head.material = skin.head.map(map => new THREE.MeshLambertMaterial({ map }));
          const torso = box(.64, .8, .4, 0xffffff, 1.04);
          torso.material = new THREE.MeshLambertMaterial({ map: skin.top });
          mesh.add(head, torso, box(.56, .66, .35, 0x4b4951, .33));
          for (const side of [-1, 1]) {
            const arm = box(.23, .68, .24, 0xffffff, 1.05);
            arm.material = new THREE.MeshLambertMaterial({ map: skin.sleeve });
            arm.position.x = side * .45; mesh.add(arm);
          }
          if(obj.weapon==='silver_spear'){const silver=makeWeapon('silver_spear',false,false);silver.position.set(.5,.5,.1);mesh.add(silver);mesh.userData.silverWeapon=silver;}
          const label = labelSprite(obj.name + ' · 对话 E', '#91e9d4', 448, 100, 38);
          label.position.y = 2.5; label.scale.set(3.1, .7, 1); label.material.depthTest = true; mesh.add(label);
        } else if (obj.kind === 'chapter_gate') {
          const ring = new THREE.Mesh(new THREE.TorusGeometry(.9, .13, 8, 32),
            new THREE.MeshBasicMaterial({ color: 0x65e8ef }));
          ring.position.y = 1.15;
          mesh.add(ring, box(2.3, .16, .9, 0x39435e, .08));
          const label = labelSprite(obj.text + ' · E', '#a3ffff', 640, 100, 36);
          label.position.y = 2.6; label.scale.set(4.2, .7, 1); label.material.depthTest = true; mesh.add(label);
          const status = labelSprite('清城后开启', '#bdb6cb', 320, 90, 36);
          status.position.y = 3.2; status.scale.set(2.4, .6, 1); status.material.depthTest = true;
          mesh.add(status); mesh.userData.gateStatus = status;
        } else if (obj.kind === 'weapon_pickup') {
          const model = makeWeapon(obj.weapon);
          model.position.y = .9;
          model.scale.setScalar(1.45);
          if (obj.weapon !== 'beam') model.rotation.z = -.18;
          mesh.add(model);
          const label = labelSprite(obj.text + (obj.uses ? ' · ' + (obj.uses===-1?'无限':obj.uses+'次') : '') + ' · E', obj.rarity === 'boss' ? '#e6b0ff' : '#ffe78b', 640, 100, 38);
          label.position.y = 2.25;
          label.scale.set(obj.rarity ? 3.5 : 2.4, .75, 1);
          label.material.depthTest = true;
          mesh.add(label);
        } else if(obj.kind==='workbench'){
          const wood=box(1.2,.85,1.2,0x99703d,.45);wood.material.map=this.tiles.bark.map;mesh.add(wood);
          mesh.add(box(1.3,.13,1.3,0xc99957,.95));
          for(const i of [-.36,0,.36]){const line=box(.025,.015,1.16,0x62432d,1.025);line.position.x=i;mesh.add(line);const cross=box(1.16,.015,.025,0x62432d,1.025);cross.position.z=i;mesh.add(cross);}
          const hammer=box(.17,.38,.22,0xb8bfc1,.66);hammer.position.set(.62,.66,.12);mesh.add(hammer);
          const label=labelSprite('合成工作台 · E','#f1cb81',512,110,40);label.position.y=1.7;label.scale.set(3.8,.8,1);label.material.depthTest=true;mesh.add(label);
        } else if(obj.kind==='resource'){
          const cfg=this.world.resources[obj.resource];
          mesh.add(box(.72,.62,.72,obj.resource==='wood'?0xa77743:obj.resource==='obsidian'?0x292136:0x737c7c,.31));
          if(obj.resource==='wood')mesh.children[0].material.map=this.tiles.bark.map;
          else for(const [x,z] of [[-.2,.1],[.14,.24],[.25,-.15]]){const vein=box(.2,.12,.18,cfg.color,.67);vein.position.set(x,.67,z);mesh.add(vein);}
          const label=labelSprite(cfg.name+' · E',cfg.color,384,90,34);label.position.y=1.05;label.scale.set(2.2,.52,1);label.material.depthTest=true;mesh.add(label);
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
      this.applyHitFlash(mesh, !!obj.hurt && Math.floor(this.time * 12) % 2 === 0);
      mesh.position.set(obj.x, obj.y || 0, obj.z);
      mesh.traverse(part=>{if(part.isSprite)part.visible=distance<(this.monocular?145:26)});
      if(mesh.userData.silverWeapon&&distance<12)mesh.userData.silverWeapon.userData.loadModel?.();
      if(mesh.userData.cityFlag){const color=this.world.teams[obj.owner]?.color||this.world.factions?.[obj.owner]?.color||'#d5b65e';mesh.userData.cityFlag.material.color.set(color);for(const f of this.openCityFlags?.get(obj.city)||[])f.material.color.set(color);}
      if (obj.kind === 'chapter_gate') {
        mesh.children[0].rotation.z = this.time * .6;
        mesh.children[0].material.color.setHex(obj.locked ? 0x666677 : 0x65e8ef);
        mesh.userData.gateStatus.visible = obj.locked;
      }
      if(mesh.userData.farm){
        const f=mesh.userData.farm;f.soil.material.color.setHex(obj.stage?0x65432c:0x795939);f.furrows.visible=obj.stage>0;f.crops.visible=obj.stage>=2;f.heads.visible=obj.stage===3;
        f.crops.scale.y=obj.stage===2?.3+.7*(1-(obj.grow_cd||0)/30):1;
        const text=['E 耕地','E 播种','成长 '+obj.grow_cd+'秒','已成熟 · E 收获'][obj.stage];
        if(mesh.userData.farmText!==text){
          const old=mesh.userData.farmLabel;mesh.remove(old);old.material.map.dispose();old.material.dispose();
          const label=labelSprite('军屯田 · '+text,'#e5da9c',448,100,36);label.position.y=1.45;label.scale.set(3,.65,1);label.material.depthTest=true;mesh.add(label);mesh.userData.farmLabel=label;mesh.userData.farmText=text;
        }
      }
      if(mesh.userData.villager){
        const v=mesh.userData.villager,soldier=obj.role==='soldier';v.body.rotation.y=obj.yaw||0;v.hat.visible=!soldier;v.armor.visible=v.helmet.visible=v.sword.visible=soldier;v.hoe.visible=!soldier;if(soldier&&distance<8)v.sword.userData.loadModel?.();
        v.legs.forEach((leg,i)=>leg.rotation.x=obj.moving?Math.sin(this.time*7+i*Math.PI)*.4:0);v.arms[1].rotation.x=soldier?(obj.attacking?-1.8:-.95):obj.working?Math.sin(this.time*12)*.6-.5:-.2;
        const s=mesh.userData.villagerStatus,key=obj.name+obj.owner+obj.role+obj.hp+obj.heal+(obj.favor?.[viewerName]||0);
        if(s.key!==key){const ctx=s.cv.getContext('2d');ctx.fillStyle='#16231fee';ctx.fillRect(0,0,640,120);ctx.fillStyle=soldier?'#98dfff':'#f1e6b3';ctx.font='bold 29px sans-serif';ctx.textAlign='center';
          ctx.fillText(obj.name+' · '+(soldier?obj.owner+(obj.is_general?'的武将':'的小兵'):'闲居村民 · E'),320,36,620);ctx.fillStyle='#98d899';ctx.fillRect(10,60,620*obj.hp/obj.max_hp,48);ctx.fillStyle='#fff';ctx.fillText(soldier?obj.hp+'/'+obj.max_hp+(obj.heal?' 回血+'+obj.heal+'/秒':''):'好感 '+(obj.favor?.[viewerName]||0)+'/80 · 帮忙耕种可招募',320,94,620);s.map.needsUpdate=true;s.key=key;}
      }
      if (mesh.userData.animal) {
        const { body, legs, collar } = mesh.userData.animal;
        body.rotation.y = obj.yaw || 0;
        body.rotation.x = obj.attacking ? -.12 : 0;
        body.position.y = obj.hurt ? .08 : 0;
        collar.visible = !!obj.owner;
        legs.forEach((leg, i) => leg.rotation.x = obj.moving ? Math.sin(this.time * 8 + (i % 2) * Math.PI) * .45 : 0);
        const status = mesh.userData.animalStatus;
        const title = obj.owner ? obj.owner + '的伙伴犬' : obj.name;
        const info = obj.animal === 'dog' ? '好感 ' + Math.round(obj.favor?.[viewerName] || 0) + ' · 饱食 ' + Math.round(obj.hunger) : '危险 · 主动攻击';
        const key = title + info + obj.hp;
        if (status.key !== key) {
          const ctx = status.cv.getContext('2d'); ctx.clearRect(0, 0, 640, 120);
          ctx.fillStyle = '#161d20dd'; ctx.fillRect(0, 0, 640, 120);
          ctx.fillStyle = obj.owner ? '#8fffdc' : obj.animal === 'dog' ? '#ffe3a2' : '#ffaaa0';
          ctx.font = 'bold 30px sans-serif'; ctx.textAlign = 'center'; ctx.fillText(title + ' · ' + info, 320, 38, 620);
          ctx.fillStyle = '#3a3133'; ctx.fillRect(10, 60, 620, 48);
          ctx.fillStyle = '#a4cc75'; ctx.fillRect(10, 60, 620 * obj.hp / obj.max_hp, 48);
          ctx.fillStyle = '#ffffff'; ctx.fillText(obj.hp + ' / ' + obj.max_hp, 320, 95);
          status.map.needsUpdate = true; status.key = key;
        }
      }
      if (mesh.userData.enemy) {
        const { body, legs, arms } = mesh.userData.enemy;
        body.rotation.y = obj.yaw || 0;
        const moving = mesh.userData.lastX !== undefined && Math.hypot(obj.x - mesh.userData.lastX, obj.z - mesh.userData.lastZ) > .001;
        legs.forEach((leg, i) => leg.rotation.x = moving ? Math.sin(this.time * 8 + i * Math.PI) * .5 : 0);
        arms[1].rotation.x = obj.attacking ? -1.8 : obj.weapon === 'silver_spear' ? -.95 : -.15;
        body.position.y = obj.hurt ? .09 : 0;
        mesh.userData.lastX = obj.x; mesh.userData.lastZ = obj.z;
      }
      if (obj.kind === 'weapon_pickup' || obj.kind === 'armor_pickup') mesh.children[0].rotation.y = this.time * .55;
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
          ctx.fillStyle = ({ dummy: '#95733e', enemy: obj.boss ? '#e18039' : '#ceb33d', time_stone: '#42bbae' })[obj.kind] || this.world.teams[obj.team]?.color || '#ffffff';
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
    this.crowd.sync(simple,this.time);
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

  applyHitFlash(root, active) {
    if (root.userData.hitFlash === active) return;
    root.userData.hitFlash = active;
    root.traverse(mesh => {
      if (!mesh.isMesh) return;
      for (const mat of (Array.isArray(mesh.material) ? mesh.material : [mesh.material])) {
        if (!mat?.color) continue;
        mat.userData.hitColor ||= mat.color.clone();
        if (mat.emissive && !mat.userData.hitEmissive) mat.userData.hitEmissive = mat.emissive.clone();
        mat.color.copy(mat.userData.hitColor);
        if (active) mat.color.lerp(new THREE.Color(0xff7b68), .6);
        if (mat.emissive) mat.emissive.copy(active ? new THREE.Color(0x84291e) : mat.userData.hitEmissive);
      }
    });
  }

  spawnFarm(event) {
    this.spawnHit({x:event.x,y:.2,z:event.z});
    const hit=this.hits[this.hits.length-1];
    for(const spark of hit.mesh.children)spark.material.color.setHex(event.harvest?0xf6d773:0x8fd66a);
  }

  spawnHit(event) {
    const mesh = new THREE.Group();
    const impact = new THREE.Vector3(event.x, event.y || 1, event.z);
    mesh.position.copy(impact).addScaledVector(this.camera.position.clone().sub(impact).normalize(), .4);
    for (let i = 0; i < 8; i++) {
      const spark = box(.075, .075, .075, i % 2 ? 0xfff2c7 : 0xff8059, 0, true);
      const angle = i / 8 * Math.PI * 2;
      spark.userData.velocity = new THREE.Vector3(Math.cos(angle) * 2.3, Math.sin(angle) * 1.8 + .7, (i % 3 - 1) * 1.5);
      spark.material.transparent = true;
      mesh.add(spark);
    }
    this.scene.add(mesh); this.hits.push({ mesh, age: 0 });
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

  draw() {
    const now=performance.now();this.qualityWindow.frames++;
    if(now-this.qualityWindow.time>3000){
      const fps=this.qualityWindow.frames*1000/(now-this.qualityWindow.time),dpr=this.renderer.getPixelRatio();
      const next=fps<35?Math.max(Math.min(1,this.maxDpr),dpr-.25):fps>57?Math.min(this.maxDpr,dpr+.25):dpr;
      if(next!==dpr){this.renderer.setPixelRatio(next);this.resize();}
      this.qualityWindow={time:now,frames:0};
    }
    this.renderer.info.reset();
    const overlay = this.viewModel.visible;
    if (overlay) {
      this.viewModel.traverse(object => {
        object.layers.set(1);
        if (!object.isMesh) return;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        for (const material of materials) {
          material.depthTest = true;
          material.depthWrite = true;
        }
      });
    }
    this.renderer.render(this.scene, this.camera);
    if (overlay) {
      this.renderer.autoClear = false;
      this.renderer.clearDepth();
      this.camera.layers.set(1);
      const background = this.scene.background;
      this.scene.background = null;
      this.renderer.render(this.scene, this.camera);
      this.scene.background = background;
      this.camera.layers.set(0);
      this.renderer.autoClear = true;
    }
  }

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

  setMonocular(enabled) {
    this.monocular = enabled;
    this.camera.fov = enabled ? 18 : this.viewMode === 'first' ? 76 : 54;
    this.camera.updateProjectionMatrix();
  }

  setViewMode(mode, team) {
    this.viewMode = mode === 'first' ? 'first' : 'third';
    const first = this.viewMode === 'first';
    this.viewModel.visible = first;
    this.camera.fov = this.monocular ? 18 : first ? 76 : 54;
    this.camera.updateProjectionMatrix();

  }

  applyLook(dx, dy) {
    if (this.viewMode !== 'first') return;
    // The camera looks along (sin(yaw), cos(yaw)), so its screen-right vector
    // is (-cos(yaw), sin(yaw)). Turning right therefore DECREASES yaw.
    this.yaw -= dx * (this.monocular ? .0008 : .0026);
    this.pitch = Math.max(-1.15, Math.min(1.15, this.pitch - dy * (this.monocular ? .0007 : .0022)));
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
