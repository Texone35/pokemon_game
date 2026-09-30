"""Combat : table des types, statuts, récupération et talents."""

# ---------------------------------------------------------------- types
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
DAMAGE_SPREAD = .08            # dégâts aléatoires : ±8 %

# ---------------------------------------------------------------- statuts
BURN = {'damage': 4, 'tick': .6}   # brûlure : dégâts bruts toutes les 0,6 s
SLOW_FACTOR = .55              # ralenti : vitesse de déplacement x 0,55

# ---------------------------------------------------------------- récupération
REGEN = 1.0                    # PV/s rendus en permanence aux Pokémon des équipes
NEUTRAL_REGEN = .15            # Pokémon neutres hors combat : part de leurs PV max rendue par seconde
NEUTRAL_CALM = 3.0             # secondes sans être touché avant qu'un neutre se soigne
XP_SHARE_RADIUS = 16           # les alliés à cette distance reçoivent une part de l'XP d'un K.O.
XP_SHARE = .5                  # ... cette part

# ---------------------------------------------------------------- talents
# Un effet permanent propre à chaque lignée (toutes ses formes) : (nom, description, réglages).
TRAITS = {
    'pikachu': ('Statik', 'Attaque de base : 20 % de chances d\'étourdir 0,5 s', {'chance': .2, 'stun': .5}),
    'salameche': ('Brasier', '+25 % de dégâts sous 40 % de PV', {'dmg': .25, 'below': .4}),
    'carapuce': ('Torrent', 'Dans la rivière : +10 % de vitesse en plus et +4 PV/s', {'speed': .1, 'regen': 4}),
    'bulbizarre': ('Photosynthèse', '+3 PV/s en permanence', {'regen': 3}),
    'racaillou': ('Fermeté', '-15 % de dégâts subis', {'taken': -.15}),
    'stalgamin': ('Corps Gel', 'Attaque de base : ralentit 1 s', {'slow': 1.0}),
    'hericendre': ('Éruption', '+20 % de dégâts au-dessus de 70 % de PV', {'dmg': .2, 'above': .7}),
    'kaiminus': ('Mâchoire', 'Récupère 25 % des dégâts infligés au contact', {'drain': .25}),
    'arcko': ('Engrais', '+30 % de vitesse dans les hautes herbes', {'speed': .3}),
    'abra': ('Téléport', 'Esquive deux fois plus longue', {'dash': 2.0}),
    'machoc': ('Cran', '+30 % de dégâts sous 50 % de PV', {'dmg': .3, 'below': .5}),
    'fantominus': ('Spectral', 'Reste caché dans les hautes herbes même en attaquant', {}),
    'minidraco': ('Multiécaille', '-30 % de dégâts subis au-dessus de 80 % de PV', {'taken': -.3, 'above': .8}),
    'wattouat': ('Plus', 'Lui et ses alliés à moins de 8 m : +10 % de dégâts', {'dmg': .1}),
    'embrylex': ('Impudence', 'Après un K.O. : +25 % de dégâts pendant 10 s', {}),
    'sorbebe': ('Écran Neige', 'Lui et ses alliés à moins de 8 m : -10 % de dégâts subis', {'taken': -.1}),
}
AURA_RANGE = 8.0               # portée des talents d'aura (Plus, Écran Neige)
