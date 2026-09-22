function rotateSpot(cfg, baseW, baseH) {
  const old = cfg.orientation || "vertical";
  const neu = old === "vertical" ? "horizontal" : "vertical";
  const [ow, oh] = spotSize(old, baseW, baseH);
  const [nw, nh] = spotSize(neu, baseW, baseH);
  const cx = cfg.x + ow / 2;
  const cy = cfg.y + oh / 2;
  cfg.orientation = neu;
  const [x, y] = clampSpot(snap(cx - nw / 2), snap(cy - nh / 2), neu, baseW, baseH);
  cfg.x = x;
  cfg.y = y;
}

function hitEditor(data, lx, ly) {
  const sz = sizesOf(data);
  const occ = data.occupied_spots || [];
  for (let i = occ.length - 1; i >= 0; i--) {
    const s = occ[i];
    const [w, h] = spotSize(s.orientation || "vertical", sz.obstacle_w, sz.obstacle_h);
    if (lx >= s.x && lx <= s.x + w && ly >= s.y && ly <= s.y + h) {
      return ["occ", i];
    }
  }
  const t = data.target_spot;
  const [tw, th] = spotSize(t.orientation || "vertical", sz.spot_w, sz.spot_h);
  if (lx >= t.x && lx <= t.x + tw && ly >= t.y && ly <= t.y + th) {
    return ["target"];
  }
  const [sx, sy, ang] = data.start_pos;
  const pts = startCorners(sx, sy, ang, sz.car_w, sz.car_h, sz.rear);
  if (Math.hypot(lx - sx, ly - sy) <= 18 || pointInPoly(lx, ly, pts)) {
    return ["start"];
  }
  return null;
}

class MapEditor {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.name = null;
    this.data = null;
    this.tool = "occupied";
    this.selected = ["start"];
    this.drag = false;
    this.dragOff = [0, 0];
    this.onChange = () => {};

    canvas.addEventListener("mousedown", (e) => this.onDown(e));
    window.addEventListener("mouseup", (e) => this.onUp(e));
    canvas.addEventListener("mousemove", (e) => this.onMove(e));
    canvas.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  local(e) {
    const rect = this.canvas.getBoundingClientRect();
    const scaleX = this.canvas.width / rect.width;
    const scaleY = this.canvas.height / rect.height;
    return [
      clamp((e.clientX - rect.left) * scaleX, 0, CFG.board),
      clamp((e.clientY - rect.top) * scaleY, 0, CFG.board),
    ];
  }

  load(name, data) {
    this.name = name;
    this.data = JSON.parse(JSON.stringify(data));
    this.tool = "occupied";
    this.selected = ["start"];
    this.drag = false;
    this.draw();
  }

  setTool(tool) {
    this.tool = tool;
    this.draw();
    this.onChange();
  }

  rotateSelected() {
    if (!this.selected) return;
    const sz = sizesOf(this.data);
    if (this.selected[0] === "start") {
      const [x, y, th] = this.data.start_pos;
      const neu = Math.atan2(Math.sin(th + Math.PI / 2), Math.cos(th + Math.PI / 2));
      this.data.start_pos = [x, y, neu];
    } else if (this.selected[0] === "target") {
      rotateSpot(this.data.target_spot, sz.spot_w, sz.spot_h);
    } else if (this.selected[0] === "occ") {
      rotateSpot(this.data.occupied_spots[this.selected[1]], sz.obstacle_w, sz.obstacle_h);
    }
    this.draw();
  }

  deleteSelected() {
    if (this.selected && this.selected[0] === "occ") {
      this.data.occupied_spots.splice(this.selected[1], 1);
      this.selected = null;
      this.draw();
    }
  }

  onDown(e) {
    const [lx, ly] = this.local(e);
    const hit = hitEditor(this.data, lx, ly);
    if (e.button === 2) {
      if (hit && hit[0] === "occ") {
        this.data.occupied_spots.splice(hit[1], 1);
        this.selected = null;
        this.draw();
      }
      return;
    }
    if (e.button !== 0) return;
    if (hit) {
      this.selected = hit;
      this.drag = true;
      if (hit[0] === "start") {
        const [sx, sy] = this.data.start_pos;
        this.dragOff = [sx - lx, sy - ly];
      } else if (hit[0] === "target") {
        this.dragOff = [this.data.target_spot.x - lx, this.data.target_spot.y - ly];
      } else {
        const s = this.data.occupied_spots[hit[1]];
        this.dragOff = [s.x - lx, s.y - ly];
      }
    } else if (this.tool === "start") {
      const th = this.data.start_pos[2];
      this.data.start_pos = [
        snap(clamp(lx, 20, CFG.board - 20)),
        snap(clamp(ly, 20, CFG.board - 20)),
        th,
      ];
      this.selected = ["start"];
    } else if (this.tool === "target") {
      const sz = sizesOf(this.data);
      const orient = this.data.target_spot.orientation || "vertical";
      const [w, h] = spotSize(orient, sz.spot_w, sz.spot_h);
      const [x, y] = clampSpot(snap(lx - w / 2), snap(ly - h / 2), orient, sz.spot_w, sz.spot_h);
      this.data.target_spot.x = x;
      this.data.target_spot.y = y;
      this.selected = ["target"];
    } else {
      const sz = sizesOf(this.data);
      let orient = "vertical";
      if (this.selected && this.selected[0] === "occ") {
        orient = this.data.occupied_spots[this.selected[1]].orientation || "vertical";
      }
      const [w, h] = spotSize(orient, sz.obstacle_w, sz.obstacle_h);
      const [x, y] = clampSpot(snap(lx - w / 2), snap(ly - h / 2), orient, sz.obstacle_w, sz.obstacle_h);
      this.data.occupied_spots.push({ x, y, orientation: orient });
      this.selected = ["occ", this.data.occupied_spots.length - 1];
    }
    this.draw();
    this.onChange();
  }

  onUp(e) {
    if (e.button === 0) this.drag = false;
  }

  onMove(e) {
    if (!this.drag || !this.selected) return;
    const [lx, ly] = this.local(e);
    if (this.selected[0] === "start") {
      const th = this.data.start_pos[2];
      this.data.start_pos = [
        snap(clamp(lx + this.dragOff[0], 20, CFG.board - 20)),
        snap(clamp(ly + this.dragOff[1], 20, CFG.board - 20)),
        th,
      ];
    } else if (this.selected[0] === "target") {
      const sz = sizesOf(this.data);
      const orient = this.data.target_spot.orientation || "vertical";
      const [x, y] = clampSpot(
        snap(lx + this.dragOff[0]),
        snap(ly + this.dragOff[1]),
        orient,
        sz.spot_w,
        sz.spot_h
      );
      this.data.target_spot.x = x;
      this.data.target_spot.y = y;
    } else {
      const sz = sizesOf(this.data);
      const s = this.data.occupied_spots[this.selected[1]];
      const orient = s.orientation || "vertical";
      const [x, y] = clampSpot(
        snap(lx + this.dragOff[0]),
        snap(ly + this.dragOff[1]),
        orient,
        sz.obstacle_w,
        sz.obstacle_h
      );
      s.x = x;
      s.y = y;
    }
    this.draw();
  }

  draw() {
    if (!this.data) return;
    drawMapData(this.ctx, this.data, { selected: this.selected, showGrid: true });
  }
}
