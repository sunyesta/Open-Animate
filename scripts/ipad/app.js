/* Open Animate's drawing page for the iPad (Window > Draw on iPad... on the PC; scripts/modules/oanim/ipad.py is the
 * other side). The Pencil draws, fingers pan, zoom and turn the canvas; two fingers tapped undo, three redo. Each
 * stroke's samples go to Open Animate, whose own Stroke Pen makes the line and sends it back as it grows, so the line
 * shown is the line it will be; the canvas comes back as the frame's SVG once the stroke is in. The header and the
 * shelf are the PC's Draw header and shelf, both ways. */
'use strict';

const $ = (id) => document.getElementById(id);
const art = $('art'), overlay = $('overlay'), dabsCanvas = $('dabs'), view = $('view');
const toolStrip = $('tool-strip'), sharedStrip = $('shared-strip'), shelfTabs = $('shelf-tabs'), shelfTiles = $('shelf-tiles');
const popoverLayer = $('popover-layer');

/* ---------------------------------------------------------------------------------------------------------------
 * The connection: the one-time key from the QR code's address. */

const params = new URLSearchParams(location.search);
const KEY = params.get('k') || localStorage.getItem('oa-key') || '';
if (params.get('k')) {
  try { localStorage.setItem('oa-key', KEY); } catch (e) { /* private browsing */ }
}

let ws = null, connected = false, state = null, tiles = {}, tileSize = 64;
let retry = 500;

function connect() {
  $('connect-screen').hidden = false;
  $('connect-text').textContent = KEY ? 'Connecting to Open Animate' : 'Scan the QR code in Open Animate';
  if (!KEY) return;
  ws = new WebSocket(`ws://${location.host}/ws?k=${encodeURIComponent(KEY)}`);
  ws.onopen = () => { connected = true; retry = 500; };
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (err) { return; }
    receive(m);
  };
  ws.onclose = () => {
    connected = false;
    penCancel(false);
    strokes = [];
    dirty();
    $('connect-screen').hidden = false;
    $('connect-text').textContent = 'Not connected: is Draw on iPad still on in Open Animate?';
    setTimeout(connect, retry);
    retry = Math.min(retry * 2, 5000);
  };
}

function send(m) {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify(m));
}

/* ---------------------------------------------------------------------------------------------------------------
 * The view: canvas pixels to the screen, x' = a x + c y + e, y' = b x + d y + f. */

let canvasW = 0, canvasH = 0, docHeight = 1080;
let V = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
let fitted = false;

const apply = (m, x, y) => [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f];
const zoomOf = (m) => Math.hypot(m.a, m.b);
function invert(m) {
  const det = m.a * m.d - m.b * m.c || 1e-9;
  return { a: m.d / det, b: -m.b / det, c: -m.c / det, d: m.a / det,
           e: (m.c * m.f - m.d * m.e) / det, f: (m.b * m.e - m.a * m.f) / det };
}
function multiply(p, q) {
  return { a: p.a * q.a + p.c * q.b, b: p.b * q.a + p.d * q.b, c: p.a * q.c + p.c * q.d, d: p.b * q.c + p.d * q.d,
           e: p.a * q.e + p.c * q.f + p.e, f: p.b * q.e + p.d * q.f + p.f };
}

function fitView() {
  const top = toolStrip.getBoundingClientRect().bottom || 0;
  const bottom = $('shelf').getBoundingClientRect().top || innerHeight;
  const w = innerWidth, h = Math.max(bottom - top, 50);
  const s = Math.min(w / canvasW, h / canvasH) * 0.92;
  V = { a: s, b: 0, c: 0, d: s, e: (w - canvasW * s) / 2, f: top + (h - canvasH * s) / 2 };
  applyView();
}

function applyView() {
  art.style.transform = `matrix(${V.a},${V.b},${V.c},${V.d},${V.e},${V.f})`;
  dirty();
}

/* ---------------------------------------------------------------------------------------------------------------
 * Drawing what isn't the canvas's SVG: onion skins, the line being drawn, the pen's tip, the width circle. */

let onion = [];
/* The lines drawn here that the canvas doesn't show yet, oldest first: the one being drawn and those lifted whose
 * canvas hasn't come (Open Animate sends none while a line is being drawn, so lines drawn fast one after another wait
 * for it together). Each is the line as Open Animate has made it so far, and raw, the samples sent: those it hasn't
 * answered yet are drawn as the pen's tip until it is done with the line. done is the count of strokes the canvas
 * must have made to show it. */
let strokes = [];
let strokeSeq = 0;
let live = null;         // the line being drawn
function newStroke(erasing) {
  return { id: ++strokeSeq, kind: '', color: [0, 0, 0, 1], pts: [], own: false, dabs: new Map(), n: 0, raw: [], erasing, done: null };
}
function strokeById(id) {
  return strokes.find((s) => s.id === id);
}
function strokeDrop(s) {
  strokes = strokes.filter((x) => x !== s);
  if (live === s) live = null;
  dirty();
}
let hover = null;        // the Pencil hovering: [x, y] on the screen
let drawQueued = false;

function dirty() {
  if (!drawQueued) {
    drawQueued = true;
    requestAnimationFrame(redraw);
  }
}

