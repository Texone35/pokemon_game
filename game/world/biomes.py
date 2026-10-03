"""Biomes de la carte : chaque arène donne son caractère à la jungle qui l'entoure.

Le type de chaque arène est tiré au début de la partie (config.draw_map) : la jungle autour
prend le biome de ce type. Thèmes disponibles :
  roche    : plateau de grès en terrasses, falaises striées, végétation rare
  plante   : forêt luxuriante, arbre millénaire
  electrik : forêt tempérée, centrale électrique (tours Tesla, lignes)
  eau      : lagon (sable, arbres en fleurs, cristaux, cascades)
  feu      : champ volcanique (basalte, coulées de lave, arbres calcinés, volcan)
  + les 13 autres types (glace, poison, spectre, fée...) : éléments et grands décors dans themes.py
  jungle   : le reste de la carte (centre, bases)

Les biomes ne changent que le décor (relief des massifs, couleurs du sol, végétation) :
les murs, les couloirs et les buissons de la jungle restent ceux du tracé (stadium.py).
Le passage d'un biome à l'autre est progressif (poids qui se mélangent).

Les poids ont toujours 7 canaux : jungle, les 5 secteurs (un par arène, dans l'ordre de SLOTS),
puis un canal toujours nul. set_layout() range dans KEYS le type de chaque secteur et donne aux
constantes ROCHE, FEU... le numéro de leur canal (le canal nul si ce type n'est pas tiré) : le
code qui lit W[..., biomes.FEU] ou compare un biome à biomes.ROCHE marche quelle que soit la carte.
Pour ajouter un thème : une entrée dans chaque table *_T ci-dessous (et dans celles de stadium.py).
"""
import numpy as np

# secteurs (un par arène) : angle vu du centre (0° = Nord, 90° = Est), à mi-chemin entre arènes voisines
SLOTS = ('nord', 'ouest', 'est', 'sud_ouest', 'sud_est')
SECTORS = {
    'nord': (-37, 37),
    'est': (37, 97),
    'sud_est': (97, 172),
    'sud_ouest': (-172, -97),
    'ouest': (-97, -37),
}
BLEND = 9.0             # demi-largeur (degrés) des lisières entre deux biomes
CORE = (20.0, 34.0)     # rayon du cœur de la carte (jungle), avec son fondu
JUNGLE, NONE = 0, 6     # canal de la jungle, canal toujours nul

KEYS = ()
ROCHE = PLANTE = ELECTRIK = EAU = FEU = NONE


def set_layout(types):
    """Range le type de chaque secteur (dictionnaire clé d'arène -> type) et recalcule les tables."""
    global KEYS, ROCHE, PLANTE, ELECTRIK, EAU, FEU
    global LAWN, TRAIL, TRAIL_DIRT, TRAIL_EDGE, FOREST, ROCK, BANK
    KEYS = ('jungle',) + tuple(types[k] for k in SLOTS) + ('none',)
    ROCHE, PLANTE, ELECTRIK, EAU, FEU = (of(t) for t in ('roche', 'plante', 'electrik', 'eau', 'feu'))
    LAWN, TRAIL, FOREST = by_slot(LAWN_T), by_slot(TRAIL_T), by_slot(FOREST_T)
    ROCK, BANK = by_slot(ROCK_T), by_slot(BANK_T)
    TRAIL_DIRT = [(a, a) for a, _ in TRAIL]
    TRAIL_EDGE = [(b, b) for _, b in TRAIL]


def of(t):
    """Canal du biome de type t (le canal nul s'il n'est pas sur la carte)."""
    return KEYS.index(t) if t in KEYS[:NONE] else NONE


def by_slot(table):
    """Table {type: valeur} -> liste dans l'ordre des canaux (le canal nul reprend la jungle)."""
    return [table.get(k, table['jungle']) for k in KEYS]


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def weights_np(x, z):
    """Poids des 7 canaux (somme 1) aux points numpy (x, z) : tableau (..., 7)."""
    x, z = np.asarray(x, float), np.asarray(z, float)
    r = np.hypot(x, z)
    # frontières ondulées plutôt que des rayons parfaitement droits
    ang = np.degrees(np.arctan2(x, z)) + 7 * np.sin(r * .09 + 1.3) + 3 * np.sin(r * .23)
    core = _smooth(CORE[0], CORE[1] + 4 * np.sin(ang * .1), r)
    w = []
    for k in SLOTS:
        a0, a1 = SECTORS[k]
        c, h = (a0 + a1) / 2, (a1 - a0) / 2
        d = np.abs((ang - c + 180) % 360 - 180)
        w.append(_smooth(h + BLEND, h - BLEND, d) * core)
    w = np.stack(w, -1)
    total = w.sum(-1, keepdims=True)
    w = w / np.maximum(total, 1)
    return np.concatenate([np.clip(1 - w.sum(-1, keepdims=True), 0, 1), w, np.zeros_like(w[..., :1])], -1)


