const views = {
  MAIN: document.getElementById("view-main"),
  MAP_LIST: document.getElementById("view-maps"),
  EDITOR: document.getElementById("view-editor"),
  TRAIN_SETUP: document.getElementById("view-train-setup"),
  TRAINING: document.getElementById("view-training"),
  PREVIEW: document.getElementById("view-preview"),
  GAME: document.getElementById("view-game"),
};

const mainStatus = document.getElementById("main-status");
const mapListEl = document.getElementById("map-list");
const previewGrid = document.getElementById("preview-grid");
const modal = document.getElementById("modal");
const modalText = document.getElementById("modal-text");
const trainStopBtn = document.getElementById("train-stop");
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
    car_size: 1,
    spot_size: 1,
    obstacle_size: 1,
  };
}

function paramEls() {
  return {
    vmax: document.getElementById("param-vmax"),
    car: document.getElementById("param-car"),
    spot: document.getElementById("param-spot"),
    obstacle: document.getElementById("param-obstacle"),
    vmaxVal: document.getElementById("val-vmax"),
    carVal: document.getElementById("val-car"),
    spotVal: document.getElementById("val-spot"),
    obstacleVal: document.getElementById("val-obstacle"),
  };
}

function syncEditorParamLabels() {
  const el = paramEls();
  el.vmaxVal.textContent = String(el.vmax.value);
  el.carVal.textContent = `${el.car.value}%`;
  el.spotVal.textContent = `${el.spot.value}%`;
  el.obstacleVal.textContent = `${el.obstacle.value}%`;
}

function fillEditorParams() {
  const d = editor.data || {};
  const el = paramEls();
  el.vmax.min = CFG.max_v_min ?? 40;
  el.vmax.max = CFG.max_v_max ?? 140;
  const pctMin = Math.round((CFG.size_min ?? 0.7) * 100);
  const pctMax = Math.round((CFG.size_max ?? 1.4) * 100);
  [el.car, el.spot, el.obstacle].forEach((slider) => {
    slider.min = pctMin;
    slider.max = pctMax;
  });
  el.vmax.value = Math.round(d.max_v ?? CFG.max_v ?? 90);
  el.car.value = Math.round((d.car_size ?? 1) * 100);
  el.spot.value = Math.round((d.spot_size ?? 1) * 100);
  el.obstacle.value = Math.round((d.obstacle_size ?? 1) * 100);
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

function applyEditorParams() {
  if (!editor.data) return;
  const prev = sizesOf(editor.data);
  const el = paramEls();
  editor.data.max_v = Number(el.vmax.value);
  editor.data.car_size = Number(el.car.value) / 100;
  editor.data.spot_size = Number(el.spot.value) / 100;
  editor.data.obstacle_size = Number(el.obstacle.value) / 100;
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
    edit.onclick = () => openEditor(item.name, item.data);
    const del = document.createElement("button");
    del.className = "btn danger";
    del.textContent = "Usuń";
    del.onclick = () => {
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
  const next = {
    max_v: CFG.max_v ?? 90,
    car_size: 1,
    spot_size: 1,
    obstacle_size: 1,
    ...data,
  };
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
  const model = await api("/api/model");
  if (!model.available) {
    mainStatus.textContent = "Brak modelu. Najpierw uruchom trening.";
    show("MAIN");
    return;
  }
  closeWs();
  gameBanner.textContent = "";
  gameBanner.style.color = "";
  gameCaption.textContent = label;
  show("GAME");

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/game`);
  ws.onopen = () => ws.send(JSON.stringify({ type: "start", map_name: mapName }));
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
  trainStopBtn.textContent = done ? "Zobacz agenta" : "Przerwij";
  trainStopBtn.classList.toggle("ok", done);
  trainStopBtn.classList.toggle("danger", !done);
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
  if (snap.done && !snap.error) {
    stopTrainPoll();
    await renderPreview();
    show("PREVIEW");
  }
}

async function startTraining() {
  const setupStatus = document.getElementById("train-setup-status");
  const timesteps = clampTrainSteps(Number(document.getElementById("train-steps-input").value));
  setTrainSteps(timesteps);
  try {
    await api("/api/train/start", {
      method: "POST",
      body: JSON.stringify({ timesteps }),
    });
    if (setupStatus) setupStatus.textContent = "";
    mainStatus.textContent = "";
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

function openTrainSetup() {
  mainStatus.textContent = "";
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
document.getElementById("train-setup-back").onclick = () => show("MAIN");
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
document.getElementById("preview-back").onclick = () => {
  closeWs();
  show("MAIN");
};
document.getElementById("editor-save").onclick = () => {
  upsertDraft(editor.name, editor.data);
  renderMapList();
  show("MAP_LIST");
};
document.getElementById("editor-cancel").onclick = () => {
  renderMapList();
  show("MAP_LIST");
};
["param-vmax", "param-car", "param-spot", "param-obstacle"].forEach((id) => {
  document.getElementById(id).addEventListener("input", applyEditorParams);
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
    await renderPreview();
    show("PREVIEW");
  } else {
    await api("/api/train/stop", { method: "POST" });
  }
};

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!modal.classList.contains("hidden")) {
      pendingDelete = null;
      modal.classList.add("hidden");
      modal.hidden = true;
      return;
    }
    if (currentView === "MAP_LIST") {
      mapsDraft = [];
      show("MAIN");
    } else if (currentView === "TRAIN_SETUP") {
      show("MAIN");
    } else if (currentView === "EDITOR") {
      renderMapList();
      show("MAP_LIST");
    } else if (currentView === "TRAINING") {
      api("/api/train/status").then(async (snap) => {
        if (!snap.done) await api("/api/train/stop", { method: "POST" });
        else {
          stopTrainPoll();
          await renderPreview();
          show("PREVIEW");
        }
      });
    } else if (currentView === "PREVIEW") show("MAIN");
    else if (currentView === "GAME") {
      closeWs();
      renderPreview().then(() => show("PREVIEW"));
    }
  }
  if (currentView === "EDITOR") {
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
