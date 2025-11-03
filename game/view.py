import math, random, os, time
import pygame
from .config import WIDTH, HEIGHT, FIELD_MARGIN, GREEN, BROWN, PINK, GREY, WHITE, BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, WORKER_SIZE, SOLDIER_SIZE, HOUSE_SIZE, TOWER_SIZE, GRASS_SIZE, TREE_SIZE, BOULDER_SIZE, SEED, DEFENSE_HEALTH, WINDOW_SCALE

# Dedicated RNG for visuals to avoid influencing gameplay RNG under TIME_SCALE
VIS_RNG = random.Random(SEED if SEED is not None else 13579)


def tri_points(cx, cy, size, facing_right=True):
    if facing_right:
        return [(cx+size, cy), (cx-size, cy-size), (cx-size, cy+size)]
    else:
        return [(cx-size, cy), (cx+size, cy-size), (cx+size, cy+size)]

# Sprite loading and orientation
_IMG_CACHE = {}

def _load_base(name):
    key = ("base", name)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    path = os.path.join(os.path.dirname(__file__), name)
    img = pygame.image.load(path).convert_alpha()
    _IMG_CACHE[key] = img
    return img

def get_image(kind: str, side: str):
    """Return oriented image for kind in {worker,soldier,house,tower} and side 'L' or 'R'."""
    filename = {
        'worker': 'worker.png',
        'soldier': 'soldier.png',
        'house': 'house.png',
        'tower': 'tower.png',
        'grass': 'grass.png',
        'tree':  'tree.png',
        'boulder': 'boulder.png',
    }[kind]
    key = (kind, side)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    base = _load_base(filename)
    # Scale to target size (height-based)
    base_h = {
        'worker': WORKER_SIZE,
        'soldier': SOLDIER_SIZE,
        'house': HOUSE_SIZE,
        'tower': TOWER_SIZE,
        'grass': GRASS_SIZE,
        'tree':  TREE_SIZE,
        'boulder': BOULDER_SIZE,
    }[kind]
    target_h = max(1, int(round(base_h * WINDOW_SCALE)))
    if base.get_height() != target_h:
        aspect = base.get_width() / max(1, base.get_height())
        target_w = max(1, int(round(target_h * aspect)))
        base_scaled = pygame.transform.smoothscale(base, (target_w, target_h))
    else:
        base_scaled = base
    if side == 'R' and kind in ('worker','soldier','house','tower'):
        img = pygame.transform.flip(base_scaled, True, False)
    else:
        img = base_scaled
    _IMG_CACHE[key] = img
    return img


