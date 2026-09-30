"""La carte du stade Pokémon Dominion : construction 3D, collisions et navigation.

Disposition (voir config.py) : 5 arènes ouvertes (Nord, Ouest, Est, Sud-Ouest,
Sud-Est ; l'Arène Nord est perchée sur un plateau, accessible par un escalier et des
rampes là où arrivent les voies), les bases des deux équipes au sud, le Boss Pit au centre, une
rivière peu profonde (praticable) du nord au sud, des voies principales et une
jungle avec ses camps de Pokémon neutres. Le tout est entouré par les
tribunes du stade.

Jungle (façon MOBA) : des massifs infranchissables (falaises rocheuses ou
rideaux d'arbres) séparés par des couloirs étroits et quelques clairières.
Chaque zone a son biome (biomes.py) qui change le relief des massifs, les couleurs
du sol et la végétation (plateau de grès au Nord, forêt luxuriante à l'Ouest,
forêt et centrale électrique à l'Est, lagon au Sud-Ouest, champ volcanique au
Sud-Est), et un grand décor repère (landmarks.py : volcan, cascades, arbre
millénaire, tour Tesla, ruines...). Ni les biomes ni les grands décors ne
touchent au tracé : murs, couloirs et buissons restent les mêmes.
Les couloirs sont les arêtes d'un diagramme de Voronoï dont les graines sont
symétriques (Ouest / Est). Les murs sont décrits par une fonction distance
signée (self.wall_sdf) qui sert à la fois aux collisions, à la navigation et
au décor. Des hautes herbes (buissons) cachent les Pokémon qui s'y trouvent
aux yeux de l'équipe adverse (voir bush_at et Match._update_bushes).

Tout le décor est procédural : des primitives (boîtes, sphères, cônes...)
fusionnées par MeshBuilder en quelques gros maillages.

Navigation : la carte est quadrillée (cases de NAV_CELL unités). Pour chaque
destination (arène, base, camp...) on calcule une fois la distance de chaque
case à la destination (Dijkstra) ; une IA n'a plus qu'à descendre ce champ.
"""
import math
import random

import numpy as np
from scipy import ndimage
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from ursina import Vec3, color, lerp

from game import config as C
from game.world import biomes
from game.world.emblems import add_emblem
from game.world.fx import Arcs
from game.world.geometry import ROCKS, ChunkedBuilder, MeshBuilder, _rot_matrix, glowing
from game.world.water import WaterBuilder, river_surface, set_time

F = C.FIELD_RADIUS
CELL = 8.0            # grille de collision
NAV_CELL = 2.0        # grille de navigation
J_RES = .5            # finesse de la carte des murs et des buissons de la jungle
CORRIDOR = 3.0        # demi-largeur des couloirs de la jungle
SEED_GAP = 18.0       # écart entre les graines des massifs (plus grand = massifs plus gros)
CLOSED_EDGES = .2    # part des couloirs possibles qui restent fermés

# ---------------------------------------------------------------- palette
LANE = color.rgb(.72, .71, .68)
LANE_EDGE = color.rgb(.46, .47, .5)
CURB = color.rgb(.84, .83, .8)
SEAM = color.rgb(.46, .45, .44)
NEON = color.rgb(.35, .8, 1)
PATH = color.rgb(.62, .5, .34)
WATER = color.rgb(.3, .78, .86)
WATER_DEEP = color.rgb(.1, .5, .78)
WATER_Y = -.38        # surface de la rivière (son lit est creusé dans le relief)
BRIDGE_Y = .28        # hauteur du tablier des ponts (là où l'on marche)
HM_RES = 1.0          # finesse de la carte des hauteurs
ROCK = color.rgb(.6, .57, .52)
ROCK_DARK = color.rgb(.42, .43, .46)
MOSS = color.rgb(.33, .52, .22)
WOOD = color.rgb(.55, .37, .2)
WOOD_DARK = color.rgb(.36, .23, .12)
STONE = color.rgb(.8, .81, .84)
NAVY = color.rgb(.17, .19, .36)
NAVY2 = color.rgb(.23, .25, .46)
TREE_GREENS = [color.rgb(.13, .45, .16), color.rgb(.18, .52, .18), color.rgb(.1, .4, .2),
               color.rgb(.22, .56, .2), color.rgb(.15, .48, .12), color.rgb(.26, .6, .22)]
CLIFF = color.rgb(.5, .47, .44)
BUSH_GREENS = [color.rgb(.2, .62, .42), color.rgb(.24, .68, .44), color.rgb(.17, .56, .4),
               color.rgb(.3, .7, .44)]
GRASS_TIP = color.rgb(.62, .86, .42)           # bout des feuilles des hautes herbes, éclairé par le soleil
# feuillages par biome (ordre de biomes.KEYS)
GREENS = [TREE_GREENS,
          [color.rgb(.36, .44, .2), color.rgb(.42, .46, .24), color.rgb(.3, .4, .18)],          # roche : olivier sec
          [color.rgb(.1, .44, .12), color.rgb(.16, .52, .14), color.rgb(.08, .38, .14),
           color.rgb(.22, .58, .16), color.rgb(.3, .62, .18)],                                   # plante : vert profond
          TREE_GREENS,
          [color.rgb(.12, .5, .36), color.rgb(.18, .56, .4), color.rgb(.1, .44, .38),
           color.rgb(.24, .6, .36)],                                                             # eau : vert tendre
          [color.rgb(.24, .28, .14), color.rgb(.3, .3, .16)]]                                    # feu : roussi
BLOSSOM = [color.rgb(1, .66, .8), color.rgb(.98, .74, .86), color.rgb(.95, .58, .76), color.rgb(1, .82, .9)]
CRYSTAL = [color.rgb(.45, .8, 1), color.rgb(.6, .9, 1), color.rgb(.55, .7, 1), color.rgb(.4, .95, .95)]
VOLT = [color.rgb(1, .9, .35), color.rgb(1, .95, .55), color.rgb(.95, .82, .25)]
BASALT = color.rgb(.3, .27, .26)
BASALTS = [BASALT, color.rgb(.36, .27, .23), color.rgb(.25, .23, .23), color.rgb(.4, .33, .29)]
OBSIDIAN = color.rgb(.14, .1, .18)
SAND_TOP = color.rgb(.86, .76, .56)     # sable sur le dessus du grès
ASH_TOP = color.rgb(.42, .39, .37)      # cendre sur le dessus du basalte
# végétation du cœur des massifs, par biome : (densité, essences)
FLORA = [
    (1.0, ['broadleaf'] * 55 + ['conifer'] * 25 + ['tropical'] * 20 + ['outcrop'] * 4),
    (.42, ['conifer'] * 4 + ['dry'] * 4 + ['sandstone'] * 3 + ['hoodoo'] * 2),
    (1.0, ['broadleaf'] * 50 + ['tropical'] * 22 + ['fern'] * 16 + ['bush'] * 12 + ['outcrop'] * 3),
    (1.0, ['broadleaf'] * 45 + ['conifer'] * 42 + ['tropical'] * 10 + ['outcrop'] * 4),
    (.95, ['blossom'] * 34 + ['tropical'] * 30 + ['broadleaf'] * 18 + ['crystal'] * 12 + ['fern'] * 6),
    (.55, ['dead'] * 40 + ['basalt'] * 30 + ['obsidian'] * 16 + ['vent'] * 8),
]


def seg_dist(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / L2))
    return math.hypot(px - ax - dx * t, pz - az - dz * t)


def polyline_dist(x, z, pts):
    return min(seg_dist(x, z, *a, *b) for a, b in zip(pts, pts[1:]))


def polyline_dist_np(x, z, pts):
    d = np.full(x.shape, 1e9)
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz or 1
        t = np.clip(((x - ax) * dx + (z - az) * dz) / L2, 0, 1)
        d = np.minimum(d, np.hypot(x - ax - dx * t, z - az - dz * t))
    return d


def polyline_dist_grid(xs, pts, cap):
    """Comme polyline_dist_np sur la grille carrée xs × xs, mais seulement près du tracé :
    au-delà de `cap`, la distance vaut `cap` (beaucoup plus rapide sur une grande grille)."""
    d = np.full((len(xs), len(xs)), float(cap))
    step, x0 = xs[1] - xs[0], xs[0]
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        i0 = max(0, int((min(ax, bx) - cap - x0) / step))
        i1 = min(len(xs), int((max(ax, bx) + cap - x0) / step) + 2)
        j0 = max(0, int((min(az, bz) - cap - x0) / step))
        j1 = min(len(xs), int((max(az, bz) + cap - x0) / step) + 2)
        if i0 >= i1 or j0 >= j1:
            continue
        x, z = np.meshgrid(xs[i0:i1], xs[j0:j1], indexing='ij')
        dx, dz = bx - ax, bz - az
        L2 = dx * dx + dz * dz or 1
        t = np.clip(((x - ax) * dx + (z - az) * dz) / L2, 0, 1)
        sub = d[i0:i1, j0:j1]
        np.minimum(sub, np.hypot(x - ax - dx * t, z - az - dz * t), out=sub)
    return d


def circle_pts(cx, cz, r, n=24, a0=0, a1=360):
    return [(cx + math.sin(math.radians(a0 + (a1 - a0) * i / n)) * r,
             cz + math.cos(math.radians(a0 + (a1 - a0) * i / n)) * r) for i in range(n + 1)]


def mirror(pts):
    return [(-x, z) for x, z in pts]


def polar(a, r, x0=0.0, z0=0.0):
    a = math.radians(a)
    return x0 + math.sin(a) * r, z0 + math.cos(a) * r


SHADE_LEAF = (.06, .3, .32)          # feuillage à l'ombre : bleu-vert
SUN_LEAF = (.74, .86, .36)           # feuillage au soleil : jaune-vert


def _hue(c, t):
    """Décale une couleur de feuillage : t < 0 vers le bleu-vert de l'ombre, t > 0 vers le jaune-vert
    du soleil (les peintres ne se contentent pas d'assombrir ou d'éclaircir)."""
    target = SHADE_LEAF if t < 0 else SUN_LEAF
    k = min(abs(t), 1) * (.45 if t < 0 else .35)
    return color.rgba(*(c[i] * (1 - k) + target[i] * k for i in range(3)), 1)


def shade(c, f):
    return color.rgb(min(1, c[0] * f), min(1, c[1] * f), min(1, c[2] * f))


def _collinear(a, b, c):
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-6


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > .05:
            out.append(p)
    return out


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _terrace(h, step):
    """Relief en gradins : paliers plats séparés par de courts ressauts (strates du grès)."""
    q = h / step
    f = np.floor(q)
    return step * (f + _smoothstep(.55, 1, q - f))


def _lava_np(x, z, sdf):
    """Coulées de lave (0 à 1) : lignes sinueuses au cœur des massifs volcaniques (le poids du
    biome feu est appliqué par l'appelant). Jamais dans les passages."""
    a = np.abs(np.sin(x * .105 - z * .07 + np.sin(z * .09) * 2.2 + np.sin(x * .05)))
    b = np.abs(np.sin(z * .12 + x * .045 + np.sin(x * .08) * 1.8))
    line = np.maximum(_smoothstep(.16, .03, a), _smoothstep(.1, .02, b) * .8)
    return line * _smoothstep(1.2, 3.2, sdf)


# ==================================================================== tracé
A = {a['key']: a['pos'] for a in C.ARENAS}
RB, BB = C.TEAMS['rouge']['base'], C.TEAMS['bleu']['base']

# voies principales : (points, largeur)
LANES = [
    # grand anneau qui relie les arènes ; au sud, il passe au-dessus des bases (sans les traverser) :
    # les deux arènes du bas sont reliées directement, loin des dégâts de la base adverse
    ([A['nord'], (30, 80), (56, 64), A['est'], (86, -10), A['sud_est'], (62, -78), (36, -86), (0, -88)], 4.6),
    ([A['nord'], (-30, 80), (-56, 64), A['ouest'], (-86, -10), A['sud_ouest'], (-62, -78), (-36, -86), (0, -88)],
     4.6),
    # bretelles : chaque base rejoint l'anneau juste au-dessus d'elle
    ([RB, (-36, -86)], 4.6),
    ([BB, (36, -86)], 4.6),
    # voie centrale Ouest - Boss Pit - Est
    ([(-106, -5), (-60, -5), (-14, -5)], 5.0),
    ([(14, -5), (60, -5), (106, -5)], 5.0),
    # voie verticale Nord - Boss Pit - bas
    ([(0, 14), (0, 40), (0, 68)], 3.6),
    ([(0, -14), (0, -88)], 3.6),
]

# arènes perchées sur un plateau : clé -> (hauteur, longueur des rampes d'accès)
PLATEAUS = {'nord': (2.3, 7.5)}

# rivière peu profonde : (points, largeur)
_R_MAIN = [(-6, 62.5), (-9, 58), (8, 44), (-8, 30), (-2, 17.5)]
_R_LOW = [(0, -18.5), (-9, -31), (-15, -46), (-7, -62), (0, -76), (0, -80)]   # s'arrête avant l'anneau du sud
RIVERS = [
    (_R_MAIN, 5.0),
    (circle_pts(0, -1, 17.5, 40), 4.4),                      # douve autour du Boss Pit
    (_R_LOW, 4.6), (mirror(_R_LOW), 4.6),
    ([(-9, -30), (-22, -24), (-30, -30)], 3.6), ([(9, -30), (22, -24), (30, -30)], 3.6),
    ([(8, 44), (16, 46), (20, 52)], 3.4), ([(-8, 30), (-16, 36), (-20, 46)], 3.4),
    ([(-9, 58), (-18, 64), (-34, 66)], 3.4), ([(8, 60), (18, 64), (34, 66)], 3.4),
]


