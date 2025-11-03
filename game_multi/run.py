import math, random, sys, time
import pygame

from game.config import WIDTH, HEIGHT, STEP_TIME, ATTACK_TIME, SEED, HOUSE_COST, DEFENSE_COST, DEFENSE_HEALTH, HOUSE_SIZE, TOWER_SIZE, TIME_SCALE
from game.model import PlayerState, BotView
from game.view import draw_field, draw_base, draw_hud, get_image
from game.combat import resolve_attack_packet


def sanitize_action(act_dict, prev_attack_pct, workers_available):
    # Same one-action rule as 2P, with robust parsing and clamping
    def to_int_nonneg(val):
        try:
            n = int(float(val))
        except Exception:
            n = 0
        return max(0, n)

    def to_float_01(val, default):
        try:
            f = float(val)
        except Exception:
            return default
        return max(0.0, min(1.0, f))

    convert = to_int_nonneg(act_dict.get("convert", 0))
    build_h = to_int_nonneg(act_dict.get("build_houses", 0))
    build_d = to_int_nonneg(act_dict.get("build_defenses", 0))
    attack_raw = act_dict.get("attack_pct", None)
    attack_pct = prev_attack_pct if attack_raw is None else to_float_01(attack_raw, prev_attack_pct)

    if convert > 0:
        amt = min(convert, workers_available)
        return {"kind": "convert", "convert": amt, "attack_pct": prev_attack_pct}
    if build_h > 0:
        can_h = min(build_h, workers_available // HOUSE_COST)
        return {"kind": "build_houses", "build_houses": can_h, "attack_pct": prev_attack_pct}
    if build_d > 0:
        can_d = min(build_d, workers_available // DEFENSE_COST)
        return {"kind": "build_defenses", "build_defenses": can_d, "attack_pct": prev_attack_pct}
    if attack_raw is not None and attack_pct > 0.0:
        return {"kind": "attack", "attack_pct": attack_pct}
    return {"kind": "none", "attack_pct": prev_attack_pct}


def perimeter_layout(n, margin=80):
    """Place n bases evenly along the window perimeter (rectangle) inside a margin."""
    w = max(200, WIDTH)
    h = max(200, HEIGHT)
    left, right = margin, w - margin
    top, bottom = margin, h - margin
    perim = 2 * (right - left) + 2 * (bottom - top)
    step = perim / n
    pos = []
    for i in range(n):
        d = i * step
        # Top edge (left -> right)
        if d <= (right - left):
            x = int(left + d); y = top
        # Right edge (top -> bottom)
        elif d <= (right - left) + (bottom - top):
            d2 = d - (right - left)
            x = right; y = int(top + d2)
        # Bottom edge (right -> left)
        elif d <= (right - left) * 2 + (bottom - top):
            d3 = d - ((right - left) + (bottom - top))
            x = int(right - d3); y = bottom
        # Left edge (bottom -> top)
        else:
            d4 = d - ((right - left) * 2 + (bottom - top))
            x = left; y = int(bottom - d4)
        pos.append((x, y))
    return pos


def run_game_multi(bots):
    assert 2 <= len(bots) <= 6, "Supports 2..6 players"
    if SEED is not None:
        random.seed(SEED)

    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"Workers & War — {len(bots)}P (Bots)")
    clock = pygame.time.Clock()

    # Init players on a ring
    positions = perimeter_layout(len(bots), margin=90)
    players = []
    for i, bot in enumerate(bots):
        # Side used only for sprite flipping: based on x vs center
        side = 'L' if positions[i][0] < WIDTH//2 else 'R'
        p = PlayerState(bot.__name__, side)
        p.base_x, p.base_y = positions[i]
        # enable multi ingress behavior for workers and tighter roam area
        p._multi_ingress = True
        p._multi_roam_tight = True
        p.dead = False
        players.append(p)

    step_nr = 1
    phase = "PLAN"
    step_start = time.time()

    # Preload images
    soldier_L = get_image('soldier', 'L')
    soldier_R = get_image('soldier', 'R')
    swL, shL = soldier_L.get_width(), soldier_L.get_height()
    swR, shR = soldier_R.get_width(), soldier_R.get_height()

    # Batches to animate: list of dicts with src index, dst index, starts [(x,y)], tx,ty, side
    batches = []

    while True:
        now = time.time()
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        alive_idx = [i for i,p in enumerate(players) if not getattr(p, 'dead', False)]
        if len(alive_idx) <= 1:
            # Game over screen
            draw_field(screen)
            for p in players:
                draw_base(screen, p, dt)
            pygame.display.flip()
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                        pygame.quit(); sys.exit(0)
                pygame.time.wait(10)

        if phase == "PLAN":
            draw_field(screen)
            # Draw bases and per-base floating stats
            font = pygame.font.SysFont(None, 18)
            for idx, p in enumerate(players):
                draw_base(screen, p, dt)
                info = f"{p.name}  W:{p.workers} S:{p.soldiers} H:{p.houses} D:{len(p._defense_positions)}"
                img = font.render(info, True, (240,240,240))
                screen.blit(img, (p.base_x - img.get_width()//2, p.base_y - 80))
            rem = max(0.0, STEP_TIME - (now - step_start)*TIME_SCALE)
            # Small countdown at top center
            big = pygame.font.SysFont(None, 24)
            timer = big.render(f"Step {step_nr} — PLAN {rem:0.1f}s", True, (240,240,240))
            screen.blit(timer, (WIDTH//2 - timer.get_width()//2, 6))
            pygame.display.flip()

            if (now - step_start)*TIME_SCALE >= STEP_TIME:
                # Economics
                for p in players:
                    if getattr(p, 'dead', False):
                        continue
                    p.spawn_workers()

                # Get actions
                acts = []
                for i, bot in enumerate(bots):
                    me = players[i]
                    if getattr(me, 'dead', False):
                        acts.append({"kind":"none", "attack_pct": me.attack_pct})
                        continue
                    opp_idx = (i+1) % len(players)
                    # Provide some opponent info: pick next as reference
                    state = BotView(step_nr, me, players[opp_idx])
                    try:
                        raw = bot(state) or {}
                    except Exception as e:
                        print(f"[WARN] {me.name} bot error at step {step_nr}: {e}")
                        raw = {}
                    act = sanitize_action(raw, me.attack_pct, me.workers)
                    acts.append(act)

                # Apply actions
                sends = [0]*len(players)
                starts_lists = [None]*len(players)
                def closest_edge_target(x, y):
                    # returns (tx, ty) slightly offscreen toward the nearest edge
                    d_left = x
                    d_right = WIDTH - x
                    d_top = y
                    d_bottom = HEIGHT - y
                    dm = min(d_left, d_right, d_top, d_bottom)
                    if dm == d_left:
                        return -60, y
                    if dm == d_right:
                        return WIDTH + 60, y
                    if dm == d_top:
                        return x, -40
                    return x, HEIGHT + 40

                def schedule_worker_departures_multi(p: PlayerState, n: int, duration=6.0):
                    if n <= 0 or not p._worker_positions:
                        return
                    # nearest to base
                    cx, cy = p.base_x, p.base_y
                    taken = {t['i'] for t in p._worker_tasks}
                    dists = []
                    for i_, (wx, wy) in enumerate(p._worker_positions):
                        if i_ in taken: continue
                        d2 = (wx-cx)**2 + (wy-cy)**2
                        dists.append((d2, i_))
                    dists.sort()
                    for _, i_ in dists[:n]:
                        wx, wy = p._worker_positions[i_]
                        tx, ty = closest_edge_target(wx, wy)
                        p._worker_tasks.append({'i': i_, 'tx': tx, 'ty': ty, 'ttl': duration, 'consume': True, 'depart': True})

                def schedule_soldier_ingress_multi(p: PlayerState, n: int):
                    if n <= 0:
                        return
                    targets = p.plan_soldier_targets(n)
                    for (tx, ty) in targets:
                        sx, sy = closest_edge_target(tx, ty)
                        p._soldier_incoming.append({"x": sx, "y": sy, "tx": tx, "ty": ty})

                def add_houses_multi(p: PlayerState, n: int):
                    if n <= 0: return []
                    sites = []
                    placed = 0
                    tries = 0
                    pad = max(20, HOUSE_SIZE)
                    def clamp_point(x,y):
                        return max(pad, min(WIDTH-pad, x)), max(pad, min(HEIGHT-pad, y))
                    while placed < n and tries < n*50:
                        tries += 1
                        r = 80
                        ang = random.uniform(0, 2*math.pi)
                        rad = random.uniform(10, r)
                        x = int(p.base_x + rad*math.cos(ang))
                        y = int(p.base_y + rad*math.sin(ang))
                        x, y = clamp_point(x, y)
                        ok = True
                        for (hx, hy) in p._house_positions:
                            if (hx-x)**2 + (hy-y)**2 < 18*18:
                                ok = False; break
                        if ok:
                            p._house_positions.append((x, y))
                            sites.append((x, y))
                            placed += 1
                    return sites

                def add_defenses_multi(p: PlayerState, n: int):
                    if n <= 0: return []
                    sites = []
                    base_r = 110
                    pad = max(24, TOWER_SIZE)
                    def clamp_point(x,y):
                        return max(pad, min(WIDTH-pad, x)), max(pad, min(HEIGHT-pad, y))
                    for _ in range(n):
                        ang = random.uniform(0, 2*math.pi)
                        rad = random.uniform(base_r-15, base_r+15)
                        x = int(p.base_x + rad*math.cos(ang))
                        y = int(p.base_y + rad*math.sin(ang))
                        x, y = clamp_point(x, y)
                        ok = True
                        for t in p._defense_positions:
                            tx, ty = t['x'], t['y']
                            if (tx-x)**2 + (ty-y)**2 < 26*26:
                                ok = False; break
                        if ok:
                            p._defense_positions.append({"x": x, "y": y, "hp": DEFENSE_HEALTH})
                            sites.append((x, y))
                    return sites

                for i, (p, act) in enumerate(zip(players, acts)):
                    kind = act["kind"]
                    if getattr(p, 'dead', False):
                        continue
                    if kind == "build_houses" and act["build_houses"] > 0:
                        can = act["build_houses"]
                        p.houses += can; p.workers -= can*HOUSE_COST
                        sites = add_houses_multi(p, can)
                        for site in sites:
                            p.schedule_builders_consume(site, min(HOUSE_COST, len(p._worker_positions)), duration=2.0)
                        p._record_spawns(sites)
                        p.last_action = f"Build Houses x{can}"
                    elif kind == "build_defenses" and act["build_defenses"] > 0:
                        can = act["build_defenses"]
                        p.defenses += can; p.workers -= can*DEFENSE_COST
                        sites = add_defenses_multi(p, can)
                        for site in sites:
                            p.schedule_builders_consume(site, min(DEFENSE_COST, len(p._worker_positions)), duration=1.5)
                        p._record_spawns(sites)
                        p.last_action = f"Build Defenses x{can}"
                    elif kind == "convert" and act.get("convert",0) > 0:
                        conv = act["convert"]
                        p.soldiers += conv; p.workers -= conv
                        schedule_worker_departures_multi(p, conv)
                        schedule_soldier_ingress_multi(p, conv)
                        p.last_action = f"Convert {conv}"
                    elif kind == "attack":
                        p.attack_pct = act["attack_pct"]
                        send = min(int(p.soldiers * p.attack_pct), len(p._soldier_positions))
                        sends[i] = send
                        p.soldiers -= send
                        starts_lists[i] = p.pop_attacking_soldiers(send)
                        p.last_action = f"Attack {int(p.attack_pct*100)}%"
                    else:
                        p.last_action = "Wait"

                # Split attacks evenly among other alive players
                incoming = [0]*len(players)
                batches = []
                for i, send in enumerate(sends):
                    if send <= 0:
                        continue
                    targets = [j for j in range(len(players)) if j != i and j in alive_idx]
                    if not targets:
                        continue
                    per = send // len(targets)
                    rem = send % len(targets)
                    starts = starts_lists[i][:]
                    idx = 0
                    for j, t in enumerate(targets):
                        cnt = per + (1 if j < rem else 0)
                        if cnt <= 0: continue
                        part_starts = starts[idx: idx+cnt]
                        idx += cnt
                        incoming[t] += cnt
                        # Orientation per batch based on horizontal direction to target
                        side_dir = 'L' if players[t].base_x > players[i].base_x else 'R'
                        batches.append({
                            'src': i, 'dst': t, 'starts': part_starts,
                            'tx': players[t].base_x, 'ty': players[t].base_y,
                            'side': side_dir
                        })

                # Resolve combat per defender
                destroyed_defs = [[] for _ in players]
                for j in range(len(players)):
                    if incoming[j] <= 0 or getattr(players[j], 'dead', False):
                        continue
                    p = players[j]
                    p._defense_positions, p.soldiers, p.workers, destroyed, _, _, _ = \
                        resolve_attack_packet(incoming[j], p._defense_positions, p.soldiers, p.workers)
                    destroyed_defs[j] = destroyed
                    p.defenses = len(p._defense_positions)
                    # Trim garrison visuals
                    p.trim_soldiers(p.soldiers)

                # Death check: clear assets for dead players so they disappear immediately
                for p in players:
                    if getattr(p, 'dead', False):
                        continue
                    if p.workers <= 0 and p.soldiers <= 0 and len(p._defense_positions) == 0:
                        p.dead = True
                        p.houses = 0
                        p._house_positions = []
                        p._defense_positions = []
                        p._worker_positions = []
                        p._worker_vels = []
                        p._worker_tasks = []
                        p._soldier_positions = []
                        p._soldier_incoming = []

                # Animate all batches (2x time scale)
                t0 = time.time()
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            pygame.quit(); sys.exit(0)
                    dt = clock.tick(60) / 1000.0
                    draw_field(screen)
                    for idx, p in enumerate(players):
                        if getattr(p, 'dead', False):
                            continue
                        draw_base(screen, p, dt)
                        info = f"{p.name}  W:{p.workers} S:{p.soldiers} H:{p.houses} D:{len(p._defense_positions)}"
                        img = pygame.font.SysFont(None, 18).render(info, True, (240,240,240))
                        # Clamp label fully on-screen; if top offscreen, show below base
                        lx = p.base_x - img.get_width()//2
                        ly = p.base_y - 80
                        lx = max(4, min(WIDTH - img.get_width() - 4, lx))
                        if ly < 4:
                            ly = min(HEIGHT - img.get_height() - 4, p.base_y + 50)
                        if ly > HEIGHT - img.get_height() - 4:
                            ly = HEIGHT - img.get_height() - 4
                        screen.blit(img, (lx, ly))
                    # Draw moving units
                    for b in batches:
                        img = soldier_L if b['side']=='L' else soldier_R
                        sw, sh = (swL, shL) if b['side']=='L' else (swR, shR)
                        for sx, sy in b['starts']:
                            # quadratic bezier
                            t = min(1.0, ((time.time() - t0)*TIME_SCALE)/ATTACK_TIME)
                            cx = (sx + b['tx'])/2 + ( -20 if b['side']=='L' else 20 )
                            cy = (sy + b['ty'])/2
                            it = 1.0 - t
                            x = it*it*sx + 2*it*t*cx + t*t*b['tx']
                            y = it*it*sy + 2*it*t*cy + t*t*b['ty']
                            screen.blit(img, (int(x) - sw//2, int(y) - sh//2))
                    pygame.display.flip()
                    if ((time.time() - t0)*TIME_SCALE) >= ATTACK_TIME:
                        break

                phase = "PLAN"
                step_start = time.time()
                step_nr += 1
