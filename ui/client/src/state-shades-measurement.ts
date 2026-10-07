/** Fixed proof convention for 777-S2; test-only, never imported by the client. */
export type Triple = readonly [
  number,
  number,
  number
];
export const DEUTAN_1 = [
  [0.367322, 0.860646, -0.227968],
  [0.280085, 0.672501, 0.047413],
  [-0.01182, 0.04294, 0.968881],
] as const;
const radians = (degrees: number) => degrees * Math.PI / 180;
const degrees = (radians: number) => radians * 180 / Math.PI;
const cos = (angle: number) => Math.cos(radians(angle));
const sin = (angle: number) => Math.sin(radians(angle));
export function hslRgb([h, s, l]: Triple): Triple {
  s /= 100;
  l /= 100;
  const a = s * Math.min(l, 1 - l);
  const channel = (n: number) => {
    const k = (n + h / 30) % 12;
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  return [channel(0), channel(8), channel(4)];
}
export function composite(fg: Triple, bg: Triple, opacity: number): Triple {
  return fg.map((v, i) => v * opacity + bg[i] * (1 - opacity)) as unknown as Triple;
}
const linear = (v: number) => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4;
const encoded = (v: number) => v <= .0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - .055;
export function deutanRgb(rgb: Triple): Triple {
  const input = rgb.map(linear);
  return DEUTAN_1.map(row => encoded(Math.max(0, Math.min(1, row.reduce((sum, v, i) => sum + v * input[i], 0))))) as unknown as Triple;
}
export function deutanLab(rgb: Triple): Triple {
  return deutanLinearLab(rgb.map(linear) as unknown as Triple);
}
/** Apply Machado directly to the retained linear-sRGB mask mean, then D65 Lab. */
export function deutanLinearLab(input: Triple): Triple {
  const [r, g, b] = DEUTAN_1.map(row => Math.max(0, Math.min(1, row.reduce((sum, v, i) => sum + v * input[i], 0))));
  const f = (v: number) => v > (6 / 29) ** 3 ? Math.cbrt(v) : v / (3 * (6 / 29) ** 2) + 4 / 29;
  const x = f((.4124564 * r + .3575761 * g + .1804375 * b) / .95047);
  const y = f(.2126729 * r + .7151522 * g + .072175 * b);
  const z = f((.0193339 * r + .119192 * g + .9503041 * b) / 1.08883);
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}
/** CIEDE2000, kL=kC=kH=1, including the published hue-wrap cases. */
export function ciede2000(first: Triple, second: Triple): number {
  const [l1, a1, b1] = first;
  const [l2, a2, b2] = second;
  const cbar = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2;
  const g = .5 * (1 - Math.sqrt(cbar ** 7 / (cbar ** 7 + 25 ** 7)));
  const ap1 = (1 + g) * a1;
  const ap2 = (1 + g) * a2;
  const cp1 = Math.hypot(ap1, b1);
  const cp2 = Math.hypot(ap2, b2);
  const hue = (a: number, b: number) => a === 0 && b === 0 ? 0 : (degrees(Math.atan2(b, a)) + 360) % 360;
  const h1 = hue(ap1, b1);
  const h2 = hue(ap2, b2);
  const dl = l2 - l1;
  const dc = cp2 - cp1;
  let dh = h2 - h1;
  if (cp1 * cp2 === 0)
    dh = 0;
  else if (dh > 180)
    dh -= 360;
  else if (dh < -180)
    dh += 360;
  const dH = 2 * Math.sqrt(cp1 * cp2) * sin(dh / 2);
  const lb = (l1 + l2) / 2;
  const cb = (cp1 + cp2) / 2;
  let hb = h1 + h2;
  if (cp1 * cp2 !== 0) {
    if (Math.abs(h1 - h2) <= 180)
      hb /= 2;
    else
      hb = (hb + (hb < 360 ? 360 : -360)) / 2;
  }
  const t = 1 - .17 * cos(hb - 30) + .24 * cos(2 * hb) + .32 * cos(3 * hb + 6) - .20 * cos(4 * hb - 63);
  const sl = 1 + .015 * (lb - 50) ** 2 / Math.sqrt(20 + (lb - 50) ** 2);
  const sc = 1 + .045 * cb;
  const sh = 1 + .015 * cb * t;
  const rt = -2 * Math.sqrt(cb ** 7 / (cb ** 7 + 25 ** 7)) * sin(60 * Math.exp(-(((hb - 275) / 25) ** 2)));
  return Math.sqrt((dl / sl) ** 2 + (dc / sc) ** 2 + (dH / sh) ** 2 + rt * (dc / sc) * (dH / sh));
}
