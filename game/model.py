import math, random
from .config import WIDTH, HEIGHT, FIELD_MARGIN, BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, HOUSE_COST, DEFENSE_COST, DEFENSE_HEALTH, WORKER_BONUS


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

        # Visual state
        self._worker_positions = []  # list[(x,y)] capped to draw limit
        self._worker_vels = []       # list[(vx,vy)] for gentle wander
        self._worker_tasks = []      # list[{i, tx, ty, ttl}] temporary build tasks
        self._soldier_positions = [] # list[(x,y)]
        self._house_positions = []   # list[(x,y)]
        self._defense_positions = [] # list[{x,y,hp}]
        # Ingress/egress visuals
        self._soldier_incoming = []  # list[{x,y,tx,ty}]
        self._worker_departures = [] # list[{i, tx, ty, ttl}]
        # UI
        self.last_action = ""
        self.last_worker_bonus = 0

    # No defense multiplier — defenses are HP-based towers now

    def spawn_workers(self):
        # Bonus based on current workers before base/house additions
        bonus = int(self.workers * max(0.0, (WORKER_BONUS - 1.0)))
        self.last_worker_bonus = bonus
        self.workers += BASE_WORKERS_PER_STEP + self.houses * HOUSE_WORKER_BONUS + bonus

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

    def plan_soldier_targets(self, n: int):
        """Compute n new garrison target positions without mutating the current list."""
        if n <= 0:
            return []
        direction = 1 if self.side=="L" else -1
        start_x = self.base_x + direction*14
        start_y = self.base_y
        base = list(self._soldier_positions) + [(u.get('tx'), u.get('ty')) for u in self._soldier_incoming]
        cols = max(3, int(math.sqrt(max(1, len(base)+n))))
        targets = []
        for i in range(n):
            row = (len(base)+i) // cols
            col = (len(base)+i) % cols
            ox = direction * (col*12 + random.uniform(-4.0, 4.0))
            oy = (row-2)*12 + random.uniform(-6.0, 6.0)
            targets.append((start_x + ox, start_y + oy))
        return targets

    def schedule_soldier_ingress(self, n: int):
        """Visually bring n soldiers from offscreen to their garrison targets."""
        targets = self.plan_soldier_targets(n)
        if not targets:
            return
        if self.side == "L":
            sx = -50
        else:
            sx = WIDTH + 50
        for tx, ty in targets:
            sy = ty + random.randint(-40, 40)
            self._soldier_incoming.append({"x": sx, "y": sy, "tx": tx, "ty": ty})

    def pop_attacking_soldiers(self, n: int):
        send = min(n, len(self._soldier_positions))
        starts = self._soldier_positions[:send]
        self._soldier_positions = self._soldier_positions[send:]
        return starts

    def trim_soldiers(self, keep_count: int):
        if keep_count < len(self._soldier_positions):
            self._soldier_positions = self._soldier_positions[:keep_count]

    def get_defense_build_sites(self, n: int):
        # Deprecated in favor of add_defenses; kept for compatibility
        return self.add_defenses(n)

    def add_defenses(self, n: int):
        """Create visual defense tower positions near midfield border on this side."""
        if n <= 0:
            return []
        sites = []
        if self.side == "L":
            x_center = WIDTH//2 - 70
        else:
            x_center = WIDTH//2 + 70
        for _ in range(n):
            x = x_center + random.randint(-12, 12)
            y = self.base_y + random.randint(-90, 90)
            # avoid overlapping too closely with existing towers
            ok = True
            for t in self._defense_positions:
                tx = t['x'] if isinstance(t, dict) else t[0]
                ty = t['y'] if isinstance(t, dict) else t[1]
                if (tx - x)**2 + (ty - y)**2 < 20*20:
                    ok = False; break
            if ok:
                self._defense_positions.append({"x": x, "y": y, "hp": DEFENSE_HEALTH})
                sites.append((x, y))
            else:
                # fallback slight jitter
                x2 = x_center + random.randint(-6, 6)
                y2 = self.base_y + random.randint(-90, 90)
                self._defense_positions.append({"x": x2, "y": y2, "hp": DEFENSE_HEALTH})
                sites.append((x2, y2))
        return sites

    def schedule_builders(self, sites, per_site=3, duration=1.0):
        if not sites or not self._worker_positions:
            return
        taken = {t['i'] for t in self._worker_tasks}
        for (tx, ty) in sites:
            dists = []
            for i, (x, y) in enumerate(self._worker_positions):
                if i in taken: continue
                d2 = (x-tx)**2 + (y-ty)**2
                dists.append((d2, i))
            dists.sort()
            for _, i in dists[:per_site]:
                self._worker_tasks.append({'i': i, 'tx': tx, 'ty': ty, 'ttl': duration, 'consume': False})
                taken.add(i)

    def schedule_builders_consume(self, site, n, duration=2.0):
        if n <= 0 or not self._worker_positions:
            return
        tx, ty = site
        taken = {t['i'] for t in self._worker_tasks}
        dists = []
        for i, (x, y) in enumerate(self._worker_positions):
            if i in taken: continue
            d2 = (x-tx)**2 + (y-ty)**2
            dists.append((d2, i))
        dists.sort()
        for _, i in dists[:n]:
            self._worker_tasks.append({'i': i, 'tx': tx, 'ty': ty, 'ttl': duration, 'consume': True, 'depart': False})
            taken.add(i)

    def schedule_worker_departures(self, n: int, duration=9.0):
        if n <= 0 or not self._worker_positions:
            return
        # Choose nearest to base center to depart
        cx = self.base_x + (40 if self.side=="L" else -40)
        cy = self.base_y
        side_tx = -60 if self.side=="L" else WIDTH + 60
        taken = {t['i'] for t in self._worker_tasks}
        dists = []
        for i, (x, y) in enumerate(self._worker_positions):
            if i in taken: continue
            d2 = (x-cx)**2 + (y-cy)**2
            dists.append((d2, i))
        dists.sort()
        for _, i in dists[:n]:
            tx = side_tx
            ty = self._worker_positions[i][1] + random.randint(-20, 20)
            self._worker_tasks.append({'i': i, 'tx': tx, 'ty': ty, 'ttl': duration, 'consume': True, 'depart': True})


class BotView:
    __slots__ = ("step","me","opp","economy","costs")
    def __init__(self, step, me: 'PlayerState', opp: 'PlayerState'):
        self.step = step
        self.me  = Simple(me.workers, me.soldiers, me.houses, me.defenses, me.attack_pct)
        self.opp = Simple(opp.workers, opp.soldiers, opp.houses, opp.defenses, opp.attack_pct)
        self.economy = Simple(BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, 0, 0, 0.0)
        self.costs   = Simple(HOUSE_COST, DEFENSE_COST, 0, 0, 0.0)


class Simple:
    def __init__(self, a,b,c,d,e):
        self.workers=a; self.soldiers=b; self.houses=c; self.defenses=d; self.attack_pct=e
