// Draws the extension icons (the app's blue "H" mark) into static/icons/. Run once after changing
// the design: `node scripts/make-icons.mjs`. Plain Node: a tiny PNG writer, 4x4 supersampling.
import { mkdir, writeFile } from "node:fs/promises";
import { deflateSync } from "node:zlib";

const ACCENT = [0x8f, 0xa8, 0xff];
const INK = [0x0d, 0x0e, 0x10];
const SS = 4;

/** Coverage of the shape at (x, y) in a 0..1 square: 0 outside, 1 background, 2 the letter. */
function shape(x, y) {
  const r = 0.22; // corner radius of the rounded square
  const cx = Math.min(Math.max(x, r), 1 - r);
  const cy = Math.min(Math.max(y, r), 1 - r);
  if ((x - cx) ** 2 + (y - cy) ** 2 > r * r) return 0;
  const stem = 0.13;
  const inLetter =
    y >= 0.24 && y <= 0.76 &&
    ((x >= 0.27 && x <= 0.27 + stem) || (x >= 0.73 - stem && x <= 0.73) || (y >= 0.44 && y <= 0.56 && x >= 0.27 && x <= 0.73));
  return inLetter ? 2 : 1;
}

function draw(size) {
  const rows = [];
  for (let py = 0; py < size; py++) {
    const row = Buffer.alloc(1 + size * 4); // filter byte 0, then RGBA
    for (let px = 0; px < size; px++) {
      let bg = 0;
      let ink = 0;
      for (let sy = 0; sy < SS; sy++) {
        for (let sx = 0; sx < SS; sx++) {
          const s = shape((px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size);
          if (s === 1) bg++;
          if (s === 2) ink++;
        }
      }
      const covered = bg + ink;
      const i = 1 + px * 4;
      if (covered) {
        for (let c = 0; c < 3; c++) row[i + c] = Math.round((ACCENT[c] * bg + INK[c] * ink) / covered);
      }
      row[i + 3] = Math.round((covered / (SS * SS)) * 255);
    }
    rows.push(row);
  }
  return png(size, Buffer.concat(rows));
}

function png(size, raw) {
  const chunk = (type, data) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const out = Buffer.alloc(8 + data.length + 4);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc32(body), 8 + data.length);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8); // 8-bit RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function crc32(buf) {
  let c = ~0;
  for (const byte of buf) {
    c ^= byte;
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return ~c >>> 0;
}

await mkdir("static/icons", { recursive: true });
for (const size of [16, 32, 48, 128]) {
  await writeFile(`static/icons/${size}.png`, draw(size));
}
console.log("wrote static/icons/{16,32,48,128}.png");
