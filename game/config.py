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
    'detail': 1.0,             # grain du sol et de la roche (0 = couleurs unies, un peu plus léger)
}

# ---------------------------------------------------------------- partie
# Une partie dure 8 à 10 minutes : assez pour que les Pokémon évoluent deux fois.
# Rythme visé : une équipe qui tient 3 arènes atteint l'objectif vers 8 min ; à égalité
# (2 arènes chacune), la partie va jusqu'au bout du temps et la meilleure équipe gagne.
MATCH_TIME = 10 * 60           # durée maximale (secondes) ; on gagne aussi en atteignant SCORE_TO_WIN
SCORE_TO_WIN = 1200
# points Dominion par seconde selon le nombre d'arènes tenues (0 à 5) : chaque arène de plus
# rapporte un peu moins, pour qu'une équipe qui domine ne termine pas la partie trop vite
ARENA_POINTS = (0, .6, 1.2, 1.6, 1.9, 2.1)
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
              'base': (-36, -102)},
    'bleu': {'name': 'Bleue', 'color': color.rgb(.2, .45, .95), 'light': color.rgb(.55, .75, 1),
             'base': (36, -102)},
}

ARENAS = [
    {'key': 'nord', 'name': 'Arène Nord', 'type': 'roche', 'pos': (0, 82), 'weather': 'sable'},
    {'key': 'ouest', 'name': 'Arène Ouest', 'type': 'plante', 'pos': (-77, 22), 'weather': 'pollen'},
    {'key': 'est', 'name': 'Arène Est', 'type': 'electrik', 'pos': (77, 22), 'weather': 'orage'},
    {'key': 'sud_ouest', 'name': 'Arène Sud-Ouest', 'type': 'eau', 'pos': (-74, -42), 'weather': 'pluie'},
    {'key': 'sud_est', 'name': 'Arène Sud-Est', 'type': 'feu', 'pos': (74, -42), 'weather': 'soleil'},
]

# Effets du terrain selon le type du Pokémon, dans une arène (son cercle de capture) ou dans la
# rivière : 'dmg' dégâts infligés, 'taken' dégâts subis, 'speed' vitesse (+.2 = +20 %).
# '*' : tous les autres types. Un Pokémon du type de l'arène y est plus fort ; les types qui
# « craignent » ce terrain y sont gênés (un Pokémon Électrik mouillé, un Pokémon Feu sous la pluie...).
ZONE_EFFECTS = {
    'eau': {'eau': {'dmg': .2, 'speed': .1}, 'glace': {'dmg': .1},
            'electrik': {'dmg': -.15, 'taken': .15}, 'feu': {'dmg': -.2, 'speed': -.1}, 'roche': {'speed': -.1}},
    'feu': {'feu': {'dmg': .2, 'speed': .1}, 'dragon': {'dmg': .1},
            'plante': {'dmg': -.15, 'taken': .15}, 'glace': {'dmg': -.2, 'taken': .1}, 'eau': {'dmg': .1}},
    'plante': {'plante': {'dmg': .2, 'speed': .1}, 'feu': {'dmg': .1}, 'eau': {'dmg': -.1},
               'roche': {'speed': -.1}},
    'electrik': {'electrik': {'dmg': .2, 'speed': .15}, 'eau': {'taken': .15, 'speed': -.1},
                 'roche': {'taken': -.1}},
    'roche': {'roche': {'dmg': .2, 'taken': -.1}, 'combat': {'dmg': .1}, 'electrik': {'dmg': -.15},
              'feu': {'speed': -.1}},
    'riviere': {'eau': {'speed': .2}, 'glace': {'speed': .1}, 'feu': {'speed': -.2, 'dmg': -.1},
                'electrik': {'dmg': -.1, 'taken': .1}, 'roche': {'speed': -.15}, 'spectre': {},
                '*': {'speed': -.08}},
}
ZONE_NAMES = {'eau': 'Arène Eau', 'feu': 'Arène Feu', 'plante': 'Arène Plante', 'electrik': 'Arène Électrik',
              'roche': 'Arène Roche', 'riviere': 'Rivière'}


def zone_effect(zone, ptype):
    """Effets du terrain `zone` sur un Pokémon de type `ptype` (dictionnaire, vide si aucun)."""
    z = ZONE_EFFECTS.get(zone)
    if not z:
        return {}
    return z.get(ptype, z.get('*', {}))


def zone_text(eff):
    """Résumé lisible : « +20 % dégâts, -10 % vitesse »."""
    names = (('dmg', 'dégâts'), ('taken', 'dégâts subis'), ('speed', 'vitesse'))
    return ', '.join(f"{'+' if eff[k] > 0 else ''}{round(eff[k] * 100)} % {n}" for k, n in names if eff.get(k))


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
    'combat': {'name': 'Combat', 'color': color.rgb(.8, .32, .2), 'light': color.rgb(1, .6, .45),
               'dark': color.rgb(.4, .12, .08), 'floor': color.rgb(.55, .35, .3)},
    'spectre': {'name': 'Spectre', 'color': color.rgb(.45, .3, .68), 'light': color.rgb(.72, .58, .95),
                'dark': color.rgb(.18, .1, .3), 'floor': color.rgb(.35, .28, .45)},
    'dragon': {'name': 'Dragon', 'color': color.rgb(.38, .35, .95), 'light': color.rgb(.65, .62, 1),
               'dark': color.rgb(.12, .1, .4), 'floor': color.rgb(.35, .35, .6)},
}

