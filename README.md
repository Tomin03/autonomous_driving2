# autonomous_driving2

Gra parkowania z modelem rowerowym, czujnikiem LiDAR i agentem SAC (1 Actor + 1 Q).

## Uruchomienie

```
pip install -r requirements.txt
python steering_logic.py
```

W menu klawisz **A** (albo przycisk Tryb) przełącza:

`GRAJ RECZNIE` → `AGENT SAC` → …

Klawisz `L` w grze włącza/wyłącza wizualizację wiązek LiDAR.

## Trening

```
python train_sac.py
python train_sac.py --timesteps 300000 --maps map_1 map_2
```

Model: `models/sac_parking_best.pt` (Actor + jedna sieć Q + target).
