"""Statistiques des Pokémon : rôles, courbes de puissance, stats de base, formule de dégâts.

Chaque Pokémon a six stats (dans l'ordre du Pokédex) :
  PV, Attaque (attaques physiques ET auto-attaques), Défense (contre le physique),
  Attaque spéciale, Défense spéciale, Vitesse (vitesse d'attaque ET de déplacement).

Calcul d'une stat pour un Pokémon d'équipe au niveau n (voir game/pokemon/kit.py) :
    valeur = rôle(n, courbe) x signature de la forme x puissance de la lignée
  - rôle(n, courbe) : valeur du rôle entre le niveau 1 et le niveau max (ROLES), suivant la courbe
    de la lignée (CURVES) : « early » progresse vite puis plafonne, « late » part bas et finit haut ;
  - signature : (stat de base officielle / SIGNATURE_REF) ^ SIGNATURE_DAMP. Elle donne à chaque
    Pokémon son caractère (Grolem très solide, Alakazam très rapide...) et fait grimper les stats
    à chaque évolution (les formes évoluées ont de meilleures stats de base) ;
  - puissance de la lignée : LINES[...]['power'] (1.0 = normal), pour ajuster une lignée entière.
"""

STATS = ('hp', 'atk', 'def', 'spa', 'spd', 'spe')
STAT_NAMES = {'hp': 'PV', 'atk': 'Attaque', 'def': 'Défense', 'spa': 'Att. Spé.', 'spd': 'Déf. Spé.',
              'spe': 'Vitesse'}
STAT_SHORT = {'hp': 'PV', 'atk': 'Att', 'def': 'Déf', 'spa': 'AtS', 'spd': 'DéS', 'spe': 'Vit'}
MAX_LEVEL = 15

# ---------------------------------------------------------------- rôles
# Stats au niveau 1 et au niveau MAX_LEVEL (PV, Att, Déf, AtS, DéS, Vit), avant la signature.
ROLES = {
    'tank':       {'name': 'Tank', 'lv1': (600, 48, 58, 36, 54, 64), 'max': (1500, 170, 165, 110, 150, 80)},
    'combattant': {'name': 'Combattant', 'lv1': (540, 54, 46, 36, 42, 70), 'max': (1350, 205, 125, 110, 115, 88)},
    'rapide':     {'name': 'Rapide', 'lv1': (460, 60, 38, 40, 36, 84), 'max': (1150, 245, 100, 130, 95, 110)},
    'sniper':     {'name': 'Sniper', 'lv1': (430, 48, 34, 60, 40, 72), 'max': (1050, 150, 90, 255, 105, 92)},
    'soutien':    {'name': 'Soutien', 'lv1': (500, 38, 44, 50, 52, 68), 'max': (1250, 110, 120, 190, 140, 84)},
}

# Composition conseillée d'une équipe (salon) : au moins un Pokémon de ces rôles, et pas plus de
# TEAM_MAX_SAME Pokémon du même rôle.
TEAM_NEEDS = ('tank', 'soutien')
TEAM_MAX_SAME = 2
ROLE_COLORS = {'tank': (.45, .65, 1), 'combattant': (1, .6, .3), 'rapide': (.8, .5, 1), 'sniper': (1, .45, .45),
               'soutien': (.45, 1, .6)}

# Courbes de puissance : 'shape' < 1 = progression rapide au début (early game), > 1 = progression
# lente puis forte (late game). 'lv1' et 'max' multiplient les stats du rôle au niveau 1 et au niveau max.
CURVES = {
    'early':    {'name': 'Early game', 'shape': .7, 'lv1': 1.1, 'max': .9},
    'standard': {'name': 'Équilibré', 'shape': 1.0, 'lv1': 1.0, 'max': 1.0},
    'late':     {'name': 'Late game', 'shape': 1.4, 'lv1': .9, 'max': 1.16},
}

SIGNATURE_REF = 80             # stat de base officielle qui vaut x 1
SIGNATURE_DAMP = .4            # 0 = tous pareils, 1 = écarts des jeux officiels (très grands)

