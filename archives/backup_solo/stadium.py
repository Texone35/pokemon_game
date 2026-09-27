"""La carte du stade Pokémon Dominion : construction 3D, collisions et navigation.

Disposition (voir config.py) : 5 arènes ouvertes (Nord, Ouest, Est, Sud-Ouest,
Sud-Est), les bases des deux équipes au sud, le Boss Pit au centre, une
rivière peu profonde (praticable) du nord au sud, des voies principales et une
jungle dense avec ses camps de Pokémon neutres. Le tout est entouré par les
tribunes du stade.

Tout le décor est procédural : des primitives (boîtes, sphères, cônes...)
fusionnées par MeshBuilder en quelques gros maillages.

Navigation : la carte est quadrillée (cases de NAV_CELL unités). Pour chaque
destination (arène, base, camp...) on calcule une fois la distance de chaque
case à la destination (Dijkstra) ; une IA n'a plus qu'à descendre ce champ.
"""
import math
import random

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from ursina import Vec3, color, lerp

import config as C
from emblems import add_emblem
from fx import Flow
from geometry import ChunkedBuilder, MeshBuilder

F = C.FIELD_RADIUS
CELL = 8.0            # grille de collision
NAV_CELL = 2.0        # grille de navigation

# ---------------------------------------------------------------- palette
LAWN1, LAWN2 = color.rgb(.42, .72, .27), color.rgb(.35, .64, .22)
FOREST1, FOREST2 = color.rgb(.22, .42, .15), color.rgb(.28, .38, .16)
SAND = color.rgb(.76, .7, .52)
LANE = color.rgb(.88, .89, .9)
LANE_EDGE = color.rgb(.62, .64, .7)
CURB = color.rgb(.97, .97, .98)
SEAM = color.rgb(.74, .75, .79)
NEON = color.rgb(.35, .8, 1)
PATH = color.rgb(.62, .5, .34)
WATER = color.rgb(.3, .78, .86)
WATER_DEEP = color.rgb(.1, .5, .78)
WATER_Y = -.38        # surface de la rivière (son lit est creusé dans le relief)
BRIDGE_Y = .28        # hauteur du tablier des ponts (là où l'on marche)
HM_RES = 1.0          # finesse de la carte des hauteurs
ROCK = color.rgb(.55, .56, .58)
ROCK_DARK = color.rgb(.42, .43, .46)
MOSS = color.rgb(.33, .52, .22)
WOOD = color.rgb(.55, .37, .2)
WOOD_DARK = color.rgb(.36, .23, .12)
STONE = color.rgb(.8, .81, .84)
NAVY = color.rgb(.17, .19, .36)
NAVY2 = color.rgb(.23, .25, .46)
TREE_GREENS = [color.rgb(.13, .45, .16), color.rgb(.18, .52, .18), color.rgb(.1, .4, .2),
               color.rgb(.22, .56, .2), color.rgb(.15, .48, .12), color.rgb(.26, .6, .22)]


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


def circle_pts(cx, cz, r, n=24, a0=0, a1=360):
    return [(cx + math.sin(math.radians(a0 + (a1 - a0) * i / n)) * r,
             cz + math.cos(math.radians(a0 + (a1 - a0) * i / n)) * r) for i in range(n + 1)]


def mirror(pts):
    return [(-x, z) for x, z in pts]


def polar(a, r, x0=0.0, z0=0.0):
    a = math.radians(a)
    return x0 + math.sin(a) * r, z0 + math.cos(a) * r


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


# ==================================================================== tracé
A = {a['key']: a['pos'] for a in C.ARENAS}
RB, BB = C.TEAMS['rouge']['base'], C.TEAMS['bleu']['base']

# voies principales : (points, largeur)
LANES = [
    # grand anneau qui relie les arènes et les bases
    ([A['nord'], (30, 80), (56, 64), A['est'], (86, -10), A['sud_est'], (62, -78), BB], 4.6),
    ([A['nord'], (-30, 80), (-56, 64), A['ouest'], (-86, -10), A['sud_ouest'], (-62, -78), RB], 4.6),
    ([RB, (0, -104), BB], 4.6),
    # voie centrale Ouest - Boss Pit - Est
    ([(-106, -5), (-60, -5), (-14, -5)], 5.0),
    ([(14, -5), (60, -5), (106, -5)], 5.0),
    # voie verticale Nord - Boss Pit - bas
    ([(0, 14), (0, 40), (0, 68)], 3.6),
    ([(0, -14), (0, -104)], 3.6),
    # liaisons bases -> arènes proches
    ([RB, (-52, -60)], 3.4),
    ([BB, (52, -60)], 3.4),
]

