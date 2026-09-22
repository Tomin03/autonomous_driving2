import copy
import json
import math
import os

from items import Car, ParkingSpot

STORE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_maps.json")
SPOT_W, SPOT_H = 50, 88
CAR_W, CAR_H = 25, 60
REAR = 10.0
WHEELBASE = 40.0
DEFAULT_MAX_V = 90.0
MAX_V_MIN, MAX_V_MAX = 40.0, 140.0
SIZE_MIN, SIZE_MAX = 0.70, 1.40

MAPS = {
    "map_1": {
        "start_pos": (90.0, 175.0, 0.0),
        "target_spot": {"x": 390, "y": 50, "orientation": "vertical"},
        "occupied_spots": [
            #Górny pas
            {"x": 270, "y": 50, "orientation": "vertical"},
            {"x": 330, "y": 50, "orientation": "vertical"},
            {"x": 450, "y": 50, "orientation": "vertical"},
            {"x": 510, "y": 50, "orientation": "vertical"},

            #Drugi pas
            {"x": 270, "y": 230, "orientation": "vertical"},
            {"x": 330, "y": 230, "orientation": "vertical"},
            {"x": 390, "y": 230, "orientation": "vertical"},
            {"x": 450, "y": 230, "orientation": "vertical"},
            {"x": 510, "y": 230, "orientation": "vertical"},

         

            #Trzeci pas 
            {"x": 270, "y": 470, "orientation": "vertical"},
            {"x": 330, "y": 470, "orientation": "vertical"},
            {"x": 390, "y": 470, "orientation": "vertical"},
            {"x": 450, "y": 470, "orientation": "vertical"},
            {"x": 510, "y": 470, "orientation": "vertical"},
        ]
    }, 
    "map_2": {
        "start_pos": (70.0, 450.0, -1.5708), 
        "target_spot": {"x": 500, "y": 90, "orientation": "horizontal"},
        "occupied_spots": [
            # Pierwszy pas od lewej
            {"x": 150, "y": 220, "orientation": "vertical"},
            {"x": 150, "y": 310, "orientation": "vertical"},
            {"x": 150, "y": 400, "orientation": "vertical"},
            {"x": 150, "y": 490, "orientation": "vertical"},

            # Środkowy górny
            {"x": 270, "y": 20, "orientation": "horizontal"},
            {"x": 270, "y": 170, "orientation": "vertical"},
            {"x": 270, "y": 260, "orientation": "vertical"},
            {"x": 325, "y": 170, "orientation": "vertical"},
            {"x": 325, "y": 260, "orientation": "vertical"},

            # Środkowy dolny
            {"x": 270, "y": 450, "orientation": "vertical"},
            {"x": 325, "y": 450, "orientation": "vertical"},

            # Prawy
            {"x": 500, "y": 30, "orientation": "horizontal"},
            {"x": 500, "y": 150, "orientation": "horizontal"},
            {"x": 500, "y": 210, "orientation": "horizontal"},
            {"x": 500, "y": 270, "orientation": "horizontal"},                     
            {"x": 500, "y": 330, "orientation": "horizontal"},                     
            {"x": 500, "y": 390, "orientation": "horizontal"},                     
            {"x": 500, "y": 450, "orientation": "horizontal"},                     
            {"x": 500, "y": 510, "orientation": "horizontal"},                     

        ]
    },
    "map_3": {
        "start_pos": (90.0, 470.0, -1.5708),  # Autko na dole po lewej, skierowane w górę
        "target_spot": {"x": 450, "y": 210, "orientation": "vertical"},
        "occupied_spots": [
            # Pas 1 Górny
            {"x": 270, "y": 20, "orientation": "vertical"},
            {"x": 330, "y": 20, "orientation": "vertical"},
            {"x": 390, "y": 20, "orientation": "vertical"},
            {"x": 450, "y": 20, "orientation": "vertical"},
            {"x": 510, "y": 20, "orientation": "vertical"},

            # Pas 2 (Drugi - 4 zajęte miejsca + 1 wolne docelowe pod x: 450)
            {"x": 270, "y": 210, "orientation": "vertical"},
            {"x": 330, "y": 210, "orientation": "vertical"},
            {"x": 390, "y": 210, "orientation": "vertical"},
            {"x": 510, "y": 210, "orientation": "vertical"},

    
            # Pas 4 (Dolny - 5 zajętych miejsc obok pozycji startowej)
            {"x": 270, "y": 500, "orientation": "vertical"},
            {"x": 330, "y": 500, "orientation": "vertical"},
            {"x": 390, "y": 500, "orientation": "vertical"},
            {"x": 450, "y": 500, "orientation": "vertical"},
            {"x": 510, "y": 500, "orientation": "vertical"},
        ]
    },
    "map_4": {
        "start_pos": (90.0, 500.0, 0),  
        "target_spot": {"x": 390, "y": 150, "orientation": "horizontal"},
        "occupied_spots": [
            # Pas 1 (Górny - 5 zajętych miejsc)
            {"x": 160, "y": 50, "orientation": "vertical"},
            {"x": 230, "y": 50, "orientation": "vertical"},
            {"x": 300, "y": 50, "orientation": "vertical"},
            {"x": 370, "y": 50, "orientation": "vertical"},
            {"x": 440, "y": 50, "orientation": "vertical"},
            {"x": 510, "y": 50, "orientation": "vertical"},

            # Pas 2 (Drugi - z wolnym poziomym miejscem docelowym w środku)
            {"x": 160, "y": 150, "orientation": "vertical"},
            {"x": 230, "y": 150, "orientation": "vertical"},

            # Pas 3 (Trzeci)
            {"x": 160, "y": 250, "orientation": "vertical"},
            {"x": 230, "y": 250, "orientation": "vertical"},


            # Pas tych kolo docelowego
            {"x": 390, "y": 210, "orientation": "horizontal"},
            {"x": 390, "y": 270, "orientation": "horizontal"},
            {"x": 390, "y": 330, "orientation": "horizontal"},
            {"x": 390, "y": 390, "orientation": "horizontal"},
           
        ]
    },
    "map_5": {
        "start_pos": (170.0, 470.0, -1.5708),  
        "target_spot": {"x": 360, "y": 140, "orientation": "vertical"},
        "occupied_spots": [
            # Lewa kolumna (wzdłuż krawędzi)
            {"x": 20, "y": 30, "orientation": "vertical"},
            {"x": 20, "y": 140, "orientation": "vertical"},
            {"x": 20, "y": 250, "orientation": "vertical"},
            {"x": 20, "y": 360, "orientation": "vertical"},
            {"x": 20, "y": 470, "orientation": "vertical"},

            # Prawa kolumna (wzdłuż krawędzi)
            {"x": 520, "y": 30, "orientation": "vertical"},
            {"x": 520, "y": 140, "orientation": "vertical"},
            {"x": 520, "y": 250, "orientation": "vertical"},
            {"x": 520, "y": 360, "orientation": "vertical"},
            {"x": 520, "y": 470, "orientation": "vertical"},

            # Środkowy wyspowy blok - Górny rząd
            {"x": 240, "y": 30, "orientation": "vertical"},
            {"x": 300, "y": 30, "orientation": "vertical"},
            {"x": 360, "y": 30, "orientation": "vertical"},

            # Środkowy wyspowy blok - Drugi rząd 
            {"x": 240, "y": 140, "orientation": "vertical"},
            {"x": 300, "y": 140, "orientation": "vertical"},

            # Dolny rząd dolny
            {"x": 240, "y": 470, "orientation": "vertical"},
            {"x": 300, "y": 470, "orientation": "vertical"},
            {"x": 360, "y": 470, "orientation": "vertical"},

             # Dolny rząd górny 
            {"x": 240, "y": 360, "orientation": "vertical"},
            {"x": 300, "y": 360, "orientation": "vertical"},
            {"x": 360, "y": 360, "orientation": "vertical"},
        ]
    }
}

