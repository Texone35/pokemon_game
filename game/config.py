"""Données du jeu Pokémon Dominion : carte, arènes, espèces, équipes, objectifs.

Pour équilibrer le jeu ou ajouter du contenu, c'est ici qu'il faut regarder.

Repère de la carte : x vers l'Est, z vers le Nord, centre du stade en (0, 0).

Attaques de base ('attack') :
  - 'ranged' : projectile vers la cible
  - 'melee'  : coup au contact
Capacités spéciales ('special', lancées automatiquement par l'IA) :
  - 'beam'   : rayon annoncé puis tiré en ligne droite
  - 'wave'   : onde de choc circulaire autour du lanceur
  - 'zone'   : zone d'impact annoncée au sol sous la cible
  - 'nova'   : anneau de projectiles
  - 'charge' : fonce sur la cible
  - 'heal'   : soigne les alliés proches
Statuts : ('burn', durée) brûlure, ('slow', durée) ralentissement.
"""
from ursina import color

WINDOW_SIZE = (1280, 720)
SHOW_FPS = True

# ---------------------------------------------------------------- qualité graphique
# Valeurs prudentes, fluides sur une puce graphique intégrée (Intel).
# Sur un PC plus puissant : msaa = 4, tree_spacing = 3.4, crowd = .6, grass = 2500.
QUALITY = {
    'msaa': 0,                 # anticrénelage matériel : 0, 2 ou 4 (très lourd sur puce Intel)
    'shadow_resolution': 4096, # finesse des ombres
    'tree_spacing': 3.7,       # écart moyen entre les arbres de la jungle (plus petit = plus dense)
    'crowd': .45,              # proportion de sièges occupés dans les tribunes
    'grass': 1400,             # touffes d'herbe et de fleurs
    'relief': 1.0,             # hauteur des collines (0 = sol plat)
}

# ---------------------------------------------------------------- partie
MATCH_TIME = 30 * 60           # durée maximale (secondes) ; on gagne aussi en atteignant SCORE_TO_WIN
SCORE_TO_WIN = 1000
POINTS_PER_ARENA = 1.0         # points Dominion par seconde et par arène contrôlée
POINTS_KO = 8                  # points pour avoir mis K.O. un adversaire
RESPAWN_TIME = 8.0             # + 0.25 s par minute de jeu écoulée

# ---------------------------------------------------------------- carte
FIELD_RADIUS = 118             # terrain de jeu (entouré par les tribunes)
ARENA_RADIUS = 14              # zone de capture d'une arène
CAPTURE_TIME = 8.0             # secondes pour capturer une arène seul (depuis neutre)
CAPTURE_BONUS_PER_UNIT = 0.35  # chaque allié en plus accélère la capture
BASE_RADIUS = 9
BASE_HEAL = 60                 # PV/s rendus dans sa propre base
BASE_DAMAGE = 80               # dégâts/s infligés aux ennemis qui entrent dans une base
PIT_RADIUS = 11
TREE_SPACING = 4.2             # densité de la jungle
# Hautes herbes : un Pokémon qui s'y trouve est invisible pour l'équipe adverse, sauf si un
# adversaire est dans la même touffe ou tout près, ou s'il vient d'attaquer ou d'être touché.
BUSH = {'reveal': 1.2,          # secondes pendant lesquelles on reste visible après une attaque / un coup
        'sight': 3.0}           # distance à laquelle un adversaire voit quand même dans l'herbe

TEAMS = {
    'rouge': {'name': 'Rouge', 'color': color.rgb(.92, .2, .2), 'light': color.rgb(1, .55, .5),
              'base': (-36, -100)},
    'bleu': {'name': 'Bleue', 'color': color.rgb(.2, .45, .95), 'light': color.rgb(.55, .75, 1),
             'base': (36, -100)},
}

