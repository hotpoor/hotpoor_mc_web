import * as THREE from './vendor/three.module.js';
import { GLTFLoader } from './vendor/loaders/GLTFLoader.js';

const loader = new GLTFLoader();
const models = new Map();
const settings = {
  sword: { height: 1.08, grip: .20 },
  bow: { height: 1.04, grip: .50 },
  beam: { height: .40, grip: .50 },
  rocket: { height: .95, grip: .35, horizontal: true },
  gun: { height: .78, grip: .34, horizontal: true },
  axe: { height: 1.02, grip: .22 },
  mace: { height: 1.08, grip: .22 },
  hammer: { height: 1.10, grip: .24 },
  dual: { height: 1.08, grip: .20 },
  spear: { height: 1.65, grip: .35 },
  blade: { height: 1.65, grip: .35 },
  halberd: { height: 1.65, grip: .35 },
};

function loadModel(kind) {
  if (!models.has(kind)) {
    const url = new URL('./models/weapons/' + kind + '.glb', import.meta.url);
    models.set(kind, loader.loadAsync(url.href).then(gltf => gltf.scene));
  }
  return models.get(kind);
}

export function attachWeaponModel(group, kind, overlay = false) {
  const config = settings[kind];
  if (!config) return;
  const fallback = [...group.children];
  loadModel(kind).then(source => {
    const model = source.clone(true);
    // Share immutable geometry and maps, clone materials for first-person depth settings.
    model.traverse(mesh => {
      if (!mesh.isMesh) return;
      mesh.geometry = mesh.geometry.clone();
      const prepare = material => {
        const copy = material.clone();
        copy.userData.sharedTextures = true;
        copy.depthTest = !overlay;
        copy.depthWrite = !overlay;
        copy.fog = !overlay;
        copy.roughness = Math.max(.45, copy.roughness ?? .7);
        return copy;
      };
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map(prepare) : prepare(mesh.material);
      mesh.renderOrder = overlay ? 999 : 0;
    });
    let bounds = new THREE.Box3().setFromObject(model);
    const size = bounds.getSize(new THREE.Vector3());
    const longest = ['x', 'y', 'z'].sort((a, b) => size[b] - size[a])[0];
    if (config.horizontal) {
      if (longest === 'x') model.rotation.y = -Math.PI / 2;
    } else {
      if (longest === 'x') model.rotation.z = Math.PI / 2;
      if (longest === 'z') model.rotation.x = -Math.PI / 2;
    }
    bounds = new THREE.Box3().setFromObject(model);
    const facing = bounds.getSize(new THREE.Vector3());
    if (!config.horizontal && facing.z > facing.x) {
      const rotation = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 2);
      model.quaternion.premultiply(rotation);
      bounds = new THREE.Box3().setFromObject(model);
    }
    const dimensions = bounds.getSize(new THREE.Vector3());
    const scale = config.height / (config.horizontal ? dimensions.z : dimensions.y);
    const center = bounds.getCenter(new THREE.Vector3());
    const normalized = new THREE.Group();
    model.position.sub(center);
    if (config.horizontal) {
      model.position.y += dimensions.y * .22;
      model.position.z += dimensions.z * (.5 - config.grip);
    } else {
      model.position.y += dimensions.y * (.5 - config.grip);
    }
    normalized.add(model);
    normalized.scale.setScalar(scale);
    if (kind === 'bow') {
      const bowBounds = new THREE.Box3().setFromObject(normalized);
      normalized.position.x = -bowBounds.min.x;
      group.userData.tipX = bowBounds.max.x - bowBounds.min.x;
      for (const string of group.userData.string) string.position.x = group.userData.tipX;
      group.userData.arrow.position.x = group.userData.tipX;
    }
    for (const child of fallback) {
      // Keep the animated string and arrow attached to the generated bow.
      if (kind === 'bow' && (group.userData.string.includes(child) || child === group.userData.arrow)) continue;
      child.visible = false;
    }
    group.add(normalized);
    group.userData.tripoModel = normalized;
  }).catch(error => console.warn('[weapon model]', kind, error.message));
}
