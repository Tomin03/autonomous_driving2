import math
import os
import sys
import numpy as np
from items import Car
from physics import KinematicBicycleModel
from maps import get_map, list_map_names, load_map, map_dims
from lidar import LidarSensor

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
except ImportError:
    pygame = None


def _project(corners, axis):
    ax, ay = axis
    dots = [cx * ax + cy * ay for cx, cy in corners]
    return min(dots), max(dots)


def _axes(corners):
    axes = []
    for i in range(len(corners)):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % len(corners)]
        axes.append((-(y2 - y1), x2 - x1))
    return axes


def polygons_overlap(corners_a, corners_b):
    """SAT: czy dwa wypukłe wielokąty (OBB) nachodzą na siebie."""
    for corners in (corners_a, corners_b):
        for axis in _axes(corners):
            min_a, max_a = _project(corners_a, axis)
            min_b, max_b = _project(corners_b, axis)
            if max_a < min_b or max_b < min_a:
                return False
    return True


def rect_corners(rect):
    return (
        (rect.left, rect.top),
        (rect.right, rect.top),
        (rect.right, rect.bottom),
        (rect.left, rect.bottom),
    )


def _wrap_angle(a):
    return math.atan2(math.sin(a), math.cos(a))


def _point_aabb_dist(px, py, rect):
    cx = min(max(px, rect.left), rect.right)
    cy = min(max(py, rect.top), rect.bottom)
    return math.hypot(px - cx, py - cy)


