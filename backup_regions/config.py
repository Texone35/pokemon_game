"""Données du jeu : types, régions, Pokémon boss et attaques.

Pour équilibrer le jeu ou ajouter du contenu, c'est ici qu'il faut regarder.

Chaque attaque ennemie est décrite par un `kind` interprété par battle.py :
  - 'spread'  : salve de projectiles en éventail vers le joueur
  - 'stream'  : rafale rapide de projectiles successifs
  - 'nova'    : anneau de projectiles tirés dans toutes les directions
  - 'homing'  : projectiles qui suivent le joueur
  - 'zone'    : zone(s) d'impact annoncée(s) au sol puis explosion
  - 'charge'  : l'ennemi fonce sur le joueur (dégâts au contact)
  - 'beam'    : rayon annoncé par une ligne au sol, puis tir en ligne droite
  - 'wave'    : onde de choc circulaire qui s'élargit (à traverser en esquivant)
  - 'spiral'  : rafale de projectiles en spirale autour de l'ennemi

Option 'status' d'une attaque ennemie : ('burn', durée) = brûlure,
('slow', durée) = ralentissement.
"""
from ursina import color

WINDOW_SIZE = (1280, 720)
SHOW_FPS = True

# ---------------------------------------------------------------- monde
# L'île est découpée en 5 régions (parts de 72°) autour d'une place centrale.
WORLD_RADIUS = 118         # rayon de l'île
HUB_RADIUS = 20            # place centrale neutre
LAIR_DISTANCE = 68         # distance du centre au repaire du boss de chaque région
CHALLENGE_DISTANCE = 11.0  # distance au boss pour pouvoir le défier
DECOR_DENSITY = 1.0        # multiplicateur du nombre d'éléments de décor

# ---------------------------------------------------------------- combat
# Le combat a lieu sur place, dans un cercle de ce rayon autour du repaire.
BATTLE_ARENA_RADIUS = 18
INVULNERABILITY = 0.6      # secondes d'invincibilité après un coup

PLAYER = {
    'name': 'Pikachu',
    'type': 'electrik',
    'level': 25,
    'max_hp': 120,
    'speed': 8.0,
    'dash_speed': 26.0,
    'dash_time': 0.16,
    'dash_cooldown': 0.9,
    # Attaques de Pikachu : toutes au clavier, visée automatique sur l'adversaire.
    'moves': [
        {'key': 'j', 'name': 'Éclair', 'kind': 'bolt', 'cooldown': 0.33,
         'damage': 9, 'speed': 26, 'size': 0.55, 'color': color.rgb(1, .95, .25)},
        {'key': 'k', 'name': 'Vive-Attaque', 'kind': 'rush', 'cooldown': 2.5,
         'damage': 14, 'speed': 34, 'duration': 0.3},
        {'key': 'l', 'name': 'Tonnerre', 'kind': 'strike', 'cooldown': 5.0,
         'damage': 26, 'radius': 2.8, 'delay': 0.6, 'color': color.rgb(1, .95, .3)},
        {'key': 'u', 'name': 'Cage-Éclair', 'kind': 'stun', 'cooldown': 7.0,
         'damage': 5, 'speed': 15, 'size': 1.0, 'stun': 1.8, 'color': color.rgb(.6, .95, 1)},
        {'key': 'i', 'name': 'Queue de Fer', 'kind': 'spin', 'cooldown': 3.5,
         'damage': 16, 'radius': 3.4},
    ],
}

# Multiplicateur des dégâts d'Éclair (Électrik) contre chaque type.
EFFECTIVENESS = {
    'feu': 1.0,
    'eau': 1.5,
    'plante': 0.75,
    'roche': 0.75,
    'glace': 1.0,
}

# Ordre des régions autour de l'île (sens horaire en partant du nord).
# Chaque type a : 'region' (nom de la région), 'ground' / 'ground2' (couleurs
# du sol, mélangées par du bruit), 'shore' (rivage), 'sky' (ciel dans la
# région) et 'particles' (particules d'ambiance autour du joueur).
TYPE_ORDER = ['feu', 'eau', 'plante', 'roche', 'glace']

