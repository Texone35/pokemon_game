"""Attaques des Pokémon jouables : auto-attaque, 4 attaques, ultime, déblocage et visée.

Chaque lignée (clé = forme de base) a un kit :
  'auto'        auto-attaque (maintenir J) : physique, ciblage automatique
  1, 2, 3, 4    les quatre attaques (touches K, L, U, I)
  'ult'         l'ultime (touche O)
L'attaque n°1 est à ciblage automatique (« lock ») ; les suivantes et l'ultime se visent à la
souris (« skill ») : maintenir la touche affiche la visée, la relâcher lance l'attaque. Les
attaques visées frappent plus fort (AIM_POWER).

Champs d'une attaque :
  name, kind (sorte, voir plus bas), cat ('phys' : utilise l'Attaque / 'spec' : l'Attaque spéciale),
  power (puissance, comme dans les jeux), cooldown (s), status (('burn'|'slow', durée)), stun (s),
  tags : 'solaire' (Lance-Soleil : quasi instantané au soleil), 'synthese' (soin renforcé au soleil),
         'sur_pluie' (ne rate jamais sous la pluie : frappe tout de suite sur la cible)
Sortes :
  'rush'   fonce (speed, duration) et frappe au contact      'charge' roule et frappe tout sur son passage
  'strike' zone au sol (radius, delay, range = portée)       'shot'   projectile en ligne droite (speed, size, range)
  'homing' projectile à tête chercheuse (ciblage auto)       'spin'   onde autour de soi (radius)
  'wave'   onde de choc qui s'élargit (radius, speed)        'beam'   rayon (length, width, delay)
  'nova'   anneau de projectiles (count, speed, size)        'blink'  téléportation + onde à l'arrivée
  'heal'   soigne les alliés proches (power = puissance du soin, radius)
Options : 'guard' (durée, réduction) protège le lanceur ; 'style' ('lightning' | 'explosion') pour
les zones ; 'color', 'shape' ('leaf', 'shard', 'rock', 'cage') pour l'aspect.
"""
from ursina import color

rgb = color.rgb

# ---------------------------------------------------------------- touches et déblocage
# Touches, désignées par leur POSITION sur le clavier (Panda3D nomme les touches comme sur un clavier
# QWERTY, quelle que soit la disposition) : 'q' = touche A d'un clavier AZERTY, 'a' = Q, 'w' = Z.
# Sur AZERTY : A auto-attaque, Q Z S D attaques, E ultime, F transformation (le jeu affiche les
# lettres de votre clavier). On se déplace au clic (ou aux flèches).
KEYS = {'auto': 'q', 1: 'a', 2: 'w', 3: 's', 4: 'd', 'ult': 'e'}
SLOTS = (1, 2, 3, 4, 'ult')
# Visée : les attaques qui partent du Pokémon vers une direction ou un point (rayon, tir, ruée,
# zone au sol...) se visent à la souris (maintenir la touche, relâcher pour lancer). Celles qui
# agissent autour du Pokémon partent tout de suite.
SELF_CAST = ('spin', 'wave', 'nova', 'heal')
AUTO_POWER = .7                # puissance des auto-attaques des Pokémon d'équipe (x 0,7 : elles complètent
                               # les attaques entre deux recharges sans les remplacer)
UNLOCK = {1: 1, 2: 3, 3: 5, 4: 7, 'ult': 10}     # niveau qui débloque chaque attaque
AIM_POWER = {'lock': 1.0, 'skill': 1.25}          # bonus de puissance des attaques visées
CAST_LOCK = .3                 # délai minimal entre deux attaques (hors auto-attaque)

# À chaque évolution, les attaques du kit gagnent en puissance et en taille (étape 1, étape 2).
EVO_POWER = (1.0, 1.1, 1.2)
EVO_AREA = (1.0, 1.06, 1.12)

# ---------------------------------------------------------------- couleurs
FIRE_C, WATER_C, GRASS_C = rgb(1, .45, .1), rgb(.35, .7, 1), rgb(.45, .95, .3)
PSY_C, FIGHT_C, GHOST_C = rgb(.85, .45, 1), rgb(1, .55, .3), rgb(.55, .35, .85)
DRAGON_C, ELEC_C, ROCK_C, ICE_C = rgb(.5, .45, 1), rgb(1, .95, .3), rgb(.75, .6, .4), rgb(.7, .95, 1)