class BiomeMap:
    """Poids des biomes précalculés sur une grille (lecture rapide point par point)."""

    RES = 2.0

    def __init__(self, radius):
        n = int(radius / self.RES) + 2
        self.n, self.x0 = 2 * n + 1, -n * self.RES
        xs = self.x0 + np.arange(self.n) * self.RES
        X, Z = np.meshgrid(xs, xs, indexing='ij')
        self.w = weights_np(X, Z)

    def at(self, x, z):
        i = min(max(int(round((x - self.x0) / self.RES)), 0), self.n - 1)
        j = min(max(int(round((z - self.x0) / self.RES)), 0), self.n - 1)
        return self.w[i, j]

    def main(self, x, z):
        """Biome dominant en (x, z)."""
        return int(np.argmax(self.at(x, z)))

    def pick(self, rng, x, z):
        """Biome tiré au hasard selon les poids : les lisières mélangent les deux décors."""
        w = self.at(x, z)
        r = rng.random()
        for k, v in enumerate(w):
            r -= v
            if r <= 0:
                return k
        return JUNGLE


# ---------------------------------------------------------------- palettes (r, g, b), par type
# sol praticable (deux teintes mélangées par un bruit)
LAWN_T = {'jungle': ((.42, .72, .27), (.35, .64, .22)),
          'roche': ((.66, .58, .4), (.58, .52, .34)),        # terre sèche et herbe rase
          'plante': ((.33, .64, .22), (.26, .55, .17)),      # herbe grasse
          'electrik': ((.5, .7, .3), (.42, .62, .26)),       # herbe plus jaune
          'eau': ((.44, .72, .42), (.36, .64, .38)),         # herbe fraîche
          'feu': ((.3, .26, .24), (.38, .31, .26)),          # cendre et scories
          'normal': ((.55, .74, .33), (.48, .68, .28)),      # prairie
          'glace': ((.88, .92, .96), (.8, .86, .92)),        # neige
          'combat': ((.58, .6, .36), (.5, .54, .3)),         # herbe de montagne
          'poison': ((.42, .46, .3), (.36, .4, .28)),        # marais
          'sol': ((.72, .58, .38), (.66, .52, .33)),         # terre de canyon
          'vol': ((.6, .8, .5), (.54, .74, .46)),            # herbe d'altitude
          'psy': ((.62, .5, .7), (.56, .44, .66)),           # mousse mauve
          'insecte': ((.46, .6, .22), (.4, .54, .18)),       # sous-bois dense
          'spectre': ((.34, .38, .36), (.3, .33, .33)),      # herbe grise
          'dragon': ((.46, .5, .42), (.4, .44, .38)),
          'tenebres': ((.24, .26, .3), (.2, .22, .26)),      # sol de nuit
          'acier': ((.56, .58, .6), (.5, .52, .55)),         # dalles et gravier
          'fee': ((.62, .82, .58), (.7, .86, .66))}          # prairie fleurie
# sentiers des couloirs de la jungle : (terre battue, bordure de cailloux)
TRAIL_T = {'jungle': ((.62, .5, .33), (.42, .36, .27)),      # terre claire
           'roche': ((.7, .5, .34), (.48, .36, .27)),        # terre ocre (contraste avec le grès)
           'plante': ((.6, .48, .31), (.4, .34, .24)),
           'electrik': ((.64, .58, .48), (.42, .4, .38)),    # gravier
           'eau': ((.8, .73, .56), (.55, .5, .42)),          # sable blond
           'feu': ((.6, .52, .44), (.2, .17, .16)),          # cendre claire bordée de basalte
           'normal': ((.66, .55, .38), (.46, .4, .3)), 'glace': ((.72, .78, .84), (.5, .56, .64)),
           'combat': ((.62, .48, .36), (.44, .34, .26)), 'poison': ((.4, .36, .32), (.28, .24, .24)),
           'sol': ((.6, .44, .3), (.42, .3, .2)), 'vol': ((.78, .74, .62), (.56, .54, .48)),
           'psy': ((.78, .66, .82), (.52, .42, .6)), 'insecte': ((.5, .42, .28), (.36, .3, .2)),
           'spectre': ((.4, .38, .42), (.26, .24, .3)), 'dragon': ((.5, .44, .5), (.32, .28, .36)),
           'tenebres': ((.3, .28, .32), (.16, .14, .18)), 'acier': ((.62, .62, .64), (.38, .38, .42)),
           'fee': ((.9, .8, .82), (.7, .58, .66))}
