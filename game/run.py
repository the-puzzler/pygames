import sys, time, random, math
import pygame
from .config import WIDTH, HEIGHT, STEP_TIME, BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, HOUSE_COST, DEFENSE_COST, SEED, TIME_SCALE
from .model import PlayerState, BotView
from .combat import resolve_attack_packet
from .view import draw_field, draw_base, draw_hud
from .anim import spawn_attack_units, animate_attack

# Visual RNG so animation jitter doesn't affect gameplay RNG
VIS_RNG = random.Random()


def sanitize_action(act_dict, prev_attack_pct, workers_available):
    """Enforce exactly one action per step with robust parsing.
    Priority: convert > build_houses > build_defenses > attack.
    Attack action both sets attack_pct and triggers sending this step.
    Non-numeric or out-of-range inputs are clamped; invalid values become 0 or previous.
    """

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
    # no-op
    return {"kind": "none", "attack_pct": prev_attack_pct}


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

    phase = "PLAN"
    step_start = time.time()

    while True:
        now = time.time()
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit(0)

        if phase == "PLAN":
            draw_field(screen)
            draw_base(screen, p1, dt)
            draw_base(screen, p2, dt)
            rem = max(0.0, STEP_TIME - (now - step_start) * TIME_SCALE)
            draw_hud(screen, p1, p2, "PLAN", rem, step_nr)
            pygame.display.flip()

            if (now - step_start) * TIME_SCALE >= STEP_TIME:
                p1.spawn_workers(); p2.spawn_workers()

                state_L = BotView(step_nr, p1, p2)
                state_R = BotView(step_nr, p2, p1)
                try:
                    raw_L = BOT_L(state_L) or {}
                except Exception as e:
                    print(f"[WARN] {p1.name} bot error at step {step_nr}: {e}")
                    raw_L = {}
                try:
                    raw_R = BOT_R(state_R) or {}
                except Exception as e:
                    print(f"[WARN] {p2.name} bot error at step {step_nr}: {e}")
                    raw_R = {}
                act_L = sanitize_action(raw_L, p1.attack_pct, p1.workers)
                act_R = sanitize_action(raw_R, p2.attack_pct, p2.workers)

                # Enforce one action per side
                # Houses
                if act_L["kind"] == "build_houses":
                    can_h_L = act_L["build_houses"]
                    p1.houses += can_h_L; p1.workers -= can_h_L*HOUSE_COST; new_sites_L = p1.add_houses(can_h_L)
                    if new_sites_L:
                        for site in new_sites_L:
                            p1.schedule_builders_consume(site, min(HOUSE_COST, len(p1._worker_positions)), duration=2.0)
                        p1._record_spawns(new_sites_L)
                    p1.last_action = f"Build Houses x{can_h_L}" if can_h_L else "Wait"
                if act_R["kind"] == "build_houses":
                    can_h_R = act_R["build_houses"]
                    p2.houses += can_h_R; p2.workers -= can_h_R*HOUSE_COST; new_sites_R = p2.add_houses(can_h_R)
                    if new_sites_R:
                        for site in new_sites_R:
                            p2.schedule_builders_consume(site, min(HOUSE_COST, len(p2._worker_positions)), duration=2.0)
                        p2._record_spawns(new_sites_R)
                    p2.last_action = f"Build Houses x{can_h_R}" if can_h_R else "Wait"

                # Defenses (consume DEFENSE_COST workers each visually as builders)
                if act_L["kind"] == "build_defenses":
                    can_d_L = act_L["build_defenses"]
                    p1.defenses += can_d_L; p1.workers -= can_d_L*DEFENSE_COST
                    if can_d_L:
                        sites_Ld = p1.add_defenses(can_d_L)
                        for site in sites_Ld:
                            p1.schedule_builders_consume(site, min(DEFENSE_COST, len(p1._worker_positions)), duration=1.5)
                        p1._record_spawns(sites_Ld)
                    p1.last_action = f"Build Defenses x{can_d_L}" if can_d_L else "Wait"
                if act_R["kind"] == "build_defenses":
                    can_d_R = act_R["build_defenses"]
                    p2.defenses += can_d_R; p2.workers -= can_d_R*DEFENSE_COST
                    if can_d_R:
                        sites_Rd = p2.add_defenses(can_d_R)
                        for site in sites_Rd:
                            p2.schedule_builders_consume(site, min(DEFENSE_COST, len(p2._worker_positions)), duration=1.5)
                        p2._record_spawns(sites_Rd)
                    p2.last_action = f"Build Defenses x{can_d_R}" if can_d_R else "Wait"

                # Convert workers -> soldiers (visual ingress/egress)
                if act_L["kind"] == "convert":
                    conv_L = act_L["convert"]
                    p1.soldiers += conv_L; p1.workers -= conv_L; p1.schedule_worker_departures(conv_L); p1.schedule_soldier_ingress(conv_L)
                    p1.last_action = f"Convert {conv_L}"
                if act_R["kind"] == "convert":
                    conv_R = act_R["convert"]
                    p2.soldiers += conv_R; p2.workers -= conv_R; p2.schedule_worker_departures(conv_R); p2.schedule_soldier_ingress(conv_R)
                    p2.last_action = f"Convert {conv_R}"

                # Attack: only if chosen this step
                send_L = 0; send_R = 0
                if act_L["kind"] == "attack":
                    p1.attack_pct = act_L["attack_pct"]
                    send_L = int(p1.soldiers * p1.attack_pct)
                    p1.last_action = f"Attack {int(p1.attack_pct*100)}%"
                if act_R["kind"] == "attack":
                    p2.attack_pct = act_R["attack_pct"]
                    send_R = int(p2.soldiers * p2.attack_pct)
                    p2.last_action = f"Attack {int(p2.attack_pct*100)}%"
                # Limit to garrison
                send_L = min(send_L, len(p1._soldier_positions))
                send_R = min(send_R, len(p2._soldier_positions))
                starts_L = p1.pop_attacking_soldiers(send_L)
                starts_R = p2.pop_attacking_soldiers(send_R)
                p1.soldiers -= send_L
                p2.soldiers -= send_R

                pre_R_w = p2.workers; pre_L_w = p1.workers
                pre_R_s = p2.soldiers; pre_L_s = p1.soldiers

                # Resolve both sides identically: defenses soak first (HP), then soldiers (1:1), then workers (1:1)
                p2_def_before = list(p2._defense_positions)
                p1_def_before = list(p1._defense_positions)
                p2._defense_positions, p2.soldiers, p2.workers, destroyed_R_defs, killed_R_soldiers, killed_R_workers, def_dmg_R = \
                    resolve_attack_packet(send_L, p2._defense_positions, pre_R_s, pre_R_w,
                                           apply_defense_to_soldiers=True, apply_defense_to_workers=True)
                p1._defense_positions, p1.soldiers, p1.workers, destroyed_L_defs, killed_L_soldiers, killed_L_workers, def_dmg_L = \
                    resolve_attack_packet(send_R, p1._defense_positions, pre_L_s, pre_L_w,
                                           apply_defense_to_soldiers=True, apply_defense_to_workers=True)
                # Keep garrison visuals in sync
                p2.trim_soldiers(p2.soldiers)
                p1.trim_soldiers(p1.soldiers)
                p2.defenses = len(p2._defense_positions)
                p1.defenses = len(p1._defense_positions)
                # Attackers that survive after all kills are zero in this model (each attacker deals 1 dmg)
                cont_L = 0; cont_R = 0

                # Build target points and placeholders for visual hits
                placeholders_L = None; placeholders_R = None
                targets_L = []; targets_R = []
                if send_L > 0:
                    # Right-side victims
                    victims_s_R = []
                    if killed_R_soldiers > 0 and len(p2._soldier_positions) >= killed_R_soldiers:
                        victims_s_R = list(p2._soldier_positions[-killed_R_soldiers:])
                    victims_w_R = []
                    if killed_R_workers > 0 and len(p2._worker_positions) > 0:
                        victims_w_R = list(p2._worker_positions[:min(killed_R_workers, len(p2._worker_positions))])
                    # Defense damage targets: distribute across destroyed towers first, then remaining towers if any
                    def_targets_R = []
                    if def_dmg_R > 0:
                        # Use destroyed tower positions preferentially
                        for (tx, ty) in destroyed_R_defs:
                            def_targets_R.extend([(tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0))])
                        # Fill remaining damage on surviving towers' positions
                        survive_defs = [(t['x'], t['y']) for t in p2_def_before if isinstance(t, dict) and (t['x'], t['y']) not in destroyed_R_defs]
                        i = 0
                        while len(def_targets_R) < def_dmg_R and survive_defs:
                            tx, ty = survive_defs[i % len(survive_defs)]
                            def_targets_R.append((tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0)))
                            i += 1
                    # Build target list: defenses first, then soldiers, then workers
                    targets_L = def_targets_R + [(tx + VIS_RNG.uniform(-4.0,4.0), ty + VIS_RNG.uniform(-4.0,4.0)) for (tx,ty) in victims_s_R] + \
                                [(tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0)) for (tx,ty) in victims_w_R]
                    targets_L = targets_L[:send_L]
                    placeholders_R = { 'towers': destroyed_R_defs[:], 'soldiers': victims_s_R[:], 'workers': victims_w_R[:] }
                if send_R > 0:
                    victims_s_L = []
                    if killed_L_soldiers > 0 and len(p1._soldier_positions) >= killed_L_soldiers:
                        victims_s_L = list(p1._soldier_positions[-killed_L_soldiers:])
                    victims_w_L = []
                    if killed_L_workers > 0 and len(p1._worker_positions) > 0:
                        victims_w_L = list(p1._worker_positions[:min(killed_L_workers, len(p1._worker_positions))])
                    def_targets_L = []
                    if def_dmg_L > 0:
                        for (tx, ty) in destroyed_L_defs:
                            def_targets_L.extend([(tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0))])
                        survive_defs_L = [(t['x'], t['y']) for t in p1_def_before if isinstance(t, dict) and (t['x'], t['y']) not in destroyed_L_defs]
                        i = 0
                        while len(def_targets_L) < def_dmg_L and survive_defs_L:
                            tx, ty = survive_defs_L[i % len(survive_defs_L)]
                            def_targets_L.append((tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0)))
                            i += 1
                    targets_R = def_targets_L + [(tx + VIS_RNG.uniform(-4.0,4.0), ty + VIS_RNG.uniform(-4.0,4.0)) for (tx,ty) in victims_s_L] + \
                                [(tx + VIS_RNG.uniform(-3.0,3.0), ty + VIS_RNG.uniform(-3.0,3.0)) for (tx,ty) in victims_w_L]
                    targets_R = targets_R[:send_R]
                    placeholders_L = { 'towers': destroyed_L_defs[:], 'soldiers': victims_s_L[:], 'workers': victims_w_L[:] }

                # Prepare animation units only if someone attacked
                if send_L > 0 or send_R > 0:
                    u_L = spawn_attack_units(p1, send_L, p2, both_attacking=(send_R>0), starts=starts_L, target_points=targets_L if targets_L else None)
                    u_R = spawn_attack_units(p2, send_R, p1, both_attacking=(send_L>0), starts=starts_R, target_points=targets_R if targets_R else None)
                    # Only continue to workers if there were survivors from the mid-fight
                    if not (send_L>0 and send_R>0):
                        cont_L = 0; cont_R = 0
                    phase = "ATTACK"
                    step_start = time.time()
                else:
                    # No attack this step; proceed to next PLAN step
                    # If neither attacked, we already recorded last_action above; if none set, set to Wait
                    if not getattr(p1, 'last_action', ''):
                        p1.last_action = "Wait"
                    if not getattr(p2, 'last_action', ''):
                        p2.last_action = "Wait"
                    step_nr += 1
                    step_start = time.time()
                    continue

        elif phase == "ATTACK":
            animate_attack(screen, clock, u_L, u_R, p1, p2, step_nr, cont_L, cont_R, placeholders_L, placeholders_R, destroyed_L_defs, destroyed_R_defs)

            left_dead  = (p1.soldiers <= 0 and p1.workers <= 0)
            right_dead = (p2.soldiers <= 0 and p2.workers <= 0)

            if left_dead or right_dead:
                # Clear all assets for a clean end screen
                def _clear_assets(pl):
                    pl.houses = 0
                    pl.defenses = 0
                    pl.workers = 0
                    pl.soldiers = 0
                    pl._house_positions = []
                    pl._defense_positions = []
                    pl._worker_positions = []
                    pl._worker_vels = []
                    pl._worker_tasks = []
                    pl._soldier_positions = []
                    pl._soldier_incoming = []
                _clear_assets(p1)
                _clear_assets(p2)

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
                img = big.render(txt, True, (240,240,240))
                screen.blit(img, (WIDTH//2 - img.get_width()//2, HEIGHT//2 - 30))
                pygame.display.flip()
                while True:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                            pygame.quit(); sys.exit(0)
                    pygame.time.wait(10)

            phase = "PLAN"
            step_start = time.time()
            step_nr += 1
