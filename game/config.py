import math

# ================== CONFIG ==================
WIDTH, HEIGHT = 1024, 600
FIELD_MARGIN = 80

# Slow the pacing to showcase animations better
STEP_TIME   = 0.5     # seconds between action points
ATTACK_TIME = 0.7     # seconds of attack animation
FPS = 60

BASE_WORKERS_PER_STEP = 10
WORKER_BONUS = 1.05
HOUSE_WORKER_BONUS    = 3     # extra workers/house/step
HOUSE_COST            = 20    # workers
DEFENSE_COST          = 20    # workers
DEFENSE_HEALTH     = 30

SEED = None                   # set to an int for reproducibility


# Colors
GREEN  = (24, 120, 44)
BROWN  = (139, 69, 19)
PINK   = (255, 105, 180)
GREY   = (128, 128, 128)
WHITE  = (240, 240, 240)
BLACK  = (0, 0, 0)
