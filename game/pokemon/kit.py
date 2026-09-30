"""Calculs tirés des valeurs d'équilibrage (game/balance/) : stats d'un Pokémon à un niveau donné,
son auto-attaque et ses attaques débloquées, dégâts bruts d'une attaque.

Ces fonctions ne dépendent que des données : les deux PC d'une partie à deux obtiennent
exactement les mêmes valeurs.
"""
from game import config as C

STAT_INDEX = {k: i for i, k in enumerate(C.STATS)}


# ---------------------------------------------------------------- lignées et builds
def builds_for(line):
    """Builds disponibles pour une lignée : [('standard', nom, description), ...]."""
    out = [('standard', 'Standard', C.ROLES[C.LINES[line]['role']]['name'])]
    for key, b in C.BUILDS.get(line, {}).items():
        out.append((key, b.get('name', key), b.get('desc', '')))
    return out


def build_cfg(line, build):
    return C.BUILDS.get(line, {}).get(build or 'standard', {})


def line_role(line, build=None):
    return build_cfg(line, build).get('role', C.LINES[line]['role'])


def line_curve(line, build=None):
    return build_cfg(line, build).get('curve', C.LINES[line]['curve'])


def stage_of(line, form):
    """Étape d'évolution d'une forme (0 : forme de base). Une forme hors de la lignée
    (Méga-évolution) compte comme la dernière étape."""
    forms = C.evolution_line(line)
    return forms.index(form) if form in forms else len(forms) - 1


# ---------------------------------------------------------------- stats
def role_stats(role, curve, level):
    r, c = C.ROLES[role], C.CURVES[curve]
    t = (max(1, min(level, C.MAX_LEVEL)) - 1) / (C.MAX_LEVEL - 1)
    f = t ** c['shape']
    return tuple(a * c['lv1'] + (b * c['max'] - a * c['lv1']) * f for a, b in zip(r['lv1'], r['max']))


def signature(form):
    base = C.BASE_STATS.get(form)
    if base is None:
        return (1.0,) * 6
    return tuple((v / C.SIGNATURE_REF) ** C.SIGNATURE_DAMP for v in base)


def team_stats(line, form, level, build=None):
    """Les six stats d'un Pokémon d'équipe (dictionnaire)."""
    rs = role_stats(line_role(line, build), line_curve(line, build), level)
    sig = signature(form)
    power = C.LINES[line].get('power', 1.0)
    bias = build_cfg(line, build).get('stats', {})
    return {k: rs[i] * sig[i] * power * bias.get(k, 1.0) for i, k in enumerate(C.STATS)}


def neutral_stats(species, minutes=0.0):
    """Stats d'un Pokémon neutre, renforcé selon le temps de jeu écoulé."""
    base = C.NEUTRALS[species]['stats']
    g = C.NEUTRAL_GROWTH
    return {k: base[i] * (1 + g.get(k, 0) * minutes) for i, k in enumerate(C.STATS)}


def scaled_stats(base, growth, minutes=0.0):
    """Stats (tuple dans l'ordre de STATS) renforcées selon le temps de jeu (tours, sbires)."""
    return {k: base[i] * (1 + growth.get(k, 0) * minutes) for i, k in enumerate(C.STATS)}


def attack_speed(spe):
    lo, hi = C.ATTACK_SPEED_LIMITS
    return max(lo, min(hi, 1 + C.ATTACK_SPEED_K * (spe / C.SPEED_REF - 1)))


def move_speed(spe):
    lo, hi = C.MOVE_SPEED_LIMITS
    return C.MOVE_SPEED * max(lo, min(hi, 1 + C.MOVE_SPEED_K * (spe / C.SPEED_REF - 1)))


# ---------------------------------------------------------------- attaques
def _scaled(mv, stage):
    """Attaque renforcée par l'étape d'évolution (puissance, taille des zones)."""
    mv = dict(mv)
    p, a = C.EVO_POWER[min(stage, len(C.EVO_POWER) - 1)], C.EVO_AREA[min(stage, len(C.EVO_AREA) - 1)]
    if 'power' in mv:
        mv['power'] = mv['power'] * p
    for k in ('radius', 'length', 'width'):
        if k in mv:
            mv[k] = mv[k] * a
    return mv


def kit(line, build=None):
    """Kit complet d'une lignée pour un build (le kit standard modifié par le build)."""
    k = dict(C.KITS[line])
    b = build_cfg(line, build)
    for slot in ('auto',) + C.SLOTS:
        if slot in b:
            k[slot] = b[slot]
    return k


def auto_for(line, form, build=None):
    """Auto-attaque d'un Pokémon d'équipe sous sa forme actuelle."""
    return _scaled(kit(line, build)['auto'], stage_of(line, form))


def moves_for(line, form, level=None, build=None):
    """Attaques d'un Pokémon d'équipe (emplacements 1 à 4 puis ultime), sous sa forme actuelle.
    Chaque attaque reçoit 'slot', 'key', 'aim' ('lock' ou 'skill'), et 'locked' / 'unlock'
    si elle n'est pas encore débloquée au niveau `level` (None : tout est débloqué)."""
    k = kit(line, build)
    stage = stage_of(line, form)
    forms = C.evolution_line(line)[1:stage + 1] + ([form] if form not in C.evolution_line(line) else [])
    out = []
    for slot in C.SLOTS:
        mv = _scaled(k[slot], stage)
        if (build or 'standard') == 'standard' or slot not in build_cfg(line, build):
            for f in forms:                              # noms et réglages propres aux évolutions
                mv.update(C.FORM_MOVES.get(f, {}).get(slot, {}))
        mv['slot'], mv['key'] = slot, C.KEYS[slot]
        mv.setdefault('aim', 'lock' if slot == 1 else 'skill')
        mv['unlock'] = C.UNLOCK[slot]
        mv['locked'] = level is not None and level < mv['unlock']
        out.append(mv)
    return out


def neutral_moves(species):
    sp = C.NEUTRALS[species].get('special')
    if not sp:
        return []
    return [dict(sp, slot=1, key='', aim='lock', unlock=1, locked=False)]


def raw_damage(power, off_stat, aim='lock'):
    """Dégâts bruts d'une attaque (avant défense, types et bonus)."""
    return power / 100 * (C.DAMAGE_FLAT + off_stat) * C.AIM_POWER.get(aim, 1.0)


def mitigation(defense):
    return C.DEFENSE_K / (C.DEFENSE_K + max(0.0, defense))


def heal_amount(power, spa):
    return power / 100 * (C.HEAL_FLAT + spa)


def cast_range(mv):
    """Portée à laquelle on peut viser (indicateur de visée, IA)."""
    k = mv['kind']
    if k in ('strike',):
        return mv.get('range', 12)
    if k == 'shot':
        return mv.get('range', 14)
    if k == 'beam':
        return mv['length']
    if k in ('rush', 'charge'):
        return mv['speed'] * mv['duration']
    if k == 'blink':
        return mv['distance']
    if k in ('spin', 'wave', 'heal'):
        return mv['radius']
    if k == 'nova':
        return mv['speed'] * 1.5
    return 14


def transform_of(line):
    """Transformation d'une lignée : ('mega', forme Méga) ou ('dynamax', None)."""
    mega = C.MEGA_FORMS.get(line)
    return ('mega', mega) if mega else ('dynamax', None)