# multiplicateur attaquant -> défenseur (1.0 si absent)
TYPE_CHART = {
    ('feu', 'plante'): 1.25, ('feu', 'glace'): 1.25, ('feu', 'eau'): .8, ('feu', 'roche'): .8,
    ('eau', 'feu'): 1.25, ('eau', 'roche'): 1.25, ('eau', 'plante'): .8,
    ('plante', 'eau'): 1.25, ('plante', 'roche'): 1.25, ('plante', 'feu'): .8,
    ('electrik', 'eau'): 1.25, ('electrik', 'plante'): .8,
    ('roche', 'feu'): 1.25, ('roche', 'glace'): 1.25,
    ('glace', 'plante'): 1.25, ('glace', 'feu'): .8,
    ('glace', 'dragon'): 1.25, ('dragon', 'dragon'): 1.25,
    ('combat', 'roche'): 1.25, ('combat', 'glace'): 1.25, ('combat', 'normal'): 1.25, ('combat', 'psy'): .8,
    ('combat', 'spectre'): .8, ('psy', 'combat'): 1.25, ('spectre', 'psy'): 1.25, ('spectre', 'spectre'): 1.25,
    ('spectre', 'normal'): .8, ('normal', 'spectre'): .8, ('eau', 'dragon'): .8, ('feu', 'dragon'): .8,
    ('plante', 'dragon'): .8, ('electrik', 'dragon'): .8,
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
    # ---- évolutions des Pokémon jouables (voir EVOLUTIONS) : plus robustes, plus forts,
    #      et une capacité spéciale plus puissante pour l'IA
    'raichu': {'name': 'Raichu', 'type': 'electrik', 'hp': 380, 'speed': 7.4, 'radius': .65, 'scale': 1.5,
               'attack': {'kind': 'ranged', 'range': 13.5, 'damage': 25, 'cooldown': .65, 'speed': 30,
                          'size': .55, 'color': color.rgb(1, .95, .25)},
               'special': {'name': 'Tonnerre', 'kind': 'zone', 'damage': 75, 'radius': 3.4, 'delay': .6,
                           'cooldown': 7, 'color': color.rgb(1, .95, .3), 'style': 'lightning'}},
    'mega_raichu': {'name': 'Méga-Raichu', 'type': 'electrik', 'hp': 440, 'speed': 7.7, 'radius': .75,
                    'scale': 1.7,
                    'attack': {'kind': 'ranged', 'range': 14, 'damage': 28, 'cooldown': .62, 'speed': 32,
                               'size': .65, 'color': color.rgb(.75, .95, 1)},
                    'special': {'name': 'Fatal-Foudre', 'kind': 'zone', 'damage': 100, 'radius': 4.2, 'delay': .6,
                                'cooldown': 7, 'color': color.rgb(.8, .95, 1), 'style': 'lightning'}},
    'reptincel': {'name': 'Reptincel', 'type': 'feu', 'hp': 400, 'speed': 6.8, 'radius': .65, 'scale': 1.5,
                  'attack': {'kind': 'ranged', 'range': 12.5, 'damage': 28, 'cooldown': .8, 'speed': 23,
                             'size': .65, 'color': color.rgb(1, .45, .1)},
                  'special': {'name': 'Lance-Flammes', 'kind': 'beam', 'damage': 85, 'width': 2.4, 'length': 17,
                              'delay': .7, 'cooldown': 7, 'color': color.rgb(1, .4, .05), 'status': ('burn', 3)}},
    'dracaufeu': {'name': 'Dracaufeu', 'type': 'feu', 'hp': 480, 'speed': 7.0, 'radius': .85, 'scale': 1.8,
                  'attack': {'kind': 'ranged', 'range': 13, 'damage': 33, 'cooldown': .8, 'speed': 24,
                             'size': .75, 'color': color.rgb(1, .45, .1)},
                  'special': {'name': 'Lance-Flammes', 'kind': 'beam', 'damage': 110, 'width': 2.8, 'length': 19,
                              'delay': .7, 'cooldown': 7, 'color': color.rgb(1, .4, .05), 'status': ('burn', 3.5)}},
    'carabaffe': {'name': 'Carabaffe', 'type': 'eau', 'hp': 490, 'speed': 6.4, 'radius': .65, 'scale': 1.5,
                  'attack': {'kind': 'ranged', 'range': 11.5, 'damage': 22, 'cooldown': .7, 'speed': 23,
                             'size': .55, 'color': color.rgb(.35, .7, 1)},
                  'special': {'name': 'Surf', 'kind': 'wave', 'damage': 58, 'radius': 9, 'speed': 12,
                              'cooldown': 8, 'color': color.rgb(.25, .6, 1)}},
    'tortank': {'name': 'Tortank', 'type': 'eau', 'hp': 580, 'speed': 6.4, 'radius': .9, 'scale': 1.75,
                'attack': {'kind': 'ranged', 'range': 12, 'damage': 26, 'cooldown': .7, 'speed': 25,
                           'size': .65, 'color': color.rgb(.35, .7, 1)},
                'special': {'name': 'Hydrocanon', 'kind': 'beam', 'damage': 100, 'width': 2.6, 'length': 18,
                            'delay': .8, 'cooldown': 8, 'color': color.rgb(.3, .65, 1)}},
    'herbizarre': {'name': 'Herbizarre', 'type': 'plante', 'hp': 460, 'speed': 6.2, 'radius': .75, 'scale': 1.5,
                   'attack': {'kind': 'ranged', 'range': 11.5, 'damage': 19, 'cooldown': .8, 'speed': 19,
                              'size': .6, 'color': color.rgb(.45, .95, .3), 'shape': 'leaf'},
                   'special': {'name': 'Synthèse', 'kind': 'heal', 'heal': 115, 'radius': 9.5, 'cooldown': 10,
                               'color': color.rgb(.5, 1, .45)}},
    'florizarre': {'name': 'Florizarre', 'type': 'plante', 'hp': 560, 'speed': 6.2, 'radius': .95, 'scale': 1.7,
                   'attack': {'kind': 'ranged', 'range': 12, 'damage': 23, 'cooldown': .8, 'speed': 20,
                              'size': .7, 'color': color.rgb(.45, .95, .3), 'shape': 'leaf'},
                   'special': {'name': 'Synthèse', 'kind': 'heal', 'heal': 145, 'radius': 10, 'cooldown': 10,
                               'color': color.rgb(.5, 1, .45)}},
    'gravalanch': {'name': 'Gravalanch', 'type': 'roche', 'hp': 620, 'speed': 6.0, 'radius': .9, 'scale': 1.45,
                   'attack': {'kind': 'melee', 'range': 3.0, 'damage': 40, 'cooldown': 1.0},
                   'special': {'name': 'Roulade', 'kind': 'charge', 'damage': 70, 'speed': 25, 'duration': .75,
                               'cooldown': 7}},
    'grolem': {'name': 'Grolem', 'type': 'roche', 'hp': 720, 'speed': 6.0, 'radius': 1.05, 'scale': 1.6,
               'attack': {'kind': 'melee', 'range': 3.3, 'damage': 48, 'cooldown': 1.0},
               'special': {'name': 'Roulade', 'kind': 'charge', 'damage': 90, 'speed': 27, 'duration': .8,
                           'cooldown': 7}},
    'oniglali': {'name': 'Oniglali', 'type': 'glace', 'hp': 430, 'speed': 6.8, 'radius': .8, 'scale': 1.45,
                 'attack': {'kind': 'ranged', 'range': 12.5, 'damage': 25, 'cooldown': .75, 'speed': 25,
                            'size': .6, 'color': color.rgb(.7, .95, 1), 'shape': 'shard'},
                 'special': {'name': 'Blizzard', 'kind': 'zone', 'damage': 70, 'radius': 4.0, 'delay': .9,
                             'cooldown': 8, 'color': color.rgb(.6, .9, 1), 'status': ('slow', 2.5)}},
    'mega_oniglali': {'name': 'Méga-Oniglali', 'type': 'glace', 'hp': 510, 'speed': 7.0, 'radius': .9,
                      'scale': 1.6,
                      'attack': {'kind': 'ranged', 'range': 13, 'damage': 30, 'cooldown': .7, 'speed': 26,
                                 'size': .7, 'color': color.rgb(.7, .95, 1), 'shape': 'shard'},
                      'special': {'name': 'Blizzard', 'kind': 'zone', 'damage': 92, 'radius': 4.6, 'delay': .9,
                                  'cooldown': 8, 'color': color.rgb(.6, .9, 1), 'status': ('slow', 3)}},
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
                             'cooldown': 7, 'color': color.rgb(.6, .48, .3), 'fx': 'roche'}},
    'mewtwo': {'name': 'Mewtwo', 'type': 'psy', 'hp': 2600, 'speed': 5, 'radius': 1.3, 'scale': 2.2,
               'attack': {'kind': 'ranged', 'range': 13, 'damage': 30, 'cooldown': .9, 'speed': 20,
                          'size': .8, 'color': color.rgb(.85, .45, 1)},
               'special': {'name': 'Psyko', 'kind': 'nova', 'damage': 26, 'count': 18, 'speed': 11,
                           'cooldown': 5, 'color': color.rgb(.8, .4, 1), 'size': .7}},
    'regigigas': {'name': 'Regigigas', 'type': 'normal', 'hp': 6500, 'speed': 4.5, 'radius': 2.0, 'scale': 2.4,
                  'attack': {'kind': 'melee', 'range': 4.5, 'damage': 60, 'cooldown': 1.6},
                  'special': {'name': 'Presse', 'kind': 'wave', 'damage': 70, 'radius': 12, 'speed': 9,
                              'cooldown': 6, 'color': color.rgb(.95, .9, .75), 'fx': 'roche'}},
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