# ---------------------------------------------------------------- aides
def ranged(power, rng, cd, speed, size, col, **kw):
    return dict({'kind': 'ranged', 'power': power, 'range': rng, 'cooldown': cd, 'speed': speed, 'size': size,
                 'color': col}, **kw)


def melee(power, rng, cd):
    return {'kind': 'melee', 'power': power, 'range': rng, 'cooldown': cd}


def rush(name, cat, power, cd, speed=32, dur=.3, **kw):
    return dict({'name': name, 'kind': 'rush', 'cat': cat, 'power': power, 'cooldown': cd, 'speed': speed,
                 'duration': dur}, **kw)


def charge(name, cat, power, cd, speed=26, dur=.6, **kw):
    return dict({'name': name, 'kind': 'charge', 'cat': cat, 'power': power, 'cooldown': cd, 'speed': speed,
                 'duration': dur}, **kw)


def strike(name, cat, power, cd, radius, col, delay=.7, rng=12, style='explosion', **kw):
    return dict({'name': name, 'kind': 'strike', 'cat': cat, 'power': power, 'cooldown': cd, 'radius': radius,
                 'delay': delay, 'range': rng, 'color': col, 'style': style}, **kw)


def shot(name, cat, power, cd, col, speed=20, size=.9, rng=14, **kw):
    return dict({'name': name, 'kind': 'shot', 'cat': cat, 'power': power, 'cooldown': cd, 'speed': speed,
                 'size': size, 'range': rng, 'color': col}, **kw)


def homing(name, cat, power, cd, col, speed=18, size=.9, **kw):
    return dict({'name': name, 'kind': 'homing', 'cat': cat, 'power': power, 'cooldown': cd, 'speed': speed,
                 'size': size, 'color': col}, **kw)


def spin(name, cat, power, cd, radius, col, **kw):
    return dict({'name': name, 'kind': 'spin', 'cat': cat, 'power': power, 'cooldown': cd, 'radius': radius,
                 'color': col}, **kw)


def wave(name, cat, power, cd, radius, col, speed=12, **kw):
    return dict({'name': name, 'kind': 'wave', 'cat': cat, 'power': power, 'cooldown': cd, 'radius': radius,
                 'speed': speed, 'color': col}, **kw)


def beam(name, cat, power, cd, length, width, col, delay=.7, **kw):
    return dict({'name': name, 'kind': 'beam', 'cat': cat, 'power': power, 'cooldown': cd, 'length': length,
                 'width': width, 'delay': delay, 'color': col}, **kw)


def nova(name, cat, power, cd, count, col, speed=12, size=.6, **kw):
    return dict({'name': name, 'kind': 'nova', 'cat': cat, 'power': power, 'cooldown': cd, 'count': count,
                 'speed': speed, 'size': size, 'color': col}, **kw)


def blink(name, cat, power, cd, distance, radius, col, **kw):
    return dict({'name': name, 'kind': 'blink', 'cat': cat, 'power': power, 'cooldown': cd, 'distance': distance,
                 'radius': radius, 'color': col}, **kw)


def heal(name, power, cd, radius, col, **kw):
    return dict({'name': name, 'kind': 'heal', 'cat': 'spec', 'power': power, 'cooldown': cd, 'radius': radius,
                 'color': col}, **kw)