ARENAS = [
    {'key': 'nord', 'name': 'Arène Nord', 'type': 'roche', 'pos': (0, 82), 'weather': 'sable'},
    {'key': 'ouest', 'name': 'Arène Ouest', 'type': 'plante', 'pos': (-77, 22), 'weather': 'pollen'},
    {'key': 'est', 'name': 'Arène Est', 'type': 'electrik', 'pos': (77, 22), 'weather': 'orage'},
    {'key': 'sud_ouest', 'name': 'Arène Sud-Ouest', 'type': 'eau', 'pos': (-74, -42), 'weather': 'pluie'},
    {'key': 'sud_est', 'name': 'Arène Sud-Est', 'type': 'feu', 'pos': (74, -42), 'weather': 'soleil'},
]
WEATHER_BONUS = 1.2            # dégâts des Pokémon du type de l'arène quand ils y combattent

# Bonus d'équipe tant qu'elle contrôle l'arène du type correspondant.
ARENA_BONUS = {
    'roche': ('defense', .10, '-10 % dégâts subis'),
    'plante': ('regen', 3.0, '+3 PV/s'),
    'electrik': ('speed', .10, '+10 % vitesse'),
    'eau': ('cooldown', .10, '-10 % recharge'),
    'feu': ('damage', .10, '+10 % dégâts'),
}

# ---------------------------------------------------------------- types
TYPES = {
    'feu': {'name': 'Feu', 'color': color.rgb(.93, .33, .15), 'light': color.rgb(1, .62, .3),
            'dark': color.rgb(.45, .12, .06), 'floor': color.rgb(.55, .3, .22)},
    'eau': {'name': 'Eau', 'color': color.rgb(.2, .5, .95), 'light': color.rgb(.5, .78, 1),
            'dark': color.rgb(.06, .18, .45), 'floor': color.rgb(.4, .62, .8)},
    'plante': {'name': 'Plante', 'color': color.rgb(.3, .75, .3), 'light': color.rgb(.6, .95, .45),
               'dark': color.rgb(.1, .3, .12), 'floor': color.rgb(.38, .6, .3)},
    'roche': {'name': 'Roche', 'color': color.rgb(.62, .52, .38), 'light': color.rgb(.85, .74, .55),
              'dark': color.rgb(.3, .25, .18), 'floor': color.rgb(.62, .5, .36)},
    'electrik': {'name': 'Électrik', 'color': color.rgb(.98, .8, .15), 'light': color.rgb(1, .93, .45),
                 'dark': color.rgb(.5, .38, .05), 'floor': color.rgb(.75, .66, .35)},
    'glace': {'name': 'Glace', 'color': color.rgb(.55, .88, .95), 'light': color.rgb(.85, .97, 1),
              'dark': color.rgb(.2, .42, .55), 'floor': color.rgb(.7, .82, .9)},
    'normal': {'name': 'Normal', 'color': color.rgb(.7, .65, .6), 'light': color.rgb(.9, .88, .82),
               'dark': color.rgb(.35, .32, .3), 'floor': color.rgb(.6, .6, .55)},
    'psy': {'name': 'Psy', 'color': color.rgb(.75, .35, .85), 'light': color.rgb(.9, .65, 1),
            'dark': color.rgb(.3, .1, .4), 'floor': color.rgb(.45, .3, .55)},
}

# multiplicateur attaquant -> défenseur (1.0 si absent)
TYPE_CHART = {
    ('feu', 'plante'): 1.25, ('feu', 'glace'): 1.25, ('feu', 'eau'): .8, ('feu', 'roche'): .8,
    ('eau', 'feu'): 1.25, ('eau', 'roche'): 1.25, ('eau', 'plante'): .8,
    ('plante', 'eau'): 1.25, ('plante', 'roche'): 1.25, ('plante', 'feu'): .8,
    ('electrik', 'eau'): 1.25, ('electrik', 'plante'): .8,
    ('roche', 'feu'): 1.25, ('roche', 'glace'): 1.25,
    ('glace', 'plante'): 1.25, ('glace', 'feu'): .8,
}

