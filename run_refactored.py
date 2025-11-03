from game.run import run_game
from game.bots import greedy_rush, adaptive_match, boom_econ, king_bot

if __name__ == "__main__":
    run_game(adaptive_match,king_bot)