# ---------------------------------------------------------------- lignées jouables
# 'role' et 'curve' : voir ci-dessus. 'evolutions' : (niveau, forme). 'power' : réglage global.
# Les builds (plusieurs façons de jouer une lignée) sont dans moves.py.
LINES = {
    'pikachu':    {'role': 'sniper', 'curve': 'early', 'evolutions': [(4, 'raichu')], 'power': 1.0},
    'salameche':  {'role': 'sniper', 'curve': 'late', 'evolutions': [(5, 'reptincel'), (9, 'dracaufeu')],
                   'power': 1.0},
    'carapuce':   {'role': 'tank', 'curve': 'standard', 'evolutions': [(4, 'carabaffe'), (7, 'tortank')],
                   'power': 1.0},
    'bulbizarre': {'role': 'soutien', 'curve': 'standard', 'evolutions': [(4, 'herbizarre'), (7, 'florizarre')],
                   'power': 1.0},
    'racaillou':  {'role': 'tank', 'curve': 'early', 'evolutions': [(3, 'gravalanch'), (5, 'grolem')],
                   'power': 1.0},
    'stalgamin':  {'role': 'soutien', 'curve': 'standard', 'evolutions': [(5, 'oniglali')], 'power': 1.08},
    'hericendre': {'role': 'sniper', 'curve': 'standard', 'evolutions': [(4, 'feurisson'), (7, 'typhlosion')],
                   'power': 1.0},
    'kaiminus':   {'role': 'combattant', 'curve': 'early', 'evolutions': [(3, 'crocrodil'), (5, 'aligatueur')],
                   'power': 0.9},
    'arcko':      {'role': 'rapide', 'curve': 'standard', 'evolutions': [(4, 'massko'), (7, 'jungko')],
                   'power': 0.95},
    'abra':       {'role': 'sniper', 'curve': 'late', 'evolutions': [(5, 'kadabra'), (9, 'alakazam')],
                   'power': 1.0},
    'machoc':     {'role': 'combattant', 'curve': 'standard', 'evolutions': [(4, 'machopeur'), (7, 'mackogneur')],
                   'power': 0.85},
    'fantominus': {'role': 'rapide', 'curve': 'standard', 'evolutions': [(4, 'spectrum'), (7, 'ectoplasma')],
                   'power': 1.0},
    'minidraco':  {'role': 'combattant', 'curve': 'late', 'evolutions': [(5, 'draco'), (9, 'dracolosse')],
                   'power': 1.0},
    'wattouat':   {'role': 'soutien', 'curve': 'standard', 'evolutions': [(4, 'lainergie'), (7, 'pharamp')],
                   'power': 1.1},
    'embrylex':   {'role': 'tank', 'curve': 'late', 'evolutions': [(5, 'ymphect'), (9, 'tyranocif')],
                   'power': 1.05},
    'sorbebe':    {'role': 'soutien', 'curve': 'standard', 'evolutions': [(4, 'sorboul'), (7, 'sorbouboul')],
                   'power': 1.05},
}

