import random, time, math, sys
import pygame
from .config import WIDTH, HEIGHT, ATTACK_TIME, FPS, GREY, PINK, TIME_SCALE, SEED
from .view import draw_field, draw_base, draw_hud, tri_points, get_image

# Dedicated RNG for visuals
VIS_RNG = random.Random(SEED if SEED is not None else 97531)


def spawn_attack_units(p, count, defender, both_attacking, starts, target_points=None):
    units = []
    if count <= 0:
        return units
    direction = 1 if p.side=="L" else -1
    for (sx, sy) in starts:
        jitter_x = random.uniform(-3.0, 3.0)
        jitter_y = random.uniform(-3.0, 3.0)
        x = sx + jitter_x
        y = sy + jitter_y
        units.append({"x": x, "y": y, "sx": x, "sy": y, "dir": direction})

    if target_points:
        # Assign provided targets per unit for precise hits
        for i, u in enumerate(units):
            if i < len(target_points):
                tx, ty = target_points[i]
            else:
                tx, ty = (WIDTH//2, p.base_y)
            u["tx"], u["ty"] = tx, ty
            # Control point slightly arced toward target
            midx = (u["sx"] + tx) * 0.5
            arc = (-1 if p.side=="L" else 1) * VIS_RNG.uniform(10.0, 28.0)
            midy = (u["sy"] + ty) * 0.5 + arc
            u["cx"], u["cy"] = midx, midy
        return units
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
            midx = (u["sx"] + u["tx"]) * 0.5
            arc = ( -1 if p.side=="L" else 1 ) * random.uniform(18.0, 42.0)
            midy = (u["sy"] + ty) * 0.5 + arc
            u["cx"], u["cy"] = midx, midy
    else:
        worker_targets = defender._worker_positions or [(defender.base_x, defender.base_y)]
        for i, u in enumerate(units):
            tx = defender.base_x - 44 if p.side=="L" else defender.base_x + 44
            wx, wy = worker_targets[i % len(worker_targets)]
            ty = wy + random.uniform(-8.0, 8.0)
            u["tx"], u["ty"] = tx, ty
            t_ctrl = 0.4 if p.side=="L" else 0.6
            cx = u["sx"] + (tx - u["sx"]) * t_ctrl
            cy = u["sy"] + (ty - u["sy"]) * t_ctrl + ( -1 if p.side=="L" else 1 ) * VIS_RNG.uniform(16.0, 36.0)
            u["cx"], u["cy"] = cx, cy
    return units


def animate_attack(screen, clock, p1_units, p2_units, p1, p2, step_nr, cont_L=0, cont_R=0, placeholders_L=None, placeholders_R=None, bursts_L=None, bursts_R=None, upscale_win=None):
    t0 = time.time()
    while ((time.time() - t0) * TIME_SCALE) < ATTACK_TIME:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        dt = clock.tick(FPS) / 1000.0
        elapsed = (time.time() - t0) * TIME_SCALE
        t = max(0.0, min(1.0, elapsed / ATTACK_TIME))
        def bezier(p0, c, p1p, tt):
            it = 1.0 - tt
            return (
                it*it*p0[0] + 2*it*tt*c[0] + tt*tt*p1p[0],
                it*it*p0[1] + 2*it*tt*c[1] + tt*tt*p1p[1],
            )
        def remove_near(lst, x, y, tol=6.0):
            if not lst:
                return False
            for i, (px, py) in enumerate(lst):
                if (px - x)**2 + (py - y)**2 <= tol*tol:
                    lst.pop(i)
                    return True
            return False
        for u in p1_units:
            bx, by = bezier((u["sx"], u["sy"]), (u["cx"], u["cy"]), (u["tx"], u["ty"]), t)
            u["x"], u["y"] = bx, by
            # If close to target, clear corresponding placeholder on R side (towers -> soldiers -> workers)
            if placeholders_R and t >= 0.98:
                if not remove_near(placeholders_R.get('towers', []), bx, by):
                    if not remove_near(placeholders_R.get('soldiers', []), bx, by):
                        remove_near(placeholders_R.get('workers', []), bx, by)
        for u in p2_units:
            bx, by = bezier((u["sx"], u["sy"]), (u["cx"], u["cy"]), (u["tx"], u["ty"]), t)
            u["x"], u["y"] = bx, by
            if placeholders_L and t >= 0.98:
                if not remove_near(placeholders_L.get('towers', []), bx, by):
                    if not remove_near(placeholders_L.get('soldiers', []), bx, by):
                        remove_near(placeholders_L.get('workers', []), bx, by)

        draw_field(screen)
        draw_base(screen, p1, dt)
        draw_base(screen, p2, dt)

        # Tower destruction flair: expanding rings
        def draw_bursts(positions):
            if not positions:
                return
            # progress in [0,1]
            prog = max(0.0, min(1.0, (time.time() - t0) / ATTACK_TIME))
            for (bx, by) in positions:
                # two rings with phase offset
                for k in (0.0, 0.35):
                    p = (prog + k) % 1.0
                    radius = 6 + int(26 * p)
                    alpha = int(max(0, 180 * (1.0 - p)))
                    if alpha <= 0:
                        continue
                    col = (255, 200, 60, alpha)
                    ring = pygame.Surface((radius*2+2, radius*2+2), pygame.SRCALPHA)
                    pygame.draw.circle(ring, col, (radius+1, radius+1), radius, width=2)
                    screen.blit(ring, (int(bx) - radius - 1, int(by) - radius - 1))

        draw_bursts(bursts_L)
        draw_bursts(bursts_R)

        # Draw placeholders for victims (static until hit)
        if placeholders_L:
            soldier_L = get_image('soldier', 'L')
            worker_L = get_image('worker', 'L')
            tower_L = get_image('tower', 'L')
            sw, sh = soldier_L.get_width(), soldier_L.get_height()
            ww, wh = worker_L.get_width(), worker_L.get_height()
            tw, th = tower_L.get_width(), tower_L.get_height()
            for (x, y) in placeholders_L.get('soldiers', []):
                screen.blit(soldier_L, (int(x) - sw//2, int(y) - sh//2))
            for (x, y) in placeholders_L.get('workers', []):
                screen.blit(worker_L, (int(x) - ww//2, int(y) - wh//2))
            for (x, y) in placeholders_L.get('towers', []):
                screen.blit(tower_L, (int(x) - tw//2, int(y) - th//2))
        if placeholders_R:
            soldier_R = get_image('soldier', 'R')
            worker_R = get_image('worker', 'R')
            tower_R = get_image('tower', 'R')
            sw, sh = soldier_R.get_width(), soldier_R.get_height()
            ww, wh = worker_R.get_width(), worker_R.get_height()
            tw, th = tower_R.get_width(), tower_R.get_height()
            for (x, y) in placeholders_R.get('soldiers', []):
                screen.blit(soldier_R, (int(x) - sw//2, int(y) - sh//2))
            for (x, y) in placeholders_R.get('workers', []):
                screen.blit(worker_R, (int(x) - ww//2, int(y) - wh//2))
            for (x, y) in placeholders_R.get('towers', []):
                screen.blit(tower_R, (int(x) - tw//2, int(y) - th//2))

        # Removed extra defensive bars on sides for cleaner look

        soldier_L = get_image('soldier', 'L')
        soldier_R = get_image('soldier', 'R')
        swL, shL = soldier_L.get_width(), soldier_L.get_height()
        swR, shR = soldier_R.get_width(), soldier_R.get_height()
        for u in p1_units:
            screen.blit(soldier_L, (int(u["x"]) - swL//2, int(u["y"]) - shL//2))
        for u in p2_units:
            screen.blit(soldier_R, (int(u["x"]) - swR//2, int(u["y"]) - shR//2))

        rem = max(0.0, ATTACK_TIME - ((time.time()-t0) * TIME_SCALE))
        draw_hud(screen, p1, p2, "ATTACK", rem, step_nr)
        if upscale_win is not None:
            up = pygame.transform.smoothscale(screen, upscale_win.get_size())
            upscale_win.blit(up, (0,0))
            pygame.display.flip()
        else:
            pygame.display.flip()

    if (len(p1_units) > 0 and len(p2_units) > 0) and (cont_L > 0 or cont_R > 0):
        def assign_phase2(units, defender, count, side_left):
            work_targets = defender._worker_positions or [(defender.base_x, defender.base_y)]
            survivors = []
            for i in range(min(count, len(units))):
                u = units[i]
                sx2, sy2 = u["x"], u["y"]
                wx, wy = work_targets[i % len(work_targets)]
                tx2 = defender.base_x - 40 if side_left else defender.base_x + 40
                ty2 = wy + random.uniform(-10.0, 10.0)
                t_ctrl = 0.6 if side_left else 0.4
                cx2 = sx2 + (tx2 - sx2) * t_ctrl
                cy2 = sy2 + (ty2 - sy2) * t_ctrl + ( -1 if side_left else 1 ) * random.uniform(14.0, 28.0)
                survivors.append({'sx': sx2, 'sy': sy2, 'cx': cx2, 'cy': cy2, 'tx': tx2, 'ty': ty2})
            return survivors

        surv_L = assign_phase2(p1_units, p2, cont_L, True)
        surv_R = assign_phase2(p2_units, p1, cont_R, False)
        EXTRA = 1.0
        t1 = time.time()
        while ((time.time() - t1) * TIME_SCALE) < EXTRA:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit(); sys.exit(0)
            dt = clock.tick(FPS) / 1000.0
            elapsed = (time.time() - t1) * TIME_SCALE
            t = max(0.0, min(1.0, elapsed / EXTRA))
            def bezier(p0, c, p1p, tt):
                it = 1.0 - tt
                return (it*it*p0[0] + 2*it*tt*c[0] + tt*tt*p1p[0], it*it*p0[1] + 2*it*tt*c[1] + tt*tt*p1p[1])
            draw_field(screen)
            draw_base(screen, p1, dt)
            draw_base(screen, p2, dt)
            # No defensive bars here either
            for s in surv_L:
                x, y = bezier((s['sx'], s['sy']), (s['cx'], s['cy']), (s['tx'], s['ty']), t)
                pts = tri_points(int(x), int(y), 6, facing_right=True)
                pygame.draw.polygon(screen, GREY, pts)
            for s in surv_R:
                x, y = bezier((s['sx'], s['sy']), (s['cx'], s['cy']), (s['tx'], s['ty']), t)
                pts = tri_points(int(x), int(y), 6, facing_right=False)
                pygame.draw.polygon(screen, GREY, pts)
            rem = max(0.0, EXTRA - ((time.time()-t1) * TIME_SCALE))
            draw_hud(screen, p1, p2, "PUSH", rem, step_nr)
            if upscale_win is not None:
                up = pygame.transform.smoothscale(screen, upscale_win.get_size())
                upscale_win.blit(up, (0,0))
                pygame.display.flip()
            else:
                pygame.display.flip()