class SteeringParkingEnv:

    def __init__(
        self,
        map_name="map_1",
        render_mode="human",
        n_lidar_beams=16,
        lidar_max_range=280.0,
        randomize_maps=False,
        spawn_noise=False,
        time_limit=False,
        max_episode_steps=500,
        train_maps=None,
        create_window=True,
    ):
        self.render_mode = render_mode
        self.randomize_maps = randomize_maps
        self.spawn_noise = spawn_noise
        self.time_limit = time_limit
        self.max_episode_steps = max_episode_steps
        self.train_maps = list(train_maps) if train_maps else list_map_names()
        if not self.train_maps:
            self.train_maps = ["map_1"]
        self.rng = np.random.default_rng()
        self._owns_window = False

        self.width = 600
        self.height = 600

        if render_mode == "human" and pygame is not None:
            pygame.init()
            pygame.font.init()
            self.screen = pygame.Surface((self.width, self.height))
            if create_window:
                self._window = pygame.display.set_mode((self.width, self.height))
                pygame.display.set_caption("Parking Environment - Bicycle Kinematic Model")
                self._owns_window = True
            else:
                self._window = None
            self.clock = pygame.time.Clock()
            self.hud_font = pygame.font.SysFont("Consolas", 14)
        else:
            self.screen = None
            self.clock = None
            self.hud_font = None
            self._window = None

        # Konfiguracja wymiarów (piksele) — nadpisywana parametrami mapy
        self.spot_w, self.spot_h = 50, 88
        self.obstacle_w, self.obstacle_h = 50, 88
        self.car_w, self.car_h = 25, 60
        self.obstacle_car_w, self.obstacle_car_h = 25, 60
        self.wheelbase = 40.0
        self.rear = 10.0
        self.obstacle_wheelbase = 40.0
        self.obstacle_rear = 10.0

        # Limity sterowania w przestrzeni pikseli
        self.max_v = 90.0
        self.max_phi = math.radians(40)
        self.max_steer_rate = math.radians(90.0)
        self.steer_jerk_coef = 1.0
        self.park_hold_required = 0.5
        self.park_speed_eps = 8.0
        self.align_heading_tol = math.radians(18)
        self.success_reward = 250.0
        self.idle_grace = 0.6
        self.idle_penalty = 0.35
        self.border_margin = 8.0
        self.tsdf_d0 = 45.0
        self.tsdf_near_dist = 80.0
        self.anchor_dist = 110.0
        self.use_hybrid_escape = False
        self.hybrid_escape = False
        self._escape_active = False
        self._escape_clear = 0.0
        self._escape_hold = 0.0
        self._escape_phase = "follow"
        self._backup_time = 0.0

        self.n_lidar_beams = n_lidar_beams
        self.lidar_max_range = lidar_max_range
        self.lidar = LidarSensor(n_beams=n_lidar_beams, max_range=lidar_max_range)
        self.lidar_ranges = np.full(n_lidar_beams, lidar_max_range, dtype=np.float32)
        self.lidar_hits = np.zeros((n_lidar_beams, 2), dtype=np.float32)
        self.show_lidar = True

        # obs: lidar + [local_x, local_y, sin_err, cos_err, v, phi, horizontal]
        self.obs_dim = n_lidar_beams + 7
        # priv: obs + [bound_clear, occ_clear, tsdf, in_occupied, coverage, dist]
        self.priv_dim = self.obs_dim + 6
        self.act_dim = 2

        self.physics = KinematicBicycleModel(wheelbase=self.wheelbase)

        names = list_map_names()
        if map_name not in names:
            map_name = names[0] if names else "map_1"
        self.map_name = map_name
        self._init_map()
        self.reset()

    def set_map(self, map_name):
        """Zmienia bieżącą mapę i resetuje środowisko."""
        self.map_name = map_name
        self._init_map()
        return self.reset()

    def _apply_map_params(self, data):
        dims = map_dims(data)
        self.max_v = float(dims["max_v"])
        self.car_w = dims["car_w"]
        self.car_h = dims["car_h"]
        self.spot_w = dims["spot_w"]
        self.spot_h = dims["spot_h"]
        self.obstacle_w = dims["obstacle_w"]
        self.obstacle_h = dims["obstacle_h"]
        self.obstacle_car_w = dims["obstacle_car_w"]
        self.obstacle_car_h = dims["obstacle_car_h"]
        self.wheelbase = float(dims["wheelbase"])
        self.rear = float(dims["rear"])
        self.obstacle_wheelbase = float(dims["obstacle_wheelbase"])
        self.obstacle_rear = float(dims["obstacle_rear"])
        self.physics = KinematicBicycleModel(wheelbase=self.wheelbase)

    def _init_map(self):
        """Ładuje dane mapy z modułu maps.py."""
        data = get_map(self.map_name)
        self._apply_map_params(data)
        self.spots, self.target_spot, self.obstacles, self.start_pos = load_map(
            self.map_name, self, data=data
        )
        self.lidar.set_scene(
            self.obstacles, (0.0, 0.0, float(self.width), float(self.height))
        )

    def reset(self):
        if self.randomize_maps:
            self.map_name = str(self.rng.choice(self.train_maps))
            self._init_map()

        self.x, self.y, self.theta = self._spawn_pose()
        self.v = 0.0
        self.phi = 0.0

        self.car = Car(
            self.x,
            self.y,
            self.car_w,
            self.car_h,
            color=(0, 102, 204),
            is_hollow=True,
            wheelbase=self.wheelbase,
            rear_axle_offset_y=self.rear,
        )
        self.car.update_position(self.x, self.y, self.theta)
        self.park_time = 0.0
        self._idle_time = 0.0
        self._escape_active = False
        self._escape_clear = 0.0
        self._escape_hold = 0.0
        self._escape_phase = "follow"
        self._backup_time = 0.0
        self.hybrid_escape = False
        self._anchor_given = False
        self._steps = 0
        self._prev_dist = self._dist_to_target()
        self._prev_tsdf = self._tsdf_value()
        self._prev_coverage = self._park_coverage()
        self._prev_heading_err = abs(self._signed_heading_error())
        return self._get_obs()

    def _spawn_pose(self):
        x0, y0, th0 = self.start_pos
        if not self.spawn_noise:
            return x0, y0, th0

        dummy = Car(
            x0, y0, self.car_w, self.car_h,
            wheelbase=self.wheelbase, rear_axle_offset_y=self.rear,
        )
        for _ in range(24):
            x = x0 + float(self.rng.uniform(-10.0, 10.0))
            y = y0 + float(self.rng.uniform(-10.0, 10.0))
            th = _wrap_angle(th0 + float(self.rng.uniform(-0.15, 0.15)))
            dummy.update_position(x, y, th)
            if self._pose_collides(dummy.corners):
                continue
            return x, y, th
        return x0, y0, th0

    def _pose_collides(self, corners):
        if self._corners_out_of_bounds(corners):
            return True
        for obs in self.obstacles:
            if polygons_overlap(corners, obs.corners):
                return True
        return False

    def _corners_out_of_bounds(self, corners):
        m = self.border_margin
        for x, y in corners:
            if x < m or x > self.width - m or y < m or y > self.height - m:
                return True
        return False

    def _target_center(self):
        r = self.target_spot.rect
        return r.centerx, r.centery

    def _dist_to_target(self):
        cx, cy = self.car.center()
        tx, ty = self._target_center()
        return math.hypot(tx - cx, ty - cy)

    def _clearance_to_bounds(self):
        best = 1e9
        for x, y in self.car.corners:
            best = min(best, x, y, self.width - x, self.height - y)
        return float(best)

    def _clearance_to_occupied(self):
        best = 1e9
        for obs in self.obstacles:
            if polygons_overlap(self.car.corners, obs.corners):
                return 0.0
            r = obs.rect
            for px, py in self.car.corners:
                best = min(best, _point_aabb_dist(px, py, r))
            er = self.car.rect
            for ox, oy in obs.corners:
                best = min(best, _point_aabb_dist(ox, oy, er))
        if best > 1e8:
            return 1e9
        return float(best)

    def _tsdf_value(self):
        """Przybliżenie TSDF z artykułu REAP: 0 przy przeszkodzie, 1 poza buforem d0."""
        d = min(self._clearance_to_bounds(), self._clearance_to_occupied())
        d0 = self.tsdf_d0
        return float(max(0.0, (min(d, d0) / d0) ** 0.5))

    def _privileged_extras(self):
        bound = self._clearance_to_bounds()
        occ = self._clearance_to_occupied()
        return np.array(
            [
                bound / self.width,
                min(occ, self.width) / self.width,
                self._tsdf_value(),
                1.0 if self._in_occupied_bay() else 0.0,
                self._park_coverage(),
                self._dist_to_target() / self.width,
            ],
            dtype=np.float32,
        )

    def get_priv_obs(self, obs=None):
        """Obserwacja aktora + geometria GT tylko dla krytyka (asymetryczny SAC)."""
        if obs is None:
            obs = self._get_obs()
        return np.concatenate([obs, self._privileged_extras()])

    def _desired_heading(self):
        """Najbliższa dopuszczalna orientacja względem slotu."""
        if self.target_spot.rect.width > self.target_spot.rect.height:
            candidates = (0.0, math.pi)
        else:
            candidates = (-math.pi / 2.0, math.pi / 2.0)
        return min(candidates, key=lambda h: abs(_wrap_angle(self.theta - h)))

    def _signed_heading_error(self):
        return _wrap_angle(self._desired_heading() - self.theta)

    def _target_in_car_frame(self):
        cx, cy = self.car.center()
        tx, ty = self._target_center()
        dx, dy = tx - cx, ty - cy
        c, s = math.cos(self.theta), math.sin(self.theta)
        local_x = dx * c + dy * s
        local_y = -dx * s + dy * c
        return local_x, local_y

    def _get_obs(self):
        origin = self.car.center()
        self.lidar_ranges, self.lidar_hits = self.lidar.scan(origin, self.theta)

        lidar_n = self.lidar_ranges / self.lidar_max_range
        local_x, local_y = self._target_in_car_frame()
        err = self._signed_heading_error()
        is_horizontal = 1.0 if self.target_spot.rect.width > self.target_spot.rect.height else 0.0

        extra = np.array(
            [
                local_x / self.width,
                local_y / self.height,
                math.sin(err),
                math.cos(err),
                self.v / self.max_v,
                self.phi / self.max_phi,
                is_horizontal,
            ],
            dtype=np.float32,
        )
        return np.concatenate([lidar_n.astype(np.float32), extra])

    def unscale_action(self, action):
        """Mapuje akcję agenta z [-1, 1] na (v, phi) w jednostkach fizycznych."""
        a_v = float(np.clip(action[0], -1.0, 1.0))
        a_phi = float(np.clip(action[1], -1.0, 1.0))
        if a_v >= 0.0:
            v = a_v * self.max_v
        else:
            v = a_v * (self.max_v / 2.0)
        phi = a_phi * self.max_phi
        return v, phi

    def scale_action(self, v, phi):
        """Odwrotność unscale_action: (v, phi) → [-1, 1]."""
        v = float(np.clip(v, -self.max_v / 2.0, self.max_v))
        phi = float(np.clip(phi, -self.max_phi, self.max_phi))
        a_v = v / self.max_v if v >= 0.0 else v / (self.max_v / 2.0)
        a_phi = phi / self.max_phi
        return np.array([a_v, a_phi], dtype=np.float32)

    def _refresh_lidar(self):
        origin = self.car.center()
        self.lidar_ranges, self.lidar_hits = self.lidar.scan(origin, self.theta)

    def _lidar_sector_min(self, center_deg, halfwidth_deg):
        """Najmniejszy zasięg LiDAR w sektorze względem przodu auta."""
        if self.lidar_ranges.size == 0:
            return self.lidar_max_range
        center = math.radians(center_deg)
        half = math.radians(halfwidth_deg)
        angs = np.asarray(self.lidar.relative_angles, dtype=np.float64)
        delta = np.abs((angs - center + math.pi) % (2.0 * math.pi) - math.pi)
        sel = delta <= half
        if not np.any(sel):
            idx = int(np.argmin(delta))
            return float(self.lidar_ranges[idx])
        return float(np.min(self.lidar_ranges[sel]))

    def _looks_like_parking(self):
        """SAC ma parkować — nie wyciągaj auta ze slotu docelowego."""
        if self._is_fully_parked():
            return True
        if polygons_overlap(self.car.corners, rect_corners(self.target_spot.rect)):
            return True
        if self._park_coverage() >= 0.5 and self._dist_to_target() < 90.0:
            return True
        return False

    def _in_occupied_bay(self):
        """Karoseria zachodzi na zajęte miejsce parkingowe (z małym marginesem)."""
        for spot in self.spots:
            r = spot.rect.inflate(10, 10)
            if polygons_overlap(self.car.corners, rect_corners(r)):
                return True
        return False

    def _near_occupied_spot(self, inflate=22):
        for spot in self.spots:
            r = spot.rect.inflate(inflate, inflate)
            if polygons_overlap(self.car.corners, rect_corners(r)):
                return True
        return False

    def _approaching_occupied(self):
        """Zbyt blisko zajętego slotu z przodu — jeszcze niekoniecznie w środku."""
        if self._looks_like_parking():
            return False
        front = self._lidar_sector_min(0.0, 34.0)
        if front > 44.0:
            return False
        return self._near_occupied_spot(24)

    def _should_backup_first(self):
        rear = self._lidar_sector_min(180.0, 38.0)
        if rear < 18.0:
            return False
        front = self._lidar_sector_min(0.0, 38.0)
        return front < 52.0 or self._in_occupied_bay()

    def _escape_space_clear(self):
        front = self._lidar_sector_min(0.0, 35.0)
        return (not self._in_occupied_bay()) and front > 62.0

    def _backup_action(self, dt):
        """Lekkie cofanie na wprost — bez skrętu, żeby odejść od slotu."""
        rear = self._lidar_sector_min(180.0, 38.0)
        front = self._lidar_sector_min(0.0, 36.0)
        if rear < 16.0:
            self._escape_phase = "follow"
            self._backup_time = 0.0
            return self._follow_action()

        self._backup_time += dt
        v = -24.0
        phi = 0.0
        backed_enough = self._backup_time >= 0.28 and front >= 48.0
        timed_out = self._backup_time >= 0.70
        if backed_enough or timed_out:
            self._escape_phase = "follow"
            self._backup_time = 0.0
        return v, phi

    def _follow_action(self):
        """Dopiero po cofnięciu: obrót i jazda wzdłuż prawej ściany."""
        front = self._lidar_sector_min(0.0, 32.0)
        right = self._lidar_sector_min(90.0, 28.0)
        right_fwd = self._lidar_sector_min(50.0, 22.0)
        rear = self._lidar_sector_min(180.0, 38.0)

        if front < 30.0 and rear > 20.0:
            self._escape_phase = "backup"
            self._backup_time = 0.0
            return -24.0, 0.0

        desired_right = 36.0
        err = desired_right - right
        phi = -0.045 * err
        if right_fwd < right - 8.0:
            phi -= 0.22 * self.max_phi
        if front < 70.0:
            phi -= 0.18 * self.max_phi * (1.0 - front / 70.0)
            v = 32.0
        else:
            v = 42.0
        return v, float(np.clip(phi, -self.max_phi, self.max_phi))

    def _escape_action(self, dt):
        if self._escape_phase == "backup":
            return self._backup_action(dt)
        return self._follow_action()

    def apply_hybrid_escape(self, v_cmd, phi_cmd, dt=0.05):
        """W zajętym slocie: najpierw cofnij, potem wall-follow, na końcu SAC."""
        if not self.use_hybrid_escape:
            self.hybrid_escape = False
            return v_cmd, phi_cmd

        self._refresh_lidar()
        was_active = self._escape_active
        was_phase = self._escape_phase
        trapped = self._in_occupied_bay() or self._approaching_occupied()

        if self._looks_like_parking():
            self._escape_active = False
            self._escape_clear = 0.0
            self._escape_hold = 0.0
            self._backup_time = 0.0
        elif trapped:
            if not self._escape_active:
                self._escape_phase = (
                    "backup" if self._should_backup_first() else "follow"
                )
                self._backup_time = 0.0
            self._escape_active = True
            self._escape_clear = 0.0
            self._escape_hold = 0.0
        elif self._escape_active:
            self._escape_hold += dt
            if self._escape_hold >= 0.45 and self._escape_space_clear():
                self._escape_clear += dt
                if self._escape_clear >= 0.30:
                    self._escape_active = False
                    self._escape_hold = 0.0
                    self._escape_clear = 0.0
                    self._backup_time = 0.0
            else:
                self._escape_clear = 0.0

        self.hybrid_escape = self._escape_active
        if self._escape_active:
            v_cmd, phi_cmd = self._escape_action(dt)

        if self._escape_active and not was_active:
            if was_phase == "backup" or self._escape_phase == "backup":
                print("Hybryda: cofanie (za blisko slotu)")
            else:
                print("Hybryda: wall-follow (wyjazd z zajetego slotu)")
        elif self._escape_active and was_phase == "backup" and self._escape_phase == "follow":
            print("Hybryda: wall-follow wzdluz scian")
        elif was_active and not self._escape_active:
            print("Hybryda: oddaje sterowanie SAC")

        return v_cmd, phi_cmd

    def step(self, action, dt=0.1):
        """action = [v_cmd, delta_cmd] w jednostkach fizycznych."""
        target_v, target_phi = action

        self.v = float(np.clip(target_v, -self.max_v / 2, self.max_v))
        target_phi = float(np.clip(target_phi, -self.max_phi, self.max_phi))
        dphi_cmd = abs(target_phi - self.phi)
        max_step = self.max_steer_rate * dt
        self.phi = float(np.clip(target_phi, self.phi - max_step, self.phi + max_step))

        reward = 0.0
        reward -= self.steer_jerk_coef * (dphi_cmd / (2.0 * self.max_phi)) ** 2

        self.x, self.y, self.theta = self.physics.update(
            self.x, self.y, self.theta, self.v, self.phi, dt
        )
        self.car.update_position(self.x, self.y, self.theta)
        self._steps += 1

        dist = self._dist_to_target()
        heading_err = abs(self._signed_heading_error())
        proximity = max(0.0, 1.0 - dist / 220.0)
        coverage = self._park_coverage()
        in_spot = self._body_in_spot()
        aligned = in_spot and heading_err <= self.align_heading_tol

        reward += (self._prev_dist - dist) * 0.25
        reward -= 0.04
        reward -= (heading_err / math.pi) * 0.4 * proximity
        # Pokrycie i kąt: tylko przyrost, bez premii za „siedzenie” w slocie.
        reward += (coverage - self._prev_coverage) * 2.0
        if coverage > 0.0 or dist < 90.0:
            reward += (self._prev_heading_err - heading_err) * 0.8

        tsdf = self._tsdf_value()
        # TSDF nie karze wjazdu między zaparkowane auta przy celu.
        if in_spot or coverage > 0.0:
            tsdf_coef = 0.0
        else:
            tsdf_coef = 1.5 * min(
                1.0, max(0.0, (dist - self.tsdf_near_dist) / 70.0)
            )
        reward += (tsdf - self._prev_tsdf) * tsdf_coef
        if not self._anchor_given and dist < self.anchor_dist:
            reward += 4.0
            self._anchor_given = True
        self._prev_dist = dist
        self._prev_tsdf = tsdf
        self._prev_coverage = coverage
        self._prev_heading_err = heading_err

        if abs(self.v) <= self.park_speed_eps:
            self._idle_time += dt
        else:
            self._idle_time = 0.0
        # Bezruch: kara tylko daleko od slotu. Prędkość: kara tylko po wyrównaniu.
        if not in_spot and dist > 90.0 and self._idle_time > self.idle_grace:
            reward -= self.idle_penalty * (self._idle_time - self.idle_grace)
        if aligned:
            reward -= abs(self.v) / self.max_v * 0.15

        info = {
            "dist": dist,
            "success": False,
            "collision": False,
            "timeout": False,
        }

        if in_spot:
            if aligned:
                self.park_time += dt
                if self.park_time >= self.park_hold_required:
                    info["success"] = True
                    return self._get_obs(), self.success_reward, True, info
            else:
                # Krótki flicker >18° nie zeruje holdu (brak farmy za oscylację).
                self.park_time = max(0.0, self.park_time - dt)
        else:
            self.park_time = 0.0

        if self._corners_out_of_bounds(self.car.corners):
            info["collision"] = True
            return self._get_obs(), -40.0, True, info

        for obs in self.obstacles:
            if polygons_overlap(self.car.corners, obs.corners):
                info["collision"] = True
                return self._get_obs(), -40.0, True, info

        if self.time_limit and self._steps >= self.max_episode_steps:
            info["timeout"] = True
            return self._get_obs(), reward - 5.0, True, info

        return self._get_obs(), reward, False, info

    def _park_coverage(self):
        r = self.target_spot.rect
        n = 0
        for x, y in self.car.corners:
            if r.left <= x <= r.right and r.top <= y <= r.bottom:
                n += 1
        return n / 4.0

    def _heading_error(self):
        """Oblicza błąd kąta w zależności od orientacji slotu (pionowy vs poziomy)."""
        return abs(self._signed_heading_error())

    def _body_in_spot(self):
        """Wszystkie narożniki karoserii są w prostokącie slotu."""
        r = self.target_spot.rect
        margin = 1.0
        for x, y in self.car.corners:
            if not (
                r.left + margin <= x <= r.right - margin
                and r.top + margin <= y <= r.bottom - margin
            ):
                return False
        return True

    def _is_fully_parked(self):
        """Całe auto w slocie i kąt ≤ 18° (równe koła)."""
        return (
            self._body_in_spot()
            and self._heading_error() <= self.align_heading_tol
        )

    def get_render_state(self, reward=0.0, done=False, info=None):
        """Stan planszy do narysowania w przeglądarce (bez pygame)."""
        origin = self.car.center()
        info = info or {}

        def spot_payload(spot):
            r = spot.rect
            return {
                "x": int(r.x),
                "y": int(r.y),
                "w": int(r.width),
                "h": int(r.height),
                "is_target": bool(spot.is_target),
            }

        def car_payload(car, phi=0.0, hollow=None):
            return {
                "corners": [[float(x), float(y)] for x, y in car.corners],
                "x": float(car.x),
                "y": float(car.y),
                "theta": float(car.theta),
                "width": float(car.width),
                "height": float(car.height),
                "hollow": bool(car.is_hollow if hollow is None else hollow),
                "phi": float(phi),
                "color": [int(c) for c in car.color],
                "wheelbase": float(car.wheelbase),
                "rear_axle_offset_y": float(car.rear_axle_offset_y),
                "wheel_w": int(car.wheel_w),
                "wheel_h": int(car.wheel_h),
            }

        if self.hybrid_escape:
            ctrl = "COFANIE" if self._escape_phase == "backup" else "ESCAPE"
        else:
            ctrl = ""

        return {
            "width": self.width,
            "height": self.height,
            "map_name": self.map_name,
            "spots": [spot_payload(s) for s in self.spots],
            "target": spot_payload(self.target_spot),
            "obstacles": [car_payload(obs) for obs in self.obstacles],
            "car": {
                **car_payload(self.car, phi=self.phi, hollow=True),
                "center": [float(origin[0]), float(origin[1])],
            },
            "lidar": {
                "show": bool(self.show_lidar),
                "origin": [float(origin[0]), float(origin[1])],
                "hits": self.lidar_hits.astype(float).tolist(),
                "ranges": self.lidar_ranges.astype(float).tolist(),
                "max_range": float(self.lidar_max_range),
            },
            "hud": {
                "v": float(self.v),
                "phi_deg": float(math.degrees(self.phi)),
                "lidar_min": float(np.min(self.lidar_ranges)),
                "dist": float(self._dist_to_target()),
                "parked": bool(self._is_fully_parked()),
                "control": ctrl,
            },
            "reward": float(reward),
            "done": bool(done),
            "info": {
                "dist": float(info.get("dist", 0.0)),
                "success": bool(info.get("success", False)),
                "collision": bool(info.get("collision", False)),
                "timeout": bool(info.get("timeout", False)),
            },
        }

    def render(self, dest=None, pos=(0, 0), flip=True):
        if self.screen is None:
            return

        self.screen.fill((240, 240, 240))

        pygame.draw.rect(self.screen, (30, 30, 30), (0, 0, self.width, self.height), 8)

        for spot in self.spots:
            spot.draw(self.screen)
        self.target_spot.draw(self.screen)

        for obstacle in self.obstacles:
            self._draw_rotated_car(obstacle, obstacle.theta)

        if self.show_lidar:
            self._draw_lidar()

        self._draw_rotated_car(self.car, self.theta, self.phi)
        self._draw_hud()

        target = dest if dest is not None else self._window
        if target is not None:
            target.blit(self.screen, pos)
        if flip and target is not None:
            pygame.display.flip()

    def _draw_lidar(self):
        origin = self.car.center()
        ox, oy = int(origin[0]), int(origin[1])
        for i, dist in enumerate(self.lidar_ranges):
            hx, hy = self.lidar_hits[i]
            t = float(np.clip(dist / self.lidar_max_range, 0.0, 1.0))
            color = (int(220 * (1.0 - t)), int(180 * t), 40)
            pygame.draw.line(self.screen, color, (ox, oy), (int(hx), int(hy)), 1)
            pygame.draw.circle(self.screen, color, (int(hx), int(hy)), 2)
        pygame.draw.circle(self.screen, (255, 140, 0), (ox, oy), 3)

    def _draw_hud(self):
        if self.hud_font is None:
            return
        min_lidar = float(np.min(self.lidar_ranges))
        if self.hybrid_escape:
            ctrl = "COFANIE" if self._escape_phase == "backup" else "ESCAPE"
        else:
            ctrl = ""
        lines = [
            f"v={self.v:6.1f}  phi={math.degrees(self.phi):5.1f}deg",
            f"lidar_min={min_lidar:5.1f}  dist={self._dist_to_target():5.1f}",
            f"mapa={self.map_name}  parked={self._is_fully_parked()}"
            + (f"  {ctrl}" if ctrl else ""),
        ]
        y = 10
        for line in lines:
            surf = self.hud_font.render(line, True, (20, 20, 20))
            self.screen.blit(surf, (12, y))
            y += 16

    def _draw_rotated_car(self, car, theta, steer_angle=0.0):
        """Obrót wokół tylnej osi."""
        image = pygame.Surface((car.width, car.height), pygame.SRCALPHA)
        car.draw(image, steer_angle=steer_angle)

        degrees = -math.degrees(theta) - 90.0
        pivot = pygame.math.Vector2(
            car.width / 2.0, car.height - car.rear_axle_offset_y
        )
        origin = pygame.math.Vector2(car.x, car.y)

        image_rect = image.get_rect(
            topleft=(origin.x - pivot.x, origin.y - pivot.y)
        )
        offset = origin - pygame.math.Vector2(image_rect.center)
        rotated_offset = offset.rotate(-degrees)
        rotated_image = pygame.transform.rotate(image, degrees)
        rotated_center = origin - rotated_offset
        draw_rect = rotated_image.get_rect(center=rotated_center)

        self.screen.blit(rotated_image, draw_rect.topleft)

    def close(self):
        if self._owns_window and pygame is not None:
            pygame.quit()


