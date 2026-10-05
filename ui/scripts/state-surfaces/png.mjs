/** Decode Playwright's 8-bit, non-interlaced RGB/RGBA PNGs without dependencies. */
import { inflateSync } from 'node:zlib';

export function decodePng(bytes) {
  if (!bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])))
    throw new Error('Invalid PNG signature');
  let width, height, channels;
  const data = [];
  for (let offset = 8; offset < bytes.length;) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    const chunk = bytes.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = chunk.readUInt32BE(0); height = chunk.readUInt32BE(4);
      if (chunk[8] !== 8 || ![2, 6].includes(chunk[9]) || chunk[10] || chunk[11] || chunk[12])
        throw new Error('Expected 8-bit, non-interlaced RGB/RGBA PNG');
      channels = chunk[9] === 2 ? 3 : 4;
    } else if (type === 'IDAT') data.push(chunk);
    offset += length + 12;
    if (type === 'IEND') break;
  }
  if (!width || !height || !channels || !data.length) throw new Error('Incomplete PNG');
  const raw = inflateSync(Buffer.concat(data));
  const stride = width * channels;
  if (raw.length !== height * (stride + 1)) throw new Error('Unexpected PNG scanline length');
  const pixels = Buffer.alloc(height * stride);
  const paeth = (a, b, c) => {
    const p = a + b - c, da = Math.abs(p - a), db = Math.abs(p - b), dc = Math.abs(p - c);
    return da <= db && da <= dc ? a : db <= dc ? b : c;
  };
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)];
    if (filter > 4) throw new Error(`Unknown PNG filter ${filter}`);
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? pixels[y * stride + x - channels] : 0;
      const b = y ? pixels[(y - 1) * stride + x] : 0;
      const c = y && x >= channels ? pixels[(y - 1) * stride + x - channels] : 0;
      const predictor = [0, a, b, Math.floor((a + b) / 2), paeth(a, b, c)][filter];
      pixels[y * stride + x] = (raw[y * (stride + 1) + x + 1] + predictor) & 255;
    }
  }
  return { width, height, channels, pixels };
}

/** Retain the full histogram for audit; receipts can display its top eight. */
export function histogramPng(bytes) {
  const { width, height, channels, pixels } = decodePng(bytes);
  const counts = new Map();
  for (let i = 0; i < pixels.length; i += channels) {
    const key = Array.from(pixels.subarray(i, i + 3)).join(',');
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const histogram = [...counts].map(([key, count]) => ({ rgb: key.split(',').map(Number), count }))
    .sort((a, b) => b.count - a.count || a.rgb[0] - b.rgb[0] || a.rgb[1] - b.rgb[1] || a.rgb[2] - b.rgb[2]);
  return { width, height, histogram };
}

/** Foreground is exclusively the device pixels changed by hiding this surface. */
export function foreground(paintedBytes, controlBytes, label, minimumModeFraction = .02) {
  const a = decodePng(paintedBytes), b = decodePng(controlBytes);
  if (a.width !== b.width || a.height !== b.height || a.channels !== b.channels)
    throw new Error(`Measurement failure ${label}: control dimensions differ`);
  const counts = new Map(); let maskSize = 0;
  for (let i = 0; i < a.pixels.length; i += a.channels) {
    if (a.pixels.subarray(i, i + a.channels).equals(b.pixels.subarray(i, i + b.channels))) continue;
    maskSize++;
    const key = Array.from(a.pixels.subarray(i, i + 3)).join(',');
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  const histogram = [...counts].map(([key, count]) => ({ rgb: key.split(',').map(Number), count }))
    .sort((a, b) => b.count - a.count || a.rgb[0] - b.rgb[0] || a.rgb[1] - b.rgb[1] || a.rgb[2] - b.rgb[2]);
  if (!maskSize) throw new Error(`Measurement failure ${label}: empty foreground mask`);
  const modeFraction = histogram[0].count / maskSize;
  if (modeFraction < minimumModeFraction)
    throw new Error(`Measurement failure ${label}: weak foreground mask; mode=${modeFraction.toFixed(6)} < ${minimumModeFraction}; top8=${JSON.stringify(histogram.slice(0, 8))}`);
  return { painted: histogram[0].rgb, maskSize, modeFraction, histogram: histogram.slice(0, 8),
    width: a.width, height: a.height };
}
