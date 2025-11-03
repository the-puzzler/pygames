import sys, math, random, time
import pygame

# ================== CONFIG ==================
WIDTH, HEIGHT = 1024, 600
FIELD_MARGIN = 80

# Slow the pacing to showcase animations better
STEP_TIME   = 1.0     # seconds between action points
ATTACK_TIME = 1.4     # seconds of attack animation
FPS = 60

BASE_WORKERS_PER_STEP = 10
HOUSE_WORKER_BONUS    = 3     # extra workers/house/step
HOUSE_COST            = 20    # workers
DEFENSE_COST          = 20    # workers
DEFENSE_MULT_STEP     = 1.0   # each defense increases attackers needed per defender by +1
DEFENSE_MULT_CAP      = 4.0   # max defenders advantage
SEED = None                   # set to an int for reproducibility

# Colors
GREEN  = (24, 120, 44)
BROWN  = (139, 69, 19)
PINK   = (255, 105, 180)
GREY   = (128, 128, 128)
WHITE  = (240, 240, 240)
BLACK  = (0, 0, 0)

# ================== MODEL ==================

class PlayerState:
    def __init__(self, name, side):
        self.name = name
        self.side = side  # "L" or "R"
        self.workers  = 20
        self.soldiers = 0
        self.houses   = 0
        self.defenses = 0
        self.attack_pct = 0.0  # persisted between steps

        self.base_x = FIELD_MARGIN if side=="L" else WIDTH - FIELD_MARGIN
        self.base_y = HEIGHT//2

        # Stable per-frame worker visuals (avoid jittery redraw)
        self._worker_positions = []  # list[(x,y)] capped to draw limit
        self._worker_vels = []       # list[(vx,vy)] for gentle wander
        self._worker_tasks = []      # list[{i, tx, ty, ttl}] temporary build tasks
        # Persistent placements for soldiers and houses
        self._soldier_positions = [] # list[(x,y)]
        self._house_positions = []   # list[(x,y)]

    # ----- Visual placement helpers -----
    def _side_bounds(self):
        if self.side == "L":
            return 20, WIDTH//2 - 80
        else:
            return WIDTH//2 + 80, WIDTH - 20

    def add_houses(self, n: int):
        if n <= 0:
            return []
        left, right = self._side_bounds()
        cx = self.base_x + (30 if self.side=="L" else -30)
        cy = self.base_y
        added = []
        for _ in range(n):
            # Try to place with min separation
            placed = False
            for _try in range(30):
                x = random.randint(min(cx-120, right-20), max(cx+120, left+20))
                y = random.randint(cy-120, cy+120)
                x = max(left+10, min(right-10, x))
                y = max(70, min(HEIGHT-70, y))
                ok = True
                for hx, hy in self._house_positions:
                    if (hx-x)**2 + (hy-y)**2 < 26*26:
                        ok = False; break
                if ok:
                    self._house_positions.append((x, y))
                    added.append((x, y))
                    placed = True
                    break
            if not placed:
                hx = cx + random.randint(-30,30)
                hy = cy + random.randint(-30,30)
                self._house_positions.append((hx, hy))
                added.append((hx, hy))
        return added

    def add_soldiers(self, n: int):
        if n <= 0:
            return
        # Place in a loose wedge in front of base with jitter
        direction = 1 if self.side=="L" else -1
        start_x = self.base_x + direction*14
        start_y = self.base_y
        cols = max(3, int(math.sqrt(max(1, len(self._soldier_positions)+n))))
        for i in range(n):
            row = (len(self._soldier_positions)+i) // cols
            col = (len(self._soldier_positions)+i) % cols
            ox = direction * (col*12 + random.uniform(-4.0, 4.0))
            oy = (row-2)*12 + random.uniform(-6.0, 6.0)
            self._soldier_positions.append((start_x + ox, start_y + oy))

    def pop_attacking_soldiers(self, n: int):
        send = min(n, len(self._soldier_positions))
        starts = self._soldier_positions[:send]
        self._soldier_positions = self._soldier_positions[send:]
        return starts

    def trim_soldiers(self, keep_count: int):
        if keep_count < len(self._soldier_positions):
            self._soldier_positions = self._soldier_positions[:keep_count]

    def get_defense_build_sites(self, n: int):
        # Generate plausible defense build sites near base as anchors
        sites = []
        direction = 1 if self.side=="L" else -1
        for i in range(n):
            offx = direction * random.randint(0, 30)
            offy = random.randint(-40, 40)
            sites.append((self.base_x + offx, self.base_y + offy))
        return sites

    def schedule_builders(self, sites, per_site=3, duration=1.0):
        if not sites or not self._worker_positions:
            return
        taken = {t['i'] for t in self._worker_tasks}
        for (tx, ty) in sites:
            # Pick nearest free workers
            dists = []
            for i, (x, y) in enumerate(self._worker_positions):
                if i in taken: continue
                d2 = (x-tx)**2 + (y-ty)**2
                dists.append((d2, i))
            dists.sort()
            for _, i in dists[:per_site]:
                self._worker_tasks.append({'i': i, 'tx': tx, 'ty': ty, 'ttl': duration})
                taken.add(i)

    @property
    def defense_mult(self):
        return min(1.0 + self.defenses * DEFENSE_MULT_STEP, DEFENSE_MULT_CAP)

    def spawn_workers(self):
        self.workers += BASE_WORKERS_PER_STEP + self.houses * HOUSE_WORKER_BONUS