function sizeCanvases() {
  const dpr = devicePixelRatio || 1;
  for (const c of [overlay, dabsCanvas]) {
    const w = Math.round(innerWidth * dpr), h = Math.round(innerHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
  }
  dirty();
}

function rgba(c, alpha = 1) {
  return `rgba(${Math.round(c[0] * 255)},${Math.round(c[1] * 255)},${Math.round(c[2] * 255)},${c[3] * alpha})`;
}

/* A line of varying width (flat [x, y, half width, opacity] in `m`'s space), round at every point as the renderer's:
 * capsules filled together, each run of one opacity at once so they don't darken where they overlap. */
function drawVarLine(ctx, pts, color, m, stride = 4) {
  const n = Math.floor(pts.length / stride);
  if (n === 0) return;
  const z = zoomOf(m);
  const level = (i) => (stride > 3 ? Math.round(Math.min(Math.max(pts[i * stride + 3], 0), 1) * 32) / 32 : 1);
  let i = 0;
  while (i < n) {
    const o = level(i);
    ctx.beginPath();
    let j = i;
    for (; j < n; j++) {
      if (j > i && level(j) !== o) break;
      const [x0, y0] = apply(m, pts[j * stride], pts[j * stride + 1]);
      const r0 = Math.max(pts[j * stride + 2] * z, 0.35);
      ctx.moveTo(x0 + r0, y0);
      ctx.arc(x0, y0, r0, 0, Math.PI * 2, false);
      if (j + 1 < n) {
        const [x1, y1] = apply(m, pts[(j + 1) * stride], pts[(j + 1) * stride + 1]);
        const r1 = Math.max(pts[(j + 1) * stride + 2] * z, 0.35);
        const dx = x1 - x0, dy = y1 - y0, len = Math.hypot(dx, dy);
        if (len > 1e-6) {
          const nx = -dy / len, ny = dx / len;
          let q = [[x0 + nx * r0, y0 + ny * r0], [x1 + nx * r1, y1 + ny * r1], [x1 - nx * r1, y1 - ny * r1], [x0 - nx * r0, y0 - ny * r0]];
          let area = 0;
          for (let k = 0; k < 4; k++) {
            const p = q[k], s = q[(k + 1) % 4];
            area += p[0] * s[1] - s[0] * p[1];
          }
          /* One way round, as the arcs go, so filled together they make one shape (nonzero). */
          if (area < 0) q = q.reverse();
          ctx.moveTo(q[0][0], q[0][1]);
          for (let k = 1; k < 4; k++) ctx.lineTo(q[k][0], q[k][1]);
          ctx.closePath();
        }
      }
    }
    ctx.fillStyle = rgba(color, o);
    ctx.fill('nonzero');
    /* The next run starts where this one stopped, so the line has no gap. */
    i = j === i ? i + 1 : j;
  }
}

function penHalfWidth() {
  /* The line's half width in canvas pixels, as the header has it (the tip drawn before Open Animate's line comes). */
  if (!state) return 1;
  const z = zoomOf(V);
  const px = state.settings.size_view ? state.size_px / z : state.size_px * canvasH / docHeight;
  return Math.max(px * 0.5, 0.5);
}

/* A brushed line's tip ([x, y, half width, opacity] in canvas pixels) as stamps of the brush (the brush button's
 * preview says which images and how they're laid), added to `out` as a line of dabs; false for a plain line. */
function stampsTip(s, tip, out) {
  const b = brushPreview;
  if (!state || state.mode !== 'FREEHAND' || !b || b.kind !== 'dabs' || !b.tip || !b.images.length) return false;
  const t = b.tip, ids = b.images.map((im) => String(im.id));
  const c = state.settings.line_color, alpha = c[3];
  const col = b.own ? [alpha, alpha, alpha, alpha] : [c[0] * alpha, c[1] * alpha, c[2] * alpha, alpha];
  const dabs = new Map();
  const u0 = t.flip_x ? 1 : 0, u1 = 1 - u0, v0 = t.flip_y ? 1 : 0, v1 = 1 - v0;
  /* `since`: how far the line has gone since the last stamp (the line sent back has the ones before the tip). */
  let k = 0, since = s.n > 0 ? 0 : Infinity;
  const stamp = (x, y, h, angle) => {
    const i = k++ % ids.length, aspect = t.aspects[i] > 0 ? t.aspects[i] : 1, size = 2 * h;
    const hx = aspect >= 1 ? size * 0.5 : size * 0.5 * aspect;
    const hy = (aspect >= 1 ? size * 0.5 / aspect : size * 0.5) * t.roundness;
    const ca = Math.cos(angle), sa = Math.sin(angle);
    const ax = [ca * hx, sa * hx], ay = [-sa * hy, ca * hy];
    const v = (px, py, u, w) => [px, py, u, w, ...col];
    const tl = v(x - ax[0] + ay[0], y - ax[1] + ay[1], u0, v0), tr = v(x + ax[0] + ay[0], y + ax[1] + ay[1], u1, v0);
    const br = v(x + ax[0] - ay[0], y + ax[1] - ay[1], u1, v1), bl = v(x - ax[0] - ay[0], y - ax[1] - ay[1], u0, v1);
    const list = dabs.get(ids[i]) || [];
    list.push(...tl, ...tr, ...br, ...tl, ...br, ...bl);
    dabs.set(ids[i], list);
  };
  for (let j = 0; j + 4 <= tip.length; j += 4) {
    const x = tip[j], y = tip[j + 1], h = tip[j + 2];
    const nx = j + 8 <= tip.length ? tip[j + 4] : x, ny = j + 8 <= tip.length ? tip[j + 5] : y;
    const len = Math.hypot(nx - x, ny - y), dir = Math.atan2(ny - y, nx - x);
    const angle = t.angle + (t.align ? dir : 0);
    const step = Math.max(t.spacing * 2 * h, 0.5);
    if (since >= step) { stamp(x, y, h, angle); since = 0; }
    /* Along the segment to the next sample, a stamp each step. */
    let last = -since;
    for (let d = step - since; d < len; d += step) {
      stamp(x + (nx - x) * d / len, y + (ny - y) * d / len, h, angle);
      last = d;
    }
    since = len - last;
  }
  out.push({ dabs, own: b.own });
  return true;
}

function redraw() {
  drawQueued = false;
  const dpr = devicePixelRatio || 1;
  const ctx = overlay.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, overlay.width, overlay.height);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  /* Onion skins, as the viewport's wires. */
  ctx.lineWidth = 1.4;
  ctx.lineJoin = 'round';
  for (const ghost of onion) {
    ctx.strokeStyle = rgba(ghost.c);
    ctx.beginPath();
    for (const line of ghost.lines) {
      for (let i = 0; i + 1 < line.length; i += 2) {
        const [x, y] = apply(V, line[i], line[i + 1]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
    }
    ctx.stroke();
  }
  /* The lines drawn, as Open Animate makes them. */
  for (const s of strokes) if (s.kind === 'line') drawVarLine(ctx, s.pts, s.color, V);
  /* What the pen has drawn since: the samples Open Animate hasn't answered yet, at the line's width; a brushed line's
   * stamped as the brush stamps, so it doesn't show as a plain line until the line comes back. */
  const half = penHalfWidth();
  const usePressure = state && state.settings.use_pressure;
  const minSize = state ? state.settings.min_size : 0;
  const tipDabs = [];
  for (const s of strokes) {
    if (s.done !== null || s.raw.length === 0) continue;
    const tip = [];
    for (let i = Math.max(0, s.n - 1); i < s.raw.length; i++) {
      const p = s.raw[i];
      tip.push(p[0], p[1], half * (usePressure ? Math.max(p[2], minSize) : 1), 1);
    }
    if (!s.erasing && stampsTip(s, tip, tipDabs)) continue;
    const c = state ? (s.erasing ? [0.9, 0.3, 0.3, 0.4] : state.mode === 'FILL_PEN' ? state.settings.fill_color : state.settings.line_color) : [0, 0, 0, 1];
    drawVarLine(ctx, tip, c, V);
  }
  drawDabs(dabRenderer, strokes.filter((s) => s.kind === 'dabs').concat(tipDabs), V, innerWidth, innerHeight);
  /* The width circle round the hovering Pencil. */
  if (hover && state && state.settings.cursor_circle && !penDown) {
    const r = penHalfWidth() * zoomOf(V);
    if (r >= 1.5) {
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(0,0,0,0.67)';
      ctx.beginPath(); ctx.arc(hover[0], hover[1], r, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = 'rgba(255,255,255,0.67)';
      ctx.beginPath(); ctx.arc(hover[0], hover[1], r + 1, 0, Math.PI * 2); ctx.stroke();
    }
  }
}

/* ---------------------------------------------------------------------------------------------------------------
 * A brushed line's stamps: the triangles Open Animate lays them out as, textured with the brush's pictures. */

const brushImages = new Map();   // image id -> HTMLImageElement

function addPngs(pngs) {
  for (const id in pngs) {
    if (brushImages.has(id)) continue;
    const img = new Image();
    img.onload = () => { dirty(); renderBrushButton(); };
    img.src = 'data:image/png;base64,' + pngs[id];
    brushImages.set(id, img);
  }
}

class DabRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = this.gl = canvas.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: true });
    if (!gl) return;
    const vs = `attribute vec2 p; attribute vec2 uv; attribute vec4 col; uniform mat3 m;
      varying vec2 v_uv; varying vec4 v_col;
      void main() { vec3 q = m * vec3(p, 1.0); gl_Position = vec4(q.xy, 0.0, 1.0); v_uv = uv; v_col = col; }`;
    const fs = `precision mediump float; uniform sampler2D tex; uniform float own; varying vec2 v_uv; varying vec4 v_col;
      void main() { vec4 t = texture2D(tex, v_uv); gl_FragColor = own > 0.5 ? t * v_col.a : t.a * v_col; }`;
    const shader = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = this.prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, vs));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(prog);
    this.loc = { p: gl.getAttribLocation(prog, 'p'), uv: gl.getAttribLocation(prog, 'uv'), col: gl.getAttribLocation(prog, 'col'),
                 m: gl.getUniformLocation(prog, 'm'), own: gl.getUniformLocation(prog, 'own') };
    this.buffer = gl.createBuffer();
    this.textures = new Map();
  }
  texture(id) {
    const gl = this.gl;
    if (this.textures.has(id)) return this.textures.get(id);
    const img = brushImages.get(String(id));
    if (!img || !img.complete || !img.naturalWidth) return null;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.textures.set(id, t);
    return t;
  }
}