# rivière peu profonde : (points, largeur)
_R_MAIN = [(0, 70), (-9, 58), (8, 44), (-8, 30), (-2, 17.5)]
_R_LOW = [(0, -18.5), (-9, -31), (-15, -46), (-7, -62), (0, -76), (0, -90)]
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
        self.flows = []
        self._plan_paths()
        self._build_heightmap()
        self._new_builders()
        self._build_ground()
        self._build_lanes()
        self._build_river()
        self._build_stands()
        self._build_arenas()
        self._build_bases()
        self._build_pit()
        self._build_camps()
        self._build_jungle()
        self._flush()
        self._build_nav()

    def _flush(self):
        """Transforme les constructeurs restants en entités (quelques gros maillages)."""
        for b, em in ((self.b, 0), (self.glow, .95), (self.water, .22), (self.flat, 0)):
            if b.count:
                b.static(self.root, emissive=em, transparent=b is self.water)
        self._new_builders()

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
        return any(math.hypot(x - ox, z - oz) < orad + r for ox, oz, orad in self.nearby(x, z, r))

    def collide(self, pos, radius=.5):
        """Repousse la position hors des obstacles et dans le terrain."""
        lim = F - 1 - radius
        r = math.hypot(pos.x, pos.z)
        if r > lim:
            pos.x *= lim / r
            pos.z *= lim / r
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

    # ================================================================ espaces libres
    def _open_space(self, x, z, margin=0.0):
        """Vrai si (x, z) est hors de toute zone de jeu ouverte (donc dans la jungle)."""
        for pts, w in LANES:
            if polyline_dist(x, z, pts) < w / 2 + 2.4 + margin:
                return False
        for pts, w in RIVERS:
            if polyline_dist(x, z, pts) < w / 2 + 1.8 + margin:
                return False
        for pts, w in self.paths:
            if polyline_dist(x, z, pts) < w / 2 + 1.2 + margin:
                return False
        for a in C.ARENAS:
            if math.hypot(x - a['pos'][0], z - a['pos'][1]) < C.ARENA_RADIUS + 9 + margin:
                return False
        for t in C.TEAMS.values():
            if math.hypot(x - t['base'][0], z - t['base'][1]) < C.BASE_RADIUS + 7 + margin:
                return False
        if math.hypot(x, z) < C.PIT_RADIUS + 9 + margin:
            return False
        for c in C.CAMPS:
            if math.hypot(x - c['pos'][0], z - c['pos'][1]) < 7.5 + margin:
                return False
        return True

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
        """Rocher aux formes irrégulières, parfois couvert de mousse."""
        rng = rng or self.rng
        rot = (rng.uniform(-12, 12), rng.uniform(0, 180), rng.uniform(-12, 12))
        c = shade(ROCK, rng.uniform(.8, 1.12))
        b.add('blob', (x, s * .28, z), (s * 1.7, s * 1.15, s * 1.4), rot=rot, col=c, wobble=.24, grad=.4)
        if rng.random() < moss:
            b.add('blob', (x, s * .66, z), (s * 1.2, s * .38, s * 1.0), rot=rot, col=MOSS, wobble=.22, grad=.25)

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
        """Relief : collines dans la jungle, légères ondulations sur les pelouses, lit de rivière
        creusé bordé de petits talus. Voies, arènes, bases, Boss Pit et camps restent plats."""
        n = int(F + 6)
        xs = np.arange(-n, n + HM_RES / 2, HM_RES)
        X, Z = np.meshgrid(xs, xs, indexing='ij')
        open_d, river_d, lane_d, disc_d = self._fields_np(X, Z)
        amp = C.QUALITY['relief']
        big = ((np.sin(X * .07 + np.sin(Z * .05) * 2) * np.cos(Z * .06 + np.sin(X * .04) * 1.5) * .5 + .5) * 2.6
               + (np.sin(X * .21 + Z * .17) * np.sin(Z * .19 - X * .07) * .5 + .5) * 1.0)
        bumps = np.sin(X * .55 + np.sin(Z * .4) * 1.5) * np.sin(Z * .5 + X * .2) * .5 + .5
        flat_d = np.minimum(lane_d, disc_d)
        jungle = _smoothstep(1.5, 9, open_d)
        lawn = _smoothstep(.8, 4.5, np.minimum(flat_d, river_d + 2))
        H = amp * (big * jungle + bumps * (.35 * lawn + .6 * jungle))
        # rivière : lit profond au centre, berges en pente, petit talus juste derrière
        H -= 1.3 * (1 - _smoothstep(-2.4, .9, river_d))
        H += amp * .4 * np.exp(-((river_d - 2.4) / 1.2) ** 2) * _smoothstep(.5, 2.5, flat_d)
        H *= 1 - _smoothstep(F - 7, F - 2, np.hypot(X, Z))
        self.hm, self.hm_n, self.hm_min = H, len(xs), -n
        self.hm_gx, self.hm_gz = np.gradient(H, HM_RES)
        # hauteur où l'on marche : comme le sol, sauf sur les voies (planes) et les ponts
        on_lane = lane_d < .4
        self.walk_hm = np.where(on_lane, np.where(river_d < 1.0, BRIDGE_Y, np.maximum(H, 0)), H)

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
        # pelouse claire autour des zones de jeu, sous-bois plus sombre dans la jungle
        jungle = _smoothstep(1.0, 6.0, open_d)[..., None]
        lawn = np.array(tuple(LAWN1)) * (1 - noise) + np.array(tuple(LAWN2)) * noise
        forest = np.array(tuple(FOREST1)) * (1 - noise2) + np.array(tuple(FOREST2)) * noise2
        col = lawn * (1 - jungle) + forest * jungle
        # sommets des collines un peu plus clairs, creux plus sombres
        col[..., :3] *= (.88 + .07 * np.clip(y, -1.2, 3.5))[..., None]
        bank = (1 - _smoothstep(.2, 2.0, river_d))[..., None]
        col = col * (1 - bank) + np.array(tuple(SAND)) * bank
        depth = np.clip((WATER_Y - y) / 1.0, 0, 1)[..., None]     # lit : plus sombre en profondeur
        col = col * (1 - depth) + np.array([.08, .3, .42, 1]) * depth
        edge = _smoothstep(F - 3.5, F - 1.5, rr)[..., None]
        col = col * (1 - edge) + np.array([.34, .34, .4, 1]) * edge
        col[..., 3] = 1
        NR, NA = rr.shape
        idx = np.arange(NR * NA).reshape(NR, NA)
        a, b_, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
        tris = np.stack([a, c, b_, b_, c, d], -1).reshape(-1)
        verts = np.stack([x, y, z], -1).reshape(-1, 3)
        MeshBuilder().add_raw(verts, tris, norms.reshape(-1, 3), col.reshape(-1, 4)).static(self.root)

    # ================================================================ voies
    def _lane_pieces(self, pts, cut_river=False):
        """Découpe une voie : elle s'arrête au bord des arènes, des bases et du Boss Pit
        (et au-dessus de la rivière si cut_river : un pont y est construit)."""
        def inside(x, z):
            if cut_river and any(polyline_dist(x, z, rp) < rw / 2 + .5 for rp, rw in RIVERS):
                return True
            for a in C.ARENAS:
                if math.hypot(x - a['pos'][0], z - a['pos'][1]) < C.ARENA_RADIUS + 1.8:
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
        for pts, w in dry:
            main = w >= 4.5
            self._ribbon(b, pts, w + 1.3, LANE_EDGE, .04, h=.08)
            self._ribbon(b, pts, w, LANE, .07, h=.08)
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
                k = 1.25
                while k < L:            # joints du dallage
                    b.add('box', (ax + ux * k, .113, az + uz * k), (w, .01, .07), rot=(0, yaw, 0), col=SEAM)
                    k += 2.5
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
            if math.hypot(x - a['pos'][0], z - a['pos'][1]) < C.ARENA_RADIUS + 4:
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
        b, water, rng = self.b, self.water, self.rng
        for pts, w in RIVERS:
            # surface translucide : on devine le lit plus sombre au centre
            self._ribbon(water, pts, w + .8, color.rgba(.3, .74, .9, .62), WATER_Y, h=.03)
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
                            water.add('cyl24', (qx, WATER_Y + .03, qz), (1, .03, 1), col=color.rgb(.25, .6, .25))
                            if rng.random() < .4:
                                water.add('sphere_lo', (qx, WATER_Y + .11, qz), .28, col=color.rgb(1, .6, .8))
        for pts, w in RIVERS:
            if len(pts) > 2:
                self.flows.append(Flow(self.root, [(x, WATER_Y + .05, z) for x, z in pts], count=int(len(pts) * 1.8),
                                       col=color.rgb(.88, .97, 1), size=(.3, .04, .7), speed=3.0,
                                       jitter=w * .32, glow=.8, rng=rng))

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

    # ================================================================ arènes
    def _build_arenas(self):
        R = C.ARENA_RADIUS
        for a in C.ARENAS:
            t = C.TYPES[a['type']]
            x0, z0 = a['pos']
            b, glow = self.b, self.glow
            b.add('cyl_hi', (x0, .03, z0), ((R + 3.6) * 2, .06, (R + 3.6) * 2), col=STONE)
            # rebord segmenté aux couleurs du type
            n = 40
            for i in range(n):
                ang = i * 360 / n
                x, z = polar(ang, R + 1.7, x0, z0)
                col = t['color'] if i % 2 == 0 else lerp(t['color'], color.white, .45)
                b.add('box', (x, .1, z), (2 * math.pi * (R + 1.7) / n * .92, .14, 2.1), rot=(0, ang, 0), col=col)
            b.add('ring_97', (x0, .1, z0), ((R + .55) * 2, .16, (R + .55) * 2), col=color.white)
            # terrain : cercles, rayons, damier et emblème peint au centre
            b.add('cyl_hi', (x0, .07, z0), (R * 2, .1, R * 2), col=t['floor'])
            for i in range(24):
                ang = i * 15
                x, z = polar(ang, R * .78, x0, z0)
                col = lerp(t['floor'], t['light'], .22 if i % 2 else .08)
                b.add('box', (x, .125, z), (2 * math.pi * R * .78 / 24 * .95, .01, R * .34), rot=(0, ang, 0), col=col)
            for rr_ in (R * .95, R * .6, R * .3):
                b.add('ring_97', (x0, .13, z0), (rr_ * 2, .02, rr_ * 2), col=lerp(t['light'], color.white, .6))
            for i in range(12):
                ang = i * 30
                x, z = polar(ang, R * .62, x0, z0)
                b.add('box', (x, .132, z), (.1, .01, R * .64), rot=(0, ang, 0), col=lerp(t['light'], color.white, .5))
            b.add('cyl_hi', (x0, .12, z0), (R * .58, .02, R * .58), col=lerp(t['floor'], t['light'], .35))
            emb = MeshBuilder()
            add_emblem(emb, a['type'], (0, 0, 0), R * .15)
            emb.entity(parent=self.root, emissive=.55, position=(x0, .16, z0), rotation_x=90, scale=(1, 1, .03))
            # pylônes lumineux autour (jamais sur une voie)
            for i in range(10):
                ang = i * 36 + 18
                x, z = polar(ang, R + 4.4, x0, z0)
                if not self._clear_of_lanes(x, z, 1.6):
                    continue
                b.add('cyl8', (x, 1.4, z), (.9, 2.8, .9), col=color.rgb(.92, .93, .95))
                b.add('cyl8', (x, 2.1, z), (1.0, .35, 1.0), col=t['color'])
                b.add('cone8', (x, 3.15, z), (1.1, .5, 1.1), col=t['dark'])
                glow.add('sphere_lo', (x, 3.7, z), .5, col=t['light'])
                self.block(x, z, .6)
            self._arena_stands(a, t, x0, z0, R)
            self._arena_props(a['type'], x0, z0, R)

    def _arena_stands(self, a, t, x0, z0, R):
        """Petites tribunes courbes autour de l'arène, là où aucune voie ne passe."""
        b, rng = self.b, self.rng
        cands = []
        for i in range(16):
            ang = i * 22.5
            x, z = polar(ang, R + 7, x0, z0)
            if math.hypot(x, z) > F - 8:
                continue
            d = min(polyline_dist(x, z, pts) - w / 2 for pts, w in LANES)
            cands.append((d, ang))
        cands.sort(reverse=True)
        chosen = []
        for d, ang in cands:
            if d > 6 and all(abs((ang - c + 180) % 360 - 180) > 80 for c in chosen):
                chosen.append(ang)
            if len(chosen) == 2:
                break
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

    def _arena_props(self, k, x0, z0, R):
        """Décor typique de chaque arène, planté à l'extérieur."""
        b, glow, rng = self.b, self.glow, self.rng
        for i in range(14):
            ang = i * (360 / 14) + rng.uniform(-6, 6)
            rr = R + 8.5 + rng.uniform(0, 2.5)
            x, z = polar(ang, rr, x0, z0)
            if not self._clear_of_lanes(x, z, 2) or self.blocked(x, z, 1.5) or math.hypot(x, z) > F - 5:
                continue
            if k == 'roche':
                for _ in range(3):
                    self._rock(b, x + rng.uniform(-1, 1), z + rng.uniform(-1, 1), rng.uniform(.8, 1.8), moss=.2)
                b.add('cone4', (x, 1.8, z), (2.2, 3.6, 2), rot=(0, rng.uniform(0, 90), 0), col=color.rgb(.62, .5, .38))
            elif k == 'plante':
                b.add('sphere', (x, .9, z), (2.6, 1.9, 2.6), col=color.rgb(.2, .55, .22))
                for _ in range(4):
                    glow.add('sphere_lo', (x + rng.uniform(-1, 1), 1.7, z + rng.uniform(-1, 1)), .32,
                             col=rng.choice((color.rgb(1, .45, .6), color.rgb(1, .9, .3), color.white)))
            elif k == 'electrik':
                b.add('cyl8', (x, 1.9, z), (.6, 3.8, .6), col=color.rgb(.4, .42, .45))
                for j in range(3):
                    b.add('ring_thin', (x, 1.4 + j * .8, z), (1.3 - j * .2, .18, 1.3 - j * .2), col=color.rgb(.75, .62, .2))
                glow.add('sphere', (x, 4.1, z), 1.0, col=color.rgb(1, .95, .45))
            elif k == 'eau':
                b.add('cyl24', (x, .25, z), (3.6, .5, 3.6), col=color.rgb(.72, .75, .8))
                self.water.add('cyl24', (x, .5, z), (3.0, .05, 3.0), col=WATER)
                glow.add('cyl8', (x, 1.1, z), (.35, 1.4, .35), col=color.rgb(.75, .92, 1))
                glow.add('sphere_lo', (x, 1.9, z), (.9, .5, .9), col=color.rgb(.75, .92, 1))
            elif k == 'feu':
                b.add('cyl8', (x, .55, z), (1.5, 1.1, 1.5), col=color.rgb(.3, .25, .25))
                b.add('ring_thin', (x, 1.1, z), (1.6, .2, 1.6), col=color.rgb(.2, .17, .17))
                glow.add('cone', (x, 1.9, z), (1.2, 1.7, 1.2), col=color.rgb(1, .5, .1))
                glow.add('cone', (x, 1.7, z), (.7, 1.3, .7), col=color.rgb(1, .85, .2))
            self.block(x, z, 1.4)

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
            b.add('box', (bx, .165, bz + 1.4), (5.2, .03, 2.8), col=tc)
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
        for i in range(8):                # obélisques
            ang = i * 45 + 22.5
            x, z = polar(ang, R + 2.2)
            b.add('box', (x, 2.2, z), (1.3, 4.4, 1.3), rot=(0, ang, 0), col=color.rgb(.28, .26, .34))
            b.add('cone4', (x, 4.9, z), (1.5, 1, 1.5), rot=(0, ang + 45, 0), col=color.rgb(.22, .2, .28))
            glow.add('cone4', (x, 6.3, z), (.7, .9, .7), col=purple)
            glow.add('cone4', (x, 5.6, z), (.7, .5, .7), rot=(180, 0, 0), col=purple)
            self.block(x, z, .9)
        for ang in (0, 90, 180, 270):     # arches aux quatre entrées
            x, z = polar(ang, R + 3.3)
            for s in (-1, 1):
                sx, sz = polar(ang + 90, 3.6 * s)
                b.add('box', (x + sx, 2.8, z + sz), (1.1, 5.6, 1.4), rot=(0, ang, 0), col=color.rgb(.33, .31, .4))
                self.block(x + sx, z + sz, .75)
            b.add('box', (x, 5.9, z), (8.4, .9, 1.6), rot=(0, ang, 0), col=color.rgb(.3, .28, .37))
            ox, oz = polar(ang, -.85)
            glow.add('box', (x + ox, 5.9, z + oz), (6, .25, .1), rot=(0, ang, 0), col=purple)

    # ================================================================ camps
    def _build_camps(self):
        b, glow, rng = self.b, self.glow, self.rng
        for camp in C.CAMPS:
            x0, z0 = camp['pos']
            b.add('cyl24', (x0, .02, z0), (11, .04, 10), col=color.rgb(.5, .5, .3))
            b.add('cyl24', (x0, .03, z0), (8, .04, 7.4), col=color.rgb(.56, .5, .34))
            col = C.BUFFS[camp['buff']]['color'] if camp.get('buff') else color.rgb(.85, .85, .85)
            for i in range(7):
                ang = i * 360 / 7 + 10
                x, z = polar(ang, 5.4, x0, z0)
                self._rock(b, x, z, rng.uniform(.45, .7), moss=.5)
            glow.add('ring_97', (x0, .07, z0), (3.2, .04, 3.2), col=col)
            # icône flottante au-dessus du camp, comme sur la carte
            glow.add('ring_thin', (x0, 6.5, z0), (2.4, .25, 2.4), col=col)
            glow.add('sphere_lo', (x0, 6.5, z0), .8, col=col)
            b.add('cyl8', (x0, 6.5, z0), (2.2, .12, 2.2), col=color.rgb(.12, .12, .16))

    # ================================================================ jungle
    def _tree(self, b, x, z, s, kind):
        rng = self.rng
        bark = color.rgb(.42, .28, .16)
        if kind == 'broadleaf':
            b.add('cyl', (x, 1.1 * s, z), (.55 * s, 2.2 * s, .55 * s), rot=(rng.uniform(-5, 5), 0, rng.uniform(-5, 5)),
                  col=bark, grad=.35)
            g = rng.choice(TREE_GREENS)
            b.add('blob', (x, 3.0 * s, z), (3.5 * s, 2.8 * s, 3.5 * s), col=g, wobble=.16, grad=.45)
            for i in range(3):
                ox, oz = polar(i * 120 + rng.uniform(-30, 30), 1.25 * s)
                b.add('blob', (x + ox, (2.5 + rng.uniform(0, .8)) * s, z + oz), (2.1 * s, 1.8 * s, 2.1 * s),
                      col=shade(g, rng.uniform(.85, 1.1)), wobble=.18, grad=.45)
            b.add('blob', (x - .2 * s, 3.95 * s, z + .2 * s), (2.1 * s, 1.5 * s, 2.1 * s), col=shade(g, 1.2),
                  wobble=.16, grad=.3)
            return 1.0 * s
        if kind == 'conifer':
            b.add('cyl', (x, .8 * s, z), (.45 * s, 1.6 * s, .45 * s), col=color.rgb(.4, .26, .15), grad=.35)
            g = color.rgb(.1, .36 + rng.uniform(-.04, .04), .2)
            for i, (r, y) in enumerate(((3.0, 2.2), (2.3, 3.5), (1.6, 4.6), (1.0, 5.5))):
                b.add('cone', (x, y * s, z), (r * s, 1.9 * s, r * s), rot=(0, rng.uniform(0, 36), 0),
                      col=shade(g, 1 + i * .08), wobble=.06, grad=.4)
            return .9 * s
        if kind == 'tropical':
            b.add('cyl', (x, 1.8 * s, z), (.45 * s, 3.6 * s, .45 * s), rot=(rng.uniform(-6, 6), 0, rng.uniform(-6, 6)),
                  col=color.rgb(.5, .36, .22), grad=.3)
            g = rng.choice(TREE_GREENS)
            for i in range(7):
                ang = i * 360 / 7 + rng.uniform(-10, 10)
                ox, oz = polar(ang, 1.3 * s)
                b.add('blob', (x + ox, 3.55 * s, z + oz), (1.1 * s, .35 * s, 2.7 * s), rot=(20, ang, 0), col=g,
                      wobble=.1, grad=.3)
            b.add('blob', (x, 3.9 * s, z), 1.5 * s, col=shade(g, 1.15), wobble=.15, grad=.35)
            return .8 * s
        g = color.rgb(.2, .5 + rng.uniform(-.06, .06), .2)       # buisson fleuri
        b.add('blob', (x, .6 * s, z), (2.8 * s, 1.8 * s, 2.8 * s), col=g, wobble=.2, grad=.45)
        b.add('blob', (x + .6 * s, 1.05 * s, z - .3 * s), (1.7 * s, 1.3 * s, 1.7 * s), col=shade(g, 1.15),
              wobble=.2, grad=.35)
        if rng.random() < .6:
            fc = rng.choice((color.rgb(1, .4, .55), color.rgb(1, .9, .3), color.white, color.rgb(.7, .5, 1)))
            for _ in range(5):
                ox, oz = polar(rng.uniform(0, 360), rng.uniform(.4, 1.2) * s)
                b.add('sphere_lo', (x + ox, 1.3 * s, z + oz), .22, col=fc)
        return 1.2 * s

    def _outcrop(self, b, x0, z0):
        """Massif rocheux, parfois avec des ruines de pierre."""
        rng = self.rng
        for _ in range(rng.randint(4, 7)):
            ox, oz = rng.uniform(-3, 3), rng.uniform(-3, 3)
            s = rng.uniform(1.2, 2.6)
            rot = (rng.uniform(-10, 10), rng.uniform(0, 180), rng.uniform(-10, 10))
            b.add('blob', (x0 + ox, s * .75, z0 + oz), (s * 1.9, s * 2.1, s * 1.7), rot=rot,
                  col=shade(ROCK, rng.uniform(.8, 1.1)), wobble=.22, grad=.45)
            if rng.random() < .5:
                b.add('blob', (x0 + ox, s * 1.72, z0 + oz), (s * 1.1, s * .35, s * 1.0), rot=rot, col=MOSS,
                      wobble=.2, grad=.2)
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
        self.block(x0, z0, 3.6)
        self.block(x0 + 3, z0, 1.6)

    def _build_jungle(self):
        rng = self.rng
        b = self.b
        # massifs rocheux
        rocks = []
        for _ in range(600):
            if len(rocks) >= 22:
                break
            a, r = rng.uniform(0, 360), math.sqrt(rng.random()) * (F - 10)
            x, z = polar(a, r)
            if self._open_space(x, z, 3) and all(math.hypot(x - rx, z - rz) > 20 for rx, rz in rocks):
                self._outcrop(b, x, z)
                rocks.append((x, z))
        # arbres
        S = C.QUALITY['tree_spacing']
        n = int(F / S)
        kinds = ['broadleaf'] * 50 + ['conifer'] * 18 + ['tropical'] * 14 + ['bush'] * 18
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x = i * S + rng.uniform(-S * .38, S * .38)
                z = j * S + rng.uniform(-S * .38, S * .38)
                if math.hypot(x, z) > F - 3 or not self._open_space(x, z) or self.blocked(x, z, 1.2):
                    continue
                s = rng.uniform(.85, 1.35)
                r = self._tree(b, x, z, s, rng.choice(kinds))
                self.block(x, z, r)
                if rng.random() < .5:      # sous-bois
                    for _ in range(rng.randint(2, 4)):
                        ox, oz = polar(rng.uniform(0, 360), rng.uniform(1.2, 2.2))
                        ang = rng.uniform(0, 360)
                        b.add('box', (x + ox, .3, z + oz), (.4, .04, 1.2), rot=(-35, ang, 0), col=color.rgb(.2, .5, .2))
                if rng.random() < .06:
                    ox, oz = polar(rng.uniform(0, 360), 1.8)
                    b.add('cyl6', (x + ox, .2, z + oz), (.18, .4, .18), col=color.rgb(.95, .92, .85))
                    b.add('dome', (x + ox, .35, z + oz), (.6, .4, .6), col=color.rgb(.9, .2, .15))

        # herbes et fleurs sur les pelouses
        for _ in range(C.QUALITY['grass']):
            a, r = rng.uniform(0, 360), math.sqrt(rng.random()) * (F - 4)
            x, z = polar(a, r)
            if not self._clear_of_lanes(x, z, .6) or self.blocked(x, z, .3) or self._inside_open_disc(x, z):
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

    def in_river(self, x, z):
        i, j = self.cell_of(x, z)
        return bool(self.river[i, j])

    def update(self, dt, focus=None):
        for f in self.flows:
            f.update(dt, focus)