# ---------------------------------------------------------------- évolutions
# Chaque Pokémon jouable évolue deux fois en montant de niveau. Au début, seules les touches
# J K L sont disponibles ; la 1re évolution débloque U, la 2e débloque I, et certaines attaques
# sont remplacées par des versions plus puissantes (EVOLVED_MOVES).
# Pikachu et Stalgamin n'ont qu'une évolution dans les jeux : leur 2e étape est une Méga-Évolution.
EVOLUTIONS = {
    'pikachu': [(3, 'raichu'), (7, 'mega_raichu')],
    'salameche': [(3, 'reptincel'), (7, 'dracaufeu')],
    'carapuce': [(3, 'carabaffe'), (7, 'tortank')],
    'bulbizarre': [(3, 'herbizarre'), (7, 'florizarre')],
    'racaillou': [(3, 'gravalanch'), (7, 'grolem')],
    'stalgamin': [(3, 'oniglali'), (7, 'mega_oniglali')],
}
UNLOCK = {'u': 1, 'i': 2}      # étape d'évolution qui débloque la touche

# Attaques remplacées (ou renforcées) à chaque évolution, par touche. Elles restent acquises
# à l'étape suivante, sauf si celle-ci les remplace à son tour.
EVOLVED_MOVES = {
    'raichu': {
        'k': {'name': 'Vive-Attaque', 'kind': 'rush', 'cooldown': 4.0, 'damage': 50, 'speed': 36, 'duration': .3},
        'l': {'name': 'Tonnerre', 'kind': 'strike', 'cooldown': 6.0, 'damage': 90, 'radius': 3.5, 'delay': .6,
              'color': color.rgb(1, .95, .3), 'style': 'lightning'},
    },
    'mega_raichu': {
        'k': {'name': 'Électacle', 'kind': 'rush', 'cooldown': 4.0, 'damage': 72, 'speed': 40, 'duration': .35,
              'stun': .6},
        'l': {'name': 'Fatal-Foudre', 'kind': 'strike', 'cooldown': 6.0, 'damage': 115, 'radius': 4.3,
              'delay': .6, 'color': color.rgb(.8, .95, 1), 'style': 'lightning'},
        'i': {'name': 'Queue de Fer', 'kind': 'spin', 'cooldown': 5.0, 'damage': 68, 'radius': 4.4},
    },
    'reptincel': {
        'k': {'name': 'Crocs Feu', 'kind': 'rush', 'cooldown': 4.5, 'damage': 50, 'speed': 33, 'duration': .3,
              'status': ('burn', 2.5)},
    },
    'dracaufeu': {
        'k': {'name': 'Vol', 'kind': 'rush', 'cooldown': 4.0, 'damage': 66, 'speed': 42, 'duration': .38},
        'i': {'name': 'Déflagration', 'kind': 'strike', 'cooldown': 8.0, 'damage': 120, 'radius': 4.6,
              'delay': .8, 'color': color.rgb(1, .35, .05), 'style': 'explosion', 'status': ('burn', 4)},
    },
    'carabaffe': {
        'k': {'name': 'Aqua-Jet', 'kind': 'rush', 'cooldown': 4.0, 'damage': 46, 'speed': 35, 'duration': .3},
    },
    'tortank': {
        'k': {'name': 'Coud\'Krâne', 'kind': 'rush', 'cooldown': 4.5, 'damage': 64, 'speed': 32, 'duration': .35,
              'stun': .8},
        'i': {'name': 'Vague Géante', 'kind': 'spin', 'cooldown': 7.0, 'damage': 80, 'radius': 6.5,
              'color': color.rgb(.3, .65, 1), 'status': ('slow', 2.0)},
    },
    'herbizarre': {
        'k': {'name': 'Fouet Lianes', 'kind': 'rush', 'cooldown': 4.5, 'damage': 44, 'speed': 32, 'duration': .3},
    },
    'florizarre': {
        'k': {'name': 'Bélier', 'kind': 'rush', 'cooldown': 4.5, 'damage': 62, 'speed': 32, 'duration': .35,
              'stun': .6},
        'i': {'name': 'Lance-Soleil', 'kind': 'beam', 'cooldown': 9.0, 'damage': 125, 'length': 18,
              'width': 2.6, 'delay': 1.0, 'color': color.rgb(.75, 1, .45)},
    },
    'gravalanch': {
        'l': {'name': 'Éboulement', 'kind': 'strike', 'cooldown': 7.0, 'damage': 85, 'radius': 3.9, 'delay': .7,
              'color': color.rgb(.75, .6, .4), 'style': 'explosion'},
    },
    'grolem': {
        'l': {'name': 'Lame de Roc', 'kind': 'strike', 'cooldown': 7.0, 'damage': 110, 'radius': 4.4,
              'delay': .7, 'color': color.rgb(.75, .6, .4), 'style': 'explosion', 'stun': .8},
        'i': {'name': 'Séisme', 'kind': 'spin', 'cooldown': 7.0, 'damage': 85, 'radius': 7.0,
              'color': color.rgb(.8, .7, .5)},
    },
    'oniglali': {
        'k': {'name': 'Crocs Givre', 'kind': 'rush', 'cooldown': 4.5, 'damage': 48, 'speed': 33, 'duration': .3,
              'status': ('slow', 2.0)},
    },
    'mega_oniglali': {
        'k': {'name': 'Crocs Givre', 'kind': 'rush', 'cooldown': 4.0, 'damage': 64, 'speed': 36, 'duration': .32,
              'status': ('slow', 2.5)},
        'i': {'name': 'Avalanche', 'kind': 'strike', 'cooldown': 8.0, 'damage': 115, 'radius': 4.8, 'delay': .8,
              'color': color.rgb(.75, .95, 1), 'style': 'explosion', 'status': ('slow', 3)},
    },
}


