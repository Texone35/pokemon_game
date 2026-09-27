"""Décor des cinq arènes : chacune a son thème, reconnaissable au premier coup d'œil.

  roche    : carrière de grès (dalles irrégulières, portiques de pierre, menhirs, ambre, fossile)
  plante   : jardin (pelouse, allée, mosaïque de pétales, arches de lierre, fleurs géantes, cerisiers)
  electrik : centrale électrique (plaques de métal, circuits lumineux, bobines Tesla, pylônes et câbles)
  eau      : temple aquatique (mosaïque de vagues, bassins, canal, colonnade, fontaines, coraux)
  feu      : forge volcanique (dalles de basalte fendues de lave, obsidienne, braseros, petit volcan)

Chaque arène garde un sol plat (on y combat) et le cercle de capture dessiné par la partie ;
le décor qui bloque le passage est posé autour, jamais sur les voies. Chaque voie qui
arrive dans l'arène passe entre deux piliers aux couleurs du thème.
"""
import math

from ursina import color, lerp

from game import config as C
from game.world.emblems import add_emblem
from game.world.geometry import MeshBuilder
from game.world.stadium import LANES, polyline_dist


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
            x, z = polar(ang, r, self.x0, self.z0)
            if self.near_gate(ang, 10) or not self.st._clear_of_lanes(x, z, clear):
                continue
            if self.st.blocked(x, z, radius) or math.hypot(x, z) > C.FIELD_RADIUS - 5:
                continue
            out.append((x, z, ang))
        return out

    def disc(self, b, r, y, h, col, prim='cyl_hi'):
        b.add(prim, (self.x0, y, self.z0), (r * 2, h, r * 2), col=col)

    def ring(self, b, r, y, h, col, prim='ring_97'):
        b.add(prim, (self.x0, y, self.z0), (r * 2, h, r * 2), col=col)

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
                if d > r_out - size * .6 or d < r_in + size * .6:
                    continue
                s = size * 2 * gap * (1 - rng.uniform(0, jitter))
                ox = rng.uniform(-jitter, jitter) * size
                oz = rng.uniform(-jitter, jitter) * size
                b.add(prim, (self.x0 + x + ox, y, self.z0 + z + oz), (s, h, s),
                      rot=(0, 30 + (rng.uniform(-25, 25) if jitter else 0), 0), col=col_fn(x, z))

    def emblem(self, s=None, y=.17, col=None, emissive=.6):
        emb = MeshBuilder()
        add_emblem(emb, self.cfg['type'], (0, 0, 0), s or self.R * .17, col=col)
        emb.entity(parent=self.st.root, emissive=emissive, position=(self.x0, y, self.z0), rotation_x=90,
                   scale=(1, 1, .03))

    def gate(self, build_post, build_top=None, height=4.2):
        """Entrée de chaque voie : deux piliers au thème de l'arène, de part et d'autre (pas de
        traverse au-dessus : elle cacherait les Pokémon qui passent dessous)."""
        r = self.R + 4.6
        for ang, w in self.gates:
            cx, cz = polar(ang, r, self.x0, self.z0)
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
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        sand, dark = rgb(.8, .69, .5), rgb(.33, .26, .19)
        self.disc(b, R + 3.6, .03, .06, sand)
        self.disc(b, R + .3, .06, .06, dark)                  # joints entre les dalles
        stones = [rgb(.76, .63, .45), rgb(.7, .57, .4), rgb(.8, .7, .52), rgb(.66, .5, .36)]
        self.hex_tiles(b, 1.0, .1, .1, lambda x, z: shade(rng.choice(stones), rng.uniform(.9, 1.08)),
                       r_in=2.9, gap=.9, jitter=.14, prim='cyl6')
        for _ in range(14):                                   # fissures
            a, r = rng.uniform(0, 360), rng.uniform(4, R - 2)
            x, z = polar(a, r, self.x0, self.z0)
            b.add('box', (x, .155, z), (.09, .01, rng.uniform(1.5, 3)), rot=(0, rng.uniform(0, 180), 0), col=dark)
        # médaillon central taillé
        self.disc(b, 2.9, .09, .12, rgb(.58, .47, .33))
        self.ring(b, 2.6, .16, .02, rgb(.9, .8, .6), 'ring_thin')
        self.emblem(col=rgb(.95, .78, .45))
        # bordure de gros moellons
        n = 44
        for i in range(n):
            ang = i * 360 / n
            x, z = polar(ang, R + 1.1, self.x0, self.z0)
            c = shade(rgb(.62, .54, .44), rng.uniform(.85, 1.1))
            b.add('box', (x, .12, z), (2 * math.pi * (R + 1.1) / n * .9, .18, 1.5),
                  rot=(rng.uniform(-2, 2), ang + rng.uniform(-3, 3), 0), col=c)

        def post(x, z, ang):
            b.add('box', (x, 2.1, z), (1.3, 4.2, 1.3), rot=(0, ang + rng.uniform(-4, 4), 0),
                  col=shade(rgb(.66, .58, .48), rng.uniform(.9, 1.05)))
            b.add('box', (x, .3, z), (1.8, .6, 1.8), rot=(0, ang, 0), col=rgb(.5, .44, .36))
            b.add('box', (x, 4.4, z), (1.6, .4, 1.6), rot=(0, ang, 0), col=rgb(.55, .48, .38))
            b.add('box', (x, 4.7, z), (1.3, .25, 1.3), rot=(0, ang, 0), col=rgb(.45, .56, .3))
            glow.add('cone4', (x, 5.4, z), (.6, 1.2, .6), rot=(0, 45, 0), col=rgb(1, .62, .18))

        self.gate(post)
        # menhirs, trilithons, rochers et ambre autour
        for x, z, ang in self.spots(9, R + 6, R + 9, 2.5, 1.6):
            k = rng.random()
            if k < .45:                                        # menhir penché
                h = rng.uniform(3.5, 5.5)
                b.add('box', (x, h / 2 - .3, z), (1.2, h, .8), rot=(rng.uniform(-8, 8), ang, rng.uniform(-8, 8)),
                      col=shade(rgb(.6, .56, .5), rng.uniform(.85, 1.1)))
                b.add('box', (x, h - .1, z), (1.25, .3, .85), rot=(0, ang, 0), col=rgb(.42, .55, .28))
                self.st.block(x, z, 1.0)
            elif k < .7:                                       # trilithon
                tx, tz = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
                for s in (-1, 1):
                    b.add('box', (x + tx * s * 1.4, 1.7, z + tz * s * 1.4), (.9, 3.4, .9), rot=(0, ang, 0),
                          col=rgb(.64, .58, .5))
                    self.st.block(x + tx * s * 1.4, z + tz * s * 1.4, .7)
                b.add('box', (x, 3.7, z), (4.0, .8, 1.1), rot=(0, ang + 90, 0), col=rgb(.58, .52, .45))
            else:                                              # rochers et cristaux d'ambre
                for _ in range(3):
                    self.st._rock(b, x + rng.uniform(-1.2, 1.2), z + rng.uniform(-1.2, 1.2), rng.uniform(.8, 1.6),
                                  moss=.15)
                for _ in range(rng.randint(2, 4)):
                    ox, oz = rng.uniform(-1, 1), rng.uniform(-1, 1)
                    h = rng.uniform(.8, 1.8)
                    glow.add('cone4', (x + ox, h / 2 + .4, z + oz), (.5, h, .5),
                             rot=(rng.uniform(-20, 20), rng.uniform(0, 90), rng.uniform(-20, 20)),
                             col=rgb(1, .62, .18))
                self.st.block(x, z, 1.6)
        # fossile à moitié enterré
        for x, z, ang in self.spots(1, R + 5.2, R + 6, 3, 2.5, offset=rng.uniform(0, 360), jitter=180)[:1]:
            bone = rgb(.94, .9, .8)
            b.add('cyl8', (x, .15, z), (.35, 4.2, .35), rot=(90, ang + 90, 0), col=bone)
            tx, tz = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
            for k in range(-3, 4):
                px, pz = x + tx * k * .55, z + tz * k * .55
                b.add('ring_thin', (px, .1, pz), (2.2 - abs(k) * .2, .18, 1.2), rot=(90, ang + 90, 0), col=bone)
            b.add('blob', (x + tx * 2.5, .35, z + tz * 2.5), (1.1, .7, .8), rot=(0, ang, 0), col=bone)

    # ================================================================ PLANTE
    def build_plante(self):
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        self.disc(b, R + 3.6, .03, .06, rgb(.62, .66, .52))
        self.disc(b, R + .3, .07, .08, rgb(.34, .6, .27))
        for _ in range(160):                                  # herbe plus claire et plus sombre
            a, r = rng.uniform(0, 360), math.sqrt(rng.random()) * (R - .5)
            x, z = polar(a, r, self.x0, self.z0)
            b.add('cyl8', (x, .115, z), (rng.uniform(1.2, 2.4), .01, rng.uniform(1.2, 2.4)),
                  col=rng.choice((rgb(.37, .63, .29), rgb(.32, .57, .25))))
        # allée circulaire et allées en croix : terre battue et pierres plates
        path = rgb(.8, .77, .66)
        dirt = rgb(.6, .5, .36)
        self.ring(b, R * .8 - .62, .12, .02, dirt, 'ring')
        for ang in (45, 135, 225, 315):
            x, z = polar(ang, 3.6 + 1.95, self.x0, self.z0)
            b.add('box', (x, .12, z), (1.3, .02, 5.2), rot=(0, ang, 0), col=dirt)
        for rr, n in ((R * .8, 34), (R * .8 - 1.25, 30)):
            for i in range(n):
                x, z = polar(i * 360 / n + rng.uniform(-2, 2), rr, self.x0, self.z0)
                b.add('cyl8', (x, .13, z), (1.05, .06, .85), rot=(0, rng.uniform(0, 90), 0), col=shade(path, rng.uniform(.9, 1.05)))
        for ang in (45, 135, 225, 315):
            for k in range(4):
                x, z = polar(ang + rng.uniform(-3, 3), 3.6 + k * 1.3, self.x0, self.z0)
                b.add('cyl8', (x, .13, z), (1.0, .06, .8), rot=(0, rng.uniform(0, 90), 0), col=shade(path, rng.uniform(.9, 1.05)))
        # massifs de fleurs sur la pelouse
        petal_cols = (rgb(1, .45, .62), rgb(1, .92, .35), rgb(.98, .98, 1), rgb(.72, .5, 1), rgb(1, .6, .3))
        for i in range(8):
            ang = i * 45 + 22.5
            x, z = polar(ang, R * .55, self.x0, self.z0)
            c = petal_cols[i % len(petal_cols)]
            for _ in range(9):
                ox, oz = rng.uniform(-1.1, 1.1), rng.uniform(-1.1, 1.1)
                b.add('sphere_lo', (x + ox, .2, z + oz), (.32, .12, .32), col=c)
                b.add('cone6', (x + ox, .18, z + oz), (.18, .3, .18), col=rgb(.25, .55, .2))
        # grande fleur en mosaïque au centre
        for i in range(8):
            ang = i * 45
            x, z = polar(ang, 1.9, self.x0, self.z0)
            b.add('sphere', (x, .12, z), (1.4, .06, 2.6), rot=(0, ang, 0), col=rgb(1, .55, .7) if i % 2 else rgb(1, .72, .82))
        self.disc(b, 1.3, .15, .04, rgb(1, .86, .3), 'cyl24')
        self.emblem(s=R * .1, y=.2, col=rgb(.25, .7, .25))
        # bordure : haie basse fleurie (coupée aux entrées)
        n = 40
        for i in range(n):
            ang = i * 360 / n
            if self.near_gate(ang, 12):
                continue
            x, z = polar(ang, R + 1.4, self.x0, self.z0)
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

    # ================================================================ ELECTRIK
    def build_electrik(self):
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        yellow, black = rgb(1, .82, .12), rgb(.13, .13, .15)
        self.disc(b, R + 3.6, .03, .06, rgb(.5, .53, .58))
        # bandeau de sécurité jaune et noir
        n = 72
        for i in range(n):
            ang = i * 360 / n
            x, z = polar(ang, R + 1.5, self.x0, self.z0)
            b.add('box', (x, .09, z), (2 * math.pi * (R + 1.5) / n * .98, .1, 1.6), rot=(0, ang, 0),
                  col=yellow if i % 2 else black)
        self.disc(b, R + .6, .07, .1, rgb(.2, .21, .25))
        # plaques de métal rivetées
        s = 2.2
        n = int(R / s) + 1
        for i in range(-n, n + 1):
            for j in range(-n, n + 1):
                x, z = i * s, j * s
                if math.hypot(x, z) > R - 1 or math.hypot(x, z) < 3:
                    continue
                col = rgb(.52, .55, .62) if (i + j) % 2 else rgb(.45, .48, .55)
                b.add('box', (self.x0 + x, .13, self.z0 + z), (s * .94, .06, s * .94), col=col)
                for cx in (-1, 1):
                    for cz in (-1, 1):
                        b.add('cyl6', (self.x0 + x + cx * s * .38, .165, self.z0 + z + cz * s * .38), (.14, .02, .14),
                              col=rgb(.7, .72, .78))
        # circuits lumineux en zigzag depuis le centre
        for k in range(8):
            ang = k * 45 + 22.5
            r0, side = 3.2, 1
            while r0 < R - 1.5:
                r1 = r0 + 2.2
                a0, a1 = ang + side * 4, ang - side * 4
                (ax, az), (bx, bz) = polar(a0, r0, self.x0, self.z0), polar(a1, r1, self.x0, self.z0)
                L = math.hypot(bx - ax, bz - az)
                glow.add('box', ((ax + bx) / 2, .17, (az + bz) / 2), (.16, .02, L + .16),
                         rot=(0, math.degrees(math.atan2(bx - ax, bz - az)), 0), col=rgb(1, .9, .3))
                r0, side = r1, -side
            ex, ez = polar(ang, r0, self.x0, self.z0)
            glow.add('cyl8', (ex, .17, ez), (.5, .03, .5), col=rgb(1, .95, .5))
        self.disc(b, 3, .12, .1, rgb(.18, .18, .22))
        self.ring(b, 2.8, .18, .03, yellow, 'ring_thin')
        self.emblem(emissive=1.0)

        def post(x, z, ang):
            b.add('box', (x, 2.2, z), (.9, 4.4, .9), rot=(0, ang, 0), col=rgb(.42, .45, .5))
            for k in range(5):
                b.add('box', (x, .5 + k * .9, z), (.95, .42, .95), rot=(0, ang, 0), col=yellow if k % 2 else black)
            glow.add('sphere_lo', (x, 4.7, z), .45, col=rgb(1, .95, .5))

        self.gate(post)
        # bobines Tesla, pylônes reliés par des câbles, générateurs
        pylons = []
        for x, z, ang in self.spots(10, R + 6, R + 9, 2.5, 1.6):
            k = rng.random()
            if k < .38:                                        # bobine Tesla
                b.add('box', (x, .3, z), (1.8, .6, 1.8), col=rgb(.3, .31, .36))
                b.add('cyl16', (x, 2.2, z), (.7, 3.4, .7), col=rgb(.45, .47, .52))
                for j in range(5):
                    b.add('ring_thin', (x, 1.1 + j * .6, z), (1.2 - j * .12, .2, 1.2 - j * .12), col=rgb(.8, .5, .25))
                b.add('ring', (x, 4.2, z), (2.0, .5, 2.0), col=rgb(.7, .72, .78))
                glow.add('sphere', (x, 4.5, z), .9, col=rgb(.75, .95, 1))
                self.st.block(x, z, 1.1)
            elif k < .7:                                       # pylône en treillis
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
                for s in (-1, 1):
                    px, pz = polar(ang + 90, s * .8, x, z)
                    b.add('cyl8', (px, 2.35, pz), (.3, .7, .3), col=black)
                    glow.add('sphere_lo', (px, 2.8, pz), .2, col=rgb(1, .9, .3))
                self.st.block(x, z, 1.5)
        for (ax, az), (bx, bz) in zip(pylons, pylons[1:]):     # câbles entre pylônes voisins
            L = math.hypot(bx - ax, bz - az)
            if L < 14:
                b.add('box', ((ax + bx) / 2, 5.3, (az + bz) / 2), (.06, .06, L),
                      rot=(0, math.degrees(math.atan2(bx - ax, bz - az)), 0), col=black)

    # ================================================================ EAU
    def build_eau(self):
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        marble, deep = rgb(.93, .95, .98), rgb(.12, .38, .7)
        self.disc(b, R + 3.6, .03, .06, marble)
        # canal d'eau autour du terrain (peu profond : on le traverse)
        self.disc(b, R + 2.4, .05, .06, rgb(.2, .45, .7))
        self.water.add('ring', (self.x0, .12, self.z0), ((R + 2.4) * 2, .04, (R + 2.4) * 2), col=rgb(.35, .8, .95))
        self.disc(b, R + .7, .08, .1, marble)
        # mosaïque de vagues
        cols = [rgb(.3, .62, .9), rgb(.5, .8, .95), rgb(.85, .95, 1), rgb(.2, .5, .82)]
        r = 3.4
        while r < R:
            n = int(2 * math.pi * r / 1.05)
            for i in range(n):
                ang = i * 360 / n
                x, z = polar(ang, r, self.x0, self.z0)
                w = math.sin(math.radians(ang) * 6 + r * .9)
                c = cols[0] if w < -.3 else cols[1] if w < .3 else cols[2] if w < .8 else cols[3]
                b.add('box', (x, .15, z), (2 * math.pi * r / n * .9, .04, .95), rot=(0, ang, 0), col=c)
            r += 1.08
        # bassins peu profonds
        for k in range(4):
            x, z = polar(k * 90 + 45, R * .6, self.x0, self.z0)
            b.add('cyl24', (x, .16, z), (4.6, .04, 4.6), col=deep)
            self.water.add('cyl24', (x, .2, z), (4.4, .03, 4.4), col=rgb(.4, .82, .95))
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
            x, z = polar(ang, R + 5, self.x0, self.z0)
            if self.near_gate(ang, 16) or not self.st._clear_of_lanes(x, z, 1.6) or self.st.blocked(x, z, .8):
                continue
            b.add('cyl16', (x, 1.6, z), (.8, 3.2, .8), col=marble)
            b.add('box', (x, 3.3, z), (1.2, .3, 1.2), rot=(0, ang, 0), col=rgb(.3, .6, .9))
            self.st.block(x, z, .6)
        # fontaines et coraux
        for x, z, ang in self.spots(8, R + 7.5, R + 9.5, 3, 1.8, offset=22):
            if rng.random() < .5:                              # fontaine à étages
                b.add('cyl24', (x, .35, z), (3.4, .7, 3.4), col=marble)
                self.water.add('cyl24', (x, .66, z), (3.0, .04, 3.0), col=rgb(.4, .82, .95))
                b.add('cyl16', (x, 1.3, z), (.5, 1.8, .5), col=marble)
                b.add('cyl24', (x, 2.2, z), (1.8, .3, 1.8), col=marble)
                self.water.add('cyl24', (x, 2.36, z), (1.5, .03, 1.5), col=rgb(.4, .82, .95))
                glow.add('cone', (x, 2.9, z), (.35, 1.2, .35), col=rgb(.7, .95, 1))
                glow.add('sphere_lo', (x, 3.5, z), .35, col=rgb(.85, 1, 1))
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
        b, glow, rng, R = self.b, self.glow, self.rng, self.R
        basalt = rgb(.24, .21, .21)
        lava, lava2 = rgb(1, .42, .06), rgb(1, .75, .2)
        self.disc(b, R + 3.6, .03, .06, rgb(.3, .26, .25))
        # canal de lave (lumineux) autour du terrain
        glow.add('ring', (self.x0, .07, self.z0), ((R + 2.3) * 2, .04, (R + 2.3) * 2), col=lava)
        self.disc(b, R + 1.6, .065, .07, basalt)
        # dalles de basalte : la lave brille dans les joints
        glow.add('cyl_hi', (self.x0, .11, self.z0), ((R + .2) * 2, .02, (R + .2) * 2), col=lava)
        self.hex_tiles(b, 1.05, .15, .06, lambda x, z: shade(basalt, rng.uniform(.75, 1.15)), r_in=3.0, gap=.86,
                       jitter=.08)
        self.disc(b, 3.0, .15, .07, rgb(.16, .13, .13))
        self.ring(b, 2.7, .19, .03, lava2, 'ring_thin')
        self.emblem(emissive=1.0)
        # pointes d'obsidienne le long du bord
        n = 30
        for i in range(n):
            ang = i * 360 / n + 6
            if self.near_gate(ang, 13):
                continue
            x, z = polar(ang, R + 3.6, self.x0, self.z0)
            h = rng.uniform(.9, 1.8)
            b.add('cone4', (x, h / 2, z), (.7, h, .7), rot=(rng.uniform(-12, 12), rng.uniform(0, 90), rng.uniform(-12, 12)),
                  col=rgb(.14, .1, .16))

        def post(x, z, ang):
            b.add('box', (x, 2.0, z), (1.2, 4.0, 1.2), rot=(0, ang + 45, 0), col=rgb(.18, .15, .16))
            glow.add('box', (x, 2.0, z), (.12, 3.6, 1.25), rot=(0, ang + 45, 0), col=lava)
            b.add('cyl8', (x, 4.3, z), (1.4, .6, 1.4), col=rgb(.25, .2, .2))
            glow.add('cone', (x, 5.2, z), (1.1, 1.6, 1.1), col=lava)
            glow.add('cone', (x, 5.0, z), (.6, 1.1, .6), col=lava2)

        self.gate(post)
        # volcan miniature (à l'endroit le plus dégagé)
        best = None
        for k in range(24):
            ang = k * 15
            x, z = polar(ang, R + 8.5, self.x0, self.z0)
            if self.near_gate(ang, 25) or math.hypot(x, z) > C.FIELD_RADIUS - 6 or self.st.blocked(x, z, 3.2):
                continue
            d = min(self.lane_gap(x, z), 12)
            if best is None or d > best[0]:
                best = (d, x, z)
        if best and best[0] > 4:
            _, x, z = best
            b.add('frustum', (x, 2.0, z), (7.5, 4.0, 7.5), col=rgb(.28, .22, .21), grad=.3)
            b.add('cyl16', (x, 4.0, z), (1.9, .12, 1.9), col=rgb(.15, .1, .1))
            glow.add('cyl16', (x, 4.03, z), (1.6, .1, 1.6), col=lava)
            for k in range(5):                                 # coulées de lave
                a = k * 72 + rng.uniform(-15, 15)
                px, pz = polar(a, 1.9, x, z)
                glow.add('box', (px, 2.1, pz), (.35, .1, 3.8), rot=(62, a, 0), col=lava)
            self.st.block(x, z, 3.4)
        # braseros, mares de lave et rochers volcaniques
        for x, z, ang in self.spots(10, R + 6, R + 9.5, 2.5, 1.6):
            k = rng.random()
            if k < .4:                                         # brasero
                b.add('cyl8', (x, .8, z), (.7, 1.6, .7), col=rgb(.3, .26, .26))
                b.add('cyl16', (x, 1.75, z), (1.6, .5, 1.6), col=rgb(.22, .18, .18))
                glow.add('cone', (x, 2.5, z), (1.2, 1.7, 1.2), col=lava)
                glow.add('cone', (x, 2.35, z), (.7, 1.3, .7), col=lava2)
                self.st.block(x, z, .9)
            elif k < .65:                                      # mare de lave
                glow.add('cyl16', (x, .06, z), (3.2, .04, 2.6), rot=(0, ang, 0), col=lava)
                glow.add('cyl16', (x, .07, z), (1.6, .04, 1.2), rot=(0, ang, 0), col=lava2)
                for p in range(7):
                    px, pz = polar(p * 51, 1.6, x, z)
                    self.st._rock(b, px, pz, rng.uniform(.3, .5), moss=0)
                self.st.block(x, z, 1.6)
            else:                                              # rocher volcanique veiné de lave
                s = rng.uniform(1.2, 1.9)
                rot = (rng.uniform(-10, 10), rng.uniform(0, 180), rng.uniform(-10, 10))
                b.add('blob', (x, s * .6, z), (s * 1.8, s * 1.5, s * 1.5), rot=rot, col=rgb(.2, .17, .17),
                      wobble=.22, grad=.4)
                for _ in range(3):
                    glow.add('box', (x + rng.uniform(-.5, .5), s * .7, z + rng.uniform(-.5, .5)),
                             (.08, s * 1.1, s * 1.6), rot=(rng.uniform(-30, 30), rng.uniform(0, 180), 0), col=lava)
                for _ in range(2):
                    h = rng.uniform(.9, 1.6)
                    ox, oz = rng.uniform(-1.4, 1.4), rng.uniform(-1.4, 1.4)
                    b.add('cone4', (x + ox, h / 2, z + oz), (.5, h, .5), rot=(rng.uniform(-15, 15), 0, 0),
                          col=rgb(.18, .1, .22))
                self.st.block(x, z, s)
