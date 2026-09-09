import math
import sys
import numpy as np
import pygame
from items import Car, ParkingSpot
from physics import KinematicBicycleModel
from maps import load_map


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


class SteeringParkingEnv:

    def __init__(self, map_name="map_2"):
        pygame.init()
        self.width = 600
        self.height = 600
        self.screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("Parking Environment - Bicycle Kinematic Model")
        self.clock = pygame.time.Clock()

        # Konfiguracja wymiarów (piksele)
        self.spot_w, self.spot_h = 50, 88
        self.car_w, self.car_h = 25, 60
        self.wheelbase = 40.0

        # Limity sterowania w przestrzeni pikseli
        self.max_v = 90.0
        self.max_phi = math.radians(40)
        self.park_hold_required = 2.0
        self.park_speed_eps = 8.0

        # Model fizyki i mapa
        self.physics = KinematicBicycleModel(wheelbase=self.wheelbase)
        
        self.map_name = map_name
        self._init_map()
        self.reset()

    def set_map(self, map_name):
        """Zmienia bieżącą mapę i resetuje środowisko."""
        self.map_name = map_name
        self._init_map()
        self.reset()

    def _init_map(self):
        """Ładuje dane mapy z modułu maps.py."""
        self.spots, self.target_spot, self.obstacles, self.start_pos = load_map(
            self.map_name, self
        )

    def reset(self):
        self.x, self.y, self.theta = self.start_pos
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
        )
        self.car.update_position(self.x, self.y, self.theta)
        self.park_time = 0.0
        return self._get_obs()

    def _get_obs(self):
        return np.array(
            [self.x, self.y, self.theta, self.v, self.phi], dtype=np.float32
        )

    def step(self, action, dt=0.1):
        """action = [v_cmd, delta_cmd]"""
        target_v, target_phi = action

        self.v = float(np.clip(target_v, -self.max_v / 2, self.max_v))
        self.phi = float(np.clip(target_phi, -self.max_phi, self.max_phi))

        self.x, self.y, self.theta = self.physics.update(
            self.x, self.y, self.theta, self.v, self.phi, dt
        )
        self.car.update_position(self.x, self.y, self.theta)

        reward = -1.0
        done = False

        if self._is_fully_parked() and abs(self.v) <= self.park_speed_eps:
            self.park_time += dt
            if self.park_time >= self.park_hold_required:
                return self._get_obs(), 100.0, True, {}
        else:
            self.park_time = 0.0

        if not (0 <= self.x <= self.width and 0 <= self.y <= self.height):
            return self._get_obs(), -100.0, True, {}

        for obs in self.obstacles:
            if polygons_overlap(self.car.corners, obs.corners):
                return self._get_obs(), -100.0, True, {}

        return self._get_obs(), reward, done, {}

    def _heading_error(self):
        """Oblicza błąd kąta w zależności od orientacji slotu (pionowy vs poziomy)."""
        is_horizontal = self.target_spot.rect.width > self.target_spot.rect.height
        
        if is_horizontal:
            to_right = abs(math.atan2(math.sin(self.theta), math.cos(self.theta)))
            to_left = abs(math.atan2(math.sin(self.theta - math.pi), math.cos(self.theta - math.pi)))
            return min(to_right, to_left)
        else:
            to_up = abs(math.atan2(math.sin(self.theta + math.pi / 2), math.cos(self.theta + math.pi / 2)))
            to_down = abs(math.atan2(math.sin(self.theta - math.pi / 2), math.cos(self.theta - math.pi / 2)))
            return min(to_up, to_down)

    def _is_fully_parked(self):
        """Cała karoseria mieści się w slocie, auto poprawnie wyrównane."""
        if self._heading_error() > math.radians(18):
            return False
        r = self.target_spot.rect
        margin = 1.0
        for x, y in self.car.corners:
            if not (
                r.left + margin <= x <= r.right - margin
                and r.top + margin <= y <= r.bottom - margin
            ):
                return False
        return True

    def render(self):
        self.screen.fill((240, 240, 240))

        # Bandy mapy (zewnętrzna ramka krawędziowa)
        pygame.draw.rect(self.screen, (30, 30, 30), (0, 0, self.width, self.height), 8)

        for spot in self.spots:
            spot.draw(self.screen)
        self.target_spot.draw(self.screen)

        for obstacle in self.obstacles:
            self._draw_rotated_car(obstacle, obstacle.theta)

        self._draw_rotated_car(self.car, self.theta, self.phi)

        pygame.display.flip()

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
        pygame.quit()


def _apply_keyboard(env, keys, dt, v_cmd, delta_cmd):
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


if __name__ == "__main__":
    env = SteeringParkingEnv(map_name="map_2")
    running = True
    v_cmd = 0.0
    delta_cmd = 0.0

    while running:
        dt = env.clock.tick(60) / 1000.0
        dt = min(dt, 0.05)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    env.reset()
                    v_cmd = 0.0
                    delta_cmd = 0.0
                elif event.key == pygame.K_1:
                    env.set_map("map_1")
                    v_cmd = 0.0
                    delta_cmd = 0.0
                elif event.key == pygame.K_2:
                    env.set_map("map_2")
                    v_cmd = 0.0
                    delta_cmd = 0.0

        keys = pygame.key.get_pressed()
        v_cmd, delta_cmd = _apply_keyboard(env, keys, dt, v_cmd, delta_cmd)

        obs, reward, done, info = env.step([v_cmd, delta_cmd], dt=dt)
        env.render()

        if done:
            print(f"Koniec epizodu! Nagroda: {reward}")
            pygame.time.wait(700)
            env.reset()
            v_cmd = 0.0
            delta_cmd = 0.0

    env.close()
    sys.exit(0)