# ---------------------------------------------------------------- Pokémon supplémentaires
# Dix lignées de plus, chacune avec trois formes. _line crée les trois espèces : PV +18 % puis
# +40 %, dégâts de l'attaque de base +11 % puis +24 %, portée un peu plus longue.
def _line(keys, names, type_, hp, speed, radius, scale, attack, specials, role):
    for i, (k, n) in enumerate(zip(keys, names)):
        g = (1.0, 1.18, 1.4)[i]
        a = dict(attack, damage=round(attack['damage'] * (1 + (g - 1) * .6)), range=attack['range'] + .4 * i)
        SPECIES[k] = {'name': n, 'type': type_, 'hp': round(hp * g), 'speed': round(speed + .15 * i, 2),
                      'radius': radius[i], 'scale': scale[i], 'attack': a, 'special': specials[i]}
    EVOLUTIONS[keys[0]] = [(3, keys[1]), (7, keys[2])]
    PLAYABLE_ROLE[keys[0]] = role


rgb = color.rgb
FIRE_C, WATER_C, GRASS_C = rgb(1, .45, .1), rgb(.35, .7, 1), rgb(.45, .95, .3)
PSY_C, FIGHT_C, GHOST_C = rgb(.85, .45, 1), rgb(1, .55, .3), rgb(.55, .35, .85)
DRAGON_C, ELEC_C, ROCK_C, ICE_C = rgb(.5, .45, 1), rgb(1, .95, .3), rgb(.75, .6, .4), rgb(.7, .95, 1)

_line(('hericendre', 'feurisson', 'typhlosion'), ('Héricendre', 'Feurisson', 'Typhlosion'), 'feu',
      320, 6.8, (.6, .7, .9), (1.3, 1.5, 1.75),
      {'kind': 'ranged', 'range': 12.5, 'damage': 24, 'cooldown': .8, 'speed': 22, 'size': .6, 'color': FIRE_C},
      [{'name': 'Roue de Feu', 'kind': 'wave', 'damage': 45, 'radius': 7, 'speed': 12, 'cooldown': 8,
        'color': FIRE_C, 'status': ('burn', 2)},
       {'name': 'Roue de Feu', 'kind': 'wave', 'damage': 58, 'radius': 8, 'speed': 12, 'cooldown': 8,
        'color': FIRE_C, 'status': ('burn', 2.5)},
       {'name': 'Roue de Feu', 'kind': 'wave', 'damage': 76, 'radius': 9, 'speed': 13, 'cooldown': 8,
        'color': FIRE_C, 'status': ('burn', 3)}],
      'Mage de feu : grosses explosions, plus fort en pleine santé')
_line(('kaiminus', 'crocrodil', 'aligatueur'), ('Kaiminus', 'Crocrodil', 'Aligatueur'), 'eau',
      400, 6.4, (.65, .8, 1.0), (1.3, 1.55, 1.8),
      {'kind': 'melee', 'range': 2.8, 'damage': 32, 'cooldown': .9},
      [{'name': 'Aqua-Jet', 'kind': 'charge', 'damage': 50, 'speed': 26, 'duration': .55, 'cooldown': 7},
       {'name': 'Aqua-Jet', 'kind': 'charge', 'damage': 66, 'speed': 27, 'duration': .6, 'cooldown': 7},
       {'name': 'Aqua-Jet', 'kind': 'charge', 'damage': 86, 'speed': 29, 'duration': .65, 'cooldown': 7}],
      'Cogneur : mord au contact et se soigne en frappant')
_line(('arcko', 'massko', 'jungko'), ('Arcko', 'Massko', 'Jungko'), 'plante',
      300, 7.4, (.55, .65, .75), (1.3, 1.5, 1.7),
      {'kind': 'melee', 'range': 2.6, 'damage': 28, 'cooldown': .6},
      [{'name': 'Lame-Feuille', 'kind': 'charge', 'damage': 48, 'speed': 30, 'duration': .4, 'cooldown': 6},
       {'name': 'Lame-Feuille', 'kind': 'charge', 'damage': 64, 'speed': 32, 'duration': .42, 'cooldown': 6},
       {'name': 'Lame-Feuille', 'kind': 'charge', 'damage': 84, 'speed': 34, 'duration': .45, 'cooldown': 6}],
      'Assassin : très rapide, file à travers les hautes herbes')
