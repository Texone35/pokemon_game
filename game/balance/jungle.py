"""Jungle : buffs, camps de Pokémon neutres, petits sauvages et boss du Boss Pit."""
from ursina import color

from game.balance.moves import melee, nova, ranged, rgb, strike, wave

# ---------------------------------------------------------------- Pokémon neutres
# 'stats' : (PV, Att, Déf, AtS, DéS, Vit) à la première minute ; 'move' : vitesse de déplacement.
# Les neutres se renforcent avec le temps (NEUTRAL_GROWTH, par minute de jeu, au moment où ils
# apparaissent) pour rester intéressants face à des Pokémon de haut niveau.
NEUTRALS = {
    'rattata': {'stats': (220, 30, 35, 20, 30, 60), 'move': 2.6, 'auto': melee(23, 2.2, 1.0)},
    'chenipan': {'stats': (100, 18, 30, 15, 25, 30), 'move': 1.5, 'auto': melee(12, 2.0, 1.3)},
    'roucool': {'stats': (120, 24, 30, 15, 25, 50), 'move': 2.25, 'auto': melee(16, 2.2, 1.2)},
    'mystherbe': {'stats': (110, 22, 35, 25, 30, 30), 'move': 1.7, 'auto': melee(14, 2.0, 1.2)},
    'magmar': {'stats': (1050, 60, 50, 60, 50, 60), 'move': 5.0,
               'auto': ranged(30, 10, 1.1, 16, .8, rgb(1, .45, .1)),
               'special': strike('Déflagration', 'spec', 55, 6.0, 4, rgb(1, .3, .05), delay=1.0, status=('burn', 2.5))},
    'lokhlass': {'stats': (1100, 55, 60, 60, 60, 50), 'move': 5.0,
                 'auto': ranged(28, 10, 1.0, 16, .7, rgb(.4, .75, 1)),
                 'special': wave('Hydrocanon', 'spec', 48, 7.0, 8, rgb(.3, .6, 1), speed=10)},
    'torterra': {'stats': (1300, 70, 70, 40, 55, 45), 'move': 5.0, 'auto': melee(42, 3.5, 1.4),
                 'special': wave('Séisme', 'phys', 50, 7.0, 9, rgb(.6, .48, .3), speed=9, fx='roche')},
    'heliatronc': {'stats': (1150, 55, 60, 65, 60, 45), 'move': 5.0,
                   'auto': ranged(28, 10, 1.1, 15, .7, rgb(.45, .95, .3), shape='leaf'),
                   'special': strike('Lance-Soleil', 'spec', 55, 7.0, 3.6, rgb(.75, 1, .45), delay=1.1)},
    'mewtwo': {'stats': (2900, 60, 70, 95, 70, 80), 'move': 5.0,
               'auto': ranged(28, 13, .9, 20, .8, rgb(.85, .45, 1)),
               'special': nova('Psyko', 'spec', 24, 5.0, 18, rgb(.8, .4, 1), speed=11, size=.7)},
    'regigigas': {'stats': (7200, 110, 110, 60, 110, 60), 'move': 4.5, 'auto': melee(46, 4.5, 1.6),
                  'special': wave('Presse', 'phys', 55, 6.0, 12, rgb(.95, .9, .75), speed=9, fx='roche')},
}
NEUTRAL_GROWTH = {'hp': .10, 'atk': .08, 'def': .04, 'spa': .08, 'spd': .04, 'spe': 0}

