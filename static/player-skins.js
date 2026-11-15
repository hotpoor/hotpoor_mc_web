import * as THREE from './vendor/three.module.js';

const steveFace = [
  'hhhhhhhh', 'hhhhhhhh', 'hhsssshh', 'ssssssss',
  'swEssEws', 'ssssssss', 'ssbbbbss', 'ssbssbss',
];
const alexFace = [
  'oooooooo', 'oooooooo', 'ooosssso', 'osssssso',
  'swGssGws', 'ssssssso', 'ssspssso', 'ssssssso',
];

export function makeSkin(name) {
  const alex = name === 'alex';
  const colors = {
    h: '#392923', o: '#b95220', s: alex ? '#f0c4a2' : '#b98059',
    w: '#f5eddb', E: '#4a396f', G: '#3c7953', b: '#6d4232', p: '#b46f61',
    c: alex ? '#73934c' : '#279fac', d: alex ? '#4e6d37' : '#197b8d',
    l: alex ? '#675847' : '#424278', k: '#343238',
  };
  const texture = rows => {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 8;
    const ctx = canvas.getContext('2d');
    rows.forEach((row, y) => [...row].forEach((pixel, x) => {
      ctx.fillStyle = colors[pixel];
      ctx.fillRect(x, y, 1, 1);
    }));
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
    head: [side, side, back, texture(repeat('ssssssss')), texture(alex ? alexFace : steveFace), back],
    top: texture(alex ? ['ddossodd', 'cdooddcc', 'ccdoddcc', 'cccccccc', 'cdccccdc', 'cccccccc', 'cccccccc', 'dddddddd']
      : ['ddssssdd', 'cccssccc', 'cccccccc', 'cdccccdc', 'cccccccc', 'cccccccc', 'cccccccc', 'dddddddd']),
    sleeve: texture(repeat('cccdcccc')),
    hand: texture(repeat('ssssssss')),
    legs: texture(['llllllll', 'llklllll', 'llllllll', 'llllllll', 'lllllkll', 'llllllll', 'kkkkkkkk', 'kkkkkkkk']),
  };
}