def _apply_keyboard(env, keys, dt, v_cmd, delta_cmd):
    if pygame is None:
        return v_cmd, delta_cmd
    v_rate = 180.0
    delta_rate = math.radians(120.0)

    if keys[pygame.K_w] or keys[pygame.K_UP]:
        v_cmd += v_rate * dt
    elif keys[pygame.K_s] or keys[pygame.K_DOWN]:
        v_cmd -= v_rate * dt
    else:
        if abs(v_cmd) <= v_rate * dt:
            v_cmd = 0.0
        else:
            v_cmd -= math.copysign(v_rate * dt, v_cmd)

    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        delta_cmd -= delta_rate * dt
    elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        delta_cmd += delta_rate * dt
    else:
        if abs(delta_cmd) <= delta_rate * dt:
            delta_cmd = 0.0
        else:
            delta_cmd -= math.copysign(delta_rate * dt, delta_cmd)

    v_cmd = float(np.clip(v_cmd, -env.max_v / 2, env.max_v))
    delta_cmd = float(np.clip(delta_cmd, -env.max_phi, env.max_phi))
    return v_cmd, delta_cmd


def draw_menu(screen, font, title_font, map_list, mouse_pos, agent_kind):
    """Rysuje graficzny interfejs wyboru mapy i trybu."""
    if pygame is None:
        return [], None
    screen.fill((30, 35, 45))

    title_surf = title_font.render("WYBÓR MAPY", True, (255, 255, 255))
    title_rect = title_surf.get_rect(center=(300, 42))
    screen.blit(title_surf, title_rect)

    mode_labels = {
        "manual": ("GRAJ RECZNIE", (70, 130, 180)),
        "sac": ("AGENT SAC", (80, 180, 120)),
    }
    mode_label, mode_color = mode_labels.get(agent_kind, mode_labels["manual"])
    mode_rect = pygame.Rect(160, 72, 280, 40)
    is_mode_hover = mode_rect.collidepoint(mouse_pos)
    pygame.draw.rect(screen, mode_color, mode_rect, border_radius=8)
    pygame.draw.rect(
        screen,
        (255, 255, 255) if is_mode_hover else (100, 110, 125),
        mode_rect,
        2,
        border_radius=8,
    )
    mode_surf = font.render(f"Tryb: {mode_label}   [A]", True, (255, 255, 255))
    screen.blit(mode_surf, mode_surf.get_rect(center=mode_rect.center))

    buttons = []
    w, h = 280, 52
    x = (600 - w) // 2

    for i, map_name in enumerate(map_list):
        y = 128 + i * 64

        rect = pygame.Rect(x, y, w, h)
        buttons.append((rect, map_name))

        is_hover = rect.collidepoint(mouse_pos)
        color = (70, 130, 180) if is_hover else (50, 60, 75)
        border_color = (255, 255, 255) if is_hover else (100, 110, 125)

        pygame.draw.rect(screen, color, rect, border_radius=8)
        pygame.draw.rect(screen, border_color, rect, 2, border_radius=8)

        text_str = f"Mapa {i+1}   [{i+1}]"
        txt_surf = font.render(text_str, True, (255, 255, 255))
        txt_rect = txt_surf.get_rect(center=rect.center)
        screen.blit(txt_surf, txt_rect)

    hint = font.render("python train_sac.py", True, (170, 175, 185))
    screen.blit(hint, hint.get_rect(center=(300, 560)))

    return buttons, mode_rect


AGENT_CYCLE = ("manual", "sac")

AGENT_MODEL_PATHS = {
    "sac": [
        os.path.join("models", "sac_parking_best.pt"),
        os.path.join("models", "sac_parking.pt"),
    ],
}


def _load_policy_actor(path, obs_dim, act_dim, device, algo_hint=None):
    """Wczytuje Actor z checkpointu SAC."""
    import torch
    from sac import Actor

    try:
        ckpt = torch.load(path, map_location=device, weights_only=False)
    except TypeError:
        ckpt = torch.load(path, map_location=device)

    algo = ckpt.get("algo") or algo_hint or "sac"
    saved_obs = int(ckpt.get("obs_dim", obs_dim))
    saved_act = int(ckpt.get("act_dim", act_dim))

    actor = Actor(saved_obs, saved_act)
    actor.load_state_dict(ckpt["actor"])
    actor.to(device)
    actor.eval()
    return actor, ckpt, algo


def _agent_action(actor, obs, device):
    import torch

    with torch.no_grad():
        x = torch.as_tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)
        action = actor.act(x, deterministic=True)
    return action.squeeze(0).cpu().numpy()


if __name__ == "__main__":
    from app import run_app

    run_app()
