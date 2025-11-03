from .config import HOUSE_COST, DEFENSE_COST

# Bots now pick exactly one action per step to align with the engine

def greedy_rush(state):
    me = state.me
    # Early: convert aggressively until we have a base army; then attack at 50%
    spare = max(0, me.workers - 20)
    
    if me.soldiers > 0:
        return {"attack_pct": 0.5}
    if spare > 0:
        return {"convert": spare}
    
    return {}

def boom_econ(state):
    me, opp = state.me, state.opp
    if me.houses < 5 and me.workers >= HOUSE_COST:
        return {"build_houses": 1}
    # After some buildup, start light pressure
    if state.step >= 8 and me.soldiers >= 10:
        return {"attack_pct": 0.35}
    # Otherwise grow army steadily
    amt = max(0, me.workers // 2)
    return {"convert": amt}

def turtle_defense(state):
    me = state.me
    want_def = 4
    if me.defenses < want_def and me.workers >= DEFENSE_COST:
        return {"build_defenses": 1}
    if me.soldiers >= 8:
        return {"attack_pct": 0.2}
    # trickle-convert
    amt = max(0, me.workers // 3)
    return {"convert": amt}

def adaptive_match(state):
    me, opp = state.me, state.opp
    # Scared? build defense
    if opp.soldiers > me.soldiers * 1.3 and me.workers >= DEFENSE_COST:
        return {"build_defenses": 1}
    # Build a small economy early
    if me.houses < 3 and me.workers >= HOUSE_COST:
        return {"build_houses": 1}
    # If we have an edge, pressure more
    if me.soldiers >= opp.soldiers * 1.1 and me.soldiers >= 6:
        return {"attack_pct": 0.45}
    # Otherwise convert conservatively, leave some workers
    amt = max(0, me.workers - 10)
    return {"convert": amt}


def king_bot(state):
    me, opp = state.me, state.opp
    my_pop = me.soldiers + me.workers
    opp_pop = opp.soldiers + opp.workers
    
    if me.soldiers > opp.soldiers + opp.workers:
        return {'attack_pct': 100}
    
    if my_pop > opp_pop * 1.5:
        return {'convert':me.workers * 0.5}
    
    if opp.soldiers > my_pop:
        difference = opp.soldiers - my_pop
        return {'build_defences': (difference //2) + 1}
    
    if me.soldiers > 200 :
        return {'attack_pct': 100}
    
    if my_pop > opp.soldiers * 1.2 :
        return {'build_houses': (( opp.soldiers) * (2/3))//20}
    
    return {'convert':my_pop * 0.045}
    
    
    
    
    