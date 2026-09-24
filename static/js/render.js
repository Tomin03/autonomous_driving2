const COLORS = {
  accent: "rgb(124, 58, 237)",
  ok: "rgb(16, 185, 129)",
  danger: "rgb(225, 29, 72)",
  text: "rgb(26, 11, 46)",
  muted: "rgb(110, 94, 128)",
  warn: "rgb(217, 119, 6)",
  board: "rgb(244, 241, 248)",
  border: "rgb(26, 11, 46)",
  grid: "rgb(228, 220, 238)",
  occStroke: "rgb(180, 168, 196)",
  occFill: "rgb(70, 55, 92)",
  target: "rgb(16, 185, 129)",
  start: "rgb(109, 40, 217)",
  axle: "rgb(249, 115, 22)",
  selected: "rgb(167, 139, 250)",
  wheel: "rgb(20, 20, 20)",
};

let CFG = {
  px_per_m: 17.6,
  board: 600,
  snap: 10,
  spot_w: 44,
  spot_h: 88,
  car_w: 24,
  car_h: 60,
  rear: 10,
  max_v: 90,
  max_v_min: 24.4,
  max_v_max: 97.8,
  max_v_kmh_min: 5,
  max_v_kmh_max: 20,
  dim_limits: {
    car_w: [14, 48],
    car_h: [36, 96],
    spot_w: [28, 90],
    spot_h: [56, 180],
    obstacle_w: [28, 90],
    obstacle_h: [56, 180],
  },
  train_steps_min: 1000,
  train_steps_max: 1_000_000,
  train_steps_default: 350_000,
};

function setConfig(cfg) {
  CFG = { ...CFG, ...cfg };
}

function pxToM(px) {
  return Number(px) / (CFG.px_per_m || 17.6);
}

function parseM(value) {
  const n = Number(String(value).trim().replace(",", "."));
  return Number.isFinite(n) ? n : NaN;
}

function mToPx(m) {
  return Math.round(parseM(m) * (CFG.px_per_m || 17.6));
}

function formatM(px) {
  return pxToM(px).toFixed(2).replace(".", ",");
}

function kmhToPx(kmh) {
  return mToPx(parseM(kmh) / 3.6);
}

function pxToKmh(px) {
  return pxToM(px) * 3.6;
}

function clampDim(key, value) {
  const lim = CFG.dim_limits?.[key];
  const n = Math.round(Number(value));
  if (!lim || !Number.isFinite(n)) return Math.round(Number(CFG[key] ?? value) || 0);
  return Math.max(lim[0], Math.min(lim[1], n));
}

function sizesOf(data) {
  const carW = clampDim("car_w", data?.car_w ?? CFG.car_w);
  const carH = clampDim("car_h", data?.car_h ?? CFG.car_h);
  const spotW = clampDim("spot_w", data?.spot_w ?? CFG.spot_w);
  const spotH = clampDim("spot_h", data?.spot_h ?? CFG.spot_h);
  const obsW = clampDim("obstacle_w", data?.obstacle_w ?? CFG.spot_w);
  const obsH = clampDim("obstacle_h", data?.obstacle_h ?? CFG.spot_h);
  const rearRatio = CFG.rear / CFG.car_h;
  const obsCarW = Math.max(8, Math.round(CFG.car_w * obsW / CFG.spot_w));
  const obsCarH = Math.max(12, Math.round(CFG.car_h * obsH / CFG.spot_h));
  return {
    car_w: carW,
    car_h: carH,
    rear: carH * rearRatio,
    spot_w: spotW,
    spot_h: spotH,
    obstacle_w: obsW,
    obstacle_h: obsH,
    obstacle_car_w: obsCarW,
    obstacle_car_h: obsCarH,
    obstacle_rear: obsCarH * rearRatio,
  };
}

function mapLabel(name) {
  if (name.startsWith("map_") && /^\d+$/.test(name.slice(4))) {
    return `Mapa ${name.slice(4)}`;
  }
  return name;
}

