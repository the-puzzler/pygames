import math

def apply_attack_to_defenses(attackers, defenses):
    """Apply attackers as 1 damage per attacker to defense towers.
    Mutates defenses (list of dicts with x,y,hp). Returns (remaining_attackers, destroyed_positions, total_damage).
    """
    damage = 0
    destroyed = []
    if attackers <= 0 or not defenses:
        return attackers, destroyed, damage
    for t in list(defenses):
        if attackers <= 0:
            break
        hit = min(attackers, t.get('hp', 0))
        t['hp'] = t.get('hp', 0) - hit
        attackers -= hit
        damage += hit
        if t.get('hp', 0) <= 0:
            destroyed.append((t.get('x'), t.get('y')))
    # Remove destroyed
    defenses[:] = [t for t in defenses if t.get('hp', 0) > 0]
    return attackers, destroyed, damage

def resolve_attack_packet(attackers, defenses, defender_soldiers, defender_workers,
                          apply_defense_to_soldiers=True,
                          apply_defense_to_workers=True):
    """
    Attackers kill soldiers first, then workers.
    - Soldiers: needs ceil(defense_mult) attackers per defending soldier when apply_defense_to_soldiers.
      Otherwise needs 1 attacker per soldier (used for mid-clash visuals when both sides attack).
    - Workers: needs ceil(defense_mult) attackers per worker when apply_defense_to_workers, else 1:1.

    Returns new (def_soldiers, def_workers) after consuming attackers accordingly.
    """
    destroyed = []
    defense_damage = 0
    if attackers > 0 and defenses is not None:
        attackers, destroyed, defense_damage = apply_attack_to_defenses(attackers, defenses)

    if attackers <= 0:
        return defenses, defender_soldiers, defender_workers, destroyed, 0, 0, defense_damage

    need_s = 1 if not apply_defense_to_soldiers else 1
    need_w = 1 if not apply_defense_to_workers else 1

    # Soldiers next (1:1)
    killed_soldiers = min(defender_soldiers, attackers // need_s)
    attackers -= killed_soldiers * need_s
    defender_soldiers -= killed_soldiers

    # Then workers (1:1)
    killed_workers = min(defender_workers, attackers // need_w)
    attackers -= killed_workers * need_w
    defender_workers -= killed_workers

    return defenses, defender_soldiers, defender_workers, destroyed, killed_soldiers, killed_workers, defense_damage