# State object passed to bots
class BotView:
    __slots__ = ("step","me","opp","economy","costs")
    def __init__(self, step, me: PlayerState, opp: PlayerState):
        self.step = step
        self.me  = Simple(me.workers, me.soldiers, me.houses, me.defenses, me.attack_pct)
        self.opp = Simple(opp.workers, opp.soldiers, opp.houses, opp.defenses, opp.attack_pct)
        self.economy = Simple(BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, 0, 0, 0.0)
        self.costs   = Simple(HOUSE_COST, DEFENSE_COST, 0, 0, 0.0)

class Simple:
    def __init__(self, a,b,c,d,e):
        self.workers=a; self.soldiers=b; self.houses=c; self.defenses=d; self.attack_pct=e

# ================== COMBAT ==================

def resolve_attack_packet(attackers, defender_soldiers, defender_workers, defense_mult):
    """
    Attackers kill soldiers first. Needs ceil(defense_mult) attackers per defending soldier.
    Surplus attackers kill workers 1:1. Returns new (def_soldiers, def_workers).
    """
    if attackers <= 0:
        return defender_soldiers, defender_workers
    need = int(math.ceil(defense_mult))
    soldiers_killable = attackers // need
    killed_soldiers = min(defender_soldiers, soldiers_killable)
    attackers -= killed_soldiers * need
    defender_soldiers -= killed_soldiers

    killed_workers = min(defender_workers, attackers)
    defender_workers -= killed_workers
    return defender_soldiers, defender_workers

# ================== PYGAME VIEW ==================

def tri_points(cx, cy, size, facing_right=True):
    if facing_right:
        return [(cx+size, cy), (cx-size, cy-size), (cx-size, cy+size)]
    else:
        return [(cx-size, cy), (cx+size, cy-size), (cx+size, cy+size)]

