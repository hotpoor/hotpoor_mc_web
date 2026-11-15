import * as THREE from './vendor/three.module.js';

const steveFace = [
  'hhhhhhhh', 'hhhhhhhh', 'hhsssshh', 'ssssssss',
  'swEssEws', 'ssssssss', 'ssbbbbss', 'ssbssbss',
];
const alexFace = [
  'oooooooo', 'oooooooo', 'ooosssso', 'osssssso',
  'swGssGws', 'ssssssso', 'ssspssso', 'ssssssso',
];

export const SKIN_NAMES = {
  red: '纯红', blue: '纯蓝', steve: '史蒂夫', alex: '艾利克斯',
  miner: '矿工', ranger: '游侠', robot: '机器人',
};

const EXTRA_SKINS = {
  red: { solid: '#e64448' },
  blue: { solid: '#3d72e7' },
  miner: {
    palette: { h: '#e6a33c', s: '#c99066', c: '#c77b32', d: '#714e39', l: '#514958' },
    face: ['hhhhhhhh', 'hhhwwhhh', 'hhhhhhhh', 'ssssssss', 'sEssssEs', 'ssssssss', 'ssbbbbss', 'ssssssss'],
  },
  ranger: {
    palette: { h: '#345344', s: '#d8a382', c: '#537a57', d: '#344638', l: '#495a57' },
    face: ['hhhhhhhh', 'hhhhhhhh', 'hhsssshh', 'hssssssh', 'hsGssGsh', 'hssssssh', 'ddssssdd', 'dddddddd'],
  },
  robot: {
    palette: { h: '#52677a', s: '#a4b6c1', c: '#728697', d: '#425767', l: '#556875', G: '#40e3dc' },
    face: ['hhhhhhhh', 'hssssssh', 'hssssssh', 'hGGssGGh', 'hGGssGGh', 'hssssssh', 'hsddddsh', 'hhhhhhhh'],
  },
};

function design(name) {
  const alex = name === 'alex';
  const colors = {
    h: '#392923', o: '#b95220', s: alex ? '#f0c4a2' : '#b98059',
    w: '#f5eddb', E: '#4a396f', G: '#3c7953', b: '#6d4232', p: '#b46f61',
    c: alex ? '#73934c' : '#279fac', d: alex ? '#4e6d37' : '#197b8d',
    l: alex ? '#675847' : '#424278', k: '#343238',
  };
  const extra = EXTRA_SKINS[name];
  Object.assign(colors, extra?.palette);
  if (extra?.solid) for (const key of ['h', 's', 'c', 'd', 'l', 'k']) colors[key] = extra.solid;
  return { alex, colors, face: extra?.solid ? Array(8).fill('hhhhhhhh') : extra?.face || (alex ? alexFace : steveFace) };
}

export function drawSkinFace(canvas, name) {
  const { colors, face } = design(name);
  paintPixels(canvas, face, colors);
}

function paintPixels(canvas, rows, colors) {
  canvas.width = canvas.height = 8;
  const ctx = canvas.getContext('2d');
  rows.forEach((row, y) => [...row].forEach((pixel, x) => {
    ctx.fillStyle = colors[pixel];
    ctx.fillRect(x, y, 1, 1);
  }));
}

export function makeSkin(name) {
  const { alex, colors, face } = design(name);
  const texture = rows => {
    const canvas = document.createElement('canvas');
    paintPixels(canvas, rows, colors);
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.magFilter = map.minFilter = THREE.NearestFilter;
    return map;
  };
  const repeat = row => Array(8).fill(row);
  const hair = alex ? 'oooooooo' : 'hhhhhhhh';
  const side = texture([...Array(5).fill(hair), alex ? 'sooooooo' : 'sshhhhss', 'ssssssss', 'ssssssss']);
  const back = texture(repeat(hair));
  return {
    head: [side, side, back, texture(repeat('ssssssss')), texture(face), back],
    top: texture(alex ? ['ddossodd', 'cdooddcc', 'ccdoddcc', 'cccccccc', 'cdccccdc', 'cccccccc', 'cccccccc', 'dddddddd']
      : ['ddssssdd', 'cccssccc', 'cccccccc', 'cdccccdc', 'cccccccc', 'cccccccc', 'cccccccc', 'dddddddd']),
    sleeve: texture(repeat('cccdcccc')),
    hand: texture(repeat('ssssssss')),
    legs: texture(['llllllll', 'llklllll', 'llllllll', 'llllllll', 'lllllkll', 'llllllll', 'kkkkkkkk', 'kkkkkkkk']),
  };
}
