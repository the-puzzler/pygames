import math, random
import pygame
from .config import WIDTH, HEIGHT, FIELD_MARGIN, GREEN, BROWN, PINK, GREY, WHITE, BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS


def tri_points(cx, cy, size, facing_right=True):
    if facing_right:
        return [(cx+size, cy), (cx-size, cy-size), (cx-size, cy+size)]
    else:
        return [(cx-size, cy), (cx+size, cy-size), (cx+size, cy+size)]


def draw_base(surface, player, dt: float):
    # Defenses: draw towers at stored positions (dicts: x,y,hp)
    # Sync count from list
    player.defenses = len(player._defense_positions)
    for t in player._defense_positions:
        tx, ty = int(t['x']), int(t['y'])
        base = pygame.Rect(int(tx - 6), int(ty + 6), 12, 6)
        shaft = pygame.Rect(int(tx - 3), int(ty - 10), 6, 16)
        pygame.draw.rect(surface, GREY, base)
        pygame.draw.rect(surface, (90,90,90), shaft)

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
            if player.side == "L":
                x = random.randint(-50, -10)
            else:
                x = random.randint(WIDTH+10, WIDTH+50)
            y = cy + random.randint(-120, 120)
            player._worker_positions.append((float(x), float(y)))
            dx = cx - x; dy = cy - y
            dist = math.hypot(dx, dy) + 1e-6
            spd = random.uniform(120.0, 200.0)
            player._worker_vels.append((dx/dist*spd, dy/dist*spd))
    elif len(player._worker_positions) > need:
        # Avoid shrinking while there are consuming tasks to preserve identity illusion
        if consuming == 0:
            player._worker_positions = player._worker_positions[:need]
            player._worker_vels = player._worker_vels[:need]

    if need:
        # Rectangular roam area across this side
        left, right = player._side_bounds()
        top, bottom = 60, HEIGHT-60
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
            # Keep inside rectangular side bounds unless on a task (so it can reach offscreen or far build sites)
            if idx not in tasked:
                nx = max(left+10, min(right-10, nx))
                ny = max(top, min(bottom, ny))
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
            # Departures get higher speed to clear the screen quickly
            spd = 160.0 if (t.get('consume') and not t.get('arrived') and (tx < 0 or tx > WIDTH)) else 120.0
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

    for (x, y) in player._worker_positions:
        pygame.draw.circle(surface, PINK, (int(x), int(y)), wr)

    # Soldiers: garrison triangles; trim excess only (no auto-add)
    if len(player._soldier_positions) > player.soldiers:
        player._soldier_positions = player._soldier_positions[:player.soldiers]
    draw_n = min(player.soldiers, len(player._soldier_positions))
    for i in range(draw_n):
        cx2, cy2 = player._soldier_positions[i]
        pts = tri_points(int(cx2), int(cy2), 5, facing_right=(player.side=="L"))
        pygame.draw.polygon(surface, GREY, pts)

    # Incoming soldiers walking in from edge until they reach garrison
    if player._soldier_incoming:
        new_incoming = []
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
                pts = tri_points(int(ux), int(uy), 5, facing_right=(player.side=="L"))
                pygame.draw.polygon(surface, GREY, pts)
        player._soldier_incoming = new_incoming

    # Houses: draw last so they appear over workers/soldiers/towers
    size = 10
    if len(player._house_positions) != player.houses:
        if len(player._house_positions) < player.houses:
            player.add_houses(player.houses - len(player._house_positions))
        else:
            player._house_positions = player._house_positions[:player.houses]
    for (hx, hy) in player._house_positions:
        rect = pygame.Rect(int(hx - size//2), int(hy - size//2), size, size)
        pygame.draw.rect(surface, BROWN, rect)

    # Defense count text
    font = pygame.font.SysFont(None, 18)
    shield = font.render(f"Defenses: {player.defenses}", True, WHITE)
    if player.side == "L":
        surface.blit(shield, (player.base_x - 20, player.base_y + 90))
    else:
        w = shield.get_width()
        surface.blit(shield, (player.base_x - w + 20, player.base_y + 90))


def draw_field(surface):
    surface.fill(GREEN)
    # Plain field; no center line


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