_line(('abra', 'kadabra', 'alakazam'), ('Abra', 'Kadabra', 'Alakazam'), 'psy',
      280, 6.6, (.55, .62, .7), (1.3, 1.5, 1.65),
      {'kind': 'ranged', 'range': 13, 'damage': 25, 'cooldown': .75, 'speed': 24, 'size': .55, 'color': PSY_C},
      [{'name': 'Psyko', 'kind': 'nova', 'damage': 22, 'count': 10, 'speed': 12, 'cooldown': 7, 'size': .6,
        'color': PSY_C},
       {'name': 'Psyko', 'kind': 'nova', 'damage': 28, 'count': 12, 'speed': 12, 'cooldown': 7, 'size': .65,
        'color': PSY_C},
       {'name': 'Psyko', 'kind': 'nova', 'damage': 34, 'count': 16, 'speed': 13, 'cooldown': 7, 'size': .7,
        'color': PSY_C}],
      'Mage fragile : se téléporte, frappe de loin')
_line(('machoc', 'machopeur', 'mackogneur'), ('Machoc', 'Machopeur', 'Mackogneur'), 'combat',
      440, 6.2, (.65, .8, 1.0), (1.3, 1.55, 1.8),
      {'kind': 'melee', 'range': 2.8, 'damage': 34, 'cooldown': .9},
      [{'name': 'Balayage', 'kind': 'wave', 'damage': 45, 'radius': 5, 'speed': 12, 'cooldown': 7,
        'color': FIGHT_C, 'fx': 'combat'},
       {'name': 'Balayage', 'kind': 'wave', 'damage': 58, 'radius': 5.5, 'speed': 12, 'cooldown': 7,
        'color': FIGHT_C, 'fx': 'combat'},
       {'name': 'Balayage', 'kind': 'wave', 'damage': 78, 'radius': 6, 'speed': 13, 'cooldown': 7,
        'color': FIGHT_C, 'fx': 'combat'}],
      'Cogneur : encaisse, frappe plus fort quand il est blessé')
_line(('fantominus', 'spectrum', 'ectoplasma'), ('Fantominus', 'Spectrum', 'Ectoplasma'), 'spectre',
      290, 7.0, (.6, .65, .8), (1.3, 1.5, 1.65),
      {'kind': 'ranged', 'range': 12, 'damage': 24, 'cooldown': .75, 'speed': 22, 'size': .65, 'color': GHOST_C},
      [{'name': 'Ombre Nocturne', 'kind': 'zone', 'damage': 55, 'radius': 3.6, 'delay': .8, 'cooldown': 7,
        'color': GHOST_C, 'status': ('slow', 2)},
       {'name': 'Ombre Nocturne', 'kind': 'zone', 'damage': 70, 'radius': 4, 'delay': .8, 'cooldown': 7,
        'color': GHOST_C, 'status': ('slow', 2)},
       {'name': 'Ombre Nocturne', 'kind': 'zone', 'damage': 90, 'radius': 4.4, 'delay': .8, 'cooldown': 7,
        'color': GHOST_C, 'status': ('slow', 2.5)}],
      'Embusqueur : reste invisible dans les hautes herbes même en attaquant')
_line(('minidraco', 'draco', 'dracolosse'), ('Minidraco', 'Draco', 'Dracolosse'), 'dragon',
      420, 6.4, (.6, .8, 1.05), (1.3, 1.6, 1.8),
      {'kind': 'ranged', 'range': 11, 'damage': 24, 'cooldown': .8, 'speed': 20, 'size': .65, 'color': DRAGON_C},
      [{'name': 'Draco-Souffle', 'kind': 'beam', 'damage': 60, 'width': 2.2, 'length': 13, 'delay': .6,
        'cooldown': 8, 'color': DRAGON_C},
       {'name': 'Draco-Souffle', 'kind': 'beam', 'damage': 76, 'width': 2.4, 'length': 15, 'delay': .6,
        'cooldown': 8, 'color': DRAGON_C},
       {'name': 'Draco-Météore', 'kind': 'zone', 'damage': 110, 'radius': 4.8, 'delay': 1.0, 'cooldown': 8,
        'color': DRAGON_C}],
      'Colosse : très résistant tant qu\'il est en pleine forme')
_line(('wattouat', 'lainergie', 'pharamp'), ('Wattouat', 'Lainergie', 'Pharamp'), 'electrik',
      330, 6.3, (.6, .7, .85), (1.3, 1.5, 1.75),
      {'kind': 'ranged', 'range': 13, 'damage': 20, 'cooldown': .7, 'speed': 26, 'size': .55, 'color': ELEC_C},
      [{'name': 'Luminocanon', 'kind': 'beam', 'damage': 62, 'width': 2.0, 'length': 15, 'delay': .6,
        'cooldown': 8, 'color': ELEC_C},
       {'name': 'Luminocanon', 'kind': 'beam', 'damage': 78, 'width': 2.2, 'length': 16, 'delay': .6,
        'cooldown': 8, 'color': ELEC_C},
       {'name': 'Luminocanon', 'kind': 'beam', 'damage': 100, 'width': 2.5, 'length': 18, 'delay': .6,
        'cooldown': 8, 'color': ELEC_C}],
      'Soutien : renforce les alliés proches, soigne, tire de loin')
_line(('embrylex', 'ymphect', 'tyranocif'), ('Embrylex', 'Ymphect', 'Tyranocif'), 'roche',
      470, 5.9, (.6, .8, 1.1), (1.3, 1.5, 1.85),
      {'kind': 'melee', 'range': 2.9, 'damage': 36, 'cooldown': 1.0},
      [{'name': 'Éboulement', 'kind': 'zone', 'damage': 55, 'radius': 3.6, 'delay': .7, 'cooldown': 7,
        'color': ROCK_C},
       {'name': 'Éboulement', 'kind': 'zone', 'damage': 70, 'radius': 4, 'delay': .7, 'cooldown': 7,
        'color': ROCK_C},
       {'name': 'Lame de Roc', 'kind': 'zone', 'damage': 100, 'radius': 4.6, 'delay': .7, 'cooldown': 7,
        'color': ROCK_C}],
      'Tank : chaque K.O. le rend plus dangereux')