# ---------------------------------------------------------------- kits
KITS = {
    'pikachu': {
        'auto': ranged(42, 13, .6, 28, .5, rgb(1, .95, .25)),
        1: homing('Boule Élek', 'spec', 95, 5.0, ELEC_C, speed=20, size=.8),
        2: strike('Tonnerre', 'spec', 110, 7.0, 3.2, ELEC_C, delay=.6, rng=12, style='lightning'),
        3: rush('Vive-Attaque', 'phys', 70, 5.0, speed=36),
        4: shot('Cage-Éclair', 'spec', 40, 9.0, rgb(.6, .95, 1), speed=18, size=1.0, stun=1.4, shape='cage'),
        'ult': strike('Fatal-Foudre', 'spec', 300, 80.0, 5.5, rgb(.8, .95, 1), delay=.9, rng=14, style='lightning',
                      tags=('sur_pluie',)),
    },
    'salameche': {
        'auto': ranged(45, 12, .8, 22, .6, FIRE_C),
        1: beam('Lance-Flammes', 'spec', 95, 6.0, 15, 2.2, rgb(1, .4, .05), status=('burn', 3)),
        2: strike('Danse Flammes', 'spec', 115, 8.0, 3.6, rgb(1, .4, .05), status=('burn', 3), rng=11),
        3: rush('Crocs Feu', 'phys', 80, 6.0, status=('burn', 2.5)),
        4: strike('Déflagration', 'spec', 150, 10.0, 4.6, rgb(1, .35, .05), delay=.8, status=('burn', 4)),
        'ult': beam('Rafale Feu', 'spec', 320, 85.0, 20, 4.0, rgb(1, .35, .05), delay=.9, status=('burn', 4)),
    },
    'carapuce': {
        'auto': ranged(42, 11, .7, 22, .5, WATER_C),
        1: rush('Aqua-Jet', 'phys', 85, 5.0, speed=34),
        2: wave('Surf', 'spec', 100, 8.0, 8, rgb(.25, .6, 1)),
        3: shot("Bulles d'O", 'spec', 70, 7.0, rgb(.4, .75, 1), speed=16, size=.9, status=('slow', 2.5)),
        4: spin('Abri Carapace', 'phys', 70, 10.0, 3.8, rgb(.5, .8, 1), guard=(2.5, .5)),
        'ult': beam('Hydroblast', 'spec', 330, 85.0, 22, 3.4, rgb(.3, .65, 1), delay=1.0, stun=.8),
    },
    'bulbizarre': {
        'auto': ranged(40, 11, .8, 18, .55, GRASS_C, shape='leaf'),
        1: homing("Tranch'Herbe", 'spec', 80, 5.0, GRASS_C, speed=20, size=.7, shape='leaf'),
        2: heal('Synthèse', 90, 12.0, 9, rgb(.5, 1, .45), tags=('synthese',)),
        3: shot('Poudre Dodo', 'spec', 35, 10.0, rgb(.75, .6, 1), speed=14, size=1.0, stun=1.4),
        4: beam('Lance-Soleil', 'spec', 170, 11.0, 18, 2.6, rgb(.75, 1, .45), delay=1.2, tags=('solaire',)),
        'ult': strike('Végé-Attaque', 'spec', 280, 85.0, 6.0, GRASS_C, delay=.7, stun=1.0, rng=12),
    },
    'racaillou': {
        'auto': melee(55, 2.8, 1.0),
        1: charge('Roulade', 'phys', 80, 6.0, speed=24, dur=.7),
        2: strike('Éboulement', 'phys', 110, 7.0, 3.6, ROCK_C, rng=10),
        3: shot('Jet-Pierres', 'phys', 60, 9.0, rgb(.7, .6, .45), speed=18, size=.9, stun=1.2, shape='rock'),
        4: spin('Ampleur', 'phys', 100, 6.0, 4.5, rgb(.8, .7, .5)),
        'ult': spin('Séisme', 'phys', 280, 80.0, 8.0, rgb(.8, .7, .5), stun=.8),
    },
    'stalgamin': {
        'auto': ranged(40, 12, .75, 24, .5, ICE_C, shape='shard'),
        1: homing('Laser Glace', 'spec', 85, 6.0, ICE_C, speed=20, size=.8, shape='shard', status=('slow', 2.5)),
        2: strike('Blizzard', 'spec', 110, 8.0, 3.6, rgb(.6, .9, 1), delay=.9, status=('slow', 2.5)),
        3: spin('Vent Glace', 'spec', 80, 6.0, 4.0, rgb(.75, .95, 1), status=('slow', 2.0)),
        4: rush('Crocs Givre', 'phys', 90, 6.0, speed=33, status=('slow', 2.0)),
        'ult': spin('Glaciation', 'spec', 250, 85.0, 7.0, ICE_C, stun=1.4),
    },
    'hericendre': {
        'auto': ranged(44, 12.5, .8, 22, .6, FIRE_C),
        1: beam('Lance-Flammes', 'spec', 95, 7.0, 15, 2.2, FIRE_C, status=('burn', 3)),
        2: wave('Roue de Feu', 'spec', 95, 8.0, 7, FIRE_C, status=('burn', 2)),
        3: rush('Nitrocharge', 'phys', 65, 5.0),
        4: strike('Déflagration', 'spec', 150, 10.0, 4.6, rgb(1, .35, .05), delay=.8, status=('burn', 4)),
        'ult': strike('Éruption', 'spec', 330, 85.0, 6.0, rgb(1, .35, .05), delay=1.0, rng=13, status=('burn', 3)),
    },
    'kaiminus': {
        'auto': melee(55, 2.8, .9),
        1: charge('Aqua-Jet', 'phys', 85, 6.0, speed=26, dur=.55),
        2: spin('Hydroqueue', 'phys', 100, 6.0, 3.8, WATER_C),
        3: rush('Mâchouille', 'phys', 100, 8.0, speed=30, stun=.8),
        4: strike('Hydroblast', 'phys', 150, 9.0, 4.4, rgb(.3, .65, 1), stun=.8, rng=10),
        'ult': wave('Tempête Aquatique', 'phys', 280, 80.0, 10, rgb(.25, .6, 1), speed=13, status=('slow', 2.5)),
    },
    'arcko': {
        'auto': melee(45, 2.6, .6),
        1: rush('Vive-Attaque', 'phys', 75, 4.0, speed=38, dur=.28),
        2: shot('Balle Graine', 'phys', 90, 6.0, GRASS_C, speed=22, size=.7, shape='leaf'),
        3: charge('Lame-Feuille', 'phys', 110, 7.0, speed=30, dur=.4),
        4: spin('Tempête Verte', 'phys', 120, 8.0, 5.0, GRASS_C, status=('slow', 2)),
        'ult': rush('Frénésie Verte', 'phys', 300, 70.0, speed=42, dur=.35, stun=.6),
    },
    'abra': {
        'auto': ranged(42, 13, .75, 24, .55, PSY_C),
        1: homing('Choc Mental', 'spec', 90, 5.0, PSY_C, speed=20, size=.7),
        2: blink('Téléport', 'spec', 70, 6.0, 8, 3.0, PSY_C),
        3: nova('Psyko', 'spec', 60, 8.0, 10, PSY_C),
        4: shot("Psykoud'Boul", 'spec', 70, 9.0, PSY_C, speed=18, size=1.0, stun=1.2),
        'ult': strike('Prescience', 'spec', 360, 80.0, 5.0, PSY_C, delay=1.4, rng=16),
    },
    'machoc': {
        'auto': melee(58, 2.8, .9),
        1: rush('Mach Punch', 'phys', 80, 4.0, speed=34),
        2: wave('Balayage', 'phys', 100, 7.0, 5, FIGHT_C, fx='combat'),
        3: rush('Dynamopoing', 'phys', 110, 9.0, speed=28, dur=.35, stun=1.0),
        4: spin('Close Combat', 'phys', 150, 8.0, 4.5, FIGHT_C),
        'ult': rush('Gigacoup', 'phys', 320, 75.0, speed=36, dur=.4, stun=1.2),
    },
    'fantominus': {
        'auto': ranged(44, 12, .75, 22, .65, GHOST_C),
        1: rush('Ombre Portée', 'phys', 75, 4.5, speed=36),
        2: strike('Ombre Nocturne', 'spec', 110, 7.0, 3.6, GHOST_C, delay=.8, status=('slow', 2)),
        3: shot("Ball'Ombre", 'spec', 95, 7.0, GHOST_C, size=1.0, status=('slow', 2.5)),
        4: spin('Malédiction', 'spec', 130, 9.0, 5.5, GHOST_C, status=('slow', 3)),
        'ult': blink('Hantise', 'spec', 300, 75.0, 12, 5.0, GHOST_C),
    },
    'minidraco': {
        'auto': ranged(46, 11, .8, 20, .65, DRAGON_C),
        1: rush('Vitesse Extrême', 'phys', 80, 5.0, speed=36),
        2: beam('Draco-Souffle', 'spec', 110, 8.0, 13, 2.2, DRAGON_C, delay=.6),
        3: shot('Draco-Queue', 'phys', 80, 8.0, DRAGON_C, stun=1.0),
        4: spin('Colère', 'phys', 150, 8.0, 6.0, DRAGON_C),
        'ult': strike('Draco-Météore', 'spec', 360, 85.0, 6.0, DRAGON_C, delay=1.1, rng=15),
    },
    'wattouat': {
        'auto': ranged(38, 13, .7, 26, .55, ELEC_C),
        1: homing('Cage-Éclair', 'spec', 60, 8.0, rgb(.6, .95, 1), speed=16, size=1.0, stun=.8, shape='cage'),
        2: heal('Soin', 100, 12.0, 9, rgb(1, .95, .55)),
        3: spin('Cotogarde', 'spec', 60, 7.0, 3.6, rgb(1, 1, .8), status=('slow', 2), guard=(2.0, .35)),
        4: beam('Luminocanon', 'spec', 140, 9.0, 16, 2.2, ELEC_C, delay=.6),
        'ult': strike('Fatal-Foudre', 'spec', 300, 80.0, 5.0, ELEC_C, delay=.8, rng=14, style='lightning',
                      tags=('sur_pluie',)),
    },
    'embrylex': {
        'auto': melee(58, 2.9, 1.0),
        1: rush('Charge', 'phys', 80, 5.0),
        2: strike('Éboulement', 'phys', 110, 7.0, 3.6, ROCK_C, rng=10),
        3: spin('Tempête de Sable', 'phys', 90, 7.0, 5.0, rgb(.85, .75, .55), status=('slow', 2)),
        4: rush('Mâchouille', 'phys', 110, 8.0, speed=34, stun=.8),
        'ult': spin('Séisme', 'phys', 300, 85.0, 8.0, rgb(.8, .7, .5), stun=.8),
    },
    'sorbebe': {
        'auto': ranged(40, 12, .75, 23, .6, ICE_C, shape='shard'),
        1: homing('Laser Glace', 'spec', 80, 7.0, ICE_C, speed=20, size=.8, shape='shard', status=('slow', 2.5)),
        2: wave('Vent Glace', 'spec', 90, 8.0, 7, ICE_C, speed=11, status=('slow', 2)),
        3: spin('Brume', 'spec', 50, 8.0, 3.6, ICE_C, status=('slow', 2.5), guard=(2.0, .35)),
        4: strike('Avalanche', 'spec', 140, 9.0, 5.0, ICE_C, delay=.8, status=('slow', 3)),
        'ult': spin('Ère Glaciaire', 'spec', 280, 85.0, 7.0, ICE_C, stun=1.2),
    },
}

