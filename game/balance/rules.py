"""Règles de la partie : durée, score, réapparition, base, esquive, visée automatique, vision."""

# ---------------------------------------------------------------- partie
# Une partie dure 8 à 10 minutes : assez pour que les Pokémon évoluent deux fois.
# Rythme visé (mesuré sur des parties entre IA) : une équipe qui domine atteint l'objectif vers 8-9 min ; à égalité
# (2 arènes chacune), la partie va jusqu'au bout du temps et la meilleure équipe gagne.
MATCH_TIME = 10 * 60           # durée maximale (secondes) ; on gagne aussi en atteignant SCORE_TO_WIN
SCORE_TO_WIN = 1650
POINTS_KO = 8                  # points Dominion pour avoir mis K.O. un adversaire
ASSIST_TIME = 10.0             # un coup porté moins de 10 s avant un K.O. compte comme une aide

# ---------------------------------------------------------------- réapparition et base
RESPAWN_TIME = 6.0             # délai de réapparition en début de partie (secondes)
RESPAWN_PER_MIN = 1.2          # + ce délai par minute de jeu écoulée (18 s à 10 min : les arènes « maison »
                               # deviennent prenables en fin de partie, sans retour à la base)
RESPAWN_INVULN = 2.0           # invulnérabilité à la réapparition
BASE_RADIUS = 9
BASE_HEAL = 60                 # PV/s rendus dans sa propre base
BASE_DAMAGE = 80               # dégâts/s infligés aux ennemis qui entrent dans une base

# ---------------------------------------------------------------- hautes herbes
# Un Pokémon dans les hautes herbes est invisible pour l'équipe adverse, sauf si un
# adversaire est dans la même touffe ou tout près, ou s'il vient d'attaquer ou d'être touché.
BUSH = {'reveal': 1.2,          # secondes pendant lesquelles on reste visible après une attaque / un coup
        'sight': 3.0}           # distance à laquelle un adversaire voit quand même dans l'herbe

# ---------------------------------------------------------------- commandes (façon MOBA)
# Cliquer au sol envoie son Pokémon à cet endroit (il contourne les murs) ; cliquer sur un
# adversaire le fait approcher puis l'auto-attaquer. Z Q S D restent utilisables.
CONTROLS = {
    'move_buttons': ('right mouse', 'left mouse'),   # boutons qui déplacent (clic droit comme dans LoL)
    'drag_repeat': .15,        # bouton maintenu : la destination suit la souris (toutes les 0,15 s)
    'auto_acquire': True,      # à l'arrêt et sans ordre, attaque tout seul l'adversaire à portée
    'pick_radius': 1.5,        # tolérance (m) pour cliquer sur un adversaire
}

# ---------------------------------------------------------------- joueur et IA
# Esquive (Espace) : un bond rapide, rare comme le Flash de LoL (vers la souris ou les flèches).
PLAYER_DASH = {'speed': 30.0, 'time': .2, 'cooldown': 45.0}
AIM_ERROR = 7.0                # imprécision des tirs des IA (degrés) : on peut esquiver en se déplaçant
MELEE_WINDUP = .25             # délai avant qu'un coup au contact porte : on peut s'écarter à temps
TARGET_RANGE = 16              # portée de la visée automatique
VISION = 20                    # un adversaire n'apparaît sur la mini-carte qu'à cette distance d'un allié