# ---------------------------------------------------------------- stats de base officielles
# (PV, Attaque, Défense, Att. Spé., Déf. Spé., Vitesse) de chaque forme.
BASE_STATS = {
    'pikachu': (35, 55, 40, 50, 50, 90), 'raichu': (60, 90, 55, 90, 80, 110),
    'mega_raichu': (60, 100, 55, 160, 80, 130),
    'salameche': (39, 52, 43, 60, 50, 65), 'reptincel': (58, 64, 58, 80, 65, 80),
    'dracaufeu': (78, 84, 78, 109, 85, 100), 'mega_dracaufeu': (78, 130, 111, 130, 85, 100),
    'carapuce': (44, 48, 65, 50, 64, 43), 'carabaffe': (59, 63, 80, 65, 80, 58),
    'tortank': (79, 83, 100, 85, 105, 78),
    'bulbizarre': (45, 49, 49, 65, 65, 45), 'herbizarre': (60, 62, 63, 80, 80, 60),
    'florizarre': (80, 82, 83, 100, 100, 80), 'mega_florizarre': (80, 100, 123, 122, 120, 80),
    'racaillou': (40, 80, 100, 30, 30, 20), 'gravalanch': (55, 95, 115, 45, 45, 35),
    'grolem': (80, 120, 130, 55, 65, 45),
    'stalgamin': (50, 50, 50, 50, 50, 50), 'oniglali': (80, 80, 80, 80, 80, 80),
    'mega_oniglali': (80, 120, 80, 120, 80, 100),
    'hericendre': (39, 52, 43, 60, 50, 65), 'feurisson': (58, 64, 58, 80, 65, 80),
    'typhlosion': (78, 84, 78, 109, 85, 100),
    'kaiminus': (50, 65, 64, 44, 48, 43), 'crocrodil': (65, 80, 80, 59, 63, 58),
    'aligatueur': (85, 105, 100, 79, 83, 78),
    'arcko': (40, 45, 35, 65, 55, 70), 'massko': (50, 65, 45, 85, 65, 95), 'jungko': (70, 85, 65, 105, 85, 120),
    'abra': (25, 20, 15, 105, 55, 90), 'kadabra': (40, 35, 30, 120, 70, 105),
    'alakazam': (55, 50, 45, 135, 95, 120),
    'machoc': (70, 80, 50, 35, 35, 35), 'machopeur': (80, 100, 70, 50, 60, 45),
    'mackogneur': (90, 130, 80, 65, 85, 55),
    'fantominus': (30, 35, 30, 100, 35, 80), 'spectrum': (45, 50, 45, 115, 55, 95),
    'ectoplasma': (60, 65, 60, 130, 75, 110),
    'minidraco': (41, 64, 45, 50, 50, 50), 'draco': (61, 84, 65, 70, 70, 70),
    'dracolosse': (91, 134, 95, 100, 100, 80),
    'wattouat': (55, 40, 40, 65, 45, 35), 'lainergie': (70, 55, 55, 80, 60, 45),
    'pharamp': (90, 75, 85, 115, 90, 55),
    'embrylex': (50, 64, 50, 45, 50, 41), 'ymphect': (70, 84, 70, 65, 70, 51),
    'tyranocif': (100, 134, 110, 95, 100, 61),
    'sorbebe': (36, 50, 50, 65, 60, 44), 'sorboul': (51, 65, 65, 80, 75, 59),
    'sorbouboul': (71, 95, 85, 110, 95, 79),
}

# ---------------------------------------------------------------- dégâts
# dégâts = puissance / 100 x (DAMAGE_FLAT + stat d'attaque) x bonus de visée
#          x DEFENSE_K / (DEFENSE_K + stat de défense) x type x bonus (buffs, talents, météo)
# La stat d'attaque est l'Attaque pour une attaque physique (et les auto-attaques), l'Attaque
# spéciale pour une attaque spéciale ; la défense est la Défense ou la Défense spéciale.
DAMAGE_FLAT = 20
DEFENSE_K = 300                # défense 300 : dégâts divisés par deux
HEAL_FLAT = 40                 # soins = puissance / 100 x (HEAL_FLAT + Att. Spé.)

# ---------------------------------------------------------------- vitesse
# La Vitesse agit sur la vitesse d'attaque ET sur la vitesse de déplacement, avec deux réglages
# séparés et plafonnés : écart = Vitesse / SPEED_REF - 1.
SPEED_REF = 80
ATTACK_SPEED_K = .8            # vitesse d'attaque x (1 + 0,8 x écart)
ATTACK_SPEED_LIMITS = (.75, 1.6)
MOVE_SPEED = 6.4               # vitesse de déplacement d'un Pokémon à SPEED_REF (m/s)
MOVE_SPEED_K = .4              # déplacement x (1 + 0,4 x écart)
MOVE_SPEED_LIMITS = (.85, 1.18)