def draw_base(surface, player, dt: float):
    # Defenses: draw towers at stored positions (dicts: x,y,hp), with spawn scale-in
    player.defenses = len(player._defense_positions)
    tower_img = get_image('tower', player.side)
    tw, th = tower_img.get_width(), tower_img.get_height()
    now = time.time()
    for t in player._defense_positions:
        tx, ty = int(t['x']), int(t['y'])
        # Check recent spawn for scale-in (0.15s from 0.9->1.0)
        scale = 1.0
        if getattr(player, '_spawn_bursts', None):
            for b in player._spawn_bursts:
                if abs(b.get('x',0)-tx) < 8 and abs(b.get('y',0)-ty) < 8:
                    start = b.get('until', now) - 0.6
                    prog = max(0.0, min(1.0, (now - start) / 0.15))
                    scale = 0.9 + 0.1 * prog
                    break
        if scale != 1.0:
            sw = max(1, int(tw * scale)); sh = max(1, int(th * scale))
            simg = pygame.transform.smoothscale(tower_img, (sw, sh))
            surface.blit(simg, (tx - sw//2, ty - sh//2))
        else:
            surface.blit(tower_img, (tx - tw//2, ty - th//2))
        # Small HP bar above tower
        try:
            hp = max(0, min(DEFENSE_HEALTH, int(t.get('hp', DEFENSE_HEALTH))))
        except Exception:
            hp = DEFENSE_HEALTH
        ratio = hp / max(1, DEFENSE_HEALTH)
        bar_w = max(12, tw)
        bar_h = 3
        bx = tx - bar_w//2
        by = ty - th//2 - 6
        # background
        pygame.draw.rect(surface, (40,40,40), pygame.Rect(bx, by, bar_w, bar_h))
        # foreground color from red->yellow->green
        if ratio < 0.33:
            col = (200, 40, 40)
        elif ratio < 0.66:
            col = (220, 180, 40)
        else:
            col = (50, 200, 70)
        pygame.draw.rect(surface, col, pygame.Rect(bx, by, int(bar_w * ratio), bar_h))

    # Building spawn bursts (same flavor as tower destruction rings)
    if getattr(player, '_spawn_bursts', None):
        now = time.time()
        keep = []
        for b in player._spawn_bursts:
            tleft = b.get('until', 0) - now
            if tleft <= 0:
                continue
            bx, by = b.get('x', 0), b.get('y', 0)
            prog = 1.0 - (tleft / max(1e-6, (b.get('until', now) - (b.get('until', now) - 0.6))))
            for k in (0.0, 0.35):
                p = (prog + k) % 1.0
                radius = 6 + int(26 * p)
                alpha = int(max(0, 180 * (1.0 - p)))
                if alpha <= 0:
                    continue
                col = (255, 200, 60, alpha)
                ring = pygame.Surface((radius*2+2, radius*2+2), pygame.SRCALPHA)
                pygame.draw.circle(ring, col, (radius+1, radius+1), radius, width=2)
                surface.blit(ring, (int(bx) - radius - 1, int(by) - radius - 1))
            keep.append(b)
        player._spawn_bursts = keep

    # Workers: pink dots, gentle continuous wandering around base
    wr = 4
    # Keep consuming workers visible until they finish/exit, so count them too
    consuming = sum(1 for t in getattr(player, '_worker_tasks', []) if t.get('consume'))
    need = player.workers + consuming
    # Ensure we have stable positions matching current shown worker count
    cx = player.base_x + (40 if player.side=="L" else -40)
    cy = player.base_y
    # Grow new workers from off-screen; shrink by truncating
    if len(player._worker_positions) < need:
        add = need - len(player._worker_positions)
        for _ in range(add):
            # In multi-player, allow ingress from nearest edge to the base area
            if hasattr(player, '_multi_ingress') and player._multi_ingress:
                bx, by = player.base_x, player.base_y
                d_left = bx
                d_right = WIDTH - bx
                d_top = by
                d_bottom = HEIGHT - by
                dm = min(d_left, d_right, d_top, d_bottom)
                if dm == d_left:
                    x = VIS_RNG.randint(-60, -20)
                    y = int(by) + VIS_RNG.randint(-140, 140)
                elif dm == d_right:
                    x = VIS_RNG.randint(WIDTH+20, WIDTH+60)
                    y = int(by) + VIS_RNG.randint(-140, 140)
                elif dm == d_top:
                    x = int(bx) + VIS_RNG.randint(-140, 140)
                    y = VIS_RNG.randint(-50, -20)
                else:
                    x = int(bx) + VIS_RNG.randint(-140, 140)
                    y = VIS_RNG.randint(HEIGHT+20, HEIGHT+60)
            else:
                if player.side == "L":
                    x = VIS_RNG.randint(-50, -10)
                else:
                    x = VIS_RNG.randint(WIDTH+10, WIDTH+50)
                # Ingress from around base Y but allow ~80% window height spread
                y = int(cy + VIS_RNG.randint(int(-HEIGHT*0.40), int(HEIGHT*0.40)))
            player._worker_positions.append((float(x), float(y)))
            dx = cx - x; dy = cy - y
            dist = math.hypot(dx, dy) + 1e-6
            spd = VIS_RNG.uniform(120.0, 200.0)
            player._worker_vels.append((dx/dist*spd, dy/dist*spd))
    elif len(player._worker_positions) > need:
        # Avoid shrinking while there are consuming tasks to preserve identity illusion
        if consuming == 0:
            player._worker_positions = player._worker_positions[:need]
            player._worker_vels = player._worker_vels[:need]

    if need:
        # Rectangular roam area
        if getattr(player, '_multi_roam_tight', False):
            # Tight leash around base in multi-player mode
            roam_w = 220
            roam_h = 200
            left = max(20, int(player.base_x - roam_w//2))
            right = min(WIDTH-20, int(player.base_x + roam_w//2))
            top = max(40, int(player.base_y - roam_h//2))
            bottom = min(HEIGHT-40, int(player.base_y + roam_h//2))
        else:
            # Full side bounds in 2-player mode, with ~10% margins vertically (~80% usable height)
            left, right = player._side_bounds()
            v_margin = int(HEIGHT * 0.10)
            top, bottom = v_margin, HEIGHT - v_margin
        # Population factor to weaken bias and encourage spread
        f = min(1.0, math.sqrt(max(1.0, need)) / 20.0)
        tasked = {t['i'] for t in player._worker_tasks if 0 <= t['i'] < len(player._worker_positions)}
        # Ensure per-worker anchors within the rectangle (change occasionally)
        if not hasattr(player, '_worker_anchors'):
            player._worker_anchors = []
            player._worker_anchor_ttls = []
        # Resize anchors to match positions length
        while len(player._worker_anchors) < len(player._worker_positions):
            ax = random.uniform(left+10, right-10)
            ay = random.uniform(top, bottom)
            player._worker_anchors.append((ax, ay))
            player._worker_anchor_ttls.append(random.uniform(4.0, 9.0))
        if len(player._worker_anchors) > len(player._worker_positions):
            player._worker_anchors = player._worker_anchors[:len(player._worker_positions)]
            player._worker_anchor_ttls = player._worker_anchor_ttls[:len(player._worker_positions)]
        new_pos = []
        new_vel = []
        new_anchors = list(player._worker_anchors)
        new_ttls = list(player._worker_anchor_ttls)
        for idx, ((x, y), (vx, vy)) in enumerate(zip(player._worker_positions, player._worker_vels)):
            # Refresh anchor sometimes to avoid static congregation
            ttl = new_ttls[idx] - dt
            ax, ay = new_anchors[idx]
            if ttl <= 0 or not (left+10 <= ax <= right-10 and top <= ay <= bottom):
                ax = random.uniform(left+10, right-10)
                ay = random.uniform(top, bottom)
                ttl = random.uniform(4.0, 9.0)
                new_anchors[idx] = (ax, ay)
            new_ttls[idx] = ttl
            # Ornstein–Uhlenbeck style Brownian motion with gentle bias toward base
            decay = math.exp(-1.2 * dt)  # velocity persistence
            vx *= decay; vy *= decay
            # gentle bias toward personal anchor, weakens with population size
            bias = max(0.03, 0.22 * (1.0 - 0.8 * f))
            vx += bias * (ax - x) * dt
            vy += bias * (ay - y) * dt
            # Gaussian noise term (Brownian component)
            sigma = 44.0  # px / sqrt(s)
            vx += random.gauss(0.0, sigma) * math.sqrt(max(1e-6, dt))
            vy += random.gauss(0.0, sigma) * math.sqrt(max(1e-6, dt))
            # Speed clamp
            speed = math.hypot(vx, vy)
            max_s = 90.0
            if speed > max_s:
                scale = max_s / (speed + 1e-6)
                vx *= scale; vy *= scale
            # Integrate
            nx = x + vx * dt
            ny = y + vy * dt
            # Soft bounds: apply gentle push back inside instead of hard clamps (multi tight or normal)
            if idx not in tasked:
                # Horizontal soft push
                if nx < left:
                    vx += (left - nx) * 2.5 * dt
                elif nx > right:
                    vx -= (nx - right) * 2.5 * dt
                # Vertical soft push
                if ny < top:
                    vy += (top - ny) * 2.5 * dt
                elif ny > bottom:
                    vy -= (ny - bottom) * 2.5 * dt
                # Safety soft clamp to a small margin outside bounds
                nx = max(left - 12, min(right + 12, nx))
                ny = max(top - 12, min(bottom + 12, ny))
            new_pos.append((nx, ny))
            new_vel.append((vx, vy))
        player._worker_anchors = new_anchors
        player._worker_anchor_ttls = new_ttls
        player._worker_positions = new_pos
        player._worker_vels = new_vel

        # Update build/depart tasks steering and lifetimes. Support consumption with a short linger
        alive_tasks = []
        to_remove = set()
        for t in player._worker_tasks:
            i = t['i']
            if i < 0 or i >= len(player._worker_positions):
                continue
            x, y = player._worker_positions[i]
            tx, ty = t['tx'], t['ty']
            dx = tx - x; dy = ty - y
            dist = math.hypot(dx, dy) + 1e-6
            # Speed: departures fastest; defense-builders faster than house builders
            is_depart = (t.get('consume') and not t.get('arrived') and (tx < 0 or tx > WIDTH))
            is_defense_build = False
            if not is_depart and t.get('consume') and not t.get('arrived'):
                # Heuristic: if target matches (or is very close to) a defense position
                for d in getattr(player, '_defense_positions', []):
                    if (abs(d.get('x', 0) - tx) <= 8) and (abs(d.get('y', 0) - ty) <= 8):
                        is_defense_build = True
                        break
            if is_depart:
                spd = 160.0
            elif is_defense_build:
                spd = 240.0  # ~2x faster toward towers under construction
            else:
                spd = 120.0
            vx = dx/dist*spd
            vy = dy/dist*spd
            player._worker_vels[i] = (vx, vy)
            if dist < 2:
                player._worker_positions[i] = (float(tx), float(ty))
                player._worker_vels[i] = (0.0, 0.0)
                if t.get('consume'):
                    # Linger briefly at the exact site before being consumed
                    if not t.get('arrived'):
                        t['arrived'] = True
                        t['ttl'] = max(t.get('ttl', 0.0), 0.25)
                        alive_tasks.append(t)
                        continue
                    # already arrived previously; fall through to ttl countdown
            # Update TTL only for build-site tasks; keep departure tasks alive until offscreen
            if t.get('consume') and not t.get('arrived') and (tx < 0 or tx > WIDTH):
                # departure task
                # if already offscreen sufficiently, remove
                if (tx < 0 and x <= -40) or (tx > WIDTH and x >= WIDTH+40):
                    to_remove.add(i)
                else:
                    alive_tasks.append(t)
            else:
                # build or non-consuming tasks
                if t.get('consume') and not t.get('arrived'):
                    # Consuming build task: keep alive until arrival, don't decrement TTL yet
                    alive_tasks.append(t)
                else:
                    # Non-consuming builder or post-arrival linger uses TTL
                    t['ttl'] -= dt
                    if t['ttl'] > 0:
                        alive_tasks.append(t)
                    else:
                        if t.get('consume') and t.get('arrived'):
                            to_remove.add(i)
        player._worker_tasks = alive_tasks
        # Remove consumed workers by index (descending to keep indices valid), remap remaining task indices
        if to_remove:
            removed = sorted(list(to_remove), reverse=True)
            for idx in removed:
                if 0 <= idx < len(player._worker_positions):
                    player._worker_positions.pop(idx)
                    player._worker_vels.pop(idx)
            if player._worker_tasks:
                def shift_index(i):
                    dec = sum(1 for r in removed if r < i)
                    return i - dec
                for t in player._worker_tasks:
                    t['i'] = shift_index(t['i'])

    worker_img = get_image('worker', player.side)
    ww, wh = worker_img.get_width(), worker_img.get_height()
    for (x, y) in player._worker_positions:
        surface.blit(worker_img, (int(x) - ww//2, int(y) - wh//2))

    # Soldiers: garrison triangles; trim excess only (no auto-add)
    if len(player._soldier_positions) > player.soldiers:
        player._soldier_positions = player._soldier_positions[:player.soldiers]
    draw_n = min(player.soldiers, len(player._soldier_positions))
    soldier_img = get_image('soldier', player.side)
    sw, sh = soldier_img.get_width(), soldier_img.get_height()
    for i in range(draw_n):
        cx2, cy2 = player._soldier_positions[i]
        surface.blit(soldier_img, (int(cx2) - sw//2, int(cy2) - sh//2))

    # Incoming soldiers walking in from edge until they reach garrison
    if player._soldier_incoming:
        new_incoming = []
        soldier_img = get_image('soldier', player.side)
        sw, sh = soldier_img.get_width(), soldier_img.get_height()
        for u in player._soldier_incoming:
            x, y = u['x'], u['y']
            tx, ty = u['tx'], u['ty']
            dx, dy = tx - x, ty - y
            dist = math.hypot(dx, dy) + 1e-6
            spd = 80.0
            if dist < 4:
                player._soldier_positions.append((tx, ty))
            else:
                ux = x + dx/dist*spd*dt
                uy = y + dy/dist*spd*dt
                u['x'], u['y'] = ux, uy
                new_incoming.append(u)
                surface.blit(soldier_img, (int(ux) - sw//2, int(uy) - sh//2))
        player._soldier_incoming = new_incoming

    # Houses: draw last so they appear over workers/soldiers/towers, with spawn scale-in
    if len(player._house_positions) != player.houses:
        if len(player._house_positions) < player.houses:
            player.add_houses(player.houses - len(player._house_positions))
        else:
            player._house_positions = player._house_positions[:player.houses]
    house_img = get_image('house', player.side)
    hw, hh = house_img.get_width(), house_img.get_height()
    for (hx, hy) in player._house_positions:
        scale = 1.0
        if getattr(player, '_spawn_bursts', None):
            for b in player._spawn_bursts:
                if abs(b.get('x',0)-hx) < 8 and abs(b.get('y',0)-hy) < 8:
                    start = b.get('until', now) - 0.6
                    prog = max(0.0, min(1.0, (now - start) / 0.15))
                    scale = 0.9 + 0.1 * prog
                    break
        if scale != 1.0:
            sw = max(1, int(hw * scale)); sh = max(1, int(hh * scale))
            simg = pygame.transform.smoothscale(house_img, (sw, sh))
            surface.blit(simg, (int(hx) - sw//2, int(hy) - sh//2))
        else:
            surface.blit(house_img, (int(hx) - hw//2, int(hy) - hh//2))

    # (No per-base defense text; shown only in top HUD)


_DECOR = None
_NOISE_SURF = None

def _smoothstep(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)

def _value_noise(x: float, y: float, grid, gw: int, gh: int):
    # x,y in [0,1]; grid is gw x gh of random values
    xf = x * (gw - 1)
    yf = y * (gh - 1)
    x0 = int(xf)
    y0 = int(yf)
    x1 = min(x0 + 1, gw - 1)
    y1 = min(y0 + 1, gh - 1)
    tx = _smoothstep(xf - x0)
    ty = _smoothstep(yf - y0)
    v00 = grid[y0][x0]
    v10 = grid[y0][x1]
    v01 = grid[y1][x0]
    v11 = grid[y1][x1]
    a = v00 * (1 - tx) + v10 * tx
    b = v01 * (1 - tx) + v11 * tx
    return a * (1 - ty) + b * ty

def _init_noise_surface():
    global _NOISE_SURF
    rng = random.Random(SEED if SEED is not None else None)
    # Compute low-res noise then upscale for performance
    NX = max(64, WIDTH // 6)
    NY = max(64, HEIGHT // 6)
    small = pygame.Surface((NX, NY), flags=pygame.SRCALPHA)
    octaves = 3
    base_freq = 12
    max_alpha = 30
    # Precompute grids per octave once
    grids = []
    freqs = []
    for o in range(octaves):
        freq = int(base_freq * (2 ** o))
        gw = max(2, int(freq))
        gh = max(2, int(freq * NY / NX))
        rng.seed((o+1) * 9176)
        grid = [[rng.random() for _ in range(gw)] for __ in range(gh)]
        grids.append((grid, gw, gh))
        freqs.append(freq)
    for y in range(NY):
        for x in range(NX):
            nx = x / max(1, NX - 1)
            ny = y / max(1, NY - 1)
            amp = 1.0
            val = 0.0
            norm = 0.0
            for (grid, gw, gh) in grids:
                val += _value_noise(nx, ny, grid, gw, gh) * amp
                norm += amp
                amp *= 0.5
            v = val / max(1e-6, norm)
            a = int(max(0, min(max_alpha, (v - 0.5) * 2.0 * max_alpha)))
            if a > 0:
                small.set_at((x, y), (0, 0, 0, a))
    _NOISE_SURF = pygame.transform.smoothscale(small, (WIDTH, HEIGHT))

def _init_decor():
    global _DECOR
    rng = random.Random(SEED if SEED is not None else None)
    area = WIDTH * HEIGHT
    # More grass than trees
    n_grass = max(60, area // 9000)
    n_trees = max(15, area // 28000)
    n_boulders = max(2, area // 200000)
    # Avoid HUD/top/bottom margins
    xmin, xmax = 20, WIDTH-20
    ymin, ymax = 40, HEIGHT-40
    grass = [(rng.randint(xmin, xmax), rng.randint(ymin, ymax)) for _ in range(int(n_grass))]
    trees = [(rng.randint(xmin, xmax), rng.randint(ymin, ymax)) for _ in range(int(n_trees))]
    boulders = [(rng.randint(xmin, xmax), rng.randint(ymin, ymax)) for _ in range(int(n_boulders))]
    _DECOR = { 'grass': grass, 'trees': trees, 'boulders': boulders }

def draw_field(surface):
    surface.fill(GREEN)
    # Scatter background decor
    global _DECOR
    global _NOISE_SURF
    if _DECOR is None:
        _init_decor()
    if _NOISE_SURF is None:
        _init_noise_surface()
    # Darken with subtle noise overlay
    if _NOISE_SURF is not None:
        surface.blit(_NOISE_SURF, (0, 0))
    gimg = get_image('grass', 'L')
    timg = get_image('tree', 'L')
    bimg = get_image('boulder', 'L')
    gw, gh = gimg.get_width(), gimg.get_height()
    tw, th = timg.get_width(), timg.get_height()
    bw, bh = bimg.get_width(), bimg.get_height()
    # Static noise overlay
    if _NOISE_SURF is not None:
        surface.blit(_NOISE_SURF, (0, 0))
    # Static decor
    for (x, y) in _DECOR['grass']:
        surface.blit(gimg, (x - gw//2, y - gh//2))
    for (x, y) in _DECOR['trees']:
        surface.blit(timg, (x - tw//2, y - th//2))
    for (x, y) in _DECOR.get('boulders', []):
        surface.blit(bimg, (x - bw//2, y - bh//2))


def draw_hud(surface, p1, p2, phase, step_time_left, step_nr):
    font = pygame.font.SysFont(None, 22)

    def panel(player, x, align_left=True):
        y = 8
        # Compute worker bonus preview based on current workers
        try:
            from .config import WORKER_BONUS
            bonus_pct = int((WORKER_BONUS - 1.0) * 100)
        except Exception:
            bonus_pct = 0
        s = [
            f"{player.name}",
            f"Workers: {player.workers}   Soldiers: {player.soldiers}",
            f"Houses: {player.houses} (+{player.houses*HOUSE_WORKER_BONUS + BASE_WORKERS_PER_STEP}/step)",
            f"Attack%: {int(player.attack_pct*100)}",
            f"Defenses: {player.defenses}",
            f"Worker Bonus: +{bonus_pct}% (~+{int(player.workers * bonus_pct/100)})",
            (f"Last: {player.last_action}" if getattr(player, 'last_action', '') else "")
        ]
        for line in s:
            if not line:
                continue
            img = font.render(line, True, WHITE)
            if align_left:
                surface.blit(img, (x, y)); y += 20
            else:
                surface.blit(img, (x - img.get_width(), y)); y += 20

    panel(p1, 10, True)
    panel(p2, WIDTH-10, False)

    phase_text = f"Step {step_nr} — {phase}  {step_time_left:0.1f}s"
    img = font.render(phase_text, True, WHITE)
    surface.blit(img, (WIDTH//2 - img.get_width()//2, 8))