/* Lines' stamps ([{dabs, own}], oldest first), over each other in that order. */
function drawDabs(r, lines, m, cssW, cssH) {
  if (!r || !r.gl) return;
  const gl = r.gl;
  gl.viewport(0, 0, r.canvas.width, r.canvas.height);
  gl.clearColor(0, 0, 0, 0);
  gl.clear(gl.COLOR_BUFFER_BIT);
  if (lines.length === 0) return;
  gl.useProgram(r.prog);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
  /* Canvas pixels to the screen (m), then to clip space. */
  const sx = 2 / cssW, sy = -2 / cssH;
  gl.uniformMatrix3fv(r.loc.m, false, new Float32Array([
    m.a * sx, m.b * sy, 0,
    m.c * sx, m.d * sy, 0,
    m.e * sx - 1, m.f * sy + 1, 1]));
  gl.bindBuffer(gl.ARRAY_BUFFER, r.buffer);
  for (const line of lines) {
  gl.uniform1f(r.loc.own, line.own ? 1 : 0);
  for (const [id, verts] of line.dabs) {
    const t = r.texture(id);
    if (!t || verts.length < 48) continue;
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(verts), gl.STREAM_DRAW);
    gl.enableVertexAttribArray(r.loc.p);
    gl.vertexAttribPointer(r.loc.p, 2, gl.FLOAT, false, 32, 0);
    gl.enableVertexAttribArray(r.loc.uv);
    gl.vertexAttribPointer(r.loc.uv, 2, gl.FLOAT, false, 32, 8);
    gl.enableVertexAttribArray(r.loc.col);
    gl.vertexAttribPointer(r.loc.col, 4, gl.FLOAT, false, 32, 16);
    gl.drawArrays(gl.TRIANGLES, 0, Math.floor(verts.length / 8));
  }
  }
}

const dabRenderer = new DabRenderer(dabsCanvas);

/* A "live" body into `into`: what's kept of what was sent, then what's added. */
function liveUpdate(into, m) {
  if (m.kind !== into.kind) {
    into.pts = [];
    into.dabs = new Map();
  }
  into.kind = m.kind;
  if (m.kind === 'line') {
    into.color = m.color;
    into.pts.length = Math.min(m.keep, into.pts.length);
    for (const v of m.add) into.pts.push(v);
  }
  else if (m.kind === 'dabs') {
    into.own = m.own;
    addPngs(m.pngs || {});
    const seen = new Set();
    for (const im of m.images) {
      const key = String(im.id);
      seen.add(key);
      let arr = into.dabs.get(key) || [];
      arr.length = Math.min(im.keep * 8, arr.length);
      for (const v of im.add) arr.push(v);
      into.dabs.set(key, arr);
    }
    for (const key of [...into.dabs.keys()]) if (!seen.has(key)) into.dabs.delete(key);
  }
}


/* ---------------------------------------------------------------------------------------------------------------
 * The Pencil: it draws, and only it. This iPad's own pressure curve (Options > Pencil) goes first. */

let penDown = false, penId = -1, penErasing = false, penRefused = false;

function pencilCurve() {
  try {
    const c = JSON.parse(localStorage.getItem('oa-pencil-curve'));
    if (Array.isArray(c) && c.length === 4) return c;
  } catch (e) { /* none kept */ }
  return [0.25, 0.25, 0.75, 0.75];
}
let pencil = pencilCurve();

/* y at x on the curve from (0, 0) to (1, 1) through handles (ax, ay) and (bx, by). */
function curveAt(c, x) {
  const bez = (t, p1, p2) => 3 * (1 - t) * (1 - t) * t * p1 + 3 * (1 - t) * t * t * p2 + t * t * t;
  let lo = 0, hi = 1;
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (bez(mid, c[0], c[2]) < x) lo = mid; else hi = mid;
  }
  return Math.min(Math.max(bez((lo + hi) / 2, c[1], c[3]), 0), 1);
}

function sampleOf(e) {
  const inv = invert(V);
  const r = view.getBoundingClientRect();
  const [x, y] = apply(inv, e.clientX - r.left, e.clientY - r.top);
  let p = e.pointerType === 'mouse' ? 1 : e.pressure;
  if (!(p > 0)) p = penDown ? 0.01 : 0.5;
  p = curveAt(pencil, Math.min(Math.max(p, 0), 1));
  return [round2(x), round2(y), Math.round(p * 1000) / 1000, e.tiltX || 0, -(e.tiltY || 0), e.timeStamp / 1000];
}
const round2 = (v) => Math.round(v * 100) / 100;

function coalesced(e) {
  const list = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
  return list.length ? list : [e];
}

function penStart(e) {
  if (penDown) return;
  closePopovers();
  if (!state || state.refused) {
    flashBanner(state ? state.refused : 'Not connected');
    penRefused = true;
    return;
  }
  penDown = true;
  penRefused = false;
  penId = e.pointerId;
  penErasing = e.button === 5 || (e.buttons & 32) !== 0 || erasing();
  live = newStroke(penErasing);
  strokes.push(live);
  const s = coalesced(e).map(sampleOf);
  live.raw.push(...s);
  send({ t: 'down', id: live.id, eraser: penErasing, zoom: zoomOf(V), s });
  dirty();
}

function penMove(e) {
  if (!penDown || e.pointerId !== penId) return;
  const s = coalesced(e).map(sampleOf);
  if (live) live.raw.push(...s);
  send({ t: 'move', s });
  dirty();
}

function penEnd(e) {
  if (!penDown || e.pointerId !== penId) return;
  penDown = false;
  live = null;
  /* Lifting isn't a sample (its pressure is 0): the line ends where the last one was, as the viewport's does. */
  send({ t: 'up', s: [] });
  dirty();
}

function penCancel(tell = true) {
  if (!penDown) return;
  penDown = false;
  if (tell) send({ t: 'cancel' });
  if (live) strokeDrop(live);
}

/* ---------------------------------------------------------------------------------------------------------------
 * Erasing. The button at the right edge swaps the pen for its eraser (the Stroke Pen's and the Bezier Pen's Stroke
 * Eraser, the Fill Pen's Fill Eraser) and, tapped again, back to the pen it was. A finger held still anywhere on the
 * canvas erases while it stays, as Ctrl does on the PC: the strokes drawn meanwhile take the pen's matching eraser. */

const ERASES = ['FREEHAND', 'FILL_PEN'];
const HOLD_MS = 300, HOLD_SLIP = 15;  // a finger held this long without going further than this (px) holds
const PALM_PX = 100;                  // a touch wider than this is a hand resting, never a held finger
const eraseHolds = new Set();        // the fingers resting on the canvas
const eraseButton = $('erase-button');
let eraseBack = null;                // the pen the button swapped from: {preset, mode}

const erases = () => !!state && ERASES.includes(state.mode);
const erasing = () => erases() && eraseHolds.size > 0;

/* The shelf's first pen of a mode. */
const presetOf = (mode) => state.presets.find((p) => p.mode === mode);

function eraserFor(mode) {
  return presetOf(mode === 'FILL_PEN' ? 'FILL_ERASER' : 'STROKE_ERASER');
}

function eraseShow() {
  if (!state) return;
  const cut = CUTS.includes(state.mode);
  eraseButton.hidden = state.tool !== 'DRAW' || (!cut && !eraserFor(state.mode));
  eraseButton.classList.toggle('on', cut || erasing());
  eraseButton.title = cut ? 'Back to the pen' : state.mode === 'FILL_PEN' ? 'Swap to the Fill Eraser' : 'Swap to the Stroke Eraser';
}

function eraseHold(id, on) {
  if (on) eraseHolds.add(id);
  else eraseHolds.delete(id);
  eraseShow();
}

function eraseSwap() {
  if (!state) return;
  if (CUTS.includes(state.mode)) {
    /* Back to the pen swapped from, or (an eraser picked on the shelf) the shelf's pen of its kind. */
    const back = eraseBack && (state.presets.find((p) => p.name === eraseBack.preset && p.mode === eraseBack.mode)
                               || presetOf(eraseBack.mode));
    const pen = back || presetOf(state.mode === 'FILL_ERASER' ? 'FILL_PEN' : 'FREEHAND');
    eraseBack = null;
    if (pen) send({ t: 'preset', name: pen.name });
    return;
  }
  const eraser = eraserFor(state.mode);
  if (!eraser) return;
  eraseBack = { preset: state.preset, mode: state.mode };
  send({ t: 'preset', name: eraser.name });
}

eraseButton.addEventListener('pointerdown', (e) => {
  e.stopPropagation();
  e.preventDefault();
  closePopovers();
  eraseSwap();
});

