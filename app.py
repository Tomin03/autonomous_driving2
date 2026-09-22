"""Aplikacja webowa: FastAPI + frontend JS (zamiast pygame)."""

import argparse
import asyncio
import os
import threading
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from maps import (
    CAR_H,
    CAR_W,
    DEFAULT_MAX_V,
    MAX_V_MAX,
    MAX_V_MIN,
    REAR,
    SIZE_MAX,
    SIZE_MIN,
    SPOT_H,
    SPOT_W,
    default_new_map,
    delete_map,
    get_map,
    list_map_names,
    map_dims,
    next_map_name,
    replace_all_maps,
    save_map,
)
from steering_logic import (
    AGENT_MODEL_PATHS,
    SteeringParkingEnv,
    _agent_action,
    _load_policy_actor,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
BOARD = 600
SNAP = 10
TRAIN_STEPS_MIN = 1_000
TRAIN_STEPS_MAX = 1_000_000
TRAIN_STEPS_DEFAULT = 350_000


class TrainMonitor:
    def __init__(self):
        self.lock = threading.Lock()
        self.rewards = []
        self.avg20 = []
        self.successes = 0
        self.collisions = 0
        self.timeouts = 0
        self.streak = 0
        self.best_streak = 0
        self.episode = 0
        self.step = 0
        self.timesteps = 1
        self.eval_stats = None
        self.done = False
        self.stopped = False
        self.error = None
        self.elapsed = 0.0

    def on_progress(self, payload):
        with self.lock:
            if payload.get("error"):
                self.error = payload["error"]
            if "ep_reward" in payload:
                self.rewards.append(float(payload["ep_reward"]))
                self.avg20.append(float(payload.get("avg20", 0.0)))
            self.successes = int(payload.get("successes", self.successes))
            self.collisions = int(payload.get("collisions", self.collisions))
            self.timeouts = int(payload.get("timeouts", self.timeouts))
            self.streak = int(payload.get("streak", self.streak))
            self.best_streak = int(payload.get("best_streak", self.best_streak))
            self.episode = int(payload.get("episode", self.episode))
            self.step = int(payload.get("step", self.step))
            self.timesteps = int(payload.get("timesteps", self.timesteps))
            self.elapsed = float(payload.get("elapsed", self.elapsed))
            if payload.get("eval"):
                self.eval_stats = payload["eval"]
            self.done = bool(payload.get("done", False))
            self.stopped = bool(payload.get("stopped", False))

    def snapshot(self):
        with self.lock:
            return {
                "rewards": list(self.rewards),
                "avg20": list(self.avg20),
                "successes": self.successes,
                "collisions": self.collisions,
                "timeouts": self.timeouts,
                "streak": self.streak,
                "best_streak": self.best_streak,
                "episode": self.episode,
                "step": self.step,
                "timesteps": self.timesteps,
                "eval": self.eval_stats,
                "done": self.done,
                "stopped": self.stopped,
                "error": self.error,
                "elapsed": self.elapsed,
                "running": not self.done,
            }


class AppRuntime:
    def __init__(self):
        self.train_monitor: Optional[TrainMonitor] = None
        self.train_thread: Optional[threading.Thread] = None
        self.train_stop: Optional[threading.Event] = None
        self.actor = None
        self.device = None
        self.actor_lock = threading.Lock()

    def invalidate_actor(self):
        with self.actor_lock:
            self.actor = None
            self.device = None


runtime = AppRuntime()


def map_label(name: str) -> str:
    if name.startswith("map_") and name[4:].isdigit():
        return f"Mapa {name[4:]}"
    return name


def map_to_json(data: dict) -> dict:
    start = data["start_pos"]
    dims = map_dims(data)
    return {
        "start_pos": [float(start[0]), float(start[1]), float(start[2])],
        "target_spot": dict(data["target_spot"]),
        "occupied_spots": [dict(s) for s in data.get("occupied_spots", [])],
        "max_v": dims["max_v"],
        "car_size": dims["car_size"],
        "spot_size": dims["spot_size"],
        "obstacle_size": dims["obstacle_size"],
    }


def model_path() -> Optional[str]:
    return next((p for p in AGENT_MODEL_PATHS["sac"] if os.path.isfile(p)), None)


def load_actor(env: SteeringParkingEnv):
    import torch

    with runtime.actor_lock:
        if runtime.actor is not None:
            return runtime.actor, runtime.device
        path = model_path()
        if path is None:
            raise FileNotFoundError("Brak modelu. Najpierw uruchom trening.")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        actor, _, _ = _load_policy_actor(
            path, env.obs_dim, env.act_dim, device, algo_hint="sac"
        )
        runtime.actor = actor
        runtime.device = device
        return actor, device


def step_agent(env: SteeringParkingEnv, actor, device):
    obs = env._get_obs()
    raw = _agent_action(actor, obs, device)
    v_cmd, delta_cmd = env.unscale_action(raw)
    _, reward, done, info = env.step([v_cmd, delta_cmd], dt=0.05)
    return env.get_render_state(reward=reward, done=done, info=info)


class MapPayload(BaseModel):
    start_pos: list[float]
    target_spot: dict[str, Any]
    occupied_spots: list[dict[str, Any]] = []
    max_v: float = DEFAULT_MAX_V
    car_size: float = 1.0
    spot_size: float = 1.0
    obstacle_size: float = 1.0


class MapItem(BaseModel):
    name: str
    data: MapPayload


class MapsBulkPayload(BaseModel):
    maps: list[MapItem]


class TrainStartPayload(BaseModel):
    timesteps: int = TRAIN_STEPS_DEFAULT


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if runtime.train_stop is not None:
        runtime.train_stop.set()


app = FastAPI(title="Autonomous Parking", lifespan=lifespan)


@app.get("/api/config")
def api_config():
    return {
        "board": BOARD,
        "snap": SNAP,
        "spot_w": SPOT_W,
        "spot_h": SPOT_H,
        "car_w": CAR_W,
        "car_h": CAR_H,
        "rear": REAR,
        "max_v": DEFAULT_MAX_V,
        "max_v_min": MAX_V_MIN,
        "max_v_max": MAX_V_MAX,
        "size_min": SIZE_MIN,
        "size_max": SIZE_MAX,
        "train_steps_min": TRAIN_STEPS_MIN,
        "train_steps_max": TRAIN_STEPS_MAX,
        "train_steps_default": TRAIN_STEPS_DEFAULT,
    }


@app.get("/api/maps")
def api_list_maps():
    names = list_map_names()
    return {
        "maps": [
            {
                "name": name,
                "label": map_label(name),
                "data": map_to_json(get_map(name)),
            }
            for name in names
        ]
    }


@app.put("/api/maps")
def api_replace_maps(payload: MapsBulkPayload):
    maps_by_name = {item.name: item.data.model_dump() for item in payload.maps}
    names = replace_all_maps(maps_by_name)
    return {
        "maps": [
            {
                "name": name,
                "label": map_label(name),
                "data": map_to_json(get_map(name)),
            }
            for name in names
        ]
    }


@app.get("/api/maps/{name}")
def api_get_map(name: str):
    try:
        data = get_map(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"name": name, "label": map_label(name), "data": map_to_json(data)}


@app.post("/api/maps")
def api_create_map():
    name = next_map_name()
    data = default_new_map()
    return {"name": name, "label": map_label(name), "data": map_to_json(data)}


@app.put("/api/maps/{name}")
def api_save_map(name: str, payload: MapPayload):
    save_map(name, payload.model_dump())
    return {"name": name, "label": map_label(name), "data": map_to_json(get_map(name))}


@app.delete("/api/maps/{name}")
def api_delete_map(name: str):
    if not delete_map(name):
        raise HTTPException(status_code=404, detail=f"Nieznana mapa: {name}")
    return {"ok": True}


@app.get("/api/model")
def api_model():
    path = model_path()
    return {"available": path is not None, "path": path}


@app.get("/api/train/status")
def api_train_status():
    if runtime.train_monitor is None:
        return {
            "running": False,
            "done": False,
            "rewards": [],
            "avg20": [],
            "successes": 0,
            "collisions": 0,
            "timeouts": 0,
            "streak": 0,
            "best_streak": 0,
            "episode": 0,
            "step": 0,
            "timesteps": 1,
            "eval": None,
            "stopped": False,
            "error": None,
            "elapsed": 0.0,
        }
    return runtime.train_monitor.snapshot()


@app.post("/api/train/start")
def api_train_start(payload: TrainStartPayload):
    names = list_map_names()
    if not names:
        raise HTTPException(status_code=400, detail="Najpierw dodaj przynajmniej jedną mapę.")
    if runtime.train_thread is not None and runtime.train_thread.is_alive():
        raise HTTPException(status_code=409, detail="Trening już trwa.")

    from train_sac import train

    timesteps = max(TRAIN_STEPS_MIN, min(TRAIN_STEPS_MAX, int(payload.timesteps)))
    warmup = min(2_000, max(100, timesteps // 10))
    eval_interval = min(10_000, max(500, timesteps // 10))

    runtime.invalidate_actor()
    runtime.train_monitor = TrainMonitor()
    runtime.train_stop = threading.Event()
    args = argparse.Namespace(
        timesteps=timesteps,
        warmup=warmup,
        max_steps=500,
        hidden=256,
        lidar_beams=16,
        lidar_range=280.0,
        eval_interval=eval_interval,
        eval_episodes=25,
        save_dir="models",
        maps=names,
        cpu=False,
    )

    def worker():
        try:
            train(args, progress_cb=runtime.train_monitor.on_progress, stop_event=runtime.train_stop)
        except Exception as exc:
            runtime.train_monitor.on_progress({"done": True, "error": str(exc)})
        finally:
            runtime.invalidate_actor()

    runtime.train_thread = threading.Thread(target=worker, daemon=True)
    runtime.train_thread.start()
    return {"ok": True}


@app.post("/api/train/stop")
def api_train_stop():
    if runtime.train_stop is not None:
        runtime.train_stop.set()
    return {"ok": True}


@app.websocket("/ws/game")
async def game_ws(websocket: WebSocket):
    await websocket.accept()
    env: Optional[SteeringParkingEnv] = None
    actor = None
    device = None
    running = False
    loop_task: Optional[asyncio.Task] = None
    executor_loop = asyncio.get_running_loop()

    async def send_state(state: dict):
        await websocket.send_json(state)

    async def run_loop():
        nonlocal running
        try:
            while running and env is not None and actor is not None:
                state = await executor_loop.run_in_executor(
                    None, step_agent, env, actor, device
                )
                await send_state(state)
                if state.get("done"):
                    await asyncio.sleep(0.7)
                    if env is not None and running:
                        env.reset()
                else:
                    await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            running = False
        except Exception as exc:
            running = False
            try:
                await websocket.send_json({"error": str(exc)})
            except Exception:
                pass

    try:
        while True:
            msg = await websocket.receive_json()
            kind = msg.get("type")
            if kind == "start":
                names = list_map_names()
                map_name = msg.get("map_name")
                if not names:
                    await websocket.send_json({"error": "Brak map."})
                    continue
                if map_name not in names:
                    map_name = names[0]
                if env is None:
                    env = SteeringParkingEnv(
                        map_name=map_name, render_mode=None, create_window=False
                    )
                else:
                    env.set_map(map_name)
                try:
                    actor, device = await executor_loop.run_in_executor(None, load_actor, env)
                except Exception as exc:
                    await websocket.send_json({"error": str(exc)})
                    continue
                env.reset()
                env.show_lidar = True
                running = True
                if loop_task is not None and not loop_task.done():
                    running = False
                    loop_task.cancel()
                    try:
                        await loop_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    running = True
                await send_state(env.get_render_state())
                loop_task = asyncio.create_task(run_loop())
            elif kind == "reset":
                if env is not None:
                    env.reset()
                    await send_state(env.get_render_state())
            elif kind == "toggle_lidar":
                if env is not None:
                    env.show_lidar = not env.show_lidar
            elif kind == "stop":
                running = False
                if loop_task is not None and not loop_task.done():
                    loop_task.cancel()
                    try:
                        await loop_task
                    except (asyncio.CancelledError, Exception):
                        pass
                loop_task = None
            elif kind == "close":
                break
    except WebSocketDisconnect:
        pass
    finally:
        running = False
        if loop_task is not None and not loop_task.done():
            loop_task.cancel()
        if env is not None:
            env.close()


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def run_app():
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run_app()
