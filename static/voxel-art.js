import * as THREE from './vendor/three.module.js';

export function voxelMaterial(kind) {
  const palette = {
    grass: [105, 148, 63], dirt: [124, 86, 54], stone: [131, 135, 134],
    brick: [162, 88, 61], bark: [113, 79, 48], rings: [174, 130, 76],
    leaves: [68, 126, 49], grassSide: [105, 148, 63],
  };
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = 16;
  const ctx = canvas.getContext('2d');
  for (let y = 0; y < 16; y++) {
    for (let x = 0; x < 16; x++) {
      const noise = ((Math.imul(x + 19, 374761393) ^ Math.imul(y + 37, 668265263)) >>> 15) % 33 - 16;
      let color = palette[kind];
      let shade = noise;
      if (kind === 'grassSide' && y > 3 + (x * 7 % 3)) color = palette.dirt;
      if (kind === 'brick') {
        const seam = y % 4 === 0 || (x + 4 * (y >> 2)) % 8 === 0;
        if (seam) color = [107, 102, 89];
        else shade += y % 4 === 1 ? 17 : -5;
      }
      if (kind === 'bark') shade += x % 5 < 2 ? -24 : 8;
      if (kind === 'rings') shade += Math.max(Math.abs(x - 7), Math.abs(y - 7)) % 3 === 0 ? -30 : 5;
      if (kind === 'stone') shade += ((x >> 2) + 2 * (y >> 2)) % 4 === 0 ? -20 : 5;
      if (kind === 'leaves') shade += ((x >> 1) ^ (y >> 1)) % 3 === 0 ? -26 : 9;
      ctx.fillStyle = 'rgb(' + color.map(channel => channel + shade).join(',') + ')';
      ctx.fillRect(x, y, 1, 1);
    }
  }
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  map.magFilter = THREE.NearestFilter;
  map.minFilter = THREE.NearestMipmapLinearFilter;
  map.wrapS = map.wrapT = THREE.RepeatWrapping;
  return new THREE.MeshLambertMaterial({ map });
}

export function makeWeapon(kind, overlay = false) {
  const group = new THREE.Group();
  function part(w, h, d, color, x, y, z = 0) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d),
      new THREE.MeshBasicMaterial({ color, depthTest: !overlay, depthWrite: !overlay, fog: !overlay }));
    mesh.position.set(x, y, z);
    if (overlay) mesh.renderOrder = 999;
    group.add(mesh);
    return mesh;
  }
  if (kind === 'sword') {
    part(.095, .23, .10, 0x68442d, 0, -.06);
    part(.13, .07, .12, 0x373a47, 0, -.20);
    part(.33, .09, .14, 0x344e57, 0, .09);
    part(.16, .65, .10, 0x3a9e9d, 0, .45);
    part(.085, .60, .102, 0xaaf4df, .022, .47);
    part(.095, .09, .10, 0x8df1d9, .025, .81);
  } else if (kind === 'bow') {
    part(.11, .20, .13, 0x644228, 0, 0);
    for (const sign of [-1, 1]) {
      part(.10, .24, .10, 0xb27c43, .03, sign * .20).rotation.z = -sign * .32;
      part(.10, .22, .10, 0xc99455, .13, sign * .39).rotation.z = -sign * .65;
      part(.09, .13, .09, 0x775032, .23, sign * .50);
    }
    group.userData.string = [
      part(.018, 1, .018, 0xeadac1, 0, 0),
      part(.018, 1, .018, 0xeadac1, 0, 0),
    ];
    const arrow = makeWeapon('arrow', overlay);
    arrow.rotation.x = Math.PI / 2;
    group.add(arrow);
    group.userData.arrow = arrow;
    poseBow(group, null);
  } else if (kind === 'gun') {
    part(.18, .17, .42, 0x46515c, 0, 0, .13);
    part(.10, .10, .36, 0x687481, 0, .02, .46);
    part(.13, .2, .13, 0x373c43, 0, -.12, .15);
  } else if (kind === 'rocket') {
    part(.22, .22, .78, 0x55633e, 0, 0, .27);
    part(.29, .26, .12, 0x384039, 0, 0, .7);
    part(.12, .2, .13, 0x383130, 0, -.13, .25);
  } else if (kind === 'missile') {
    part(.13, .42, .13, 0x65694f, 0, 0);
    part(.09, .13, .09, 0xec653e, 0, .24);
    part(.16, .12, .16, 0xffb34b, 0, -.23);
  } else {
    part(.035, .66, .035, 0xa77845, 0, 0);
    part(.065, .12, .065, 0xb9d2d4, 0, .32);
    part(.12, .12, .03, 0xf4e4c6, 0, -.27);
  }
  return group;
}

export function poseBow(bow, draw) {
  const { string, arrow } = bow.userData;
  const nock = new THREE.Vector3(.24, 0, -(draw ?? 0) * .49);
  for (let i = 0; i < string.length; i++) {
    const tip = new THREE.Vector3(.23, i === 0 ? -.52 : .52, 0);
    const delta = tip.clone().sub(nock);
    string[i].position.copy(nock).lerp(tip, .5);
    string[i].scale.y = delta.length();
    string[i].quaternion.setFromUnitVectors(THREE.Object3D.DEFAULT_UP, delta.normalize());
  }
  arrow.visible = draw !== null;
  arrow.position.copy(nock);
  arrow.position.z += .29;
}
