"""Décor des cinq arènes : chacune a son thème, reconnaissable au premier coup d'œil.

  roche    : perchée sur un plateau de grès (falaises en colonnes, escalier et rampes : voir
             Stadium._build_plateaus), sol de terre battue en grandes dalles, bannières des équipes
  plante   : jardin (pelouse, allée, mosaïque de pétales, fleurs géantes, cerisiers) sous une serre
  electrik : centrale électrique (plate-forme d'acier en secteurs, anneau blindé et voyants bleus,
             trois tours Tesla reliées par des arcs électriques, générateurs et pylônes)
  eau      : temple aquatique (mosaïque de vagues, bassins, canal, colonnade, fontaines, coraux)
  feu      : forge volcanique (plaques de basalte fendues de lave, douve de lave, orgues de basalte,
             mares de lave, braseros, petit volcan)

Chaque arène garde un sol plat (on y combat) et le cercle de capture dessiné par la partie ;
le décor qui bloque le passage est posé autour, jamais sur les voies. Chaque voie qui
arrive dans l'arène passe entre deux piliers aux couleurs du thème (ou par un escalier).
"""
import math
import random

import numpy as np
from scipy.spatial import Voronoi
from ursina import color

from game import config as C
from game.world.emblems import add_emblem
from game.world.geometry import ROCKS, MeshBuilder, add_hex_band, add_hex_slab, glowing
from game.world.stadium import BASALTS, LANES, SAND_TOP, polyline_dist


def rgb(r, g, b):
    return color.rgb(r, g, b)


def shade(c, f):
    return color.rgb(min(1, c[0] * f), min(1, c[1] * f), min(1, c[2] * f))


def polar(a, r, x0=0.0, z0=0.0):
    a = math.radians(a)
    return x0 + math.sin(a) * r, z0 + math.cos(a) * r


