// Живий фон вікна: кілька шейдерів (порти компонентів Originkit на чистий WebGL) на одному canvas
// + налаштування графіки. Новий фон = запис у BACKGROUNDS (frag + colors + uniforms) — у меню з'явиться сам.
//   frag закінчується на gl_FragColor = vec4(rzOut(колір), 1.0) — rzOut дає яскравість і спалахи індикатора;
//   colors.<палітра>.ui = [c1, c2] — акцент інтерфейсу під цей фон (нема — стандартний червоний).
// window.RZGfx: { DEFAULTS, backgrounds, palettes, qualities, read(), state(), set(gfx), autoLevel(), onauto, level(p), pulse(), previews(items) }
(function () {
  'use strict';
  const DEFAULTS = { bg: 'dots', palette: 'custom', quality: 'auto', tone: 'cyan', bright: 100, panel: 100, speed: 100, pointer: true, motion: true, react: true, pauseBlur: true, splash: true, sound: false, accent: true, glass: true, glassLvl: 'mid' };
  // dpr — стеля щільності пікселів, scale — частка від неї, fps — стеля кадрів (0 = кожен кадр)
  const QUALITY = {
    high:   { label: 'Высокое', dpr: 2, scale: 1,   fps: 60 },   // 3.2: стеля 60 — скло домальовується між кадрами фону, тож прокрутка й наведення лишаються плавними
    medium: { label: 'Среднее', dpr: 1, scale: 1,   fps: 30 },
    low:    { label: 'Низкое',  dpr: 1, scale: 0.5, fps: 20 },
  };
  const PALETTES = { red: 'Красный', orig: 'Родной', custom: 'Свой' };   // «родной» — кольори самого компонента, «свой» — тон із TONES
  // [id, назва, світлий c1, насичений c2] — фарбує і фон, і акцент інтерфейсу
  const TONES = [
    ['cyan', 'Неоновый Циан', '#00F0FF', '#0070FF'],
    ['blue', 'Сапфир', '#00D2FF', '#2A75FF'],
    ['emerald', 'Изумруд', '#00FF88', '#00B862'],
    ['orange', 'Оранжевый', '#FFC38F', '#FF7A1A'], ['amber', 'Янтарный', '#FFE08F', '#F2B01E'], ['green', 'Зелёный', '#9CF0B8', '#22C55E'],
    ['teal', 'Бирюзовый', '#8FEDE3', '#14B8A6'], ['blue', 'Синий', '#8FC0FF', '#2F6BFF'], ['violet', 'Фиолетовый', '#C3B0FF', '#7B61FF'],
    ['pink', 'Розовый', '#FFA8D8', '#F0439A'], ['white', 'Белый', '#EDEDF2', '#A9AEC4'],
  ];
  const PAGES = ['base', 'msg'];   // сторінки вікна, яким можна дати свій фон (парсер — основний)
  // Спалахи фону-індикатора: на мить узор фону перефарбовується в колір події (ті самі, що --ok / --warm / --err в інтерфейсі)
  const FLASH = { reply: ['Ответ', '#6FD39A'], due: ['Пора дожать', '#F2C94C'], error: ['Ошибка', '#FF6B6B'] };

  const VERT = `attribute vec2 a_pos; void main(){ gl_Position = vec4(a_pos, 0.0, 1.0); }`;
  const HEAD = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes; uniform float uTime;
uniform vec3 uBg, uBase, uAccent, uHigh;
uniform float uGain;
uniform vec4 uFlash;   // колір події і сила спалаху
vec3 rzOut(vec3 c) {
  vec3 ink = (c - uBg) * uGain;
  ink = mix(ink, uFlash.rgb * max(ink.r, max(ink.g, ink.b)) * 1.25, uFlash.a);
  return clamp(uBg + ink, 0.0, 1.0);
}
`;

  // Predictive Arc — точкова дуга, притиснута до низу вікна, тягнеться до курсора.
  const DOTS = { density: 78, dotSize: 1.02, peak: 1.0, archHeight: 0, thickness: 2.06, falloff: 6.0, pointerRadius: 236, pointerStrength: 0.34 };
  const DOTS_FS = HEAD + `
uniform float uDpr, uCell, uDot;
uniform float uPeak, uHeight, uThick, uFall;
uniform vec2 uMouse; uniform float uMouseRadius, uMouseStrength;
void main(){
  float cs = max(uCell, 2.0);
  vec2 ci = floor(gl_FragCoord.xy / cs);
  vec2 cc = (ci + 0.5) * cs;
  float x = cc.x / uDpr;
  float y = (uRes.y - cc.y) / uDpr;
  float w = uRes.x / uDpr;
  float h = uRes.y / uDpr;
  float normX = (x - w * 0.5) / (w * 0.75);
  float curveY = h * uPeak + normX * normX * (h * uHeight);
  float mdx = x - uMouse.x;
  float influence = uMouseStrength * exp(-(mdx * mdx) / (2.0 * uMouseRadius * uMouseRadius + 1.0));
  curveY = mix(curveY, uMouse.y, influence);
  float dist = abs(y - curveY);
  float th = (140.0 + (1.0 - abs(normX)) * 80.0) * uThick;
  vec3 col = uBg;
  if (dist < th) {
    float i = 1.0 - dist / th;
    float waveX = sin(x * 0.015 + uTime);
    float waveY = cos(y * 0.02 + uTime);
    i = i * 0.7 + waveX * waveY * 0.3 * i;
    i *= max(0.0, 1.0 - pow(abs(normX), uFall));
    if (i > 0.02) {
      float side = uDot * i * uDpr;
      vec2 d = abs(gl_FragCoord.xy - cc);
      float cov = 1.0 - smoothstep(side * 0.5 - 1.0, side * 0.5 + 1.0, max(d.x, d.y));
      vec3 ink = mix(uBase, uAccent, clamp(pow(i, 1.1), 0.0, 1.0));
      ink = mix(ink, uHigh, smoothstep(0.72, 1.0, i));
      col = mix(uBg, ink, cov * clamp(i * 1.6, 0.0, 1.0));
    }
  }
  gl_FragColor = vec4(rzOut(col), 1.0);
}`;

  // Fibre Arc — пучок тонких волокон-парабол, курсор «розчісує» їх. Пресет: curve 20.
  const FIBRE = { strands: 26, hover: 2.0, reach: 0.23, direction: 0, curve: 0.2, spread: 1.0, thickness: 1.0, comb: 1.7 };
  const FIBRE_FS = HEAD + `
uniform vec2 uMouse; uniform float uHover;
uniform float uStrands, uCurve, uSpread, uThin, uComb, uReach, uDir;
float sat(float x){ return clamp(x, 0.0, 1.0); }
float pw(float x, float e){ return pow(max(x, 1e-5), e); }
float hash21(vec2 p){ p = fract(p * vec2(123.34, 456.21)); p += dot(p, p + 34.56); return fract(p.x * p.y); }
void main(){
  float ar = uRes.x / max(uRes.y, 1.0);
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p = (uv - 0.5) * vec2(ar, 1.0);
  float t = uTime;
  vec2 apex = vec2(0.34, 0.20);
  float cs = cos(uDir), sn = sin(uDir);
  mat2 rot = mat2(cs, sn, -sn, cs);
  vec2 q  = rot * p;
  vec2 pm = q - rot * ((uMouse - 0.5) * vec2(ar, 1.0));
  vec2 ps = q - normalize(pm + vec2(1e-5)) * uComb * 0.10 * sat(uHover)
            * exp(-dot(pm, pm) / max(uReach * uReach, 1e-4));
  float core = 0.0, halo = 0.0;
  for(int i = 0; i < 26; i++){
    float fi = float(i);
    float f = fi / 25.0;
    float on = sat(uStrands - fi);
    float jit = hash21(vec2(fi, 1.7));
    float k = uCurve * (0.55 + 1.30 * f + 0.10 * jit);
    float ax = apex.x + (f - 0.5) * uSpread * 0.18;
    float ay = apex.y + (f - 0.5) * uSpread * 0.14 + 0.012 * sin(t * 0.5 + fi);
    float dx = ps.x - ax;
    float yc = ay - k * dx * dx;
    float sl = -2.0 * k * dx;
    float dd = abs(ps.y - yc) / sqrt(1.0 + sl * sl);
    float w = uThin * (0.0016 + 0.0032 * jit);
    core += on * pw(w / (w + dd), 3.2);
    halo += on * pw(w * 11.0 / (w * 11.0 + dd), 1.9) * 0.085;
  }
  float env = mix(0.20, 1.0, sat((ps.x + 0.52) / 0.95));
  core *= env; halo *= env;
  vec3 col = uBg;
  col += uBase * halo * 1.5;
  col += mix(uAccent, uHigh, sat(core * 0.75)) * core * 1.4;
  gl_FragColor = vec4(rzOut(col), 1.0);
}`;

  // Ribbon Glow — стрічка світла з 84 шарів, курсор закручує її і тягне за собою. В оригіналі поле
  // рахується в половинній роздільності й розтягується — тут те саме через res: 0.5.
  const RIBBON = { size: 1.0, angle: -180, hover: 1.0, reach: 240 };
  const RIBBON_FS = HEAD + `
uniform float uSize, uAngle, uOn, uReach;
uniform vec2 uMouse, uVel;
const float LAYERS = 84.0;
const float TWIST = 1.25;
const float DRAG = 0.18;
const float GAIN = 0.62;
const vec2 CENTRE = vec2(-0.62, 0.24);
const float TILT = 0.6;
const float ZOOM = 1.05;
const float THETA = 2.13;
const float SHEAR = 0.963;
const float SHRINK = 0.953;
const vec2 WARP_FREQ = vec2(0.42, 2.4);
const vec2 WARP_AMP = vec2(0.13, 0.027);
const vec2 ASPECT = vec2(2.1, 0.17);
const float OFFSET = 0.36;
const float GLOW = 0.0021;
const float SOFT = 0.0019;
const float FALLOFF = 0.37;
const float PHASE = 12.0;
const float CYCLE = 0.16;
const float HUE_TRAVEL = 2.0;
mat2 rot(float a) { float c = cos(a), s = sin(a); return mat2(c, s, -s, c); }
float ign(vec2 p, float f) { p += 5.588238 * mod(f, 64.0); return fract(52.9829189 * fract(0.06711056 * p.x + 0.00583715 * p.y)); }
void main() {
  vec2 pos = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  vec2 d = pos - uMouse;
  float w = uOn * exp(-dot(d, d) / (uReach * uReach));
  if (w > 1e-4) pos = uMouse + rot(w * TWIST) * d * (1.0 - 0.3 * min(w, 1.0)) - uVel * min(w, 1.0) * DRAG;
  pos = rot(uAngle) * pos / uSize;
  float t = uTime * 0.49 + PHASE;
  float breath = (-sin(uTime * 0.735) + sin(uTime * 0.49 + 1.0)) * 0.25 + 0.5;
  vec2 u = rot(TILT) * ((pos - CENTRE) * (ZOOM - breath * 0.085));
  mat2 fold = mat2(cos(THETA), sin(THETA), -SHEAR, cos(THETA));
  vec3 col = vec3(0.0);
  for (float i = 1.0; i <= LAYERS; i += 1.0) {
    u.x -= sin(u.y * WARP_FREQ.x + t + i * 0.007) * WARP_AMP.x;
    u.y -= sin(u.x * WARP_FREQ.y - t + i * 0.02) * WARP_AMP.y;
    u = fold * u * SHRINK;
    vec2 q = (u - vec2(OFFSET + breath * 0.1, 0.0)) * ASPECT;
    float g = GLOW / (dot(q, q) + SOFT) * (0.25 + breath * 0.4);
    float r = length(u);
    float k = sin(i * CYCLE + t * 1.2 + r * HUE_TRAVEL) * 0.5 + 0.5;
    col += g * mix(uBase, uAccent, k) * (0.62 + 0.5 * k) * exp2(-r * FALLOFF);
  }
  vec3 x = max(col * GAIN, 0.0);
  col = (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14);
  col = pow(clamp(col, 0.0, 1.0), vec3(0.85, 0.92, 0.98));
  col *= 1.0 - smoothstep(0.5, 1.6, length(pos)) * 0.07;
  col = uBg + col * (1.0 - uBg);
  col += (ign(gl_FragCoord.xy, floor(uTime * 24.0)) - 0.5) / 255.0;
  gl_FragColor = vec4(rzOut(col), 1.0);
}`;

  // Reflect Shader — кільця, що розходяться від центру, з райдужним розшаруванням; центр тягнеться до курсора.
  const REFLECT = { lines: 5, thickness: 0.002, chromatic: 0.01, bandGap: 0.2, zoom: 2.95, brightness: 1.0, hover: 0.9, reachPx: 260 };
  const REFLECT_FS = HEAD + `
#define MAXLINES 12
uniform float uLineWidth, uSpread, uBands, uScale, uIntensity, uHover, uReach;
uniform int uLineCount;
uniform vec2 uPointer;
float channel(vec2 uv, float r, float t, float jf) {
  float sum = 0.0;
  float band = mod(uv.x + uv.y, uBands);
  for (int i = 0; i < MAXLINES; i++) {
    if (i < uLineCount) {
      float d = fract(t - uSpread * jf + float(i) * 0.01) * 5.0 - r + band;
      sum += uLineWidth * float(i * i) / max(abs(d), 1e-4);
    }
  }
  return sum;
}
void main() {
  vec2 s = (gl_FragCoord.xy * 2.0 - uRes) / min(uRes.x, uRes.y);
  s *= uScale;
  vec2 uv = s - uPointer * min(uHover, 1.0);
  float r = length(uv);
  float t = uTime * 0.05;
  vec3 color = vec3(channel(uv, r, t, 0.0), channel(uv, r, t, 1.0), channel(uv, r, t, 2.0));
  float dp = length(s - uPointer) / max(uReach, 1e-3);
  float glow = uHover * exp(-dp * dp);
  vec3 c = min(color * uIntensity * (1.0 + glow) * uBase, vec3(1.0));
  float a = clamp(max(max(c.r, c.g), c.b), 0.0, 1.0);
  gl_FragColor = vec4(rzOut(c + uBg * (1.0 - a)), 1.0);
}`;

  // Swell Grid — сітка вузьких плашок, по якій іде «морська» хвиля з чотирьох синусів; ближче до низу
  // хвиля крупніша (перспектива), курсор лишає слід, що згасає. Оригінал — Canvas 2D із буфером сліду;
  // тут слід = останні TRAIL положень курсора з вагою за віком (той самий max, без буфера).
  const SWELL = { size: 9, aspect: 438, gap: 3, rounded: 45, alpha: 0.92, minAlpha: 0.15,
    length: 100, direction: 68, contrast: 145, fog: 0, hover: 1.0, reach: 38, damping: 10, trail: 16 };
  const SWELL_WAVES = (() => {   // [k·sin, k·0.055·cos, omega, phase] на хвилю; частоти кратні 2π/24 → час зациклюється без шва
    const W = [[1, 7.5, 1.18, 0], [0.66, 4.6, 0.88, 1.7], [0.42, 2.7, 1.95, 3.9], [0.26, 1.8, 2.32, 5.2]];
    const base = 2 * Math.PI / 24, sum = W.reduce((a, w) => a + w[0], 0), h0 = SWELL.direction * Math.PI / 180;
    const terms = new Float32Array(16), amps = new Float32Array(4);
    W.forEach(([amp, len, heading, phase], i) => {
      const k = 2 * Math.PI / (len * Math.max(0.01, SWELL.length / 100));
      const h = h0 + (heading - W[0][2]);
      terms.set([k * Math.sin(h), k * 0.055 * Math.cos(h), Math.max(1, Math.round(Math.sqrt(9.81 * k) / base)) * base, phase], i * 4);
      amps[i] = amp / sum;
    });
    return { terms, amps };
  })();
  const swellHist = [], swellBuf = new Float32Array(SWELL.trail * 3);
  const SWELL_FS = HEAD + `
#define TRAIL ${SWELL.trail}
uniform float uK, uAlpha, uMinAlpha;
uniform vec4 uGrid;          // ширина й висота плашки, крок по x і y (px CSS)
uniform vec3 uDim;           // колонок, рядів, радіус кута
uniform vec3 uShape;         // гама, туман угорі, 1/(2σ²) курсора
uniform vec4 uWave[4];
uniform vec4 uAmp;
uniform vec3 uTrail[TRAIL];  // x, y, вага
void main() {
  vec2 p = vec2(gl_FragCoord.x, uRes.y - gl_FragCoord.y) / uK;
  float col = min(floor(p.x / uGrid.z), uDim.x - 1.0);
  float row = floor(p.y / uGrid.w);
  vec2 org = vec2(col * uGrid.z, row * uGrid.w);
  vec2 hs = uGrid.xy * 0.5;
  vec2 q = abs(p - org - hs) - hs + uDim.z;
  float d = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - uDim.z;
  float cov = clamp(0.5 - d * uK, 0.0, 1.0);
  vec3 c = uBg;
  if (cov > 0.0) {
    float n = (row + 0.5) / uDim.y;
    float depth = 1.0 / tan(0.095 + 0.425 * n);
    float fog = uShape.y + (1.0 - uShape.y) * (1.0 - n);
    float o = col - (uDim.x - 1.0) * 0.5;
    float s = 0.0;
    for (int i = 0; i < 4; i++) { vec4 w = uWave[i]; s += uAmp[i] * sin(depth * (w.x + w.y * o) - w.z * uTime + w.w); }
    float base = pow(clamp(0.5 + 0.5 * s, 0.0, 1.0), uShape.x) * fog;
    float pulse = 0.0;
    for (int i = 0; i < TRAIL; i++) { vec3 t = uTrail[i]; vec2 dd = org - t.xy; pulse = max(pulse, t.z * exp(-dot(dd, dd) * uShape.z)); }
    float v = base + (1.0 - base) * pulse;
    c = mix(uBg, uBase, clamp(uMinAlpha + uAlpha * v, 0.0, 1.0) * cov);
  }
  gl_FragColor = vec4(rzOut(c), 1.0);
}`;

  // f — кадр: { bw, bh, cw, ch, k (px буфера на px CSS), ps (курсор: x, y від верху, vx, vy — px/с, active; tx, ty, ta — без згладжування), live, thumb }
  const BACKGROUNDS = [
    { id: 'dots', label: 'Точки', note: 'Дуга из точек внизу окна', frag: DOTS_FS, speed: 1.8, wrap: 6283,
      colors: { red:  { bg: '#030303', base: '#FF0000', accent: '#FF9898', high: '#FF0000' },
                orig: { bg: '#01030A', base: '#1B4FD8', accent: '#6FC8FF', high: '#FFFFFF', ui: ['#8FC0FF', '#2F6BFF'] } },
      uniforms(gl, u, f) {
        const pitch = Math.min(f.cw, f.ch) / DOTS.density;
        gl.uniform1f(u('uDpr'), f.k);
        gl.uniform1f(u('uCell'), Math.max(2, pitch * f.k));
        gl.uniform1f(u('uDot'), pitch * 1.2 * DOTS.dotSize);
        gl.uniform1f(u('uPeak'), DOTS.peak);
        gl.uniform1f(u('uHeight'), DOTS.archHeight);
        gl.uniform1f(u('uThick'), DOTS.thickness);
        gl.uniform1f(u('uFall'), DOTS.falloff);
        gl.uniform2f(u('uMouse'), f.ps.x, f.ps.y);
        gl.uniform1f(u('uMouseRadius'), DOTS.pointerRadius);
        gl.uniform1f(u('uMouseStrength'), f.live ? DOTS.pointerStrength * f.ps.active : 0);
      } },
    { id: 'fibre', label: 'Нити', note: 'Пучок тонких волокон', frag: FIBRE_FS, speed: 2, wrap: 3600,
      colors: { red:  { bg: '#030303', base: '#D81B1B', accent: '#FF6F6F', high: '#FFFFFF' },
                orig: { bg: '#01030A', base: '#1B4FD8', accent: '#6FC8FF', high: '#FFFFFF', ui: ['#8FC0FF', '#2F6BFF'] } },
      uniforms(gl, u, f) {
        gl.uniform2f(u('uMouse'), f.ps.x / f.cw, 1 - f.ps.y / f.ch);
        gl.uniform1f(u('uHover'), f.live ? f.ps.active * FIBRE.hover : 0);
        gl.uniform1f(u('uStrands'), FIBRE.strands);
        gl.uniform1f(u('uReach'), FIBRE.reach);
        gl.uniform1f(u('uDir'), FIBRE.direction * Math.PI / 180);
        gl.uniform1f(u('uCurve'), FIBRE.curve);
        gl.uniform1f(u('uSpread'), FIBRE.spread);
        gl.uniform1f(u('uThin'), FIBRE.thickness);
        gl.uniform1f(u('uComb'), FIBRE.comb);
      } },
    { id: 'ribbon', label: 'Лента', note: 'Светящаяся лента. Самый тяжёлый фон', frag: RIBBON_FS, speed: 1, wrap: 3600, res: 0.5,
      colors: { red:  { bg: '#030303', base: '#FF8F8F', accent: '#FF3030', high: '#FFFFFF' },
                orig: { bg: '#0B0A10', base: '#2FD3F2', accent: '#7B61FF', high: '#FFFFFF', ui: ['#8FE3F5', '#7B61FF'] } },
      uniforms(gl, u, f) {
        const vl = Math.hypot(f.ps.vx, f.ps.vy) / f.ch, cap = vl > 3 ? 3 / vl : 1;
        gl.uniform1f(u('uSize'), RIBBON.size);
        gl.uniform1f(u('uAngle'), RIBBON.angle * Math.PI / 180);
        gl.uniform2f(u('uMouse'), (f.ps.x - f.cw / 2) / f.ch, (f.ch / 2 - f.ps.y) / f.ch);
        gl.uniform1f(u('uOn'), f.live ? f.ps.active * RIBBON.hover : 0);
        gl.uniform1f(u('uReach'), RIBBON.reach / f.ch);
        gl.uniform2f(u('uVel'), f.ps.vx / f.ch * cap, -f.ps.vy / f.ch * cap);
      } },
    { id: 'reflect', label: 'Кольца', note: 'Расходящиеся круги с радужным краем', frag: REFLECT_FS, speed: 3, wrap: 20000, thumbT: 6,   // у мініатюрі кільце вже розійшлося, а не точка в центрі
      colors: { red:  { bg: '#030303', base: '#FF4A4A', accent: '#FF4A4A', high: '#FFFFFF' },
                orig: { bg: '#020202', base: '#FFFFFF', accent: '#FFFFFF', high: '#FFFFFF', ui: ['#E9E9F2', '#A9AEC4'] } },
      uniforms(gl, u, f) {
        const m = Math.min(f.cw, f.ch);
        gl.uniform1f(u('uLineWidth'), REFLECT.thickness);
        gl.uniform1f(u('uSpread'), REFLECT.chromatic);
        gl.uniform1f(u('uBands'), REFLECT.bandGap);
        gl.uniform1f(u('uScale'), REFLECT.zoom);
        gl.uniform1f(u('uIntensity'), REFLECT.brightness);
        gl.uniform1i(u('uLineCount'), REFLECT.lines);
        gl.uniform2f(u('uPointer'), (f.ps.x * 2 - f.cw) / m * REFLECT.zoom, (f.ch - f.ps.y * 2) / m * REFLECT.zoom);
        gl.uniform1f(u('uHover'), f.live ? REFLECT.hover * f.ps.active : 0);
        gl.uniform1f(u('uReach'), REFLECT.reachPx * 2 / m * REFLECT.zoom);
      } },
    { id: 'swell', label: 'Зыбь', note: 'Сетка плашек, по которой идёт волна', frag: SWELL_FS, speed: 1, wrap: 24,
      colors: { red:  { bg: '#030303', base: '#FF5A5A', accent: '#FF5A5A', high: '#FFFFFF' },
                orig: { bg: '#000000', base: '#E6E6E6', accent: '#E6E6E6', high: '#FFFFFF', ui: ['#E6E6E6', '#9C9CA8'] } },
      uniforms(gl, u, f) {
        const S = SWELL, w = S.size, h = S.size * S.aspect / 100, g = S.gap;
        const cols = Math.max(1, Math.floor((f.cw + g) / (w + g))), rows = Math.max(1, Math.ceil((f.ch + g) / (h + g)));
        gl.uniform1f(u('uK'), f.k);
        gl.uniform1f(u('uAlpha'), S.alpha);
        gl.uniform1f(u('uMinAlpha'), S.minAlpha);
        gl.uniform4f(u('uGrid'), w, h, cols > 1 ? (f.cw - w) / (cols - 1) : w + g, h + g);
        gl.uniform3f(u('uDim'), cols, rows, Math.min(w, h) / 2 * S.rounded / 100);
        gl.uniform3f(u('uShape'), S.contrast / 100, 1 - S.fog / 100, 1 / (2 * S.reach * S.reach));
        gl.uniform4fv(u('uWave[0]'), SWELL_WAVES.terms);
        gl.uniform4fv(u('uAmp'), SWELL_WAVES.amps);
        // слід курсора: поточна точка + історія, вага спадає як exp(-вік / tau)
        const now = performance.now(), on = f.live && f.ps.on > 0, tau = 3.2 / Math.max(1, S.damping) * 1000;
        if (f.thumb) { gl.uniform3fv(u('uTrail[0]'), swellBuf.fill(0)); return; }   // мініатюра — без сліду і не чіпає історію
        if (!f.live) swellHist.length = 0;
        else if (on && (!swellHist.length || now - swellHist[0].t > 45)) { swellHist.unshift({ x: f.ps.tx, y: f.ps.ty, t: now }); if (swellHist.length > S.trail - 1) swellHist.length = S.trail - 1; }
        swellBuf.fill(0);
        if (on) swellBuf.set([f.ps.tx, f.ps.ty, S.hover]);
        swellHist.forEach((p, i) => swellBuf.set([p.x, p.y, S.hover * Math.exp(-(now - p.t) / tau)], (i + 1) * 3));
        gl.uniform3fv(u('uTrail[0]'), swellBuf);
      } },
  ];

  function normalize(g) {
    const s = Object.assign({}, DEFAULTS, g && typeof g === 'object' ? g : null);
    if (s.bg !== 'none' && !BACKGROUNDS.some(b => b.id === s.bg)) s.bg = DEFAULTS.bg;
    if (s.palette === 'blue' || s.palette === 'red') { s.palette = 'custom'; s.tone = 'cyan'; }   // так називалась у 2.11
    if (!PALETTES[s.palette]) s.palette = DEFAULTS.palette;
    if (!TONES.some(t => t[0] === s.tone)) s.tone = DEFAULTS.tone;
    s.speed = Math.min(200, Math.max(25, Math.round(+s.speed) || 100));
    s.pointer = s.pointer !== false;
    // свій фон для сторінок «База» і «Сообщения»; '' — як у парсері
    const pg = s.pages && typeof s.pages === 'object' ? s.pages : {};
    s.pages = {};
    for (const k of PAGES) s.pages[k] = pg[k] === 'none' || BACKGROUNDS.some(b => b.id === pg[k]) ? pg[k] : '';
    s.idle = [0, 1, 3, 5, 10].includes(+s.idle) ? +s.idle : 0;   // екран спокою, хвилин; 0 — вимкнено
    if (s.quality !== 'auto' && !QUALITY[s.quality]) s.quality = DEFAULTS.quality;
    s.bright = Math.min(100, Math.max(20, Math.round(+s.bright) || 100));
    s.panel = Math.min(130, Math.max(50, Math.round(+s.panel) || 100));
    for (const k of ['motion', 'glass', 'accent', 'react', 'pauseBlur', 'splash']) s[k] = s[k] !== false;
    s.sound = s.sound === true;   // 3.1.3: звук монеты — только если включили сами
    if (!['soft', 'mid', 'strong'].includes(s.glassLvl)) s.glassLvl = 'mid';   // 3.1: сила стекла — слабо / средне / сильно
    return s;
  }
  function read() {
    try { return normalize((JSON.parse(localStorage.getItem('rz.settings') || '{}') || {}).gfx); } catch { return normalize(null); }
  }

  // «Авто»: рівень якості, до якого програма сама спустилась на цьому ПК (пам'ятаємо між запусками)
  const LEVELS = Object.keys(QUALITY);
  let autoLevel = LEVELS[0];
  try { const v = JSON.parse(localStorage.getItem('rz.gfxAuto')); if (LEVELS.includes(v)) autoLevel = v; } catch {}
  const saveAuto = () => { try { localStorage.setItem('rz.gfxAuto', JSON.stringify(autoLevel)); } catch {} };

  const hexInts = h => { h = h.replace('#', ''); return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16)); };
  const hex = h => hexInts(h).map(v => v / 255);
  // Кольори фону за налаштуваннями: палітра фону або «свій» тон (світлий c1 + насичений c2 на будь-який фон)
  const rawColors = b => {
    if (state.palette !== 'custom' && state.palette !== 'red') return b.colors[state.palette];
    const t = TONES.find(x => x[0] === state.tone);
    return { bg: '#030303', base: t[3], accent: t[2], high: '#FFFFFF', ui: [t[2], t[3]] };
  };
  const colorsOf = b => { const c = rawColors(b); return { bg: hex(c.bg), base: hex(c.base), accent: hex(c.accent), high: hex(c.high) }; };

  // Акцент інтерфейсу від палітри фону: змінні --c1/--c2 (+ їхні rgb для rgba(var(--c1-rgb), a)); без ui — стандартний червоний із CSS
  function applyAccent() {
    const b = BACKGROUNDS.find(x => x.id === bgId());   // «свій» тон фарбує інтерфейс і без фону
    const ui = state.accent && (b || state.palette === 'custom') && rawColors(b || BACKGROUNDS[0]).ui;
    const st = document.documentElement.style;
    st.setProperty('--dens', (state.panel / 100).toFixed(2));   // щільність панелей: множник прозорості бокової панелі, шапки і карток
    if (ui) { st.setProperty('--c1', ui[0]); st.setProperty('--c2', ui[1]); st.setProperty('--c1-rgb', hexInts(ui[0]).join(',')); st.setProperty('--c2-rgb', hexInts(ui[1]).join(',')); }
    else ['--c1', '--c2', '--c1-rgb', '--c2-rgb'].forEach(p => st.removeProperty(p));
  }

  let state = read();
  let page = 'lead';   // сторінка вікна: lead | base | msg — у «Базі» й «Сообщениях» може бути свій фон
  const bgId = () => state.pages[page] || state.bg;
  let apply =() => { const c = document.getElementById('bg'); if (c) c.style.display = 'none'; };
  // інші живі елементи (напис wordmark.js) слухають, щоб зупинитись при «Без фона» / низькій якості
  const gfxChanged = () => { try { window.dispatchEvent(new Event('rzgfx')); } catch {} };
  const api = window.RZGfx = {
    DEFAULTS,
    backgrounds: BACKGROUNDS.map(b => [b.id, b.label, b.note]).concat([['none', 'Без фона', 'Чёрное окно, ничего не рисуется']]),
    palettes: Object.entries(PALETTES),
    tones: TONES.map(t => [t[0], t[1], t[3]]),   // [id, назва, колір зразка]
    qualities: [['auto', 'Авто']].concat(Object.entries(QUALITY).map(([id, q]) => [id, q.label])),
    glassLevels: [['soft', 'Слабо'], ['mid', 'Средне'], ['strong', 'Сильно']],   // 3.1: «Сила стекла» в «Графике»
    read, normalize,
    state: () => state,   // живі налаштування графіки без розбору rz.settings (лише читати); змінюються — подія rzgfx
    set(g) {
      const was = state.quality;
      state = normalize(g);
      if (state.quality === 'auto' && was !== 'auto') { autoLevel = LEVELS[0]; saveAuto(); }   // вибрали «Авто» заново — міряємо з початку
      applyAccent(); apply();
      gfxChanged();
    },
    pages: PAGES,
    page(p) { p = PAGES.includes(p) ? p : 'lead'; if (p === page) return; page = p; applyAccent(); apply(); },
    idle() {},          // idle(true) — екран спокою: фон на повну яскравість
    autoLevel: () => [autoLevel, QUALITY[autoLevel].label],
    onauto: null,       // (id, label) — «Авто» знизило якість
    level() {},         // 0…1 — йде пошук (фон яскравіший і швидший), null — кінець
    flashes: Object.entries(FLASH).map(([id, f]) => [id, f[0]]),
    pulse() {},         // pulse(kind) — короткий спалах кольором події: 'reply' | 'due' | 'error'
    previews() {},      // [{ id, canvas }] — живі мініатюри в списку фонів
    banner: () => ({ set(){}, stop(){} }),   // banner(canvas, {bg, tone}) — жива шапка профілю (без WebGL — нічого, під canvas лишається CSS-градієнт)
    bannerTones: [['red', 'Красный', '#FF4D4D'], ['orig', 'Родной', '#8FC0FF']].concat(TONES.map(t => [t[0], t[1], t[3]])),   // [id, назва, зразок]
  };
  applyAccent();

  const canvas = document.getElementById('bg');
  const glOpts = { alpha: false, antialias: false, depth: false };
  const gl = canvas && canvas.getContext('webgl', glOpts);
  if (!gl) { apply(); return; }

  // Контекст → збирач програм. Програма збирається при першому зверненні; невдала — фон просто вимикається.
  function setup(glx) {
    const sh = (type, src) => { const s = glx.createShader(type); glx.shaderSource(s, src); glx.compileShader(s);
      if (!glx.getShaderParameter(s, glx.COMPILE_STATUS)) { console.error('bg shader:', glx.getShaderInfoLog(s)); return null; } return s; };
    const vs = sh(glx.VERTEX_SHADER, VERT);
    glx.bindBuffer(glx.ARRAY_BUFFER, glx.createBuffer());
    glx.bufferData(glx.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), glx.STATIC_DRAW);
    glx.enableVertexAttribArray(0);
    glx.vertexAttribPointer(0, 2, glx.FLOAT, false, 0, 0);
    const built = {};
    return {
      has: b => b.id in built,
      get(b) {
        if (b.id in built) return built[b.id];
        let out = null;
        const fs = vs && sh(glx.FRAGMENT_SHADER, b.frag);
        if (fs) {
          const prog = glx.createProgram();
          glx.attachShader(prog, vs); glx.attachShader(prog, fs);
          glx.bindAttribLocation(prog, 0, 'a_pos');
          glx.linkProgram(prog);
          if (glx.getProgramParameter(prog, glx.LINK_STATUS)) {
            const locs = {};
            out = { prog, u: n => (n in locs ? locs[n] : (locs[n] = glx.getUniformLocation(prog, n))) };
          } else console.error('bg link:', glx.getProgramInfoLog(prog));
        }
        return (built[b.id] = out);
      },
    };
  }
  function paint(glx, p, b, c, time, gain, flash, f) {
    const u = p.u;
    glx.useProgram(p.prog);
    glx.uniform2f(u('uRes'), f.bw, f.bh);
    glx.uniform1f(u('uTime'), time);
    glx.uniform1f(u('uGain'), gain);
    glx.uniform4fv(u('uFlash'), flash);
    glx.uniform3fv(u('uBg'), c.bg);
    glx.uniform3fv(u('uBase'), c.base);
    glx.uniform3fv(u('uAccent'), c.accent);
    glx.uniform3fv(u('uHigh'), c.high);
    b.uniforms(glx, u, f);
    glx.drawArrays(glx.TRIANGLES, 0, 3);
  }
  let programs = setup(gl);
  // Контекст GPU можуть забрати (драйвер, сон, багато вкладок): preventDefault — щоб його повернули; після повернення — програми заново
  let lost = false;
  canvas.addEventListener('webglcontextlost', e => { e.preventDefault(); lost = true; cancelAnimationFrame(raf); raf = 0; }, false);
  canvas.addEventListener('webglcontextrestored', () => { lost = false; programs = setup(gl); lgT = null; last = 0; apply(); }, false);

  // ================= 3.2 «Стекло в шейдере» =================
  // Скло нижнього шару (заголовок, бічна панель, кнопки, картки, тулбар) малює сам фон: сцена → текстура,
  // з неї розмиття dual-kawase (½ → ¼ → ⅛ і назад), потім на екран — фон з вуаллю і поверх, у прямокутниках
  // елементів, лінза по краю (профіль «сквіркл»), дисперсія R/B, матовість, тон, кромка, Френель, блік за світлом.
  // У DOM у цих елементів лишаються тільки текст і вміст (html.lg-gl знімає з них фон, backdrop-filter і тіні).
  // Спливаючі шари (панель ліда, меню, тости) — поверх карток, їх шейдер не бачить: у них свій CSS-рецепт.
  const LGP = { refr: 30, bevel: 0.2, disp: 0.07, frost: 1, tintPanel: 0.55, tintCard: 0.25, rim: 0.45, spec: 0.2, shadow: 0, sign: 1, profile: 2, clear: 0.3, lift: 0.15, sceneRes: 1, levels: 3, cards: true, boost: 1.2 };   // значення владельця з лабораторії 04.10
  const lg = window.RZLG = { on: true, P: LGP, stat: { js: 0, n: 0, draws: 0 }, kick: () => lgKick(400) };
  const LG_HEAD = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes; uniform float uK, uVeil;
// вуаль .bg-veil (app.css) — тепер у шейдері: та сама крива по висоті вікна, css px від верху
vec3 veil(vec3 c, float py){
  float H = uRes.y / uK, y = (uRes.y - py) / uK, a;
  if (y < 120.0) a = mix(0.3, 0.62, y / 120.0);
  else if (y < 300.0) a = mix(0.62, 0.78, (y - 120.0) / 180.0);
  else if (y < H - 240.0) a = 0.78;
  else a = mix(0.78, 0.5, clamp((y - H + 240.0) / 240.0, 0.0, 1.0));
  return mix(c, vec3(3.0 / 255.0), a * uVeil);
}
`;
  // dual-kawase: uUp 0 — крок вниз (5 вибірок), 1 — вгору (8 вибірок); uOff — пів-текселя джерела
  const KD_FS = LG_HEAD + `
uniform sampler2D uT; uniform vec2 uDst, uOff; uniform float uUp;
void main(){
  vec2 uv = gl_FragCoord.xy / uDst;
  vec4 s;
  if (uUp < 0.5) {
    s = texture2D(uT, uv) * 4.0;
    s += texture2D(uT, uv - uOff) + texture2D(uT, uv + uOff);
    s += texture2D(uT, uv + vec2(uOff.x, -uOff.y)) + texture2D(uT, uv + vec2(-uOff.x, uOff.y));
    s /= 8.0;
  } else {
    s  = texture2D(uT, uv + vec2(-uOff.x * 2.0, 0.0)) + texture2D(uT, uv + vec2(uOff.x * 2.0, 0.0));
    s += texture2D(uT, uv + vec2(0.0, uOff.y * 2.0)) + texture2D(uT, uv + vec2(0.0, -uOff.y * 2.0));
    s += (texture2D(uT, uv + uOff) + texture2D(uT, uv - uOff) + texture2D(uT, uv + vec2(uOff.x, -uOff.y)) + texture2D(uT, uv + vec2(-uOff.x, uOff.y))) * 2.0;
    s /= 12.0;
  }
  gl_FragColor = vec4(s.rgb, 1.0);
}`;
  const BLIT_FS = LG_HEAD + `
uniform sampler2D uScene;
void main(){ vec2 p = gl_FragCoord.xy; gl_FragColor = vec4(veil(texture2D(uScene, p / uRes).rgb, p.y), 1.0); }`;
  const GLASS_FS = LG_HEAD + `
uniform sampler2D uScene, uBlur;
uniform vec4 uBox;        // центр xy, піврозміри zw — буферні px, y знизу
uniform float uRad;
uniform vec4 uClip;       // x0 y0 x1 y1 — прокручуваний контейнер
uniform vec4 uM1;         // фаска px, заломлення px, матовість 0..1, сила тону
uniform vec4 uM2;         // дисперсія, кромка, блік, тінь
uniform vec3 uTint, uRimC;
uniform vec3 uUnder;      // що під елементом: матовість батька, сила тону батька, прозорість елемента
uniform vec3 uUnderTint;
uniform vec4 uHot;        // xy курсор (буфер), z наведення 0..1, w знак заломлення (−1 — всередину)
uniform vec2 uLight;
uniform float uBoost;
uniform vec3 uM3;         // профіль краю (2 — дуга кола, 4 — сквіркл), прозорість кромки 0..1, підйом (скло світліше за вуаль) 0..1
float sdRR(vec2 p, vec2 b, float r){ vec2 q = abs(p) - b + r; return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r; }
vec3 S(vec2 px, float fr){
  vec2 uv = clamp(px / uRes, vec2(0.0), vec2(1.0));
  vec3 c = mix(texture2D(uScene, uv).rgb, texture2D(uBlur, uv).rgb, fr);
  c = mix(c, veil(c, px.y), 1.0 - uM3.z);   // скло «збирає світло» — під ним вуаль слабша
  return mix(c, uUnderTint, uUnder.y);
}
float hash(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
void main(){
  vec2 p = gl_FragCoord.xy;
  if (p.x < uClip.x || p.y < uClip.y || p.x > uClip.z || p.y > uClip.w) discard;
  vec2 q = p - uBox.xy;
  float r = min(uRad, min(uBox.z, uBox.w));
  float d = sdRR(q, uBox.zw, r);
  float cov = clamp(0.5 - d, 0.0, 1.0) * uUnder.z;
  float shA = 0.0;
  if (uM2.w > 0.0) {   // м'яка тінь трохи нижче елемента
    float sd = sdRR(q + vec2(0.0, 6.0 * uK), uBox.zw, r);
    shA = uM2.w * uUnder.z * (1.0 - smoothstep(-6.0 * uK, 24.0 * uK, sd));
  }
  if (cov <= 0.0) { if (shA < 0.004) discard; gl_FragColor = vec4(0.0, 0.0, 0.0, shA); return; }
  vec2 e = vec2(1.0, 0.0);
  vec2 g = vec2(sdRR(q + e, uBox.zw, r) - sdRR(q - e, uBox.zw, r), sdRR(q + e.yx, uBox.zw, r) - sdRR(q - e.yx, uBox.zw, r));
  g /= max(length(g), 1e-4);                                  // нормаль краю назовні
  float x = 1.0 - clamp(-d / max(uM1.x, 1.0), 0.0, 1.0);       // 1 на краю → 0 там, де фаска скінчилась
  float bend = 1.0 - pow(max(1.0 - pow(x, uM3.x), 0.0), 1.0 / uM3.x);   // профіль: 2 — дуга (широка лінза), 4 — сквіркл (лише біля краю)
  float fr = max(uM1.z, uUnder.x) * (1.0 - uM3.y * smoothstep(0.0, 0.35, bend));   // кромка прозора — видно, як гнеться фон
  vec2 off = g * bend * uM1.y * uHot.w;
  vec2 ca = g * bend * uM1.y * uM2.x;
  vec3 col = vec3(S(p + off + ca, fr).r, S(p + off, fr).g, S(p + off - ca, fr).b);
  float L = dot(col, vec3(0.299, 0.587, 0.114));
  col = max(mix(vec3(L), col, uBoost), 0.0);
  col = mix(col, uTint, uM1.w);
  vec3 N = normalize(vec3(g * bend * 1.6, 1.0));
  vec2 Ld = normalize(mix(uLight, normalize(uHot.xy - uBox.xy + 1e-3), 0.6 * uHot.z));
  vec3 Hh = normalize(normalize(vec3(Ld, 0.55)) + vec3(0.0, 0.0, 1.0));
  float sp = pow(max(dot(N, Hh), 0.0), 40.0) * uM2.z * smoothstep(0.0, 0.3, bend);
  float face = dot(g, Ld);
  float rimW = 1.0 - smoothstep(0.0, 1.5 * uK, -d);            // кромка 1,5 css px
  col *= 1.0 - rimW * 0.4 * max(-face, 0.0) * sign(uM2.y);      // тіньовий бік кромки
  float lit = rimW * (0.3 + 0.7 * max(face, 0.0)) + pow(bend, 3.0) * 0.22;   // кромка + Френель
  col += uRimC * lit * uM2.y + sp;
  if (uHot.z > 0.0) { float md = length(p - uHot.xy) / (120.0 * uK); col += uHot.z * 0.07 * exp(-md * md * 2.5); }
  col += (hash(p) - 0.5) / 255.0;
  gl_FragColor = vec4(col * cov, cov + shA * (1.0 - cov));
}`;
  const LG_PROGS = { kd: { id: '_lgkd', frag: KD_FS }, blit: { id: '_lgblit', frag: BLIT_FS }, glass: { id: '_lgglass', frag: GLASS_FS } };

  // Цілі рендеру: сцена + рівні розмиття. Перестворюються при зміні розміру; втрата контексту — lgT = null.
  let lgT = null;
  function lgTarget(w, h) {
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    return { t, f, w, h };
  }
  function lgTargets(sw, sh, levels) {
    const key = sw + 'x' + sh + ':' + levels;
    if (lgT && lgT.key === key) return lgT;
    if (lgT) for (const x of lgT.all) { gl.deleteTexture(x.t); gl.deleteFramebuffer(x.f); }
    const scene = lgTarget(sw, sh), down = [], up = [];
    for (let i = 1; i <= levels; i++) down.push(lgTarget(Math.max(1, sw >> i), Math.max(1, sh >> i)));
    for (let i = levels - 1; i >= 1; i--) up.push(lgTarget(Math.max(1, sw >> i), Math.max(1, sh >> i)));
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return (lgT = { key, scene, down, up, all: [scene, ...down, ...up] });
  }

  // ---- які елементи скляні: [селектор, вид, шар]. Шар — порядок малювання (як z-index у CSS) ----
  const LG_KINDS = [
    ['.titlebar', 'bar', 2], ['aside.side', 'panel', 1], ['#main .toolbar', 'veil', 1], ['#main .stats', 'veil', 1],
    ['.card', 'card', 1], ['.mcard', 'card', 1], ['.brow', 'card', 1], ['.btn', 'btn', 1],
  ];
  const LG_SEL = LG_KINDS.map(k => k[0]).join(',');   // ті самі селектори — у app.css під html.lg-gl
  // поверх цих шарів шейдер не бачить (під ними DOM-вміст) — кнопки в них лишаються на CSS
  const LG_OVER = '.drawer,.pop,.catmenu,.gsx,.toast,.rzc,.ac-card,.rz-home,.rz-news,.rz-hero,.rz-splash,[role=dialog],.updbar';
  const LG_CLIP = '.tablewrap,.side-main,aside.side,.titlebar,.toolbar,.stats';
  const lgSt = new WeakMap();   // елемент → стан
  const lgAll = new Set();      // усі відстежувані (для перескану)
  const lgVis = new Set();      // видимі (IntersectionObserver)
  let lgOrderDirty = true, lgOrder = [];
  const lgIO = 'IntersectionObserver' in window ? new IntersectionObserver(es => {
    for (const e of es) { const s = lgSt.get(e.target); if (!s) continue; if (e.isIntersecting) lgVis.add(s); else lgVis.delete(s); }
    lgOrderDirty = true; lgKick(200);
  }, { rootMargin: '200px' }) : null;
  function lgKindOf(el) {
    for (const k of LG_KINDS) if (el.matches(k[0])) {
      if (k[1] === 'btn' && el.closest(LG_OVER)) return null;
      return k;
    }
    return null;
  }
  function lgTrack(el) {
    if (lgSt.has(el)) return;
    const k = lgKindOf(el); if (!k) return;
    const s = { el, kind: k[1], layer: k[2], parent: null, rad: -1, hot: 0, hotT: 0, primary: el.classList.contains('primary'), danger: el.classList.contains('danger'), clipEl: null };
    for (let p = el.parentElement; p; p = p.parentElement) { const ps = lgSt.get(p); if (ps) { s.parent = ps; s.layer = Math.max(s.layer, ps.layer); break; } }
    s.clipEl = el.parentElement && el.parentElement.closest(LG_CLIP);
    s.top = el; while (s.top.parentElement && s.top.parentElement !== document.body) s.top = s.top.parentElement;   // екран спокою гасить дітей body через opacity
    lgSt.set(el, s); lgAll.add(el);   // без атрибутів у DOM: patchList (core.js) порівнює вузли — мітка зробила б кожну картку «зміненою»
    if (lgIO) lgIO.observe(el); else lgVis.add(s);
  }
  function lgUntrack(el) { const s = lgSt.get(el); if (!s) return; lgSt.delete(el); lgAll.delete(el); lgVis.delete(s); if (lgIO) lgIO.unobserve(el); lgOrderDirty = true; }
  function lgScan(root) {
    if (root.nodeType !== 1) return;
    if (root.matches(LG_SEL)) lgTrack(root);
    root.querySelectorAll(LG_SEL).forEach(lgTrack);   // DOM-порядок: батьки раніше за дітей
  }
  function lgRescan() {
    [...lgAll].forEach(lgUntrack);
    lgScan(document.body);
  }
  new MutationObserver(ms => {
    for (const m of ms) {
      m.removedNodes.forEach(n => { if (n.nodeType !== 1 || n.isConnected) return; lgUntrack(n); if (n.firstElementChild) n.querySelectorAll(LG_SEL).forEach(lgUntrack); });
      m.addedNodes.forEach(lgScan);
    }
    lgOrderDirty = true; lgKick(300);
  }).observe(document.body, { childList: true, subtree: true });

  // наведення: світло і легке світіння йдуть за курсором (у всіх скляних предків під ним)
  const lgPtr = { x: -1e4, y: -1e4, hot: new Set() };
  document.addEventListener('pointerover', e => {
    const now = new Set();
    for (let n = e.target; n && n.nodeType === 1; n = n.parentElement) { const s = lgSt.get(n); if (s) now.add(s); }
    for (const s of lgPtr.hot) if (!now.has(s)) s.hotT = 0;
    for (const s of now) s.hotT = 1;
    lgPtr.hot = now; lgKick(500);
  }, { passive: true });
  window.addEventListener('pointermove', e => { lgPtr.x = e.clientX; lgPtr.y = e.clientY; if (lgPtr.hot.size) lgKick(120); }, { passive: true });
  document.addEventListener('pointerleave', () => { for (const s of lgPtr.hot) s.hotT = 0; lgPtr.hot.clear(); lgKick(500); });
  document.addEventListener('scroll', () => lgKick(250), { capture: true, passive: true });
  document.addEventListener('transitionrun', () => lgKick(700), true);
  document.addEventListener('transitionend', () => lgKick(100), true);
  document.addEventListener('animationstart', () => lgKick(700), true);

  let lgDirtyUntil = 0, lgLastSig = '';
  function lgKick(ms) {
    lgDirtyUntil = Math.max(lgDirtyUntil, performance.now() + ms);
    if (!raf && !document.hidden && !lost && cur && lgActive()) raf = requestAnimationFrame(frame);
  }
  const lgActive = () => lg.on && state.glass && !!cur;
  let lgClassOn = false;
  function lgClass(on) {
    if (on === lgClassOn) return;
    lgClassOn = on;
    document.documentElement.classList.toggle('lg-gl', on);
    if (on) lgRescan();
    gfxChanged();   // glass.js знімає/повертає SVG-фільтри
  }
  lg.rescan = () => { lgRescan(); lgKick(300); };

  const rgbOf = v => { const m = String(v).split(',').map(x => +x / 255); return m.length === 3 && m.every(x => x >= 0) ? m : null; };
  let lgAccent = [1, 0.18, 0.18], lgErr = [1, 0.42, 0.42];
  window.addEventListener('rzgfx', () => { const cs = getComputedStyle(document.documentElement); lgAccent = rgbOf(cs.getPropertyValue('--c2-rgb')) || lgAccent; lgErr = rgbOf(cs.getPropertyValue('--err-rgb')) || lgErr; });
  const DARK = [6 / 255, 6 / 255, 6 / 255], WHITE = [1, 1, 1];

  // Матеріал за видом (css px; у шейдер — буферні). tint/ta — колір і сила тону; under — що бачать діти
  function lgMat(s) {
    const P = LGP, dens = state.panel / 100;
    switch (s.kind) {
      case 'btn': return { bev: -P.bevel, refr: P.refr, frost: 0.25, tint: s.primary ? lgAccent : s.danger ? lgErr : WHITE, ta: s.primary ? 0.3 : s.danger ? 0.12 : 0.035, disp: P.disp, rim: P.rim, spec: P.spec, shadow: P.shadow * 0.7 };
      case 'panel': return { bev: 22, refr: P.refr * 1.4, frost: P.frost, tint: DARK, ta: Math.min(0.95, P.tintPanel * dens), disp: P.disp * 0.6, rim: P.rim * 0.7, spec: P.spec * 0.5, shadow: 0 };
      case 'bar': return { bev: 8, refr: 6, frost: P.frost, tint: DARK, ta: Math.min(0.95, (P.tintPanel + 0.1) * dens), disp: 0, rim: P.rim * 0.5, spec: 0, shadow: 0 };
      case 'card': return { bev: 18, refr: P.refr, frost: P.frost * 0.8, tint: DARK, ta: Math.min(0.95, P.tintCard * dens), disp: P.disp, rim: P.rim, spec: P.spec * 0.7, shadow: P.shadow };
      default: return { bev: 1, refr: 0, frost: 0, tint: DARK, ta: 0.5 * dens, disp: 0, rim: 0, spec: 0, shadow: 0 };   // veil: лише тон
    }
  }

  // Збирає видимі скляні прямокутники цього кадру. sig — відбиток, щоб не перемальовувати однаковий кадр
  function lgCollect(k, bh, bw) {
    if (lgOrderDirty) {
      lgOrder = [...lgVis].filter(s => s.el.isConnected);
      lgOrder.sort((a, b) => a.layer - b.layer || (a.el.compareDocumentPosition(b.el) & 4 ? -1 : 1));
      lgOrderDirty = false;
    }
    const out = [], clipCache = new Map(), topOp = new Map();
    let sig = '';
    for (const s of lgOrder) {
      const r = s.el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      let c = null;
      if (s.clipEl) { c = clipCache.get(s.clipEl); if (!c) clipCache.set(s.clipEl, c = s.clipEl.getBoundingClientRect()); }
      const cx0 = c ? c.left : 0, cy0 = c ? c.top : 0, cx1 = c ? c.right : bw / k, cy1 = c ? c.bottom : bh / k;
      if (r.right < cx0 || r.left > cx1 || r.bottom < cy0 || r.top > cy1) continue;
      if (s.rad < 0) { const cs = getComputedStyle(s.el); s.rad = parseFloat(cs.borderTopLeftRadius) || 0; s.fade = s.kind === 'card'; }
      let to = topOp.get(s.top); if (to == null) topOp.set(s.top, to = +getComputedStyle(s.top).opacity);
      if (!(to > 0.004)) continue;
      s.op = (s.fade ? +getComputedStyle(s.el).opacity || 1 : 1) * to;
      s.hot += (s.hotT - s.hot) * 0.25; if (Math.abs(s.hotT - s.hot) < 0.01) s.hot = s.hotT;
      s.r = r; s.c = [cx0, cy0, cx1, cy1];
      s.active = s.kind === 'card' && (s.el.classList.contains('active') || s.el.classList.contains('sel'));
      s.dis = s.kind === 'btn' && s.el.disabled;
      out.push(s);
      sig += r.left.toFixed(1) + ',' + r.top.toFixed(1) + ',' + r.width.toFixed(1) + ',' + r.height.toFixed(1) + ',' + s.hot.toFixed(2) + ',' + s.op + (s.active ? 'a' : '') + ';';
    }
    sig += lgPtr.hot.size ? lgPtr.x + ',' + lgPtr.y : '';
    return { list: out, sig };
  }

  // Кадр скла: сцена вже в lgT.scene. Розмиття → екран (фон з вуаллю) → скляні прямокутники
  function lgRender(T, bw, bh, k, list, blurNew) {
    const pk = programs.get(LG_PROGS.kd), pb = programs.get(LG_PROGS.blit), pg = programs.get(LG_PROGS.glass);
    if (!pk || !pb || !pg) return false;
    if (blurNew) {
      gl.useProgram(pk.prog);
      gl.activeTexture(gl.TEXTURE0);
      gl.uniform1i(pk.u('uT'), 0);
      let src = T.scene;
      const pass = (dst, up) => {
        gl.bindFramebuffer(gl.FRAMEBUFFER, dst.f); gl.viewport(0, 0, dst.w, dst.h);
        gl.bindTexture(gl.TEXTURE_2D, src.t);
        gl.uniform2f(pk.u('uDst'), dst.w, dst.h);
        gl.uniform2f(pk.u('uOff'), 0.5 / src.w, 0.5 / src.h);
        gl.uniform1f(pk.u('uUp'), up ? 1 : 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        src = dst;
      };
      for (const d of T.down) pass(d, false);
      for (const u of T.up) pass(u, true);
    }
    const blurT = T.up.length ? T.up[T.up.length - 1] : T.down[T.down.length - 1];
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, bw, bh);
    const veilOp = (state.panel / 100) * (1 - boost.idleK);   // екран спокою ховає вуаль, як і CSS
    gl.useProgram(pb.prog);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, T.scene.t);
    gl.uniform1i(pb.u('uScene'), 0);
    gl.uniform2f(pb.u('uRes'), bw, bh); gl.uniform1f(pb.u('uK'), k); gl.uniform1f(pb.u('uVeil'), veilOp);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (!list.length) return true;

    gl.useProgram(pg.prog);
    const u = pg.u;
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, blurT.t);
    gl.uniform1i(u('uScene'), 0); gl.uniform1i(u('uBlur'), 1);
    gl.uniform2f(u('uRes'), bw, bh); gl.uniform1f(u('uK'), k); gl.uniform1f(u('uVeil'), veilOp);
    gl.uniform2f(u('uLight'), -0.55, 0.835);
    gl.uniform1f(u('uBoost'), LGP.boost);
    gl.uniform3f(u('uM3'), LGP.profile, LGP.clear, LGP.lift);
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);
    gl.enable(gl.SCISSOR_TEST);
    const mats = new Map();
    let draws = 0;
    for (const s of list) {
      const m = lgMat(s); mats.set(s, m);
      const r = s.r, w = r.width * k, h = r.height * k;
      const cx = r.left * k + w / 2, cy = bh - (r.top * k + h / 2);
      const pad = m.shadow > 0 ? 32 * k : 2;
      const c = s.c;
      const x0 = Math.max(0, Math.floor(Math.max(r.left * k - pad, c[0] * k))), x1 = Math.min(bw, Math.ceil(Math.min(r.right * k + pad, c[2] * k)));
      const y0 = Math.max(0, Math.floor(Math.max(bh - r.bottom * k - pad, bh - c[3] * k))), y1 = Math.min(bh, Math.ceil(Math.min(bh - r.top * k + pad, bh - c[1] * k)));
      if (x1 <= x0 || y1 <= y0) continue;
      gl.scissor(x0, y0, x1 - x0, y1 - y0);
      const rad = Math.min(s.rad * k, w / 2, h / 2);
      const bev = m.bev < 0 ? Math.min(w, h) / 2 * -m.bev : m.bev * k;
      gl.uniform4f(u('uBox'), cx, cy, w / 2, h / 2);
      gl.uniform1f(u('uRad'), rad);
      gl.uniform4f(u('uClip'), c[0] * k, bh - c[3] * k, c[2] * k, bh - c[1] * k);
      const dim = s.dis ? 0.45 : 1;
      gl.uniform4f(u('uM1'), bev, m.refr * k, m.frost, m.ta);
      gl.uniform4f(u('uM2'), m.disp, m.rim * dim, m.spec * dim, m.shadow);
      gl.uniform3fv(u('uTint'), m.tint);
      gl.uniform3fv(u('uRimC'), s.active ? lgAccent : WHITE);
      const pm = s.parent && mats.get(s.parent);
      gl.uniform3f(u('uUnder'), pm ? pm.frost : 0, pm ? pm.ta : 0, s.op);
      gl.uniform3fv(u('uUnderTint'), pm ? pm.tint : DARK);
      gl.uniform4f(u('uHot'), lgPtr.x * k, bh - lgPtr.y * k, s.hot, LGP.sign);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      draws++;
    }
    gl.disable(gl.SCISSOR_TEST); gl.disable(gl.BLEND);
    lg.stat.draws = draws;
    return true;
  }

  // Курсор по всьому вікну (інтерфейс лежить поверх фону)
  const ps = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0, active: 0, ta: 0 };
  window.addEventListener('pointermove', e => {
    ps.tx = e.clientX; ps.ty = e.clientY; // y рахуємо від верху — як і в шейдері
    ps.ta = 1;
  }, { passive: true });
  document.addEventListener('pointerout', e => { if (!e.relatedTarget) ps.ta = 0; });

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  let cur = null, pr = null, col = null;   // активний фон, його програма, кольори
  let raf = 0, last = 0, clock = 0;
  let focused = document.hasFocus();
  const qual = () => QUALITY[state.quality === 'auto' ? autoLevel : state.quality];
  const isLive = () => state.motion && !reduced.matches && (focused || !state.pauseBlur);

  // Фон-індикатор: lv — плавний рівень пошуку, pulse — спалах, що згасає
  const boost = { level: -1, lv: 0, pulse: 0, pending: '', flash: new Float32Array(4), idle: false, idleK: 0 };
  const NO_FLASH = new Float32Array(4);

  // «Авто»: якщо більше половини з 90 кадрів ідуть у 1.6 раза довше належного — спускаємось на рівень нижче.
  // Вгору не повертаємось (не гойдатись); заново міряємо, коли «Авто» вибрано знову.
  const perf = { n: 0, slow: 0, skip: 30 };
  function measure(iv, q) {
    if (perf.skip > 0) { perf.skip--; return; }
    perf.n++;
    if (iv > 1000 / (q.fps || 60) * 1.6) perf.slow++;
    if (perf.n < 90) return;
    const bad = perf.slow > perf.n / 2, i = LEVELS.indexOf(autoLevel);
    perf.n = perf.slow = 0;
    if (!bad || i >= LEVELS.length - 1) return;
    autoLevel = LEVELS[i + 1]; saveAuto(); perf.skip = 30;
    if (api.onauto) api.onauto(autoLevel, QUALITY[autoLevel].label);
    gfxChanged();
  }

  // 3.2: кадр = сцена (за стелею кадрів) + скло (щойно щось зрушило: прокрутка, наведення, анімація).
  // Без скла — як раніше: сцена прямо в canvas. Зі склом сцена йде в текстуру, а скло домальовується
  // і між кадрами сцени — тож картки при прокрутці не відстають навіть на «Среднем» (30 кадрів фону).
  let sceneStale = true;
  function frame(now) {
    raf = 0;
    if (!cur || lost) return;
    const t0 = performance.now();
    const q = qual(), live = isLive(), glassOn = lgActive() && !!programs.get(LG_PROGS.glass);
    lgClass(glassOn);
    const busy = glassOn && now < lgDirtyUntil;
    if (live || busy || (glassOn && lgPtr.hot.size && [...lgPtr.hot].some(s => s.hot !== s.hotT))) raf = requestAnimationFrame(frame);
    const sceneDue = sceneStale || (live && !(q.fps && last && now - last < 1000 / q.fps - 2));

    // розмір: зі склом canvas — повна щільність (кромки й текст скла чіткі), а сцена — з q.scale і res фону
    const cw = canvas.clientWidth || 1200, ch = canvas.clientHeight || 800;
    const cdpr = glassOn ? Math.min(window.devicePixelRatio || 1, q.dpr) : Math.min(window.devicePixelRatio || 1, q.dpr) * q.scale * (cur.res || 1);
    const bw = Math.max(1, Math.round(cw * cdpr)), bh = Math.max(1, Math.round(ch * cdpr));
    if (canvas.width !== bw || canvas.height !== bh) { canvas.width = bw; canvas.height = bh; }
    const sres = glassOn ? q.scale * (cur.res || 1) * LGP.sceneRes : 1;
    const sw = Math.max(1, Math.round(bw * sres)), sh = Math.max(1, Math.round(bh * sres));

    let col2 = null;
    if (glassOn) {
      const tc = performance.now();
      col2 = lgCollect(bw / cw, bh, bw);
      lg.stat.col = performance.now() - tc; lg.stat.nvis = lgOrder.length;
      if (!sceneDue && col2.sig === lgLastSig) return;   // нічого не зрушило
    } else if (!sceneDue) return;

    let T = null;
    if (sceneDue) {
      sceneStale = false;
      const iv = last ? now - last : 0;
      const dt = live ? Math.min(0.05, iv / 1000) : 0;
      last = now;
      if (live && state.quality === 'auto' && iv > 0 && iv < 250) measure(iv, q);   // довші паузи — не гальма фону, а згорнуте вікно чи важка операція

      const target = state.react && boost.level >= 0 ? 0.25 + 0.35 * boost.level : 0;
      if (live) {
        if (boost.pending) { boost.pulse = 1; boost.flash.set(hex(FLASH[boost.pending][1])); boost.pending = ''; }
        boost.lv += (target - boost.lv) * Math.min(1, dt * 3);
        boost.pulse *= Math.exp(-dt * 2.2);
      } else { boost.lv = target; boost.pulse = 0; }
      clock = (clock + dt * cur.speed * state.speed / 100 * (1 + 2 * boost.lv)) % cur.wrap;

      const pl = Math.min(1, dt * 12), al = Math.min(1, dt * 6);
      const nx = ps.x + (ps.tx - ps.x) * pl, ny = ps.y + (ps.ty - ps.y) * pl;
      if (dt > 0) { const kv = 1 - Math.exp(-dt * 8); ps.vx += ((nx - ps.x) / dt - ps.vx) * kv; ps.vy += ((ny - ps.y) / dt - ps.vy) * kv; }
      ps.on = state.pointer ? ps.ta : 0;   // «Фон тягнеться до курсора» вимкнено — курсора для фону нема
      ps.x = nx; ps.y = ny; ps.active += (ps.on - ps.active) * al;

      boost.flash[3] = boost.pulse;
      boost.idleK += ((boost.idle ? 1 : 0) - boost.idleK) * (live ? Math.min(1, dt * 2) : 1);   // екран спокою — фон на повну яскравість
      const gain = (state.bright / 100 + (1 - state.bright / 100) * boost.idleK) * (1 + boost.lv + boost.pulse * 0.9);
      if (glassOn) {
        T = lgTargets(sw, sh, Math.max(1, Math.min(5, LGP.levels | 0)));
        gl.bindFramebuffer(gl.FRAMEBUFFER, T.scene.f);
        gl.viewport(0, 0, sw, sh);
        paint(gl, pr, cur, col, clock, gain, boost.flash, { bw: sw, bh: sh, cw, ch, k: sw / cw, ps, live });
      } else {
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        gl.viewport(0, 0, bw, bh);
        paint(gl, pr, cur, col, clock, gain, boost.flash, { bw, bh, cw, ch, k: bw / cw, ps, live });
      }
    }
    if (glassOn) {
      T = T || lgTargets(sw, sh, Math.max(1, Math.min(5, LGP.levels | 0)));
      lgRender(T, bw, bh, bw / cw, col2.list, sceneDue);
      lgLastSig = col2.sig;
    }
    const js = performance.now() - t0;
    lg.stat.js = lg.stat.js * 0.95 + js * 0.05; lg.stat.n++;
  }
  function kick() { sceneStale = true; if (!raf && !document.hidden && !lost) { last = 0; perf.n = perf.slow = 0; perf.skip = 30; raf = requestAnimationFrame(frame); } }
  lg.redraw = kick;
  lg.frameNow = () => { sceneStale = true; lgLastSig = ''; cancelAnimationFrame(raf); frame(performance.now()); };   // стенд: кадр без rAF (скрытая панель)

  apply = () => {
    if (lost) return;   // поверниться — webglcontextrestored викличе apply() сам
    const b = BACKGROUNDS.find(x => x.id === bgId()) || null;
    const p = b && programs.get(b);
    if (b !== cur) clock = 0;
    cur = p ? b : null; pr = p;
    canvas.style.display = cur ? '' : 'none';
    if (!cur) { cancelAnimationFrame(raf); raf = 0; lgClass(false); return; }   // «Без фона» — скла в шейдері нема, працює CSS
    col = colorsOf(cur);
    kick();
  };

  api.idle = on => { boost.idle = !!on; kick(); };
  api.level = p => { boost.level = p == null ? -1 : Math.min(1, Math.max(0, +p || 0)); kick(); };
  api.pulse = kind => { if (state.react) { boost.pending = FLASH[kind] ? kind : 'reply'; kick(); } };   // без анімації чи у фоні — спалахне, коли фон знову оживе

  // Мініатюри: окремий маленький контекст, кадр копіюється в canvas кнопки. Сцена рахується як вікно TV_W×TV_H,
  // щоб фони з розмірами в px (точки, плашки) виглядали собою. Малюємо, лише поки список на екрані.
  // Контекст і таймер з'являються при першому показі вкладки «Графика», таймер стоїть, поки список не видно.
  const TH_W = 128, TH_H = 72, TV_W = 512, TV_H = 288;
  let thumbs = null;
  api.previews = items => {
    if (thumbs) return;
    thumbs = items.map(it => ({ b: BACKGROUNDS.find(b => b.id === it.id), el: it.canvas, ctx: it.canvas.getContext('2d') })).map(t => Object.assign(t, { t: t.b ? t.b.thumbT || 0 : 0 })).filter(t => t.b && t.ctx);
    if (!thumbs.length) return;
    const still = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0, active: 0, ta: 0 };
    const f = { bw: TH_W, bh: TH_H, cw: TV_W, ch: TV_H, k: TH_W / TV_W, ps: still, live: false, thumb: true };
    let tc = null, tgl = null, tprog = null, tried = false, timer = 0, prev = 0;
    const init = () => {
      tried = true;
      tc = document.createElement('canvas'); tc.width = TH_W; tc.height = TH_H;
      tgl = tc.getContext('webgl', glOpts);
      if (!tgl) return;
      tc.addEventListener('webglcontextlost', e => { e.preventDefault(); tprog = null; }, false);
      tc.addEventListener('webglcontextrestored', () => { tprog = setup(tgl); tgl.viewport(0, 0, TH_W, TH_H); }, false);
      tprog = setup(tgl); tgl.viewport(0, 0, TH_W, TH_H);
    };
    const stop = () => { clearInterval(timer); timer = 0; prev = 0; };
    const start = () => { if (timer) return; if (!tried) init(); if (!tgl) return; prev = 0; timer = setInterval(tick, 110); tick(); };
    const host = thumbs[0].el.closest('.gfxlist') || thumbs[0].el;
    if ('IntersectionObserver' in window) new IntersectionObserver(es => { if (es[es.length - 1].isIntersecting) start(); else stop(); }).observe(host);
    else start();
    function tick() {
      if (!tprog || document.hidden || thumbs[0].el.offsetParent === null) { prev = 0; return; }
      const now = performance.now(), dt = prev && isLive() ? Math.min(0.25, (now - prev) / 1000) : 0;
      prev = now;
      let fresh = false;   // не більше однієї нової збірки шейдера за тік — щоб не було ривка при відкритті вкладки
      for (const t of thumbs) {
        if (!tprog.has(t.b)) { if (fresh) continue; fresh = true; }
        const p = tprog.get(t.b);
        if (!p) continue;
        t.t = (t.t + dt * t.b.speed * state.speed / 100) % t.b.wrap;
        paint(tgl, p, t.b, colorsOf(t.b), t.t, 1, NO_FLASH, f);
        t.ctx.drawImage(tc, 0, 0, t.el.width, t.el.height);
      }
    }
  };

  // «Шапка профиля» (2.81): любой фон зі списку в canvas профілю своїм тоном — tone з TONES, 'red' / 'orig' — палітри самого фону.
  // Один спільний маленький контекст на всі шапки, кадр копіюється в canvas шапки. Сцена — як вікно 960×240 (точки фону свого розміру).
  // Малюємо, лише поки шапка на екрані; без анімації — один кадр.
  const BN_W = 480, BN_H = 120, bnStill = { x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0, active: 0, ta: 0 };
  let bnGl = null, bnProg = null, bnCanvas = null, bnTimer = 0;
  const banners = new Set();
  const bannerColors = (b, tone) => {
    const c = (tone === 'red' || tone === 'orig') && b.colors[tone];
    if (c) return { bg: hex(c.bg), base: hex(c.base), accent: hex(c.accent), high: hex(c.high) };
    const t = TONES.find(x => x[0] === tone) || TONES.find(x => x[0] === 'blue');
    return { bg: hex('#030303'), base: hex(t[3]), accent: hex(t[2]), high: hex('#FFFFFF') };
  };
  function bannerTick(){
    const f = { bw: BN_W, bh: BN_H, cw: 960, ch: 240, k: BN_W / 960, ps: bnStill, live: false, thumb: true };
    const now = performance.now(), live = isLive();
    for (const h of banners) {
      if (!h.el.isConnected) { banners.delete(h); continue; }
      if (document.hidden || h.el.offsetParent === null) { h.prev = 0; continue; }
      if (!live && h.drawn) continue;
      const p = bnProg && bnProg.get(h.b); if (!p) continue;   // контекст втрачено — чекаємо на повернення
      const dt = h.prev && live ? Math.min(0.25, (now - h.prev) / 1000) : 0;
      h.prev = now;
      h.t = (h.t + dt * h.b.speed * state.speed / 100) % h.b.wrap;
      bnGl.viewport(0, 0, BN_W, BN_H);
      paint(bnGl, p, h.b, h.col, h.t, 1, NO_FLASH, f);
      h.ctx.drawImage(bnCanvas, 0, 0, h.el.width, h.el.height);
      h.drawn = true;
    }
    if (!banners.size) { clearInterval(bnTimer); bnTimer = 0; }
  }
  api.banner = (el, o) => {
    const ctx = el && el.getContext && el.getContext('2d');
    const h = { el, ctx, t: 0, prev: 0, drawn: false,
      set(o){ o = o || {}; this.b = BACKGROUNDS.find(x => x.id === o.bg) || BACKGROUNDS[0]; this.col = bannerColors(this.b, o.tone); this.t = this.b.thumbT || 0; this.drawn = false; },
      stop(){ banners.delete(this); } };
    if (!ctx) return h;
    h.set(o);
    if (!bnCanvas) {
      bnCanvas = document.createElement('canvas'); bnCanvas.width = BN_W; bnCanvas.height = BN_H; bnGl = bnCanvas.getContext('webgl', glOpts); bnProg = bnGl && setup(bnGl);
      bnCanvas.addEventListener('webglcontextlost', e => { e.preventDefault(); bnProg = null; }, false);
      bnCanvas.addEventListener('webglcontextrestored', () => { bnProg = setup(bnGl); for (const x of banners) x.drawn = false; if (banners.size && !bnTimer) bnTimer = setInterval(bannerTick, 50); }, false);
    }
    if (!bnGl) return h;
    banners.add(h);
    if (!bnTimer) bnTimer = setInterval(bannerTick, 50);
    setTimeout(bannerTick, 0);
    return h;
  };

  document.addEventListener('visibilitychange', () => { if (document.hidden) { cancelAnimationFrame(raf); raf = 0; } else kick(); });
  window.addEventListener('blur', () => { ps.ta = 0; focused = false; });   // з «паузою в неактивному вікні» наступний кадр стане останнім
  window.addEventListener('focus', () => { focused = true; kick(); });
  window.addEventListener('resize', kick);   // без анімації кадр перемальовуємо самі
  reduced.addEventListener('change', kick);
  apply();
})();
