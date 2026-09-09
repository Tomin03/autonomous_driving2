import math
from items import Car, ParkingSpot

MAPS = {
    "map_1": {
        "start_pos": (90.0, 175.0, 0.0),
        "target_spot": {"x": 410, "y": 50, "orientation": "vertical"},
        "occupied_spots": [
            {"x": 270, "y": 50, "orientation": "vertical"},
            {"x": 330, "y": 50, "orientation": "vertical"},
            {"x": 500, "y": 50, "orientation": "vertical"},
            {"x": 330, "y": 230, "orientation": "vertical"},
            {"x": 500, "y": 230, "orientation": "vertical"},
            {"x": 330, "y": 340, "orientation": "vertical"},
            {"x": 110, "y": 460, "orientation": "vertical"},
            {"x": 190, "y": 460, "orientation": "vertical"},
            {"x": 270, "y": 460, "orientation": "vertical"},
        ]
    },
    "map_2": {
        "start_pos": (70.0, 250.0, 0.0),  
        "target_spot": {"x": 500, "y": 130, "orientation": "horizontal"},
        "occupied_spots": [
            # Prawa kolumna (parkowanie równoległe/poziome)
            {"x": 500, "y": 60, "orientation": "horizontal"},
            {"x": 500, "y": 200, "orientation": "horizontal"},
            {"x": 500, "y": 270, "orientation": "horizontal"},
            {"x": 500, "y": 340, "orientation": "horizontal"},
            {"x": 500, "y": 410, "orientation": "horizontal"},
            {"x": 500, "y": 480, "orientation": "horizontal"},

            # Środkowa podwójna kolumna z szeroką przerwą na przejazd
            {"x": 270, "y": 80, "orientation": "vertical"},
            {"x": 325, "y": 80, "orientation": "vertical"},
            {"x": 270, "y": 170, "orientation": "vertical"},
            {"x": 325, "y": 170, "orientation": "vertical"},
            {"x": 270, "y": 260, "orientation": "vertical"},
            {"x": 325, "y": 260, "orientation": "vertical"},
            
            {"x": 270, "y": 450, "orientation": "vertical"},
            {"x": 325, "y": 450, "orientation": "vertical"},

            # Lewa pojedyncza kolumna przeszkód
            {"x": 150, "y": 130, "orientation": "vertical"},
            {"x": 150, "y": 220, "orientation": "vertical"},
            {"x": 150, "y": 310, "orientation": "vertical"},
            {"x": 150, "y": 400, "orientation": "vertical"},
            {"x": 150, "y": 490, "orientation": "vertical"},

            # Górne auto
            {"x": 270, "y": 20, "orientation": "horizontal"},

        ]
    }
}


def load_map(map_name, env_ref):
    """Generuje obiekty spots, target_spot oraz obstacles na podstawie nazwy mapy."""
    if map_name not in MAPS:
        raise ValueError(f"Nie znaleziono mapy: {map_name}")

    data = MAPS[map_name]
    spots = []
    obstacles = []

    def create_spot_and_car(spot_cfg, is_target=False):
        orient = spot_cfg.get("orientation", "vertical")
        
        # Samochód w bazowej orientacji ma wymiary car_w x car_h (25 x 60)
        car_w, car_h = env_ref.car_w, env_ref.car_h

        if orient == "vertical":
            w, h = env_ref.spot_w, env_ref.spot_h
            theta = -math.pi / 2  # Nosem w górę
            axle_x = spot_cfg["x"] + (w // 2)
            axle_y = spot_cfg["y"] + h - 20
        else:  # horizontal (parkowanie równoległe)
            w, h = env_ref.spot_h, env_ref.spot_w
            theta = 0.0  # Nosem w prawo (funkcja rysująca obróci auto do poziomu)
            axle_x = spot_cfg["x"] + 20
            axle_y = spot_cfg["y"] + (h // 2)

        spot_obj = ParkingSpot(spot_cfg["x"], spot_cfg["y"], w, h, is_target=is_target)

        if is_target:
            return spot_obj, None

        car_obj = Car(
            axle_x, axle_y, car_w, car_h,
            color=(70, 70, 70), is_hollow=False, wheelbase=env_ref.wheelbase
        )
        car_obj.update_position(axle_x, axle_y, theta)
        return spot_obj, car_obj

    # Miejsce docelowe
    target_spot, _ = create_spot_and_car(data["target_spot"], is_target=True)

    # Zajęte miejsca i przeszkody
    for s_cfg in data["occupied_spots"]:
        spot_obj, car_obj = create_spot_and_car(s_cfg, is_target=False)
        spots.append(spot_obj)
        obstacles.append(car_obj)

    return spots, target_spot, obstacles, data["start_pos"]