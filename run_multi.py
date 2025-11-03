from game_multi.run import run_game_multi
from game.bots import greedy_rush, boom_econ, turtle_defense, adaptive_match

if __name__ == "__main__":
    # Pick up to 6 bots — feel free to edit
    bots = [greedy_rush, boom_econ, turtle_defense, adaptive_match]
    run_game_multi(bots)

