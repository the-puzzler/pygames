# TRON / Light-Cycles (Pygame, multi-bot)
# - Students implement: def bot(state) -> "L"|"R"|"S"
# - Add their functions to BOTS; the function names become player names
# - Run: uv run tron/main.py

import sys, math, random
import pygame

# ========== CONFIG ==========
GRID_W, GRID_H = 49, 49          # odd numbers keep a single center cell
CELL = 14                         # pixels per grid cell
FPS = 30                          # visual framerate (logic runs 1 step/frame)
TICKS_MAX = 5000                  # safety cap
WALL_MARGIN = 2                   # spawn in from walls
SEED = None                       # set to an int for reproducibility

# player colors (cycled)
PLAYER_COLORS = [
    (30,144,255),   # dodgerblue
    (255,69,0),     # orangered
    (50,205,50),    # limegreen
    (255,215,0),    # gold
    (147,112,219),  # mediumpurple
    (64,224,208),   # turquoise
    (255,105,180),  # hotpink
    (160,82,45),    # sienna
]

# ========== DIRECTIONS ==========
DIRS = ["E","N","W","S"]             # clockwise order
DELTA = {"E":(1,0), "N":(0,-1), "W":(-1,0), "S":(0,1)}
TURN_L = {"E":"N","N":"W","W":"S","S":"E"}
TURN_R = {"E":"S","S":"W","W":"N","N":"E"}

def in_bounds(x, y):
    return 0 <= x < GRID_W and 0 <= y < GRID_H

# ========== STUDENT STATE OBJECT ==========
class BotState:
    """
    Read-only info for student functions.

    Attributes:
      me_index: index of this bot
      pos: (gx, gy) current grid cell (0..GRID_W-1, 0..GRID_H-1)
      heading: one of "E","N","W","S"
      alive_count: number of living players
      others: list of ((gx,gy), alive_bool)
      bounds: (0, GRID_W-1, 0, GRID_H-1)
      sensors: dict of booleans: 'ahead_free', 'left_free', 'right_free'
    """
    __slots__ = ("me_index","pos","heading","alive_count","others","bounds","sensors")
    def __init__(self, me_index, pos, heading, alive_count, others, sensors):
        self.me_index = me_index
        self.pos = pos
        self.heading = heading
        self.alive_count = alive_count
        self.others = others
        self.bounds = (0, GRID_W-1, 0, GRID_H-1)
        self.sensors = sensors

# ========== SENSOR COMPUTATION ==========
def compute_sensors(heading, pos, occupied):
    gx, gy = pos
    left_h  = TURN_L[heading]
    right_h = TURN_R[heading]
    ahead_h = heading

    def free(h):
        dx, dy = DELTA[h]
        nx, ny = gx + dx, gy + dy
        return in_bounds(nx, ny) and ((nx, ny) not in occupied)

    return {
        "left_free":  free(left_h),
        "ahead_free": free(ahead_h),
        "right_free": free(right_h),
    }

# ========== START POSITIONS ==========
def evenly_spaced_starts(n):
    """Place players on a circle facing inward (grid coords)."""
    cx, cy = GRID_W//2, GRID_H//2
    # radius measured in cells
    r = min(GRID_W, GRID_H)//2 - WALL_MARGIN - 1
    spots = []
    for i in range(n):
        ang = (i / n) * 2*math.pi
        gx = int(round(cx + r * math.cos(ang)))
        gy = int(round(cy + r * math.sin(ang)))
        # face roughly toward center
        dx, dy = cx - gx, cy - gy
        if abs(dx) >= abs(dy):
            heading = "E" if dx > 0 else "W"
        else:
            heading = "S" if dy > 0 else "N"
        spots.append(((gx, gy), heading))
    return spots

# ========== DRAW HELPERS ==========
def draw_board(surface, board, colors):
    """board: dict[(x,y)] = player_index who owns the trail cell."""
    surface.fill((8, 10, 14))
    rect = pygame.Rect(0, 0, CELL, CELL)
    for (x, y), owner in board.items():
        rect.topleft = (x*CELL, y*CELL)
        pygame.draw.rect(surface, colors[owner], rect)

def draw_snakes(surface, heads, colors):
    """Draw head squares with a brighter outline."""
    for i, (x, y) in enumerate(heads):
        if x is None: continue
        rect = pygame.Rect(x*CELL, y*CELL, CELL, CELL)
        pygame.draw.rect(surface, colors[i], rect, width=2)

def draw_hud(hud_surface, names, alive):
    hud_surface.fill((0,0,0,0))  # transparent
    font = pygame.font.SysFont(None, 20)
    y = 6
    for i, name in enumerate(names):
        label = f"{name} {' ' if alive[i] else '✖'}"
        color = PLAYER_COLORS[i % len(PLAYER_COLORS)]
        pygame.draw.rect(hud_surface, color, pygame.Rect(8, y+2, 10, 10))
        img = font.render(label, True, (220,220,230))
        hud_surface.blit(img, (24, y))
        y += 18

