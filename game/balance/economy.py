"""Progression : expérience, niveaux et Poké Dollars (₽).

L'expérience ne vient que des combats : Pokémon sauvages et camps de la jungle (voir jungle.py),
boss et adversaires mis K.O. (XP_KO). Les alliés proches reçoivent une part de l'XP du
vainqueur (voir combat.py : XP_SHARE).
Paliers : XP_TABLE[n - 1] = XP pour passer du niveau n au niveau n+1 (niveau max : stats.py).
Rythme visé sur une partie de 10 min : Nv 3 vers 1 min, Nv 5 vers 2 min 30, Nv 7 vers 4 min,
Nv 10 (ultime) vers 6 min 30, niveau max en fin de partie pour les meilleurs.
Les boss donnent peu d'XP par rapport à leurs points : sinon l'équipe qui les bat s'envole.
"""

XP_TABLE = (50, 70, 105, 125, 150, 170, 190, 215, 240, 275, 310, 345, 380, 420)
XP_KO = 110


def xp_to_next(level):
    """XP pour passer du niveau `level` au suivant."""
    return XP_TABLE[min(level, len(XP_TABLE)) - 1]


# ---------------------------------------------------------------- expérience et ₽ des actions
# Les Pokémon neutres (camps, sauvages, boss) ont leurs gains dans jungle.py ('xp', 'gold').
XP_ASSIST = 40                 # XP d'une aide (en plus du partage avec les alliés proches)
XP_CAPTURE = 40                # XP de chaque Pokémon présent dans le cercle à la capture d'une arène
START_GOLD = 500               # ₽ au début de la partie
GOLD_KO = 350                  # ₽ pour avoir mis K.O. un adversaire
GOLD_ASSIST = 110              # ₽ pour une aide
GOLD_CAPTURE = 200             # ₽ pour chaque Pokémon présent à la capture d'une arène
# Rattrapage (contre l'effet boule de neige) :
CATCHUP_XP = .12               # +12 % d'XP par niveau de retard sur la moyenne des adversaires...
CATCHUP_MAX = .6               # ... jusqu'à +60 %
BOUNTY = .15                   # K.O. d'un adversaire de plus haut niveau : +15 % d'XP et de ₽ par niveau d'écart
GOLD_CAPTURE_TEAM = 50         # ₽ pour chaque autre Pokémon de l'équipe