TYPES = {
    'feu': {
        'name': 'Feu',
        'region': 'Mont Brasier',
        'ground': color.rgb(.33, .24, .21),
        'ground2': color.rgb(.22, .17, .16),
        'shore': color.rgb(.2, .17, .17),
        'sky': (0.86, 0.6, 0.5, 1),
        'particles': {'color': color.rgb(1, .55, .15), 'rise': 1.6, 'drift': .6, 'size': .12, 'glow': True},
        'color': color.rgb(.93, .33, .15),
        'light': color.rgb(1, .62, .3),
        'dark': color.rgb(.45, .12, .06),
        'floor': color.rgb(.42, .26, .2),
        'fog': (0.95, 0.62, 0.45, 1),
        'pokemon': {
            'species': 'salameche',
            'name': 'Salamèche',
            'level': 22,
            'max_hp': 150,
            'speed': 6.0,
            'scale': 2.0,
            'radius': 1.1,
            'attack_interval': (1.3, 2.0),
        },
        'moves': [
            {'name': 'Flammèche', 'kind': 'spread', 'count': 5, 'angle': 50, 'speed': 13,
             'damage': 9, 'size': 0.8, 'color': color.rgb(1, .45, .1), 'status': ('burn', 2.5)},
            {'name': 'Déflagration', 'kind': 'zone', 'count': 1, 'radius': 4.5, 'delay': 1.0,
             'damage': 22, 'color': color.rgb(1, .3, .05)},
            {'name': 'Danse Flammes', 'kind': 'nova', 'count': 14, 'speed': 9,
             'damage': 8, 'size': 0.7, 'color': color.rgb(1, .6, .1)},
            {'name': 'Lance-Flammes', 'kind': 'beam', 'delay': 0.8, 'width': 2.2,
             'damage': 20, 'color': color.rgb(1, .4, .05), 'status': ('burn', 3.5)},
        ],
    },
    'eau': {
        'name': 'Eau',
        'region': 'Lagon Azur',
        'ground': color.rgb(.52, .78, .5),
        'ground2': color.rgb(.9, .84, .62),
        'shore': color.rgb(.95, .88, .66),
        'sky': (0.6, 0.82, 1.0, 1),
        'particles': {'color': color.rgb(.75, .92, 1), 'rise': .7, 'drift': .4, 'size': .1, 'glow': True},
        'color': color.rgb(.2, .5, .95),
        'light': color.rgb(.5, .78, 1),
        'dark': color.rgb(.06, .18, .45),
        'floor': color.rgb(.55, .75, .85),
        'fog': (0.55, 0.75, 0.98, 1),
        'pokemon': {
            'species': 'carapuce',
            'name': 'Carapuce',
            'level': 23,
            'max_hp': 175,
            'speed': 6.5,
            'scale': 2.0,
            'radius': 1.1,
            'attack_interval': (1.1, 1.8),
        },
        'moves': [
            {'name': 'Pistolet à O', 'kind': 'stream', 'count': 7, 'interval': 0.09, 'speed': 22,
             'damage': 6, 'size': 0.5, 'color': color.rgb(.35, .7, 1)},
            {'name': 'Surf', 'kind': 'wave', 'waves': 2, 'speed': 11, 'interval': 0.7,
             'damage': 14, 'color': color.rgb(.25, .6, 1)},
            {'name': 'Hydrocanon', 'kind': 'spread', 'count': 1, 'angle': 0, 'speed': 18,
             'damage': 20, 'size': 1.6, 'color': color.rgb(.1, .45, .95)},
            {'name': 'Siphon', 'kind': 'spiral', 'count': 36, 'arms': 2, 'interval': 0.05, 'spin': 22,
             'speed': 10, 'damage': 7, 'size': 0.6, 'color': color.rgb(.4, .75, 1)},
        ],
    },
    'plante': {
        'name': 'Plante',
        'region': 'Forêt Émeraude',
        'ground': color.rgb(.24, .52, .2),
        'ground2': color.rgb(.3, .6, .22),
        'shore': color.rgb(.8, .76, .55),
        'sky': (0.62, 0.84, 0.66, 1),
        'particles': {'color': color.rgb(.85, 1, .4), 'rise': -.5, 'drift': 1.2, 'size': .1, 'glow': True},
        'color': color.rgb(.3, .75, .3),
        'light': color.rgb(.6, .95, .45),
        'dark': color.rgb(.1, .3, .12),
        'floor': color.rgb(.35, .55, .25),
        'fog': (0.6, 0.85, 0.6, 1),
        'pokemon': {
            'species': 'bulbizarre',
            'name': 'Bulbizarre',
            'level': 24,
            'max_hp': 190,
            'speed': 5.0,
            'scale': 2.0,
            'radius': 1.2,
            'attack_interval': (1.2, 2.0),
        },
        'moves': [
            {'name': "Tranch'Herbe", 'kind': 'homing', 'count': 4, 'angle': 80, 'speed': 10,
             'turn': 2.2, 'damage': 8, 'size': 0.6, 'color': color.rgb(.45, .95, .3), 'life': 3.5},
            {'name': 'Vampigraine', 'kind': 'zone', 'count': 3, 'radius': 2.6, 'delay': 1.1,
             'damage': 12, 'color': color.rgb(.2, .7, .15), 'scatter': 5, 'heal': 6},
            {'name': 'Fouet Lianes', 'kind': 'spread', 'count': 3, 'angle': 20, 'speed': 17,
             'damage': 10, 'size': 0.6, 'color': color.rgb(.2, .6, .2)},
            {'name': 'Lance-Soleil', 'kind': 'beam', 'delay': 1.3, 'width': 3.0,
             'damage': 28, 'color': color.rgb(1, .95, .55)},
        ],
    },
    'roche': {
        'name': 'Roche',
        'region': 'Canyon Ocre',
        'ground': color.rgb(.74, .55, .36),
        'ground2': color.rgb(.62, .44, .3),
        'shore': color.rgb(.85, .72, .52),
        'sky': (0.88, 0.76, 0.6, 1),
        'particles': {'color': color.rgb(.8, .66, .48), 'rise': .2, 'drift': 2.4, 'size': .09, 'glow': False},
        'color': color.rgb(.62, .52, .38),
        'light': color.rgb(.8, .72, .55),
        'dark': color.rgb(.3, .25, .18),
        'floor': color.rgb(.55, .47, .36),
        'fog': (0.78, 0.7, 0.58, 1),
        'pokemon': {
            'species': 'racaillou',
            'name': 'Racaillou',
            'level': 26,
            'max_hp': 230,
            'speed': 5.5,
            'scale': 2.1,
            'radius': 1.3,
            'attack_interval': (1.4, 2.2),
        },
        'moves': [
            {'name': 'Jet-Pierres', 'kind': 'spread', 'count': 3, 'angle': 30, 'speed': 11,
             'damage': 14, 'size': 1.2, 'color': color.rgb(.55, .48, .4)},
            {'name': 'Roulade', 'kind': 'charge', 'speed': 24, 'duration': 0.9, 'damage': 20},
            {'name': 'Éboulement', 'kind': 'zone', 'count': 4, 'radius': 2.4, 'delay': 1.0,
             'damage': 16, 'color': color.rgb(.5, .4, .3), 'scatter': 6},
            {'name': 'Séisme', 'kind': 'wave', 'waves': 3, 'speed': 9, 'interval': 0.55,
             'damage': 15, 'color': color.rgb(.65, .5, .3)},
        ],
    },
    'glace': {
        'name': 'Glace',
        'region': 'Pic Givré',
        'ground': color.rgb(.9, .94, .98),
        'ground2': color.rgb(.78, .86, .95),
        'shore': color.rgb(.82, .9, .97),
        'sky': (0.82, 0.9, 1.0, 1),
        'particles': {'color': color.rgb(1, 1, 1), 'rise': -1.4, 'drift': .7, 'size': .13, 'glow': True},
        'color': color.rgb(.55, .88, .95),
        'light': color.rgb(.85, .97, 1),
        'dark': color.rgb(.2, .42, .55),
        'floor': color.rgb(.62, .76, .86),
        'fog': (0.85, 0.93, 1.0, 1),
        'pokemon': {
            'species': 'stalgamin',
            'name': 'Stalgamin',
            'level': 28,
            'max_hp': 210,
            'speed': 7.0,
            'scale': 2.1,
            'radius': 1.1,
            'attack_interval': (1.0, 1.6),
        },
        'moves': [
            {'name': 'Éclats Glace', 'kind': 'nova', 'count': 16, 'speed': 12,
             'damage': 8, 'size': 0.55, 'color': color.rgb(.7, .95, 1), 'waves': 3},
            {'name': 'Blizzard', 'kind': 'zone', 'count': 5, 'radius': 2.4, 'delay': 1.0,
             'damage': 13, 'color': color.rgb(.6, .9, 1), 'scatter': 7, 'status': ('slow', 2.5)},
            {'name': 'Laser Glace', 'kind': 'beam', 'delay': 0.7, 'width': 1.6,
             'damage': 16, 'color': color.rgb(.75, .97, 1), 'status': ('slow', 2.0)},
            {'name': 'Vent Glace', 'kind': 'spiral', 'count': 30, 'arms': 3, 'interval': 0.07, 'spin': -18,
             'speed': 9, 'damage': 6, 'size': 0.5, 'color': color.rgb(.8, 1, 1), 'status': ('slow', 1.5)},
        ],
    },
}