_line(('sorbebe', 'sorboul', 'sorbouboul'), ('Sorbébé', 'Sorboul', 'Sorbouboul'), 'glace',
      330, 6.4, (.6, .7, .9), (1.3, 1.5, 1.7),
      {'kind': 'ranged', 'range': 12, 'damage': 22, 'cooldown': .75, 'speed': 23, 'size': .6, 'color': ICE_C,
       'shape': 'shard'},
      [{'name': 'Vent Glace', 'kind': 'wave', 'damage': 40, 'radius': 7, 'speed': 11, 'cooldown': 8,
        'color': ICE_C, 'status': ('slow', 2)},
       {'name': 'Vent Glace', 'kind': 'wave', 'damage': 52, 'radius': 7.5, 'speed': 11, 'cooldown': 8,
        'color': ICE_C, 'status': ('slow', 2.5)},
       {'name': 'Blizzard', 'kind': 'zone', 'damage': 95, 'radius': 4.6, 'delay': .9, 'cooldown': 8,
        'color': ICE_C, 'status': ('slow', 3)}],
      'Contrôle : ralentit tout le monde, protège ses alliés')
PLAYABLE += ['hericendre', 'kaiminus', 'arcko', 'abra', 'machoc', 'fantominus', 'minidraco', 'wattouat',
             'embrylex', 'sorbebe']


def _rush(name, cd, dmg, speed=32, dur=.3, **kw):
    return dict({'name': name, 'kind': 'rush', 'cooldown': cd, 'damage': dmg, 'speed': speed, 'duration': dur}, **kw)


def _strike(name, cd, dmg, radius, col, delay=.7, style='explosion', **kw):
    return dict({'name': name, 'kind': 'strike', 'cooldown': cd, 'damage': dmg, 'radius': radius, 'delay': delay,
                 'color': col, 'style': style}, **kw)


def _homing(name, cd, dmg, col, speed=18, size=.9, **kw):
    return dict({'name': name, 'kind': 'homing', 'cooldown': cd, 'damage': dmg, 'speed': speed, 'size': size,
                 'color': col}, **kw)


def _spin(name, cd, dmg, radius, col, **kw):
    return dict({'name': name, 'kind': 'spin', 'cooldown': cd, 'damage': dmg, 'radius': radius, 'color': col}, **kw)


def _beam(name, cd, dmg, length, width, col, delay=.7, **kw):
    return dict({'name': name, 'kind': 'beam', 'cooldown': cd, 'damage': dmg, 'length': length, 'width': width,
                 'delay': delay, 'color': col}, **kw)


def _moves(*mv):
    return [dict(m, key=k) for k, m in zip('jklui', mv)]


BASIC, SPECIAL = {'kind': 'basic'}, {'kind': 'special', 'cooldown': 8.0}
MOVESETS.update({
    'hericendre': _moves(dict(BASIC, name='Flammèche'), _rush('Nitrocharge', 4.5, 38),
                         dict(SPECIAL, name='Roue de Feu'),
                         _beam('Lance-Flammes', 8, 70, 15, 2.2, FIRE_C, status=('burn', 3)),
                         _strike('Éruption', 9, 120, 5, rgb(1, .35, .05), delay=1.0, status=('burn', 3))),
    'kaiminus': _moves(dict(BASIC, name='Morsure'), dict(SPECIAL, name='Aqua-Jet', cooldown=6.0),
                       _spin('Hydroqueue', 5.5, 45, 3.8, WATER_C),
                       _rush('Mâchouille', 7, 58, speed=30, stun=.8),
                       _strike('Hydroblast', 8, 115, 4.4, rgb(.3, .65, 1), stun=.8)),
    'arcko': _moves(dict(BASIC, name="Écras'Face"), _rush('Vive-Attaque', 3.5, 36, speed=38, dur=.28),
                    _homing('Balle Graine', 6, 34, GRASS_C, speed=22, size=.7, shape='leaf'),
                    dict(SPECIAL, name='Lame-Feuille', cooldown=6.0),
                    _spin('Tempête Verte', 7, 78, 5.0, GRASS_C, status=('slow', 2))),
    'abra': _moves(dict(BASIC, name='Choc Mental'),
                   {'name': 'Téléport', 'kind': 'blink', 'cooldown': 5.0, 'damage': 30, 'radius': 3.0, 'distance': 8,
                    'color': PSY_C},
                   dict(SPECIAL, name='Psyko', cooldown=7.0),
                   _homing("Psykoud'Boul", 8, 30, PSY_C, stun=1.2),
                   _strike('Prescience', 9, 118, 4.6, PSY_C, delay=1.2)),
    'machoc': _moves(dict(BASIC, name='Poing-Karaté'), _rush('Mach Punch', 4, 40, speed=34),
                     dict(SPECIAL, name='Balayage', cooldown=7.0),
                     _rush('Dynamopoing', 8, 62, speed=28, dur=.35, stun=1.0),
                     _spin('Close Combat', 7, 95, 4.5, FIGHT_C)),
    'fantominus': _moves(dict(BASIC, name='Léchouille'), _rush('Ombre Portée', 4, 38, speed=36),
                         dict(SPECIAL, name='Ombre Nocturne', cooldown=7.0),
                         _homing("Ball'Ombre", 7, 40, GHOST_C, size=1.0, status=('slow', 2.5)),
                         _spin('Malédiction', 8, 82, 5.5, GHOST_C, status=('slow', 3))),
    'minidraco': _moves(dict(BASIC, name='Draco-Rage'), _rush('Vitesse Extrême', 4.5, 40, speed=36),
                        dict(SPECIAL, name='Draco-Souffle'),
                        _homing('Draco-Queue', 8, 36, DRAGON_C, stun=1.0),
                        _spin('Colère', 7, 95, 6.0, DRAGON_C)),
    'wattouat': _moves(dict(BASIC, name='Éclair'), _spin('Cotogarde', 6, 30, 3.6, rgb(1, 1, .8), status=('slow', 2)),
                       dict(SPECIAL, name='Luminocanon'),
                       {'name': 'Soin', 'kind': 'heal', 'cooldown': 11.0, 'heal': 95, 'radius': 9,
                        'color': rgb(1, .95, .55)},
                       _strike('Fatal-Foudre', 8, 115, 4.6, ELEC_C, delay=.6, style='lightning')),
    'embrylex': _moves(dict(BASIC, name='Morsure'), _rush('Charge', 5, 38),
                       dict(SPECIAL, name='Éboulement', cooldown=7.0),
                       _spin('Tempête de Sable', 6, 50, 5.0, rgb(.85, .75, .55), status=('slow', 2)),
                       _spin('Séisme', 7, 98, 7.0, rgb(.8, .7, .5))),
    'sorbebe': _moves(dict(BASIC, name='Éclats Glace'), _spin('Brume', 6, 30, 3.6, ICE_C, status=('slow', 2.5)),
                      dict(SPECIAL, name='Vent Glace'),
                      _homing('Laser Glace', 8, 30, ICE_C, speed=20, size=.8, shape='shard', stun=.8,
                              status=('slow', 2.5)),
                      _strike('Avalanche', 8, 110, 5.0, ICE_C, delay=.8, status=('slow', 3))),
})
EVOLVED_MOVES.update({
    'feurisson': {'k': _rush('Nitrocharge', 4.5, 50, speed=34)},
    'typhlosion': {'k': _rush('Nitrocharge', 4, 66, speed=36),
                   'u': _beam('Lance-Flammes', 8, 96, 18, 2.6, FIRE_C, status=('burn', 3.5))},
    'crocrodil': {'l': _spin('Hydroqueue', 5.5, 58, 4.2, WATER_C)},
    'aligatueur': {'l': _spin('Hydroqueue', 5, 74, 4.6, WATER_C), 'u': _rush('Mâchouille', 6.5, 80, speed=32, stun=1.0)},
    'massko': {'l': _homing('Balle Graine', 6, 46, GRASS_C, speed=23, size=.75, shape='leaf')},
    'jungko': {'k': _rush('Vive-Attaque', 3.2, 56, speed=42, dur=.3),
               'l': _homing('Balle Graine', 5.5, 60, GRASS_C, speed=24, size=.8, shape='leaf')},
    'kadabra': {'k': {'name': 'Téléport', 'kind': 'blink', 'cooldown': 5.0, 'damage': 44, 'radius': 3.4,
                      'distance': 9, 'color': PSY_C}},
    'alakazam': {'k': {'name': 'Téléport', 'kind': 'blink', 'cooldown': 4.5, 'damage': 62, 'radius': 3.8,
                       'distance': 10, 'color': PSY_C},
                 'u': _homing("Psykoud'Boul", 7, 46, PSY_C, stun=1.4)},
    'machopeur': {'k': _rush('Mach Punch', 4, 52, speed=35)},
    'mackogneur': {'k': _rush('Mitra-Poing', 4, 72, speed=36), 'u': _rush('Dynamopoing', 7, 86, speed=30, dur=.38,
                                                                          stun=1.2)},
    'spectrum': {'k': _rush('Ombre Portée', 4, 50, speed=38)},
    'ectoplasma': {'k': _rush('Ombre Portée', 3.5, 66, speed=40),
                   'u': _homing("Ball'Ombre", 6.5, 58, GHOST_C, size=1.1, status=('slow', 3))},
    'draco': {'k': _rush('Vitesse Extrême', 4.5, 52, speed=38)},
    'dracolosse': {'k': _rush('Vitesse Extrême', 4, 70, speed=42),
                   'u': _homing('Draco-Queue', 7, 52, DRAGON_C, stun=1.2)},
    'lainergie': {'k': _spin('Cotogarde', 6, 42, 4.0, rgb(1, 1, .8), status=('slow', 2))},
    'pharamp': {'k': _spin('Cotogarde', 5.5, 56, 4.4, rgb(1, 1, .8), status=('slow', 2.5)),
                'u': {'name': 'Soin', 'kind': 'heal', 'cooldown': 10.0, 'heal': 140, 'radius': 10,
                      'color': rgb(1, .95, .55)}},
    'ymphect': {'k': _rush('Charge', 5, 50, stun=.5)},
    'tyranocif': {'k': _rush('Mâchouille', 4.5, 72, speed=34, stun=.8),
                  'u': _spin('Tempête de Sable', 6, 70, 5.6, rgb(.85, .75, .55), status=('slow', 2.5))},
    'sorboul': {'k': _spin('Brume', 6, 42, 4.0, ICE_C, status=('slow', 2.5))},
    'sorbouboul': {'k': _spin('Brume', 5.5, 56, 4.4, ICE_C, status=('slow', 3)),
                   'u': _homing('Laser Glace', 7, 46, ICE_C, speed=22, size=.9, shape='shard', stun=1.0,
                                status=('slow', 3))},
})