# ---------------------------------------------------------------- espèces
SPECIES = {
    'pikachu': {'name': 'Pikachu', 'type': 'electrik', 'hp': 330, 'speed': 7.2, 'radius': .6, 'scale': 1.35,
                'attack': {'kind': 'ranged', 'range': 13, 'damage': 22, 'cooldown': .6, 'speed': 28,
                           'size': .5, 'color': color.rgb(1, .95, .25)}},
    'salameche': {'name': 'Salamèche', 'type': 'feu', 'hp': 340, 'speed': 6.6, 'radius': .6, 'scale': 1.35,
                  'attack': {'kind': 'ranged', 'range': 12, 'damage': 24, 'cooldown': .8, 'speed': 22,
                             'size': .6, 'color': color.rgb(1, .45, .1)},
                  'special': {'name': 'Lance-Flammes', 'kind': 'beam', 'damage': 70, 'width': 2.2, 'length': 16,
                              'delay': .7, 'cooldown': 7, 'color': color.rgb(1, .4, .05), 'status': ('burn', 3)}},
    'carapuce': {'name': 'Carapuce', 'type': 'eau', 'hp': 430, 'speed': 6.2, 'radius': .6, 'scale': 1.35,
                 'attack': {'kind': 'ranged', 'range': 11, 'damage': 19, 'cooldown': .7, 'speed': 22,
                            'size': .5, 'color': color.rgb(.35, .7, 1)},
                 'special': {'name': 'Surf', 'kind': 'wave', 'damage': 45, 'radius': 8, 'speed': 12,
                             'cooldown': 8, 'color': color.rgb(.25, .6, 1)}},
    'bulbizarre': {'name': 'Bulbizarre', 'type': 'plante', 'hp': 400, 'speed': 6.0, 'radius': .7, 'scale': 1.35,
                   'attack': {'kind': 'ranged', 'range': 11, 'damage': 16, 'cooldown': .8, 'speed': 18,
                              'size': .55, 'color': color.rgb(.45, .95, .3), 'shape': 'leaf'},
                   'special': {'name': 'Synthèse', 'kind': 'heal', 'heal': 90, 'radius': 9, 'cooldown': 10,
                               'color': color.rgb(.5, 1, .45)}},
    'racaillou': {'name': 'Racaillou', 'type': 'roche', 'hp': 540, 'speed': 5.8, 'radius': .8, 'scale': 1.3,
                  'attack': {'kind': 'melee', 'range': 2.8, 'damage': 34, 'cooldown': 1.0},
                  'special': {'name': 'Roulade', 'kind': 'charge', 'damage': 55, 'speed': 24, 'duration': .7,
                              'cooldown': 7}},
    'stalgamin': {'name': 'Stalgamin', 'type': 'glace', 'hp': 360, 'speed': 6.6, 'radius': .6, 'scale': 1.35,
                  'attack': {'kind': 'ranged', 'range': 12, 'damage': 21, 'cooldown': .75, 'speed': 24,
                             'size': .5, 'color': color.rgb(.7, .95, 1), 'shape': 'shard'},
                  'special': {'name': 'Blizzard', 'kind': 'zone', 'damage': 55, 'radius': 3.6, 'delay': .9,
                              'cooldown': 8, 'color': color.rgb(.6, .9, 1), 'status': ('slow', 2.5)}},
    # ---- Pokémon neutres de la jungle et boss
    'rattata': {'name': 'Rattata', 'type': 'normal', 'hp': 200, 'speed': 5.2, 'radius': .5, 'scale': 1.2,
                'attack': {'kind': 'melee', 'range': 2.2, 'damage': 10, 'cooldown': 1.0}},
    # petits Pokémon sauvages : faibles, ils rapportent surtout de l'expérience
    'chenipan': {'name': 'Chenipan', 'type': 'plante', 'hp': 90, 'speed': 3, 'radius': .45, 'scale': 1.15,
                 'attack': {'kind': 'melee', 'range': 2.0, 'damage': 4, 'cooldown': 1.3}},
    'roucool': {'name': 'Roucool', 'type': 'normal', 'hp': 110, 'speed': 4.5, 'radius': .5, 'scale': 1.15,
                'attack': {'kind': 'melee', 'range': 2.2, 'damage': 6, 'cooldown': 1.2}},
    'mystherbe': {'name': 'Mystherbe', 'type': 'plante', 'hp': 100, 'speed': 3.4, 'radius': .45, 'scale': 1.2,
                  'attack': {'kind': 'melee', 'range': 2.0, 'damage': 5, 'cooldown': 1.2}},
    'magmar': {'name': 'Magmar', 'type': 'feu', 'hp': 950, 'speed': 5, 'radius': 1.0, 'scale': 1.9,
               'attack': {'kind': 'ranged', 'range': 10, 'damage': 22, 'cooldown': 1.1, 'speed': 16,
                          'size': .8, 'color': color.rgb(1, .45, .1)},
               'special': {'name': 'Déflagration', 'kind': 'zone', 'damage': 50, 'radius': 4, 'delay': 1.0,
                           'cooldown': 6, 'color': color.rgb(1, .3, .05), 'status': ('burn', 2.5)}},
    'lokhlass': {'name': 'Lokhlass', 'type': 'eau', 'hp': 1000, 'speed': 5, 'radius': 1.3, 'scale': 1.8,
                 'attack': {'kind': 'ranged', 'range': 10, 'damage': 20, 'cooldown': 1.0, 'speed': 16,
                            'size': .7, 'color': color.rgb(.4, .75, 1)},
                 'special': {'name': 'Hydrocanon', 'kind': 'wave', 'damage': 40, 'radius': 8, 'speed': 10,
                             'cooldown': 7, 'color': color.rgb(.3, .6, 1)}},
    'torterra': {'name': 'Torterra', 'type': 'plante', 'hp': 1200, 'speed': 5, 'radius': 1.5, 'scale': 1.7,
                 'attack': {'kind': 'melee', 'range': 3.5, 'damage': 38, 'cooldown': 1.4},
                 'special': {'name': 'Séisme', 'kind': 'wave', 'damage': 45, 'radius': 9, 'speed': 9,
                             'cooldown': 7, 'color': color.rgb(.6, .48, .3)}},
    'mewtwo': {'name': 'Mewtwo', 'type': 'psy', 'hp': 2600, 'speed': 5, 'radius': 1.3, 'scale': 2.2,
               'attack': {'kind': 'ranged', 'range': 13, 'damage': 30, 'cooldown': .9, 'speed': 20,
                          'size': .8, 'color': color.rgb(.85, .45, 1)},
               'special': {'name': 'Psyko', 'kind': 'nova', 'damage': 26, 'count': 18, 'speed': 11,
                           'cooldown': 5, 'color': color.rgb(.8, .4, 1), 'size': .7}},
    'regigigas': {'name': 'Regigigas', 'type': 'normal', 'hp': 6500, 'speed': 4.5, 'radius': 2.0, 'scale': 2.4,
                  'attack': {'kind': 'melee', 'range': 4.5, 'damage': 60, 'cooldown': 1.6},
                  'special': {'name': 'Presse', 'kind': 'wave', 'damage': 70, 'radius': 12, 'speed': 9,
                              'cooldown': 6, 'color': color.rgb(.95, .9, .75)}},
}

