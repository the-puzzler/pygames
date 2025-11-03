"""
Workers & War — Headless 1v1 Text Simulator

Self-contained script with minimal setup. No pygame. Prints step-by-step state.
Bots defined at the bottom; the last line runs a sample match vs a greedy bot.

Usage:
  uv run ww_headless.py
or
  python ww_headless.py
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Tuple


# ================== SIMPLE MODEL ==================

@dataclass
class Player:
    name: str
    workers: int = 20
    soldiers: int = 0
    houses: int = 0
    attack_pct: float = 0.0
    # Defenses are a list of HP values (each tower starts at DEFENSE_HEALTH)
    defenses_hp: List[int] = field(default_factory=list)


@dataclass
class SimpleView:
    workers: int
    soldiers: int
    houses: int
    defenses: int
    attack_pct: float


@dataclass
class BotView:
    step: int
    me: SimpleView
    opp: SimpleView
    # economy: workers -> BASE_WORKERS_PER_STEP, soldiers -> HOUSE_WORKER_BONUS
    economy: SimpleView
    # costs: workers -> HOUSE_COST, soldiers -> DEFENSE_COST
    costs: SimpleView


# ================== CONSTANTS (SAFE TO TWEAK/HARDCODE) ==================

BASE_WORKERS_PER_STEP = 10
HOUSE_WORKER_BONUS = 3
WORKER_BONUS = 1.05  # ~5% bonus per step based on current workers

HOUSE_COST = 20
DEFENSE_COST = 20
DEFENSE_HEALTH = 30


# ================== HELPERS ==================

def spawn_workers(p: Player) -> int:
    bonus = int(p.workers * max(0.0, WORKER_BONUS - 1.0))
    before = p.workers
    p.workers += BASE_WORKERS_PER_STEP + p.houses * HOUSE_WORKER_BONUS + bonus
    return p.workers - before


def to_int_nonneg(val) -> int:
    try:
        n = int(float(val))
    except Exception:
        n = 0
    return max(0, n)


def to_float_01(val, default: float) -> float:
    try:
        f = float(val)
    except Exception:
        return default
    return max(0.0, min(1.0, f))


def sanitize_action(act: Dict, prev_attack_pct: float, workers_available: int) -> Dict:
    """Exactly one action per step. Clamp invalid inputs and cap by affordability.
    Accepted keys: convert, build_houses, build_defenses, attack_pct
    """
    convert = to_int_nonneg(act.get("convert", 0))
    build_h = to_int_nonneg(act.get("build_houses", 0))
    build_d = to_int_nonneg(act.get("build_defenses", 0))
    attack_raw = act.get("attack_pct", None)
    attack_pct = prev_attack_pct if attack_raw is None else to_float_01(attack_raw, prev_attack_pct)

    # Choose exactly one action; ignore extras if multiple provided
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


def apply_attack(attackers: int, defender: Player) -> Tuple[int, int, int]:
    """Resolve attackers against defender.
    Returns (destroyed_towers, killed_soldiers, killed_workers).
    Attackers deal 1 damage each. Damage hits defenses (HP) first, then soldiers 1:1, then workers 1:1.
    """
    destroyed_towers = 0
    killed_soldiers = 0
    killed_workers = 0

    # Defenses soak first
    i = 0
    while attackers > 0 and i < len(defender.defenses_hp):
        defender.defenses_hp[i] -= 1
        attackers -= 1
        if defender.defenses_hp[i] <= 0:
            destroyed_towers += 1
            defender.defenses_hp.pop(i)
            # don't advance i; next tower now at index i
        else:
            i += 1

    # Kill soldiers
    if attackers > 0 and defender.soldiers > 0:
        take = min(defender.soldiers, attackers)
        defender.soldiers -= take
        attackers -= take
        killed_soldiers += take

    # Kill workers
    if attackers > 0 and defender.workers > 0:
        take = min(defender.workers, attackers)
        defender.workers -= take
        attackers -= take
        killed_workers += take

    return destroyed_towers, killed_soldiers, killed_workers


def view_for(step: int, me: Player, opp: Player) -> BotView:
    return BotView(
        step=step,
        me=SimpleView(me.workers, me.soldiers, me.houses, len(me.defenses_hp), me.attack_pct),
        opp=SimpleView(opp.workers, opp.soldiers, opp.houses, len(opp.defenses_hp), opp.attack_pct),
        economy=SimpleView(BASE_WORKERS_PER_STEP, HOUSE_WORKER_BONUS, 0, 0, 0.0),
        costs=SimpleView(HOUSE_COST, DEFENSE_COST, 0, 0, 0.0),
    )


# ================== SIMULATOR ==================

def run_text_sim(bot_L: Callable[[BotView], Dict], bot_R: Callable[[BotView], Dict], *, steps: int = 200, seed: int | None = None) -> None:
    if seed is not None:
        random.seed(seed)

    L = Player(getattr(bot_L, "__name__", "LeftBot"))
    R = Player(getattr(bot_R, "__name__", "RightBot"))

    def fmt(p: Player) -> str:
        return f"W:{p.workers:4d} S:{p.soldiers:4d} H:{p.houses:2d} D:{len(p.defenses_hp):2d} A:{int(p.attack_pct*100):3d}%"

    for step in range(1, steps + 1):
        # Economy
        spawn_workers(L)
        spawn_workers(R)

        # Decisions (robust)
        try:
            aL_raw = bot_L(view_for(step, L, R)) or {}
        except Exception as e:
            print(f"[WARN] {L.name} error @ step {step}: {e}")
            aL_raw = {}
        try:
            aR_raw = bot_R(view_for(step, R, L)) or {}
        except Exception as e:
            print(f"[WARN] {R.name} error @ step {step}: {e}")
            aR_raw = {}

        aL = sanitize_action(aL_raw, L.attack_pct, L.workers)
        aR = sanitize_action(aR_raw, R.attack_pct, R.workers)

        # Apply actions
        send_L = send_R = 0
        action_str_L = "Wait"
        action_str_R = "Wait"

        if aL["kind"] == "build_houses" and aL["build_houses"] > 0:
            n = aL["build_houses"]
            L.houses += n; L.workers -= n * HOUSE_COST
            action_str_L = f"Build Houses x{n}"
        elif aL["kind"] == "build_defenses" and aL["build_defenses"] > 0:
            n = aL["build_defenses"]
            L.workers -= n * DEFENSE_COST
            L.defenses_hp.extend([DEFENSE_HEALTH] * n)
            action_str_L = f"Build Defenses x{n}"
        elif aL["kind"] == "convert" and aL.get("convert", 0) > 0:
            n = aL["convert"]
            L.soldiers += n; L.workers -= n
            action_str_L = f"Convert {n}"
        elif aL["kind"] == "attack":
            L.attack_pct = aL["attack_pct"]
            send_L = int(L.soldiers * L.attack_pct)
            L.soldiers -= send_L
            action_str_L = f"Attack {int(L.attack_pct*100)}% (send {send_L})"

        if aR["kind"] == "build_houses" and aR["build_houses"] > 0:
            n = aR["build_houses"]
            R.houses += n; R.workers -= n * HOUSE_COST
            action_str_R = f"Build Houses x{n}"
        elif aR["kind"] == "build_defenses" and aR["build_defenses"] > 0:
            n = aR["build_defenses"]
            R.workers -= n * DEFENSE_COST
            R.defenses_hp.extend([DEFENSE_HEALTH] * n)
            action_str_R = f"Build Defenses x{n}"
        elif aR["kind"] == "convert" and aR.get("convert", 0) > 0:
            n = aR["convert"]
            R.soldiers += n; R.workers -= n
            action_str_R = f"Convert {n}"
        elif aR["kind"] == "attack":
            R.attack_pct = aR["attack_pct"]
            send_R = int(R.soldiers * R.attack_pct)
            R.soldiers -= send_R
            action_str_R = f"Attack {int(R.attack_pct*100)}% (send {send_R})"

        # Resolve combat (simultaneous packets)
        dL, kLs, kLw = apply_attack(send_R, L)
        dR, kRs, kRw = apply_attack(send_L, R)

        # Print step summary
        print(f"\nStep {step}")
        print(f"  L action: {action_str_L}")
        print(f"  R action: {action_str_R}")
        if (send_L + send_R) > 0:
            print(f"  Hits on L: towers -{dL}, soldiers -{kLs}, workers -{kLw}")
            print(f"  Hits on R: towers -{dR}, soldiers -{kRs}, workers -{kRw}")
        print(f"  L: {fmt(L)}")
        print(f"  R: {fmt(R)}")

        # End condition: both troops and workers gone on a side
        left_dead = (L.soldiers <= 0 and L.workers <= 0 and len(L.defenses_hp) == 0)
        right_dead = (R.soldiers <= 0 and R.workers <= 0 and len(R.defenses_hp) == 0)
        if left_dead or right_dead:
            print("\n=== RESULT ===")
            if left_dead and right_dead:
                print("DRAW")
            elif right_dead:
                print(f"WINNER: {L.name}")
            else:
                print(f"WINNER: {R.name}")
            return

    # If steps exhausted
    print("\n=== RESULT (time limit) ===")
    score_L = L.workers + L.soldiers * 2 + len(L.defenses_hp) * 5 + L.houses * 3
    score_R = R.workers + R.soldiers * 2 + len(R.defenses_hp) * 5 + R.houses * 3
    if score_L == score_R:
        print("DRAW (scores equal)")
    elif score_L > score_R:
        print(f"WINNER (points): {L.name}")
    else:
        print(f"WINNER (points): {R.name}")


# ================== SAMPLE BOTS (EDIT BELOW) ==================

def greedy_rush(state: BotView) -> Dict:
    me = state.me
    spare = max(0, me.workers - 20)
    if me.soldiers > 0:
        return {"attack_pct": 0.5}
    if spare > 0:
        return {"convert": spare}
    return {}


# Starter: edit this function while you iterate.
def my_training_bot(state: BotView) -> Dict:
    me, opp = state.me, state.opp
    # Build a small economy, then convert and poke
    if me.houses < 3 and me.workers >= HOUSE_COST:
        return {"build_houses": 1}
    if me.soldiers >= max(6, opp.soldiers + 2):
        return {"attack_pct": 0.35}
    # keep ~10 workers around
    return {"convert": max(0, me.workers - 10)}


# ================== RUN A SAMPLE MATCH ==================
if __name__ == "__main__":
    run_text_sim(my_training_bot, greedy_rush, steps=150, seed=None)

