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

# valeurs d'équilibrage : voir le dossier game/balance/
from game.balance.arenas import *   # noqa: F401,F403
from game.balance.combat import *   # noqa: F401,F403
from game.balance.economy import *  # noqa: F401,F403
from game.balance.items import *    # noqa: F401,F403
from game.balance.jungle import *   # noqa: F401,F403
from game.balance.lanes import *    # noqa: F401,F403
from game.balance.moves import *    # noqa: F401,F403
from game.balance.rules import *    # noqa: F401,F403
from game.balance.stats import *    # noqa: F401,F403

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

# ---------------------------------------------------------------- carte
FIELD_RADIUS = 118             # terrain de jeu (entouré par les tribunes)
ARENA_RADIUS = 14              # zone de capture d'une arène
PIT_RADIUS = 11
TREE_SPACING = 4.2             # densité de la jungle

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

# ---------------------------------------------------------------- espèces
# Aspect des Pokémon sur le terrain : nom, type, rayon de collision, taille du modèle 3D.
# Leurs stats et leurs attaques sont dans game/balance/ (stats.py, moves.py, jungle.py).
def S(name, type_, radius, scale):
    return {'name': name, 'type': type_, 'radius': radius, 'scale': scale}


SPECIES = {
    'pikachu': S('Pikachu', 'electrik', 0.6, 1.35),
    'salameche': S('Salamèche', 'feu', 0.6, 1.35),
    'carapuce': S('Carapuce', 'eau', 0.6, 1.35),
    'bulbizarre': S('Bulbizarre', 'plante', 0.7, 1.35),
    'racaillou': S('Racaillou', 'roche', 0.8, 1.3),
    'stalgamin': S('Stalgamin', 'glace', 0.6, 1.35),
    'raichu': S('Raichu', 'electrik', 0.65, 1.5),
    'mega_raichu': S('Méga-Raichu', 'electrik', 0.75, 1.7),
    'mega_dracaufeu': S('Méga-Dracaufeu X', 'feu', 0.9, 1.9),
    'mega_florizarre': S('Méga-Florizarre', 'plante', 1.0, 1.8),
    'reptincel': S('Reptincel', 'feu', 0.65, 1.5),
    'dracaufeu': S('Dracaufeu', 'feu', 0.85, 1.8),
    'carabaffe': S('Carabaffe', 'eau', 0.65, 1.5),
    'tortank': S('Tortank', 'eau', 0.9, 1.75),
    'herbizarre': S('Herbizarre', 'plante', 0.75, 1.5),
    'florizarre': S('Florizarre', 'plante', 0.95, 1.7),
    'gravalanch': S('Gravalanch', 'roche', 0.9, 1.45),
    'grolem': S('Grolem', 'roche', 1.05, 1.6),
    'oniglali': S('Oniglali', 'glace', 0.8, 1.45),
    'mega_oniglali': S('Méga-Oniglali', 'glace', 0.9, 1.6),
    'rattata': S('Rattata', 'normal', 0.5, 1.2),
    'chenipan': S('Chenipan', 'plante', 0.45, 1.15),
    'roucool': S('Roucool', 'normal', 0.5, 1.15),
    'mystherbe': S('Mystherbe', 'plante', 0.45, 1.2),
    'magmar': S('Magmar', 'feu', 1.0, 1.9),
    'lokhlass': S('Lokhlass', 'eau', 1.3, 1.8),
    'torterra': S('Torterra', 'plante', 1.5, 1.7),
    'heliatronc': S('Héliatronc', 'plante', 1.3, 1.7),
    'tour': S('Tour', 'normal', 1.1, 1.0),
    'mewtwo': S('Mewtwo', 'psy', 1.3, 2.2),
    'regigigas': S('Regigigas', 'normal', 2.0, 2.4),
    'hericendre': S('Héricendre', 'feu', 0.6, 1.3),
    'feurisson': S('Feurisson', 'feu', 0.7, 1.5),
    'typhlosion': S('Typhlosion', 'feu', 0.9, 1.75),
    'kaiminus': S('Kaiminus', 'eau', 0.65, 1.3),
    'crocrodil': S('Crocrodil', 'eau', 0.8, 1.55),
    'aligatueur': S('Aligatueur', 'eau', 1.0, 1.8),
    'arcko': S('Arcko', 'plante', 0.55, 1.3),
    'massko': S('Massko', 'plante', 0.65, 1.5),
    'jungko': S('Jungko', 'plante', 0.75, 1.7),
    'abra': S('Abra', 'psy', 0.55, 1.3),
    'kadabra': S('Kadabra', 'psy', 0.62, 1.5),
    'alakazam': S('Alakazam', 'psy', 0.7, 1.65),
    'machoc': S('Machoc', 'combat', 0.65, 1.3),
    'machopeur': S('Machopeur', 'combat', 0.8, 1.55),
    'mackogneur': S('Mackogneur', 'combat', 1.0, 1.8),
    'fantominus': S('Fantominus', 'spectre', 0.6, 1.3),
    'spectrum': S('Spectrum', 'spectre', 0.65, 1.5),
    'ectoplasma': S('Ectoplasma', 'spectre', 0.8, 1.65),
    'minidraco': S('Minidraco', 'dragon', 0.6, 1.3),
    'draco': S('Draco', 'dragon', 0.8, 1.6),
    'dracolosse': S('Dracolosse', 'dragon', 1.05, 1.8),
    'wattouat': S('Wattouat', 'electrik', 0.6, 1.3),
    'lainergie': S('Lainergie', 'electrik', 0.7, 1.5),
    'pharamp': S('Pharamp', 'electrik', 0.85, 1.75),
    'embrylex': S('Embrylex', 'roche', 0.6, 1.3),
    'ymphect': S('Ymphect', 'roche', 0.8, 1.5),
    'tyranocif': S('Tyranocif', 'roche', 1.1, 1.85),
    'sorbebe': S('Sorbébé', 'glace', 0.6, 1.3),
    'sorboul': S('Sorboul', 'glace', 0.7, 1.5),
    'sorbouboul': S('Sorbouboul', 'glace', 0.9, 1.7),
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
PLAYABLE = list(LINES)
PLAYABLE_ROLE = {                  # courte description affichée dans le salon
    'pikachu': 'Rapide et mobile, attaques électriques à distance',
    'salameche': 'Gros dégâts de feu, brûle ses cibles',
    'carapuce': 'Solide, repousse les groupes avec Surf',
    'bulbizarre': 'Soutien : soigne les alliés proches',
    'racaillou': 'Colosse au contact, fonce dans la mêlée',
    'stalgamin': 'Contrôle : ralentit et étourdit les adversaires',
    'hericendre': 'Mage de feu : grosses explosions, plus fort en pleine santé',
    'kaiminus': 'Cogneur : mord au contact et se soigne en frappant',
    'arcko': 'Assassin : très rapide, file à travers les hautes herbes',
    'abra': 'Mage fragile : se téléporte, frappe de loin',
    'machoc': 'Cogneur : encaisse, frappe plus fort quand il est blessé',
    'fantominus': 'Embusqueur : reste invisible dans les hautes herbes même en attaquant',
    'minidraco': "Colosse : très résistant tant qu'il est en pleine forme",
    'wattouat': 'Soutien : renforce les alliés proches, soigne, tire de loin',
    'embrylex': 'Tank : chaque K.O. le rend plus dangereux',
    'sorbebe': 'Contrôle : ralentit tout le monde, protège ses alliés',
}

# ---------------------------------------------------------------- évolutions
EVOLUTIONS = {k: v['evolutions'] for k, v in LINES.items()}


def evolution_line(species):
    """Formes successives d'un Pokémon : [forme de base, 1re évolution, 2e évolution]."""
    return [species] + [f for _, f in EVOLUTIONS.get(species, ())]


def evolution_stage(species, level):
    return sum(1 for lvl, _ in EVOLUTIONS.get(species, ()) if level >= lvl)


def form_for(species, level):
    """Forme d'un Pokémon (clé de SPECIES) à un niveau donné."""
    return evolution_line(species)[evolution_stage(species, level)]


def build_roster(team, humans=(), seed=None, builds=None):
    """Équipe `team` : les Pokémon choisis par les joueurs humains d'abord, puis des IA.

    Les IA gardent les rôles de ROSTERS (dans l'ordre). Avec `seed`, leurs Pokémon sont tirés au
    hasard parmi les jouables (même tirage sur les deux PC, sans doublon dans une équipe ni avec
    les joueurs) ; sans `seed`, ce sont ceux de ROSTERS."""
    import random
    humans = [h for h in humans if h] if team == 'rouge' else []
    builds = list(builds or []) + ['standard'] * len(humans)
    roster = [{'species': s, 'role': 'libre', 'player': True, 'human': i, 'build': builds[i]}
              for i, s in enumerate(humans)]
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
        build = 'standard'
        if rng is not None and s in BUILDS:          # l'ordinateur varie aussi ses builds
            build = rng.choice(['standard'] + list(BUILDS[s]))
        roster.append({'species': s, 'role': e['role'], 'player': False, 'build': build})
    return roster


# ---------------------------------------------------------------- multijoueur
NET = {
    'port': 47650,             # port TCP et UDP de l'hôte (à ouvrir sur la box si l'UPnP ne marche pas)
    'snapshot_rate': 20,       # états du monde envoyés par seconde (hôte -> invité)
    'input_rate': 30,          # positions envoyées par seconde (invité -> hôte)
    'interp_delay': .1,        # retard volontaire de l'affichage chez l'invité (lisse les à-coups du réseau)
    'upnp': True,              # ouvrir automatiquement le port sur la box (UPnP)
}