# Talents : un effet permanent propre à chaque lignée (toutes ses formes).
TRAITS = {
    'pikachu': ('Statik', 'Attaque de base : 20 % de chances d\'étourdir 0,5 s'),
    'salameche': ('Brasier', '+25 % de dégâts sous 40 % de PV'),
    'carapuce': ('Torrent', 'Dans la rivière : +10 % de vitesse en plus et +4 PV/s'),
    'bulbizarre': ('Photosynthèse', '+3 PV/s en permanence'),
    'racaillou': ('Fermeté', '-15 % de dégâts subis'),
    'stalgamin': ('Corps Gel', 'Attaque de base : ralentit 1 s'),
    'hericendre': ('Éruption', '+20 % de dégâts au-dessus de 70 % de PV'),
    'kaiminus': ('Mâchoire', 'Récupère 25 % des dégâts infligés au contact'),
    'arcko': ('Engrais', '+30 % de vitesse dans les hautes herbes'),
    'abra': ('Téléport', 'Esquive deux fois plus longue'),
    'machoc': ('Cran', '+30 % de dégâts sous 50 % de PV'),
    'fantominus': ('Spectral', 'Reste caché dans les hautes herbes même en attaquant'),
    'minidraco': ('Multiécaille', '-30 % de dégâts subis au-dessus de 80 % de PV'),
    'wattouat': ('Plus', 'Lui et ses alliés à moins de 8 m : +10 % de dégâts'),
    'embrylex': ('Impudence', 'Après un K.O. : +25 % de dégâts pendant 10 s'),
    'sorbebe': ('Écran Neige', 'Lui et ses alliés à moins de 8 m : -10 % de dégâts subis'),
}
AURA_RANGE = 8.0


def evolution_line(species):
    """Formes successives d'un Pokémon : [forme de base, 1re évolution, 2e évolution]."""
    return [species] + [f for _, f in EVOLUTIONS.get(species, ())]


def evolution_stage(species, level):
    return sum(1 for lvl, _ in EVOLUTIONS.get(species, ()) if level >= lvl)


def form_for(species, level):
    """Forme d'un Pokémon (clé de SPECIES) à un niveau donné."""
    return evolution_line(species)[evolution_stage(species, level)]