class Stadium:
    def __init__(self, root):
        self.root = root
        self.rng = random.Random(11)
        self.obstacles = []
        self.grid = {}
        self.paths = []          # chemins secondaires (points, largeur)
        self.stand_angles = {}       # angles des petites tribunes de chaque arène
        self.wb = WaterBuilder()     # eau et lave animées (un seul maillage, voir water.py)
        self.emitters = []           # sources de particules du décor : (x, y, z, genre, taille)
        self.time = 0.0
        self._plan_paths()
        self._plan_jungle()
        self.biome = biomes.BiomeMap(F + 6)
        self.terrain_marks = []          # (x, z, rayon, profil) : reliefs ajoutés par les grands décors
        from game.world.landmarks import Landmarks
        self.landmarks = Landmarks(self)
        self.landmarks.plan()
        self._plan_plateaus()
        self._build_heightmap()
        self._new_builders()
        self._build_ground()
        self._build_lanes()
        self._build_river()
        self._build_stands()
        self._build_plateaus()
        self.arcs = Arcs(self.root, random.Random(5))
        self._build_arenas()
        self._build_bases()
        self._build_pit()
        self._build_camps()
        self._build_jungle()
        self.landmarks.build()
        self._flush()
        self._build_nav()

    def _flush(self):
        """Transforme les constructeurs restants en entités (quelques gros maillages)."""
        det = C.QUALITY.get('detail', 1.0)
        for b, em in ((self.b, 0), (self.glow, .95), (self.water, .22), (self.flat, 0)):
            if b.count:
                b.static(self.root, emissive=em, transparent=b is self.water,
                         detail=det * (.7 if b is self.b else .4 if b is self.flat else 0))
        self._new_builders()
        self.water_node = self.wb.build(self.root)

    def _new_builders(self):
        # décor éclairé, parties lumineuses (posés sur le relief) et eau (surface plane)
        self.b = ChunkedBuilder(lift=self.ground_y)
        self.glow = ChunkedBuilder(lift=self.ground_y)
        self.water = ChunkedBuilder()
        self.flat = ChunkedBuilder()      # voies et ponts : à hauteur fixe, même au-dessus de la rivière

    # ================================================================ collisions
    def _cells(self, x, z, r):
        for i in range(int(math.floor((x - r) / CELL)), int(math.floor((x + r) / CELL)) + 1):
            for j in range(int(math.floor((z - r) / CELL)), int(math.floor((z + r) / CELL)) + 1):
                yield i, j

    def block(self, x, z, r):
        o = (x, z, r)
        self.obstacles.append(o)
        for c in self._cells(x, z, r):
            self.grid.setdefault(c, []).append(o)

    def nearby(self, x, z, r):
        seen = set()
        for c in self._cells(x, z, r):
            for o in self.grid.get(c, ()):
                if id(o) not in seen:
                    seen.add(id(o))
                    yield o

    def blocked(self, x, z, r):
        if self.wall_dist(x, z) > -r:
            return True
        return any(math.hypot(x - ox, z - oz) < orad + r for ox, oz, orad in self.nearby(x, z, r))

    def _jcell(self, x, z):
        fx = min(max((x - self.j_min) / J_RES, 0), self.j_n - 1.001)
        fz = min(max((z - self.j_min) / J_RES, 0), self.j_n - 1.001)
        i, j = int(fx), int(fz)
        return i, j, fx - i, fz - j

    def wall_dist(self, x, z):
        """Distance signée aux murs de la jungle : > 0 dans un massif, < 0 dans un passage."""
        i, j, tx, tz = self._jcell(x, z)
        a = self.wall_sdf
        return float(a[i, j] * (1 - tx) * (1 - tz) + a[i + 1, j] * tx * (1 - tz)
                     + a[i, j + 1] * (1 - tx) * tz + a[i + 1, j + 1] * tx * tz)

    def bush_at(self, x, z):
        """Numéro du buisson (hautes herbes) en (x, z), 0 si aucun."""
        i, j, tx, tz = self._jcell(x, z)
        return int(self.bush_grid[i + (tx > .5), j + (tz > .5)])

    def collide(self, pos, radius=.5):
        """Repousse la position hors des obstacles et dans le terrain."""
        lim = F - 1 - radius
        r = math.hypot(pos.x, pos.z)
        if r > lim:
            pos.x *= lim / r
            pos.z *= lim / r
        for _ in range(2):              # murs de la jungle : on glisse le long de leur bord
            s = self.wall_dist(pos.x, pos.z) + radius
            if s <= 0:
                break
            i, j, _, _ = self._jcell(pos.x, pos.z)
            gx, gz = self.wall_gx[i, j], self.wall_gz[i, j]
            g = math.hypot(gx, gz)
            if g < 1e-6:
                break
            pos.x -= gx / g * s
            pos.z -= gz / g * s
        for ox, oz, orad in self.nearby(pos.x, pos.z, radius):
            dx, dz = pos.x - ox, pos.z - oz
            d = math.hypot(dx, dz)
            m = orad + radius
            if 0 < d < m:
                pos.x = ox + dx / d * m
                pos.z = oz + dz / d * m
        return pos

    def free_line(self, a, b, radius=.4):
        """Vrai si le segment [a, b] ne traverse aucun obstacle."""
        d = Vec3(b.x - a.x, 0, b.z - a.z)
        steps = max(1, int(d.length() / 1.5))
        for i in range(1, steps + 1):
            p = a + d * (i / steps)
            if self.blocked(p.x, p.z, radius):
                return False
        return True

    def shot_blocked(self, x, z):
        """Vrai si une attaque passant en (x, z) heurte un massif de la jungle, une falaise ou un
        obstacle solide (arbre, rocher, pilier...)."""
        if self.wall_dist(x, z) > .15:
            return True
        for ox, oz, orad in self.nearby(x, z, 0):
            if (x - ox) ** 2 + (z - oz) ** 2 < orad * orad:
                return True
        return False

    def clear_line(self, a, b, step=.7):
        """Part (0 à 1) du segment [a, b] parcourue avant le premier obstacle (1 : voie libre)."""
        dx, dz = b.x - a.x, b.z - a.z
        n = max(1, int(math.hypot(dx, dz) / step))
        for i in range(1, n + 1):
            t = i / n
            if self.shot_blocked(a.x + dx * t, a.z + dz * t):
                return (i - 1) / n
        return 1.0

    def sees(self, a, b):
        """Vrai si rien ne s'interpose entre a et b (ligne de vue, portée des attaques)."""
        return self.clear_line(a, b) >= 1.0

    def reach(self, a, b):
        """Point le plus proche de b atteignable depuis a en ligne droite (avant un mur)."""
        t = self.clear_line(a, b)
        if t >= 1.0:
            return Vec3(b.x, 0, b.z)
        return Vec3(a.x + (b.x - a.x) * t, 0, a.z + (b.z - a.z) * t)

    # ================================================================ espaces libres
    def _open_np(self, xs):
        """Distance signée, sur la grille xs × xs, aux zones de jeu ouvertes : voies et leurs
        pelouses, rivière, chemins des camps, arènes, bases, Boss Pit et camps (< 0 à l'intérieur),
        limitée à une vingtaine d'unités. Renvoie aussi la distance au dallage des voies, au bord
        de l'eau et aux zones rondes (arènes, bases...)."""
        cap = 20
        x, z = np.meshgrid(xs, xs, indexing='ij')
        pave = np.full(x.shape, 1e9)
        for pts, w in LANES:
            pave = np.minimum(pave, polyline_dist_grid(xs, pts, cap) - w / 2 - .7)
        water = np.full(x.shape, 1e9)
        for pts, w in RIVERS:
            water = np.minimum(water, polyline_dist_grid(xs, pts, cap) - w / 2)
        o = np.minimum(pave - 1.7, water - 1.8)
        for pts, w in self.paths:
            o = np.minimum(o, polyline_dist_grid(xs, pts, cap) - w / 2 - 1.2)
        discs = np.full(x.shape, 1e9)
        for a in C.ARENAS:
            discs = np.minimum(discs, np.hypot(x - a['pos'][0], z - a['pos'][1]) - C.ARENA_RADIUS - 12)
        for t in C.TEAMS.values():
            discs = np.minimum(discs, np.hypot(x - t['base'][0], z - t['base'][1]) - C.BASE_RADIUS - 7)
        discs = np.minimum(discs, np.hypot(x, z) - C.PIT_RADIUS - 9)
        for c in C.CAMPS:
            discs = np.minimum(discs, np.hypot(x - c['pos'][0], z - c['pos'][1]) - 7.5)
        return np.minimum(o, discs), pave, water, discs

    def _plan_jungle(self):
        """Tracé de la jungle : massifs infranchissables, couloirs, clairières et buissons."""
        rng = random.Random(7)
        n = F + 6
        xs = np.arange(-n, n + J_RES / 2, J_RES)
        X, Z = np.meshgrid(xs, xs, indexing='ij')
        self.j_min, self.j_n = -n, len(xs)
        open_d, pave, water, discs = self._open_np(xs)

        def at(arr, x, z):
            i = int(round((x + n) / J_RES))
            j = int(round((z + n) / J_RES))
            return arr[min(max(i, 0), len(xs) - 1), min(max(j, 0), len(xs) - 1)]

        # graines des massifs, symétriques Ouest / Est (sur l'axe si elles en sont trop près)
        seeds = []
        for _ in range(6000):
            x, z = rng.uniform(-F, 0), rng.uniform(-F, F)
            if math.hypot(x, z) > F - 3 or at(open_d, x, z) < 2.5:
                continue
            if x > -SEED_GAP / 2:
                x = 0.0
            if all(math.hypot(x - sx, z - sz) > SEED_GAP for sx, sz in seeds):
                seeds.append((x, z))
                if x:
                    seeds.append((-x, z))
        pts = np.stack([X.ravel(), Z.ravel()], -1)
        tree = cKDTree(seeds)
        (d1, d2), (i1, i2) = (a.T for a in tree.query(pts, k=2))
        s = np.array(seeds)
        gap = np.linalg.norm(s[i1] - s[i2], axis=1)
        corridor = ((d2 ** 2 - d1 ** 2) / (2 * gap)).reshape(X.shape) - CORRIDOR   # distance à l'arête
        # certaines arêtes restent fermées : massifs plus grands, culs-de-sac (fermetures symétriques)
        mir = [seeds.index((-x, z)) for x, z in seeds]
        closed = np.zeros((len(seeds), len(seeds)), bool)
        for a in range(len(seeds)):
            for b in range(a + 1, len(seeds)):
                if sorted((mir[a], mir[b])) < [a, b]:
                    continue                    # paire miroir déjà tirée
                if np.hypot(*(s[a] - s[b])) < SEED_GAP * 1.9 and rng.random() < CLOSED_EDGES:
                    for p, q in ((a, b), (mir[a], mir[b])):
                        closed[p, q] = closed[q, p] = True
        corridor = np.where(closed[i1, i2].reshape(X.shape), 1e9, corridor)
        # clairières : quelques carrefours de couloirs élargis
        clear = np.full(X.shape, 1e9)
        self.clearings = []
        ok = (X < 0) & (corridor < -2.2) & (open_d > 6) & (np.hypot(X, Z) < F - 8)
        cand = list(zip(X[ok][::7].tolist(), Z[ok][::7].tolist()))
        rng.shuffle(cand)
        for x, z in cand:
            if len(self.clearings) >= 16:
                break
            if all(math.hypot(x - cx, z - cz) > 26 for cx, cz, _ in self.clearings):
                r = rng.uniform(4.2, 5.6)
                self.clearings += [(x, z, r), (-x, z, r)]
        for cx, cz, r in self.clearings:
            clear = np.minimum(clear, np.hypot(X - cx, Z - cz) - r)
        walk = np.minimum(np.minimum(open_d, corridor), clear) < 0
        walk |= np.hypot(X, Z) > F - 1.5          # pied des tribunes (hors du terrain)
        solid = ~walk
        # on retire les massifs trop fins et on bouche les recoins inaccessibles
        lab, k = ndimage.label(solid)
        inner = ndimage.distance_transform_edt(solid) * J_RES
        if k:
            thick = ndimage.maximum(inner, lab, np.arange(1, k + 1))
            area = ndimage.sum(np.ones_like(inner), lab, np.arange(1, k + 1)) * J_RES ** 2
            keep = np.concatenate([[False], (thick > 1.4) & (area > 14)])
            solid = keep[lab]
        lab, k = ndimage.label(~solid & (np.hypot(X, Z) < F - 2.5))
        if k > 1:
            sizes = ndimage.sum(np.ones(lab.shape), lab, np.arange(1, k + 1))
            main = 1 + int(np.argmax(sizes))
            solid |= (lab != main) & (lab > 0)
        # distance signée aux murs (> 0 dans un massif)
        sdf = (ndimage.distance_transform_edt(solid) - ndimage.distance_transform_edt(~solid)) * J_RES
        sdf = np.where(solid, sdf - J_RES / 2, sdf + J_RES / 2)
        self.wall_sdf = ndimage.gaussian_filter(sdf, .8)
        self.wall_gx, self.wall_gz = np.gradient(self.wall_sdf, J_RES)
        self.jX, self.jZ, self.j_open = X, Z, open_d
        self._plan_bushes(rng, X, Z, pave, water, discs, at)

    def _plan_bushes(self, rng, X, Z, pave, water, discs, at):
        """Hautes herbes : au bord des voies, dans les couloirs, les clairières et près de la rivière."""
        sdf = self.wall_sdf
        cands = []                     # (priorité, x, z, rayon) côté Ouest, puis mis en miroir
        for pts, w in LANES:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                L = math.hypot(bx - ax, bz - az)
                for k in range(int(L / 3)):
                    t = (k + .5) * 3 / L
                    cx, cz = ax + (bx - ax) * t, az + (bz - az) * t
                    for sd in (-1, 1):
                        off = w / 2 + 3.2
                        x = cx + (bz - az) / L * sd * off
                        z = cz - (bx - ax) / L * sd * off
                        if x < -1:
                            cands.append((0, x, z, rng.uniform(2.1, 2.7), (bx - ax) / L, (bz - az) / L))
        for pts, w in RIVERS[2:]:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                L = math.hypot(bx - ax, bz - az)
                for sd in (-1, 1):
                    x = (ax + bx) / 2 + (bz - az) / L * sd * (w / 2 + 2.6)
                    z = (az + bz) / 2 - (bx - ax) / L * sd * (w / 2 + 2.6)
                    if x < -1:
                        cands.append((1, x, z, rng.uniform(2.0, 2.5), (bx - ax) / L, (bz - az) / L))
        for cx, cz, r in self.clearings:
            if cx < 0:
                a = rng.uniform(0, math.tau)
                cands.append((0, cx + math.sin(a) * r * .55, cz + math.cos(a) * r * .55, rng.uniform(2.2, 2.7),
                              math.cos(a), -math.sin(a)))
        ii, jj = np.nonzero((X < -1) & (sdf > -2.4) & (sdf < -1.2) & (self.j_open > 3))
        for i, j in zip(ii[::9].tolist(), jj[::9].tolist()):
            gx, gz = self.wall_gx[i, j], self.wall_gz[i, j]          # le long du mur voisin
            g = math.hypot(gx, gz) or 1
            cands.append((2, X[i, j], Z[i, j], rng.uniform(2.0, 2.6), gz / g, -gx / g))
        rng.shuffle(cands)
        cands.sort(key=lambda c: c[0])
        chosen, quota = [], {0: 22, 1: 5, 2: 14}
        for prio, x, z, r, dx, dz in cands:
            if quota[prio] <= 0 or math.hypot(x, z) > F - 6:
                continue
            if at(sdf, x, z) > -1.0 or at(discs, x, z) < 2 or at(pave, x, z) < .5 or at(water, x, z) < .6:
                continue
            if any(math.hypot(x - c[0], z - c[1]) < 18 for c in chosen):
                continue
            quota[prio] -= 1
            chosen += [(x, z, r, dx, dz), (-x, z, r, -dx, dz)]
        mask = np.zeros(X.shape, bool)
        for x, z, r, dx, dz in chosen:          # touffe allongée : trois disques alignés
            m = int(r * 2.4 / J_RES) + 2
            i, j = int(round((x - self.j_min) / J_RES)), int(round((z - self.j_min) / J_RES))
            win = np.s_[max(0, i - m):i + m, max(0, j - m):j + m]
            for k in (-1.2, 0, 1.2):
                mask[win] |= np.hypot(X[win] - x - dx * k * r, Z[win] - z - dz * k * r) < r * (1 - abs(k) * .12)
        mask &= (sdf < -.3) & (pave > .2) & (water > .3) & (discs > 0)
        lab, k = ndimage.label(mask)
        if k:
            area = ndimage.sum(mask, lab, np.arange(1, k + 1)) * J_RES ** 2
            lab = np.where(np.concatenate([[False], area > 5])[lab], lab, 0)
        self.bush_grid = lab.astype(np.int32)

    def _clear_of_lanes(self, x, z, m):
        return all(polyline_dist(x, z, pts) > w / 2 + m for pts, w in LANES)

    # ================================================================ outils
    def _ribbon(self, b, pts, width, col, y, h=.04, disc=True):
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            dx, dz = bx - ax, bz - az
            L = math.hypot(dx, dz)
            b.add('box', ((ax + bx) / 2, y, (az + bz) / 2), (width, h, L),
                  rot=(0, math.degrees(math.atan2(dx, dz)), 0), col=col)
            if disc:
                b.add('cyl24', (bx, y, bz), (width, h, width), col=col)
        if disc:
            b.add('cyl24', (pts[0][0], y, pts[0][1]), (width, h, width), col=col)

    def _rock(self, b, x, z, s, moss=.4, rng=None):
        """Rocher à facettes, le dessus parfois couvert de mousse."""
        rng = rng or self.rng
        rot = (rng.uniform(-10, 10), rng.uniform(0, 360), rng.uniform(-10, 10))
        c = shade(ROCK, rng.uniform(.8, 1.12))
        b.add(rng.choice(ROCKS), (x, s * .32, z), (s * 1.7, s * 1.25, s * 1.45), rot=rot, col=c, grad=.3,
              cap=(MOSS, .85) if rng.random() < moss else None)

    def _canopy(self, b, x, y, z, r, h, g, n=7, leafy=True):
        """Couronne de feuillage : un cœur et des touffes qui s'éclairent comme un seul volume doux
        (normales depuis le centre), bleu-vert à l'ombre, jaune-vert au soleil."""
        rng = self.rng
        vol = (x, y + h * .15, z, .9)
        hue = _hue if leafy else (lambda c, t: shade(c, .86 + .16 * t))      # fleurs : pas de teinte verte
        sun = (SUN_LEAF, .22) if leafy else None
        b.add('blob', (x, y, z), (r * 1.75, h * 1.25, r * 1.75), rot=(0, rng.uniform(0, 180), 0),
              col=hue(g, -.6), wobble=.22, grad=.2, volume=vol)
        for i in range(n):
            a = i * 360 / n + rng.uniform(-22, 22)
            up = rng.uniform(-.25, .9)                     # hauteur relative de la touffe
            ox, oz = polar(a, r * (1 - max(up, 0) * .5) * rng.uniform(.72, .98))
            t = r * rng.uniform(.6, .82)
            b.add('blob_lo', (x + ox, y + up * h * .7, z + oz), (t * 1.3, t * 1.05, t * 1.3),
                  rot=(rng.uniform(-10, 10), rng.uniform(0, 180), 0), col=hue(g, up - .2 + rng.uniform(-.1, .1)),
                  wobble=.26, tip=sun, volume=vol)
        b.add('blob_lo', (x + rng.uniform(-.2, .2) * r, y + h * .75, z + rng.uniform(-.2, .2) * r),
              (r * 1.15, r * .8, r * 1.15), col=hue(g, .6), wobble=.24, tip=sun, volume=vol)

    # ================================================================ sol
    def _plan_paths(self):
        """Chemins secondaires de chaque camp jusqu'à la voie (ou rivière) la plus proche."""
        for camp in C.CAMPS:
            x0, z0 = camp['pos']
            best = None
            for pts, w in LANES + RIVERS:
                for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                    dx, dz = bx - ax, bz - az
                    L2 = dx * dx + dz * dz or 1
                    t = max(0, min(1, ((x0 - ax) * dx + (z0 - az) * dz) / L2))
                    px, pz = ax + dx * t, az + dz * t
                    d = math.hypot(px - x0, pz - z0)
                    if best is None or d < best[0]:
                        best = (d, px, pz)
            self.paths.append(([(x0, z0), (best[1], best[2])], 2.6))

    def _fields_np(self, x, z):
        """Distances (tableaux numpy) : aux zones ouvertes, au bord de la rivière, au bord des voies
        et au bord des zones de jeu planes (arènes, bases, Boss Pit, camps)."""
        lane_d = np.full(x.shape, 1e9)
        for pts, w in LANES + self.paths:
            lane_d = np.minimum(lane_d, polyline_dist_np(x, z, pts) - w / 2)
        river_d = np.full(x.shape, 1e9)
        for pts, w in RIVERS:
            river_d = np.minimum(river_d, polyline_dist_np(x, z, pts) - w / 2)
        disc_d = np.full(x.shape, 1e9)
        for a in C.ARENAS:
            disc_d = np.minimum(disc_d, np.hypot(x - a['pos'][0], z - a['pos'][1]) - C.ARENA_RADIUS - 4.5)
        for t in C.TEAMS.values():
            disc_d = np.minimum(disc_d, np.hypot(x - t['base'][0], z - t['base'][1]) - C.BASE_RADIUS - 5)
        disc_d = np.minimum(disc_d, np.hypot(x, z) - C.PIT_RADIUS - 3.5)
        for c in C.CAMPS:
            disc_d = np.minimum(disc_d, np.hypot(x - c['pos'][0], z - c['pos'][1]) - 6)
        open_d = np.minimum(np.minimum(lane_d, river_d), disc_d - 1.5)
        return open_d, river_d, lane_d, disc_d

    def _build_heightmap(self):
        """Relief : massifs de la jungle surélevés selon leur biome (collines, plateau de grès en
        terrasses au Nord, crêtes de basalte creusées de coulées de lave au Sud-Est, buttes douces
        du lagon), légères ondulations sur les pelouses, lit de rivière creusé bordé de petits
        talus. Voies, arènes, bases, Boss Pit et camps restent plats."""
        n = int(F + 6)
        xs = np.arange(-n, n + HM_RES / 2, HM_RES)
        X, Z = np.meshgrid(xs, xs, indexing='ij')
        open_d, river_d, lane_d, disc_d = self._fields_np(X, Z)
        amp = C.QUALITY['relief']
        big = ((np.sin(X * .07 + np.sin(Z * .05) * 2) * np.cos(Z * .06 + np.sin(X * .04) * 1.5) * .5 + .5) * 2.6
               + (np.sin(X * .21 + Z * .17) * np.sin(Z * .19 - X * .07) * .5 + .5) * 1.0)
        bumps = np.sin(X * .55 + np.sin(Z * .4) * 1.5) * np.sin(Z * .5 + X * .2) * .5 + .5
        flat_d = np.minimum(lane_d, disc_d)
        sdf = self._jsample_np(self.wall_sdf, X, Z)
        Wb = biomes.weights_np(X, Z)
        # les massifs de la jungle sont surélevés, les couloirs à peine vallonnés
        wall = _smoothstep(-.5, 5, sdf)
        hill = big * wall * 1.3 + 1.2 * wall
        mesa = _terrace(_smoothstep(-.3, 2.8, sdf) * (3.2 + big * .7), 1.1)
        ridge = 1 - np.abs(np.sin(X * .16 + np.sin(Z * .11) * 1.8) * np.cos(Z * .14 + np.sin(X * .09) * 1.4))
        volcanic = wall * (1.5 + ridge ** 2 * 2.6 + big * .35) - 1.4 * _lava_np(X, Z, sdf)
        lagoon = wall * (1.0 + big * .6)
        massif = (Wb[..., biomes.JUNGLE] * hill + Wb[..., biomes.ROCHE] * mesa + Wb[..., biomes.PLANTE] * hill * 1.1
                  + Wb[..., biomes.ELECTRIK] * hill + Wb[..., biomes.EAU] * lagoon + Wb[..., biomes.FEU] * volcanic)
        jungle = _smoothstep(1.5, 9, open_d)
        lawn = _smoothstep(.8, 4.5, np.minimum(flat_d, river_d + 2))
        H = amp * (massif + bumps * (.35 * lawn + .3 * jungle))
        # reliefs des grands décors : volcan, collines (ajoutés), puis bassins (aplanis)
        for x0, z0, r, fn, mode in sorted(self.terrain_marks, key=lambda m: m[4] == 'flat'):
            d = np.hypot(X - x0, Z - z0) / r
            if mode == 'add':
                H += amp * fn(d)
            else:
                target, m = fn(d)
                H = H * (1 - m) + target * m
        # rivière : lit profond au centre, berges en pente, petit talus juste derrière
        H -= 1.3 * (1 - _smoothstep(-2.4, .9, river_d))
        H += amp * .4 * np.exp(-((river_d - 2.4) / 1.2) ** 2) * _smoothstep(.5, 2.5, flat_d)
        P = self._plateau_np(X, Z)                     # arènes perchées (hauteur de jeu : pas d'échelle)
        H = np.where(P > 0, np.maximum(H, P), H)
        H *= 1 - _smoothstep(F - 7, F - 2, np.hypot(X, Z))
        self.hm, self.hm_n, self.hm_min = H, len(xs), -n
        # occlusion ambiante : les creux (pied des falaises, ravines) sont plus sombres
        self.hm_ao = np.clip((ndimage.gaussian_filter(H, 2.2) - H) * .32, -.08, .38)
        self.hm_gx, self.hm_gz = np.gradient(H, HM_RES)
        # hauteur où l'on marche : comme le sol, sauf sur les voies (planes) et les ponts
        on_lane = lane_d < .4
        self.walk_hm = np.where(on_lane, np.where(river_d < 1.0, BRIDGE_Y, np.maximum(H, 0)), H)

    def _jsample_np(self, arr, x, z):
        """Lecture interpolée d'une carte de la jungle (grille J_RES) en des points numpy."""
        fx = np.clip((x - self.j_min) / J_RES, 0, self.j_n - 1.001)
        fz = np.clip((z - self.j_min) / J_RES, 0, self.j_n - 1.001)
        i, j = fx.astype(int), fz.astype(int)
        tx, tz = fx - i, fz - j
        return (arr[i, j] * (1 - tx) * (1 - tz) + arr[i + 1, j] * tx * (1 - tz)
                + arr[i, j + 1] * (1 - tx) * tz + arr[i + 1, j + 1] * tx * tz)

    def _sample_np(self, arr, x, z):
        fx = np.clip((x - self.hm_min) / HM_RES, 0, self.hm_n - 1.001)
        fz = np.clip((z - self.hm_min) / HM_RES, 0, self.hm_n - 1.001)
        i, j = fx.astype(int), fz.astype(int)
        tx, tz = fx - i, fz - j
        return (arr[i, j] * (1 - tx) * (1 - tz) + arr[i + 1, j] * tx * (1 - tz)
                + arr[i, j + 1] * (1 - tx) * tz + arr[i + 1, j + 1] * tx * tz)

    def walk_y(self, x, z):
        """Hauteur à laquelle un Pokémon se tient en (x, z) (sol, voie ou pont)."""
        return self.ground_y(x, z, self.walk_hm)

    def ground_y(self, x, z, a=None):
        """Hauteur du sol en (x, z) (interpolée dans la carte des hauteurs)."""
        fx = (x - self.hm_min) / HM_RES
        fz = (z - self.hm_min) / HM_RES
        if not (0 <= fx < self.hm_n - 1 and 0 <= fz < self.hm_n - 1):
            return 0.0
        i, j = int(fx), int(fz)
        tx, tz = fx - i, fz - j
        a = self.hm if a is None else a
        return float(a[i, j] * (1 - tx) * (1 - tz) + a[i + 1, j] * tx * (1 - tz)
                     + a[i, j + 1] * (1 - tx) * tz + a[i + 1, j + 1] * tx * tz)

    def _build_ground(self):
        radii = np.arange(0, F + 4.01, 1.0)
        S = 520
        rr, aa = np.meshgrid(radii, np.linspace(0, 360, S + 1), indexing='ij')
        x = np.sin(np.radians(aa)) * rr
        z = np.cos(np.radians(aa)) * rr
        y = self._sample_np(self.hm, x, z)
        gx, gz = self._sample_np(self.hm_gx, x, z), self._sample_np(self.hm_gz, x, z)
        norms = np.stack([-gx, np.ones_like(gx), -gz], -1)
        norms /= np.linalg.norm(norms, axis=-1, keepdims=True)
        noise = np.clip(.5 + .35 * np.sin(x * .12 + np.sin(z * .08) * 2) * np.cos(z * .1 + np.sin(x * .06))
                        + .15 * np.sin(x * .45 + z * .38), 0, 1)[..., None]
        noise2 = np.clip(.5 + .5 * np.sin(x * .31 + np.cos(z * .23) * 2.5) * np.sin(z * .27 + x * .05), 0, 1)[..., None]
        open_d, river_d, _, _ = self._fields_np(x, z)
        W = biomes.weights_np(x, z)[..., None]                 # (…, 6, 1)
        wf, wr = W[..., biomes.FEU, :], W[..., biomes.ROCHE, :]

        def palette(pal, t):
            """Couleur par biome (deux teintes mélangées par t), pondérée par les poids des biomes."""
            a, b_ = np.array([p[0] for p in pal]), np.array([p[1] for p in pal])
            t = t[..., None, None]
            return ((a * (1 - t) + b_ * t) * W).sum(-2)

        # pelouse claire autour des zones de jeu, sous-bois plus sombre dans la jungle
        jungle = _smoothstep(1.0, 6.0, open_d)[..., None]
        lawn = palette(biomes.LAWN, noise[..., 0]) * (.95 + .1 * noise2)
        sand = _smoothstep(.62, .82, noise2) * W[..., biomes.EAU, :] * .8      # plages du lagon
        lawn = lawn * (1 - sand) + np.array(biomes.BANK[biomes.EAU]) * sand
        forest = palette(biomes.FOREST, noise2[..., 0])
        col = lawn * (1 - jungle) + forest * jungle
        # couloirs de la jungle : sentier de terre au milieu, mousse au pied des murs
        wsd = self._jsample_np(self.wall_sdf, x, z)
        trail = jungle * (1 - _smoothstep(-2.6, -.8, wsd))[..., None] * (.35 + .25 * noise)
        col = col * (1 - trail) + (np.array([.42, .34, .22]) * (1 - wf) + np.array([.23, .19, .17]) * wf) * trail
        moss = (_smoothstep(-1.2, .5, wsd) * .5)[..., None] * (1 - wf - wr)
        col = col * (1 - moss) + np.array([.17, .32, .13]) * moss
        # pentes raides : roche nue (strates colorées du grès sur le plateau Nord)
        slope = np.hypot(gx, gz)[..., None]
        rock = (np.array(biomes.ROCK) * W).sum(-2)
        mossy = (_smoothstep(.45, .8, noise2) * .45) * (1 - wf - wr)
        rock = rock * (1 - mossy) + np.array([.3, .42, .2]) * mossy
        band = np.floor(y * 1.7 + np.sin(x * .09 + z * .05) * .8).astype(int) % len(biomes.STRATA)
        strata = np.array(biomes.STRATA)[band] * (.93 + .1 * noise)
        rock = rock * (1 - wr) + strata * wr
        steep = _smoothstep(.45, 1.1, slope) * _smoothstep(-.5, .8, wsd)[..., None]
        col = col * (1 - steep) + rock * steep
        # sommets un peu plus clairs, creux et pieds de falaise plus sombres
        col *= (.88 + .07 * np.clip(y, -1.2, 3.5))[..., None]
        col *= 1 - self._sample_np(self.hm_ao, x, z)[..., None]
        bank = (1 - _smoothstep(.2, 2.0, river_d))[..., None]
        col = col * (1 - bank) + (np.array(biomes.BANK) * W).sum(-2) * bank
        depth = np.clip((WATER_Y - y) / 1.0, 0, 1)[..., None]     # lit : plus sombre en profondeur
        col = col * (1 - depth) + np.array([.08, .3, .42]) * depth
        # coulées de lave lumineuses dans les massifs volcaniques
        lava = _lava_np(x, z, wsd)[..., None] * wf
        hot = _smoothstep(.55, 1, lava)
        col = col * (1 - lava) + (np.array(biomes.LAVA) * (1 - hot) + np.array(biomes.LAVA_HOT) * hot) * lava
        glow = lava * .95
        self.landmarks.paint(x, z, y, col, glow)
        edge = _smoothstep(F - 3.5, F - 1.5, rr)[..., None]
        col = col * (1 - edge) + np.array([.34, .34, .4]) * edge
        col = np.concatenate([col, 1 + glow], -1)
        NR, NA = rr.shape
        idx = np.arange(NR * NA).reshape(NR, NA)
        a, b_, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
        tris = np.stack([a, c, b_, b_, c, d], -1).reshape(-1)
        verts = np.stack([x, y, z], -1).reshape(-1, 3)
        MeshBuilder().add_raw(verts, tris, norms.reshape(-1, 3), col.reshape(-1, 4)).static(
            self.root, detail=C.QUALITY.get('detail', 1.0))

    # ================================================================ voies
    def _lane_pieces(self, pts, cut_river=False):
        """Découpe une voie : elle s'arrête au bord des arènes, des bases et du Boss Pit
        (et au-dessus de la rivière si cut_river : un pont y est construit)."""
        def inside(x, z):
            if cut_river and any(polyline_dist(x, z, rp) < rw / 2 + .5 for rp, rw in RIVERS):
                return True
            for a in C.ARENAS:
                if math.hypot(x - a['pos'][0], z - a['pos'][1]) < self.arena_reach(a['key'], 1.8):
                    return True
            for t in C.TEAMS.values():
                if math.hypot(x - t['base'][0], z - t['base'][1]) < C.BASE_RADIUS + 1.5:
                    return True
            return math.hypot(x, z) < C.PIT_RADIUS + 2.6
        pieces, cur, prov = [], [], False
        for si, ((ax, az), (bx, bz)) in enumerate(zip(pts, pts[1:])):
            n = max(1, int(math.hypot(bx - ax, bz - az) / .5))
            for i in range(n + 1):
                if si > 0 and i == 0:
                    continue
                t = i / n
                x, z = ax + (bx - ax) * t, az + (bz - az) * t
                if inside(x, z):
                    if len(cur) >= 2:
                        pieces.append(cur)
                    cur, prov = [], False
                elif not cur:
                    cur, prov = [(x, z)], False
                elif prov:
                    cur[-1] = (x, z)
                    prov = i < n
                else:
                    cur.append((x, z))
                    prov = i < n
        if len(cur) >= 2:
            pieces.append(cur)
        return [_dedupe(p) for p in pieces if len(_dedupe(p)) >= 2]

    def _build_lanes(self):
        b, glow = self.flat, self.glow
        lanes = [(piece, w) for pts, w in LANES for piece in self._lane_pieces(pts)]
        dry = [(piece, w) for pts, w in LANES for piece in self._lane_pieces(pts, cut_river=True)]
        rng = random.Random(3)          # tirage à part : ne décale pas le décor des arènes
        for pts, w in dry:
            main = w >= 4.5
            self._ribbon(b, pts, w + 1.3, LANE_EDGE, .04, h=.08)
            self._ribbon(b, pts, w, SEAM, .07, h=.08)
            dist = 0.0
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                dx, dz = bx - ax, bz - az
                L = math.hypot(dx, dz)
                ux, uz = dx / L, dz / L
                px, pz = uz, -ux
                yaw = math.degrees(math.atan2(dx, dz))
                for s in (-1, 1):       # bordures
                    b.add('box', ((ax + bx) / 2 + px * s * (w / 2 + .32), .12, (az + bz) / 2 + pz * s * (w / 2 + .32)),
                          (.34, .2, L), rot=(0, yaw, 0), col=CURB)
                n = max(1, round(L / 2.5))
                for i in range(n):      # dalles de pierre (les joints restent visibles entre elles)
                    k = (i + .5) * L / n
                    b.add('box', (ax + ux * k, .08, az + uz * k), (w - .12, .08, L / n - .07), rot=(0, yaw, 0),
                          col=shade(LANE, rng.uniform(.94, 1.04)))
                k = (12 - dist % 12) % 12
                while k < L:            # balises lumineuses
                    for s in (-1, 1):
                        qx, qz = ax + ux * k + px * s * (w / 2 + 1.1), az + uz * k + pz * s * (w / 2 + 1.1)
                        if self._inside_open_disc(qx, qz):
                            continue
                        b.add('cyl8', (qx, .4, qz), (.26, .8, .26), col=color.rgb(.3, .32, .38))
                        glow.add('sphere_lo', (qx, .88, qz), .28, col=NEON)
                    k += 12
                if main:
                    k = (20 - (dist + 6) % 20) % 20
                    while k < L:        # flèches bleues au sol
                        cx, cz = ax + ux * k, az + uz * k
                        for s in (-1, 1):
                            glow.add('box', (cx - ux * .45 + px * s * .5, .12, cz - uz * .45 + pz * s * .5),
                                     (.3, .02, 1.5), rot=(0, yaw + 50 * s, 0), col=NEON)
                        k += 20
                dist += L
        # chemins secondaires (terre battue bordée de pierres)
        b = self.b
        for pts, w in self.paths:
            self._ribbon(b, pts, w, PATH, .03, h=.04)
            (ax, az), (bx, bz) = pts[0], pts[-1]
            L = math.hypot(bx - ax, bz - az) or 1
            for k in range(int(L / 2.2)):
                t = (k + .5) * 2.2 / L
                for s in (-1, 1):
                    qx = ax + (bx - ax) * t + (bz - az) / L * s * (w / 2 + .3)
                    qz = az + (bz - az) * t - (bx - ax) / L * s * (w / 2 + .3)
                    b.add('sphere_lo', (qx, .08, qz), (.45, .25, .4), rot=(0, self.rng.uniform(0, 180), 0),
                          col=shade(ROCK, self.rng.uniform(.85, 1.1)))
        self._build_bridges(lanes)

    def _inside_open_disc(self, x, z):
        """Vrai si le point est dans une arène, une base ou le Boss Pit (pas de balise là)."""
        for a in C.ARENAS:
            if math.hypot(x - a['pos'][0], z - a['pos'][1]) < self.arena_reach(a['key'], 4):
                return True
        for t in C.TEAMS.values():
            if math.hypot(x - t['base'][0], z - t['base'][1]) < C.BASE_RADIUS + 4:
                return True
        return math.hypot(x, z) < C.PIT_RADIUS + 4

    def _build_bridges(self, lanes):
        """Ponts de bois partout où une voie traverse la rivière."""
        b = self.flat
        for pts, w in lanes:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                dx, dz = bx - ax, bz - az
                L = math.hypot(dx, dz)
                ux, uz = dx / L, dz / L
                yaw = math.degrees(math.atan2(dx, dz))
                span = None
                k = 0.0
                while k <= L + .01:
                    x, z = ax + ux * k, az + uz * k
                    wet = any(polyline_dist(x, z, rp) < rw / 2 + .6 for rp, rw in RIVERS) and \
                        math.hypot(x, z) > C.PIT_RADIUS + 1.5
                    if wet and span is None:
                        span = k
                    if (not wet or k >= L) and span is not None:
                        k0, k1 = span - .8, k + .8
                        span = None
                        mx, mz = ax + ux * (k0 + k1) / 2, az + uz * (k0 + k1) / 2
                        bl = k1 - k0
                        b.add('box', (mx, .2, mz), (w + .9, .14, bl), rot=(0, yaw, 0), col=WOOD)
                        n = int(bl / .6)
                        for i in range(n):   # planches
                            t = k0 + (i + .5) * bl / n
                            b.add('box', (ax + ux * t, .28, az + uz * t), (w + .8, .03, .08), rot=(0, yaw, 0),
                                  col=WOOD_DARK)
                        for t in (k0 + .5, (k0 + k1) / 2, k1 - .5):   # piliers plantés dans le lit
                            for s in (-.5, .5):
                                ox, oz = uz * s * w, -ux * s * w
                                b.add('cyl8', (ax + ux * t + ox, -.55, az + uz * t + oz), (.35, 1.5, .35), col=WOOD_DARK)
                        for s in (-1, 1):   # rambardes
                            ox, oz = uz * s * (w / 2 + .45), -ux * s * (w / 2 + .45)
                            b.add('box', (mx + ox, .95, mz + oz), (.14, .12, bl), rot=(0, yaw, 0), col=WOOD_DARK)
                            for i in range(int(bl / 1.6) + 1):
                                t = k0 + i * bl / max(1, int(bl / 1.6))
                                b.add('box', (ax + ux * t + ox, .6, az + uz * t + oz), (.16, .8, .16),
                                      rot=(0, yaw, 0), col=WOOD_DARK)
                    k += .5

    # ================================================================ rivière
    def _build_river(self):
        b, rng = self.b, self.rng
        verts, tris, flow, depth = river_surface(self, RIVERS, WATER_Y)
        self.wb.add_raw(verts, tris, flow, depth, speed=.45)
        for pts, w in RIVERS:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                dx, dz = bx - ax, bz - az
                L = math.hypot(dx, dz) or 1
                px, pz = dz / L, -dx / L
                for k in range(int(L / 1.7)):
                    t = (k + rng.random()) * 1.7 / L
                    cx, cz = ax + dx * t, az + dz * t
                    for s in (-1, 1):
                        r = rng.random()
                        off = w / 2 + rng.uniform(.5, 1.6)
                        qx, qz = cx + px * s * off, cz + pz * s * off
                        if self._inside_open_disc(qx, qz) or not self._clear_of_lanes(qx, qz, .6):
                            continue
                        if r < .45:
                            self._rock(b, qx, qz, rng.uniform(.35, .9))
                        elif r < .6:
                            for _ in range(rng.randint(4, 7)):
                                hh = rng.uniform(.7, 1.4)
                                b.add('cyl6', (qx + rng.uniform(-.4, .4), hh / 2, qz + rng.uniform(-.4, .4)),
                                      (.06, hh, .06), rot=(rng.uniform(-10, 10), 0, rng.uniform(-10, 10)),
                                      col=color.rgb(.32, .55, .2))
                    if rng.random() < .22:       # nénuphars
                        o = rng.uniform(-w * .35, w * .35)
                        qx, qz = cx + px * o, cz + pz * o
                        if self._clear_of_lanes(qx, qz, .3):
                            f = self.flat
                            f.add('cyl24', (qx, WATER_Y + .03, qz), (1.1, .03, .95), rot=(0, rng.uniform(0, 360), 0),
                                  col=shade(color.rgb(.25, .55, .22), rng.uniform(.85, 1.1)))
                            f.add('box', (qx + .28, WATER_Y + .05, qz), (.5, .03, .06), rot=(0, rng.uniform(0, 360), 0),
                                  col=color.rgb(.12, .3, .2))                   # l'encoche de la feuille
                            if rng.random() < .4:
                                for k in range(5):
                                    fx_, fz_ = polar(k * 72, .12, qx, qz)
                                    f.add('sphere_lo', (fx_, WATER_Y + .12, fz_), (.18, .1, .14), rot=(0, k * 72, 30),
                                          col=color.rgb(1, .72, .86))
                                f.add('sphere_lo', (qx, WATER_Y + .14, qz), .1, col=color.rgb(1, .9, .4))

    # ================================================================ stade
    def _build_stands(self):
        """Tribunes : muret lumineux, gradins avec sièges et public, toit, mâts et écrans."""
        b, glow, rng = self.b, self.glow, self.rng
        b.add('ring_99', (0, .7, 0), ((F + 1.3) * 2, 1.4, (F + 1.3) * 2), col=NAVY)
        glow.add('ring_99', (0, 1.45, 0), ((F + 1.32) * 2, .12, (F + 1.32) * 2), col=NEON)
        section_cols = [color.rgb(.25, .4, .85), color.rgb(.45, .3, .75), color.rgb(.8, .25, .3),
                        color.rgb(.2, .55, .75), color.rgb(.9, .9, .92)]
        tiers = 7
        for i in range(tiers):
            outer = F + 4 + i * 3.2
            h = 1.6 + i * 1.5
            b.add('ring_97', (0, h / 2, 0), (outer * 2, h, outer * 2), col=NAVY if i % 2 else NAVY2)
            r_seat = outer - 1.7
            n = int(2 * math.pi * r_seat / 1.25)
            for k in range(n):
                ang = 360 * k / n
                sec = int(ang // 15)
                if (ang % 15) < 1.4:           # escaliers entre les sections
                    continue
                x, z = polar(ang, r_seat)
                col = section_cols[sec % len(section_cols)]
                b.add('box', (x, h + .12, z), (.95, .24, .8), rot=(0, ang, 0), col=col)
                bx_, bz_ = polar(ang, .38)
                b.add('box', (x + bx_, h + .5, z + bz_), (.95, .7, .12), rot=(0, ang, 0), col=col)
                if rng.random() < C.QUALITY['crowd']:          # spectateur assis
                    shirt = rng.choice([color.rgb(.9, .3, .3), color.rgb(.3, .5, .9), color.rgb(.95, .85, .3),
                                        color.rgb(.35, .8, .4), color.rgb(.95, .95, .95), color.rgb(.6, .4, .8)])
                    ox, oz = polar(ang, .1)
                    b.add('sphere_xlo', (x + ox, h + .62, z + oz), (.62, .7, .5), col=shirt)
                    b.add('sphere_xlo', (x + ox, h + 1.18, z + oz), .4,
                          col=rng.choice([color.rgb(1, .85, .7), color.rgb(.8, .6, .45), color.rgb(.55, .38, .28)]))
            glow.add('ring_97', (0, h + .02, 0), ((outer - 3.15) * 2, .06, (outer - 3.15) * 2),
                     col=color.rgb(.3, .55, .95))
        # mur extérieur et toit en porte-à-faux
        top = F + 4 + tiers * 3.2
        hw = 1.6 + tiers * 1.5 + 5
        b.add('ring_97', (0, hw / 2, 0), (top * 2, hw, top * 2), col=NAVY)
        glow.add('ring_99', (0, hw - 1.2, 0), ((top - .2) * 2, .5, (top - .2) * 2), col=NEON)
        for k in range(72):
            ang = k * 5
            x, z = polar(ang, top - 6)
            b.add('box', (x, hw + 1.2, z), (math.radians(5) * (top - 6) * 1.02, .5, 13), rot=(-12, ang, 0),
                  col=color.rgb(.85, .87, .93))
            if k % 3 == 0:
                x2, z2 = polar(ang, top - 11.5)
                glow.add('box', (x2, hw - .1, z2), (.8, .2, .8), rot=(0, ang, 0), col=color.rgb(1, .98, .85))
        # écrans géants au nord-est et au nord-ouest
        for ang in (-38, 38):
            x, z = polar(ang, top + 1)
            b.add('box', (x, hw + 8, z), (26, 12, 1.4), rot=(0, ang, 0), col=color.rgb(.1, .1, .14))
            ox, oz = polar(ang, -.75)
            glow.add('box', (x + ox, hw + 8, z + oz), (24, 10, .2), rot=(0, ang, 0), col=color.rgb(.15, .3, .6))
            for s, tc in ((-1, C.TEAMS['rouge']['color']), (1, C.TEAMS['bleu']['color'])):
                sx, sz = polar(ang + 90, 6 * s)
                glow.add('box', (x + ox * 1.1 + sx, hw + 8, z + oz * 1.1 + sz), (9, 6, .2), rot=(0, ang, 0), col=tc)
        # mâts d'éclairage
        for i in range(8):
            ang = i * 45 + 22.5
            x, z = polar(ang, top + 6)
            b.add('cyl8', (x, (hw + 22) / 2, z), (1.4, hw + 22, 1.4), col=color.rgb(.35, .36, .42))
            b.add('box', (x, hw + 22.5, z), (7, 3, 1.2), rot=(0, ang, 0), col=color.rgb(.22, .22, .28))
            ox, oz = polar(ang, -.7)
            glow.add('box', (x + ox, hw + 22.5, z + oz), (6.4, 2.4, .2), rot=(0, ang, 0), col=color.rgb(1, .98, .88))
        # entrées des joueurs (au nord) et banderoles derrière chaque base
        for ang, key in ((-10, 'rouge'), (10, 'bleu')):
            x, z = polar(ang, F + 2.5)
            tc = C.TEAMS[key]['color']
            for s in (-1, 1):
                sx, sz = polar(ang + 90, 3.2 * s)
                b.add('box', (x + sx, 2.5, z + sz), (1.2, 5, 3), rot=(0, ang, 0), col=color.rgb(.9, .9, .94))
            b.add('box', (x, 5.4, z), (8, 1.2, 3.2), rot=(0, ang, 0), col=tc)
            b.add('box', (x, 2.2, z), (5.2, 4.4, 2), rot=(0, ang, 0), col=color.rgb(.08, .08, .12))
        for team in C.TEAMS.values():
            bx, bz = team['base']
            ang = math.degrees(math.atan2(bx, bz))
            x, z = polar(ang, F + 2.4)
            b.add('box', (x, 5, z), (20, 6, .6), rot=(0, ang, 0), col=team['color'])
            ox, oz = polar(ang, -.35)
            glow.add('box', (x + ox, 7.6, z + oz), (20, .3, .1), rot=(0, ang, 0), col=color.white)

    # ================================================================ plateaux
    def _plan_plateaus(self):
        """Arènes perchées : plateau rond (rayon rp) bordé de falaises, une rampe par voie d'accès."""
        self.plateaus = {}
        for a in C.ARENAS:
            if a['key'] in PLATEAUS:
                h, L = PLATEAUS[a['key']]
                x0, z0 = a['pos']
                gates = self._gate_angles(x0, z0, C.ARENA_RADIUS + 4.5, margin=.1)
                self.plateaus[a['key']] = {'pos': (x0, z0), 'h': h, 'L': L, 'rp': C.ARENA_RADIUS + 3.2,
                                           'gates': [(ang, w / 2 + 1.8) for ang, w in gates]}

    def arena_floor(self, key):
        """Hauteur du sol d'une arène (0, ou la hauteur de son plateau)."""
        p = self.plateaus.get(key)
        return p['h'] if p else 0.0

    def arena_reach(self, key, margin):
        """Rayon autour d'une arène où les voies s'arrêtent (au pied des rampes si elle est perchée)."""
        p = self.plateaus.get(key)
        return p['rp'] + p['L'] + .3 if p else C.ARENA_RADIUS + margin

    def _plateau_np(self, X, Z):
        """Hauteur des plateaux et de leurs rampes aux points numpy (0 ailleurs)."""
        H = np.zeros(X.shape)
        for p in self.plateaus.values():
            dx, dz = X - p['pos'][0], Z - p['pos'][1]
            top = _smoothstep(p['rp'] + 1.3, p['rp'] + .1, np.hypot(dx, dz))
            for ang, half in p['gates']:
                ux, uz = math.sin(math.radians(ang)), math.cos(math.radians(ang))
                along, side = dx * ux + dz * uz, np.abs(dz * ux - dx * uz)
                ramp = np.clip(1 - (along - p['rp']) / p['L'], 0, 1) * (along > 0)
                top = np.maximum(top, ramp * _smoothstep(half + 2.4, half - .1, side))   # flancs en pente douce
            H = np.maximum(H, p['h'] * top)
        return H

    def _in_gate(self, p, ang, extra=0.0):
        return any(abs((ang - g + 180) % 360 - 180) < math.degrees(math.atan2(half + extra, p['rp'])) + 1
                   for g, half in p['gates'])

    def _build_plateaus(self):
        """Falaises en colonnes de grès (infranchissables), escalier face au centre de la carte,
        rampes dallées pour les autres voies, et la source de la rivière qui tombe du plateau."""
        b, rng = self.b, random.Random(29)
        for key, p in self.plateaus.items():
            (x0, z0), h, rp = p['pos'], p['h'], p['rp']
            for k in range(120):                          # on ne grimpe pas aux falaises
                ang = k * 3
                if not self._in_gate(p, ang, .5):
                    self.block(*polar(ang, rp + .8, x0, z0), 1.0)
            src = RIVERS[0][0][0]
            fall = math.degrees(math.atan2(src[0] - x0, src[1] - z0))
            for row, (rr, lo, hi) in enumerate(((rp + .45, h + .15, h + .75), (rp + 1.4, h * .45, h + .2))):
                n = int(2 * math.pi * rr / 1.2)
                for k in range(n):
                    ang = k * 360 / n + rng.uniform(-1.5, 1.5)
                    if self._in_gate(p, ang, .3 + row) or abs((ang - fall + 180) % 360 - 180) < 3.5:
                        continue
                    x, z = polar(ang, rr + rng.uniform(-.25, .25), x0, z0)
                    hc = rng.uniform(lo, hi)
                    b.add(rng.choice(('prism6', 'prism5')), (x, hc / 2 - self.ground_y(x, z) - .15, z),
                          (rng.uniform(1.35, 1.85), hc + .3, rng.uniform(1.2, 1.6)),
                          rot=(rng.uniform(-3, 3), rng.uniform(0, 60), rng.uniform(-3, 3)),
                          col=shade(rng.choice(biomes.STRATA), rng.uniform(.8, 1.0)), grad=.5, cap=(SAND_TOP, .75))
            for k in range(26):                           # blocs tombés au pied des falaises
                ang = rng.uniform(0, 360)
                if self._in_gate(p, ang, 2.5):
                    continue
                x, z = polar(ang, rp + rng.uniform(2.3, 3.6), x0, z0)
                t = rng.uniform(.4, .9)
                b.add(rng.choice(ROCKS), (x, t * .3, z), (t * 1.7, t * 1.1, t * 1.4), rot=(0, rng.uniform(0, 360), 0),
                      col=shade(rng.choice(biomes.STRATA), rng.uniform(.8, 1.0)), grad=.3, cap=(SAND_TOP, .5))
            centre = math.degrees(math.atan2(-x0, -z0))  # l'escalier regarde le centre de la carte
            stairs = min(p['gates'], key=lambda g: abs((g[0] - centre + 180) % 360 - 180))[0]
            for ang, half in p['gates']:
                self._ramp(p, ang, half, rng, ang == stairs)
            self._plateau_spring(p, fall, rng)

    def _ramp(self, p, ang, half, rng, stairs):
        """Accès au plateau : escalier de pierre ou rampe dallée, murets de colonnes de chaque côté."""
        (x0, z0), h, rp, L = p['pos'], p['h'], p['rp'], p['L']
        ux, uz = math.sin(math.radians(ang)), math.cos(math.radians(ang))
        px, pz = uz, -ux
        f = self.flat
        stone = color.rgb(.78, .68, .52)
        if stairs:
            n = 9
            for i in range(n):
                t = (i + .5) / n
                top = h * (1 - t) + .06
                cx, cz = x0 + ux * (rp - .6 + (L + .6) * t), z0 + uz * (rp - .6 + (L + .6) * t)
                f.add('box', (cx, top - .4, cz), (half * 2 - .2, .8, (L + .6) / n + .04), rot=(0, ang, 0),
                      col=shade(stone, rng.uniform(.88, 1.04)))
                f.add('box', (cx - ux * (L + .6) / n * .5, top + .005, cz - uz * (L + .6) / n * .5),
                      (half * 2 - .2, .02, .12), rot=(0, ang, 0), col=shade(stone, .72))       # arête de la marche
        else:
            n = 4
            pitch = math.degrees(math.atan2(h, L + .6))
            for i in range(n):
                t = (i + .5) / n
                cx, cz = x0 + ux * (rp - .6 + (L + .6) * t), z0 + uz * (rp - .6 + (L + .6) * t)
                f.add('box', (cx, h * (1 - t) + .02, cz), (half * 2 - .3, .3, math.hypot(L + .6, h) / n - .06),
                      rot=(pitch, ang, 0), col=shade(LANE, rng.uniform(.93, 1.04)))
        for side in (-1, 1):                              # flancs : pente de terre et quelques blocs posés
            for k in range(3):
                t = (k + .5) / 3
                x = x0 + ux * (rp + L * t * .8) + px * side * (half + 1.4)
                z = z0 + uz * (rp + L * t * .8) + pz * side * (half + 1.4)
                r = rng.uniform(.35, .55)
                self.b.add(rng.choice(ROCKS), (x, r * .3, z), (r * 1.6, r * 1.1, r * 1.4), rot=(0, rng.uniform(0, 360), 0),
                           col=shade(rng.choice(biomes.STRATA), rng.uniform(.8, 1.0)), grad=.3, cap=(SAND_TOP, .5))

    def _plateau_spring(self, p, fall, rng):
        """La source de la rivière : un filet d'eau qui tombe du plateau dans son lit."""
        (x0, z0), h, rp = p['pos'], p['h'], p['rp']
        sx, sz = RIVERS[0][0][0]
        lip = polar(fall, rp - .3, x0, z0)
        pts = [(lip[0] + (sx - lip[0]) * t, h + .06 - (h + .06 - WATER_Y) * t ** 1.5, lip[1] + (sz - lip[1]) * t)
               for t in (i / 6 for i in range(7))]
        self.wb.curtain(pts, 1.5)
        self.wb.disc(lip[0], h + .07, lip[1], 1.1, depth=.4, speed=.6)          # vasque au bord du plateau
        self.emitters.append((sx, WATER_Y, sz, 'fall', 1.0))

    # ================================================================ arènes
    def _build_arenas(self):
        """Chaque arène a son décor thématique (voir arenas.py) et deux petites tribunes."""
        from game.world.arenas import ArenaDecor
        for a in C.ARENAS:
            x0, z0 = a['pos']
            if a['key'] not in self.plateaus:     # sur un plateau : bannières à la place des tribunes
                self._arena_stands(a, C.TYPES[a['type']], x0, z0, C.ARENA_RADIUS)
            ArenaDecor(self, a).build()

    def _arena_stands(self, a, t, x0, z0, R):
        """Petites tribunes courbes autour de l'arène, là où aucune voie ne passe."""
        b, rng = self.b, self.rng
        cands = []
        for i in range(16):
            ang = i * 22.5
            x, z = polar(ang, R + 7, x0, z0)
            if math.hypot(x, z) > F - 8:
                continue
            back = math.degrees(math.atan2(x0, z0))
            if a['type'] == 'electrik' and abs((ang - back + 180) % 360 - 180) < 62:
                continue                  # place des tours Tesla, au fond de l'arène
            d = min(polyline_dist(x, z, pts) - w / 2 for pts, w in LANES)
            cands.append((d, ang))
        cands.sort(reverse=True)
        chosen = []
        for d, ang in cands:
            if d > 6 and all(abs((ang - c + 180) % 360 - 180) > 80 for c in chosen):
                chosen.append(ang)
            if len(chosen) == 2:
                break
        self.stand_angles[a['key']] = chosen
        for ang0 in chosen:
            for row in range(3):
                r = R + 5.6 + row * 1.3
                h = .35 + row * .45
                for k in range(-5, 6):
                    ang = ang0 + k * 4.5
                    x, z = polar(ang, r, x0, z0)
                    b.add('box', (x, h / 2, z), (2 * math.pi * r * 4.5 / 360 * 1.02, h, 1.3), rot=(0, ang, 0),
                          col=color.rgb(.85, .86, .9) if row % 2 else lerp(t['dark'], color.white, .55))
                    b.add('box', (x, h + .12, z), (1.1, .22, .7), rot=(0, ang, 0),
                          col=t['color'] if (k + row) % 2 else lerp(t['color'], color.white, .4))
                    if rng.random() < .5:
                        b.add('sphere_lo', (x, h + .55, z), (.55, .6, .45),
                              col=rng.choice([color.rgb(.9, .3, .3), color.rgb(.3, .5, .9), color.rgb(.95, .85, .3),
                                              color.rgb(.95, .95, .95)]))
                        b.add('sphere_lo', (x, h + 1.02, z), .36, col=color.rgb(1, .85, .7))
            for k in range(-5, 6, 2):
                x, z = polar(ang0 + k * 4.5, R + 6.9, x0, z0)
                self.block(x, z, 1.9)

    # ================================================================ bases
    def _build_bases(self):
        R = C.BASE_RADIUS
        for key, team in C.TEAMS.items():
            b, glow = self.b, self.glow
            bx, bz = team['base']
            tc, tl = team['color'], team['light']
            for i, (rad, h, col) in enumerate(((R + 4, .06, STONE), (R + 2.2, .1, color.rgb(.92, .92, .95)),
                                              (R, .14, lerp(tc, color.white, .55)))):
                b.add('cyl_hi', (bx, h / 2 + .01, bz), (rad * 2, h, rad * 2), col=col)
            glow.add('ring_97', (bx, .16, bz), (R * 2, .06, R * 2), col=tc)
            glow.add('ring_97', (bx, .12, bz), ((R + 2.2) * 2, .04, (R + 2.2) * 2), col=tl)
            # Poké Ball peinte au sol : zone de réapparition
            b.add('cyl_hi', (bx, .15, bz), (6, .03, 6), col=color.rgb(.1, .1, .12))
            b.add('cyl_hi', (bx, .16, bz), (5.6, .03, 5.6), col=color.rgb(.97, .97, .97))
            half = [(bx, bz)] + [polar(a_, 2.8, bx, bz) for a_ in range(-90, 91, 6)]   # moitié nord rouge
            verts = np.array([(x, .168, z) for x, z in half])
            tris = np.array([(0, i + 1, i) for i in range(1, len(half) - 1)]).ravel()
            b.add_raw(verts, tris, np.tile((0, 1, 0), (len(half), 1)), np.tile(tuple(tc), (len(half), 1)))
            b.add('box', (bx, .17, bz), (5.6, .03, .35), col=color.rgb(.1, .1, .12))
            b.add('cyl_hi', (bx, .175, bz), (1.5, .03, 1.5), col=color.rgb(.1, .1, .12))
            glow.add('cyl_hi', (bx, .18, bz), (1, .03, 1), col=color.white)
            # cristaux de soin
            for i in range(4):
                x, z = polar(i * 90 + 45, R - 1.2, bx, bz)
                b.add('cyl8', (x, .4, z), (.9, .8, .9), col=color.rgb(.85, .86, .9))
                glow.add('cone4', (x, 1.4, z), (.6, 1.2, .6), col=tl)
                glow.add('cone4', (x, .95, z), (.6, .6, .6), rot=(180, 0, 0), col=tl)
            # bâtiment de l'équipe, adossé aux tribunes
            ang = math.degrees(math.atan2(bx, bz))
            gx, gz = polar(ang, R + 5.5, bx, bz)
            b.add('box', (gx, 3, gz), (18, 6, 5), rot=(0, ang, 0), col=lerp(tc, color.black, .25))
            b.add('dome', (gx, 5.8, gz), (19, 5, 6.5), rot=(0, ang, 0), col=tc)
            for i in range(-3, 4):
                sx, sz = polar(ang + 90, i * 2.5)
                fx, fz = polar(ang, -2.8)
                b.add('cyl8', (gx + sx + fx, 2.8, gz + sz + fz), (.6, 5.6, .6), col=color.rgb(.95, .95, .97))
            fx, fz = polar(ang, -2.6)
            glow.add('box', (gx + fx, 4.8, gz + fz), (15, .35, .2), rot=(0, ang, 0), col=tl)
            px, pz = polar(ang, -2.9)
            b.add('sphere', (gx + px, 7.4, gz + pz), 3.2, col=color.rgb(.97, .97, .97))
            b.add('dome', (gx + px, 7.4, gz + pz), 3.25, col=tc)
            b.add('cyl24', (gx + px, 7.4, gz + pz), (3.28, .3, 3.28), col=color.rgb(.1, .1, .12))
            qx, qz = polar(ang, -1.6)
            glow.add('cyl24', (gx + px + qx, 7.4, gz + pz + qz), (.9, .25, .9), rot=(90, ang, 0), col=color.white)
            for s in (-1, 1):
                sx, sz = polar(ang + 90, 11 * s)
                tx, tz = gx + sx, gz + sz
                b.add('cyl24', (tx, 4, tz), (3.4, 8, 3.4), col=color.rgb(.9, .9, .93))
                b.add('cone', (tx, 9.5, tz), (4, 3, 4), col=tc)
                glow.add('cyl24', (tx, 6.5, tz), (3.45, .3, 3.45), col=tl)
                self.block(tx, tz, 2)
                # drapeau
                fx2, fz2 = polar(ang, -5)
                b.add('cyl8', (tx + fx2 * .3, 6, tz + fz2 * .3), (.15, 12, .15), col=color.rgb(.8, .8, .82))
            for i in range(-3, 4):
                sx, sz = polar(ang + 90, i * 2.6)
                self.block(gx + sx, gz + sz, 2.6)

    # ================================================================ Boss Pit
    def _build_pit(self):
        R = C.PIT_RADIUS
        b, glow = self.b, self.glow
        purple = color.rgb(.72, .38, 1)
        b.add('cyl_hi', (0, .04, 0), ((R + 3) * 2, .08, (R + 3) * 2), col=color.rgb(.38, .36, .45))
        b.add('cyl_hi', (0, .07, 0), (R * 2, .08, R * 2), col=color.rgb(.2, .18, .27))
        for rr_, col in ((R * .8, color.rgb(.26, .23, .34)), (R * .55, color.rgb(.17, .15, .23)),
                         (R * .3, color.rgb(.3, .27, .4))):
            b.add('cyl_hi', (0, .09, 0), (rr_ * 2, .04, rr_ * 2), col=col)
        glow.add('ring_97', (0, .12, 0), (R * 2, .05, R * 2), col=purple)
        glow.add('ring_97', (0, .13, 0), (R * 1.1, .05, R * 1.1), col=purple)
        for i in range(24):               # runes
            ang = i * 15
            x, z = polar(ang, R * .8)
            glow.add('box', (x, .12, z), (.5, .02, 1.1 if i % 2 else .6), rot=(0, ang, 0), col=purple)
        emb = MeshBuilder()
        add_emblem(emb, 'psy', (0, 0, 0), 2.2)
        emb.entity(parent=self.root, emissive=.8, position=(0, .14, 0), rotation_x=90, scale=(1, 1, .03))
        self._pit_colosseum(R, purple)
        # portail psychique qui tourne au-dessus de l'arène (au-dessus des boss)
        v = MeshBuilder()
        for k, (r, tilt) in enumerate(((4.2, 0), (3.3, 18), (2.4, -24), (1.5, 30))):
            v.add('ring_thin', (0, k * .25, 0), (r * 2, .22, r * 2), rot=(tilt, k * 40, 0),
                  col=glowing(lerp(purple, color.white, k * .12), .85))
        v.add('sphere', (0, .4, 0), 1.1, col=glowing(color.rgb(.35, .12, .55), .6))
        self.vortex = v.static(self.root)
        self.vortex.set_pos(0, 10.5, 0)
        self.vortex.hide()                # il tourne : on le montre après le calcul (figé) des ombres

    def _gate_angles(self, x0, z0, r, margin=1.0):
        """Angles (vus de (x0, z0)) où une voie coupe le cercle de rayon r : [(angle, largeur)]."""
        hits = []
        for k in range(180):
            ang = k * 2
            x, z = polar(ang, r, x0, z0)
            w = next((w for pts, w in LANES if polyline_dist(x, z, pts) < w / 2 + margin), None)
            hits.append((ang, w))
        gates, group = [], []
        start = next((i for i, (_, w) in enumerate(hits) if w is None), 0)
        for i in range(181):
            ang, w = hits[(start + i) % 180]
            if w is not None:
                group.append((ang, w))
            elif group:
                a0 = group[0][0]
                gates.append(((a0 + ((group[-1][0] - a0) % 360) / 2) % 360, max(g[1] for g in group)))
                group = []
        return gates

    def _pit_colosseum(self, R, purple):
        """Colisée en ruine autour du Boss Pit : colonnade à arcades au nord (intacte), colonnes
        brisées au sud (basses, pour ne pas cacher le combat à la caméra), portes monumentales
        là où arrivent les voies. Les colonnes sont espacées : on passe entre elles."""
        b, rng = self.b, self.rng
        stone, dark = color.rgb(.5, .48, .55), color.rgb(.36, .34, .42)
        # couronne dallée autour de l'arène
        for rr_, n in ((R + .75, 44), (R + 1.95, 50), (R + 3.1, 56)):
            for k in range(n):
                ang = k * 360 / n + rng.uniform(-1, 1)
                x, z = polar(ang, rr_)
                b.add('box', (x, .09, z), (2 * math.pi * rr_ / n * .92, .06, 1.1), rot=(0, ang, 0),
                      col=shade(stone, rng.uniform(.78, .98)))
        rc = R + 2.4
        gates = self._gate_angles(0, 0, rc)
        tall = lambda ang: abs((ang + 180) % 360 - 180) < 100        # moitié nord : intacte
        n = 20
        cols = []
        for k in range(n):
            ang = k * 360 / n + 9
            if any(abs((ang - g + 180) % 360 - 180) < 14 for g, _ in gates):
                cols.append(None)
                continue
            x, z = polar(ang, rc)
            b.add('box', (x, .35, z), (1.5, .7, 1.5), rot=(0, ang, 0), col=dark)
            if tall(ang):
                b.add('cyl16', (x, 3.1, z), (1.0, 4.8, 1.0), col=shade(stone, rng.uniform(.95, 1.08)), grad=.25)
                b.add('box', (x, 5.7, z), (1.5, .45, 1.5), rot=(0, ang, 0), col=dark)
                cols.append((x, z, ang))
            else:                         # colonne brisée, tambours tombés au pied
                h = rng.uniform(1.0, 2.6)
                b.add('cyl16', (x, .7 + h / 2, z), (1.0, h, 1.0), col=shade(stone, rng.uniform(.9, 1.05)), grad=.25)
                b.add('cone6', (x, .7 + h + .2, z), (1.0, .5, 1.0), rot=(rng.uniform(-20, 20), rng.uniform(0, 60), 0),
                      col=shade(stone, .95))
                if rng.random() < .6:
                    fx, fz = polar(ang + rng.choice((-1, 1)) * 6, rc + rng.uniform(.8, 1.6))
                    b.add('cyl16', (fx, .45, fz), (.95, 1.1, .95), rot=(90, ang + rng.uniform(-40, 40), 0),
                          col=shade(stone, .9))
                cols.append(None)
            self.block(x, z, .65)
        for a, c in zip(cols, cols[1:] + cols[:1]):   # arcades entre deux colonnes intactes voisines
            if a is None or c is None:
                continue
            mx, mz = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
            yaw = math.degrees(math.atan2(c[0] - a[0], c[1] - a[1]))
            L = math.hypot(c[0] - a[0], c[1] - a[1])
            b.add('box', (mx, 6.2, mz), (.9, .6, L + 1.2), rot=(0, yaw, 0), col=shade(stone, .92))
            b.add('box', (mx, 5.75, mz), (.3, .12, L - 1.2), rot=(0, yaw, 0), col=glowing(purple, .8))
            if rng.random() < .4:         # lierre qui pend de l'arcade
                b.add('blob', (mx, 5.9, mz), (1.2, .8, 1.8), rot=(0, yaw, 0), col=color.rgb(.24, .42, .2), wobble=.25)
        for ang, w in gates:              # portes monumentales aux entrées
            half = w / 2 + 1.6
            x, z = polar(ang, rc + .3)
            high = tall(ang)
            for s in (-1, 1):
                sx, sz = polar(ang + 90, half * s)
                h = 6.4 if high else 3.2
                b.add('box', (x + sx, h / 2, z + sz), (1.3, h, 1.6), rot=(0, ang, 0), col=dark)
                b.add('cone4', (x + sx, h + .5, z + sz), (1.0, 1.0, 1.0), rot=(0, ang + 45, 0), col=shade(dark, .8))
                self.glow.add('cone4', (x + sx, h + 1.4, z + sz), (.55, .8, .55), col=purple)
                self.block(x + sx, z + sz, .8)
            if high:
                b.add('box', (x, 6.6, z), (half * 2 + 1.6, .9, 1.8), rot=(0, ang, 0), col=shade(dark, .9))
                ox, oz = polar(ang, -.95)
                self.glow.add('box', (x + ox, 6.6, z + oz), (half * 2 - .6, .25, .1), rot=(0, ang, 0), col=purple)

    # ================================================================ camps
    def _build_camps(self):
        b, glow, rng = self.b, self.glow, self.rng
        for camp in C.CAMPS:
            x0, z0 = camp['pos']
            buff = camp.get('buff')
            # sol et bordure du camp au thème de son gardien
            ground = {'braise': ((.28, .24, .22), (.34, .28, .25)), 'flux': ((.62, .62, .5), (.7, .68, .56)),
                      'bastion': ((.3, .42, .2), (.36, .46, .24))}.get(buff, ((.5, .5, .3), (.56, .5, .34)))
            b.add('cyl24', (x0, .02, z0), (11, .04, 10), col=color.rgb(*ground[0]))
            b.add('cyl24', (x0, .03, z0), (8, .04, 7.4), col=color.rgb(*ground[1]))
            col = C.BUFFS[buff]['color'] if buff else color.rgb(.85, .85, .85)
            for i in range(7):
                ang = i * 360 / 7 + 10
                x, z = polar(ang, 5.4, x0, z0)
                if buff == 'braise':        # orgues de basalte et braises
                    for _ in range(2):
                        h = rng.uniform(.6, 1.5)
                        b.add('prism6', (x + rng.uniform(-.4, .4), h / 2, z + rng.uniform(-.4, .4)), (.7, h, .7),
                              rot=(0, rng.uniform(0, 60), 0), col=shade(rng.choice(BASALTS), .95), grad=.3)
                    if i % 2:
                        b.add('blob', (x, .06, z), (.9, .08, .7), col=glowing(biomes.LAVA, .9), wobble=.3)
                elif buff == 'flux':        # rochers mouillés, flaques et cristaux
                    self._rock(b, x, z, rng.uniform(.45, .7), moss=0)
                    if i % 2:
                        self.wb.disc(x + .8, self.ground_y(x + .8, z) + .09, z, .6, depth=.35, sx=1.4, seg=20)
                    elif i % 3 == 0:
                        self._crystals(b, x, z, .6)
                else:
                    self._rock(b, x, z, rng.uniform(.45, .7), moss=.9 if buff == 'bastion' else .5)
                    if buff == 'bastion' and i % 2:
                        self._tree(b, x + .3, z + .3, rng.uniform(.55, .7), 'fern', biomes.PLANTE)
            glow.add('ring_97', (x0, .07, z0), (3.2, .04, 3.2), col=col)
            # icône flottante au-dessus du camp, comme sur la carte : le type du Pokémon qui y vit
            glow.add('ring_thin', (x0, 6.5, z0), (2.4, .25, 2.4), col=col)
            b.add('cyl8', (x0, 6.5, z0), (2.2, .12, 2.2), col=color.rgb(.12, .12, .16))
            kind = C.SPECIES[camp['species']]['type']
            if camp.get('buff') and kind in ('feu', 'eau', 'plante'):
                add_emblem(glow, kind, (x0, 7.0, z0), .55)
            else:
                glow.add('sphere_lo', (x0, 6.9, z0), .7, col=col)

    # ================================================================ jungle
    def _trunk(self, b, x, z, s, h, bark, branches=2):
        """Tronc organique : racines qui s'étalent au sol, fût légèrement coudé qui s'affine, branches
        qui plongent dans le feuillage. Renvoie le sommet (x, z) où poser la couronne."""
        rng = self.rng
        a0 = rng.uniform(0, 360)
        for i in range(3):                               # racines à peine sorties du sol
            a = a0 + i * 120 + rng.uniform(-25, 25)
            ox, oz = polar(a, .3 * s)
            b.add('blob_lo', (x + ox, .02 * s, z + oz), (.26 * s, .22 * s, .7 * s), rot=(18, a, 0),
                  col=shade(bark, .85), grad=.4)
        b.add('cone8', (x, .3 * s, z), (.9 * s, .6 * s, .9 * s), col=shade(bark, .9), grad=.35)   # pied évasé
        dx, dz = polar(rng.uniform(0, 360), rng.uniform(.15, .35) * s)                          # coude
        lo = h * .55
        b.add('trunk', (x + dx * .25, lo / 2, z + dz * .25), (.62 * s, lo, .62 * s),
              rot=(math.degrees(math.atan2(dz * .5, lo)), 0, -math.degrees(math.atan2(dx * .5, lo))),
              col=bark, grad=.45)
        mx, mz = x + dx * .5, z + dz * .5
        hi = h - lo + .3 * s
        b.add('trunk', (mx + dx * .25, lo + hi / 2 - .15 * s, mz + dz * .25), (.38 * s, hi, .38 * s),
              rot=(math.degrees(math.atan2(dz * .5, hi)), 0, -math.degrees(math.atan2(dx * .5, hi))),
              col=shade(bark, 1.08), grad=.3, tip=(color.rgb(.62, .48, .32), .25))
        for i in range(branches):                        # branches qui s'ouvrent vers la couronne
            a = a0 + 45 + i * 360 / branches + rng.uniform(-30, 30)
            ox, oz = polar(a, .5 * s)
            b.add('trunk', (mx + ox * .6, h * .95, mz + oz * .6), (.2 * s, 1.1 * s, .2 * s),
                  rot=(0, a, 38 + rng.uniform(-8, 8)), col=shade(bark, 1.05))
        return x + dx, z + dz

    def _tree(self, b, x, z, s, kind, bio=biomes.JUNGLE):
        rng = self.rng
        bark = color.rgb(.46, .31, .19)
        greens = GREENS[bio]
        if kind == 'blossom':           # arbre en fleurs (lagon)
            tx, tz = self._trunk(b, x, z, s * .9, 2.8 * s, color.rgb(.44, .3, .25))
            self._canopy(b, tx, 3.4 * s, tz, 1.4 * s, 1.2 * s, rng.choice(BLOSSOM), n=6, leafy=False)
            return 1.0 * s
        if kind == 'dead':              # arbre calciné (champ volcanique)
            trunk = color.rgb(.16, .13, .12)
            h = 3.2 * s
            b.add('cone8', (x, h / 2, z), (.6 * s, h, .6 * s), rot=(rng.uniform(-6, 6), 0, rng.uniform(-6, 6)), col=trunk)
            for i in range(3):
                a = i * 120 + rng.uniform(-30, 30)
                ox, oz = polar(a, .5 * s)
                b.add('cone6', (x + ox, (1.6 + i * .45) * s, z + oz), (.22 * s, 1.8 * s, .22 * s),
                      rot=(0, a, rng.uniform(40, 60)), col=trunk)
            if rng.random() < .4:       # braises au pied
                b.add('blob', (x + .5 * s, .1, z), (.7 * s, .25, .6 * s), col=glowing(biomes.LAVA, .7), wobble=.2)
            return .5 * s
        if kind == 'dry':               # touffe d'herbe sèche et arbuste épineux
            g = rng.choice(GREENS[biomes.ROCHE])
            b.add('blob', (x, .45 * s, z), (1.9 * s, 1.1 * s, 1.9 * s), col=g, wobble=.3, grad=.45)
            for _ in range(4):
                h = rng.uniform(.8, 1.4) * s
                b.add('cone6', (x + rng.uniform(-.6, .6) * s, h / 2, z + rng.uniform(-.6, .6) * s), (.2 * s, h, .2 * s),
                      rot=(rng.uniform(-20, 20), 0, rng.uniform(-20, 20)), col=color.rgb(.72, .64, .38))
            return .8 * s
        if kind == 'fern':              # fougère géante
            g = rng.choice(greens)
            for i in range(7):
                a = i * 360 / 7 + rng.uniform(-12, 12)
                ox, oz = polar(a, .9 * s)
                b.add('blob', (x + ox, .75 * s, z + oz), (.7 * s, .16 * s, 2.3 * s), rot=(-28, a, 0),
                      col=shade(g, rng.uniform(.9, 1.15)), wobble=.1, grad=.3)
            b.add('blob', (x, .4 * s, z), .9 * s, col=shade(g, .75), wobble=.2)
            return .9 * s
        if kind == 'crystal':
            self._crystals(b, x, z, s * .9)
            return .8 * s
        if kind == 'hoodoo':            # cheminée de fée : colonne de grès coiffée d'un bloc
            c = shade(rng.choice(biomes.STRATA), 1)
            h = rng.uniform(2.6, 4.2) * s
            b.add('prism5', (x, h / 2, z), (1.7 * s, h, 1.7 * s), rot=(0, rng.uniform(0, 90), 0), col=c, grad=.35)
            b.add(rng.choice(ROCKS), (x, h + .1, z), (2.0 * s, .9 * s, 1.8 * s), rot=(0, rng.uniform(0, 180), 0),
                  col=shade(rng.choice(biomes.STRATA), .9), cap=(SAND_TOP, .6))
            return .9 * s
        if kind == 'sandstone':         # rochers de grès
            for _ in range(rng.randint(2, 3)):
                t = rng.uniform(.8, 1.5) * s
                b.add(rng.choice(ROCKS), (x + rng.uniform(-1, 1), t * .35, z + rng.uniform(-1, 1)), (t * 1.8, t * 1.2, t * 1.5),
                      rot=(rng.uniform(-8, 8), rng.uniform(0, 360), 0), col=shade(rng.choice(biomes.STRATA), .9),
                      grad=.35, cap=(SAND_TOP, .6))
            return 1.2 * s
        if kind == 'basalt':            # orgues de basalte, parfois veinées de lave
            for _ in range(rng.randint(3, 5)):
                h = rng.uniform(1.2, 3.2) * s
                b.add('prism6', (x + rng.uniform(-1, 1), h / 2 - .1, z + rng.uniform(-1, 1)), (1.1 * s, h, 1.1 * s),
                      rot=(rng.uniform(-6, 6), rng.uniform(0, 60), 0), col=shade(rng.choice(BASALTS), rng.uniform(.85, 1.15)),
                      grad=.35, cap=(ASH_TOP, .5))
            if rng.random() < .5:
                b.add('blob', (x, .15, z), (1.6 * s, .2, 1.3 * s), col=glowing(biomes.LAVA, .9), wobble=.3)
            return 1.2 * s
        if kind == 'obsidian':
            for _ in range(rng.randint(3, 5)):
                h = rng.uniform(1.0, 2.6) * s
                b.add('cone4', (x + rng.uniform(-1, 1), h / 2, z + rng.uniform(-1, 1)), (.6 * s, h, .6 * s),
                      rot=(rng.uniform(-15, 15), rng.uniform(0, 90), rng.uniform(-15, 15)), col=OBSIDIAN)
            return .8 * s
        if kind == 'vent':              # cheminée volcanique : cône de scories et lueur au sommet
            b.add('frustum', (x, .7 * s, z), (2.6 * s, 1.4 * s, 2.6 * s), col=shade(BASALT, 1.1), grad=.3)
            b.add('cyl8', (x, 1.42 * s, z), (.55 * s, .06, .55 * s), col=glowing(biomes.LAVA_HOT, 1))
            return 1.0 * s
        if kind == 'broadleaf':         # feuillu : tronc qui s'affine, branches, couronne en touffes
            tx, tz = self._trunk(b, x, z, s, 2.9 * s, bark)
            self._canopy(b, tx, 3.5 * s, tz, 1.45 * s, 1.3 * s, rng.choice(greens))
            return 1.0 * s
        if kind == 'conifer':           # conifère : étages de branches tombantes
            b.add('trunk', (x, .9 * s, z), (.45 * s, 1.8 * s, .45 * s), col=color.rgb(.38, .25, .15), grad=.35)
            g = color.rgb(.1, .36 + rng.uniform(-.04, .04), .2)
            if bio == biomes.ROCHE:     # pin des plateaux, plus sec
                g = color.rgb(.2, .36 + rng.uniform(-.04, .04), .18)
            for i in range(5):
                r = (2.9 - i * .5) * rng.uniform(.92, 1.06)
                b.add('cone8', (x, (1.8 + i * .92) * s, z), (r * s, 1.7 * s, r * s),
                      rot=(rng.uniform(-4, 4), rng.uniform(0, 45), rng.uniform(-4, 4)),
                      col=shade(g, .82 + i * .09), wobble=.12, grad=.45, light=.12)
            return .9 * s
        if kind == 'tropical':          # palmier : tronc courbé, palmes qui retombent
            a0 = rng.uniform(0, 360)
            dx, dz = polar(a0, 1)
            for i in range(3):
                t = i / 3
                b.add('cyl6', (x + dx * t * t * .9 * s, (.65 + i * 1.2) * s, z + dz * t * t * .9 * s),
                      (.42 * s, 1.35 * s, .42 * s), rot=(0, a0, -(4 + i * 7)), col=color.rgb(.5, .37, .24), grad=.25)
            tx, ty, tz = x + dx * .8 * s, 3.8 * s, z + dz * .8 * s
            g = rng.choice(greens)
            for i in range(8):
                ang = i * 45 + rng.uniform(-12, 12)
                ox, oz = polar(ang, 1.25 * s)
                b.add('blob', (tx + ox, ty - .15 * s, tz + oz), (.95 * s, .22 * s, 2.7 * s), rot=(26, ang, 0),
                      col=shade(g, rng.uniform(.88, 1.12)), wobble=.12, grad=.3, light=.15)
            b.add('blob_lo', (tx, ty + .1 * s, tz), .9 * s, col=shade(g, .8), wobble=.15)
            for _ in range(3):
                b.add('sphere_lo', (tx + rng.uniform(-.3, .3) * s, ty - .35 * s, tz + rng.uniform(-.3, .3) * s),
                      .28 * s, col=color.rgb(.45, .32, .15))
            return .8 * s
        g = rng.choice(greens)          # buisson fleuri
        for i in range(4):
            ox, oz = polar(i * 90 + rng.uniform(-30, 30), .6 * s if i else 0)
            t = rng.uniform(1.2, 1.7) * s
            b.add('blob_lo', (x + ox, .45 * t, z + oz), (t * 1.2, t, t * 1.2), col=shade(g, rng.uniform(.85, 1.1)),
                  wobble=.25, grad=.45, light=.18)
        if rng.random() < .6:
            fc = rng.choice((color.rgb(1, .4, .55), color.rgb(1, .9, .3), color.white, color.rgb(.7, .5, 1)))
            for _ in range(6):
                ox, oz = polar(rng.uniform(0, 360), rng.uniform(.3, 1.1) * s)
                b.add('sphere_lo', (x + ox, 1.25 * s, z + oz), .2, col=fc)
        return 1.2 * s

    def _outcrop(self, b, x0, z0, block=True):
        """Massif rocheux, parfois avec des ruines de pierre."""
        rng = self.rng
        for _ in range(rng.randint(4, 7)):
            ox, oz = rng.uniform(-3, 3), rng.uniform(-3, 3)
            s = rng.uniform(1.2, 2.6)
            rot = (rng.uniform(-10, 10), rng.uniform(0, 180), rng.uniform(-10, 10))
            b.add(rng.choice(ROCKS), (x0 + ox, s * .75, z0 + oz), (s * 1.9, s * 2.1, s * 1.7), rot=rot,
                  col=shade(ROCK, rng.uniform(.8, 1.1)), grad=.4, cap=(MOSS, .9) if rng.random() < .6 else None)
        for _ in range(rng.randint(2, 4)):
            ox, oz = rng.uniform(-4, 4), rng.uniform(-4, 4)
            self._rock(b, x0 + ox, z0 + oz, rng.uniform(.7, 1.4))
        if rng.random() < .5:            # ruines
            ang = rng.uniform(0, 180)
            stone = color.rgb(.78, .75, .66)
            for s in (-1, 1):
                sx, sz = polar(ang, 1.8 * s)
                hh = rng.uniform(2.2, 3.4)
                b.add('cyl', (x0 + sx + 3, hh / 2, z0 + sz), (.8, hh, .8), col=stone, grad=.3)
            b.add('box', (x0 + 3, 3.5, z0), (4.6, .6, .9), rot=(0, ang + 90, 0), col=shade(stone, .95))
            b.add('cyl', (x0 + 1, .35, z0 + 2.5), (.8, 1.6, .8), rot=(90, rng.uniform(0, 180), 0), col=shade(stone, .92))
        if block:
            self.block(x0, z0, 3.6)
            self.block(x0 + 3, z0, 1.6)

    def _wall_points(self, spacing):
        """Points au bord des massifs, espacés d'environ `spacing`, avec la normale (nx, nz)
        qui s'enfonce dans le massif."""
        sdf, rng = self.wall_sdf, self.rng
        ii, jj = np.nonzero((sdf > 0) & (sdf < J_RES * 1.5))
        order = list(range(len(ii)))
        rng.shuffle(order)
        taken, out = {}, []
        for k in order:
            i, j = ii[k], jj[k]
            x, z = self.j_min + i * J_RES, self.j_min + j * J_RES
            if math.hypot(x, z) > F - 2.5:
                continue
            cx, cz = int(x // spacing), int(z // spacing)
            if any(math.hypot(x - px, z - pz) < spacing
                   for a in (cx - 1, cx, cx + 1) for b in (cz - 1, cz, cz + 1) for px, pz in taken.get((a, b), ())):
                continue
            taken.setdefault((cx, cz), []).append((x, z))
            gx, gz = self.wall_gx[i, j], self.wall_gz[i, j]
            g = math.hypot(gx, gz) or 1
            out.append((x, z, gx / g, gz / g))
        return out

    def _cliff(self, b, x, z, nx, nz):
        """Morceau de falaise : gros blocs à facettes serrés, le dessus moussu, plus hauts vers l'intérieur."""
        rng = self.rng
        yaw = math.degrees(math.atan2(nx, nz))
        h = rng.uniform(2.8, 3.9)
        c = shade(CLIFF, rng.uniform(.82, 1.12))
        px, pz = x + nx * .7, z + nz * .7
        b.add(rng.choice(ROCKS), (px, h * .42, pz), (rng.uniform(3.2, 4.0), h * 1.2, 2.8),
              rot=(rng.uniform(-6, 6), yaw + rng.uniform(-18, 18), rng.uniform(-6, 6)), col=c, grad=.45,
              cap=(shade(MOSS, rng.uniform(.9, 1.1)), .9))
        if rng.random() < .55:          # deuxième rangée, plus haute
            h2 = h * rng.uniform(1.1, 1.4)
            b.add(rng.choice(ROCKS), (x + nx * 2.6, h2 * .45, z + nz * 2.6), (3.6, h2 * 1.2, 3.2),
                  rot=(0, yaw + rng.uniform(-30, 30), 0), col=shade(c, .9), grad=.45, cap=(MOSS, .9))
        if rng.random() < .35:          # éboulis au pied
            self._rock(b, x - nx * .5 + nz * rng.uniform(-1, 1), z - nz * .5 - nx * rng.uniform(-1, 1),
                       rng.uniform(.3, .55), moss=.3)

    def _grove(self, b, x, z, nx, nz, k, bio=biomes.JUNGLE):
        """Rideau d'arbres : troncs serrés derrière une haie épaisse et des racines."""
        rng = self.rng
        yaw = math.degrees(math.atan2(nx, nz))
        g = rng.choice(GREENS[bio])
        for j in (-1, 1):                # haie : deux touffes serrées
            t = rng.uniform(.3, .9) * j
            d = .6 + rng.uniform(0, .5)
            b.add('blob_lo', (x + nx * d + nz * t, .9, z + nz * d - nx * t),
                  (rng.uniform(2.2, 2.8), rng.uniform(1.8, 2.3), 2.0), rot=(0, yaw + rng.uniform(-30, 30), 0),
                  col=shade(g, rng.uniform(.72, .9)), wobble=.26, grad=.5, light=.15)
        if rng.random() < .5:
            b.add('blob', (x + nx * .1, .3, z + nz * .1), (1.6, .6, 1.0), rot=(0, yaw, 0),
                  col=color.rgb(.36, .25, .15), wobble=.25, grad=.3)
        if k % 2 == 0:
            kinds = {biomes.EAU: ('blossom', 'tropical', 'broadleaf'),
                     biomes.PLANTE: ('broadleaf', 'broadleaf', 'tropical')}.get(bio, ('broadleaf', 'conifer'))
            self._tree(b, x + nx * 1.9, z + nz * 1.9, rng.uniform(1.0, 1.35), rng.choice(kinds), bio)

    def _build_jungle(self):
        rng = self.rng
        b = self.b
        # bords des massifs : falaises ou rideaux d'arbres selon la région et le biome
        for k, (x, z, nx, nz) in enumerate(self._wall_points(1.9)):
            bio = self.biome.pick(rng, x, z)
            if bio == biomes.ROCHE:
                self._mesa_foot(b, x, z, nx, nz, k)
            elif bio == biomes.FEU:
                self._basalt_wall(b, x, z, nx, nz, k)
            elif bio == biomes.EAU:
                self._grove(b, x, z, nx, nz, k, bio)
                if rng.random() < .16:
                    self._crystals(b, x + nx * .4, z + nz * .4, rng.uniform(.7, 1.1))
            elif bio == biomes.PLANTE:
                self._grove(b, x, z, nx, nz, k, bio)
                if rng.random() < .25:
                    self._tree(b, x - nx * .2, z - nz * .2, rng.uniform(.7, .95), 'fern')
            else:
                style = math.sin(x * .045 + math.sin(z * .03) * 2) * math.cos(z * .05 + math.sin(x * .035) * 1.5)
                if style > -.2:
                    self._cliff(b, x, z, nx, nz)
                else:
                    self._grove(b, x, z, nx, nz, k, bio)
                if bio == biomes.ELECTRIK and rng.random() < .1:   # cristaux chargés d'électricité
                    self._crystals(b, x + nx * .3, z + nz * .3, rng.uniform(.6, .9), VOLT)
            if bio not in (biomes.ROCHE, biomes.FEU) and rng.random() < .05:       # champignons au pied du mur
                ox, oz = x - nx * .9, z - nz * .9
                b.add('cyl6', (ox, .2, oz), (.18, .4, .18), col=color.rgb(.95, .92, .85))
                b.add('dome', (ox, .35, oz), (.6, .4, .6), col=color.rgb(.9, .2, .15))
        # cœur des massifs : végétation du biome (inaccessible, simple décor)
        S = C.QUALITY['tree_spacing']
        n = int(F / S)
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x = i * S + rng.uniform(-S * .38, S * .38)
                z = j * S + rng.uniform(-S * .38, S * .38)
                if math.hypot(x, z) > F - 3 or self.wall_dist(x, z) < 2.6 or self.landmarks.reserved(x, z):
                    continue
                bio = self.biome.pick(rng, x, z)
                density, kinds = FLORA[bio]
                if rng.random() > density:
                    continue
                kind = rng.choice(kinds)
                if kind == 'outcrop':
                    self._outcrop(b, x, z, block=False)
                else:
                    self._tree(b, x, z, rng.uniform(1.0, 1.45), kind, bio)
        self._build_bushes()

    def _mesa_foot(self, b, x, z, nx, nz, k):
        """Pied du plateau de grès : colonnes de roche serrées (le dessus ensablé) et blocs éboulés."""
        rng = self.rng
        yaw = math.degrees(math.atan2(nx, nz))
        for j in range(rng.randint(2, 3)):
            t = rng.uniform(-1, 1)
            d = rng.uniform(.4, 1.6)
            cx, cz = x + nx * d + nz * t, z + nz * d - nx * t
            h = rng.uniform(1.6, 3.2) + d * .6
            c = shade(rng.choice(biomes.STRATA), rng.uniform(.85, 1.05))
            b.add(rng.choice(('prism6', 'prism5')), (cx, h / 2 - .2, cz), (rng.uniform(1.2, 1.8), h, rng.uniform(1.1, 1.6)),
                  rot=(rng.uniform(-4, 4), yaw + rng.uniform(0, 60), rng.uniform(-4, 4)), col=c, grad=.4,
                  cap=(SAND_TOP, .7))
        if rng.random() < .35:           # blocs éboulés
            for _ in range(rng.randint(1, 3)):
                ox = x - nx * rng.uniform(.2, 1.0) + nz * rng.uniform(-1.2, 1.2)
                oz = z - nz * rng.uniform(.2, 1.0) - nx * rng.uniform(-1.2, 1.2)
                t = rng.uniform(.35, .7)
                b.add(rng.choice(ROCKS), (ox, t * .3, oz), (t * 1.6, t * 1.1, t * 1.4), rot=(0, rng.uniform(0, 360), 0),
                      col=shade(rng.choice(biomes.STRATA), rng.uniform(.8, 1.0)), grad=.3)
        if rng.random() < .18:           # touffe d'herbe sèche
            self._tree(b, x - nx * .3, z - nz * .3, rng.uniform(.5, .7), 'dry', biomes.ROCHE)

    def _basalt_wall(self, b, x, z, nx, nz, k):
        """Paroi de basalte : orgues (colonnes hexagonales) sombres, fissures de lave, arbres calcinés."""
        rng = self.rng
        yaw = math.degrees(math.atan2(nx, nz))
        for j in range(rng.randint(2, 4)):
            t = rng.uniform(-1.1, 1.1)
            d = rng.uniform(.4, 1.8)
            cx, cz = x + nx * d + nz * t, z + nz * d - nx * t
            h = rng.uniform(1.4, 2.8) + d * .7
            b.add('prism6', (cx, h / 2 - .2, cz), (rng.uniform(1.0, 1.5), h, rng.uniform(1.0, 1.4)),
                  rot=(rng.uniform(-5, 5), rng.uniform(0, 60), rng.uniform(-5, 5)),
                  col=shade(rng.choice(BASALTS), rng.uniform(.85, 1.15)), grad=.4, cap=(ASH_TOP, .5))
        if rng.random() < .35:           # fissure où la lave affleure, côté passage
            t = rng.uniform(-.8, .8)
            b.add('blob', (x + nx * .1 + nz * t, .5, z + nz * .1 - nx * t), (.3, 1.2, .3),
                  rot=(rng.uniform(-20, 20), yaw, rng.uniform(-25, 25)), col=glowing(biomes.LAVA, .85), wobble=.3)
        if rng.random() < .3:            # blocs au pied
            t = rng.uniform(.4, .8)
            b.add(rng.choice(ROCKS), (x - nx * .4 + nz * rng.uniform(-1, 1), t * .3, z - nz * .4 - nx * rng.uniform(-1, 1)),
                  (t * 1.6, t * 1.1, t * 1.4), rot=(0, rng.uniform(0, 360), 0), col=shade(BASALT, rng.uniform(.85, 1.1)),
                  grad=.3)
        if k % 5 == 0:
            self._tree(b, x + nx * 1.8, z + nz * 1.8, rng.uniform(1.0, 1.3), 'dead', biomes.FEU)

    def _crystals(self, b, x, z, s, palette=None):
        """Grappe de cristaux (bleutés par défaut), légèrement lumineux."""
        rng = self.rng
        base = rng.choice(palette or CRYSTAL)
        for i in range(rng.randint(3, 5)):
            h = rng.uniform(1.0, 2.4) * s * (1.25 if i == 0 else 1)
            ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(.3, .7) * s)
            b.add('cone6', (x + ox, h * .42, z + oz), (.55 * s, h, .55 * s),
                  rot=(rng.uniform(-22, 22) if i else 0, rng.uniform(0, 60), rng.uniform(-22, 22) if i else 0),
                  col=glowing(shade(base, rng.uniform(.9, 1.1)), .35))

    def _grass_clump(self, b, x, z, s, g, mound=False):
        """Touffe de hautes herbes : longues feuilles courbées qui s'ouvrent en éventail, sombres au
        pied et claires au bout (comme les cachettes de Pokémon Unite)."""
        rng = self.rng
        n = 6
        a0 = rng.uniform(0, 360)
        for k in range(n):
            a = a0 + k * 360 / n + rng.uniform(-22, 22)
            h = rng.uniform(1.5, 2.1) * s
            tilt = rng.uniform(14, 34) if k else rng.uniform(0, 8)            # une feuille presque droite
            rot = (tilt, a, rng.uniform(-10, 10))
            scale = (rng.uniform(.62, .82), h, rng.uniform(.45, .75) * h)
            base = _rot_matrix(rot) @ np.array((0, -h / 2, 0))                # pied de la feuille au sol
            ox, oz = polar(a, rng.uniform(.05, .3))
            b.add('blade', (x + ox - base[0], -.05 - base[1], z + oz - base[2]), scale, rot=rot,
                  col=shade(g, rng.uniform(.92, 1.1)), grad=.4, tip=(GRASS_TIP, .7))
        if mound:                        # masse sombre au pied : la touffe paraît dense
            b.add('sphere_lo', (x, .2 * s, z), (1.7 * s, .8 * s, 1.7 * s), rot=(0, rng.uniform(0, 90), 0),
                  col=shade(g, .78), wobble=.2, grad=.4)

    def _build_bushes(self):
        """Hautes herbes : touffes de longues feuilles, bien plus hautes que l'herbe des pelouses."""
        b, rng = self.b, self.rng
        inside = self.bush_grid > 0
        depth = ndimage.distance_transform_edt(inside) * J_RES       # distance au bord de la touffe
        ii, jj = np.nonzero(inside & (np.arange(inside.shape[0])[:, None] % 2 == 0)
                            & (np.arange(inside.shape[1])[None, :] % 2 == 0))
        for i, j in zip(ii, jj):
            x = self.j_min + i * J_RES + rng.uniform(-.3, .3)
            z = self.j_min + j * J_RES + rng.uniform(-.3, .3)
            s = .62 + .38 * _smoothstep(.2, 1.6, depth[i, j])    # plus basses au bord : silhouette arrondie
            self._grass_clump(b, x, z, s, rng.choice(BUSH_GREENS), mound=(i + j) % 4 == 0)

        # herbes et fleurs sur les pelouses
        for _ in range(C.QUALITY['grass']):
            a, r = rng.uniform(0, 360), math.sqrt(rng.random()) * (F - 4)
            x, z = polar(a, r)
            if not self._clear_of_lanes(x, z, .6) or self.blocked(x, z, .3) or self._inside_open_disc(x, z):
                continue
            if self.bush_at(x, z):
                continue
            if any(polyline_dist(x, z, rp) < rw / 2 + .3 for rp, rw in RIVERS):
                continue
            q = rng.random()
            if q < .55:
                for _ in range(3):
                    b.add('cone6', (x + rng.uniform(-.3, .3), .25, z + rng.uniform(-.3, .3)), (.25, .55, .25),
                          rot=(rng.uniform(-15, 15), 0, rng.uniform(-15, 15)), col=color.rgb(.3, .62, .24))
            else:
                c = rng.choice((color.rgb(1, .4, .5), color.rgb(1, .92, .3), color.white, color.rgb(.6, .5, 1)))
                for _ in range(4):
                    b.add('sphere_lo', (x + rng.uniform(-.6, .6), .14, z + rng.uniform(-.6, .6)), .2, col=c)

    # ================================================================ navigation
    def _build_nav(self):
        n = int(math.ceil(F / NAV_CELL)) + 1
        self.nav_n = n
        size = 2 * n
        ii, jj = np.meshgrid(np.arange(size), np.arange(size), indexing='ij')
        cx = (ii - n + .5) * NAV_CELL
        cz = (jj - n + .5) * NAV_CELL
        walk = np.hypot(cx, cz) < F - 2
        margin = .75
        walk &= self._jsample_np(self.wall_sdf, cx, cz) < -margin      # murs de la jungle
        for ox, oz, orad in self.obstacles:
            r = orad + margin
            i0, i1 = int((ox - r) / NAV_CELL + n), int((ox + r) / NAV_CELL + n) + 1
            j0, j1 = int((oz - r) / NAV_CELL + n), int((oz + r) / NAV_CELL + n) + 1
            i0, j0 = max(i0, 0), max(j0, 0)
            sub = np.hypot(cx[i0:i1, j0:j1] - ox, cz[i0:i1, j0:j1] - oz) < r
            walk[i0:i1, j0:j1] &= ~sub
        self.walk = walk
        self.size = size
        river = np.zeros_like(walk)
        for pts, w in RIVERS:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                dx, dz = bx - ax, bz - az
                L2 = dx * dx + dz * dz or 1
                t = np.clip(((cx - ax) * dx + (cz - az) * dz) / L2, 0, 1)
                river |= np.hypot(cx - ax - dx * t, cz - az - dz * t) < w / 2
        self.river = river
        # un graphe par équipe : la base adverse est interdite (elle blesse les intrus)
        self.team_walk, self.graphs = {}, {}
        for team, other in (('rouge', 'bleu'), ('bleu', 'rouge')):
            ox, oz = C.TEAMS[other]['base']
            tw = walk & (np.hypot(cx - ox, cz - oz) > C.BASE_RADIUS + 3)
            self.team_walk[team] = tw
            self.graphs[team] = self._graph(tw)
        self.team_walk[None], self.graphs[None] = walk, self._graph(walk)
        self.fields = {}

    def _graph(self, walk):
        '''Graphe 8-voisins entre cases praticables.'''
        size = self.size
        ids = np.arange(size * size).reshape(size, size)
        rows, cols, costs = [], [], []
        for di, dj, cost in ((1, 0, 1), (0, 1, 1), (1, 1, 1.414), (1, -1, 1.414)):
            i0, i1 = max(0, -di), size - max(0, di)
            j0, j1 = max(0, -dj), size - max(0, dj)
            ok = walk[i0:i1, j0:j1] & walk[i0 + di:i1 + di, j0 + dj:j1 + dj]
            rows.append(ids[i0:i1, j0:j1][ok])
            cols.append(ids[i0 + di:i1 + di, j0 + dj:j1 + dj][ok])
            costs.append(np.full(int(ok.sum()), cost * NAV_CELL))
        return coo_matrix((np.concatenate(costs), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(size * size, size * size)).tocsr()

    def cell_of(self, x, z):
        n = self.nav_n
        return (min(max(int(math.floor(x / NAV_CELL)) + n, 0), 2 * n - 1),
                min(max(int(math.floor(z / NAV_CELL)) + n, 0), 2 * n - 1))

    def cell_centre(self, i, j):
        return Vec3((i - self.nav_n + .5) * NAV_CELL, 0, (j - self.nav_n + .5) * NAV_CELL)

    def _nearest_walkable(self, i, j, walk=None):
        walk = self.walk if walk is None else walk
        if walk[i, j]:
            return i, j
        for r in range(1, 8):
            for di in range(-r, r + 1):
                for dj in range(-r, r + 1):
                    a, b = i + di, j + dj
                    if 0 <= a < walk.shape[0] and 0 <= b < walk.shape[1] and walk[a, b]:
                        return a, b
        return i, j

    def field(self, key, x, z, team=None):
        """Carte des distances vers la destination (x, z), calculée une seule fois par clé."""
        f = self.fields.get((key, team))
        if f is None:
            i, j = self._nearest_walkable(*self.cell_of(x, z), self.team_walk[team])
            d = dijkstra(self.graphs[team], directed=False, indices=i * self.size + j)
            f = d.reshape(self.size, self.size)
            self.fields[(key, team)] = f
        return f

    def direction(self, key, target, pos, team=None):
        """Direction (Vec3 normalisée) à suivre pour aller de pos vers la destination `key`."""
        f = self.field(key, target.x, target.z, team)
        i, j = self._nearest_walkable(*self.cell_of(pos.x, pos.z), self.team_walk[team])
        if not np.isfinite(f[i, j]) or f[i, j] < 2.5:
            d = Vec3(target.x - pos.x, 0, target.z - pos.z)
            return d.normalized() if d.length() > .01 else Vec3(0, 0, 0)
        # on descend le champ sur quelques cases et on vise la dernière (trajectoire plus lisse)
        size = f.shape[0]
        for _ in range(3):
            best = (f[i, j], i, j)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    a, b = i + di, j + dj
                    if 0 <= a < size and 0 <= b < size and f[a, b] < best[0]:
                        best = (f[a, b], a, b)
            if best[1:] == (i, j):
                break
            i, j = best[1], best[2]
        d = self.cell_centre(i, j) - Vec3(pos.x, 0, pos.z)
        return d.normalized() if d.length() > .01 else Vec3(0, 0, 0)

    def _update_emitters(self, dt, focus):
        """Particules du décor près de la caméra : écume et bruine au pied des cascades, bulles qui
        éclatent dans la lave, panache du volcan."""
        from game.world import fx
        P = fx.PARTICLES
        if P is None or focus is None:
            return
        rng = random
        for x, y, z, kind, s in self.emitters:
            if (x - focus.x) ** 2 + (z - focus.z) ** 2 > 60 ** 2:
                continue
            if kind == 'fall':
                if rng.random() < 18 * dt * s:
                    P.emit((x + fx.rnd(.8 * s), y + .2, z + fx.rnd(.8 * s)), fx.MIST, size=1.6 * s, life=1.2,
                           vel=(fx.rnd(.6), fx.ru(.6, 1.4), fx.rnd(.6)), grow=2.2, tex='smoke', blend='alpha', alpha=.35)
                if rng.random() < 30 * dt * s:
                    fx.droplet(P, (x + fx.rnd(.6 * s), y + .1, z + fx.rnd(.6 * s)),
                               (fx.rnd(1.8), fx.ru(2, 4), fx.rnd(1.8)), s=.18, life=.5)
                if rng.random() < 5 * dt * s:
                    fx.ground_ring(P, (x + fx.rnd(.8 * s), y + .06, z + fx.rnd(.8 * s)), (.9, .97, 1), .3, 1.6 * s, .9,
                                   alpha=.55, blend='alpha')
            elif kind == 'lava':
                if rng.random() < 2.5 * dt * s:
                    a, r = rng.uniform(0, math.tau), rng.uniform(0, s)
                    bx, bz = x + math.sin(a) * r, z + math.cos(a) * r
                    P.emit((bx, y + .1, bz), (1, .75, .25), size=.6, life=.35, grow=1.8)
                    for _ in range(4):
                        fx.spark(P, (bx, y + .15, bz), (fx.rnd(1.5), fx.ru(2, 4), fx.rnd(1.5)), s=.1, life=.6,
                                 gravity=8)
                    if rng.random() < .5:
                        fx.smoke(P, (bx, y + .3, bz), (0, 1, 0), s=.9, life=1.2, alpha=.25)
            elif kind == 'volcano':
                if rng.random() < 6 * dt:
                    fx.smoke(P, (x + fx.rnd(1), y + .5, z + fx.rnd(1)), (fx.rnd(.5) + .4, fx.ru(2.5, 4), fx.rnd(.5)),
                             s=3.2, life=4, alpha=.45, col=(.26, .24, .23), col2=(.5, .48, .47))
                if rng.random() < 10 * dt:
                    fx.spark(P, (x + fx.rnd(1.2), y + .3, z + fx.rnd(1.2)), (fx.rnd(2), fx.ru(5, 9), fx.rnd(2)),
                             s=.14, life=1.4, gravity=5)

    def in_river(self, x, z):
        i, j = self.cell_of(x, z)
        return bool(self.river[i, j])

    def update(self, dt, focus=None):
        self.time += dt
        set_time(self.water_node, self.time)
        self._update_emitters(dt, focus)
        self.vortex.set_h(self.vortex.get_h() + dt * 30)
        self.arcs.update(dt)