class ArenaDecor:
    """Construit le décor d'une arène dans les constructeurs du stade (st.b, st.glow, st.water)."""

    def __init__(self, st, cfg):
        self.st, self.cfg = st, cfg
        self.b, self.glow, self.water, self.rng = st.b, st.glow, st.water, st.rng
        self.x0, self.z0 = cfg['pos']
        self.R = C.ARENA_RADIUS
        self.t = C.TYPES[cfg['type']]
        self.y0 = st.arena_floor(cfg['key'])          # hauteur du sol (arène perchée)
        self.gates = self._entrances()

    # ------------------------------------------------------------ outils
    def _entrances(self):
        """Angles (vus du centre) où une voie entre dans l'arène, et largeur de la voie."""
        r = self.R + 4.5
        hits = []
        for k in range(180):
            ang = k * 2
            x, z = polar(ang, r, self.x0, self.z0)
            w = next((w for pts, w in LANES if polyline_dist(x, z, pts) < w / 2 + .1), None)
            hits.append((ang, w))
        gates, group = [], []
        start = next((i for i, (_, w) in enumerate(hits) if w is None), 0)
        for i in range(180):
            ang, w = hits[(start + i) % 180]
            if w is not None:
                group.append((ang, w))
            elif group:
                a0 = group[0][0]
                mid = (a0 + ((group[-1][0] - a0) % 360) / 2) % 360
                gates.append((mid, max(g[1] for g in group)))
                group = []
        return gates

    @staticmethod
    def lane_gap(x, z):
        """Distance au bord de la voie la plus proche."""
        return min(polyline_dist(x, z, pts) - w / 2 for pts, w in LANES)

    def near_gate(self, ang, margin=14):
        return any(abs((ang - g + 180) % 360 - 180) < margin for g, _ in self.gates)

    def spots(self, n, rmin, rmax, clear, radius, step=None, jitter=6, offset=0.0):
        """Emplacements libres autour de l'arène (hors voies, murs, tribunes et portiques)."""
        out = []
        step = step or 360 / n
        for i in range(n):
            ang = offset + i * step + self.rng.uniform(-jitter, jitter)
            r = self.rng.uniform(rmin, rmax)
            x, z = self.hpolar(ang, r)
            if self.near_gate(ang, 10) or not self.st._clear_of_lanes(x, z, clear):
                continue
            if self.st.blocked(x, z, radius) or math.hypot(x, z) > C.FIELD_RADIUS - 5:
                continue
            out.append((x, z, ang))
        return out

    def disc(self, b, r, y, h, col, prim='cyl_hi'):
        """Sol de l'arène : hexagonal (les petits médaillons du centre restent ronds)."""
        if r >= 5:
            add_hex_slab(b, self.x0, y, self.z0, r, h, col)
        else:
            b.add(prim, (self.x0, y, self.z0), (r * 2, h, r * 2), col=col)

    def ring(self, b, r, y, h, col, prim='ring_97'):
        if r >= 5:
            add_hex_band(b, self.x0, y, self.z0, r + .35, r - .35, h, col)
        else:
            b.add(prim, (self.x0, y, self.z0), (r * 2, h, r * 2), col=col)

    def hpolar(self, ang, r):
        """Point à l'angle `ang` sur le contour hexagonal de « rayon » r (autour du centre de l'arène)."""
        return polar(ang, r * (C.hex_factor(ang) if r >= 5 else 1), self.x0, self.z0)

    def hex_tiles(self, b, size, y, h, col_fn, r_in=0.0, r_out=None, gap=.9, jitter=0.0, prim='cyl6'):
        """Pavage de dalles hexagonales (ou irrégulières avec `jitter`) sur l'anneau [r_in, r_out]."""
        rng = self.rng
        r_out = self.R if r_out is None else r_out
        dx, dz = size * math.sqrt(3), size * 1.5
        n = int(r_out / dz) + 2
        for j in range(-n, n + 1):
            for i in range(-n, n + 1):
                x = i * dx + (j % 2) * dx / 2
                z = j * dz
                d = math.hypot(x, z)
                if not C.in_arena(x, z, r_out - size * .6) or d < r_in + size * .6:
                    continue
                s = size * 2 * gap * (1 - rng.uniform(0, jitter))
                ox = rng.uniform(-jitter, jitter) * size
                oz = rng.uniform(-jitter, jitter) * size
                b.add(prim, (self.x0 + x + ox, y, self.z0 + z + oz), (s, h, s),
                      rot=(0, 30 + (rng.uniform(-25, 25) if jitter else 0), 0), col=col_fn(x, z))

    def paving(self, r_out, cell, y, col_fn, gap=.12, r_in=0.0, jitter=.38, b=None):
        """Dallage naturel : pierres irrégulières (cellules de Voronoï) séparées par des joints où
        l'on voit le sol dessous. Chaque pierre est un peu plus sombre sur ses bords."""
        rng = self.rng
        n = int(r_out / cell) + 2
        pts = np.array([(i * cell + (j % 2) * cell / 2 + rng.uniform(-jitter, jitter) * cell,
                         j * cell * .87 + rng.uniform(-jitter, jitter) * cell)
                        for j in range(-n, n + 1) for i in range(-n, n + 1)])
        vor = Voronoi(pts)
        verts, tris, cols = [], [], []
        for k, (px, pz) in enumerate(pts):
            reg = vor.regions[vor.point_region[k]]
            if not reg or -1 in reg:
                continue
            poly = vor.vertices[reg]
            if not all(C.in_arena(vx, vz, r_out) for vx, vz in poly) or math.hypot(px, pz) < r_in:
                continue
            c = poly.mean(0)
            poly = poly[np.argsort(np.arctan2(poly[:, 1] - c[1], poly[:, 0] - c[0]))]
            size = max(float(np.linalg.norm(poly - c, axis=1).mean()), .1)
            poly = c + (poly - c) * (1 - gap / size)
            col = tuple(col_fn(px, pz))[:3]
            yy = y + self.y0 + rng.uniform(0, .025)
            base = len(verts)
            verts.append((self.x0 + c[0], yy + .015, self.z0 + c[1]))
            cols.append(col + (1,))
            for vx, vz in poly:
                verts.append((self.x0 + vx, yy, self.z0 + vz))
                cols.append(tuple(v * .86 for v in col) + (1,))
            m = len(poly)
            for i in range(m):
                tris += [base, base + 1 + (i + 1) % m, base + 1 + i]
        (b or self.b).add_raw(np.array(verts), np.array(tris), np.tile((0.0, 1.0, 0.0), (len(verts), 1)), np.array(cols))

    def outward(self):
        """Angle qui s'éloigne du centre de la carte (l'arrière de l'arène)."""
        return math.degrees(math.atan2(self.x0, self.z0))

    def emblem(self, s=None, y=.17, col=None, emissive=.6):
        emb = MeshBuilder()
        add_emblem(emb, self.cfg['type'], (0, 0, 0), s or self.R * .17, col=col)
        emb.entity(parent=self.st.root, emissive=emissive, position=(self.x0, y + self.y0, self.z0), rotation_x=90,
                   scale=(1, 1, .03))

    def gate(self, build_post, build_top=None, height=4.2):
        """Entrée de chaque voie : deux piliers au thème de l'arène, de part et d'autre (pas de
        traverse au-dessus : elle cacherait les Pokémon qui passent dessous)."""
        r = self.R + 4.6
        for ang, w in self.gates:
            cx, cz = self.hpolar(ang, r)
            tx, tz = math.cos(math.radians(ang)), -math.sin(math.radians(ang))   # tangente
            half = w / 2 + 1.5
            for s in (-1, 1):
                px, pz = cx + tx * s * half, cz + tz * s * half
                build_post(px, pz, ang)
                self.st.block(px, pz, .8)
            if build_top is not None:
                build_top(cx, cz, ang, half * 2 + 1.2, height)

    # ------------------------------------------------------------ construction
    def build(self):
        getattr(self, 'build_' + self.cfg['type'])()

    # ================================================================ ROCHE
    def build_roche(self):
        """Arène perchée sur un plateau de grès (voir Stadium._build_plateaus) : sol de terre battue
        couvert de grandes dalles irrégulières, bordure de moellons, bannières des équipes au fond."""
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        sand, dark = rgb(.76, .64, .46), rgb(.5, .41, .3)
        self.disc(b, R + 3.1, .03, .06, sand)
        self.disc(b, R + .3, .06, .06, dark)                  # joints entre les dalles
        stones = [rgb(.8, .68, .5), rgb(.74, .61, .44), rgb(.84, .74, .56), rgb(.7, .56, .41), rgb(.78, .64, .46)]
        self.paving(R - .2, 2.3, .1, lambda x, z: shade(rng.choice(stones), rng.uniform(.9, 1.06)), gap=.13, r_in=2.6)
        for _ in range(10):                                   # fissures
            a, r = rng.uniform(0, 360), rng.uniform(4, R - 2)
            x, z = self.hpolar(a, r)
            b.add('box', (x, .145, z), (.07, .01, rng.uniform(1.2, 2.4)), rot=(0, rng.uniform(0, 180), 0), col=dark)
        # médaillon central taillé
        self.disc(b, 2.9, .09, .12, rgb(.6, .49, .35))
        self.ring(b, 2.6, .16, .02, rgb(.9, .8, .6), 'ring_thin')
        self.emblem(col=rgb(.95, .78, .45))
        # bordure de gros moellons irréguliers
        n = 40
        for i in range(n):
            ang = i * 360 / n + rng.uniform(-1.5, 1.5)
            x, z = self.hpolar(ang, R + 1.1)
            ang = C.hex_normal(ang)                 # bordure alignée sur le côté de l'hexagone
            c = shade(rgb(.66, .56, .44), rng.uniform(.85, 1.1))
            b.add('box', (x, .12, z), (2 * math.pi * (R + 1.1) / n * rng.uniform(.8, .95), .2, rng.uniform(1.2, 1.6)),
                  rot=(rng.uniform(-3, 3), ang + rng.uniform(-4, 4), rng.uniform(-2, 2)), col=c)
        # bannières des deux équipes au fond de l'arène, sur le rebord du plateau
        back = self.outward()
        for side, team in ((-1, 'rouge'), (1, 'bleu')):
            ang = back + side * 24
            x, z = self.hpolar(ang, R + 2.3)
            tc = C.TEAMS[team]['color']
            for s_ in (-1, 1):
                px, pz = polar(ang + 90, 2.1 * s_, x, z)
                b.add('prism6', (px, 1.8, pz), (.7, 3.6, .7), rot=(0, ang, 0), col=rgb(.55, .45, .34), grad=.3)
                self.st.block(px, pz, .45)
            b.add('box', (x, 2.5, z), (4.6, 2.2, .25), rot=(0, ang, 0), col=shade(tc, .8))
            b.add('box', (x, 3.75, z), (5.0, .35, .4), rot=(0, ang, 0), col=rgb(.3, .26, .22))
            fx, fz = polar(ang, -.15, x, z)
            b.add('cyl24', (fx, 2.5, fz), (1.5, .08, 1.5), rot=(90, ang, 0), col=rgb(.97, .97, .97))
            b.add('box', (fx, 2.84, fz), (1.52, .7, .1), rot=(0, ang, 0), col=tc)
            b.add('box', (fx, 2.5, fz), (1.55, .12, .11), rot=(0, ang, 0), col=rgb(.1, .1, .12))
            glow.add('cyl8', polar(ang, -.22, x, z)[:1] + (2.5,) + polar(ang, -.22, x, z)[1:], (.35, .06, .35),
                     rot=(90, ang, 0), col=color.white)
            glow.add('box', (x, 1.3, z), (4.4, .12, .05), rot=(0, ang, 0), col=C.TEAMS[team]['light'])
        # quelques rochers et touffes sèches sur le rebord
        for x, z, ang in self.spots(10, R + 1.9, R + 2.6, 1.2, .5):
            if abs((ang - back + 180) % 360 - 180) < 40:
                continue
            t = rng.uniform(.35, .6)
            b.add(rng.choice(ROCKS), (x, t * .3, z), (t * 1.6, t * 1.1, t * 1.4), rot=(0, rng.uniform(0, 360), 0),
                  col=shade(rgb(.72, .58, .42), rng.uniform(.85, 1.05)), grad=.3, cap=(SAND_TOP, .5))

    # ================================================================ PLANTE
    def build_plante(self):
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        self.disc(b, R + 3.6, .03, .06, rgb(.62, .66, .52))
        self.disc(b, R + .3, .07, .08, rgb(.34, .6, .27))
        for _ in range(160):                                  # herbe plus claire et plus sombre
            a, r = rng.uniform(0, 360), math.sqrt(rng.random()) * (R - .5)
            x, z = self.hpolar(a, r)
            b.add('cyl8', (x, .115, z), (rng.uniform(1.2, 2.4), .01, rng.uniform(1.2, 2.4)),
                  col=rng.choice((rgb(.37, .63, .29), rgb(.32, .57, .25))))
        # allée circulaire et allées en croix : terre battue et pierres plates
        path = rgb(.8, .77, .66)
        dirt = rgb(.6, .5, .36)
        self.ring(b, R * .8 - .62, .12, .02, dirt, 'ring')
        for ang in (45, 135, 225, 315):
            x, z = self.hpolar(ang, 3.6 + 1.95)
            b.add('box', (x, .12, z), (1.3, .02, 5.2), rot=(0, ang, 0), col=dirt)
        for rr, n in ((R * .8, 34), (R * .8 - 1.25, 30)):
            for i in range(n):
                x, z = self.hpolar(i * 360 / n + rng.uniform(-2, 2), rr)
                b.add('cyl8', (x, .13, z), (1.05, .06, .85), rot=(0, rng.uniform(0, 90), 0), col=shade(path, rng.uniform(.9, 1.05)))
        for ang in (45, 135, 225, 315):
            for k in range(4):
                x, z = self.hpolar(ang + rng.uniform(-3, 3), 3.6 + k * 1.3)
                b.add('cyl8', (x, .13, z), (1.0, .06, .8), rot=(0, rng.uniform(0, 90), 0), col=shade(path, rng.uniform(.9, 1.05)))
        # massifs de fleurs sur la pelouse
        petal_cols = (rgb(1, .45, .62), rgb(1, .92, .35), rgb(.98, .98, 1), rgb(.72, .5, 1), rgb(1, .6, .3))
        for i in range(8):
            ang = i * 45 + 22.5
            x, z = self.hpolar(ang, R * .55)
            c = petal_cols[i % len(petal_cols)]
            for _ in range(9):
                ox, oz = rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1)
                b.add('sphere_lo', (x + ox, .2, z + oz), (.32, .12, .32), col=c)
                b.add('cone6', (x + ox, .18, z + oz), (.18, .3, .18), col=rgb(.25, .55, .2))
        # grande fleur en mosaïque au centre
        for i in range(8):
            ang = i * 45
            x, z = self.hpolar(ang, 1.9)
            b.add('sphere', (x, .12, z), (1.4, .06, 2.6), rot=(0, ang, 0), col=rgb(1, .55, .7) if i % 2 else rgb(1, .72, .82))
        self.disc(b, 1.3, .15, .04, rgb(1, .86, .3), 'cyl24')
        self.emblem(s=R * .1, y=.2, col=rgb(.25, .7, .25))
        # bordure : haie basse fleurie (coupée aux entrées)
        n = 40
        for i in range(n):
            ang = i * 360 / n
            if self.near_gate(ang, 12):
                continue
            x, z = self.hpolar(ang, R + 1.4)
            ang = C.hex_normal(ang)                 # bordure alignée sur le côté de l'hexagone
            b.add('blob', (x, .35, z), (2.3, .8, 1.3), rot=(0, ang + 90, 0), col=shade(rgb(.2, .5, .2), rng.uniform(.9, 1.1)),
                  wobble=.2, grad=.4)
            if i % 2:
                b.add('sphere_lo', (x, .75, z), .25, col=rng.choice(petal_cols))

        def post(x, z, ang):
            b.add('cyl8', (x, 2.1, z), (.55, 4.2, .55), col=rgb(.5, .35, .2))
            for k in range(6):                                 # lierre enroulé
                b.add('blob', (x + math.sin(k * 2.1) * .35, .5 + k * .65, z + math.cos(k * 2.1) * .35), (.7, .5, .7),
                      col=shade(rgb(.2, .55, .22), rng.uniform(.9, 1.15)), wobble=.2)
            c = rng.choice(petal_cols)
            for p in range(6):                                 # fleur au sommet
                px, pz = polar(p * 60, .5, x, z)
                b.add('sphere', (px, 4.4, pz), (.8, .16, .5), rot=(0, p * 60 + 90, 0), col=c)
            glow.add('sphere_lo', (x, 4.5, z), .35, col=rgb(1, .88, .3))

        self.gate(post)
        # fleurs géantes, cerisiers et champignons
        for x, z, ang in self.spots(10, R + 6, R + 9.5, 2.5, 1.6):
            k = rng.random()
            if k < .4:                                         # fleur géante
                h = rng.uniform(2.6, 3.6)
                c = rng.choice(petal_cols)
                b.add('cyl8', (x, h / 2, z), (.3, h, .3), col=rgb(.25, .6, .22))
                b.add('sphere', (x + .5, h * .45, z), (1.2, .12, .55), rot=(0, 0, 25), col=rgb(.3, .65, .25))
                for p in range(6):
                    px, pz = polar(p * 60, .75, x, z)
                    b.add('sphere', (px, h, pz), (1.1, .2, .7), rot=(0, p * 60 + 90, 0), col=c)
                glow.add('sphere_lo', (x, h + .12, z), .55, col=rgb(1, .88, .3))
                self.st.block(x, z, .8)
            elif k < .75:                                      # cerisier en fleurs
                b.add('cyl', (x, 1.3, z), (.6, 2.6, .6), col=rgb(.42, .28, .2), grad=.3)
                for p in range(4):
                    ox, oz = polar(p * 90 + rng.uniform(-20, 20), 1.0)
                    b.add('blob', (x + ox, 3.0 + rng.uniform(0, .6), z + oz), (2.2, 1.7, 2.2),
                          col=shade(rgb(1, .7, .82), rng.uniform(.92, 1.06)), wobble=.18, grad=.35)
                b.add('blob', (x, 3.8, z), (2.2, 1.5, 2.2), col=rgb(1, .78, .88), wobble=.16)
                for _ in range(5):                             # pétales tombés
                    ox, oz = rng.uniform(-2, 2), rng.uniform(-2, 2)
                    b.add('cyl8', (x + ox, .05, z + oz), (.25, .01, .18), col=rgb(1, .75, .85))
                self.st.block(x, z, .9)
            else:                                              # champignons
                for _ in range(rng.randint(2, 3)):
                    ox, oz = rng.uniform(-1, 1), rng.uniform(-1, 1)
                    h = rng.uniform(.8, 1.6)
                    b.add('cyl8', (x + ox, h / 2, z + oz), (.35, h, .35), col=rgb(.95, .92, .85))
                    b.add('dome', (x + ox, h, z + oz), (1.4 * h, .9 * h, 1.4 * h), col=rgb(.85, .2, .18))
                    for _ in range(4):
                        px, pz = polar(rng.uniform(0, 360), .35 * h, x + ox, z + oz)
                        b.add('sphere_lo', (px, h + .3 * h, pz), .14 * h, col=color.white)
                self.st.block(x, z, 1.3)
        self.greenhouse()

    def greenhouse(self):
        """Serre en demi-dôme : armature de fer blanc au-dessus de la moitié extérieure de l'arène
        (côté opposé au centre de la carte). Les pieds évitent les entrées et les tribunes ; on passe
        dessous librement."""
        b, glow, R = self.b, self.glow, self.R
        rng = random.Random(17)             # tirage à part : ne décale pas le décor des autres arènes
        iron, iron2 = rgb(.9, .93, .88), rgb(.72, .8, .74)
        Rd, Hd = R + 3.0, 10.5
        c = math.degrees(math.atan2(self.x0, self.z0))            # vers l'extérieur de la carte
        stands = self.st.stand_angles.get(self.cfg['key'], [])

        def pt(a, phi):
            p = math.radians(phi)
            x, z = self.hpolar(a, Rd * math.cos(p))
            return x, Hd * math.sin(p), z

        def bar(p, q, w, col):
            mx, my, mz = ((p[i] + q[i]) / 2 for i in range(3))
            flat_ = math.hypot(q[0] - p[0], q[2] - p[2])
            L = math.hypot(flat_, q[1] - p[1])
            b.add('box', (mx, my, mz), (w, w, L), rot=(-math.degrees(math.atan2(q[1] - p[1], flat_)),
                                                        math.degrees(math.atan2(q[0] - p[0], q[2] - p[2])), 0), col=col)

        span = 80
        for k in range(9):                                     # méridiens
            a = c - span + k * span * 2 / 8
            if self.near_gate(a, 16) or any(abs((a - s + 180) % 360 - 180) < 26 for s in stands):
                continue
            pts = [pt(a, phi) for phi in range(0, 91, 10)]
            for p, q in zip(pts, pts[1:]):
                bar(p, q, .22, iron)
            fx, _, fz = pts[0]
            b.add('box', (fx, .35, fz), (.7, .7, .7), rot=(0, a, 0), col=rgb(.45, .5, .46))
            self.st.block(fx, fz, .4)
            for _ in range(3):                                 # plante grimpante au pied
                b.add('blob', (fx + rng.uniform(-.4, .4), rng.uniform(.6, 2.6), fz + rng.uniform(-.4, .4)),
                      (.9, .7, .9), col=shade(rgb(.2, .52, .2), rng.uniform(.9, 1.15)), wobble=.25)
        for phi in (22, 45, 66):                               # parallèles
            pts = [pt(c - span + i * span * 2 / 16, phi) for i in range(17)]
            for p, q in zip(pts, pts[1:]):
                bar(p, q, .14, iron2)
        top = (self.x0, Hd, self.z0)                           # lanterne au sommet
        b.add('cyl16', (top[0], top[1] + .3, top[2]), (1.6, .6, 1.6), col=iron)
        b.add('dome', (top[0], top[1] + .6, top[2]), (1.6, 1.0, 1.6), col=iron2)
        glow.add('sphere_lo', (top[0], top[1] - .2, top[2]), .45, col=rgb(1, .92, .6))
        for k in range(6):                                     # suspensions fleuries
            a = c - span * .8 + k * span * 1.6 / 5
            x, y, z = pt(a, 45)
            b.add('cyl6', (x, y - .7, z), (.05, 1.4, .05), col=iron2)
            b.add('blob', (x, y - 1.6, z), (.9, .7, .9), col=rgb(.22, .55, .22), wobble=.25)
            b.add('sphere_lo', (x, y - 1.3, z), .3, col=rng.choice((rgb(1, .45, .62), rgb(1, .92, .35), rgb(.98, .98, 1))))

    # ================================================================ ELECTRIK
    def build_electrik(self):
        """Centrale électrique : plate-forme d'acier en secteurs, anneau blindé jaune ponctué de
        lumières bleues, trois grandes tours Tesla au fond reliées par des arcs électriques."""
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        yellow, steel, dark = rgb(.9, .72, .16), rgb(.48, .51, .57), rgb(.2, .21, .25)
        blue = rgb(.35, .75, 1)
        self.disc(b, R + 3.6, .03, .06, rgb(.34, .36, .4))
        # anneau blindé : plaques jaunes et acier, voyants bleus
        n = 32
        for i in range(n):
            ang = i * 360 / n
            x, z = self.hpolar(ang, R + 1.45)
            ang = C.hex_normal(ang)                 # bordure alignée sur le côté de l'hexagone
            w = 2 * math.pi * (R + 1.45) / n
            b.add('box', (x, .1, z), (w * .96, .14, 2.0), rot=(0, ang, 0), col=yellow if i % 2 else shade(steel, .9))
            if i % 2 == 0:
                glow.add('box', polar(ang, -.55, x, z)[:1] + (.19,) + polar(ang, -.55, x, z)[1:], (w * .6, .04, .22),
                         rot=(0, ang, 0), col=blue)
        self.disc(b, R + .45, .07, .1, dark)                   # joints entre les plaques
        # plaques d'acier en deux couronnes de secteurs
        verts, tris, cols = [], [], []
        y = self.y0 + .135
        for r0, r1, nsec, off in ((4.6, 8.9, 8, 0), (9.2, R - .05, 8, 22.5)):
            for k in range(nsec):
                a0, a1 = off + k * 360 / nsec + 1.2, off + (k + 1) * 360 / nsec - 1.2
                col = (.47, .5, .56, 1) if k % 2 else (.41, .44, .5, 1)
                base = len(verts)
                m = 10
                for i in range(m + 1):
                    a = a0 + (a1 - a0) * i / m
                    for r in (r0 + .1, r1 - .1):
                        x, z = self.hpolar(a, r)
                        verts.append((x, y, z))
                        cols.append(col)
                for i in range(m):
                    q = base + i * 2
                    tris += [q, q + 1, q + 2, q + 1, q + 3, q + 2]
        b.add_raw(np.array(verts), np.array(tris), np.tile((0.0, 1.0, 0.0), (len(verts), 1)), np.array(cols))
        for k in range(8):                                     # rivets le long des plaques
            for r in (6.7, 11.5):
                x, z = self.hpolar(k * 45 + 22.5 * (r > 9) + 11, r)
                b.add('cyl6', (x, .16, z), (.22, .03, .22), col=rgb(.7, .72, .78))
        add_hex_band(glow, self.x0, .15, self.z0, 9.35, 8.75, .03, blue)                # anneau lumineux intermédiaire
        # plateau central surélevé
        self.disc(b, 4.3, .12, .12, rgb(.56, .59, .65), 'cyl_hi')
        glow.add('ring_thin', (self.x0, .19, self.z0), (7.2, .04, 7.2), col=blue)
        self.disc(b, 3.1, .15, .1, rgb(.26, .28, .33), 'cyl_hi')
        self.emblem(y=.22, emissive=1.0)

        def post(x, z, ang):
            b.add('box', (x, 2.1, z), (.9, 4.2, .9), rot=(0, ang, 0), col=steel)
            b.add('box', (x, .3, z), (1.3, .6, 1.3), rot=(0, ang, 0), col=dark)
            for k in range(3):
                b.add('box', (x, 1.2 + k * 1.1, z), (.95, .25, .95), rot=(0, ang, 0), col=yellow)
            glow.add('box', (x, 4.35, z), (.7, .25, .7), rot=(0, ang, 0), col=blue)

        self.gate(post)
        # trois tours Tesla au fond, reliées par des arcs
        back = self.outward()
        tops = []
        for k, off in enumerate((-38, 0, 38)):
            ang = back + off
            while self.near_gate(ang, 18):
                ang += 8 if off >= 0 else -8
            x, z = self.hpolar(ang, R + 5.6)
            tops.append(self._tesla_tower(x, z, ang, 7.5 if off == 0 else 6.2))
        self.st.arcs.add([(tops[0], tops[1]), (tops[1], tops[2]), (tops[0], tops[2])],
                         ground=[(t, self.hpolar(a, R - 1)) for t, a in
                                 zip(tops, (back - 30, back, back + 30))], y0=self.y0)
        # générateurs et pylônes autour, reliés par des câbles
        pylons = []
        for x, z, ang in self.spots(8, R + 6, R + 9, 2.5, 1.6):
            if abs((ang - back + 180) % 360 - 180) < 60:
                continue
            if rng.random() < .5:                              # pylône en treillis
                for sx in (-1, 1):
                    for sz in (-1, 1):
                        b.add('box', (x + sx * .55, 2.8, z + sz * .55), (.14, 5.8, .14),
                              rot=(sz * 5, 0, -sx * 5), col=rgb(.55, .57, .62))
                for yy in (1.2, 2.6, 4.0):
                    b.add('box', (x, yy, z), (1.3 - yy * .1, .1, .1), rot=(0, ang, 0), col=rgb(.55, .57, .62))
                    b.add('box', (x, yy, z), (.1, .1, 1.3 - yy * .1), rot=(0, ang, 0), col=rgb(.55, .57, .62))
                b.add('box', (x, 5.6, z), (3.0, .16, .16), rot=(0, ang + 90, 0), col=rgb(.5, .52, .58))
                pylons.append((x, z))
                self.st.block(x, z, 1.0)
            else:                                              # générateur
                b.add('box', (x, .9, z), (2.4, 1.8, 1.6), rot=(0, ang, 0), col=rgb(.36, .38, .44))
                b.add('box', (x, 1.9, z), (2.5, .2, 1.7), rot=(0, ang, 0), col=yellow)
                ox, oz = polar(ang, -.82)
                glow.add('box', (x + ox, 1.0, z + oz), (1.4, .5, .05), rot=(0, ang, 0), col=rgb(.55, 1, .7))
                for s_ in (-1, 1):
                    px, pz = polar(ang + 90, s_ * .8, x, z)
                    b.add('cyl8', (px, 2.35, pz), (.3, .7, .3), col=dark)
                    glow.add('sphere_lo', (px, 2.8, pz), .2, col=rgb(1, .9, .3))
                self.st.block(x, z, 1.5)
        for (ax, az), (bx, bz) in zip(pylons, pylons[1:]):     # câbles entre pylônes voisins
            L = math.hypot(bx - ax, bz - az)
            if L < 14:
                b.add('box', ((ax + bx) / 2, 5.3, (az + bz) / 2), (.06, .06, L),
                      rot=(0, math.degrees(math.atan2(bx - ax, bz - az)), 0), col=dark)

    def _tesla_tower(self, x, z, ang, H):
        """Grande tour Tesla : socle à escalier, fût d'acier, bobines violettes, sphère lumineuse.
        Renvoie la position (absolue) de la sphère, d'où partent les arcs."""
        b = self.b
        steel, dark, yellow = rgb(.5, .53, .6), rgb(.24, .25, .3), rgb(.9, .72, .16)
        violet = rgb(.8, .55, 1)
        b.add('box', (x, .6, z), (3.4, 1.2, 3.4), rot=(0, ang, 0), col=dark)
        b.add('box', (x, 1.25, z), (3.5, .12, 3.5), rot=(0, ang, 0), col=yellow)
        sx, sz = polar(ang + 180, 2.1, x, z)                   # petit escalier côté arène
        for k in range(3):
            qx, qz = polar(ang + 180, 2.1 - k * .35, x, z)
            b.add('box', (qx, .2 + k * .35, qz), (1.4, .4, .4), rot=(0, ang, 0), col=shade(yellow, .9))
        b.add('cyl16', (x, 1.3 + H / 2, z), (1.7, H, 1.7), col=steel, grad=.3)
        for k in range(4):                                     # bobines
            b.add('ring_thin', (x, 2.2 + k * (H - 1.8) / 4, z), (2.1, .3, 2.1), col=rgb(.72, .45, .25))
            b.add('ring_thin', (x, 2.45 + k * (H - 1.8) / 4, z), (1.95, .1, 1.95), col=glowing(violet, .8))
        top = 1.3 + H
        b.add('cyl16', (x, top + .2, z), (2.4, .4, 2.4), col=dark)
        b.add('ring', (x, top + .75, z), (3.0, .5, 3.0), col=rgb(.72, .74, .8))
        b.add('sphere', (x, top + 1.3, z), 1.5, col=glowing(rgb(.9, .8, 1), 1))
        glowy = self.st.ground_y(x, z)
        self.st.block(x, z, 1.9)
        return (x, glowy + top + 1.3, z)

        # ================================================================ EAU
    def build_eau(self):
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        marble, deep = rgb(.93, .95, .98), rgb(.12, .38, .7)
        self.disc(b, R + 3.6, .03, .06, marble)
        # canal d'eau autour du terrain (peu profond : on le traverse)
        self.disc(b, R + 2.4, .05, .06, rgb(.2, .45, .7))
        self.st.wb.ring(self.x0, .12, self.z0, R + .7, R + 2.4, depth=.8, speed=.4, hexa=True)
        self.disc(b, R + .7, .08, .1, marble)
        # mosaïque de vagues
        cols = [rgb(.36, .6, .76), rgb(.56, .77, .86), rgb(.86, .91, .93), rgb(.27, .5, .68)]
        r = 3.4
        while r < R:
            n = int(2 * math.pi * r / 1.05)
            for i in range(n):
                ang = i * 360 / n
                x, z = self.hpolar(ang, r)
                w = math.sin(math.radians(ang) * 6 + r * .9)
                c = cols[0] if w < -.3 else cols[1] if w < .3 else cols[2] if w < .8 else cols[3]
                b.add('box', (x, .15, z), (2 * math.pi * r / n * .9, .04, .95), rot=(0, ang, 0), col=c)
            r += 1.08
        # bassins peu profonds
        for k in range(4):
            x, z = self.hpolar(k * 90 + 45, R * .6)
            b.add('cyl24', (x, .16, z), (4.6, .04, 4.6), col=deep)
            self.st.wb.disc(x, .2, z, 2.2, depth=.8, speed=.05)
            b.add('ring_thin', (x, .2, z), (4.8, .1, 4.8), col=marble)
        # tourbillon central
        self.disc(b, 3.2, .14, .06, deep)
        for k in range(3):
            self.ring(b, 1.1 + k * .75, .18, .02, rgb(.6, .9, 1), 'ring_thin')
        self.emblem(col=rgb(.55, .88, 1), emissive=.9)

        def post(x, z, ang):
            b.add('cyl16', (x, .25, z), (1.4, .5, 1.4), col=marble)
            b.add('cyl16', (x, 2.2, z), (.9, 3.9, .9), col=marble)
            b.add('cyl16', (x, 4.2, z), (1.3, .4, 1.3), col=rgb(.3, .6, .9))
            glow.add('sphere', (x, 4.9, z), .8, col=rgb(.6, .92, 1))

        self.gate(post)
        # colonnade
        n = 16
        for i in range(n):
            ang = i * 360 / n + 11
            x, z = self.hpolar(ang, R + 5)
            if self.near_gate(ang, 16) or not self.st._clear_of_lanes(x, z, 1.6) or self.st.blocked(x, z, .8):
                continue
            b.add('cyl16', (x, 1.6, z), (.8, 3.2, .8), col=marble)
            b.add('box', (x, 3.3, z), (1.2, .3, 1.2), rot=(0, ang, 0), col=rgb(.3, .6, .9))
            self.st.block(x, z, .6)
        # fontaines et coraux
        for x, z, ang in self.spots(8, R + 7.5, R + 9.5, 3, 1.8, offset=22):
            if rng.random() < .5:                              # fontaine à étages
                b.add('cyl24', (x, .35, z), (3.4, .7, 3.4), col=marble)
                self.st.wb.disc(x, .66, z, 1.5, depth=.6, speed=.3)
                b.add('cyl16', (x, 1.3, z), (.5, 1.8, .5), col=marble)
                b.add('cyl24', (x, 2.2, z), (1.8, .3, 1.8), col=marble)
                self.st.wb.disc(x, 2.36, z, .75, depth=.5, speed=.5)
                # jet d'eau et nappe qui retombe dans la vasque
                self.st.wb.curtain([(x, 2.4, z), (x, 3.1, z), (x, 3.5, z)], .22, speed=1.4)
                for k in range(6):
                    a = k * 60
                    ox, oz = polar(a, .75)
                    self.st.wb.curtain([(x, 2.36, z), (x + ox * .6, 2.1, z + oz * .6), (x + ox, .9, z + oz)], .5,
                                       alpha=.7, speed=1.0)
                self.st.emitters.append((x, .7, z, 'fall', .5))
                self.st.block(x, z, 1.7)
            else:                                              # massif de coraux
                for _ in range(rng.randint(3, 5)):
                    c = rng.choice((rgb(1, .45, .4), rgb(1, .6, .3), rgb(.85, .4, .9), rgb(1, .75, .8)))
                    ox, oz = rng.uniform(-1, 1), rng.uniform(-1, 1)
                    h = rng.uniform(1, 2)
                    b.add('cyl8', (x + ox, h / 2, z + oz), (.3, h, .3), col=c)
                    for _ in range(3):
                        t = rng.uniform(.3, .9) * h
                        a = rng.uniform(0, 360)
                        bx_, bz_ = polar(a, .35, x + ox, z + oz)
                        b.add('cyl8', (bx_, t + .3, bz_), (.2, .8, .2), rot=(0, a, 35), col=c)
                        b.add('sphere_lo', (bx_, t + .7, bz_), .22, col=shade(c, 1.1))
                b.add('dome', (x + 1.2, 0, z - .8), (1.2, .8, 1.2), col=rgb(1, .88, .78))   # coquillage
                self.st.block(x, z, 1.3)

    # ================================================================ FEU
    def build_feu(self):
        """Forge volcanique : plaques de basalte irrégulières entre lesquelles la lave brille, douve de
        lave franchie par des dalles aux entrées, orgues de basalte, mares de lave et braseros autour."""
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        lava, lava2 = rgb(1, .42, .06), rgb(1, .75, .2)
        self.disc(b, R + 3.6, .03, .06, rgb(.22, .19, .18))
        # douve de lave autour du terrain, franchie par de larges dalles aux entrées
        self.st.wb.ring(self.x0, .075, self.z0, R + 1.5, R + 2.6, kind='lava', speed=.2, hexa=True)
        self.disc(b, R + 1.5, .065, .07, rgb(.17, .15, .15))
        for ang, w in self.gates:
            for k in range(3):
                x, z = self.hpolar(ang, R + 1.6 + k * .6)
                b.add('box', (x, .1, z), (w + 1.2, .12, .66), rot=(0, ang, 0), col=shade(BASALTS[0], rng.uniform(.9, 1.1)))
        # plaques de basalte : la lave brille dans les joints
        self.st.wb.disc(self.x0, .1, self.z0, R + .2, kind='lava', flow=(.2, 0, .3), seg=60, hexa=True)
        self.paving(R - .1, 1.9, .12, lambda x, z: shade(rng.choice(BASALTS), rng.uniform(.7, 1.0)), gap=.17, r_in=3.1)
        # bordure de colonnes de basalte basses (on marche dessus)
        n = 46
        for i in range(n):
            ang = i * 360 / n
            x, z = self.hpolar(ang, R + .75)
            ang = C.hex_normal(ang)                 # bordure alignée sur le côté de l'hexagone
            b.add('prism6', (x, .12, z), (1.15, .24 + rng.uniform(0, .08), 1.15), rot=(0, rng.uniform(0, 60), 0),
                  col=shade(rng.choice(BASALTS), rng.uniform(.8, 1.05)), cap=(rgb(.36, .33, .31), .5))
        self.disc(b, 3.0, .15, .07, rgb(.16, .13, .13))
        self.ring(b, 2.7, .19, .03, lava2, 'ring_thin')
        self.emblem(emissive=1.0)

        def post(x, z, ang):
            for k in range(3):                                 # faisceau de colonnes veinées de lave
                ox, oz = polar(ang + k * 120, .35)
                h = 3.2 + k * .5
                b.add('prism6', (x + ox, h / 2, z + oz), (.75, h, .75), rot=(0, k * 20, 0),
                      col=shade(BASALTS[k % len(BASALTS)], .9), grad=.3)
            glow.add('box', (x, 1.8, z), (.1, 3.2, .8), rot=(0, ang + 45, 0), col=lava)
            glow.add('cone', (x, 4.6, z), (.9, 1.3, .9), col=lava)
            glow.add('cone', (x, 4.45, z), (.5, .9, .5), col=lava2)

        self.gate(post)
        # petit volcan (à l'endroit le plus dégagé)
        best = None
        for k in range(24):
            ang = k * 15
            x, z = self.hpolar(ang, R + 8.5)
            if self.near_gate(ang, 25) or math.hypot(x, z) > C.FIELD_RADIUS - 6 or self.st.blocked(x, z, 3.2):
                continue
            d = min(self.lane_gap(x, z), 12)
            if best is None or d > best[0]:
                best = (d, x, z)
        if best and best[0] > 4:
            _, x, z = best
            b.add('frustum', (x, 2.0, z), (7.5, 4.0, 7.5), col=rgb(.26, .21, .2), grad=.35)
            for k in range(8):                                 # blocs sur les flancs
                a = k * 45 + rng.uniform(-15, 15)
                px, pz = polar(a, 3.2, x, z)
                b.add(rng.choice(ROCKS), (px, .5, pz), (1.6, 1.0, 1.3), rot=(0, a, 0), col=shade(BASALTS[1], .9), grad=.3)
            b.add('cyl16', (x, 4.0, z), (1.9, .12, 1.9), col=rgb(.15, .1, .1))
            glow.add('cyl16', (x, 4.03, z), (1.6, .1, 1.6), col=lava)
            for k in range(5):                                 # coulées de lave
                a = k * 72 + rng.uniform(-15, 15)
                px, pz = polar(a, 1.9, x, z)
                glow.add('box', (px, 2.1, pz), (.35, .1, 3.8), rot=(62, a, 0), col=lava)
            self.st.block(x, z, 3.4)
        # orgues de basalte, mares de lave et braseros
        for x, z, ang in self.spots(11, R + 6, R + 9.5, 2.5, 1.6):
            k = rng.random()
            if k < .45:                                        # orgues de basalte
                for _ in range(rng.randint(4, 7)):
                    h = rng.uniform(1.2, 3.6)
                    ox, oz = rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1)
                    b.add('prism6', (x + ox, h / 2 - .1, z + oz), (1.0, h, 1.0), rot=(rng.uniform(-5, 5), rng.uniform(0, 60), 0),
                          col=shade(rng.choice(BASALTS), rng.uniform(.8, 1.1)), grad=.35, cap=(rgb(.4, .37, .35), .5))
                if rng.random() < .5:
                    glow.add('blob', (x, .15, z + 1.3), (1.4, .1, .9), col=lava, wobble=.3)
                self.st.block(x, z, 1.7)
            elif k < .75:                                      # mare de lave bordée de blocs
                self.st.wb.disc(x, self.st.ground_y(x, z) + .08, z, 1.45, kind='lava', sx=1.2, seg=24)
                self.st.emitters.append((x, .1, z, 'lava', 1.2))
                for p_ in range(7):
                    px, pz = polar(p_ * 51 + rng.uniform(-10, 10), 1.75, x, z)
                    t = rng.uniform(.35, .6)
                    b.add(rng.choice(ROCKS), (px, t * .3, pz), (t * 1.6, t, t * 1.3), rot=(0, rng.uniform(0, 360), 0),
                          col=shade(rng.choice(BASALTS), rng.uniform(.85, 1.1)), grad=.3)
                self.st.block(x, z, 1.6)
            else:                                              # brasero
                b.add('prism6', (x, .8, z), (.8, 1.6, .8), col=rgb(.3, .26, .26))
                b.add('cyl16', (x, 1.75, z), (1.6, .5, 1.6), col=rgb(.22, .18, .18))
                glow.add('cone', (x, 2.5, z), (1.2, 1.7, 1.2), col=lava)
                glow.add('cone', (x, 2.35, z), (.7, 1.3, .7), col=lava2)
                self.st.block(x, z, .9)