# ---------------------------------------------------------------- équipes
# 'role' : où l'IA va de préférence (clé d'arène, 'jungle' ou 'libre').
# Les rôles suivent la répartition de la carte (Nord : ADC + support, jungle,
# Ouest/Est : mid, Sud-Ouest/Sud-Est : bruiser), en miroir pour l'équipe bleue.
ROSTERS = {
    'rouge': [
        {'species': 'pikachu', 'role': 'libre', 'player': True},
        {'species': 'salameche', 'role': 'nord'},
        {'species': 'bulbizarre', 'role': 'nord'},
        {'species': 'carapuce', 'role': 'ouest'},
        {'species': 'racaillou', 'role': 'sud_ouest'},
    ],
    'bleu': [
        {'species': 'stalgamin', 'role': 'jungle'},
        {'species': 'salameche', 'role': 'nord'},
        {'species': 'bulbizarre', 'role': 'nord'},
        {'species': 'carapuce', 'role': 'est'},
        {'species': 'racaillou', 'role': 'sud_est'},
    ],
}

# ---------------------------------------------------------------- joueurs
PLAYABLE = ['pikachu', 'salameche', 'carapuce', 'bulbizarre', 'racaillou', 'stalgamin']
PLAYABLE_ROLE = {                  # courte description affichée dans le salon
    'pikachu': 'Rapide et mobile, attaques électriques à distance',
    'salameche': 'Gros dégâts de feu, brûle ses cibles',
    'carapuce': 'Solide, repousse les groupes avec Surf',
    'bulbizarre': 'Soutien : soigne les alliés proches',
    'racaillou': 'Colosse au contact, fonce dans la mêlée',
    'stalgamin': 'Contrôle : ralentit et étourdit les adversaires',
}