_store = None


def _as_float(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def map_dims(data):
    # do parametrow i ich limitow na suwakach
    car_size = round(min(SIZE_MAX, max(SIZE_MIN, _as_float(data.get("car_size", 1.0), 1.0))), 2)
    spot_size = round(min(SIZE_MAX, max(SIZE_MIN, _as_float(data.get("spot_size", 1.0), 1.0))), 2)
    obstacle_size = round(
        min(SIZE_MAX, max(SIZE_MIN, _as_float(data.get("obstacle_size", 1.0), 1.0))), 2
    )
    max_v = round(
        min(MAX_V_MAX, max(MAX_V_MIN, _as_float(data.get("max_v", DEFAULT_MAX_V), DEFAULT_MAX_V))),
        1,
    )
    return {
        "max_v": max_v,
        "car_size": car_size,
        "spot_size": spot_size,
        "obstacle_size": obstacle_size,
        "car_w": int(round(CAR_W * car_size)),
        "car_h": int(round(CAR_H * car_size)),
        "spot_w": int(round(SPOT_W * spot_size)),
        "spot_h": int(round(SPOT_H * spot_size)),
        "obstacle_w": int(round(SPOT_W * obstacle_size)),
        "obstacle_h": int(round(SPOT_H * obstacle_size)),
        "obstacle_car_w": int(round(CAR_W * obstacle_size)),
        "obstacle_car_h": int(round(CAR_H * obstacle_size)),
        "wheelbase": WHEELBASE * car_size,
        "rear": REAR * car_size,
        "obstacle_wheelbase": WHEELBASE * obstacle_size,
        "obstacle_rear": REAR * obstacle_size,
    }

# Ustawienia mapy
def _normalize_map(data):
    start = data["start_pos"]
    dims = map_dims(data)
    return {
        "start_pos": (float(start[0]), float(start[1]), float(start[2])),
        "target_spot": {
            "x": int(data["target_spot"]["x"]),
            "y": int(data["target_spot"]["y"]),
            "orientation": data["target_spot"].get("orientation", "vertical"),
        },
        "occupied_spots": [
            {
                "x": int(s["x"]),
                "y": int(s["y"]),
                "orientation": s.get("orientation", "vertical"),
            }
            for s in data.get("occupied_spots", [])
        ],
        "max_v": dims["max_v"],
        "car_size": dims["car_size"],
        "spot_size": dims["spot_size"],
        "obstacle_size": dims["obstacle_size"],
    }

# jsonowanie mapki
def _serialize_map(data):
    n = _normalize_map(data)
    return {
        "start_pos": list(n["start_pos"]),
        "target_spot": n["target_spot"],
        "occupied_spots": n["occupied_spots"],
        "max_v": n["max_v"],
        "car_size": n["car_size"],
        "spot_size": n["spot_size"],
        "obstacle_size": n["obstacle_size"],
    }

#Ładowanie mapy
def _load_store():
    global _store
    if _store is not None:
        return _store
    if os.path.isfile(STORE_PATH):
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            maps = raw.get("maps") if isinstance(raw, dict) and "maps" in raw else raw
            _store = {
                name: _normalize_map(data)
                for name, data in maps.items()
            }
            return _store
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass
    _store = {name: _normalize_map(data) for name, data in MAPS.items()}
    return _store


def _save_store():
    store = _load_store()
    payload = {name: _serialize_map(data) for name, data in store.items()}
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def get_all_maps():
    return _load_store()


def list_map_names():
    names = list(_load_store().keys())

    def sort_key(name):
        if name.startswith("map_"):
            suffix = name[4:]
            if suffix.isdigit():
                return (0, int(suffix))
        return (1, name)

    names.sort(key=sort_key)
    return names


def get_map(map_name):
    store = _load_store()
    if map_name not in store:
        raise KeyError(f"Nieznana mapa: {map_name}")
    return copy.deepcopy(store[map_name])


def save_map(map_name, data):
    store = _load_store()
    store[map_name] = _normalize_map(data)
    _save_store()
    return map_name


# Do zapisywania map z webu
def replace_all_maps(maps_by_name):
    global _store
    _store = {
        name: _normalize_map(data)
        for name, data in maps_by_name.items()
    }
    _save_store()
    return list_map_names()


def delete_map(map_name):
    store = _load_store()
    if map_name in store:
        del store[map_name]
        _save_store()
        return True
    return False


def next_map_name():
    existing = set(_load_store().keys())
    i = 1
    while f"map_{i}" in existing:
        i += 1
    return f"map_{i}"


def default_new_map():
    return {
        "start_pos": (90.0, 300.0, 0.0),
        "target_spot": {"x": 400, "y": 250, "orientation": "vertical"},
        "occupied_spots": [],
        "max_v": DEFAULT_MAX_V,
        "car_size": 1.0,
        "spot_size": 1.0,
        "obstacle_size": 1.0,
    }


def spot_size(orientation, width=None, height=None):
    w = SPOT_W if width is None else width
    h = SPOT_H if height is None else height
    if orientation == "vertical":
        return w, h
    return h, w


def load_map(map_name, env_ref, data=None):

    data = data if data is not None else get_map(map_name)
    spots = []
    obstacles = []

    def create_spot_and_car(spot_cfg, is_target=False):
        orient = spot_cfg.get("orientation", "vertical")
        if is_target:
            sw, sh = env_ref.spot_w, env_ref.spot_h
        else:
            sw, sh = env_ref.obstacle_w, env_ref.obstacle_h

        rear = float(getattr(env_ref, "obstacle_rear", REAR))
        axle_pad = int(round(2 * rear))

        if orient == "vertical":
            w, h = sw, sh
            theta = -math.pi / 2  # Nosem w górę
            axle_x = spot_cfg["x"] + (w // 2)
            axle_y = spot_cfg["y"] + h - axle_pad
        else:  # horizontal (parkowanie równoległe)
            w, h = sh, sw
            theta = 0.0  # Nosem w prawo (funkcja rysująca obróci auto do poziomu)
            axle_x = spot_cfg["x"] + axle_pad
            axle_y = spot_cfg["y"] + (h // 2)

        spot_obj = ParkingSpot(spot_cfg["x"], spot_cfg["y"], w, h, is_target=is_target)

        if is_target:
            return spot_obj, None

        car_w = int(getattr(env_ref, "obstacle_car_w", env_ref.car_w))
        car_h = int(getattr(env_ref, "obstacle_car_h", env_ref.car_h))
        wheelbase = float(getattr(env_ref, "obstacle_wheelbase", env_ref.wheelbase))
        car_obj = Car(
            axle_x, axle_y, car_w, car_h,
            color=(70, 70, 70), is_hollow=False, wheelbase=wheelbase,
            rear_axle_offset_y=rear,
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