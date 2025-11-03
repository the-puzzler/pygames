# Bot Games for Python Workshop

Two small Pygame bot games I made for my weekly Python workshop (instead of our usual Kahoot). Students write simple Python functions to control a bot; we plug them into a match and watch them battle it out.

- Game 1: TRON / Light-Cycles (multi-bot, grid-based)
- Game 2: Workers & War (1v1 and 2–6 player variants)

Both are designed to be approachable in a single session, with a tiny API and immediate visual feedback.

Quick reference: see STUDENT_CHEATSHEET.txt for a compact summary of bot APIs, constants, and examples.

## Setup

Requires Python 3.12+. Dependencies: `pygame-ce`.

Options:

- With `uv` (recommended):
  - `uv run tron/main.py` (TRON)
  - `uv run run_refactored.py` (Workers & War 1v1)
  - `uv run run_multi.py` (Workers & War 2–6 players)

- With pip:
  - `python -m venv .venv && source .venv/bin/activate` (or your OS equivalent)
  - `pip install pygame-ce`
  - `python tron/main.py` or `python run_refactored.py` or `python run_multi.py`

Configuration knobs (window size, pacing, economy, costs) live in `game/config.py`.

## Game 1 — TRON / Light-Cycles

You control a snake-like light-cycle on a grid. Each tick, your bot returns one of: left, right, or straight. Running into walls or any trail crashes you. Last bot alive wins; head‑on collisions into the same cell eliminate both.

- Entry point: `tron/main.py`
- Register bots at the bottom: `BOTS = [...]`
- Bot state class: `class BotState`
- Game loop: `def run_match(...)`

### What your TRON bot receives (state)

`BotState` (read‑only):

- `me_index`: your index in the player list
- `pos`: `(gx, gy)` current grid position
- `heading`: one of `"E"`, `"N"`, `"W"`, `"S"`
- `alive_count`: number of players still alive
- `others`: list of `((gx, gy), alive_bool)` for each player
- `bounds`: `(0, GRID_W-1, 0, GRID_H-1)`
- `sensors`: dict of booleans — `ahead_free`, `left_free`, `right_free`

### How to write a TRON bot

Implement a function that takes `state` and returns `"L"`, `"R"`, or `"S"` (left, right, straight). Keep it short and robust: if in doubt, return `"S"`.

Example (place in `tron/main.py`, then add to `BOTS`):

```py
def right_hand_rule(state):
    s = state.sensors
    if s["right_free"]: return "R"
    if s["ahead_free"]: return "S"
    if s["left_free"]:  return "L"
    return "R"
```

Add it to the match by appending the function name to `BOTS` at the bottom of `tron/main.py`.

Run: `uv run tron/main.py` (or `python tron/main.py`).

## Game 2 — Workers & War

An economic tug‑of‑war. Each step, workers grow your economy; you choose one action: build houses, build defenses, convert workers into soldiers, or launch an attack with a percentage of your garrison. Defenses soak incoming damage and can be destroyed. Eliminate the opponent’s soldiers and workers to win.

- 1v1 entry: `run_refactored.py` (calls `game/run.py`)
- Multi‑player entry (2–6P): `run_multi.py` (calls `game_multi/run.py`)
- Example bots: `game/bots.py`
- Bot view: `game/model.py:228` (`class BotView`)
- One‑action rule: `game/run.py:13` (`sanitize_action`)
- 1v1 loop: `game/run.py:39` (`run_game`)

Headless practice (no graphics):
- Use `ww_headless.py` to simulate 1v1 in the terminal against a greedy opponent.
- Edit the `my_training_bot` at the bottom of the file and re-run.
- Run: `uv run ww_headless.py` (or `python ww_headless.py`).

Robustness: If a bot function raises an exception or returns invalid values, the engine treats it as a safe no‑op (Wait) for that step. Numeric inputs are clamped (e.g., build only as many as you can afford; negative or non‑numeric becomes 0; attack percentages are clamped to 0..1 and persist until changed).

### Turn structure and actions

Time is split into fixed PLAN steps. Each PLAN step your bot returns a dict with one action key; the engine performs exactly one action per step.

Allowed keys your bot may return:

- `{"convert": N}` — convert `N` workers into `N` soldiers
- `{"build_houses": N}` — spend `N * HOUSE_COST` workers to build `N` houses
- `{"build_defenses": N}` — spend `N * DEFENSE_COST` workers to add `N` defense towers
- `{"attack_pct": p}` — set attack percentage `p` (0..1) and send that fraction of your garrison this step

Return only one key per step; if you send more than one, the engine will perform a single action and ignore the rest. The engine also clamps by available workers and valid ranges. Attack percentage persists between steps until you change it.

Economy per step (see `game/config.py` and `PlayerState.spawn_workers`):

- Base: `BASE_WORKERS_PER_STEP`
- Per house: `HOUSE_WORKER_BONUS`
- Small compounding bonus: `int(workers * (WORKER_BONUS - 1.0))`

Combat summary (1v1 and multi):

- Attackers deal 1 damage each.
- Damage is applied to defenses first (towers have HP), then soldiers (1:1), then workers (1:1).
- In 1v1, you lose when both your soldiers and workers reach 0 (towers alone don’t keep you alive).

### What your Workers & War bot receives (state)

`BotView` contains simple, read‑only counters:

- `state.step`: current step number
- `state.me`: your stats — `workers`, `soldiers`, `houses`, `defenses`, `attack_pct`
- `state.opp`: opponent’s stats (same fields)
- `state.economy`: constants — `BASE_WORKERS_PER_STEP`, `HOUSE_WORKER_BONUS`
- `state.costs`: constants — `HOUSE_COST`, `DEFENSE_COST`

### How to write a Workers & War bot

Implement `def my_bot(state):` that returns a dict with one of the keys above. Keep returns small and valid; the engine will sanitize amounts and ranges.

Examples (see more in `game/bots.py`):

```py
def greedy_rush(state):
    me = state.me
    spare = max(0, me.workers - 20)
    if me.soldiers > 0:
        return {"attack_pct": 0.5}
    if spare > 0:
        return {"convert": spare}
    return {}

def adaptive_match(state):
    me, opp = state.me, state.opp
    from game.config import HOUSE_COST, DEFENSE_COST
    if opp.soldiers > me.soldiers * 1.3 and me.workers >= DEFENSE_COST:
        return {"build_defenses": 1}
    if me.houses < 3 and me.workers >= HOUSE_COST:
        return {"build_houses": 1}
    if me.soldiers >= max(6, opp.soldiers * 1.1):
        return {"attack_pct": 0.45}
    return {"convert": max(0, me.workers - 10)}
```

### How to plug your bot into a match

- 1v1: Edit `run_refactored.py` and pass your functions to `run_game`:

```py
from game.run import run_game
from game.bots import greedy_rush
from my_bots import my_bot

if __name__ == "__main__":
    run_game(my_bot, greedy_rush)
```

Run: `uv run run_refactored.py` (or `python run_refactored.py`).

- Multi‑player (2–6 bots): Edit `run_multi.py` and update the `bots = [...]` list, then run `uv run run_multi.py`.

## Tips for Students

- Start simple; return nothing or a single action while you print/inspect state.
- In TRON, prefer safe moves over clever ones — staying alive often wins.
- In Workers & War, balance economy (houses), defense (towers), and pressure (attack percentage). Converting all workers too early can stall your growth.
- Keep functions pure and fast; avoid long computations per tick/step.

## Credits

Made for my weekly Python workshop students as a fun alternative to our usual Kahoot. Have fun tinkering and competing!
