const views = {
  MAIN: document.getElementById("view-main"),
  MAP_LIST: document.getElementById("view-maps"),
  EDITOR: document.getElementById("view-editor"),
  TRAIN_MAPS: document.getElementById("view-train-maps"),
  TRAIN_SETUP: document.getElementById("view-train-setup"),
  TRAINING: document.getElementById("view-training"),
  SAVED: document.getElementById("view-saved"),
  PREVIEW: document.getElementById("view-preview"),
  GAME: document.getElementById("view-game"),
};

const mainStatus = document.getElementById("main-status");
const mapListEl = document.getElementById("map-list");
const previewGrid = document.getElementById("preview-grid");
const modal = document.getElementById("modal");
const modalText = document.getElementById("modal-text");
const trainStopBtn = document.getElementById("train-stop");
const trainSaveBtn = document.getElementById("train-save");
const trainMenuBtn = document.getElementById("train-menu");
const saveModal = document.getElementById("save-modal");
const trainProgress = document.getElementById("train-progress");
const trainProgressLabel = document.getElementById("train-progress-label");
const trainStats = document.getElementById("train-stats");
const trainError = document.getElementById("train-error");
const gameCanvas = document.getElementById("game-canvas");
const gameCtx = gameCanvas.getContext("2d");
const gameCaption = document.getElementById("game-caption");
const gameBanner = document.getElementById("game-banner");

const editor = new MapEditor(document.getElementById("editor-canvas"));
let pendingDelete = null;
let trainTimer = null;
let ws = null;
let currentView = "MAIN";
let mapsDraft = [];
let trainMaps = [];
let trainMapSelection = null;
let trainStopping = false;
let savedModels = [];
let activeModelId = null;
let previewOrigin = "train";

function cloneMap(item) {
  return {
    name: item.name,
    label: item.label || mapLabel(item.name),
    data: JSON.parse(JSON.stringify(item.data)),
  };
}

function defaultNewMap() {
  return {
    start_pos: [90, 300, 0],
    target_spot: { x: 400, y: 250, orientation: "vertical" },
    occupied_spots: [],
    max_v: CFG.max_v ?? 90,
    car_w: CFG.car_w ?? 24,
    car_h: CFG.car_h ?? 60,
    spot_w: CFG.spot_w ?? 44,
    spot_h: CFG.spot_h ?? 88,
    obstacle_w: CFG.spot_w ?? 44,
    obstacle_h: CFG.spot_h ?? 88,
  };
}

function paramEls() {
  return {
    vmax: document.getElementById("param-vmax"),
    vmaxVal: document.getElementById("val-vmax"),
    carW: document.getElementById("param-car-w"),
    carH: document.getElementById("param-car-h"),
    spotW: document.getElementById("param-spot-w"),
    spotH: document.getElementById("param-spot-h"),
    obstacleW: document.getElementById("param-obstacle-w"),
    obstacleH: document.getElementById("param-obstacle-h"),
  };
}

function applyDimLimits(input, key) {
  const lim = CFG.dim_limits?.[key];
  if (!lim || !input) return;
  input.min = pxToM(lim[0]).toFixed(2);
  input.max = pxToM(lim[1]).toFixed(2);
  input.step = "0.01";
}

