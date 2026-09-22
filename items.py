import math


class Rect:
    __slots__ = ("x", "y", "width", "height")
    # x,y - lewy gorny róg
    def __init__(self, x, y, width, height):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)

    @property
    def left(self):
        return self.x

    @property
    def top(self):
        return self.y

    @property
    def right(self):
        return self.x + self.width

    @property
    def bottom(self):
        return self.y + self.height

    @property
    def centerx(self):
        return self.x + self.width // 2

    @property
    def centery(self):
        return self.y + self.height // 2

    # powiekszanie/pomniejszanie
    def inflate(self, dx, dy):
        dx, dy = int(dx), int(dy)
        return Rect(
            self.x - dx // 2,
            self.y - dy // 2,
            self.width + dx,
            self.height + dy,
        )


class ParkingSpot:
    def __init__(self, x, y, width=45, height=80, is_target=False):
        self.rect = Rect(x, y, width, height)
        self.is_target = is_target


class Car:
    # x, y - środek tylnej osi
    def __init__(self, x, y, width=25, height=60, color=(70, 70, 70), is_hollow=False,
                 wheelbase=40.0, rear_axle_offset_y=10.0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.is_hollow = is_hollow
        #rozstaw osi
        self.wheelbase = wheelbase

        scale = max(0.5, width / 25.0)
        #rozmiary koła
        self.wheel_w = max(3, int(round(4 * scale)))
        self.wheel_h = max(6, int(round(10 * scale)))
        #odl od tylnej osi do zderzaka
        self.rear_axle_offset_y = float(rear_axle_offset_y)
        self.theta = 0.0
        self.corners = []
        self.rect = Rect(0, 0, self.width, self.height)
        self.update_position(self.x, self.y, 0.0)

    def update_position(self, x, y, theta=0.0):
        # x, y i nowe narozniki
        self.x = x
        self.y = y
        self.theta = theta
        self.corners = self._compute_corners(theta)
        xs = [c[0] for c in self.corners]
        ys = [c[1] for c in self.corners]
        self.rect = Rect(
            int(min(xs)),
            int(min(ys)),
            max(1, int(math.ceil(max(xs) - min(xs)))),
            max(1, int(math.ceil(max(ys) - min(ys)))),
        )

    # Oblicza rogi przy nowym srodku tylnej osi
    def _compute_corners(self, theta):
        fx, fy = math.cos(theta), math.sin(theta)
        rx, ry = -math.sin(theta), math.cos(theta)
        half_w = self.width / 2.0
        front = self.height - self.rear_axle_offset_y
        rear = self.rear_axle_offset_y
        corners = []
        for along, across in (
            (front, half_w),
            (front, -half_w),
            (-rear, -half_w),
            (-rear, half_w),
        ):
            corners.append(
                (
                    self.x + along * fx + across * rx,
                    self.y + along * fy + across * ry,
                )
            )
        return corners

    def center(self):
        offset = self.height / 2.0 - self.rear_axle_offset_y
        return (
            self.x + math.cos(self.theta) * offset,
            self.y + math.sin(self.theta) * offset,
        )