PLAYER_DASH = {'speed': 22.0, 'time': .16, 'cooldown': 1.0}
AIM_ERROR = 7.0                # imprécision des tirs des IA (degrés) : on peut esquiver en se déplaçant
MELEE_WINDUP = .25             # délai avant qu'un coup au contact porte : on peut s'écarter à temps

# Attaques des Pokémon jouables (touches J K L U I). Sortes d'attaque :
#   'basic'   : attaque de base de l'espèce (maintenir J)
#   'rush'    : fonce sur la cible, invulnérable pendant la ruée
#   'strike'  : zone annoncée sous la cible puis impact ('style' : 'lightning' ou 'explosion')
#   'homing'  : projectile à tête chercheuse ('stun' : étourdit, 'status' : brûlure/ralentissement)
#   'spin'    : onde de choc autour de soi qui renvoie les projectiles proches
#   'special' : capacité spéciale de l'espèce (voir SPECIES)
MOVESETS = {
    'pikachu': [
        {'key': 'j', 'name': 'Éclair', 'kind': 'basic'},
        {'key': 'k', 'name': 'Vive-Attaque', 'kind': 'rush', 'cooldown': 4.0, 'damage': 40, 'speed': 34,
         'duration': .3},
        {'key': 'l', 'name': 'Tonnerre', 'kind': 'strike', 'cooldown': 6.0, 'damage': 75, 'radius': 3.2,
         'delay': .6, 'color': color.rgb(1, .95, .3), 'style': 'lightning'},
        {'key': 'u', 'name': 'Cage-Éclair', 'kind': 'homing', 'cooldown': 9.0, 'damage': 15, 'speed': 16,
         'size': 1.0, 'stun': 1.6, 'color': color.rgb(.6, .95, 1), 'shape': 'cage'},
        {'key': 'i', 'name': 'Queue de Fer', 'kind': 'spin', 'cooldown': 5.0, 'damage': 45, 'radius': 3.6},
    ],
    'salameche': [
        {'key': 'j', 'name': 'Flammèche', 'kind': 'basic'},
        {'key': 'k', 'name': 'Vive-Attaque', 'kind': 'rush', 'cooldown': 4.5, 'damage': 38, 'speed': 32,
         'duration': .3},
        {'key': 'l', 'name': 'Lance-Flammes', 'kind': 'special', 'cooldown': 7.0},
        {'key': 'u', 'name': 'Danse Flammes', 'kind': 'strike', 'cooldown': 8.0, 'damage': 60, 'radius': 3.6,
         'delay': .7, 'color': color.rgb(1, .4, .05), 'style': 'explosion', 'status': ('burn', 3)},
        {'key': 'i', 'name': 'Draco-Queue', 'kind': 'spin', 'cooldown': 5.0, 'damage': 42, 'radius': 3.6,
         'color': color.rgb(1, .6, .3)},
    ],
    'carapuce': [
        {'key': 'j', 'name': 'Pistolet à O', 'kind': 'basic'},
        {'key': 'k', 'name': 'Aqua-Jet', 'kind': 'rush', 'cooldown': 4.0, 'damage': 36, 'speed': 34,
         'duration': .3},
        {'key': 'l', 'name': 'Surf', 'kind': 'special', 'cooldown': 8.0},
        {'key': 'u', 'name': "Bulles d'O", 'kind': 'homing', 'cooldown': 7.0, 'damage': 25, 'speed': 15,
         'size': .9, 'color': color.rgb(.4, .75, 1), 'status': ('slow', 2.5)},
        {'key': 'i', 'name': 'Repli', 'kind': 'spin', 'cooldown': 6.0, 'damage': 35, 'radius': 3.8,
         'color': color.rgb(.5, .8, 1)},
    ],
    'bulbizarre': [
        {'key': 'j', 'name': "Tranch'Herbe", 'kind': 'basic'},
        {'key': 'k', 'name': 'Charge', 'kind': 'rush', 'cooldown': 5.0, 'damage': 34, 'speed': 30,
         'duration': .3},
        {'key': 'l', 'name': 'Synthèse', 'kind': 'special', 'cooldown': 10.0},
        {'key': 'u', 'name': 'Poudre Dodo', 'kind': 'homing', 'cooldown': 10.0, 'damage': 12, 'speed': 14,
         'size': 1.0, 'stun': 1.4, 'color': color.rgb(.75, .6, 1)},
        {'key': 'i', 'name': 'Tempête Florale', 'kind': 'spin', 'cooldown': 6.0, 'damage': 40, 'radius': 4.2,
         'color': color.rgb(.6, 1, .5)},
    ],
    'racaillou': [
        {'key': 'j', 'name': 'Charge', 'kind': 'basic'},
        {'key': 'k', 'name': 'Roulade', 'kind': 'special', 'cooldown': 6.0},
        {'key': 'l', 'name': 'Éboulement', 'kind': 'strike', 'cooldown': 7.0, 'damage': 70, 'radius': 3.6,
         'delay': .7, 'color': color.rgb(.75, .6, .4), 'style': 'explosion'},
        {'key': 'u', 'name': 'Jet-Pierres', 'kind': 'homing', 'cooldown': 9.0, 'damage': 30, 'speed': 17,
         'size': .9, 'stun': 1.2, 'color': color.rgb(.7, .6, .45), 'shape': 'rock'},
        {'key': 'i', 'name': 'Ampleur', 'kind': 'spin', 'cooldown': 5.5, 'damage': 50, 'radius': 4.5,
         'color': color.rgb(.8, .7, .5)},
    ],
    'stalgamin': [
        {'key': 'j', 'name': 'Éclats Glace', 'kind': 'basic'},
        {'key': 'k', 'name': 'Vive-Attaque', 'kind': 'rush', 'cooldown': 4.5, 'damage': 36, 'speed': 32,
         'duration': .3},
        {'key': 'l', 'name': 'Blizzard', 'kind': 'special', 'cooldown': 8.0},
        {'key': 'u', 'name': 'Laser Glace', 'kind': 'homing', 'cooldown': 8.0, 'damage': 28, 'speed': 20,
         'size': .8, 'stun': .8, 'color': color.rgb(.7, .95, 1), 'shape': 'shard', 'status': ('slow', 2.5)},
        {'key': 'i', 'name': 'Vent Glace', 'kind': 'spin', 'cooldown': 6.0, 'damage': 38, 'radius': 4.0,
         'color': color.rgb(.75, .95, 1), 'status': ('slow', 2.0)},
    ],
}


