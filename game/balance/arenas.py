"""Arènes : capture, points Dominion, bonus d'équipe et effets de terrain."""

CAPTURE_TIME = 8.0             # secondes pour capturer une arène seul (depuis neutre)
CAPTURE_BONUS_PER_UNIT = 0.35  # chaque allié en plus accélère la capture
# Capturer est une action : dans le cercle d'une arène, on appuie sur CAPTURE_KEY. Le Pokémon reste
# alors immobile et ne peut rien faire d'autre (la touche à nouveau arrête), mais la tour ne lui tire
# plus dessus. Seuls les Pokémon en train de capturer font avancer la capture.
CAPTURE_KEY = 'g'
CAPTURE_DECAY = .3             # sans personne, l'arène revient vers l'état de son propriétaire (x vitesse de capture)

# points Dominion par seconde selon le nombre d'arènes tenues (0 à 5) : chaque arène de plus
# rapporte un peu moins, pour qu'une équipe qui domine ne termine pas la partie trop vite
ARENA_POINTS = (0, .55, 1.1, 1.45, 1.7, 1.9)

# Types d'arène pouvant être tirés en début de partie (5 différents par partie, voir config.draw_map).
# Un type n'entre ici que lorsque tout son thème existe : décor de l'arène (world/arenas.py), biome
# (world/biomes.py, world/stadium.py), grand décor (world/landmarks.py), météo et bonus ci-dessous.
ARENA_TYPES = ('normal', 'feu', 'eau', 'plante', 'electrik', 'glace', 'combat', 'poison', 'sol', 'vol', 'psy',
               'insecte', 'roche', 'spectre', 'dragon', 'tenebres', 'acier', 'fee')
WEATHER_OF = {'roche': 'sable', 'plante': 'pollen', 'electrik': 'orage', 'eau': 'pluie', 'feu': 'soleil',
              'normal': 'clair', 'glace': 'grele', 'combat': 'ferveur', 'poison': 'toxique', 'sol': 'seisme',
              'vol': 'vent', 'psy': 'psychique', 'insecte': 'essaim', 'spectre': 'brume', 'dragon': 'draconique',
              'tenebres': 'nuit', 'acier': 'magnetique', 'fee': 'feerique'}

# Bonus d'équipe tant qu'elle contrôle l'arène du type correspondant.
ARENA_BONUS = {
    'roche': ('defense', .10, '-10 % dégâts subis'),
    'plante': ('regen', 3.0, '+3 PV/s'),
    'electrik': ('speed', .10, '+10 % vitesse'),
    'eau': ('cooldown', .10, '-10 % recharge'),
    'feu': ('damage', .10, '+10 % dégâts'),
    'normal': ('regen', 3.0, '+3 PV/s'),
    'glace': ('defense', .10, '-10 % dégâts subis'),
    'combat': ('damage', .10, '+10 % dégâts'),
    'poison': ('cooldown', .10, '-10 % recharge'),
    'sol': ('defense', .10, '-10 % dégâts subis'),
    'vol': ('speed', .10, '+10 % vitesse'),
    'psy': ('cooldown', .10, '-10 % recharge'),
    'insecte': ('speed', .10, '+10 % vitesse'),
    'spectre': ('damage', .10, '+10 % dégâts'),
    'dragon': ('damage', .10, '+10 % dégâts'),
    'tenebres': ('cooldown', .10, '-10 % recharge'),
    'acier': ('defense', .10, '-10 % dégâts subis'),
    'fee': ('regen', 3.0, '+3 PV/s'),
}

# Effets du terrain selon le type du Pokémon dans la rivière : 'dmg' dégâts infligés, 'taken'
# dégâts subis, 'speed' vitesse (+.2 = +20 %). '*' : tous les autres types. (Dans les arènes, ce
# sont les météos ci-dessous qui s'appliquent.)
ZONE_EFFECTS = {
    'riviere': {'eau': {'speed': .2}, 'glace': {'speed': .1}, 'feu': {'speed': -.2, 'dmg': -.1},
                'electrik': {'dmg': -.1, 'taken': .1}, 'roche': {'speed': -.15}, 'spectre': {},
                '*': {'speed': -.08}},
}