/* ---------------------------------------------------------------------------------------------------------------
 * The input log: the canvas's last pointer and touch events and what was made of them, sent to the PC (Options > Send
 * Input Log) for finding out what this iPad's Safari sends. */

const inputLog = [];
const LOG_MAX = 1500;
function logInput(...entry) {
  inputLog.push([Math.round(performance.now()), ...entry]);
  if (inputLog.length > LOG_MAX) inputLog.splice(0, inputLog.length - LOG_MAX);
}
const r1 = (v) => (typeof v === 'number' ? Math.round(v * 10) / 10 : v);
for (const type of ['pointerdown', 'pointermove', 'pointerup', 'pointercancel']) {
  view.addEventListener(type, (e) => logInput(type, e.pointerType, e.pointerId, r1(e.clientX), r1(e.clientY), r1(e.width),
                                              r1(e.pressure), e.buttons), { capture: true });
}
for (const type of ['touchstart', 'touchmove', 'touchend', 'touchcancel']) {
  view.addEventListener(type, (e) => {
    for (const t of e.changedTouches) {
      logInput(type, t.touchType || '', t.identifier, r1(t.clientX), r1(t.clientY), r1(t.radiusX), r1(t.force),
               e.touches.length);
    }
  }, { capture: true });
}

/* ---------------------------------------------------------------------------------------------------------------
 * Safari's pointer events take one kind of input at a time: with a finger down the Pencil's never come, and with the
 * Pencil down a finger's never do. Touch events carry every touch, so they find the fingers held still, and while a
 * finger is down they draw the Pencil's strokes (with no coalesced samples, so only then). */

const fingers = new Map();   // touch identifier -> {x0, y0, slid, palm, hold, timer}
let touchPen = null;         // the Pencil's touch identifier while its stroke comes from touch events

/* A touch as a pointer event, for the pen's own functions. */
function touchAsPointer(t, e) {
  /* altitudeAngle: 0 flat on the glass, pi/2 upright; azimuthAngle, which way it leans. */
  const alt = t.altitudeAngle, az = t.azimuthAngle || 0;
  const lean = alt > 0 && alt < Math.PI / 2 ? 1 / Math.tan(alt) : 0;
  const deg = 180 / Math.PI;
  return { pointerId: 'touch' + t.identifier, pointerType: 'pen', button: 0, buttons: 1, clientX: t.clientX,
           clientY: t.clientY, pressure: Math.min(Math.max(t.force || 0, 0), 1), tiltX: Math.round(Math.atan(Math.cos(az) * lean) * deg),
           tiltY: Math.round(Math.atan(Math.sin(az) * lean) * deg), timeStamp: e.timeStamp };
}

/* A finger still where it went down: it holds the eraser on until lifted. Two resting with no stroke drawn are a pinch
 * about to start; a finger the pointer events see too stops panning, the view going back to where it was. */
function fingerRest(id) {
  const f = fingers.get(id);
  logInput('rest', id, !f ? 'gone' : f.palm ? 'palm' : f.slid ? 'slid' : !erases() ? 'no eraser' : 'ok', penDown);
  if (!f || f.palm || f.slid || !erases()) return;
  if (!penDown && [...fingers.values()].some((o) => o !== f && !o.hold)) { logInput('rest', id, 'pinch'); return; }
  f.hold = true;
  let near = null, best = 40;
  for (const t of touches.values()) {
    const d = Math.hypot(t.x0 - f.x0, t.y0 - f.y0);
    if (!t.hold && d < best) { best = d; near = t; }
  }
  if (near) {
    near.hold = true;
    V = near.V;
    applyView();
    tap = null;
    reanchor();
  }
  eraseHold('finger' + id, true);
}

function fingerGone(id) {
  const f = fingers.get(id);
  if (!f) return;
  clearTimeout(f.timer);
  fingers.delete(id);
  if (f.hold) eraseHold('finger' + id, false);
}

view.addEventListener('touchstart', (e) => {
  for (const t of e.changedTouches) {
    if (t.touchType === 'stylus') {
      if (!penDown && fingers.size > 0) {
        penStart(touchAsPointer(t, e));
        if (penDown) touchPen = t.identifier;
        logInput('touch pen', t.identifier, penDown);
      }
      continue;
    }
    const f = { x0: t.clientX, y0: t.clientY, slid: false, hold: false,
                palm: 2 * Math.max(t.radiusX || 0, t.radiusY || 0) > PALM_PX };
    f.timer = setTimeout(() => fingerRest(t.identifier), HOLD_MS);
    fingers.set(t.identifier, f);
  }
});
view.addEventListener('touchmove', (e) => {
  for (const t of e.changedTouches) {
    if (t.identifier === touchPen) penMove(touchAsPointer(t, e));
    const f = fingers.get(t.identifier);
    if (f && Math.hypot(t.clientX - f.x0, t.clientY - f.y0) > HOLD_SLIP) f.slid = true;
  }
});
const touchLift = (e) => {
  for (const t of e.changedTouches) {
    if (t.identifier === touchPen) {
      touchPen = null;
      if (e.type === 'touchend') penEnd(touchAsPointer(t, e));
      else penCancel();
      penRefused = false;
    }
    fingerGone(t.identifier);
  }
};
view.addEventListener('touchend', touchLift);
view.addEventListener('touchcancel', touchLift);

/* ---------------------------------------------------------------------------------------------------------------
 * Fingers: one pans, two pan, zoom and turn; a quick tap of two undoes, of three redoes; one held still erases. */

const touches = new Map();
let anchor = null, tap = null;

function reanchor() {
  const pts = [...touches.values()].filter((t) => !t.hold);
  anchor = { V: { ...V }, pts: pts.slice(0, 2).map((t) => [t.x, t.y]) };
}

function touchDown(e) {
  closePopovers();
  /* A finger put down while the Pencil draws only ever holds the eraser on (for the next stroke). */
  const t = { x: e.clientX, y: e.clientY, x0: e.clientX, y0: e.clientY, hold: penDown, V: { ...V } };
  touches.set(e.pointerId, t);
  if (penDown) return;
  if (touches.size === 1) tap = { t0: performance.now(), most: 1, moved: false };
  else if (tap) tap.most = Math.max(tap.most, touches.size);
  art.classList.add('moving');
  reanchor();
}

function touchMove(e) {
  const t = touches.get(e.pointerId);
  if (!t) return;
  t.x = e.clientX;
  t.y = e.clientY;
  if (Math.hypot(t.x - t.x0, t.y - t.y0) > 10 && tap) tap.moved = true;
  if (!anchor || penDown || t.hold) return;
  const pts = [...touches.values()].filter((p) => !p.hold).slice(0, 2).map((p) => [p.x, p.y]);
  if (!pts.length) return;
  if (pts.length === 1 || anchor.pts.length === 1) {
    const dx = pts[0][0] - anchor.pts[0][0], dy = pts[0][1] - anchor.pts[0][1];
    V = { ...anchor.V, e: anchor.V.e + dx, f: anchor.V.f + dy };
  }
  else {
    /* The similarity taking the two fingers where they were to where they are. */
    const [a0, b0] = anchor.pts, [a1, b1] = pts;
    const v0 = [b0[0] - a0[0], b0[1] - a0[1]], v1 = [b1[0] - a1[0], b1[1] - a1[1]];
    const l0 = Math.hypot(...v0) || 1, l1 = Math.hypot(...v1);
    let s = l1 / l0;
    const z = zoomOf(anchor.V);
    s = Math.min(Math.max(s, 0.02 / z), 64 / z);
    const ang = Math.atan2(v1[1], v1[0]) - Math.atan2(v0[1], v0[0]);
    const cos = Math.cos(ang) * s, sin = Math.sin(ang) * s;
    const g = { a: cos, b: sin, c: -sin, d: cos, e: 0, f: 0 };
    g.e = a1[0] - (g.a * a0[0] + g.c * a0[1]);
    g.f = a1[1] - (g.b * a0[0] + g.d * a0[1]);
    V = multiply(g, anchor.V);
  }
  applyView();
}

