import math


class KinematicBicycleModel:
    def __init__(self, wheelbase=40.0):
        self.L = wheelbase

    def update(self, x, y, theta, v, phi, dt):
        dx = v * math.cos(theta) * dt
        dy = v * math.sin(theta) * dt
        dtheta = (v / self.L) * math.tan(phi) * dt

        new_x = x + dx
        new_y = y + dy
        new_theta = theta + dtheta

        # Normalizacja kąta theta do zakresu [-pi, pi]
        new_theta = math.atan2(math.sin(new_theta), math.cos(new_theta))
        return new_x, new_y, new_theta