function spotSize(orientation, w = CFG.spot_w, h = CFG.spot_h) {
  return orientation === "vertical" ? [w, h] : [h, w];
}

function snap(v, grid = CFG.snap) {
  return Math.round(v / grid) * grid;
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

function clampSpot(x, y, orient, w = CFG.spot_w, h = CFG.spot_h) {
  const [sw, sh] = spotSize(orient, w, h);
  return [
    clamp(x, 8, CFG.board - sw - 8) | 0,
    clamp(y, 8, CFG.board - sh - 8) | 0,
  ];
}

function reclampMapGeometry(data) {
  if (!data) return;
  const sz = sizesOf(data);
  const t = data.target_spot;
  if (t) {
    const orient = t.orientation || "vertical";
    const [x, y] = clampSpot(t.x, t.y, orient, sz.spot_w, sz.spot_h);
    t.x = x;
    t.y = y;
  }
  for (const s of data.occupied_spots || []) {
    const orient = s.orientation || "vertical";
    const [x, y] = clampSpot(s.x, s.y, orient, sz.obstacle_w, sz.obstacle_h);
    s.x = x;
    s.y = y;
  }
}

function startCorners(x, y, theta, carW = CFG.car_w, carH = CFG.car_h, rear = CFG.rear) {
  const fx = Math.cos(theta);
  const fy = Math.sin(theta);
  const rx = -Math.sin(theta);
  const ry = Math.cos(theta);
  const halfW = carW / 2;
  const front = carH - rear;
  const pts = [];
  for (const [along, across] of [
    [front, halfW],
    [front, -halfW],
    [-rear, -halfW],
    [-rear, halfW],
  ]) {
    pts.push([x + along * fx + across * rx, y + along * fy + across * ry]);
  }
  return pts;
}

function pointInPoly(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i];
    const [xj, yj] = pts[j];
    if (yi > py !== yj > py && px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-9) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

function rgb(arr, alpha = 1) {
  if (alpha < 1) return `rgba(${arr[0]}, ${arr[1]}, ${arr[2]}, ${alpha})`;
  return `rgb(${arr[0]}, ${arr[1]}, ${arr[2]})`;
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function drawPolygon(ctx, pts, { fill, stroke, lineWidth = 2 } = {}) {
  if (!pts || pts.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  if (fill) {
    ctx.fillStyle = fill;
    ctx.fill();
  }
  if (stroke) {
    ctx.strokeStyle = stroke;
    ctx.lineWidth = lineWidth;
    ctx.stroke();
  }
}

const CAR_SVG = {
  cx: 120,
  front: 32,
  rear: 370,
};

const CAR_PAINT = {
  red: {
    shadow: "rgba(0, 0, 0, 0.28)",
    body: "#D8000F",
    hood: "#C2000C",
    cabin: "#B8000A",
    crease: "#A00008",
    handle: "#8A0006",
    bumper: "#900008",
  },
  black: {
    shadow: "rgba(0, 0, 0, 0.28)",
    body: "#2A2A2A",
    hood: "#1F1F1F",
    cabin: "#161616",
    crease: "#0C0C0C",
    handle: "#080808",
    bumper: "#050505",
  },
};

function fillPath(ctx, d, fill) {
  const p = new Path2D(d);
  ctx.fillStyle = fill;
  ctx.fill(p);
}

function strokePath(ctx, d, stroke, width, alpha = 1) {
  const p = new Path2D(d);
  ctx.save();
  ctx.globalAlpha *= alpha;
  ctx.strokeStyle = stroke;
  ctx.lineWidth = width;
  ctx.stroke(p);
  ctx.restore();
}

function drawSportsWheel(ctx, cx, cy, steer) {
  ctx.save();
  ctx.translate(cx, cy);
  if (steer) ctx.rotate(-steer);
  ctx.fillStyle = "#1a1a1a";
  roundRect(ctx, -14, -26, 28, 52, 8);
  ctx.fill();
  ctx.fillStyle = "#111111";
  roundRect(ctx, -10, -22, 20, 44, 5);
  ctx.fill();
  ctx.strokeStyle = "#333333";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, -16);
  ctx.lineTo(0, 16);
  ctx.moveTo(-6, 0);
  ctx.lineTo(6, 0);
  ctx.stroke();
  ctx.fillStyle = "#222222";
  ctx.beginPath();
  ctx.arc(0, 0, 4, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawSportsCar(ctx, car, paint = CAR_PAINT.red) {
  const height = car.height || CFG.car_h;
  const rear = car.rear_axle_offset_y ?? car.rear ?? CFG.rear;
  const svgLen = CAR_SVG.rear - CAR_SVG.front;
  const scale = height / svgLen;
  const rearY = CAR_SVG.rear - rear / scale;
  const phi = car.phi || 0;

  ctx.save();
  ctx.translate(car.x, car.y);
  ctx.rotate(car.theta || 0);
  ctx.transform(0, scale, -scale, 0, scale * rearY, -scale * CAR_SVG.cx);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";

  ctx.fillStyle = paint.shadow;
  ctx.beginPath();
  ctx.ellipse(120, 210, 88, 185, 0, 0, Math.PI * 2);
  ctx.fill();

  fillPath(ctx, "M60 80 Q60 40 120 32 Q180 40 180 80 L188 300 Q188 360 120 370 Q52 360 52 300 Z", paint.body);
  fillPath(ctx, "M80 80 Q80 48 120 38 Q160 48 160 80 Z", paint.hood);
  fillPath(ctx, "M78 170 Q78 140 120 136 Q162 140 162 170 L162 250 Q162 268 120 270 Q78 268 78 250 Z", paint.cabin);
  fillPath(ctx, "M82 134 Q82 108 120 104 Q158 108 158 134 L162 140 Q162 140 120 136 Q78 140 78 140 Z", paint.cabin);

  ctx.strokeStyle = paint.crease;
  ctx.globalAlpha = 0.55;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(120, 38);
  ctx.lineTo(120, 132);
  ctx.moveTo(120, 270);
  ctx.lineTo(120, 356);
  ctx.stroke();
  strokePath(ctx, "M58 178 L58 268", paint.crease, 1.5, 1);
  strokePath(ctx, "M182 178 L182 268", paint.crease, 1.5, 1);
  ctx.globalAlpha = 1;

  ctx.fillStyle = paint.handle;
  roundRect(ctx, 55, 208, 6, 18, 3);
  ctx.fill();
  roundRect(ctx, 179, 208, 6, 18, 3);
  ctx.fill();

  fillPath(ctx, "M60 148 L38 158 L38 170 L60 166 Z", paint.cabin);
  fillPath(ctx, "M180 148 L202 158 L202 170 L180 166 Z", paint.cabin);

  fillPath(ctx, "M80 44 Q68 46 64 56 L80 62 Z", "#FFF5C0");
  fillPath(ctx, "M160 44 Q172 46 176 56 L160 62 Z", "#FFF5C0");
  ctx.globalAlpha = 0.35;
  fillPath(ctx, "M80 44 Q68 46 64 56 L80 62 Z", "#FFE84A");
  fillPath(ctx, "M160 44 Q172 46 176 56 L160 62 Z", "#FFE84A");
  ctx.globalAlpha = 1;

  fillPath(ctx, "M80 350 Q68 352 64 344 L80 338 Z", "#FF2222");
  fillPath(ctx, "M160 350 Q172 352 176 344 L160 338 Z", "#FF2222");

  ctx.strokeStyle = paint.bumper;
  ctx.globalAlpha = 0.65;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(88, 38);
  ctx.lineTo(88, 42);
  ctx.quadraticCurveTo(120, 36, 132, 42);
  ctx.lineTo(132, 38);
  ctx.stroke();
  ctx.globalAlpha = 1;

  ctx.fillStyle = "#444444";
  roundRect(ctx, 96, 362, 10, 6, 3);
  ctx.fill();
  roundRect(ctx, 134, 362, 10, 6, 3);
  ctx.fill();

  drawSportsWheel(ctx, 48, 114, phi);
  drawSportsWheel(ctx, 192, 114, phi);
  drawSportsWheel(ctx, 48, 306, 0);
  drawSportsWheel(ctx, 192, 306, 0);
  ctx.restore();
}

function drawCar(ctx, car) {
  drawSportsCar(ctx, car, car.hollow ? CAR_PAINT.red : CAR_PAINT.black);
}

function occupiedCarPose(spot, spotW, spotH, carW, carH, rear) {
  const axlePad = 2 * rear;
  const vertical = (spot.orientation || "vertical") === "vertical";
  if (vertical) {
    return {
      x: spot.x + spotW / 2,
      y: spot.y + spotH - axlePad,
      theta: -Math.PI / 2,
      width: carW,
      height: carH,
      rear_axle_offset_y: rear,
    };
  }
  return {
    x: spot.x + axlePad,
    y: spot.y + spotH / 2,
    theta: 0,
    width: carW,
    height: carH,
    rear_axle_offset_y: rear,
  };
}

function drawMapData(ctx, data, { selected = null, showGrid = false, width = null, height = null } = {}) {
  const board = CFG.board;
  const dw = width || ctx.canvas.width;
  const dh = height || ctx.canvas.height;
  ctx.save();
  ctx.scale(dw / board, dh / board);
  ctx.fillStyle = COLORS.board;
  ctx.fillRect(0, 0, board, board);
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 8;
  ctx.strokeRect(0, 0, board, board);

  if (showGrid) {
    ctx.strokeStyle = COLORS.grid;
    ctx.lineWidth = 1;
    for (let g = 50; g < board; g += 50) {
      ctx.beginPath();
      ctx.moveTo(g, 8);
      ctx.lineTo(g, board - 8);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(8, g);
      ctx.lineTo(board - 8, g);
      ctx.stroke();
    }
  }

  const sz = sizesOf(data);

  (data.occupied_spots || []).forEach((s, i) => {
    const [w, h] = spotSize(s.orientation || "vertical", sz.obstacle_w, sz.obstacle_h);
    ctx.strokeStyle = COLORS.occStroke;
    ctx.lineWidth = 2;
    ctx.strokeRect(s.x, s.y, w, h);
    drawSportsCar(
      ctx,
      occupiedCarPose(s, w, h, sz.obstacle_car_w, sz.obstacle_car_h, sz.obstacle_rear),
      CAR_PAINT.black
    );
    if (selected && selected[0] === "occ" && selected[1] === i) {
      ctx.strokeStyle = COLORS.selected;
      ctx.lineWidth = 3;
      ctx.strokeRect(s.x, s.y, w, h);
    }
  });

  const t = data.target_spot;
  if (t) {
    const [w, h] = spotSize(t.orientation || "vertical", sz.spot_w, sz.spot_h);
    ctx.fillStyle = "rgba(16, 185, 129, 0.22)";
    ctx.fillRect(t.x, t.y, w, h);
    ctx.strokeStyle = COLORS.target;
    ctx.lineWidth = 3;
    ctx.strokeRect(t.x, t.y, w, h);
    if (selected && selected[0] === "target") {
      ctx.strokeStyle = COLORS.selected;
      ctx.lineWidth = 3;
      ctx.strokeRect(t.x, t.y, w, h);
    }
  }

  const [sx, sy, th] = data.start_pos;
  drawSportsCar(
    ctx,
    {
      x: sx,
      y: sy,
      theta: th,
      width: sz.car_w,
      height: sz.car_h,
      rear_axle_offset_y: sz.rear,
    },
    CAR_PAINT.red
  );
  if (selected && selected[0] === "start") {
    ctx.strokeStyle = COLORS.selected;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(sx, sy, 16, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

function drawGame(ctx, state) {
  const board = state.width || CFG.board;
  ctx.save();
  ctx.scale(ctx.canvas.width / board, ctx.canvas.height / board);
  ctx.fillStyle = COLORS.board;
  ctx.fillRect(0, 0, board, board);
  ctx.strokeStyle = COLORS.border;
  ctx.lineWidth = 8;
  ctx.strokeRect(0, 0, board, board);

  for (const s of state.spots || []) {
    ctx.strokeStyle = COLORS.occStroke;
    ctx.lineWidth = 2;
    ctx.strokeRect(s.x, s.y, s.w, s.h);
  }
  if (state.target) {
    const t = state.target;
    ctx.fillStyle = "rgba(16, 185, 129, 0.18)";
    ctx.fillRect(t.x, t.y, t.w, t.h);
    ctx.strokeStyle = COLORS.target;
    ctx.lineWidth = 3;
    ctx.strokeRect(t.x, t.y, t.w, t.h);
  }

  for (const obs of state.obstacles || []) drawCar(ctx, obs);

  const lidar = state.lidar;
  if (lidar && lidar.show) {
    const [ox, oy] = lidar.origin;
    (lidar.hits || []).forEach((hit, i) => {
      const dist = lidar.ranges[i];
      const t = Math.max(0, Math.min(1, dist / lidar.max_range));
      const color = `rgb(${Math.round(220 * (1 - t))}, ${Math.round(180 * t)}, 40)`;
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(ox, oy);
      ctx.lineTo(hit[0], hit[1]);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(hit[0], hit[1], 2, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.fillStyle = COLORS.axle;
    ctx.beginPath();
    ctx.arc(ox, oy, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  if (state.car) drawCar(ctx, state.car);

  const hud = state.hud;
  if (hud) {
    ctx.fillStyle = "rgb(20, 20, 20)";
    ctx.font = "14px Consolas, monospace";
    const ctrl = hud.control ? `  ${hud.control}` : "";
    const lines = [
      `v=${pxToM(hud.v).toFixed(2).padStart(5)} m/s  phi=${hud.phi_deg.toFixed(1).padStart(5)}deg`,
      `lidar=${pxToM(hud.lidar_min).toFixed(2).padStart(5)} m  dist=${pxToM(hud.dist).toFixed(2).padStart(5)} m`,
      `mapa=${state.map_name}  parked=${hud.parked}${ctrl}`,
    ];
    lines.forEach((line, i) => ctx.fillText(line, 12, 24 + i * 16));
  }
  ctx.restore();
}

function prettyTicks(min, max, n = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || Math.abs(max - min) < 1e-9) {
    min -= 1;
    max += 1;
  }
  const span = max - min;
  const raw = span / Math.max(1, n - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const residual = raw / mag;
  let step;
  if (residual <= 1.5) step = mag;
  else if (residual <= 3) step = 2 * mag;
  else if (residual <= 7) step = 5 * mag;
  else step = 10 * mag;
  const tmin = Math.floor(min / step) * step;
  const tmax = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = tmin; v <= tmax + step * 0.25; v += step) {
    ticks.push(Number(v.toFixed(10)));
  }
  return { min: tmin, max: tmax, ticks, step };
}

function formatTick(v, step) {
  if (Math.abs(step) >= 1) return String(Math.round(v));
  const digits = Math.max(0, -Math.floor(Math.log10(Math.abs(step))) + 1);
  return v.toFixed(Math.min(3, digits));
}

function downsampleXY(values, maxN) {
  if (!values.length) return [];
  if (values.length <= maxN) return values.map((y, i) => [i + 1, y]);
  const pts = [];
  for (let i = 0; i < maxN; i++) {
    const idx = Math.round((i * (values.length - 1)) / (maxN - 1));
    pts.push([idx + 1, values[idx]]);
  }
  return pts;
}

function drawChart(canvas, values, color, title, yLabel = "Nagroda", xLabel = "Epizod") {
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const font = 'Inter, ui-sans-serif, system-ui, sans-serif';
  const bg = "#ffffff";
  const panel = "#f7f3ff";
  const grid = "#ece4f7";
  const axis = "#1a0b2e";
  const muted = "#6e5e80";

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = axis;
  ctx.font = `bold 15px ${font}`;
  ctx.textAlign = "left";
  ctx.fillText(title, 14, 22);

  const left = 58;
  const right = w - 16;
  const top = 36;
  const bottom = h - 40;
  const pw = right - left;
  const ph = bottom - top;

  ctx.fillStyle = panel;
  ctx.fillRect(left, top, pw, ph);

  if (!values || values.length < 2) {
    ctx.strokeStyle = "#bdbdbd";
    ctx.strokeRect(left + 0.5, top + 0.5, pw - 1, ph - 1);
    ctx.fillStyle = muted;
    ctx.font = `13px ${font}`;
    ctx.textAlign = "center";
    ctx.fillText("Czekam na epizody...", left + pw / 2, top + ph / 2);
    ctx.textAlign = "left";
    return;
  }

  const pts = downsampleXY(values, Math.max(2, Math.floor(pw)));
  const ys = pts.map((p) => p[1]);
  const xTicks = prettyTicks(1, values.length, 5);
  const yTicks = prettyTicks(Math.min(...ys), Math.max(...ys), 5);

  const xSpan = xTicks.max - xTicks.min || 1;
  const ySpan = yTicks.max - yTicks.min || 1;
  const xTo = (x) => left + ((x - xTicks.min) / xSpan) * pw;
  const yTo = (y) => bottom - ((y - yTicks.min) / ySpan) * ph;

  ctx.lineWidth = 1;
  yTicks.ticks.forEach((tick) => {
    const y = yTo(tick);
    ctx.strokeStyle = grid;
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
  });
  xTicks.ticks.forEach((tick) => {
    const x = xTo(tick);
    ctx.strokeStyle = grid;
    ctx.beginPath();
    ctx.moveTo(x, top);
    ctx.lineTo(x, bottom);
    ctx.stroke();
  });

  ctx.strokeStyle = axis;
  ctx.lineWidth = 1.25;
  ctx.beginPath();
  ctx.moveTo(left, top);
  ctx.lineTo(left, bottom);
  ctx.lineTo(right, bottom);
  ctx.stroke();

  ctx.fillStyle = axis;
  ctx.font = `11px ${font}`;
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";
  yTicks.ticks.forEach((tick) => {
    ctx.fillText(formatTick(tick, yTicks.step), left - 8, yTo(tick));
  });
  ctx.textAlign = "center";
  ctx.textBaseline = "top";
  xTicks.ticks.forEach((tick) => {
    if (tick < xTicks.min - 1e-9 || tick > xTicks.max + 1e-9) return;
    ctx.fillText(formatTick(tick, xTicks.step), xTo(tick), bottom + 6);
  });

  ctx.save();
  ctx.fillStyle = muted;
  ctx.font = `12px ${font}`;
  ctx.translate(16, top + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(yLabel, 0, 0);
  ctx.restore();
  ctx.fillStyle = muted;
  ctx.font = `12px ${font}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.fillText(xLabel, left + pw / 2, h - 8);

  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2.2;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  pts.forEach(([x, y], i) => {
    const px = xTo(x);
    const py = yTo(y);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.stroke();

  const [lx, ly] = pts[pts.length - 1];
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(xTo(lx), yTo(ly), 3.2, 0, Math.PI * 2);
  ctx.fill();

  ctx.textAlign = "right";
  ctx.textBaseline = "bottom";
  ctx.font = `bold 11px ${font}`;
  ctx.fillText(values[values.length - 1].toFixed(1), right - 4, top - 4);
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
}