function touchUp(e) {
  if (!touches.has(e.pointerId)) return;
  touches.delete(e.pointerId);
  if ([...touches.values()].some((t) => !t.hold)) {
    reanchor();
    return;
  }
  anchor = null;
  art.classList.remove('moving');
  if (tap && !tap.moved && performance.now() - tap.t0 < 350 && !penDown) {
    if (tap.most === 2) { send({ t: 'undo' }); toast('Undo'); }
    else if (tap.most === 3) { send({ t: 'redo' }); toast('Redo'); }
  }
  tap = null;
}

view.addEventListener('pointerdown', (e) => {
  try { view.setPointerCapture(e.pointerId); } catch (err) { /* a pointer the browser doesn't know */ }
  if (e.pointerType === 'touch') touchDown(e);
  else if (e.button === 0 || e.button === 5) penStart(e);
});
view.addEventListener('pointermove', (e) => {
  if (e.pointerType === 'touch') { touchMove(e); return; }
  if (penDown) penMove(e);
  else if (e.pointerType === 'pen' || e.pointerType === 'mouse') {
    const r = view.getBoundingClientRect();
    hover = [e.clientX - r.left, e.clientY - r.top];
    if (state && state.settings.cursor_circle) dirty();
  }
});
const lift = (e) => {
  if (e.pointerType === 'touch') touchUp(e);
  else { if (penRefused) penRefused = false; penEnd(e); }
};
view.addEventListener('pointerup', lift);
view.addEventListener('pointercancel', (e) => {
  if (e.pointerType === 'touch') touchUp(e);
  else penCancel();
});
view.addEventListener('pointerleave', (e) => { if (e.pointerType !== 'touch' && !penDown) { hover = null; dirty(); } });
/* A mouse (testing on a computer): the wheel zooms about the pointer. */
view.addEventListener('wheel', (e) => {
  e.preventDefault();
  const r = view.getBoundingClientRect();
  const x = e.clientX - r.left, y = e.clientY - r.top;
  const s = Math.exp(-e.deltaY * 0.0015);
  V = multiply({ a: s, b: 0, c: 0, d: s, e: x - s * x, f: y - s * y }, V);
  applyView();
}, { passive: false });
document.addEventListener('gesturestart', (e) => e.preventDefault());
document.addEventListener('touchmove', (e) => { if (e.target.closest && !e.target.closest('#shelf-tiles, .popover')) e.preventDefault(); }, { passive: false });

/* ---------------------------------------------------------------------------------------------------------------
 * The canvas's SVG, kept as elements: a canvas sends the pieces the last one didn't have and the places of those it
 * did, and only what differs is put in, taken out or moved, so an undo doesn't lay out the whole drawing again. */

const SVG_NS = 'http://www.w3.org/2000/svg';
let canvasSeq = 0, canvasHead = '', svgRoot = null, defsEl = null, defsNodes = [], bodyNodes = [];

function parsePieces(texts) {
  if (texts.length === 0) return [];
  const doc = new DOMParser().parseFromString(canvasHead + texts.join('') + '</svg>', 'image/svg+xml');
  return [...doc.documentElement.children].map((n) => document.importNode(n, true));
}

/* `parent`'s children from `start` on made `nodes`, in order, touching only those out of place. */
function syncChildren(parent, nodes, start) {
  for (let i = 0; i < nodes.length; i++) {
    const at = parent.childNodes[start + i];
    if (at !== nodes[i]) parent.insertBefore(nodes[i], at || null);
  }
  while (parent.childNodes.length > start + nodes.length) parent.removeChild(parent.lastChild);
}

/* False when it was sent against a canvas this page doesn't have (the whole one is asked for). */
function canvasApply(m) {
  if (m.base !== 0 && m.base !== canvasSeq) {
    send({ t: 'canvas_full' });
    return false;
  }
  if (m.base === 0 || !svgRoot) {
    canvasHead = m.head;
    art.innerHTML = m.head.replace(/^<\?xml[^>]*>\s*/, '') + '</svg>';
    svgRoot = art.firstElementChild;
    defsEl = document.createElementNS(SVG_NS, 'defs');
    svgRoot.appendChild(defsEl);
    defsNodes = [];
    bodyNodes = [];
  }
  const build = (list, before) => {
    const fresh = parsePieces(list.filter((v) => typeof v === 'string'));
    const used = new Set();
    let k = 0;
    return list.map((v) => {
      if (typeof v === 'string') return fresh[k++];
      const n = before[v];
      if (used.has(n)) return n.cloneNode(true);
      used.add(n);
      return n;
    });
  };
  defsNodes = build(m.defs, defsNodes);
  bodyNodes = build(m.body, bodyNodes);
  syncChildren(defsEl, defsNodes, 0);
  if (svgRoot.firstChild !== defsEl) svgRoot.insertBefore(defsEl, svgRoot.firstChild);
  syncChildren(svgRoot, bodyNodes, 1);
  canvasSeq = m.seq;
  return true;
}

/* ---------------------------------------------------------------------------------------------------------------
 * Messages from Open Animate. */

function receive(m) {
  switch (m.t) {
    case 'state':
      state = m;
      $('connect-screen').hidden = true;
      docHeight = m.doc_height || docHeight;
      showState();
      break;
    case 'tiles':
      tileSize = m.size;
      tiles = {};
      for (const t of m.tiles) tiles[t.name] = t;
      buildShelf();
      break;
    case 'brush':
      brushPreview = m.preview;
      if (m.preview.kind === 'dabs') addPngs(m.preview.pngs || {});
      renderBrushButton();
      break;
    case 'canvas': {
      const changed = m.w !== canvasW || m.h !== canvasH;
      canvasW = m.w;
      canvasH = m.h;
      art.style.width = m.w + 'px';
      art.style.height = m.h + 'px';
      if (!canvasApply(m)) break;
      onion = m.onion || [];
      if (changed || !fitted) { fitted = true; fitView(); }
      /* The lines it has made show in it now. */
      if (m.strokes !== undefined) strokes = strokes.filter((s) => s.done === null || s.done > m.strokes);
      dirty();
      break;
    }
    case 'live': {
      const s = strokeById(m.id);
      if (!s) break;
      liveUpdate(s, m);
      s.n = m.n || s.n;
      dirty();
      break;
    }
    case 'done': {
      const s = strokeById(m.id);
      if (!s) break;
      if (m.undo) { s.done = m.count; dirty(); }
      else strokeDrop(s);
      break;
    }
    case 'refused': {
      const s = strokeById(m.id);
      if (s && s === live) penCancel(false);
      else if (s) strokeDrop(s);
      flashBanner(m.why);
      break;
    }
  }
}

/* ---------------------------------------------------------------------------------------------------------------
 * Banners and toasts. */

let bannerTimer = 0;
function flashBanner(text) {
  const b = $('banner');
  b.textContent = text;
  b.hidden = false;
  clearTimeout(bannerTimer);
  bannerTimer = setTimeout(() => showState(), 2200);
}
let toastTimer = 0;
function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 700);
}

/* ---------------------------------------------------------------------------------------------------------------
 * Widgets, as Blender's: number fields (drag across, tap to type), toggles, dropdowns with popovers. */

let interacting = 0;     // a field being dragged or typed in: the header waits to be rebuilt
let stateWaiting = false;

const el = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
};

function fmt(format, v) {
  return format.replace(/%\.(\d)f/, (_, d) => Number(v).toFixed(Number(d)));
}

function setValues(values) {
  send({ t: 'set', values });
}