# Bonus temporaires. 'effects' : ce qu'ils changent (voir aussi items.py, même format) :
#   'stats' : {stat: +x %} ; 'flat' : {stat: +x} ; 'dmg' : dégâts infligés (+.25 = +25 %) ;
#   'taken' : dégâts subis (-.25 = -25 %) ; 'cdr' : réduction des temps de recharge ;
#   'as' : vitesse d'attaque ; 'ms' : vitesse de déplacement ; 'regen' : PV/s ;
#   'regen_pct' : part des PV max rendue par seconde ; 'lifesteal' : part des dégâts récupérée ;
#   'burn_auto' : les auto-attaques brûlent (durée en s).
BUFFS = {
    # camps de la jungle : Magmar, Lokhlass, Héliatronc
    'braise': {'name': 'Braise ardente', 'desc': '+20 % Attaque, +25 % vitesse d\'attaque, auto-attaques brûlantes',
               'duration': 90, 'color': color.rgb(1, .4, .15),
               'effects': {'stats': {'atk': .2}, 'as': .25, 'burn_auto': 2.0}},
    'flux': {'name': 'Carapace marine', 'desc': '+15 % PV, +20 % Défense et Déf. Spé., régénération',
             'duration': 90, 'color': color.rgb(.35, .7, 1),
             'effects': {'stats': {'hp': .15, 'def': .2, 'spd': .2}, 'regen_pct': .008}},
    'seve': {'name': 'Sève solaire', 'desc': '+20 % Att. Spé., -20 % temps de recharge', 'duration': 90,
             'color': color.rgb(.55, 1, .35), 'effects': {'stats': {'spa': .2}, 'cdr': .2}},
    # boss et talents
    'psy': {'name': 'Aura psychique', 'desc': '+20 % dégâts, -20 % subis', 'duration': 75,
            'color': color.rgb(.8, .45, 1), 'effects': {'dmg': .2, 'taken': -.2}},
    'impudence': {'name': 'Impudence', 'desc': '+25 % dégâts', 'duration': 10, 'color': color.rgb(.9, .7, .4),
                  'effects': {'dmg': .25}},
}

# Camps symétriques (Ouest / Est). 'buff' : bonus pour le Pokémon qui achève le camp.
# 'xp' et 'gold' : partagés entre les Pokémon du camp (chacun rapporte sa part à qui l'achève).
CAMPS = [
    {'species': 'magmar', 'pos': (-50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'magmar', 'pos': (50, 55), 'buff': 'braise', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'lokhlass', 'pos': (-34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'lokhlass', 'pos': (34, -30), 'buff': 'flux', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'heliatronc', 'pos': (-24, 42), 'buff': 'seve', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'heliatronc', 'pos': (24, 42), 'buff': 'seve', 'respawn': 90, 'xp': 120, 'gold': 200, 'points': 10},
    {'species': 'rattata', 'count': 3, 'pos': (-58, -16), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (58, -16), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-50, -72), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (50, -72), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (-86, 58), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 3, 'pos': (86, 58), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (-24, 70), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
    {'species': 'rattata', 'count': 2, 'pos': (24, 70), 'respawn': 45, 'xp': 45, 'gold': 90, 'points': 3},
]
CAMP_LEASH = 16                # un Pokémon neutre ne s'éloigne pas plus de son camp

# Petits Pokémon sauvages dispersés dans toute la jungle (en plus des camps).
WILD = {
    'count': 34,                               # nombre d'emplacements
    'species': ['chenipan', 'rattata'],        # (Roucool et Mystherbe forment les vagues des voies)
    'hp_factor': .55,                          # les Rattata sauvages sont plus faibles que ceux des camps
    'xp': 36, 'gold': 40, 'points': 1, 'respawn': 40,
    'leash': 9,                                # distance de poursuite maximale
    'wander': 3.5,                             # rayon de promenade autour de leur coin
}

# Boss légendaires du Boss Pit (centre de la carte).
# Calendrier calé sur une partie de 10 min : Mewtwo à 3:30 (puis 3 min après sa défaite),
# Regigigas pour le final à 7:00 (il remplace Mewtwo).
# 'xp' et 'gold' des boss : pour chaque Pokémon de l'équipe qui les bat.
LEGENDARY = {'species': 'mewtwo', 'first_spawn': 210, 'respawn': 180, 'xp': 150, 'gold': 250, 'points': 120, 'buff': 'psy'}
FINAL_BOSS = {'species': 'regigigas', 'spawn': 7 * 60, 'xp': 200, 'gold': 350, 'points': 250, 'buff': 'psy'}

# Zones de soin : buissons de Baies Sitrus. Marcher dessus soigne tout de suite (part des PV max
# + PV fixes) puis le buisson repousse après 'respawn' secondes. Positions symétriques Ouest / Est,
# toutes dans des couloirs praticables de la jungle.
HEAL_PADS = {
    'positions': [(-34, 68), (34, 68), (-41, 13), (41, 13), (-21, -59), (21, -59)],
    'heal_pct': .2,            # 20 % des PV max
    'heal_flat': 60,
    'radius': 1.8,
    'respawn': 120,            # secondes avant que les baies repoussent
    'min_missing': .1,         # ne se déclenche que s'il manque au moins 10 % des PV
}
