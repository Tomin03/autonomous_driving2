import math


class Rect:
    """AABB z interfejsem zbliżonym do pygame.Rect (left/right/inflate)."""

    __slots__ = ("x", "y", "width", "height")

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

    @property
    def w(self):
        return self.width

    @property
    def h(self):
        return self.height

    @property
    def topleft(self):
        return (self.x, self.y)

    def inflate(self, dx, dy):
        dx, dy = int(dx), int(dy)
        return Rect(
            self.x - dx // 2,
            self.y - dy // 2,
            self.width + dx,
            self.height + dy,
        )

    def collidepoint(self, x, y=None):
        if y is None:
            x, y = x
        return self.left <= x < self.right and self.top <= y < self.bottom


class ParkingSpot:
    def __init__(self, x, y, width=45, height=80, is_target=False, color=(180, 180, 180)):
        self.rect = Rect(x, y, width, height)
        self.is_target = is_target
        self.color = (0, 200, 0) if is_target else color

    def draw(self, surface):
        import pygame

        if self.is_target:
            fill = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
            fill.fill((0, 200, 0, 50))
            surface.blit(fill, self.rect.topleft)
        width = 3 if self.is_target else 2
        pygame.draw.rect(surface, self.color, self.rect, width=width)


class Car:
    def __init__(self, x, y, width=25, height=60, color=(70, 70, 70), is_hollow=False,
                 wheelbase=40.0, rear_axle_offset_y=10.0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.is_hollow = is_hollow
        self.wheelbase = wheelbase

        scale = max(0.5, width / 25.0)
        self.wheel_w = max(3, int(round(4 * scale)))
        self.wheel_h = max(6, int(round(10 * scale)))
        self.wheel_color = (20, 20, 20)

        self.rear_axle_offset_y = float(rear_axle_offset_y)
        self.theta = 0.0
        self.corners = []
        self.rect = Rect(0, 0, self.width, self.height)
        self.update_position(self.x, self.y, 0.0)

    def update_position(self, x, y, theta=0.0):
        """Aktualizuje pozycję środka tylnej osi, narożniki OBB i AABB."""
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

    def draw(self, surface, steer_angle=0.0):
        """Rysuje karoserię i 4 koła. Sprite skierowany w górę (przód przy y=0)."""
        import pygame

        body_rect = pygame.Rect(0, 0, self.width, self.height)
        if self.is_hollow:
            pygame.draw.rect(
                surface, self.color, body_rect, width=3, border_radius=4
            )
        else:
            pygame.draw.rect(surface, self.color, body_rect, border_radius=4)

        rear_y = self.height - self.rear_axle_offset_y - self.wheel_h // 2
        front_y = rear_y - int(self.wheelbase)
        left_x = 1
        right_x = self.width - self.wheel_w - 1

        front_wheels = [
            pygame.Rect(left_x, front_y, self.wheel_w, self.wheel_h),
            pygame.Rect(right_x, front_y, self.wheel_w, self.wheel_h),
        ]
        rear_wheels = [
            pygame.Rect(left_x, rear_y, self.wheel_w, self.wheel_h),
            pygame.Rect(right_x, rear_y, self.wheel_w, self.wheel_h),
        ]

        for w_rect in rear_wheels:
            self._blit_wheel(surface, w_rect, 0.0)
        for w_rect in front_wheels:
            self._blit_wheel(surface, w_rect, steer_angle)

    def _blit_wheel(self, surface, rect, angle_rad):
        import pygame

        wheel = pygame.Surface((self.wheel_w, self.wheel_h), pygame.SRCALPHA)
        pygame.draw.rect(
            wheel, self.wheel_color, wheel.get_rect(), border_radius=1
        )
        if angle_rad != 0.0:
            wheel = pygame.transform.rotate(wheel, -math.degrees(angle_rad))
        blit_rect = wheel.get_rect(center=rect.center)
        surface.blit(wheel, blit_rect)