def build_roster(team, humans=()):
    """Équipe `team` : les Pokémon choisis par les joueurs humains d'abord, puis des IA.

    Les IA gardent les rôles de ROSTERS (dans l'ordre) et prennent de préférence une
    espèce qu'aucun joueur n'a choisie."""
    if team != 'rouge' or not humans:
        return [dict(e, player=False) for e in ROSTERS[team]]
    roster = [{'species': s, 'role': 'libre', 'player': True, 'human': i} for i, s in enumerate(humans)]
    bots = [e for e in ROSTERS[team] if not e.get('player')]
    if len(humans) > 1:            # deux joueurs : un seul Pokémon de l'IA au Nord
        bots = [bots[0]] + bots[2:]
    taken = set(humans)
    pool = ['salameche', 'bulbizarre', 'carapuce', 'racaillou', 'stalgamin', 'pikachu']
    for e in bots[:5 - len(humans)]:
        s = e['species']
        if s in taken:
            s = next((p for p in pool if p not in taken), s)
        taken.add(s)
        roster.append({'species': s, 'role': e['role'], 'player': False})
    return roster


# ---------------------------------------------------------------- multijoueur
NET = {
    'port': 47650,             # port TCP et UDP de l'hôte (à ouvrir sur la box si l'UPnP ne marche pas)
    'snapshot_rate': 20,       # états du monde envoyés par seconde (hôte -> invité)
    'input_rate': 30,          # positions envoyées par seconde (invité -> hôte)
    'interp_delay': .1,        # retard volontaire de l'affichage chez l'invité (lisse les à-coups du réseau)
    'upnp': True,              # ouvrir automatiquement le port sur la box (UPnP)
}
TARGET_RANGE = 16              # portée de la visée automatique
VISION = 20                    # un adversaire n'apparaît sur la mini-carte qu'à cette distance d'un allié