# ========== GAME LOOP ==========
def run_match(bot_functions):
    if SEED is not None:
        random.seed(SEED)

    n = len(bot_functions)
    assert 2 <= n <= len(PLAYER_COLORS), f"Need 2..{len(PLAYER_COLORS)} bots"

    names = [fn.__name__ for fn in bot_functions]
    colors = [PLAYER_COLORS[i % len(PLAYER_COLORS)] for i in range(n)]

    pygame.init()
    W, H = GRID_W * CELL, GRID_H * CELL
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("TRON — Pygame")
    clock = pygame.time.Clock()

    # board/trails
    occupied = {}    # (x,y) -> owner index
    heads = [None]*n
    heading = [None]*n
    alive = [True]*n

    # place starts
    starts = evenly_spaced_starts(n)
    for i in range(n):
        (sx, sy), h = starts[i]
        heads[i] = (sx, sy)
        heading[i] = h
        occupied[(sx, sy)] = i  # starting cell is part of trail

    # HUD surface (names)
    hud = pygame.Surface((W, H), pygame.SRCALPHA)

    ticks = 0
    winner_indices = []

    while ticks < TICKS_MAX and sum(alive) > 1:
        ticks += 1
        # ----- events -----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        # ----- decisions (all see same board) -----
        decisions = [None]*n
        for i, bot in enumerate(bot_functions):
            if not alive[i]: continue
            sensors = compute_sensors(heading[i], heads[i], occupied)
            others = [(heads[j], alive[j]) for j in range(n)]
            state = BotState(i, heads[i], heading[i], sum(alive), others, sensors)
            try:
                mv = bot(state)
            except Exception:
                mv = "S"
            mv = (mv or "S").upper().strip()[:1]
            decisions[i] = mv if mv in ("L","R","S") else "S"

        # ----- plan moves -----
        next_head = [None]*n
        next_pos = [None]*n
        cell_targets = {}  # (x,y) -> [i,...] who try to enter
        for i in range(n):
            if not alive[i]: continue
            h2 = heading[i]
            if decisions[i] == "L": h2 = TURN_L[h2]
            elif decisions[i] == "R": h2 = TURN_R[h2]
            dx, dy = DELTA[h2]
            x, y = heads[i]
            nx, ny = x + dx, y + dy
            next_head[i] = h2
            next_pos[i] = (nx, ny)
            cell_targets.setdefault((nx, ny), []).append(i)

        # ----- resolve crashes -----
        crashed = set()
        # wall/trail hits
        for i in range(n):
            if not alive[i]: continue
            nx, ny = next_pos[i]
            if (not in_bounds(nx, ny)) or ((nx, ny) in occupied):
                crashed.add(i)
        # head-on same cell
        for cell, idxs in cell_targets.items():
            if len(idxs) >= 2:
                crashed.update(idxs)

        # ----- apply moves -----
        for i in range(n):
            if not alive[i]: continue
            if i in crashed:
                alive[i] = False
                continue
            heads[i] = next_pos[i]
            heading[i] = next_head[i]
            occupied[heads[i]] = i

        # ----- draw -----
        draw_board(screen, occupied, colors)
        draw_snakes(screen, heads, colors)
        draw_hud(hud, names, alive)
        screen.blit(hud, (0,0))
        pygame.display.flip()
        clock.tick(FPS)

    # result
    winner_indices = [i for i, a in enumerate(alive) if a]
    # one last draw with "WINNER" text
    draw_board(screen, occupied, colors)
    draw_snakes(screen, heads, colors)
    draw_hud(hud, names, alive)
    screen.blit(hud, (0,0))
    font = pygame.font.SysFont(None, 36)
    if len(winner_indices) == 1:
        txt = f"WINNER: {names[winner_indices[0]]}"
    else:
        txt = f"DRAW: {', '.join(names[i] for i in winner_indices)}"
    img = font.render(txt, True, (240,240,255))
    screen.blit(img, (20, 10))
    pygame.display.flip()

    # keep window until closed
    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)
        clock.tick(30)

# ========== EXAMPLE STUDENT BOTS ==========
# Students: return "L", "R", or "S".
def straight_then_left(state):
    s = state.sensors
    if s["ahead_free"]: return "S"
    return "L" if s["left_free"] else ("R" if s["right_free"] else "S")

def right_hand_rule(state):
    s = state.sensors
    if s["right_free"]: return "R"
    if s["ahead_free"]: return "S"
    if s["left_free"]:  return "L"
    return "R"

def left_hand_rule(state):
    s = state.sensors
    if s["left_free"]:  return "L"
    if s["ahead_free"]: return "S"
    if s["right_free"]: return "R"
    return "L"

def random_safe(state):
    s = state.sensors
    opts = []
    if s["left_free"]:  opts.append("L")
    if s["ahead_free"]: opts.append("S")
    if s["right_free"]: opts.append("R")
    return random.choice(opts) if opts else "S"

def avoid_center(state):
    (x,y) = state.pos
    cx, cy = GRID_W//2, GRID_H//2
    s = state.sensors
    if abs(x-cx) <= 3 and abs(y-cy) <= 3 and s["left_free"]:
        return "L"
    if s["ahead_free"]: return "S"
    return "R" if s["right_free"] else ("L" if s["left_free"] else "S")

# ========== REGISTER BOTS HERE ==========
BOTS = [
    straight_then_left,
    right_hand_rule,
    left_hand_rule,
    random_safe,
    avoid_center,
]

if __name__ == "__main__":
    run_match(BOTS)
