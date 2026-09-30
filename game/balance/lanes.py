"""Vagues de Pokémon neutres (sbires) sur les voies entre deux arènes voisines.

Règle : chaque arène contrôlée envoie régulièrement une vague vers chaque arène voisine (sur
l'anneau de voies) qu'elle ne possède pas. Entre une arène rouge et une arène bleue, les deux
vagues se croisent au milieu et s'annulent ; vers une arène neutre ou adverse, la vague aide à
l'attaquer : elle frappe la tour et accélère la capture (sans pouvoir capturer seule).
Dans une arène, les sbires qui la défendent bloquent la capture adverse tant qu'ils sont en vie.
"""
from game.balance.moves import melee, ranged, rgb

WAVES = {
    'interval': 30.0,          # secondes entre deux vagues sur une même voie
    'first': 10.0,             # délai de la première vague après une capture
    'composition': ['roucool', 'roucool', 'mystherbe'],     # une vague, de l'avant vers l'arrière
    'spacing': 1.8,            # écart entre deux sbires d'une vague
    'pool': 24,                # sbires par équipe au maximum en même temps
    'linger': 45.0,            # un sbire arrivé dans l'arène d'en face y reste au plus ce temps
}

# 'stats' : (PV, Att, Déf, AtS, DéS, Vit) à la première minute ; 'gold' et 'xp' : pour qui l'achève.
MINIONS = {
    'roucool': {'stats': (300, 32, 30, 20, 30, 50), 'move': 2.3, 'auto': melee(28, 2.2, 1.1), 'gold': 40, 'xp': 12},
    'mystherbe': {'stats': (220, 30, 22, 30, 25, 40), 'move': 2.3,
                  'auto': ranged(26, 8, 1.3, 16, .45, rgb(.6, .9, .4)), 'gold': 48, 'xp': 14},
}
MINION_GROWTH = {'hp': .08, 'atk': .08, 'def': .04, 'spd': .04}   # renforcement par minute de jeu

MINION_AGGRO = 7.0             # distance à laquelle un sbire engage un adversaire
MINION_LEASH = 9.0             # distance maximale à la voie quand il poursuit
MINION_CAPTURE = .15           # chaque sbire allié présent accélère la capture de 15 %
MINION_XP_SHARE = 12.0         # un sbire tué par un sbire ou une tour : XP partagée aux Pokémon à cette distance
