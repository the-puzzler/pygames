import math

# ================== CONFIG ==================
# Logical base resolution
BASE_WIDTH, BASE_HEIGHT = 1024, 600
FIELD_MARGIN_BASE = 80

# Slow the pacing to showcase animations better
STEP_TIME   = 0.25     # seconds between action points
ATTACK_TIME = 0.75     # seconds of attack animation
FPS = 60

BASE_WORKERS_PER_STEP = 10
WORKER_BONUS = 1.05
HOUSE_WORKER_BONUS    = 3     # extra workers/house/step
HOUSE_COST            = 20    # workers
DEFENSE_COST          = 20    # workers
DEFENSE_HEALTH     = 30

SEED = None                   # set to an int for reproducibility

# Global time scale (affects PLAN pacing and ATTACK animations)
# 1.0 = real time, 2.0 = 2x faster
TIME_SCALE = 1

# Window scale (applies to resolution and sizes)
# 1.0 = native size; e.g., 1.5 = 150% window; larger scene and sprites
WINDOW_SCALE = 2

# Derived scaled resolution and margins
WIDTH  = int(BASE_WIDTH  * WINDOW_SCALE)
HEIGHT = int(BASE_HEIGHT * WINDOW_SCALE)
FIELD_MARGIN = int(FIELD_MARGIN_BASE * WINDOW_SCALE)


# Colors
# Slightly lighter field green
GREEN  = (54, 150, 74)
BROWN  = (139, 69, 19)
PINK   = (255, 105, 180)
GREY   = (128, 128, 128)
WHITE  = (240, 240, 240)
BLACK  = (0, 0, 0)

# Sprite target sizes (in pixels, height-based; images are scaled preserving aspect)
WORKER_SIZE  = 8
SOLDIER_SIZE = 12
HOUSE_SIZE   = 24
TOWER_SIZE   = 24
GRASS_SIZE   = 10
TREE_SIZE    = 18
BOULDER_SIZE = 16
