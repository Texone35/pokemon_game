"""Biomes de la carte : chaque arène donne son caractère à la jungle qui l'entoure.

  roche    (Nord)       : plateau de grès en terrasses, falaises striées, végétation rare
  plante   (Ouest)      : forêt luxuriante, arbre millénaire, serre
  electrik (Est)        : forêt tempérée, centrale électrique (tours Tesla, lignes)
  eau      (Sud-Ouest)  : lagon (sable, arbres en fleurs, cristaux, cascades)
  feu      (Sud-Est)    : champ volcanique (basalte, coulées de lave, arbres calcinés, volcan)
  jungle                : le reste de la carte (centre, bases)

Les biomes ne changent que le décor (relief des massifs, couleurs du sol, végétation) :
les murs, les couloirs et les buissons de la jungle restent ceux du tracé (stadium.py).
Le passage d'un biome à l'autre est progressif (poids qui se mélangent).
"""
import numpy as np

KEYS = ('jungle', 'roche', 'plante', 'electrik', 'eau', 'feu')
JUNGLE, ROCHE, PLANTE, ELECTRIK, EAU, FEU = range(6)

# Chaque biome occupe un secteur autour du Boss Pit (angle vu du centre, 0° = Nord, 90° = Est),
# à mi-chemin entre les arènes voisines. Le cœur de la carte (autour du Boss Pit) et la bande
# de la rivière du Sud entre les deux bases restent de la jungle ordinaire.
SECTORS = {
    'roche': (-37, 37),
    'electrik': (37, 97),
    'feu': (97, 172),
    'eau': (-172, -97),
    'plante': (-97, -37),
}
BLEND = 9.0             # demi-largeur (degrés) des lisières entre deux biomes
CORE = (20.0, 34.0)     # rayon du cœur de la carte (jungle), avec son fondu


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def weights_np(x, z):
    """Poids des 6 biomes (somme 1) aux points numpy (x, z) : tableau (..., 6)."""
    x, z = np.asarray(x, float), np.asarray(z, float)
    r = np.hypot(x, z)
    # frontières ondulées plutôt que des rayons parfaitement droits
    ang = np.degrees(np.arctan2(x, z)) + 7 * np.sin(r * .09 + 1.3) + 3 * np.sin(r * .23)
    core = _smooth(CORE[0], CORE[1] + 4 * np.sin(ang * .1), r)
    w = []
    for k in KEYS[1:]:
        a0, a1 = SECTORS[k]
        c, h = (a0 + a1) / 2, (a1 - a0) / 2
        d = np.abs((ang - c + 180) % 360 - 180)
        w.append(_smooth(h + BLEND, h - BLEND, d) * core)
    w = np.stack(w, -1)
    total = w.sum(-1, keepdims=True)
    w = w / np.maximum(total, 1)
    return np.concatenate([np.clip(1 - w.sum(-1, keepdims=True), 0, 1), w], -1)


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


# ---------------------------------------------------------------- palettes (r, g, b)
# sol praticable (deux teintes mélangées par un bruit), par biome
LAWN = [((.42, .72, .27), (.35, .64, .22)),        # jungle
        ((.66, .58, .4), (.58, .52, .34)),         # roche : terre sèche et herbe rase
        ((.33, .64, .22), (.26, .55, .17)),        # plante : herbe grasse
        ((.5, .7, .3), (.42, .62, .26)),           # electrik : herbe plus jaune
        ((.44, .72, .42), (.36, .64, .38)),        # eau : herbe fraîche
        ((.3, .26, .24), (.38, .31, .26))]         # feu : cendre et scories
# sous-bois (couloirs et sommets des massifs)
FOREST = [((.22, .42, .15), (.28, .38, .16)),
          ((.55, .46, .32), (.47, .39, .27)),
          ((.17, .38, .12), (.23, .35, .13)),
          ((.24, .43, .17), (.3, .4, .18)),
          ((.2, .42, .3), (.26, .46, .3)),
          ((.19, .16, .15), (.25, .2, .17))]
# roche des pentes raides
ROCK = [(.5, .47, .43), (.76, .58, .4), (.47, .45, .4), (.5, .5, .48), (.54, .59, .62), (.17, .15, .15)]
# strates du grès (plateau Nord)
STRATA = [(.84, .66, .45), (.7, .46, .31), (.9, .8, .62), (.62, .42, .3), (.78, .6, .42)]
# berges de la rivière
BANK = [(.76, .7, .52), (.78, .72, .6), (.74, .7, .5), (.72, .7, .56), (.86, .8, .62), (.3, .27, .26)]
LAVA = (1.0, .42, .06)
LAVA_HOT = (1.0, .78, .25)