function formatSpeed(px) {
  const ms = pxToM(px);
  const kmh = ms * 3.6;
  const fmt = (n) => n.toLocaleString("pl-PL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return `<span>${fmt(kmh)} km/h</span><span>(${fmt(ms)} m/s)</span>`;
}

function syncEditorParamLabels() {
  const el = paramEls();
  el.vmaxVal.innerHTML = formatSpeed(kmhToPx(el.vmax.value));
}

function fillEditorParams() {
  const d = editor.data || {};
  const sz = sizesOf(d);
  const el = paramEls();
  el.vmax.min = CFG.max_v_kmh_min ?? 5;
  el.vmax.max = CFG.max_v_kmh_max ?? 20;
  el.vmax.step = "0.5";
  applyDimLimits(el.carW, "car_w");
  applyDimLimits(el.carH, "car_h");
  applyDimLimits(el.spotW, "spot_w");
  applyDimLimits(el.spotH, "spot_h");
  applyDimLimits(el.obstacleW, "obstacle_w");
  applyDimLimits(el.obstacleH, "obstacle_h");
  el.vmax.value = pxToKmh(d.max_v ?? CFG.max_v ?? 90).toFixed(1);
  el.carW.value = formatM(sz.car_w);
  el.carH.value = formatM(sz.car_h);
  el.spotW.value = formatM(sz.spot_w);
  el.spotH.value = formatM(sz.spot_h);
  el.obstacleW.value = formatM(sz.obstacle_w);
  el.obstacleH.value = formatM(sz.obstacle_h);
  syncEditorParamLabels();
}

function rescaleSpotFromCenter(cfg, oldW, oldH, newW, newH) {
  const orient = cfg.orientation || "vertical";
  const [ow, oh] = spotSize(orient, oldW, oldH);
  const [nw, nh] = spotSize(orient, newW, newH);
  const cx = cfg.x + ow / 2;
  const cy = cfg.y + oh / 2;
  const [x, y] = clampSpot(snap(cx - nw / 2), snap(cy - nh / 2), orient, newW, newH);
  cfg.x = x;
  cfg.y = y;
}

function stepDim(input, key, dir) {
  const current = mToPx(input.value);
  let px = Number.isFinite(current) ? current : clampDim(key, CFG[key] ?? 0);
  const lim = CFG.dim_limits?.[key] || [px, px];
  for (let i = 0; i < 12; i += 1) {
    const next = clampDim(key, mToPx(pxToM(px) + dir * 0.05));
    if (next !== px || next === lim[0] || next === lim[1]) {
      px = next;
      break;
    }
  }
  input.value = formatM(px);
  applyEditorParams();
}

function applyEditorParams() {
  if (!editor.data) return;
  const prev = sizesOf(editor.data);
  const el = paramEls();
  editor.data.max_v = kmhToPx(el.vmax.value);
  const readDim = (input, key, prevPx) => {
    const px = mToPx(input.value);
    return Number.isFinite(px) ? clampDim(key, px) : prevPx;
  };
  editor.data.car_w = readDim(el.carW, "car_w", prev.car_w);
  editor.data.car_h = readDim(el.carH, "car_h", prev.car_h);
  editor.data.spot_w = readDim(el.spotW, "spot_w", prev.spot_w);
  editor.data.spot_h = readDim(el.spotH, "spot_h", prev.spot_h);
  editor.data.obstacle_w = readDim(el.obstacleW, "obstacle_w", prev.obstacle_w);
  editor.data.obstacle_h = readDim(el.obstacleH, "obstacle_h", prev.obstacle_h);
  const next = sizesOf(editor.data);
  if (editor.data.target_spot) {
    rescaleSpotFromCenter(
      editor.data.target_spot,
      prev.spot_w, prev.spot_h, next.spot_w, next.spot_h
    );
  }
  for (const s of editor.data.occupied_spots || []) {
    rescaleSpotFromCenter(
      s, prev.obstacle_w, prev.obstacle_h, next.obstacle_w, next.obstacle_h
    );
  }
  reclampMapGeometry(editor.data);
  editor.draw();
  syncEditorParamLabels();
}

function nextDraftName() {
  const existing = new Set(mapsDraft.map((m) => m.name));
  let i = 1;
  while (existing.has(`map_${i}`)) i += 1;
  return `map_${i}`;
}

function upsertDraft(name, data) {
  const item = {
    name,
    label: mapLabel(name),
    data: JSON.parse(JSON.stringify(data)),
  };
  const idx = mapsDraft.findIndex((m) => m.name === name);
  if (idx >= 0) mapsDraft[idx] = item;
  else mapsDraft.push(item);
}

function show(name) {
  currentView = name;
  document.body.dataset.view = name;
  Object.entries(views).forEach(([key, el]) => {
    const hide = key !== name;
    el.classList.toggle("hidden", hide);
    el.hidden = hide;
  });
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
      if (Array.isArray(detail)) {
        detail = detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
      }
    } catch (_err) {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function setToolButtons() {
  document.querySelectorAll(".btn.tool").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tool === editor.tool);
  });
}