# ---------------------------------------------------------------- météo des arènes
# Quand une équipe contrôle une arène, la météo de l'arène (voir config.ARENAS : 'weather')
# s'installe sur tout le quartier autour (WEATHER_RADIUS mètres autour du centre de l'arène).
# Effets possibles (pour ajouter une météo : une entrée ici, puis 'weather' dans config.ARENAS) :
#   'enemy_dps' : les adversaires de l'équipe qui tient l'arène perdent cette part de leurs PV max par seconde
#   'boost'     : {type: +x} dégâts des Pokémon de ce type de l'équipe qui tient l'arène
#   'heal_pct'  : PV max rendus par seconde à l'équipe qui tient l'arène
#   'ms'        : vitesse de déplacement de l'équipe qui tient l'arène
#   'solaire'   : Lance-Soleil quasi instantané ; 'synthese' : soins de type Synthèse renforcés
#   'sur_pluie' : les attaques électriques de type Fatal-Foudre ne ratent jamais
WEATHER_RADIUS = 34
WEATHER_TICK = .5              # fréquence des dégâts de la tempête de sable (secondes)
WEATHERS = {
    'sable': {'name': 'Tempête de sable', 'desc': 'les adversaires perdent 1,2 % de leurs PV par seconde',
              'enemy_dps': .012},
    'soleil': {'name': 'Zénith', 'desc': '+30 % dégâts Feu, Lance-Soleil instantané, Synthèse renforcée',
               'boost': {'feu': .3}, 'solaire': True, 'synthese': True},
    'pluie': {'name': 'Pluie', 'desc': '+30 % dégâts Eau, Fatal-Foudre ne rate jamais',
              'boost': {'eau': .3}, 'sur_pluie': True},
    'pollen': {'name': 'Champ Herbu', 'desc': 'soigne 1 % des PV par seconde, +15 % dégâts Plante',
               'boost': {'plante': .15}, 'heal_pct': .01},
    'orage': {'name': 'Champ Électrifié', 'desc': '+10 % vitesse, +20 % dégâts Électrik',
              'boost': {'electrik': .2}, 'ms': .1},
    # (les types sans Pokémon jouable donnent des effets pour tous : vitesse, soins, dégâts aux adversaires)
    'clair': {'name': 'Ciel Clair', 'desc': '+8 % vitesse, soigne 0,6 % des PV par seconde', 'ms': .08,
              'heal_pct': .006},
    'grele': {'name': 'Grêle', 'desc': 'les adversaires perdent 0,8 % de leurs PV par seconde, +25 % dégâts Glace',
              'enemy_dps': .008, 'boost': {'glace': .25}},
    'ferveur': {'name': 'Ferveur du Dojo', 'desc': '+30 % dégâts Combat, soigne 0,5 % des PV par seconde',
                'boost': {'combat': .3}, 'heal_pct': .005},
    'toxique': {'name': 'Brume Toxique', 'desc': 'les adversaires perdent 1,2 % de leurs PV par seconde',
                'enemy_dps': .012},
    'seisme': {'name': 'Terrain Sismique', 'desc': 'les adversaires perdent 0,7 % de leurs PV par seconde, +6 % vitesse',
               'enemy_dps': .007, 'ms': .06},
    'vent': {'name': 'Vent Arrière', 'desc': '+15 % vitesse', 'ms': .15},
    'psychique': {'name': 'Champ Psychique', 'desc': '+30 % dégâts Psy, soigne 0,5 % des PV par seconde',
                  'boost': {'psy': .3}, 'heal_pct': .005},
    'essaim': {'name': 'Essaim', 'desc': 'les adversaires perdent 0,7 % de leurs PV par seconde, +6 % vitesse',
               'enemy_dps': .007, 'ms': .06},
    'brume': {'name': 'Brume Spectrale', 'desc': '+30 % dégâts Spectre, les adversaires perdent 0,5 % PV/s',
              'boost': {'spectre': .3}, 'enemy_dps': .005},
    'draconique': {'name': 'Souffle Draconique', 'desc': '+30 % dégâts Dragon, +6 % vitesse',
                   'boost': {'dragon': .3}, 'ms': .06},
    'nuit': {'name': 'Nuit Noire', 'desc': 'les adversaires perdent 1 % de leurs PV par seconde', 'enemy_dps': .01},
    'magnetique': {'name': 'Champ Magnétique', 'desc': 'soigne 1 % des PV par seconde', 'heal_pct': .01},
    'feerique': {'name': 'Champ Brumeux', 'desc': 'soigne 1,2 % des PV par seconde', 'heal_pct': .012},
}
SUN_SOLAR_DELAY = .15          # au soleil, la charge de Lance-Soleil ne dure plus que 15 %
SUN_SYNTHESIS = 1.5            # au soleil, les soins de type Synthèse sont x 1,5

# ---------------------------------------------------------------- tour défensive
# Une tour se dresse au centre d'une arène peu après sa capture. Elle tire sur les adversaires
# dans son rayon (en priorité ceux qui attaquent un Pokémon allié, puis les sbires, puis le plus
# proche) et, tant qu'elle tient debout, ralentit la capture de l'arène par l'adversaire.
# Détruite, elle se relève au bout de 'respawn' secondes si l'arène n'a pas changé de mains.
TOWER = {
    'stats': (1800, 0, 70, 0, 70, 0),     # (PV, -, Déf, -, Déf. Spé., -) à la première minute
    'growth': {'hp': .08, 'def': .05, 'spd': .05},   # renforcement par minute de jeu
    'damage': 40, 'damage_per_min': 5,   # dégâts d'un tir (ignorent la défense)
    'interval': 1.3, 'range': 15.0,
    'build': 12.0,             # délai avant que la tour se dresse après une capture
    'respawn': 90.0,           # délai avant qu'une tour détruite se relève
    'capture_slow': .5,        # capture par l'adversaire x 0,5 tant que la tour tient
    'gold': 200, 'xp': 80,     # pour chaque Pokémon de l'équipe qui l'abat présent à moins de 20 m
    'points': 15,
}
