import math


class KinematicBicycleModel:

    def __init__(self, wheelbase=40.0):
        """
        :param wheelbase: Rozstaw osi L (odległość od tylnej osi do przedniej osi)
        """
        self.L = wheelbase

    def update(self, x, y, theta, v, phi, dt):
        """
        Oblicza nową pozycję środka TYLNEJ OSI oraz orientację pojazdu w czasie dt.
        :param x: Współrzędna X środka tylnej osi
        :param y: Współrzędna Y środka tylnej osi
        :param theta: Kąt orientacji pojazdu (w radianach)
        :param v: Prędkość liniowa pojazdu na tylnej osi
        :param phi: Kąt skrętu przednich kół (w radianach)
        :param dt: Krok czasowy (delta time)
        :return: Krotka (new_x, new_y, new_theta) dla środka tylnej osi
        """
        # Obliczenie przyrostów dla środka tylnej osi
        dx = v * math.cos(theta) * dt
        dy = v * math.sin(theta) * dt
        dtheta = (v / self.L) * math.tan(phi) * dt

        # Aktualizacja stanu
        new_x = x + dx
        new_y = y + dy
        new_theta = theta + dtheta

        # Normalizacja kąta theta do zakresu [-pi, pi]
        new_theta = math.atan2(math.sin(new_theta), math.cos(new_theta))

        return new_x, new_y, new_theta