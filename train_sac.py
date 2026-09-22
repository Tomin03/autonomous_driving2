
import argparse
import os
import time

import numpy as np
import torch

from maps import list_map_names
from sac import SACAgent
from steering_logic import SteeringParkingEnv


CONTROL_DT = 0.05


def make_env(args):
    return SteeringParkingEnv(
        map_name=args.maps[0],
        n_lidar_beams=args.lidar_beams,
        lidar_max_range=args.lidar_range,
        randomize_maps=len(args.maps) > 1,
        spawn_noise=True,
        time_limit=True,
        max_episode_steps=args.max_steps,
        train_maps=args.maps,
    )


def evaluate(env, agent, episodes=25):
    successes = 0
    collisions = 0
    timeouts = 0
    returns = []
    for _ in range(episodes):
        obs = env.reset()
        done = False
        ep_ret = 0.0
        info = {}
        while not done:
            action = agent.act(obs, deterministic=True)
            v, phi = env.unscale_action(action)
            obs, reward, done, info = env.step([v, phi], dt=CONTROL_DT)
            ep_ret += reward
        returns.append(ep_ret)
        if info.get("success"):
            successes += 1
        elif info.get("collision"):
            collisions += 1
        else:
            timeouts += 1
    return {
        "success_rate": successes / episodes,
        "collision_rate": collisions / episodes,
        "timeout_rate": timeouts / episodes,
        "return": float(np.mean(returns)),
    }


