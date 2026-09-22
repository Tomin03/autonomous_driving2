import math
import numpy as np


class LidarSensor:

    def __init__(self, n_beams=16, max_range=280.0, fov=2.0 * math.pi):
        self.n_beams = n_beams
        self.max_range = float(max_range)
        self.fov = float(fov)
        self.relative_angles = np.linspace(0.0, self.fov, n_beams, endpoint=False)
        self.segments = np.zeros((0, 4), dtype=np.float64)

    # W segs zapisywane są wszystkie przeszkody i bandy dla Lidara potem
    def set_scene(self, obstacles, bounds):
        minx, miny, maxx, maxy = bounds
        segs = [
            (minx, miny, maxx, miny),
            (maxx, miny, maxx, maxy),
            (maxx, maxy, minx, maxy),
            (minx, maxy, minx, miny),
        ]
        for obs in obstacles:
            corners = obs.corners
            n = len(corners)
            for i in range(n):
                x1, y1 = corners[i]
                x2, y2 = corners[(i + 1) % n]
                segs.append((x1, y1, x2, y2))
        self.segments = np.asarray(segs, dtype=np.float64)

    def scan(self, origin, heading):
        ox, oy = origin
        hits = np.zeros((self.n_beams, 2), dtype=np.float32)
        #Jeśli nic nie wyłapuje
        if self.segments.shape[0] == 0:
            ranges = np.full(self.n_beams, self.max_range, dtype=np.float32)
            angles = heading + self.relative_angles
            hits[:, 0] = ox + ranges * np.cos(angles)
            hits[:, 1] = oy + ranges * np.sin(angles)
            return ranges, hits

        angles = heading + self.relative_angles
        dx = np.cos(angles)
        dy = np.sin(angles)

        x1 = self.segments[:, 0]
        y1 = self.segments[:, 1]
        sx = self.segments[:, 2] - x1
        sy = self.segments[:, 3] - y1

        # Czy linie równoległe (0 - tak)
        denom = dx[:, None] * sy[None, :] - dy[:, None] * sx[None, :]
        # qx, qy - wektor od auta do pocz. krawędzi
        qx = x1[None, :] - ox
        qy = y1[None, :] - oy
        safe = np.where(np.abs(denom) > 1e-9, denom, 1.0)
        # t - jak przebiega odcinek
        # u - w której częsci odcinka przecięcie
        t = (qx * sy[None, :] - qy * sx[None, :]) / safe
        u = (qx * dy[:, None] - qy * dx[:, None]) / safe

        # Tylko pary, które się krzyżują
        valid = (
            (np.abs(denom) > 1e-9)
            & (t >= 1e-6)
            & (t <= self.max_range)
            & (u >= 0.0)
            & (u <= 1.0)
        )
        t_masked = np.where(valid, t, np.inf)
        best = np.min(t_masked, axis=1)
        ranges = np.where(np.isfinite(best), best, self.max_range).astype(np.float32)

        hits[:, 0] = ox + ranges * dx
        hits[:, 1] = oy + ranges * dy
        return ranges, hits