editor.onChange = setToolButtons;

function drawThumb(canvas, data) {
  const ctx = canvas.getContext("2d");
  drawMapData(ctx, data, { width: canvas.width, height: canvas.height });
}

function renderMapList() {
  mapListEl.innerHTML = "";
  mapsDraft.forEach((item) => {
    const row = document.createElement("div");
    row.className = "map-row";
    row.onclick = () => openEditor(item.name, item.data);
    const canvas = document.createElement("canvas");
    canvas.width = 72;
    canvas.height = 72;
    drawThumb(canvas, item.data);
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = item.label;
    const actions = document.createElement("div");
    actions.className = "map-row-actions";
    const edit = document.createElement("button");
    edit.className = "btn";
    edit.textContent = "Edytuj";
    edit.onclick = (event) => {
      event.stopPropagation();
      openEditor(item.name, item.data);
    };
    const del = document.createElement("button");
    del.className = "btn danger";
    del.textContent = "Usuń";
    del.onclick = (event) => {
      event.stopPropagation();
      pendingDelete = item.name;
      modalText.textContent = `Usunąć ${item.label}?`;
      modal.classList.remove("hidden");
      modal.hidden = false;
    };
    actions.append(edit, del);
    row.append(canvas, label, actions);
    mapListEl.appendChild(row);
  });
}

async function loadMapsDraft() {
  const { maps } = await api("/api/maps");
  mapsDraft = maps.map(cloneMap);
}

async function saveMapsDraft() {
  await api("/api/maps", {
    method: "PUT",
    body: JSON.stringify({
      maps: mapsDraft.map((item) => ({ name: item.name, data: item.data })),
    }),
  });
}

function setPreviewHeading(modelName) {
  const saved = Boolean(modelName);
  document.getElementById("preview-eyebrow").textContent = saved ? "Podgląd" : "Gotowy model";
  document.getElementById("preview-title").textContent = saved ? modelName : "Podgląd agenta";
  document.getElementById("preview-hint").textContent = saved
    ? "Kliknij mapę, żeby zobaczyć jak ten model parkuje."
    : "Kliknij mapę, żeby zobaczyć jak agent parkuje.";
  document.getElementById("preview-back").textContent = saved ? "Wstecz" : "Menu";
}

async function renderPreview() {
  const { maps } = await api("/api/maps");
  previewGrid.innerHTML = "";
  maps.forEach((item) => {
    const tile = document.createElement("div");
    tile.className = "tile";
    const canvas = document.createElement("canvas");
    canvas.width = 280;
    canvas.height = 168;
    drawThumb(canvas, item.data);
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = item.label;
    tile.append(canvas, label);
    tile.onclick = () => startGame(item.name, item.label);
    previewGrid.appendChild(tile);
  });
}

function openEditor(name, data) {
  const src = data || {};
  const fromScale = (value, scale, base) =>
    value != null ? value : Math.round(base * Number(scale ?? 1));
  const next = {
    ...src,
    max_v: src.max_v ?? CFG.max_v ?? 90,
    car_w: fromScale(src.car_w, src.car_size, CFG.car_w ?? 24),
    car_h: fromScale(src.car_h, src.car_size, CFG.car_h ?? 60),
    spot_w: fromScale(src.spot_w, src.spot_size, CFG.spot_w ?? 44),
    spot_h: fromScale(src.spot_h, src.spot_size, CFG.spot_h ?? 88),
    obstacle_w: fromScale(src.obstacle_w, src.obstacle_size, CFG.spot_w ?? 44),
    obstacle_h: fromScale(src.obstacle_h, src.obstacle_size, CFG.spot_h ?? 88),
  };
  delete next.car_size;
  delete next.spot_size;
  delete next.obstacle_size;
  editor.load(name, next);
  fillEditorParams();
  document.getElementById("editor-title").textContent = `Edytor — ${mapLabel(name)}`;
  setToolButtons();
  show("EDITOR");
}

function closeWs() {
  if (ws) {
    try {
      ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
    } catch (_err) {
      /* ignore */
    }
    ws = null;
  }
}