def train(args, progress_cb=None, stop_event=None):
    os.makedirs(args.save_dir, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() and not args.cpu else "cpu")
    print(f"Urzadzenie: {device}")
    print("Algorytm: SAC (krytyk privileged)")
    print(f"Mapy: {', '.join(args.maps)}")
    print(f"Kroki treningu: {args.timesteps}")
    print("Log: R = nagroda epizodu, avg20 = srednia z ostatnich 20 epizodow")
    print("Eval jest deterministyczny (bez szumu SAC); ok= w treningu liczy tez przypadkowe sukcesy z eksploracji")

    env = make_env(args)
    eval_env = make_env(args)
    agent = SACAgent(
        env.obs_dim,
        env.act_dim,
        device,
        priv_dim=env.priv_dim,
        hidden=args.hidden,
    )

    obs = env.reset()
    priv = env.get_priv_obs(obs)
    ep_ret = 0.0
    ep_len = 0
    ep_idx = 0
    successes = 0
    collisions = 0
    timeouts = 0
    streak = 0
    best_streak = 0
    recent = []
    recent_ok = []
    avg_window = 20
    ok_window = 50
    best_key = None
    start = time.time()
    ep_traj = []
    stopped = False
    last_step = 0

    def emit(extra=None):
        if progress_cb is None:
            return
        payload = {
            "step": last_step,
            "timesteps": args.timesteps,
            "episode": ep_idx,
            "reward": extra.get("ep_reward", 0.0) if extra else 0.0,
            "avg20": float(np.mean(recent)) if recent else 0.0,
            "successes": successes,
            "collisions": collisions,
            "timeouts": timeouts,
            "streak": streak,
            "best_streak": best_streak,
            "elapsed": time.time() - start,
            "done": False,
            "stopped": False,
        }
        if extra:
            payload.update(extra)
        progress_cb(payload)

    try:
        for step in range(1, args.timesteps + 1):
            last_step = step
            if stop_event is not None and stop_event.is_set():
                stopped = True
                print("Przerwano z interfejsu — zapisuje ostatni model.")
                break

            if step < args.warmup:
                action = np.random.uniform(-1.0, 1.0, size=env.act_dim).astype(np.float32)
                v, phi = env.unscale_action(action)
            else:
                action = agent.act(obs, deterministic=False)
                v, phi = env.unscale_action(action)

            next_obs, reward, done, info = env.step([v, phi], dt=CONTROL_DT)
            next_priv = env.get_priv_obs(next_obs)
            terminated = bool(info.get("success") or info.get("collision"))
            transition = (
                obs,
                priv,
                action,
                reward,
                next_obs,
                next_priv,
                terminated,
            )
            agent.remember(*transition)
            ep_traj.append(transition)

            obs = next_obs
            priv = next_priv
            ep_ret += reward
            ep_len += 1

            if step >= args.warmup:
                agent.update()

            if done:
                ep_idx += 1
                recent.append(ep_ret)
                if len(recent) > avg_window:
                    recent.pop(0)
                if info.get("success"):
                    successes += 1
                    streak += 1
                    best_streak = max(best_streak, streak)
                    for tr in ep_traj:
                        agent.remember_success(*tr)
                    outcome = "ok"
                elif info.get("collision"):
                    collisions += 1
                    streak = 0
                    outcome = "crash"
                else:
                    timeouts += 1
                    streak = 0
                    outcome = "timeout"
                recent_ok.append(1.0 if outcome == "ok" else 0.0)
                if len(recent_ok) > ok_window:
                    recent_ok.pop(0)
                elapsed = time.time() - start
                print(
                    f"ep={ep_idx:5d}  step={step:7d}  "
                    f"R={ep_ret:8.1f}  avg{avg_window}={np.mean(recent):7.1f}  "
                    f"len={ep_len:4d}  {outcome:7s}  "
                    f"ok={successes:4d}  crash={collisions:4d}  timeout={timeouts:4d}  "
                    f"t={elapsed:6.0f}s"
                )
                emit({"outcome": outcome, "ep_reward": ep_ret, "ep_len": ep_len})
                obs = env.reset()
                priv = env.get_priv_obs(obs)
                ep_ret = 0.0
                ep_len = 0
                ep_traj = []

            if step % args.eval_interval == 0:
                stats = evaluate(eval_env, agent, episodes=args.eval_episodes)
                train_ok = float(np.mean(recent_ok)) if recent_ok else 0.0
                print(
                    f"[eval] step={step}  "
                    f"det_ok={stats['success_rate']:.2f}  "
                    f"det_crash={stats['collision_rate']:.2f}  "
                    f"det_timeout={stats['timeout_rate']:.2f}  "
                    f"train_ok{ok_window}={train_ok:.2f}  "
                    f"R_avg={stats['return']:.1f}  "
                    f"avg{avg_window}_train={np.mean(recent) if recent else 0.0:.1f}"
                )
                ckpt_extra = {
                    "algo": "sac",
                    "n_lidar_beams": args.lidar_beams,
                    "lidar_max_range": args.lidar_range,
                    "maps": args.maps,
                    "step": step,
                }
                latest = os.path.join(args.save_dir, "sac_parking.pt")
                agent.save(latest, extra=ckpt_extra)
                key = (stats["success_rate"], stats["return"])
                if best_key is None or key > best_key:
                    best_key = key
                    best = os.path.join(args.save_dir, "sac_parking_best.pt")
                    agent.save(best, extra=ckpt_extra)
                    print(
                        f"Zapisano najlepszy model "
                        f"(det_ok={stats['success_rate']:.2f}, R_avg={stats['return']:.1f}): {best}"
                    )
                emit({"eval": stats, "saved_best": best_key == key})

    except KeyboardInterrupt:
        stopped = True
        print("Przerwano — zapisuje ostatni model.")
        agent.save(
            os.path.join(args.save_dir, "sac_parking.pt"),
            extra={
                "algo": "sac",
                "n_lidar_beams": args.lidar_beams,
                "lidar_max_range": args.lidar_range,
            },
        )
    finally:
        try:
            agent.save(
                os.path.join(args.save_dir, "sac_parking.pt"),
                extra={
                    "algo": "sac",
                    "n_lidar_beams": args.lidar_beams,
                    "lidar_max_range": args.lidar_range,
                    "maps": args.maps,
                    "step": last_step,
                },
            )
        except Exception:
            pass
        env.close()
        eval_env.close()

    print("Koniec treningu.")
    print("Obejrzyj: python app.py  (http://127.0.0.1:8000, AGENT SAC)")
    if progress_cb is not None:
        progress_cb(
            {
                "step": last_step,
                "timesteps": args.timesteps,
                "episode": ep_idx,
                "reward": 0.0,
                "avg20": float(np.mean(recent)) if recent else 0.0,
                "successes": successes,
                "collisions": collisions,
                "timeouts": timeouts,
                "streak": streak,
                "best_streak": best_streak,
                "elapsed": time.time() - start,
                "done": True,
                "stopped": stopped,
            }
        )


def parse_args():
    p = argparse.ArgumentParser(description="Trening SAC do parkowania")
    p.add_argument("--timesteps", type=int, default=350_000)
    p.add_argument("--warmup", type=int, default=2_000)
    p.add_argument("--max-steps", type=int, default=500)
    p.add_argument("--hidden", type=int, default=256)
    p.add_argument("--lidar-beams", type=int, default=16)
    p.add_argument("--lidar-range", type=float, default=280.0)
    p.add_argument("--eval-interval", type=int, default=10_000)
    p.add_argument("--eval-episodes", type=int, default=25)
    p.add_argument("--save-dir", type=str, default="models")
    p.add_argument("--maps", nargs="+", default=None)
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()
    if not args.maps:
        names = list_map_names()
        args.maps = names if names else [f"map_{i}" for i in range(1, 6)]
    return args


if __name__ == "__main__":
    train(parse_args())