/* A number field. `slider`: the fill shows where the value is in min..max. */
function numberField({ format, value, min, max, speed, slider = false, disabled = false, width = 0, onChange }) {
  const f = el('div', 'field' + (disabled ? ' disabled' : ''));
  if (width) f.style.width = width + 'px';
  const fill = el('div', 'fill');
  const label = el('div', 'label');
  f.append(fill, label);
  let v = value;
  const show = () => {
    label.textContent = fmt(format, v);
    fill.style.width = slider ? `${Math.min(Math.max((v - min) / (max - min), 0), 1) * 100}%` : '0';
  };
  show();
  if (disabled) return f;
  let start = null;
  f.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    f.setPointerCapture(e.pointerId);
    start = { x: e.clientX, v, moved: false, id: e.pointerId };
    interacting++;
  });
  f.addEventListener('pointermove', (e) => {
    if (!start || e.pointerId !== start.id) return;
    const dx = e.clientX - start.x;
    if (!start.moved && Math.abs(dx) < 6) return;
    start.moved = true;
    const step = slider ? (max - min) / Math.max(f.clientWidth, 1) : speed;
    v = Math.min(Math.max(start.v + dx * step, min), max);
    show();
    onChange(v);
  });
  const end = (e) => {
    if (!start || e.pointerId !== start.id) return;
    const moved = start.moved;
    start = null;
    interacting--;
    if (!moved) typeIn();
    else flushState();
  };
  f.addEventListener('pointerup', end);
  f.addEventListener('pointercancel', end);
  const typeIn = () => {
    interacting++;
    const input = el('input');
    input.type = 'text';
    input.inputMode = 'decimal';
    input.value = String(Math.round(v * 1000) / 1000);
    f.append(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (keep) => {
      if (done) return;
      done = true;
      const n = parseFloat(input.value);
      input.remove();
      if (keep && Number.isFinite(n)) {
        v = Math.min(Math.max(n, min), max);
        show();
        onChange(v);
      }
      interacting--;
      flushState();
    };
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') finish(true);
      if (e.key === 'Escape') finish(false);
    });
    input.addEventListener('blur', () => finish(true));
  };
  return f;
}

function toggle(label, on, onClick, tip, enabled = true) {
  const b = el('button', on ? 'on' : '', label);
  if (tip) b.title = tip;
  b.disabled = !enabled;
  b.addEventListener('click', (e) => { e.stopPropagation(); onClick(); });
  return b;
}

function check(label, on, onClick, enabled = true) {
  const c = el('div', 'check' + (on ? ' on' : '') + (enabled ? '' : ' disabled'));
  c.append(el('div', 'box'), el('span', '', label));
  if (enabled) c.addEventListener('click', (e) => { e.stopPropagation(); onClick(!on); });
  return c;
}

function joined(...items) {
  const j = el('div', 'joined');
  j.append(...items);
  return j;
}

let openPopover = null;
function closePopovers() {
  if (openPopover) {
    openPopover.el.remove();
    openPopover = null;
    flushState();
  }
}

/* A popover below `anchor`, its content made by `build` (made again as the settings change while it's open). */
function popover(anchor, id, build) {
  const wasOpen = openPopover && openPopover.id === id;
  closePopovers();
  if (wasOpen) return;
  const p = el('div', 'popover');
  build(p);
  popoverLayer.append(p);
  const r = anchor.getBoundingClientRect();
  let left = r.left;
  const width = p.offsetWidth;
  if (left + width > innerWidth - 8) left = Math.max(8, r.right - width);
  p.style.left = left + 'px';
  p.style.top = r.bottom + 4 + 'px';
  p.addEventListener('pointerdown', (e) => e.stopPropagation());
  openPopover = { el: p, id, anchor, build };
}
function popoverRefresh() {
  if (!openPopover) return;
  const p = openPopover.el;
  const scroll = p.scrollTop;
  p.replaceChildren();
  openPopover.build(p);
  p.scrollTop = scroll;
}
document.addEventListener('pointerdown', (e) => {
  if (openPopover && !openPopover.el.contains(e.target) && !openPopover.anchor.contains(e.target)) closePopovers();
});

function dropdown(label, id, tip, build) {
  const b = el('button', 'dropdown', label);
  if (tip) b.title = tip;
  b.addEventListener('click', (e) => { e.stopPropagation(); popover(b, id, build); });
  return b;
}

function withPressure(field, on, key, tip) {
  const w = el('div', 'with-pressure');
  const b = el('button', on ? 'on' : '');
  b.title = tip;
  b.append(el('div', 'pen-icon'));
  b.addEventListener('click', (e) => { e.stopPropagation(); setValues({ [key]: !on }); });
  w.append(field, b);
  return w;
}

function bar(format, value, min, max, onChange, disabled = false) {
  return numberField({ format, value, min, max, slider: true, disabled, onChange });
}

function panel(name, build) {
  const p = el('div', 'panel' + (panelsOpen.has(name) ? ' open' : ''));
  const head = el('div', 'panel-head', name);
  const body = el('div', 'panel-body');
  head.addEventListener('click', () => {
    if (panelsOpen.has(name)) panelsOpen.delete(name); else panelsOpen.add(name);
    p.classList.toggle('open');
  });
  build(body);
  p.append(head, body);
  return p;
}
const panelsOpen = new Set();

/* A curve from (0, 0) to (1, 1) through two handles, dragged about (the pressure curves). */
function curveEditor(curve, onChange) {
  const c = el('canvas', 'curve');
  let handles = curve.slice();
  const paint = () => {
    const dpr = devicePixelRatio || 1;
    const w = c.clientWidth || 230, h = c.clientHeight || 160;
    c.width = w * dpr;
    c.height = h * dpr;
    const ctx = c.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pad = 10, at = (x, y) => [pad + x * (w - 2 * pad), h - pad - y * (h - 2 * pad)];
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const [x0, y0] = at(i / 4, 0), [x1, y1] = at(i / 4, 1);
      ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
      const [a0, b0] = at(0, i / 4), [a1, b1] = at(1, i / 4);
      ctx.beginPath(); ctx.moveTo(a0, b0); ctx.lineTo(a1, b1); ctx.stroke();
    }
    const p0 = at(0, 0), p1 = at(handles[0], handles[1]), p2 = at(handles[2], handles[3]), p3 = at(1, 1);
    ctx.strokeStyle = '#777';
    ctx.beginPath(); ctx.moveTo(...p0); ctx.lineTo(...p1); ctx.moveTo(...p3); ctx.lineTo(...p2); ctx.stroke();
    ctx.strokeStyle = '#e6e6e6';
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(...p0); ctx.bezierCurveTo(...p1, ...p2, ...p3); ctx.stroke();
    ctx.fillStyle = '#4772b3';
    for (const p of [p1, p2]) { ctx.beginPath(); ctx.arc(p[0], p[1], 7, 0, Math.PI * 2); ctx.fill(); }
  };
  requestAnimationFrame(paint);
  let dragging = -1;
  const toCurve = (e) => {
    const r = c.getBoundingClientRect(), pad = 10;
    return [Math.min(Math.max((e.clientX - r.left - pad) / (r.width - 2 * pad), 0), 1),
            Math.min(Math.max(1 - (e.clientY - r.top - pad) / (r.height - 2 * pad), 0), 1)];
  };
  c.addEventListener('pointerdown', (e) => {
    e.stopPropagation();
    c.setPointerCapture(e.pointerId);
    const [x, y] = toCurve(e);
    dragging = Math.hypot(x - handles[0], y - handles[1]) <= Math.hypot(x - handles[2], y - handles[3]) ? 0 : 1;
    interacting++;
  });
  c.addEventListener('pointermove', (e) => {
    if (dragging < 0) return;
    const [x, y] = toCurve(e);
    handles[dragging * 2] = x;
    handles[dragging * 2 + 1] = y;
    paint();
    onChange(handles.slice());
  });
  const up = () => {
    if (dragging < 0) return;
    dragging = -1;
    interacting--;
    flushState();
  };
  c.addEventListener('pointerup', up);
  c.addEventListener('pointercancel', up);
  return c;
}

function swatch(color, tip, onChange) {
  const s = el('div', 'swatch');
  s.title = tip;
  const chip = el('div', 'chip');
  chip.style.background = rgba([color[0], color[1], color[2], 1]);
  const input = el('input');
  input.type = 'color';
  const hex = (v) => Math.round(Math.min(Math.max(v, 0), 1) * 255).toString(16).padStart(2, '0');
  input.value = '#' + hex(color[0]) + hex(color[1]) + hex(color[2]);
  input.addEventListener('focus', () => interacting++);
  input.addEventListener('input', () => {
    const v = input.value;
    const rgb = [1, 3, 5].map((i) => parseInt(v.substr(i, 2), 16) / 255);
    chip.style.background = v;
    onChange([...rgb, color[3]]);
  });
  input.addEventListener('blur', () => { interacting = Math.max(0, interacting - 1); flushState(); });
  s.append(chip, input);
  return s;
}