async function startGame(mapName, label) {
  if (!activeModelId) {
    const model = await api("/api/model");
    if (!model.available) {
      mainStatus.textContent = "Brak modelu. Najpierw uruchom trening.";
      show("MAIN");
      return;
    }
  }
  closeWs();
  gameBanner.textContent = "";
  gameBanner.style.color = "";
  gameCaption.textContent = label;
  show("GAME");

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/game`);
  ws.onopen = () => ws.send(JSON.stringify({
    type: "start",
    map_name: mapName,
    model_id: activeModelId,
  }));
  ws.onmessage = (ev) => {
    const state = JSON.parse(ev.data);
    if (state.error) {
      mainStatus.textContent = state.error.includes("model")
        ? "Brak modelu. Najpierw uruchom trening."
        : `Nie wczytano agenta: ${state.error}`;
      closeWs();
      show("MAIN");
      return;
    }
    drawGame(gameCtx, state);
    if (state.done) {
      const info = state.info || {};
      if (info.success) {
        gameBanner.textContent = `Zaparkowano   R=${state.reward.toFixed(1)}`;
        gameBanner.style.color = COLORS.ok;
      } else if (info.collision) {
        gameBanner.textContent = `Kolizja   R=${state.reward.toFixed(1)}`;
        gameBanner.style.color = COLORS.danger;
      } else {
        gameBanner.textContent = `Koniec epizodu   R=${state.reward.toFixed(1)}`;
        gameBanner.style.color = COLORS.warn;
      }
    } else {
      gameBanner.textContent = "";
    }
  };
  ws.onerror = () => {
    mainStatus.textContent = "Błąd połączenia z agentem.";
    show("MAIN");
  };
}

function renderTrain(snap) {
  const step = snap.step || 0;
  const total = Math.max(1, snap.timesteps || 1);
  const frac = Math.min(1, step / total);
  trainProgress.style.width = `${frac * 100}%`;
  trainProgressLabel.textContent =
    `krok ${step} / ${total}   epizod ${snap.episode || 0}   ` +
    `t=${Math.round(snap.elapsed || 0)}s`;

  drawChart(
    document.getElementById("chart-reward"),
    snap.rewards || [],
    "#7c3aed",
    "Nagroda za epizod"
  );
  drawChart(
    document.getElementById("chart-avg"),
    snap.avg20 || [],
    "#0f766e",
    "Średnia nagród (20 epizodów)"
  );

  trainStats.innerHTML = `
    <h2>Statystyki</h2>
    <div class="stat-row"><div class="k">Sukcesy</div><div class="v ok">${snap.successes || 0}</div></div>
    <div class="stat-row"><div class="k">Seria sukcesów</div><div class="v ok">${snap.streak || 0}</div><div class="k">najlepsza: ${snap.best_streak || 0}</div></div>
    <div class="stat-row"><div class="k">Kolizje / crash</div><div class="v danger">${snap.collisions || 0}</div></div>
    <div class="stat-row"><div class="k">Timeouty</div><div class="v warn">${snap.timeouts || 0}</div></div>
    <div class="stat-row"><div class="k">Epizody</div><div class="v">${snap.episode || 0}</div></div>
  `;
  trainError.textContent = snap.error ? `Błąd: ${String(snap.error).slice(0, 80)}` : "";

  const done = Boolean(snap.done);
  const interrupted = done && Boolean(snap.stopped);
  trainSaveBtn.classList.toggle("hidden", !interrupted);
  trainSaveBtn.hidden = !interrupted;
  trainMenuBtn.classList.toggle("hidden", !interrupted);
  trainMenuBtn.hidden = !interrupted;
  trainStopBtn.classList.toggle("hidden", interrupted);
  trainStopBtn.hidden = interrupted;
  if (!interrupted) {
    trainStopBtn.textContent = done ? "Zobacz agenta" : (trainStopping ? "Przerywanie…" : "Przerwij");
    trainStopBtn.disabled = trainStopping && !done;
    trainStopBtn.classList.toggle("ok", done);
    trainStopBtn.classList.toggle("danger", !done);
  }
}

function stopTrainPoll() {
  if (trainTimer) {
    clearInterval(trainTimer);
    trainTimer = null;
  }
}

async function pollTrain() {
  const snap = await api("/api/train/status");
  renderTrain(snap);
  if (snap.done && !snap.error && !snap.stopped) {
    stopTrainPoll();
    activeModelId = null;
    previewOrigin = "train";
    setPreviewHeading(null);
    await renderPreview();
    show("PREVIEW");
  }
}

function renderTrainMapPicker() {
  const grid = document.getElementById("train-map-grid");
  if (!grid) return;
  grid.innerHTML = "";
  trainMaps.forEach((item) => {
    const selected = trainMapSelection.has(item.name);
    const tile = document.createElement("div");
    tile.className = `tile train-map${selected ? " selected" : ""}`;
    const canvas = document.createElement("canvas");
    canvas.width = 280;
    canvas.height = 168;
    drawThumb(canvas, item.data);
    const label = document.createElement("div");
    label.className = "label";
    label.textContent = item.label;
    const check = document.createElement("span");
    check.className = "check";
    check.textContent = "✓";
    tile.append(canvas, label, check);
    tile.onclick = () => {
      if (trainMapSelection.has(item.name)) trainMapSelection.delete(item.name);
      else trainMapSelection.add(item.name);
      renderTrainMapPicker();
    };
    grid.appendChild(tile);
  });
}

async function startTraining() {
  const setupStatus = document.getElementById("train-setup-status");
  const timesteps = clampTrainSteps(Number(document.getElementById("train-steps-input").value));
  const maps = [...trainMapSelection];
  if (!maps.length) {
    if (setupStatus) setupStatus.textContent = "Wybierz przynajmniej jedną mapę.";
    return;
  }
  setTrainSteps(timesteps);
  try {
    await api("/api/train/start", {
      method: "POST",
      body: JSON.stringify({ timesteps, maps }),
    });
    if (setupStatus) setupStatus.textContent = "";
    mainStatus.textContent = "";
    trainStopping = false;
    show("TRAINING");
    renderTrain(await api("/api/train/status"));
    stopTrainPoll();
    trainTimer = setInterval(pollTrain, 500);
  } catch (err) {
    if (setupStatus) setupStatus.textContent = err.message;
  }
}

function trainStepsBounds() {
  return {
    min: CFG.train_steps_min ?? 1000,
    max: CFG.train_steps_max ?? 1_000_000,
    fallback: CFG.train_steps_default ?? 350_000,
  };
}

function clampTrainSteps(value) {
  const { min, max, fallback } = trainStepsBounds();
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.round(Math.max(min, Math.min(max, n)));
}

function setTrainSteps(value) {
  const steps = clampTrainSteps(value);
  const slider = document.getElementById("train-steps-slider");
  const input = document.getElementById("train-steps-input");
  slider.value = String(steps);
  input.value = String(steps);
}

async function openTrainSetup() {
  mainStatus.textContent = "";
  const { maps } = await api("/api/maps");
  trainMaps = maps;
  const names = new Set(maps.map((item) => item.name));
  if (!trainMapSelection) {
    trainMapSelection = new Set(names);
  } else {
    trainMapSelection = new Set([...trainMapSelection].filter((name) => names.has(name)));
    if (!trainMapSelection.size) trainMapSelection = new Set(names);
  }
  renderTrainMapPicker();
  document.getElementById("train-maps-status").textContent = "";
  show("TRAIN_MAPS");
}

function openTrainSteps() {
  const status = document.getElementById("train-maps-status");
  if (!trainMapSelection.size) {
    status.textContent = "Wybierz przynajmniej jedną mapę.";
    return;
  }
  status.textContent = "";
  const { min, max, fallback } = trainStepsBounds();
  const slider = document.getElementById("train-steps-slider");
  const input = document.getElementById("train-steps-input");
  slider.min = String(min);
  slider.max = String(max);
  input.min = String(min);
  input.max = String(max);
  document.getElementById("train-steps-min-label").textContent = min.toLocaleString("pl-PL");
  document.getElementById("train-steps-max-label").textContent = max.toLocaleString("pl-PL");
  setTrainSteps(input.value || fallback);
  document.getElementById("train-setup-status").textContent = "";
  show("TRAIN_SETUP");
}

function leavePreview() {
  closeWs();
  if (previewOrigin === "saved") show("SAVED");
  else show("MAIN");
}

function formatSavedWhen(iso) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("pl-PL", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderSavedList() {
  const list = document.getElementById("saved-list");
  const status = document.getElementById("saved-status");
  list.innerHTML = "";
  if (!savedModels.length) {
    status.textContent = "Brak zapisanych modeli. Przerwij trening i zapisz model.";
    return;
  }
  status.textContent = "";
  savedModels.forEach((item) => {
    const row = document.createElement("div");
    row.className = "model-row";
    const label = document.createElement("div");
    label.className = "label";
    const meta = document.createElement("div");
    meta.className = "meta";
    const when = formatSavedWhen(item.created);
    const steps = Number(item.step || 0).toLocaleString("pl-PL");
    meta.textContent = when ? `${when} · krok ${steps}` : `krok ${steps}`;
    label.append(document.createTextNode(item.name), meta);
    const open = document.createElement("button");
    open.className = "btn ok";
    open.textContent = "Podgląd";
    open.onclick = () => openSavedPreview(item);
    const del = document.createElement("button");
    del.className = "btn danger";
    del.textContent = "Usuń";
    del.onclick = async () => {
      try {
        await api(`/api/models/${item.id}`, { method: "DELETE" });
        savedModels = savedModels.filter((model) => model.id !== item.id);
        renderSavedList();
      } catch (err) {
        status.textContent = err.message;
      }
    };
    row.append(label, open, del);
    list.appendChild(row);
  });
}

async function openSavedModels() {
  mainStatus.textContent = "";
  const data = await api("/api/models");
  savedModels = data.models || [];
  renderSavedList();
  show("SAVED");
}

async function openSavedPreview(model) {
  activeModelId = model.id;
  previewOrigin = "saved";
  setPreviewHeading(model.name);
  await renderPreview();
  show("PREVIEW");
}

function openSaveModal() {
  const input = document.getElementById("save-model-name");
  const status = document.getElementById("save-model-status");
  input.value = "";
  status.textContent = "";
  saveModal.classList.remove("hidden");
  saveModal.hidden = false;
  input.focus();
}

function closeSaveModal() {
  saveModal.classList.add("hidden");
  saveModal.hidden = true;
}

document.getElementById("game-back").onclick = () => {
  closeWs();
  renderPreview().then(() => show("PREVIEW"));
};
document.getElementById("btn-maps").onclick = async () => {
  mainStatus.textContent = "";
  await loadMapsDraft();
  renderMapList();
  show("MAP_LIST");
};
document.getElementById("btn-train").onclick = openTrainSetup;
document.getElementById("btn-saved-models").onclick = openSavedModels;
document.getElementById("saved-back").onclick = () => show("MAIN");
document.getElementById("train-maps-back").onclick = () => show("MAIN");
document.getElementById("train-maps-confirm").onclick = openTrainSteps;
document.getElementById("train-setup-back").onclick = () => show("TRAIN_MAPS");
document.getElementById("train-setup-start").onclick = startTraining;
document.getElementById("train-steps-slider").addEventListener("input", (e) => {
  setTrainSteps(e.target.value);
});
document.getElementById("train-steps-input").addEventListener("input", (e) => {
  const raw = e.target.value;
  if (raw === "" || raw === "-") return;
  const slider = document.getElementById("train-steps-slider");
  const n = Number(raw);
  if (Number.isFinite(n)) slider.value = String(clampTrainSteps(n));
});
document.getElementById("train-steps-input").addEventListener("change", (e) => {
  setTrainSteps(e.target.value);
});
document.getElementById("maps-back").onclick = () => {
  mapsDraft = [];
  show("MAIN");
};
document.getElementById("maps-save").onclick = async () => {
  const mapsStatus = document.getElementById("maps-status");
  mapsStatus.textContent = "";
  try {
    await saveMapsDraft();
    mapsDraft = [];
    show("MAIN");
  } catch (err) {
    mapsStatus.textContent = err.message;
  }
};
document.getElementById("maps-new").onclick = () => {
  const name = nextDraftName();
  openEditor(name, defaultNewMap());
};
document.getElementById("preview-back").onclick = leavePreview;
document.getElementById("editor-save").onclick = () => {
  upsertDraft(editor.name, editor.data);
  renderMapList();
  show("MAP_LIST");
};
document.getElementById("editor-cancel").onclick = () => {
  renderMapList();
  show("MAP_LIST");
};
function ensureDimensionFields() {
  if (document.getElementById("param-car-w")) return;
  const box = document.querySelector("#view-editor .editor-params");
  if (!box) return;
  ["param-car", "param-spot", "param-obstacle"].forEach((id) => {
    document.getElementById(id)?.closest("label")?.remove();
  });
  box.insertAdjacentHTML(
    "beforeend",
    `<div class="param">
      <span class="param-head"><span>Auto</span></span>
      <div class="dim-row">
        <label>Szerokość <input type="text" inputmode="decimal" id="param-car-w" value="1,36" /><span class="unit">m</span></label>
        <label>Długość <input type="text" inputmode="decimal" id="param-car-h" value="3,41" /><span class="unit">m</span></label>
      </div>
    </div>
    <div class="param">
      <span class="param-head"><span>Docelowe miejsce parkingowe</span></span>
      <div class="dim-row">
        <label>Szerokość <input type="text" inputmode="decimal" id="param-spot-w" value="2,50" /><span class="unit">m</span></label>
        <label>Długość <input type="text" inputmode="decimal" id="param-spot-h" value="5,00" /><span class="unit">m</span></label>
      </div>
    </div>
    <div class="param">
      <span class="param-head"><span>Zajęte miejsca</span></span>
      <div class="dim-row">
        <label>Szerokość <input type="text" inputmode="decimal" id="param-obstacle-w" value="2,50" /><span class="unit">m</span></label>
        <label>Długość <input type="text" inputmode="decimal" id="param-obstacle-h" value="5,00" /><span class="unit">m</span></label>
      </div>
    </div>`
  );
}

ensureDimensionFields();
[
  "param-vmax",
  "param-car-w",
  "param-car-h",
  "param-spot-w",
  "param-spot-h",
  "param-obstacle-w",
  "param-obstacle-h",
].forEach((id) => {
  const input = document.getElementById(id);
  if (!input) return;
  input.addEventListener("input", () => {
    if (id !== "param-vmax" && !/^\d*(,\d*)?$/.test(input.value)) return;
    applyEditorParams();
  });
  if (id === "param-vmax") return;
  input.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const key = {
      "param-car-w": "car_w",
      "param-car-h": "car_h",
      "param-spot-w": "spot_w",
      "param-spot-h": "spot_h",
      "param-obstacle-w": "obstacle_w",
      "param-obstacle-h": "obstacle_h",
    }[id];
    stepDim(input, key, e.key === "ArrowUp" ? 1 : -1);
  });
  input.addEventListener("change", () => {
    const key = {
      "param-car-w": "car_w",
      "param-car-h": "car_h",
      "param-spot-w": "spot_w",
      "param-spot-h": "spot_h",
      "param-obstacle-w": "obstacle_w",
      "param-obstacle-h": "obstacle_h",
    }[id];
    const px = mToPx(input.value);
    if (Number.isFinite(px)) input.value = formatM(clampDim(key, px));
  });
});
document.querySelector("#view-editor .editor-params")?.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-step]");
  if (!btn) return;
  const input = document.getElementById(btn.dataset.for);
  if (!input) return;
  stepDim(input, btn.dataset.key, Number(btn.dataset.step));
});
document.getElementById("editor-rotate").onclick = () => editor.rotateSelected();
document.getElementById("editor-delete").onclick = () => editor.deleteSelected();
document.querySelectorAll(".btn.tool").forEach((btn) => {
  btn.onclick = () => {
    editor.setTool(btn.dataset.tool);
    setToolButtons();
  };
});
document.getElementById("modal-no").onclick = () => {
  pendingDelete = null;
  modal.classList.add("hidden");
  modal.hidden = true;
};
document.getElementById("modal-yes").onclick = () => {
  if (pendingDelete) {
    mapsDraft = mapsDraft.filter((m) => m.name !== pendingDelete);
    pendingDelete = null;
    modal.classList.add("hidden");
    modal.hidden = true;
    renderMapList();
  }
};
document.getElementById("train-stop").onclick = async () => {
  const snap = await api("/api/train/status");
  if (snap.done) {
    stopTrainPoll();
    activeModelId = null;
    previewOrigin = "train";
    setPreviewHeading(null);
    await renderPreview();
    show("PREVIEW");
  } else {
    trainStopping = true;
    trainStopBtn.textContent = "Przerywanie…";
    trainStopBtn.disabled = true;
    await api("/api/train/stop", { method: "POST" });
  }
};
trainSaveBtn.onclick = openSaveModal;
trainMenuBtn.onclick = () => {
  stopTrainPoll();
  trainStopping = false;
  show("MAIN");
};
document.getElementById("save-model-no").onclick = closeSaveModal;
document.getElementById("save-model-yes").onclick = async () => {
  const input = document.getElementById("save-model-name");
  const status = document.getElementById("save-model-status");
  status.textContent = "";
  try {
    const saved = await api("/api/models", {
      method: "POST",
      body: JSON.stringify({ name: input.value }),
    });
    closeSaveModal();
    stopTrainPoll();
    trainStopping = false;
    mainStatus.textContent = `Zapisano model „${saved.name}”.`;
    show("MAIN");
  } catch (err) {
    status.textContent = err.message;
  }
};
document.getElementById("save-model-name").addEventListener("keydown", (e) => {
  if (e.key === "Enter") document.getElementById("save-model-yes").click();
});

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!saveModal.classList.contains("hidden")) {
      closeSaveModal();
      return;
    }
    if (!modal.classList.contains("hidden")) {
      pendingDelete = null;
      modal.classList.add("hidden");
      modal.hidden = true;
      return;
    }
    if (currentView === "MAP_LIST") {
      mapsDraft = [];
      show("MAIN");
    } else if (currentView === "TRAIN_MAPS") {
      show("MAIN");
    } else if (currentView === "TRAIN_SETUP") {
      show("TRAIN_MAPS");
    } else if (currentView === "EDITOR") {
      renderMapList();
      show("MAP_LIST");
    } else if (currentView === "SAVED") {
      show("MAIN");
    } else if (currentView === "TRAINING") {
      api("/api/train/status").then(async (snap) => {
        if (snap.done && snap.stopped) {
          stopTrainPoll();
          show("MAIN");
          return;
        }
        if (!snap.done) {
          trainStopping = true;
          trainStopBtn.textContent = "Przerywanie…";
          trainStopBtn.disabled = true;
          await api("/api/train/stop", { method: "POST" });
        } else {
          stopTrainPoll();
          activeModelId = null;
          previewOrigin = "train";
          setPreviewHeading(null);
          await renderPreview();
          show("PREVIEW");
        }
      });
    } else if (currentView === "PREVIEW") leavePreview();
    else if (currentView === "GAME") {
      closeWs();
      renderPreview().then(() => show("PREVIEW"));
    }
  }
  const typing = e.target && (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable);
  if (currentView === "EDITOR" && !typing) {
    if (e.key === "r" || e.key === "R") editor.rotateSelected();
    if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      editor.deleteSelected();
    }
  }
  if (currentView === "GAME" && ws && ws.readyState === WebSocket.OPEN) {
    if (e.key === "m" || e.key === "M") {
      closeWs();
      renderPreview().then(() => show("PREVIEW"));
    } else if (e.key === "r" || e.key === "R") {
      ws.send(JSON.stringify({ type: "reset" }));
    } else if (e.key === "l" || e.key === "L") {
      ws.send(JSON.stringify({ type: "toggle_lidar" }));
    }
  }
});

async function boot() {
  try {
    setConfig(await api("/api/config"));
  } catch (_err) {
    mainStatus.textContent = "Nie udało się wczytać konfiguracji.";
  }
}

boot();