# sous-bois (couloirs et sommets des massifs)
FOREST_T = {'jungle': ((.22, .42, .15), (.28, .38, .16)),
            'roche': ((.55, .46, .32), (.47, .39, .27)),
            'plante': ((.17, .38, .12), (.23, .35, .13)),
            'electrik': ((.24, .43, .17), (.3, .4, .18)),
            'eau': ((.2, .42, .3), (.26, .46, .3)),
            'feu': ((.19, .16, .15), (.25, .2, .17)),
            'normal': ((.3, .48, .2), (.36, .46, .22)), 'glace': ((.78, .84, .9), (.7, .78, .86)),
            'combat': ((.3, .34, .18), (.36, .32, .2)), 'poison': ((.26, .2, .3), (.3, .24, .34)),
            'sol': ((.6, .46, .3), (.52, .4, .26)), 'vol': ((.4, .6, .38), (.46, .64, .4)),
            'psy': ((.36, .26, .46), (.42, .3, .52)), 'insecte': ((.2, .32, .1), (.26, .3, .12)),
            'spectre': ((.18, .18, .24), (.22, .2, .28)), 'dragon': ((.26, .24, .34), (.3, .26, .4)),
            'tenebres': ((.12, .12, .16), (.16, .14, .2)), 'acier': ((.4, .42, .44), (.46, .46, .5)),
            'fee': ((.36, .6, .42), (.42, .64, .48))}
# roche des pentes raides
ROCK_T = {'jungle': (.5, .47, .43), 'roche': (.76, .58, .4), 'plante': (.47, .45, .4), 'electrik': (.5, .5, .48),
          'eau': (.54, .59, .62), 'feu': (.17, .15, .15), 'normal': (.62, .6, .55), 'glace': (.62, .72, .8),
          'combat': (.55, .45, .4), 'poison': (.4, .34, .42), 'sol': (.7, .52, .36), 'vol': (.78, .78, .76),
          'psy': (.6, .5, .7), 'insecte': (.46, .44, .36), 'spectre': (.4, .4, .46), 'dragon': (.42, .38, .56),
          'tenebres': (.26, .24, .3), 'acier': (.55, .57, .6), 'fee': (.8, .72, .8)}
# berges de la rivière
BANK_T = {'jungle': (.76, .7, .52), 'roche': (.78, .72, .6), 'plante': (.74, .7, .5), 'electrik': (.72, .7, .56),
          'eau': (.86, .8, .62), 'feu': (.3, .27, .26), 'normal': (.78, .74, .6), 'glace': (.85, .9, .95),
          'combat': (.74, .66, .54), 'poison': (.52, .42, .55), 'sol': (.76, .62, .44), 'vol': (.86, .86, .82),
          'psy': (.82, .72, .86), 'insecte': (.66, .62, .46), 'spectre': (.5, .5, .56), 'dragon': (.6, .56, .66),
          'tenebres': (.36, .34, .4), 'acier': (.68, .7, .72), 'fee': (.92, .84, .9)}
# relief des massifs : 'hill' (collines), 'mesa' (plateau en terrasses), 'lagoon' (bas), 'volcanic' (crêtes, lave)
RELIEF_T = {'jungle': 'hill', 'roche': 'mesa', 'plante': 'hill', 'electrik': 'hill', 'eau': 'lagoon',
            'feu': 'volcanic', 'normal': 'hill', 'glace': 'mesa', 'combat': 'hill', 'poison': 'lagoon',
            'sol': 'mesa', 'vol': 'hill', 'psy': 'hill', 'insecte': 'hill', 'spectre': 'hill', 'dragon': 'mesa',
            'tenebres': 'hill', 'acier': 'mesa', 'fee': 'hill'}
THEMES = tuple(k for k in LAWN_T if k != 'jungle')     # types qui ont un thème complet
# strates du grès (plateau Nord)
STRATA = [(.84, .66, .45), (.7, .46, .31), (.9, .8, .62), (.62, .42, .3), (.78, .6, .42)]
LAVA = (1.0, .42, .06)
LAVA_HOT = (1.0, .78, .25)


set_layout({'nord': 'roche', 'ouest': 'plante', 'est': 'electrik', 'sud_ouest': 'eau', 'sud_est': 'feu'})
