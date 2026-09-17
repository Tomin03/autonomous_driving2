import math
from items import Car, ParkingSpot

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

def load_map(map_name, env_ref):

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