/* ---------------------------------------------------------------------------------------------------------------
 * The header: the PC's Draw header (draw_header and draw_shared_buttons in viewport.cc), the same buttons. */

const CUTS = ['FILL_ERASER', 'STROKE_ERASER', 'TRIMMER'];
let brushPreview = null, brushCanvas = null, brushRenderer = null;

function showState() {
  if (!state) return;
  $('switch-screen').hidden = state.tool === 'DRAW';
  const b = $('banner');
  if (state.tool === 'DRAW' && state.refused) {
    b.textContent = state.refused;
    b.hidden = false;
  }
  else if (!bannerTimer || b.hidden) b.hidden = true;
  bannerTimer = 0;
  eraseShow();
  if (interacting > 0) {
    stateWaiting = true;
    return;
  }
  buildHeader();
  buildShelf();
  popoverRefresh();
}

function flushState() {
  if (interacting === 0 && stateWaiting) {
    stateWaiting = false;
    buildHeader();
    buildShelf();
    popoverRefresh();
  }
}

function buildHeader() {
  const s = state.settings, mode = state.mode;
  const bezier = mode === 'PEN', fillPen = mode === 'FILL_PEN', eraser = CUTS.includes(mode);
  const left = [];
  if (!fillPen && !eraser) left.push(brushButton());
  /* Size, its pressure toggle with every pen but the Bezier Pen. */
  const paints = ['FILL_PEN', 'FILL_ERASER', 'STROKE_ERASER', 'TRIMMER'].includes(mode);
  const sizeTip = s.size_view ? 'How wide the line is on screen, whatever the zoom'
    : paints ? "How wide the brush is, in pixels of the document's height"
      : "How wide the line is, in pixels of the document's height";
  const size = numberField({ format: state.size_format, value: state.size_px, min: 0, max: 500, speed: 0.1,
                             width: bezier ? 130 : 150, onChange: (v) => setValues({ size_px: v }) });
  size.title = sizeTip;
  left.push(bezier ? size : withPressure(size, s.use_pressure, 'use_pressure', 'Pen pressure sets the size'));
  if (!eraser) {
    const linePressure = mode === 'FREEHAND';
    const op = numberField({ format: 'Opacity %.2f', value: state.opacity, min: 0, max: 1, slider: true,
                             width: linePressure ? 140 : 130, onChange: (v) => setValues({ opacity: v }) });
    op.title = fillPen ? 'How solid the fill is' : 'How solid the line is';
    left.push(linePressure ? withPressure(op, s.opacity_pressure, 'opacity_pressure', 'Pen pressure sets the opacity') : op);
  }
  if (bezier) {
    left.push(toggle('Auto Fill', s.fill, () => setValues({ fill: !s.fill }), 'Fill curves closed on their first point'));
  }
  else {
    if (eraser) {
      const items = [];
      if (mode === 'STROKE_ERASER') {
        items.push(toggle('Whole Line', s.erase_whole, () => setValues({ erase_whole: !s.erase_whole }),
                          'Take away the whole of every line touched, not just the part brushed'));
      }
      items.push(toggle('All Layers', s.erase_all_layers, () => setValues({ erase_all_layers: !s.erase_all_layers }),
                        'Cut every drawing being edited, not only the active one'));
      items.push(toggle('Selected Only', s.erase_selected, () => setValues({ erase_selected: !s.erase_selected }),
                        'Cut only the selected shapes'));
      left.push(joined(...items));
    }
    left.push(stabilizerField());
    left.push(dropdown('Advanced', 'advanced', 'Size Unit, tapers, fidelity, pressure, dynamics and the nib', advancedPopover));
  }
  toolStrip.replaceChildren(...left);
  /* The strip at the right end, shared by every pen. */
  const right = [dropdown('Options', 'options', 'Close and Fill, Weld Ends, Trim Overshoots, Hold to Shape, the cursor', optionsPopover)];
  const colors = [swatch(s.line_color, 'Line colour, for every pen', (c) => setValues({ line_color: c }))];
  if (state.fill_shown) {
    colors.push(swatch(s.fill_color, fillPen ? 'The colour the Fill Pen paints' : 'Fill colour, for strokes that close',
                       (c) => setValues({ fill_color: c })));
  }
  right.push(joined(...colors));
  sharedStrip.replaceChildren(...right);
  renderBrushButton();
}

function brushButton() {
  const b = el('button', 'brush-button dropdown');
  b.title = 'The line brush: ' + state.brush;
  brushCanvas = el('canvas');
  b.append(brushCanvas);
  b.addEventListener('click', (e) => { e.stopPropagation(); popover(b, 'brush', brushPopover); });
  return b;
}

function renderBrushButton() {
  if (!brushCanvas || !brushPreview || !brushCanvas.isConnected) return;
  const dpr = devicePixelRatio || 1;
  const w = 96, h = 24;
  brushCanvas.width = w * dpr;
  brushCanvas.height = h * dpr;
  if (brushPreview.kind === 'dabs') {
    if (!brushRenderer || brushRenderer.canvas !== brushCanvas) brushRenderer = new DabRenderer(brushCanvas);
    const sets = new Map();
    for (const im of brushPreview.images) sets.set(String(im.id), im.add);
    drawDabs(brushRenderer, [{ dabs: sets, own: brushPreview.own }], { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 }, w, h);
  }
  else {
    const ctx = brushCanvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    drawVarLine(ctx, brushPreview.add, brushPreview.color, { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 });
  }
}

function brushPopover(p) {
  if (state.brush_recent.length) {
    p.append(el('div', 'section', 'Recently Used'));
    state.brush_recent.forEach((name, i) => {
      const item = el('div', 'list-item', name || 'Plain');
      item.addEventListener('click', () => { send({ t: 'brush_recent', index: i }); closePopovers(); });
      p.append(item);
    });
  }
  p.append(el('div', 'section', 'Shape'));
  for (const name of ['Plain'].concat(state.brush_shapes)) {
    const current = name === 'Plain' ? state.brush === '' || state.brush === 'Plain' : state.brush === name;
    const item = el('div', 'list-item' + (current ? ' on' : ''), name);
    item.addEventListener('click', () => { send({ t: 'brush', name: name === 'Plain' ? '' : name }); });
    p.append(item);
  }
}

function stabilizerField() {
  const s = state.settings;
  const off = s.stabilizer === 'OFF';
  const field = s.stabilizer === 'PULLED_STRING'
    ? numberField({ format: 'String %.0f px', value: s.string_length, min: 1, max: 100, slider: true, width: 150,
                    onChange: (v) => setValues({ string_length: v }) })
    : numberField({ format: off ? 'Stabilize Off' : 'Stabilize %.2f', value: off ? 0 : s.smoothing, min: 0, max: 1,
                    slider: true, disabled: off, width: 150, onChange: (v) => setValues({ smoothing: v }) });
  field.title = off ? 'The stabilizer is off: the gear turns it on'
    : s.stabilizer === 'SMART' ? "How much of a slow hand's wobble the line leaves out (a fast hand it follows as it is)"
      : 'How long the string the line is pulled on is, in screen pixels';
  const gear = el('button', 'icon');
  gear.title = 'Stabilizer settings';
  gear.append(el('div', 'gear-icon'));
  gear.addEventListener('click', (e) => {
    e.stopPropagation();
    popover(gear, 'stabilizer', (p) => {
      const st = state.settings;
      const row = el('div', 'row');
      row.append(el('span', '', 'Stabilizer'));
      const names = [['OFF', 'Off', 'The line follows the pen exactly'],
                     ['SMART', 'Smart', "Leaves out a slow hand's wobble and follows a fast one as it is"],
                     ['PULLED_STRING', 'String', 'Pulled String: the line is pulled behind the pen on a string, for exact corners and a learned feel']];
      row.append(joined(...names.map(([id, label, tip]) => toggle(label, st.stabilizer === id, () => setValues({ stabilizer: id }), tip))));
      p.append(row);
      p.append(check('Catch Up', st.catch_up, (v) => setValues({ catch_up: v }), st.stabilizer === 'PULLED_STRING'));
    });
  });
  const j = el('div', 'joined');
  j.append(field, gear);
  return j;
}