# ---------------------------------------------------------------- progression
XP_PER_LEVEL = 120             # XP pour passer du niveau n au niveau n+1 : n * XP_PER_LEVEL
MAX_LEVEL = 12
LEVEL_BONUS = .07              # +7 % PV et dégâts par niveau
XP_PASSIVE = 1.5               # XP/s pour tous
XP_KO = 90

# ---------------------------------------------------------------- jungle et objectifs
BUFFS = {
    'braise': {'name': 'Braise ardente', 'desc': '+25 % dégâts', 'duration': 90, 'color': color.rgb(1, .4, .15)},
    'flux': {'name': 'Flux marin', 'desc': '-30 % recharge, +4 PV/s', 'duration': 90, 'color': color.rgb(.35, .7, 1)},
    'bastion': {'name': 'Bastion végétal', 'desc': '-25 % dégâts subis', 'duration': 90, 'color': color.rgb(.4, .9, .35)},
    'psy': {'name': 'Aura psychique', 'desc': '+20 % dégâts, -20 % subis', 'duration': 75, 'color': color.rgb(.8, .45, 1)},
}

# Camps symétriques (Ouest / Est). 'buff' : bonus pour le Pokémon qui achève le camp.
CAMPS = [
    {'species': 'magmar', 'pos': (-50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'magmar', 'pos': (50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'lokhlass', 'pos': (-34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'lokhlass', 'pos': (34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'torterra', 'pos': (-24, 42), 'buff': 'bastion', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'torterra', 'pos': (24, 42), 'buff': 'bastion', 'respawn': 90, 'xp': 110, 'points': 10},
    {'species': 'rattata', 'count': 3, 'pos': (-58, -16), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (58, -16), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-50, -72), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (50, -72), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-86, 58), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (86, 58), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (-24, 70), 'respawn': 45, 'xp': 40, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (24, 70), 'respawn': 45, 'xp': 40, 'points': 3},
]
CAMP_LEASH = 16                # un Pokémon neutre ne s'éloigne pas plus de son camp

# Petits Pokémon sauvages dispersés dans toute la jungle (en plus des camps).
WILD = {
    'count': 34,                               # nombre d'emplacements
    'species': ['chenipan', 'roucool', 'mystherbe', 'rattata'],
    'hp_factor': .55,                          # les Rattata sauvages sont plus faibles que ceux des camps
    'xp': 32, 'points': 1, 'respawn': 40,
    'leash': 9,                                # distance de poursuite maximale
    'wander': 3.5,                             # rayon de promenade autour de leur coin
}

# Boss légendaires du Boss Pit (centre de la carte).
LEGENDARY = {'species': 'mewtwo', 'first_spawn': 180, 'respawn': 240, 'xp': 250, 'points': 120, 'buff': 'psy'}
FINAL_BOSS = {'species': 'regigigas', 'spawn': 20 * 60, 'xp': 400, 'points': 300, 'buff': 'psy'}
