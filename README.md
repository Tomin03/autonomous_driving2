# autonomous_driving2

Gra parkowania z modelem rowerowym, czujnikiem LiDAR i agentem SAC (1 Actor + 1 Q).
Interfejs: FastAPI + JavaScript (canvas).

## Uruchomienie

```
pip install -r requirements.txt
python app.py
```

Otwórz w przeglądarce: [http://127.0.0.1:8000](http://127.0.0.1:8000)

W podglądzie agenta klawisz `L` włącza/wyłącza wizualizację wiązek LiDAR, `R` resetuje epizod, `ESC` wraca do kafelków.

## Trening

Trening można uruchomić z menu aplikacji albo z konsoli:

```
python train_sac.py
python train_sac.py --timesteps 300000 --maps map_1 map_2
```

Model: `models/sac_parking_best.pt` (Actor + jedna sieć Q + target).