def draw_base(surface, player: PlayerState, dt: float):
    # Houses: brown squares spread with stable positions
    size = 10
    if len(player._house_positions) != player.houses:
        if len(player._house_positions) < player.houses:
            player.add_houses(player.houses - len(player._house_positions))
        else:
            player._house_positions = player._house_positions[:player.houses]
    for (hx, hy) in player._house_positions:
        rect = pygame.Rect(int(hx - size//2), int(hy - size//2), size, size)
        pygame.draw.rect(surface, BROWN, rect)

    # Workers: pink dots, gentle continuous wandering around base
    wr = 4
    draw_cap = 60
    need = min(player.workers, draw_cap)
    # Ensure we have stable positions matching current shown worker count
    cx = player.base_x + (40 if player.side=="L" else -40)
    cy = player.base_y
    # Grow: append newcomers from off-screen edge; Shrink: truncate
    if len(player._worker_positions) < need:
        add = need - len(player._worker_positions)
        for _ in range(add):
            if player.side == "L":
                x = random.randint(-50, -10)
            else:
                x = random.randint(WIDTH+10, WIDTH+50)
            y = cy + random.randint(-120, 120)
            player._worker_positions.append((x, y))
            # Velocity aimed toward base area
            dx = cx - x; dy = cy - y
            dist = math.hypot(dx, dy) + 1e-6
            spd = random.uniform(30.0, 60.0)
            player._worker_vels.append((dx/dist*spd, dy/dist*spd))
    elif len(player._worker_positions) > need:
        player._worker_positions = player._worker_positions[:need]
        player._worker_vels = player._worker_vels[:need]
    # Update wandering within a tethered radius
    if need:
        cx = player.base_x + (40 if player.side=="L" else -40)
        cy = player.base_y
        radius = 110.0
        new_pos = []
        new_vel = []
        for (x, y), (vx, vy) in zip(player._worker_positions, player._worker_vels):
            # Light random drift and a soft pull toward center
            vx += random.uniform(-6.0, 6.0) * dt
            vy += random.uniform(-6.0, 6.0) * dt
            # If assigned to build task, steer to target
            # (match by index of current worker in list)
            # We will fill new arrays in the same order; safe to use enumeration index
            vx += (cx - x) * 0.6 * dt
            vy += (cy - y) * 0.6 * dt
            # Speed clamp
            speed = math.hypot(vx, vy)
            max_s = 26.0
            if speed > max_s:
                scale = max_s / (speed + 1e-6)
                vx *= scale; vy *= scale
            # Integrate
            nx = x + vx * dt
            ny = y + vy * dt
            # Keep inside side bounds and a large radius around base
            left, right = player._side_bounds()
            nx = max(left+10, min(right-10, nx))
            ny = max(60, min(HEIGHT-60, ny))
            dx = nx - cx; dy = ny - cy
            d = math.hypot(dx, dy)
            if d > radius:
                nx = cx + dx * (radius / d)
                ny = cy + dy * (radius / d)
                vx *= -0.4; vy *= -0.4
            new_pos.append((int(nx), int(ny)))
            new_vel.append((vx, vy))
        player._worker_positions = new_pos
        player._worker_vels = new_vel
        # Update build tasks steering and lifetimes (do after arrays rebuilt)
        # Recompute nearest index mapping in case list size changed
        alive_tasks = []
        for t in player._worker_tasks:
            i = t['i']
            if i < 0 or i >= len(player._worker_positions):
                continue
            x, y = player._worker_positions[i]
            tx, ty = t['tx'], t['ty']
            # Steer this worker strongly toward target
            dx = tx - x; dy = ty - y
            dist = math.hypot(dx, dy) + 1e-6
            spd = 40.0
            vx = dx/dist*spd
            vy = dy/dist*spd
            player._worker_vels[i] = (vx, vy)
            # If close, hold position
            if dist < 6:
                player._worker_positions[i] = (int(tx), int(ty))
                player._worker_vels[i] = (0.0, 0.0)
            t['ttl'] -= dt
            if t['ttl'] > 0:
                alive_tasks.append(t)
        player._worker_tasks = alive_tasks
    for (x, y) in player._worker_positions:
        pygame.draw.circle(surface, PINK, (x, y), wr)

    # Soldiers: grey triangles from stored garrison positions
    if len(player._soldier_positions) != player.soldiers:
        if len(player._soldier_positions) > player.soldiers:
            player._soldier_positions = player._soldier_positions[:player.soldiers]
        else:
            player.add_soldiers(player.soldiers - len(player._soldier_positions))
    draw_n = min(player.soldiers, 120)
    for i in range(draw_n):
        cx, cy = player._soldier_positions[i]
        pts = tri_points(int(cx), int(cy), 5, facing_right=(player.side=="L"))
        pygame.draw.polygon(surface, GREY, pts)

    # Defense multiplier text
    font = pygame.font.SysFont(None, 18)
    shield = font.render(f"DEF x{player.defense_mult:.0f}", True, WHITE)
    if player.side == "L":
        surface.blit(shield, (player.base_x - 20, player.base_y + 90))
    else:
        w = shield.get_width()
        surface.blit(shield, (player.base_x - w + 20, player.base_y + 90))

def draw_field(surface):
    surface.fill(GREEN)
    # midline
    pygame.draw.line(surface, (32,90,32), (WIDTH//2, 40), (WIDTH//2, HEIGHT-40), 2)
    # end zones
    pygame.draw.rect(surface, (20,70,20), pygame.Rect(20, 40, FIELD_MARGIN-40, HEIGHT-80))
    pygame.draw.rect(surface, (20,70,20), pygame.Rect(WIDTH-FIELD_MARGIN+20, 40, FIELD_MARGIN-40, HEIGHT-80))

def draw_hud(surface, p1: PlayerState, p2: PlayerState, phase, step_time_left, step_nr):
    font = pygame.font.SysFont(None, 22)

    def panel(player, x, align_left=True):
        y = 8
        s = [
            f"{player.name}",
            f"Workers: {player.workers}   Soldiers: {player.soldiers}",
            f"Houses: {player.houses} (+{BASE_WORKERS_PER_STEP + player.houses*HOUSE_WORKER_BONUS}/step)",
            f"Attack%: {int(player.attack_pct*100)}",
            f"Defenses: {player.defenses} (x{player.defense_mult:.0f})"
        ]
        for line in s:
            img = font.render(line, True, WHITE)
            if align_left:
                surface.blit(img, (x, y)); y += 20
            else:
                surface.blit(img, (x - img.get_width(), y)); y += 20

    panel(p1, 10, True)                     # << fixed: no extra surface arg
    panel(p2, WIDTH-10, False)

    # Phase/timer
    phase_text = f"Step {step_nr} — {phase}  {step_time_left:0.1f}s"
    img = font.render(phase_text, True, WHITE)
    surface.blit(img, (WIDTH//2 - img.get_width()//2, 8))

def spawn_attack_units(p: PlayerState, count, defender: PlayerState, both_attacking, starts):
    """Create visual 'unit sprites' for the attack phase.
    Units are spawned in a loose formation and assigned a target so that
    they visually make contact (midfield if both attack, enemy base if not).
    Each unit's speed is set to reach its target by ATTACK_TIME for smoothness.
    """
    units = []
    if count <= 0:
        return units
    direction = 1 if p.side=="L" else -1
    # Use actual garrison starts for more natural movement out of formation
    for (sx, sy) in starts:
        jitter_x = random.uniform(-3.0, 3.0)
        jitter_y = random.uniform(-3.0, 3.0)
        x = sx + jitter_x
        y = sy + jitter_y
        units.append({"x": x, "y": y, "sx": x, "sy": y, "dir": direction})
    # Targets: midfield if both attack; otherwise chase defenders near their workers
    if both_attacking:
        target_x = WIDTH//2
        lane_spacing = 12
        lanes = max(4, int(math.sqrt(max(1, len(units)))))
        base_lane_y = p.base_y - (lanes*lane_spacing)//2
        for i, u in enumerate(units):
            lane = i % lanes
            ty = base_lane_y + lane*lane_spacing + random.uniform(-6.0, 6.0)
            u["tx"] = target_x
            u["ty"] = ty
            # Curved path: control point halfway with a lateral arc
            midx = (u["sx"] + u["tx"]) * 0.5
            arc = ( -1 if p.side=="L" else 1 ) * random.uniform(18.0, 42.0)
            midy = (u["sy"] + ty) * 0.5 + arc
            u["cx"], u["cy"] = midx, midy
    else:
        # Drive into enemy base edge, pick y near a defender worker for contact
        worker_targets = defender._worker_positions or [(defender.base_x, defender.base_y)]
        for i, u in enumerate(units):
            tx = defender.base_x - 44 if p.side=="L" else defender.base_x + 44
            wx, wy = worker_targets[i % len(worker_targets)]
            ty = wy + random.uniform(-8.0, 8.0)
            u["tx"], u["ty"] = tx, ty
            # Control point: 40% along x, slight outward arc
            t_ctrl = 0.4 if p.side=="L" else 0.6
            cx = u["sx"] + (tx - u["sx"]) * t_ctrl
            cy = u["sy"] + (ty - u["sy"]) * t_ctrl + ( -1 if p.side=="L" else 1 ) * random.uniform(16.0, 36.0)
            u["cx"], u["cy"] = cx, cy
    return units

def animate_attack(screen, clock, p1_units, p2_units, p1, p2, step_nr, cont_L=0, cont_R=0):
    """Animate units following curved paths for ATTACK_TIME seconds.
    If both sides attacked, survivors continue on to enemy workers for a second phase.
    """
    t0 = time.time()
    while time.time() - t0 < ATTACK_TIME:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        dt = clock.tick(FPS) / 1000.0
        # move units along quadratic Bezier paths based on elapsed fraction
        elapsed = time.time() - t0
        t = max(0.0, min(1.0, elapsed / ATTACK_TIME))
        def bezier(p0, c, p1, t):
            it = 1.0 - t
            return (
                it*it*p0[0] + 2*it*t*c[0] + t*t*p1[0],
                it*it*p0[1] + 2*it*t*c[1] + t*t*p1[1],
            )
        for u in p1_units:
            bx, by = bezier((u["sx"], u["sy"]), (u["cx"], u["cy"]), (u["tx"], u["ty"]), t)
            u["x"], u["y"] = bx, by
        for u in p2_units:
            bx, by = bezier((u["sx"], u["sy"]), (u["cx"], u["cy"]), (u["tx"], u["ty"]), t)
            u["x"], u["y"] = bx, by

        # draw
        draw_field(screen)
        draw_base(screen, p1, dt)
        draw_base(screen, p2, dt)

        # defensive line (if one side not attacking)
        if len(p1_units)==0:
            x = WIDTH//2 - 80
            pygame.draw.line(screen, GREY, (x, 120), (x, HEIGHT-120), 3)
        if len(p2_units)==0:
            x = WIDTH//2 + 80
            pygame.draw.line(screen, GREY, (x, 120), (x, HEIGHT-120), 3)

        # units
        for u in p1_units:
            pts = tri_points(int(u["x"]), int(u["y"]), 6, facing_right=True)
            pygame.draw.polygon(screen, GREY, pts)
        for u in p2_units:
            pts = tri_points(int(u["x"]), int(u["y"]), 6, facing_right=False)
            pygame.draw.polygon(screen, GREY, pts)

        rem = max(0.0, ATTACK_TIME - (time.time()-t0))
        draw_hud(screen, p1, p2, "ATTACK", rem, step_nr)
        pygame.display.flip()

    # Second phase: winners push into enemy base to attack workers
    if (len(p1_units) > 0 and len(p2_units) > 0) and (cont_L > 0 or cont_R > 0):
        # Assign new targets for survivors
        def assign_phase2(units, defender, count, side_left):
            work_targets = defender._worker_positions or [(defender.base_x, defender.base_y)]
            survivors = []
            for i in range(min(count, len(units))):
                u = units[i]
                sx2, sy2 = u["x"], u["y"]
                wx, wy = work_targets[i % len(work_targets)]
                tx2 = defender.base_x - 40 if side_left else defender.base_x + 40
                ty2 = wy + random.uniform(-10.0, 10.0)
                # control point pulls outward slightly
                t_ctrl = 0.6 if side_left else 0.4
                cx2 = sx2 + (tx2 - sx2) * t_ctrl
                cy2 = sy2 + (ty2 - sy2) * t_ctrl + ( -1 if side_left else 1 ) * random.uniform(14.0, 28.0)
                survivors.append({
                    'sx': sx2, 'sy': sy2, 'cx': cx2, 'cy': cy2, 'tx': tx2, 'ty': ty2,
                    'facing_right': side_left
                })
            return survivors

        surv_L = assign_phase2(p1_units, p2, cont_L, True)
        surv_R = assign_phase2(p2_units, p1, cont_R, False)
        EXTRA = 1.0
        t1 = time.time()
        while time.time() - t1 < EXTRA:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
            dt = clock.tick(FPS) / 1000.0
            elapsed = time.time() - t1
            t = max(0.0, min(1.0, elapsed / EXTRA))
            def bezier(p0, c, p1p, tt):
                it = 1.0 - tt
                return (
                    it*it*p0[0] + 2*it*tt*c[0] + tt*tt*p1p[0],
                    it*it*p0[1] + 2*it*tt*c[1] + tt*tt*p1p[1],
                )
            draw_field(screen)
            draw_base(screen, p1, dt)
            draw_base(screen, p2, dt)
            # defensive lines as before if one side had none initially
            if len(p1_units)==0:
                x = WIDTH//2 - 80
                pygame.draw.line(screen, GREY, (x, 120), (x, HEIGHT-120), 3)
            if len(p2_units)==0:
                x = WIDTH//2 + 80
                pygame.draw.line(screen, GREY, (x, 120), (x, HEIGHT-120), 3)
            # Draw only survivors in phase 2
            for s in surv_L:
                x, y = bezier((s['sx'], s['sy']), (s['cx'], s['cy']), (s['tx'], s['ty']), t)
                pts = tri_points(int(x), int(y), 6, facing_right=True)
                pygame.draw.polygon(screen, GREY, pts)
            for s in surv_R:
                x, y = bezier((s['sx'], s['sy']), (s['cx'], s['cy']), (s['tx'], s['ty']), t)
                pts = tri_points(int(x), int(y), 6, facing_right=False)
                pygame.draw.polygon(screen, GREY, pts)
            rem = max(0.0, EXTRA - (time.time()-t1))
            draw_hud(screen, p1, p2, "PUSH", rem, step_nr)
            pygame.display.flip()

# ================== BOT ADAPTER ==================

def sanitize_action(act_dict, prev_attack_pct, workers_available):
    """Clamp bot outputs to valid ranges and affordability."""
    # Defaults
    convert = int(max(0, act_dict.get("convert", 0)))
    build_h = int(max(0, act_dict.get("build_houses", 0)))
    build_d = int(max(0, act_dict.get("build_defenses", 0)))
    attack_pct = act_dict.get("attack_pct", prev_attack_pct)
    attack_pct = max(0.0, min(1.0, float(attack_pct)))

    # Pay costs in this order: houses, defenses, convert (you can tweak)
    cost = build_h*HOUSE_COST + build_d*DEFENSE_COST
    if cost > workers_available:
        # scale down builds to fit budget
        can_h = min(build_h, workers_available // HOUSE_COST)
        workers_available -= can_h * HOUSE_COST
        can_d = min(build_d, workers_available // DEFENSE_COST)
        workers_available -= can_d * DEFENSE_COST
        build_h, build_d = can_h, can_d
    else:
        workers_available -= cost

    convert = min(convert, workers_available)
    return {"convert": convert, "build_houses": build_h, "build_defenses": build_d, "attack_pct": attack_pct}

# ================== GAME LOOP ==================

def run_game(BOT_L, BOT_R):
    if SEED is not None:
        random.seed(SEED)

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Workers & War — 1v1 (Bots)")
    clock = pygame.time.Clock()

    p1 = PlayerState(BOT_L.__name__, "L")
    p2 = PlayerState(BOT_R.__name__, "R")
    step_nr = 1

    # pacing
    phase = "PLAN"
    step_start = time.time()

    while True:
        now = time.time()
        dt = clock.tick(FPS) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        if phase == "PLAN":
            # draw current state during planning delay (workers still wander)
            draw_field(screen)
            draw_base(screen, p1, dt)
            draw_base(screen, p2, dt)
            rem = max(0.0, STEP_TIME - (now - step_start))
            draw_hud(screen, p1, p2, "PLAN", rem, step_nr)
            pygame.display.flip()

            if now - step_start >= STEP_TIME:
                # Step economics
                p1.spawn_workers(); p2.spawn_workers()

                # Query bots for actions
                state_L = BotView(step_nr, p1, p2)
                state_R = BotView(step_nr, p2, p1)
                raw_L = BOT_L(state_L) or {}
                raw_R = BOT_R(state_R) or {}
                act_L = sanitize_action(raw_L, p1.attack_pct, p1.workers)
                act_R = sanitize_action(raw_R, p2.attack_pct, p2.workers)

                # Apply builds/converts simultaneously
                # Houses
                can_h_L = min(act_L["build_houses"], p1.workers // HOUSE_COST)
                can_h_R = min(act_R["build_houses"], p2.workers // HOUSE_COST)
                p1.houses += can_h_L; p1.workers -= can_h_L*HOUSE_COST; new_sites_L = p1.add_houses(can_h_L)
                p2.houses += can_h_R; p2.workers -= can_h_R*HOUSE_COST; new_sites_R = p2.add_houses(can_h_R)
                # Send nearby workers to build houses
                if new_sites_L: p1.schedule_builders(new_sites_L, per_site=3, duration=1.2)
                if new_sites_R: p2.schedule_builders(new_sites_R, per_site=3, duration=1.2)
                # Defenses
                can_d_L = min(act_L["build_defenses"], p1.workers // DEFENSE_COST)
                can_d_R = min(act_R["build_defenses"], p2.workers // DEFENSE_COST)
                p1.defenses += can_d_L; p1.workers -= can_d_L*DEFENSE_COST
                p2.defenses += can_d_R; p2.workers -= can_d_R*DEFENSE_COST
                if can_d_L:
                    p1.schedule_builders(p1.get_defense_build_sites(can_d_L), per_site=2, duration=0.9)
                if can_d_R:
                    p2.schedule_builders(p2.get_defense_build_sites(can_d_R), per_site=2, duration=0.9)
                # Convert workers -> soldiers
                conv_L = min(act_L["convert"], p1.workers)
                conv_R = min(act_R["convert"], p2.workers)
                p1.soldiers += conv_L; p1.workers -= conv_L; p1.add_soldiers(conv_L)
                p2.soldiers += conv_R; p2.workers -= conv_R; p2.add_soldiers(conv_R)

                # Attack % update persists
                p1.attack_pct = act_L["attack_pct"]
                p2.attack_pct = act_R["attack_pct"]

                # Form attack packets (simultaneous)
                send_L = int(p1.soldiers * p1.attack_pct)
                send_R = int(p2.soldiers * p2.attack_pct)
                p1.soldiers -= send_L
                p2.soldiers -= send_R
                starts_L = p1.pop_attacking_soldiers(send_L)
                starts_R = p2.pop_attacking_soldiers(send_R)

                # Resolve casualties (simultaneous vs start-of-attack defender pools)
                pre_R_w = p2.workers; pre_L_w = p1.workers
                new_R_s, new_R_w = resolve_attack_packet(send_L, p2.soldiers, p2.workers, p2.defense_mult)
                new_L_s, new_L_w = resolve_attack_packet(send_R, p1.soldiers, p1.workers, p1.defense_mult)
                p2.soldiers, p2.workers = new_R_s, new_R_w
                p1.soldiers, p1.workers = new_L_s, new_L_w
                p2.trim_soldiers(p2.soldiers)
                p1.trim_soldiers(p1.soldiers)
                killed_R_workers = max(0, pre_R_w - new_R_w)
                killed_L_workers = max(0, pre_L_w - new_L_w)

                # Prepare animation units
                u_L = spawn_attack_units(p1, send_L, p2, both_attacking=(send_R>0), starts=starts_L)
                u_R = spawn_attack_units(p2, send_R, p1, both_attacking=(send_L>0), starts=starts_R)
                cont_L = killed_R_workers if (send_L>0 and send_R>0) else 0
                cont_R = killed_L_workers if (send_L>0 and send_R>0) else 0

                phase = "ATTACK"
                step_start = time.time()

        elif phase == "ATTACK":
            animate_attack(screen, clock, u_L, u_R, p1, p2, step_nr, cont_L, cont_R)

            # Win check
            left_dead  = (p1.soldiers <= 0 and p1.workers <= 0)
            right_dead = (p2.soldiers <= 0 and p2.workers <= 0)

            # Draw final or proceed
            if left_dead or right_dead:
                draw_field(screen)
                draw_base(screen, p1, 0.0)
                draw_base(screen, p2, 0.0)
                draw_hud(screen, p1, p2, "END", 0.0, step_nr)
                big = pygame.font.SysFont(None, 56)
                if left_dead and right_dead:
                    txt = "DRAW!"
                elif right_dead:
                    txt = f"{p1.name} WINS!"
                else:
                    txt = f"{p2.name} WINS!"
                img = big.render(txt, True, WHITE)
                screen.blit(img, (WIDTH//2 - img.get_width()//2, HEIGHT//2 - 30))
                pygame.display.flip()
                # Wait for close
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                            pygame.quit(); sys.exit(0)
                    pygame.time.wait(10)

            # next step
            phase = "PLAN"
            step_start = time.time()
            step_nr += 1

# ================== SAMPLE BOTS ==================

def greedy_rush(state):
    """Convert hard early and attack at 50%."""
    w = state.me.workers
    return {"convert": max(0, w - 20), "build_houses": 0, "build_defenses": 0, "attack_pct": 0.5}

def boom_econ(state):
    """Build houses until 5, low attacks early, then ramp up."""
    me, opp = state.me, state.opp
    attack = 0.1 if state.step < 10 else 0.35
    houses = 1 if me.houses < 5 and me.workers >= HOUSE_COST else 0
    convert = max(0, me.workers - houses*HOUSE_COST) // 2
    return {"convert": convert, "build_houses": houses, "build_defenses": 0, "attack_pct": attack}

def turtle_defense(state):
    """Stack defenses to x3, small counter-attacks."""
    me = state.me
    want_def = 3
    build_d = 1 if me.defenses < want_def and me.workers >= DEFENSE_COST else 0
    convert = max(0, me.workers - build_d*DEFENSE_COST) // 3
    return {"convert": convert, "build_houses": 0, "build_defenses": build_d, "attack_pct": 0.2}

def adaptive_match(state):
    """If enemy soldiers >> mine, defend; else push."""
    me, opp = state.me, state.opp
    pressure = 0.45 if me.soldiers >= opp.soldiers else 0.2
    build_h = 1 if me.houses < 3 and me.workers >= HOUSE_COST else 0
    remaining = me.workers - build_h*HOUSE_COST
    build_d = 1 if (opp.soldiers > me.soldiers*1.3) and remaining >= DEFENSE_COST else 0
    remaining -= build_d*DEFENSE_COST
    convert = max(0, remaining - 10)  # keep a small worker float
    return {"convert": convert, "build_houses": build_h, "build_defenses": build_d, "attack_pct": pressure}

# ================== RUN ==================
if __name__ == "__main__":
    # Pick any two bots here:
    run_game(greedy_rush, adaptive_match)
