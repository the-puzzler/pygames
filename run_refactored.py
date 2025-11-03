from game.run import run_game
from game.bots import greedy_rush, adaptive_match, boom_econ

if __name__ == "__main__":
    run_game(boom_econ, adaptive_match)