# Noms propres à certaines formes évoluées : {forme: {emplacement: {champ: valeur}}}.
FORM_MOVES = {
    'raichu': {1: {'name': 'Étincelle'}},
    'dracaufeu': {3: {'name': 'Vol', 'speed': 42, 'duration': .38}},
    'tortank': {2: {'name': 'Hydrocanon'}},
    'herbizarre': {1: {'name': 'Fouet Lianes'}},
    'florizarre': {1: {'name': 'Tempête Florale', 'size': .9}},
    'grolem': {2: {'name': 'Lame de Roc', 'stun': .8}},
    'oniglali': {3: {'name': 'Avalanche'}},
    'typhlosion': {3: {'name': 'Nitrocharge', 'speed': 36}},
    'aligatueur': {3: {'stun': 1.0}},
    'jungko': {1: {'speed': 42}},
    'alakazam': {2: {'distance': 10}},
    'mackogneur': {1: {'name': 'Mitra-Poing'}},
    'dracolosse': {1: {'speed': 42}},
    'tyranocif': {1: {'name': 'Mâchouille', 'stun': .5}},
}

# ---------------------------------------------------------------- builds
# Plusieurs façons de jouer une lignée, au choix dans le salon. Un build peut changer : 'role' et
# 'curve' (voir stats.py), l'auto-attaque ('auto'), une ou plusieurs attaques (1, 2, 3, 4, 'ult'), et
# orienter les stats ('stats' : multiplicateurs). Le build 'standard' (le kit ci-dessus) existe
# toujours. Les noms propres aux évolutions (FORM_MOVES) ne s'appliquent qu'au build standard.
BUILDS = {
    'bulbizarre': {
        'liane': {'name': 'Liane', 'desc': 'Combattant au corps à corps, axé sur la Vitesse', 'role': 'combattant',
                  'stats': {'spe': 1.15, 'atk': 1.1, 'spa': .85},
                  'auto': melee(50, 2.8, .7),
                  1: rush('Fouet Lianes', 'phys', 85, 4.0, speed=36),
                  2: spin("Tranch'Herbe", 'phys', 100, 6.0, 4.0, GRASS_C),
                  3: rush('Bélier', 'phys', 110, 8.0, speed=30, dur=.35, stun=.8),
                  4: spin('Danse-Fleurs', 'phys', 145, 9.0, 5.0, rgb(1, .6, .75), status=('slow', 2)),
                  'ult': charge('Végé-Écrasement', 'phys', 300, 75.0, speed=30, dur=.7, stun=1.0)},
        'solaire': {'name': 'Solaire', 'desc': 'Sniper à distance centré sur Lance-Soleil', 'role': 'sniper',
                    'stats': {'spa': 1.1},
                    'auto': ranged(44, 13, .85, 20, .6, GRASS_C, shape='leaf'),
                    1: homing('Canon Graine', 'spec', 85, 5.0, GRASS_C, speed=22, size=.7, shape='leaf'),
                    2: beam('Lance-Soleil', 'spec', 160, 8.0, 20, 2.6, rgb(.75, 1, .45), delay=1.3, tags=('solaire',)),
                    3: strike('Bombe Graine', 'spec', 120, 8.0, 3.8, GRASS_C, rng=14),
                    4: heal('Synthèse', 80, 14.0, 7, rgb(.5, 1, .45), tags=('synthese',)),
                    'ult': beam('Rayon Solaire', 'spec', 380, 85.0, 28, 5.0, rgb(1, 1, .6), delay=1.6,
                                tags=('solaire',))},
    },
    'salameche': {
        'dragon': {'name': 'Dragon', 'desc': 'Combattant au contact : griffes, plongeons et flammes',
                   'role': 'combattant', 'stats': {'atk': 1.1},
                   'auto': melee(52, 2.8, .85),
                   1: rush('Griffe', 'phys', 80, 4.0),
                   2: charge('Vol', 'phys', 110, 7.0, speed=34, dur=.45),
                   3: spin('Draco-Queue', 'phys', 110, 6.0, 4.0, DRAGON_C),
                   4: rush('Boutefeu', 'phys', 160, 10.0, speed=36, status=('burn', 3)),
                   'ult': charge('Plongeon Ardent', 'phys', 330, 80.0, speed=40, dur=.6, status=('burn', 4))},
    },
    'pikachu': {
        'queue': {'name': 'Queue de Fer', 'desc': 'Rapide au corps à corps : fonce et frappe', 'role': 'rapide',
                  'auto': melee(46, 2.4, .55),
                  1: rush('Vive-Attaque', 'phys', 75, 3.5, speed=38),
                  2: spin('Queue de Fer', 'phys', 110, 6.0, 3.6, rgb(.8, .8, .85)),
                  3: rush('Électacle', 'phys', 130, 9.0, speed=40, stun=.6),
                  4: charge('Rafale Volt', 'phys', 120, 8.0, speed=34, dur=.5, status=('slow', 1.5))},
    },
    'carapuce': {
        'canon': {'name': 'Canon à eau', 'desc': 'Sniper à distance : jets puissants et Hydrocanon', 'role': 'sniper',
                  'stats': {'spa': 1.15, 'def': .9},
                  'auto': ranged(44, 13, .75, 26, .5, WATER_C),
                  1: shot('Pistolet à O', 'spec', 85, 4.5, WATER_C, speed=26, size=.7, rng=16),
                  3: beam('Hydrocanon', 'spec', 140, 9.0, 18, 2.4, rgb(.3, .65, 1), delay=.8),
                  4: strike('Vibraqua', 'spec', 120, 9.0, 4.0, rgb(.4, .75, 1), rng=14, status=('slow', 2))},
    },
    'racaillou': {
        'artilleur': {'name': 'Artilleur', 'desc': 'Lance des rochers de loin plutôt que de foncer', 'role': 'sniper',
                      'stats': {'atk': 1.1, 'def': .9},
                      'auto': ranged(46, 11, .95, 18, .7, ROCK_C, shape='rock'),
                      1: shot('Jet-Pierres', 'phys', 80, 5.0, rgb(.7, .6, .45), speed=20, size=.9, shape='rock'),
                      3: strike('Tomberoche', 'phys', 120, 8.0, 3.8, ROCK_C, rng=14, status=('slow', 2)),
                      4: strike('Lame de Roc', 'phys', 150, 10.0, 4.4, ROCK_C, rng=13, stun=.8)},
    },
    'stalgamin': {
        'givre': {'name': 'Givre', 'desc': 'Attaquant de glace : gros dégâts de zone, moins de contrôle',
                  'role': 'sniper', 'stats': {'spa': 1.12},
                  2: strike('Blizzard', 'spec', 135, 8.0, 4.2, rgb(.6, .9, 1), delay=.9, rng=13),
                  3: beam('Laser Glace', 'spec', 125, 8.0, 16, 2.2, ICE_C, delay=.6),
                  4: strike('Avalanche', 'spec', 160, 11.0, 4.8, ICE_C, delay=.8, status=('slow', 2))},
    },
    'hericendre': {
        'volcan': {'name': 'Volcan', 'desc': 'Combattant au contact, enveloppé de flammes', 'role': 'combattant',
                   'stats': {'atk': 1.15, 'def': 1.1, 'spa': .85},
                   'auto': melee(52, 2.8, .85),
                   1: rush('Nitrocharge', 'phys', 85, 4.5, speed=34),
                   2: spin('Roue de Feu', 'phys', 110, 6.0, 4.2, FIRE_C, status=('burn', 2)),
                   3: charge('Boutefeu', 'phys', 130, 8.0, speed=30, dur=.5, status=('burn', 3))},
    },
    'kaiminus': {
        'torrent': {'name': 'Torrent', 'desc': 'Tank : encaisse et ralentit les adversaires', 'role': 'tank',
                    'stats': {'hp': 1.1, 'def': 1.15, 'atk': .9},
                    3: wave('Surf', 'phys', 90, 8.0, 8, rgb(.25, .6, 1), status=('slow', 2)),
                    4: spin('Aqua-Brèche', 'phys', 110, 9.0, 4.5, WATER_C, guard=(2.5, .45))},
    },
    'arcko': {
        'graine': {'name': 'Mitrailleur', 'desc': 'Sniper agile : graines à distance', 'role': 'sniper',
                   'stats': {'spa': 1.15, 'atk': .9},
                   'auto': ranged(42, 12, .6, 24, .5, GRASS_C, shape='leaf'),
                   1: homing('Balle Graine', 'spec', 85, 4.5, GRASS_C, speed=24, size=.7, shape='leaf'),
                   2: shot('Canon Graine', 'spec', 110, 6.0, GRASS_C, speed=24, size=.8, shape='leaf'),
                   3: blink('Détection', 'spec', 60, 7.0, 7, 3.0, GRASS_C)},
    },
    'abra': {
        'esprit': {'name': 'Esprit', 'desc': 'Soutien : soigne et contrôle avec ses pouvoirs psychiques',
                   'role': 'soutien', 'stats': {'spd': 1.15, 'hp': 1.1},
                   3: heal('Vœu', 90, 12.0, 9, rgb(1, .8, 1)),
                   4: shot('Hypnose', 'spec', 40, 10.0, PSY_C, speed=16, size=1.1, stun=1.6)},
    },
    'machoc': {
        'rempart': {'name': 'Rempart', 'desc': 'Tank : protège ses alliés et étourdit', 'role': 'tank',
                    'stats': {'hp': 1.1, 'def': 1.15, 'atk': .9},
                    2: spin('Balayage', 'phys', 90, 7.0, 4.5, FIGHT_C, stun=.6),
                    4: spin('Gonflette', 'phys', 60, 10.0, 3.5, FIGHT_C, guard=(3.0, .5))},
    },
    'fantominus': {
        'hantise': {'name': 'Hantise', 'desc': 'Sniper spectral : frappe de loin et ralentit', 'role': 'sniper',
                    'stats': {'spa': 1.15, 'atk': .85},
                    1: homing("Ball'Ombre", 'spec', 90, 5.0, GHOST_C, size=.9, status=('slow', 1.5)),
                    3: beam('Ombre Portée', 'spec', 120, 8.0, 15, 2.2, GHOST_C, delay=.6)},
    },
    'minidraco': {
        'souffle': {'name': 'Souffle', 'desc': 'Sniper draconique : rayons à longue portée', 'role': 'sniper',
                    'stats': {'spa': 1.15, 'atk': .9},
                    1: homing('Draco-Rage', 'spec', 90, 5.0, DRAGON_C, speed=22),
                    3: strike('Draco-Choc', 'spec', 120, 8.0, 3.8, DRAGON_C, rng=14),
                    4: beam('Ultralaser', 'spec', 170, 11.0, 20, 2.8, rgb(.9, .8, 1), delay=1.0)},
    },
    'wattouat': {
        'foudre': {'name': 'Foudre', 'desc': 'Sniper électrique : moins de soins, plus de dégâts', 'role': 'sniper',
                   'stats': {'spa': 1.12},
                   1: homing('Boule Élek', 'spec', 90, 5.0, ELEC_C, speed=22),
                   2: strike('Tonnerre', 'spec', 120, 7.0, 3.4, ELEC_C, delay=.6, style='lightning')},
    },
    'embrylex': {
        'fracas': {'name': 'Fracas', 'desc': 'Combattant offensif : charges et morsures', 'role': 'combattant',
                   'stats': {'atk': 1.15, 'def': .9},
                   1: charge('Roulade', 'phys', 85, 6.0, speed=26, dur=.6),
                   3: rush('Crocs Feu', 'phys', 110, 7.0, speed=34, status=('burn', 2.5))},
    },
    'sorbebe': {
        'grele': {'name': 'Grêle', 'desc': 'Sniper de glace : zones de gros dégâts', 'role': 'sniper',
                  'stats': {'spa': 1.12},
                  3: strike('Grêle', 'spec', 120, 8.0, 4.4, ICE_C, delay=.8, rng=14),
                  4: beam('Laser Glace', 'spec', 150, 10.0, 18, 2.4, ICE_C, delay=.7)},
    },
}

# ---------------------------------------------------------------- transformations (touche P)
# Méga-Évolution : prend temporairement la forme Méga (toutes les stats changent : celles de la
# forme Méga, voir stats.py : BASE_STATS). Seulement sous sa dernière forme.
# Dynamax : le Pokémon devient géant, ses PV max augmentent fortement (et seulement ses PV).
# Chaque lignée a l'une ou l'autre (MEGA_FORMS : lignées qui ont une Méga-Évolution ; Dynamax sinon).
TRANSFORM_KEY = 'f'
TRANSFORMS = {
    'mega': {'name': 'Méga-Évolution', 'level': 9, 'duration': 25.0, 'cooldown': 100.0},
    'dynamax': {'name': 'Dynamax', 'level': 8, 'duration': 15.0, 'cooldown': 110.0,
                'effects': {'stats': {'hp': .8}}, 'size': 1.6},
}
MEGA_FORMS = {'pikachu': 'mega_raichu', 'stalgamin': 'mega_oniglali', 'salameche': 'mega_dracaufeu',
              'bulbizarre': 'mega_florizarre'}
