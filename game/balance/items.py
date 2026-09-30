"""Objets tenus : achetés à la boutique (dans sa base ou pendant qu'on est K.O.), touche B.

Chaque objet a un prix en Poké Dollars (₽) et des effets, au même format que les buffs de la
jungle (voir jungle.py : BUFFS), plus quelques effets propres aux objets :
  'recoil'    : part des PV max perdue à chaque attaque lancée (Orbe Vie)
  'thorns'    : part des dégâts reçus au contact renvoyée à l'attaquant (Casque Brut)
  'sash'      : survit à un coup fatal avec 1 PV, puis attend ce nombre de secondes (Ceinture Force)
  'heal_boost': soins reçus augmentés (Grosse Racine)
"""
ITEM_SLOTS = 3                 # nombre d'objets qu'un Pokémon peut tenir
SELL_RATIO = .5                # un objet revendu rapporte la moitié de son prix
SHOP_RANGE = 3.0               # boutique accessible jusqu'à cette distance au-delà du bord de la base

ITEMS = {
    'restes': {'name': 'Restes', 'price': 800, 'desc': '+140 PV, rend 1 % des PV max par seconde',
               'effects': {'flat': {'hp': 140}, 'regen_pct': .01}},
    'orbe_vie': {'name': 'Orbe Vie', 'price': 1000, 'desc': '+20 % de dégâts, coûte 4 % des PV max par attaque',
                 'effects': {'dmg': .2, 'recoil': .04}},
    'bandeau_choix': {'name': 'Bandeau Choix', 'price': 950, 'desc': '+25 % Attaque (et auto-attaques)',
                      'effects': {'stats': {'atk': .25}}},
    'lunettes_choix': {'name': 'Lunettes Choix', 'price': 950, 'desc': '+25 % Attaque spéciale',
                       'effects': {'stats': {'spa': .25}}},
    'mouchoir_choix': {'name': 'Mouchoir Choix', 'price': 900, 'desc': "+20 % Vitesse (attaque et déplacement)",
                       'effects': {'stats': {'spe': .2}}},
    'veste_combat': {'name': 'Veste de Combat', 'price': 850, 'desc': '+30 % Défense spéciale, +80 PV',
                     'effects': {'stats': {'spd': .3}, 'flat': {'hp': 80}}},
    'casque_brut': {'name': 'Casque Brut', 'price': 850, 'desc': '+25 % Défense, renvoie 15 % des coups au contact',
                    'effects': {'stats': {'def': .25}, 'thorns': .15}},
    'ceinture_force': {'name': 'Ceinture Force', 'price': 700, 'desc': 'Survit à un coup fatal (1 fois / 60 s), +60 PV',
                       'effects': {'flat': {'hp': 60}, 'sash': 60}},
    'grelot_coque': {'name': 'Grelot Coque', 'price': 900, 'desc': 'Récupère 12 % des dégâts infligés',
                     'effects': {'lifesteal': .12}},
    'grosse_racine': {'name': 'Grosse Racine', 'price': 750, 'desc': '+30 % de soins reçus, +10 % Déf. Spé.',
                      'effects': {'heal_boost': .3, 'stats': {'spd': .1}}},
}

BOT_SHOP_MARGIN = 150          # l'ordinateur rentre acheter quand il a le prix de l'objet + cette marge
BOT_SHOP_DISTANCE = 80         # ... et qu'il n'est pas à plus de cette distance de sa base

# Ce que l'ordinateur achète, dans l'ordre, selon le rôle ('attaque' : Bandeau ou Lunettes Choix
# selon que le Pokémon frappe surtout en physique ou en spécial).
BOT_ITEMS = {
    'tank': ['restes', 'casque_brut', 'veste_combat'],
    'combattant': ['attaque', 'grelot_coque', 'restes'],
    'rapide': ['attaque', 'mouchoir_choix', 'orbe_vie'],
    'sniper': ['attaque', 'orbe_vie', 'mouchoir_choix'],
    'soutien': ['grosse_racine', 'restes', 'veste_combat'],
}