def unlock_level(species, key):
    """Niveau qui débloque une touche d'attaque (1 si elle est disponible dès le départ)."""
    stage = UNLOCK.get(key, 0)
    return EVOLUTIONS[species][stage - 1][0] if stage and species in EVOLUTIONS else 1


def moves_for(species, form):
    """Attaques d'un Pokémon sous sa forme actuelle ; les touches pas encore débloquées sont
    marquées 'locked' (avec le niveau qui les débloque dans 'unlock')."""
    line = evolution_line(species)
    stage = line.index(form) if form in line else 0
    moves = []
    for mv in MOVESETS[species]:
        k = mv['key']
        for f in line[1:stage + 1]:
            if k in EVOLVED_MOVES.get(f, {}):
                mv = dict(EVOLVED_MOVES[f][k], key=k)
        mv = dict(mv)
        if mv['kind'] == 'special':                    # la capacité spéciale de la forme actuelle
            mv['name'] = SPECIES[form]['special']['name']
        if stage < UNLOCK.get(k, 0):
            mv['locked'], mv['unlock'] = True, unlock_level(species, k)
        moves.append(mv)
    return moves


def build_roster(team, humans=(), seed=None):
    """Équipe `team` : les Pokémon choisis par les joueurs humains d'abord, puis des IA.

    Les IA gardent les rôles de ROSTERS (dans l'ordre). Avec `seed`, leurs Pokémon sont tirés au
    hasard parmi les jouables (même tirage sur les deux PC, sans doublon dans une équipe ni avec
    les joueurs) ; sans `seed`, ce sont ceux de ROSTERS."""
    import random
    humans = list(humans) if team == 'rouge' else []
    roster = [{'species': s, 'role': 'libre', 'player': True, 'human': i} for i, s in enumerate(humans)]
    bots = ROSTERS[team][1:] if humans else ROSTERS[team]
    if len(humans) > 1:            # deux joueurs : un seul Pokémon de l'IA au Nord
        bots = [bots[0]] + bots[2:]
    taken = set(humans)
    rng = random.Random(seed * 2 + (team == 'bleu')) if seed is not None else None
    for e in bots[:5 - len(humans)]:
        s = e['species']
        if rng is not None:
            s = rng.choice([p for p in PLAYABLE if p not in taken])
        elif s in taken:
            s = next((p for p in PLAYABLE if p not in taken), s)
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
# L'expérience ne vient que des combats : Pokémon sauvages et camps de la jungle (WILD, CAMPS),
# boss (LEGENDARY, FINAL_BOSS) et adversaires mis K.O. (XP_KO). Les alliés proches (16 m)
# reçoivent la moitié de l'XP du vainqueur.
# Courbe douce (partie de 8 à 10 min, mesurée sur des parties entre IA) : passer du niveau n
# au niveau n+1 demande XP_BASE + XP_STEP * (n - 1).
#   1re évolution (Nv 3, 135 XP)  ≈ 4 sauvages ou 1 K.O. et 1 sauvage           -> vers 1 à 2 min
#   2e évolution  (Nv 7, 585 XP)  ≈ 4 K.O., un grand camp et quelques sauvages  -> vers 5 à 7 min
# Les boss donnent peu d'XP par rapport à leurs points : sinon l'équipe qui les bat s'envole.
XP_BASE, XP_STEP = 60, 15
MAX_LEVEL = 12
LEVEL_BONUS = .07              # +7 % PV et dégâts par niveau
XP_KO = 110


def xp_to_next(level):
    """XP pour passer du niveau `level` au suivant."""
    return XP_BASE + XP_STEP * (level - 1)

# ---------------------------------------------------------------- jungle et objectifs
BUFFS = {
    'braise': {'name': 'Braise ardente', 'desc': '+25 % dégâts', 'duration': 90, 'color': color.rgb(1, .4, .15)},
    'flux': {'name': 'Flux marin', 'desc': '-30 % recharge, +4 PV/s', 'duration': 90, 'color': color.rgb(.35, .7, 1)},
    'bastion': {'name': 'Bastion végétal', 'desc': '-25 % dégâts subis', 'duration': 90, 'color': color.rgb(.4, .9, .35)},
    'psy': {'name': 'Aura psychique', 'desc': '+20 % dégâts, -20 % subis', 'duration': 75, 'color': color.rgb(.8, .45, 1)},
    'impudence': {'name': 'Impudence', 'desc': '+25 % dégâts', 'duration': 10, 'color': color.rgb(.9, .7, .4)},
}

# Camps symétriques (Ouest / Est). 'buff' : bonus pour le Pokémon qui achève le camp.
CAMPS = [
    {'species': 'magmar', 'pos': (-50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'magmar', 'pos': (50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'lokhlass', 'pos': (-34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'lokhlass', 'pos': (34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'torterra', 'pos': (-24, 42), 'buff': 'bastion', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'torterra', 'pos': (24, 42), 'buff': 'bastion', 'respawn': 90, 'xp': 120, 'points': 10},
    {'species': 'rattata', 'count': 3, 'pos': (-58, -16), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (58, -16), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-50, -72), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (50, -72), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-86, 58), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (86, 58), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (-24, 70), 'respawn': 45, 'xp': 45, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (24, 70), 'respawn': 45, 'xp': 45, 'points': 3},
]
CAMP_LEASH = 16                # un Pokémon neutre ne s'éloigne pas plus de son camp

# Petits Pokémon sauvages dispersés dans toute la jungle (en plus des camps).
WILD = {
    'count': 34,                               # nombre d'emplacements
    'species': ['chenipan', 'roucool', 'mystherbe', 'rattata'],
    'hp_factor': .55,                          # les Rattata sauvages sont plus faibles que ceux des camps
    'xp': 36, 'points': 1, 'respawn': 40,
    'leash': 9,                                # distance de poursuite maximale
    'wander': 3.5,                             # rayon de promenade autour de leur coin
}

# Boss légendaires du Boss Pit (centre de la carte).
# Calendrier calé sur une partie de 10 min : Mewtwo à 3:30 (puis 3 min après sa défaite),
# Regigigas pour le final à 7:00 (il remplace Mewtwo).
LEGENDARY = {'species': 'mewtwo', 'first_spawn': 210, 'respawn': 180, 'xp': 150, 'points': 120, 'buff': 'psy'}
FINAL_BOSS = {'species': 'regigigas', 'spawn': 7 * 60, 'xp': 200, 'points': 250, 'buff': 'psy'}