function advancedPopover(p) {
  const s = state.settings;
  const unit = el('div', 'row');
  unit.append(el('span', '', 'Size Unit'));
  unit.append(joined(
    toggle('View', s.size_view, () => setValues({ size_view: true }), 'Size is on screen: the line looks as wide at any zoom'),
    toggle('Scene', !s.size_view, () => setValues({ size_view: false }),
           'Size is in the drawing: zoomed in, the line is as wide on the character as zoomed out')));
  p.append(unit);
  p.append(el('div', '', 'Taper'));
  p.append(bar('Start %.0f px', s.taper_start, 0, 300, (v) => setValues({ taper_start: v })));
  p.append(bar('End %.0f px', s.taper_end, 0, 300, (v) => setValues({ taper_end: v })));
  p.append(bar('Fidelity %.2f', s.fidelity, 0, 1, (v) => setValues({ fidelity: v })));
  p.append(panel('Pressure', (b) => {
    b.append(curveEditor(s.pressure_curve, (c) => setValues({ pressure_curve: c })));
    b.append(bar('Min Size %.2f', s.min_size, 0, 1, (v) => setValues({ min_size: v })));
    if (state.mode === 'FREEHAND') {
      b.append(bar('Min Opacity %.2f', s.min_opacity, 0, 1, (v) => setValues({ min_opacity: v }), !s.opacity_pressure));
    }
    b.append(bar('Smoothing %.2f', s.pressure_smoothing, 0, 1, (v) => setValues({ pressure_smoothing: v })));
  }));
  p.append(panel('Dynamics', (b) => {
    b.append(bar('Width / Speed %.2f', s.speed_width, 0, 1, (v) => setValues({ speed_width: v })));
    b.append(bar('Width / Tilt %.2f', s.tilt_width, 0, 1, (v) => setValues({ tilt_width: v })));
  }));
  p.append(panel('Nib', (b) => {
    b.append(bar('Angle %.0f°', s.nib_angle, 0, 180, (v) => setValues({ nib_angle: v })));
    b.append(bar('Width / Direction %.2f', s.nib_direction, 0, 1, (v) => setValues({ nib_direction: v })));
  }));
}

function optionsPopover(p) {
  const s = state.settings, mode = state.mode, lines = mode === 'FREEHAND';
  p.append(el('div', 'section', 'Line'));
  p.append(check(mode === 'PEN' ? 'Close and Fill (Auto Fill)' : 'Close and Fill', s.fill, (v) => setValues({ fill: v })));
  p.append(check('Weld Ends', s.weld, (v) => setValues({ weld: v }), lines));
  p.append(check('Trim Overshoots', s.trim, (v) => setValues({ trim: v }), lines));
  p.append(check('Hold to Shape', s.hold_shape, (v) => setValues({ hold_shape: v }), lines));
  p.append(el('div', 'section', 'Cursor'));
  p.append(check('Width Circle', s.cursor_circle, (v) => setValues({ cursor_circle: v })));
  /* This iPad's own: the Pencil's pressure before the pen's curve. */
  p.append(el('div', 'section', 'Pencil'));
  p.append(curveEditor(pencil, (c) => {
    pencil = c;
    try { localStorage.setItem('oa-pencil-curve', JSON.stringify(c)); } catch (e) { /* not kept */ }
  }));
  const sendLog = el('button', '', 'Send Input Log');
  sendLog.title = "The canvas's last touches and Pencil strokes, saved on the PC for finding out what this iPad sends";
  sendLog.addEventListener('click', (e) => {
    e.stopPropagation();
    send({ t: 'input_log', agent: navigator.userAgent, events: inputLog });
    closePopovers();
    toast('Input log sent');
  });
  p.append(sendLog);
}

/* ---------------------------------------------------------------------------------------------------------------
 * The shelf: the PC's Draw shelf (draw_shelf.cc), its tabs and its tiles' pictures. */

let shelfTab = localStorage.getItem('oa-shelf-tab') || 'All';
let longPress = 0;

function buildShelf() {
  if (!state) return;
  const has = (cat) => state.presets.some((p) => p.category === cat);
  const tabs = ['All', 'Pens'];
  if (has('Erasers')) tabs.push('Erasers');
  if (has('Trim')) tabs.push('Trim');
  tabs.push('Mine');
  if (!tabs.includes(shelfTab)) shelfTab = 'All';
  shelfTabs.replaceChildren(...tabs.map((name) => {
    const b = el('button', name === shelfTab ? 'on' : '', name);
    b.addEventListener('click', () => {
      shelfTab = name;
      try { localStorage.setItem('oa-shelf-tab', name); } catch (e) { /* not kept */ }
      buildShelf();
    });
    return b;
  }));
  const shown = state.presets.filter((p) => shelfTab === 'All' || p.category === shelfTab);
  const items = shown.map((p) => {
    const t = el('div', 'tile' + (p.name === state.preset ? ' on' : ''));
    const c = el('canvas');
    t.append(c, el('div', 'name', p.name));
    paintTile(c, tiles[p.name]);
    let timer = 0, held = false;
    t.addEventListener('pointerdown', () => {
      held = false;
      timer = setTimeout(() => { held = true; tileMenu(t, p); }, 550);
    });
    const clear = () => clearTimeout(timer);
    t.addEventListener('pointerup', clear);
    t.addEventListener('pointercancel', clear);
    t.addEventListener('pointerleave', clear);
    t.addEventListener('click', (e) => {
      e.stopPropagation();
      if (!held) send({ t: 'preset', name: p.name });
    });
    return t;
  });
  if (shelfTab === 'All' || shelfTab === 'Mine') {
    const plus = el('div', 'tile plus', '+');
    plus.title = 'Save the pen as it is now';
    plus.addEventListener('click', () => {
      const name = prompt('Save the pen as', state.preset);
      if (name && name.trim()) send({ t: 'preset_save', name: name.trim() });
    });
    items.push(plus);
  }
  shelfTiles.replaceChildren(...items);
}

function tileMenu(anchor, p) {
  popover(anchor, 'tile:' + p.name, (box) => {
    const back = el('div', 'list-item', 'Put Back');
    back.addEventListener('click', () => { send({ t: 'preset_reset', name: p.name }); closePopovers(); });
    box.append(back);
    if (!p.builtin) {
      const del = el('div', 'list-item', 'Delete');
      del.addEventListener('click', () => { send({ t: 'preset_remove', name: p.name }); closePopovers(); });
      box.append(del);
    }
  });
}

function paintTile(c, pic) {
  const dpr = devicePixelRatio || 1;
  c.width = tileSize * dpr;
  c.height = tileSize * dpr;
  if (!pic) return;
  const ctx = c.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const I = { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
  for (const r of pic.rects) {
    ctx.fillStyle = rgba(r.c);
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(r.a[0], r.a[1], r.b[0] - r.a[0], r.b[1] - r.a[1], r.r);
    else ctx.rect(r.a[0], r.a[1], r.b[0] - r.a[0], r.b[1] - r.a[1]);
    ctx.fill();
  }
  for (const s of pic.strokes) {
    if (s.plain) {
      ctx.strokeStyle = rgba(s.c);
      ctx.lineWidth = s.p[2] * 2;
      ctx.lineCap = 'butt';
      ctx.lineJoin = 'round';
      ctx.beginPath();
      for (let i = 0; i < s.p.length; i += 4) {
        if (i === 0) ctx.moveTo(s.p[i], s.p[i + 1]); else ctx.lineTo(s.p[i], s.p[i + 1]);
      }
      ctx.stroke();
    }
    else drawVarLine(ctx, s.p, s.c, I);
  }
  for (const d of pic.dots) {
    ctx.fillStyle = rgba(d.c);
    ctx.beginPath();
    if (d.square) ctx.rect(d.x - d.r, d.y - d.r, d.r * 2, d.r * 2);
    else ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
    ctx.fill();
  }
}

/* ---------------------------------------------------------------------------------------------------------------
 * Start. */

addEventListener('resize', () => { sizeCanvases(); if (canvasW) fitView(); });
sizeCanvases();
connect();
