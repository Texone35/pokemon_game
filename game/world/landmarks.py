"""Grands décors de la carte : un repère visuel fort par zone (voir biomes.py).

  Nord (roche)         : arches naturelles de grès sur le plateau
  Ouest (plante)       : arbre millénaire
  Est (electrik)       : tour Tesla et ligne à haute tension
  Sud-Ouest (eau)      : colline aux cascades et son bassin, bosquet de cristaux géants
  Sud-Est (feu)        : volcan (cratère de lave, coulées), chute de lave, cheminées volcaniques
  près du Boss Pit     : ruines d'un temple envahi par la végétation (de part et d'autre)

Tous sont posés au cœur des massifs de la jungle (jamais dans un passage) : ils ne changent
ni les collisions ni la navigation. Certains modèlent le relief (volcan, colline, bassin) :
plan() les déclare avant le calcul de la carte des hauteurs, build() pose ensuite le décor.
"""
import math

import numpy as np
from ursina import color

from game import config as C
from game.world import biomes
from game.world.geometry import ROCKS, glowing
from game.world.stadium import BASALT, CRYSTAL, OBSIDIAN, polar, shade, _smoothstep

STONE = color.rgb(.62, .6, .53)
MOSS = color.rgb(.3, .45, .2)
LAVA, LAVA_HOT = biomes.LAVA, biomes.LAVA_HOT
PSY = color.rgb(.75, .45, 1)


class Landmarks:
    def __init__(self, st):
        self.st = st
        self.items = []            # (genre, x, z, rayon, données)

    # ------------------------------------------------------------ emplacements
    def _deep(self, x, z, search=10.0):
        """Point le plus profond d'un massif près de (x, z) et sa profondeur (distance au passage)."""
        st = self.st
        i0, j0, _, _ = st._jcell(x, z)
        m = int(search / .5)
        win = st.wall_sdf[max(0, i0 - m):i0 + m + 1, max(0, j0 - m):j0 + m + 1]
        a, b = np.unravel_index(int(np.argmax(win)), win.shape)
        i, j = max(0, i0 - m) + a, max(0, j0 - m) + b
        return st.j_min + i * .5, st.j_min + j * .5, float(st.wall_sdf[i, j])

    def _side(self, x, z, r, prefer=180.0):
        """Direction (degrés) où le massif reste profond à la distance r, de préférence vers `prefer`
        (180 = sud, face à la caméra)."""
        best = None
        for k in range(24):
            a = k * 15
            px, pz = polar(a, r, x, z)
            score = self.st.wall_dist(px, pz) + 1.5 * math.cos(math.radians(a - prefer))
            if best is None or score > best[0]:
                best = (score, a)
        return best[1]

    def _add(self, kind, x, z, r, **data):
        self.items.append((kind, x, z, r, data))

    def plan(self):
        """Choisit les emplacements et déclare les reliefs (avant la carte des hauteurs)."""
        st = self.st
        marks = st.terrain_marks
        # volcan (Sud-Est) et colline aux cascades (Sud-Ouest), en miroir
        x, z, d = self._deep(39, -52)
        r = min(d + 1.5, 11)
        self._add('volcano', x, z, r)
        marks.append((x, z, r, lambda t: 6.2 * _smoothstep(1, .28, t) - 2.2 * _smoothstep(.26, .06, t), 'add'))
        x, z, d = self._deep(-39, -52)
        r = min(d + 1, 10)
        side = self._side(x, z, r * .62)
        px, pz = polar(side, r * .62, x, z)
        self._add('falls', x, z, r * .5, side=side, pool=(px, pz, 2.6), big=True, lip=r * .27)
        marks.append((x, z, r * .55, lambda t: 5.0 * _smoothstep(1, .45, t), 'add'))
        marks.append((px, pz, 3.4, lambda t: (1.0, _smoothstep(1, .75, t)), 'flat'))
        # petite cascade (Sud-Ouest) et chute de lave (Sud-Est), en miroir
        for kind, sx in (('falls', -1), ('lavafall', 1)):
            x, z, d = self._deep(105 * sx, -33.5, 6)
            r = min(d + .5, 6.5)
            side = self._side(x, z, r * .7)
            px, pz = polar(side, r * .7, x, z)
            self._add(kind, x, z, r * .45, side=side, pool=(px, pz, 1.9), big=False, lip=r * .22)
            marks.append((x, z, r * .5, lambda t: 3.6 * _smoothstep(1, .4, t), 'add'))
            marks.append((px, pz, 2.6, lambda t: (1.0, _smoothstep(1, .72, t)), 'flat'))
        # arbre millénaire (Ouest) et tour Tesla (Est)
        x, z, d = self._deep(-97.5, 48.5, 8)
        self._add('giant_tree', x, z, min(d, 7))
        x, z, d = self._deep(97.5, 48.5, 8)
        self._add('tesla', x, z, 3.5)
        line = [(x, z)]
        for tx, tz in ((108, 26), (110, 5.5), (104, -16)):
            px, pz, dd = self._deep(tx, tz, 7)
            if dd > 2.2:
                line.append((px, pz))
        self.power_line = line
        for px, pz in line[1:]:
            self._add('pylon', px, pz, 2.0)
        # ruines envahies par la végétation, de part et d'autre du Boss Pit
        for sx in (-1, 1):
            x, z, d = self._deep(21.5 * sx, 21, 6)
            self._add('ruins', x, z, min(d - .5, 6.5))
        # arches de grès sur le plateau Nord
        for sx in (-1, 1):
            x, z, d = self._deep(22 * sx, 107, 6)
            self._add('arch', x, z, min(d, 5.5), yaw=90 + 25 * sx)
        # antre de Torterra : porte en ruine envahie de racines et grand arbre, derrière chaque camp
        for i, camp in enumerate(C.CAMPS):
            if camp.get('buff') != 'bastion':
                continue
            cx, cz = camp['pos']
            (px, pz), _ = st.paths[i][0][-1], None
            away = math.degrees(math.atan2(cx - px, cz - pz))           # à l'opposé du chemin d'accès
            back = self._side(cx, cz, 10, prefer=away)
            tx, tz, d = self._deep(*polar(back, 11, cx, cz), 5)
            self._add('torterra', cx, cz, 0, back=back, tree=(tx, tz, d))
        # cristaux géants (Sud-Ouest) et cheminées volcaniques (Sud-Est)
        x, z, d = self._deep(-20, -81, 6)
        self._add('crystal_grove', x, z, min(d, 5))
        x, z, d = self._deep(20, -81, 6)
        self._add('vents', x, z, min(d, 5))

    def reserved(self, x, z):
        """Vrai si (x, z) est occupé par un grand décor (pas d'arbre de la jungle ici)."""
        for kind, cx, cz, r, data in self.items:
            tree = data.get('tree')
            if tree and (x - tree[0]) ** 2 + (z - tree[1]) ** 2 < 36:
                return True
            if (x - cx) ** 2 + (z - cz) ** 2 < (r + 1.5) ** 2:
                return True
            pool = data.get('pool')
            if pool and (x - pool[0]) ** 2 + (z - pool[1]) ** 2 < (pool[2] + 2) ** 2:
                return True
        return False

    # ------------------------------------------------------------ couleurs du sol
    def paint(self, x, z, y, col, glow):
        """Colore le sol sous les grands décors (tableaux numpy modifiés sur place)."""
        for kind, cx, cz, r, data in self.items:
            d = np.hypot(x - cx, z - cz)
            if kind == 'volcano':
                t = d / r
                rock = (np.array(tuple(BASALT)[:3]) * (1.1 + .25 * np.sin(x * 1.3 + z * .9)[..., None]))
                m = _smoothstep(1.1, .8, t)[..., None]
                col[:] = col * (1 - m) + rock * m
                # lac de lave dans le cratère et coulées sur les flancs
                ang = np.arctan2(x - cx, z - cz)
                flows = _smoothstep(.93, .99, np.cos(ang * 4 + 1.1 + np.sin(t * 7) * .35)) * _smoothstep(.95, .3, t)
                lake = _smoothstep(.2, .12, t)
                lava = np.maximum(flows, lake)[..., None]
                col[:] = col * (1 - lava) + np.array(LAVA) * lava
                glow[:] = np.maximum(glow, lava * .95)
            elif kind in ('falls', 'lavafall'):
                m = _smoothstep(r * 1.15, r * .8, d)[..., None]
                if kind == 'falls':
                    rock = np.array((.52, .57, .6)) * (1 - _smoothstep(.5, 2.5, y)[..., None] * .15)
                    top = _smoothstep(5.5, 7.0, y)[..., None] * .5
                    rock = rock * (1 - top) + np.array((.26, .5, .24)) * top      # herbe au sommet
                else:
                    rock = np.array(tuple(BASALT)[:3]) * 1.15
                col[:] = col * (1 - m) + rock * m
                if kind == 'lavafall':
                    px, pz, pr = data['pool']
                    pool = _smoothstep(pr + .2, pr - .4, np.hypot(x - px, z - pz))[..., None]
                    col[:] = col * (1 - pool) + np.array(LAVA_HOT) * pool
                    glow[:] = np.maximum(glow, pool)

    # ------------------------------------------------------------ construction
    def build(self):
        for kind, x, z, r, data in self.items:
            getattr(self, 'build_' + kind)(x, z, r, **data)
        self._build_power_line()

    def _y(self, x, z):
        return self.st.ground_y(x, z)

    def build_volcano(self, x, z, r):
        """Cratère : bord déchiqueté, lac de lave animé, blocs de basalte sur les flancs, panache de
        fumée et braises (particules)."""
        st, b, rng = self.st, self.st.b, self.st.rng
        rim = r * .27
        for k in range(14):                          # bord du cratère
            a = k * 360 / 14 + rng.uniform(-8, 8)
            px, pz = polar(a, rim, x, z)
            s = rng.uniform(1.0, 1.7)
            b.add(rng.choice(ROCKS), (px, .2, pz), (s * 1.7, s * 1.2, s * 1.4), rot=(rng.uniform(-15, 15), a, 0),
                  col=shade(BASALT, rng.uniform(.9, 1.3)), grad=.3, cap=(color.rgb(.4, .36, .33), .4))
        cy = self._y(x, z)
        st.wb.disc(x, cy + .25, z, rim * .95, kind='lava', flow=(.3, 0, .2))
        st.emitters.append((x, cy + .25, z, 'lava', rim * .8))
        st.emitters.append((x, cy + .5, z, 'volcano', 1.0))
        for _ in range(9):                           # blocs sur les flancs
            a, t = rng.uniform(0, 360), rng.uniform(.4, .9)
            px, pz = polar(a, r * t, x, z)
            s = rng.uniform(.6, 1.2)
            b.add(rng.choice(ROCKS), (px, s * .3, pz), (s * 1.6, s, s * 1.4), rot=(0, rng.uniform(0, 360), 0),
                  col=shade(BASALT, rng.uniform(.9, 1.25)), grad=.3)

    def build_falls(self, x, z, r, **kw):
        """Colline rocheuse d'où tombe une cascade dans un bassin bordé de rochers."""
        self._cascade(x, z, r, lava=False, **kw)

    def build_lavafall(self, x, z, r, **kw):
        """Même chose en version volcanique : une chute de lave dans un bassin incandescent."""
        self._cascade(x, z, r, lava=True, **kw)

    def _cascade(self, x, z, r, side, pool, big, lip, lava):
        st, b, rng = self.st, self.st.b, self.st.rng
        px, pz, pr = pool
        rock = BASALT if lava else color.rgb(.5, .55, .58)
        # rochers qui couronnent la colline et encadrent la chute
        for k in range(10 if big else 7):
            a = side + 180 + (k / (9 if big else 6) - .5) * 300
            qx, qz = polar(a, r * rng.uniform(.75, 1.05), x, z)
            s = rng.uniform(1.1, 1.8) * (1 if big else .8)
            b.add(rng.choice(ROCKS), (qx, s * .45, qz), (s * 1.7, s * 1.4, s * 1.4), rot=(rng.uniform(-10, 10), a, 0),
                  col=shade(rock, rng.uniform(.85, 1.15)), grad=.35, cap=None if lava else (MOSS, .9))
        for k in range(4 if big else 2):             # gros blocs moussus sur le sommet
            a = side + 180 + rng.uniform(-110, 110)
            qx, qz = polar(a, rng.uniform(0, lip * .8), x, z)
            s = rng.uniform(1.6, 2.4) * (1 if big else .75)
            b.add(rng.choice(ROCKS), (qx, s * .4, qz), (s * 1.6, s * 1.1, s * 1.4), rot=(0, rng.uniform(0, 360), 0),
                  col=shade(rock, rng.uniform(.9, 1.1)), grad=.3, cap=None if lava else (MOSS, .9))
        # rideau de la chute : du rebord de la colline jusqu'au bassin
        lip = polar(side, lip, x, z)
        top = self._y(*lip) + .3
        pool_y = self._y(px, pz) + (.3 if lava else .35)
        dx, dz = px - lip[0], pz - lip[1]
        yaw = math.degrees(math.atan2(dx, dz))
        width = 2.4 if big else 1.6
        pts = [(lip[0] + dx * t * .85, top - (top - pool_y) * t ** 1.7, lip[1] + dz * t * .85)
               for t in (i / 10 for i in range(11))]
        st.wb.curtain(pts, width, kind='lava' if lava else 'fall', speed=.8)
        # bassin : eau (ou lave) animée
        if lava:
            st.wb.disc(px, pool_y, pz, pr, kind='lava', flow=(dx, 0, dz))
            st.emitters.append((px, pool_y, pz, 'lava', pr * .8))
        else:
            st.wb.disc(px, pool_y, pz, pr, depth=1.0, speed=.35)
            st.emitters.append((pts[-1][0], pool_y, pts[-1][2], 'fall', 1.3 if big else .9))
        n = 12 if big else 8
        for k in range(n):                           # rochers autour du bassin
            a = k * 360 / n + rng.uniform(-10, 10)
            if abs((a - yaw - 180 + 180) % 360 - 180) < 40:
                continue                             # côté de la chute
            qx, qz = polar(a, pr + .35, px, pz)
            s = rng.uniform(.4, .8)
            b.add(rng.choice(ROCKS), (qx, s * .25, qz), (s * 1.6, s, s * 1.3), rot=(0, rng.uniform(0, 360), 0),
                  col=shade(rock, rng.uniform(.85, 1.15)), grad=.3, cap=None if lava else (MOSS, .8))
        if not lava:                                 # nénuphars et cristaux au bord
            for k in range(3):
                qx, qz = polar(rng.uniform(0, 360), pr * .6, px, pz)
                st.flat.add('cyl24', (qx, pool_y + .03, qz), (.9, .03, .8), rot=(0, rng.uniform(0, 360), 0),
                            col=color.rgb(.25, .55, .22))
            st._crystals(b, *polar(yaw + 110, pr + 1.2, px, pz), .9)

    def build_giant_tree(self, x, z, r):
        """Arbre millénaire : tronc massif à contreforts, branches maîtresses, immense couronne, lianes."""
        b, rng = self.st.b, self.st.rng
        bark, bark2 = color.rgb(.36, .25, .17), color.rgb(.29, .2, .14)
        b.add('frustum', (x, 5.5, z), (4.2, 11, 4.2), col=bark, wobble=.08, grad=.35)
        for k in range(7):                           # racines contreforts
            a = k * 360 / 7 + rng.uniform(-10, 10)
            px, pz = polar(a, 2.2, x, z)
            b.add('cone6', (px, .9, pz), (1.3, 4.2, 1.0), rot=(62, a, 0), col=shade(bark2, rng.uniform(.9, 1.1)))
            b.add('blob', polar(a, 1.6, x, z)[:1] + (.4,) + polar(a, 1.6, x, z)[1:], (1.4, .8, 1.4),
                  col=shade(MOSS, rng.uniform(.9, 1.1)), wobble=.2)
        for k in range(5):                           # branches maîtresses
            a = k * 72 + rng.uniform(-15, 15)
            px, pz = polar(a, 2.4, x, z)
            b.add('cyl', (px, 8.2 + rng.uniform(0, 1), pz), (.7, 5.5, .7), rot=(55, a, 0), col=bark)
        greens = [color.rgb(.12, .42, .14), color.rgb(.16, .5, .16), color.rgb(.1, .36, .15), color.rgb(.22, .56, .2)]
        R = min(r + 1.5, 8)
        for k in range(15):                          # couronne en plusieurs dômes
            a, t = rng.uniform(0, 360), math.sqrt(rng.random()) * R * .72
            px, pz = polar(a, t, x, z)
            s = rng.uniform(3.4, 4.8)
            b.add('blob', (px, 10.5 + rng.uniform(0, 1.5) - t * .12, pz), (s * 1.3, s * .85, s * 1.3),
                  col=shade(rng.choice(greens), rng.uniform(.9, 1.1)), wobble=.2, grad=.5)
        for k in range(6):
            a = rng.uniform(0, 360)
            px, pz = polar(a, rng.uniform(0, R * .4), x, z)
            b.add('blob', (px, 13 + rng.uniform(0, .8), pz), (3.6, 2.2, 3.6), col=shade(rng.choice(greens), 1.2),
                  wobble=.18, grad=.3)
        for k in range(14):                          # lianes et petites lueurs (lucioles)
            a, t = rng.uniform(0, 360), rng.uniform(R * .4, R * .85)
            px, pz = polar(a, t, x, z)
            h = rng.uniform(2.5, 4.5)
            b.add('cyl6', (px, 9.2 - h / 2, pz), (.12, h, .12), col=color.rgb(.2, .42, .15))
            if k % 3 == 0:
                b.add('sphere_lo', (px, 9 - h, pz), .25, col=glowing(color.rgb(.85, 1, .5), .9))

    def build_tesla(self, x, z, r):
        """Tour Tesla : socle, pylône en treillis, bobine cuivrée et sphère lumineuse, transformateurs."""
        b, rng = self.st.b, self.st.rng
        steel = color.rgb(.5, .53, .58)
        yellow = color.rgb(1, .82, .12)
        b.add('cyl8', (x, .5, z), (5.6, 1.0, 5.6), col=color.rgb(.55, .55, .56))
        H = 13.0
        self.tesla_top = (x, H + 1.5, z)
        for sx in (-1, 1):                           # pieds du pylône, resserrés vers le haut
            for sz in (-1, 1):
                b.add('box', (x + sx * 1.1, 1 + H / 2, z + sz * 1.1), (.28, H + .6, .28),
                      rot=(sz * -5, 0, sx * 5), col=steel)
        for k in range(6):                           # croisillons
            yy = 1.8 + k * 2
            w = 2.6 - k * .3
            for rot in (0, 90):
                b.add('box', (x, yy, z), (w, .14, .14), rot=(0, rot, 0), col=steel)
                b.add('box', (x, yy + 1, z), (w * 1.35, .1, .1), rot=(0, rot + 45, 38), col=steel)
        b.add('cyl16', (x, H + .3, z), (1.2, 1.8, 1.2), col=color.rgb(.65, .4, .22))
        for k in range(5):
            b.add('ring_thin', (x, H - .3 + k * .35, z), (1.45, .14, 1.45), col=color.rgb(.85, .52, .25))
        b.add('ring', (x, H + 1.5, z), (3.8, .7, 3.8), col=color.rgb(.72, .74, .8))
        b.add('sphere', (x, H + 2.2, z), 1.9, col=glowing(color.rgb(.7, .92, 1), 1))
        for k in range(6):                           # arcs électriques figés
            a = k * 60 + rng.uniform(-10, 10)
            px, pz = polar(a, 1.6, x, z)
            b.add('box', (px, H + 2.2, pz), (.07, .07, 2.2), rot=(rng.uniform(-40, 40), a, 0),
                  col=glowing(color.rgb(.8, .95, 1), 1))
        for s in (-1, 1):                            # transformateurs
            px, pz = polar(90 * s + 30, 3.4, x, z)
            b.add('box', (px, 1.1, pz), (1.8, 2.2, 1.4), rot=(0, 30, 0), col=color.rgb(.42, .45, .5))
            b.add('box', (px, 2.25, pz), (1.9, .12, 1.5), rot=(0, 30, 0), col=yellow)
            for k in range(3):
                qx, qz = polar(120, (k - 1) * .5, px, pz)
                b.add('cyl8', (qx, 2.6, qz), (.18, .6, .18), col=color.rgb(.9, .88, .8))
            b.add('box', polar(210, .72, px, pz)[:1] + (1.2,) + polar(210, .72, px, pz)[1:], (.8, .3, .03),
                  rot=(0, 30, 0), col=glowing(color.rgb(.5, 1, .6), .9))

    def build_pylon(self, x, z, r):
        b = self.st.b
        steel = color.rgb(.55, .57, .62)
        for sx in (-1, 1):
            for sz in (-1, 1):
                b.add('box', (x + sx * .6, 4.5, z + sz * .6), (.16, 9.2, .16), rot=(sz * -4, 0, sx * 4), col=steel)
        for yy in (2, 4.5, 7):
            for rot in (0, 90):
                b.add('box', (x, yy, z), (1.4 - yy * .08, .1, .1), rot=(0, rot, 0), col=steel)
        b.add('box', (x, 9, z), (3.4, .2, .2), col=steel)
        for s in (-1, 1):
            b.add('cyl8', (x + s * 1.5, 8.7, z), (.16, .5, .16), col=color.rgb(.9, .88, .8))

    def _build_power_line(self):
        """Câbles (avec leur courbe) entre la tour Tesla et les pylônes."""
        pts = getattr(self, 'power_line', None)
        if not pts or len(pts) < 2:
            return
        b = self.st.b
        heights = [self.tesla_top[1] - 1.2] + [8.6] * (len(pts) - 1)
        for (ax, az), (bx, bz), ha, hb in zip(pts, pts[1:], heights, heights[1:]):
            dx, dz = bx - ax, bz - az
            L = math.hypot(dx, dz)
            px, pz = dz / L * 1.5, -dx / L * 1.5
            ga, gb = self._y(ax, az), self._y(bx, bz)
            for s in (-1, 1):
                prev = None
                for k in range(7):
                    t = k / 6
                    sag = 4 * t * (1 - t) * 1.6
                    p = (ax + dx * t + px * s, (ga + ha) * (1 - t) + (gb + hb) * t - sag, az + dz * t + pz * s)
                    if prev is not None:
                        mx, my, mz = ((prev[i] + p[i]) / 2 for i in range(3))
                        seg = math.hypot(p[0] - prev[0], p[2] - prev[2])
                        pitch = math.degrees(math.atan2(prev[1] - p[1], seg))
                        # le câble est à hauteur absolue : on retire le relief ajouté par le constructeur
                        b.add('box', (mx, my - self._y(mx, mz), mz), (.06, .06, math.hypot(seg, p[1] - prev[1])),
                              rot=(pitch, math.degrees(math.atan2(dx, dz)), 0), col=color.rgb(.12, .12, .14))
                    prev = p

    def build_ruins(self, x, z, r):
        """Temple en ruine : pyramide à degrés moussue, colonnes brisées, autel aux runes lumineuses."""
        b, rng = self.st.b, self.st.rng
        yaw = rng.uniform(0, 90)
        size = min(r * 1.25, 8)
        for k, (w, h) in enumerate(((size, 1.4), (size * .72, 1.3), (size * .46, 1.2))):
            y = sum(hh for _, hh in ((size, 1.4), (size * .72, 1.3), (size * .46, 1.2))[:k])
            b.add('box', (x, y + h / 2 - .2, z), (w, h, w), rot=(0, yaw, 0), col=shade(STONE, 1 - k * .05))
            for _ in range(3):                       # mousse qui déborde des gradins
                ox, oz = polar(rng.uniform(0, 360), w * .45, 0, 0)
                b.add('blob', (x + ox, y + h - .1, z + oz), (rng.uniform(1.2, 2.2), .45, rng.uniform(1, 1.8)),
                      col=shade(MOSS, rng.uniform(.85, 1.15)), wobble=.25)
        top = 3.7
        b.add('box', (x, top + .6, z), (1.4, 1.2, 1.4), rot=(0, yaw, 0), col=shade(STONE, .85))
        b.add('cone4', (x, top + 1.9, z), (.7, 1.3, .7), rot=(0, yaw + 45, 0), col=glowing(PSY, .9))
        for k in range(4):                           # runes sur les faces
            fx, fz = polar(yaw + k * 90, size / 2 + .02, x, z)
            b.add('box', (fx, .8, fz), (.9, .5, .05), rot=(0, yaw + k * 90, 0), col=glowing(PSY, .75))
        for k in range(5):                           # colonnes brisées et blocs tombés
            a = yaw + 45 + k * 72 + rng.uniform(-15, 15)
            px, pz = polar(a, size * .5 + 1.4, x, z)
            h = rng.uniform(1.2, 3.2)
            b.add('cyl', (px, h / 2, pz), (.8, h, .8), col=shade(STONE, rng.uniform(.85, 1.05)), grad=.3)
            if rng.random() < .6:
                b.add('box', polar(a + 20, size * .5 + 2.2, x, z)[:1] + (.3,) + polar(a + 20, size * .5 + 2.2, x, z)[1:],
                      (1.1, .6, .8), rot=(rng.uniform(-10, 10), rng.uniform(0, 90), 12), col=shade(STONE, .9))
            for _ in range(2):                       # lianes
                b.add('cyl6', (px + rng.uniform(-.3, .3), h * .5, pz + rng.uniform(-.3, .3)), (.1, h * .8, .1),
                      rot=(rng.uniform(-10, 10), 0, rng.uniform(-10, 10)), col=color.rgb(.2, .45, .16))

    def build_arch(self, x, z, r, yaw):
        """Arche naturelle de grès : deux piliers en strates reliés par un pont rocheux."""
        b, rng = self.st.b, self.st.rng
        span = min(r * 1.5, 7)
        feet = [polar(yaw + 90 * s, span / 2, x, z) for s in (-1, 1)]
        for fx, fz in feet:
            for k in range(4):
                s = 2.3 - k * .25
                b.add('blob', (fx, .6 + k * 1.35, fz), (s * 1.2, 1.6, s), rot=(0, yaw + rng.uniform(-15, 15), 0),
                      col=shade(biomes.STRATA[k % len(biomes.STRATA)], rng.uniform(.9, 1.05)), wobble=.14, grad=.3)
        for k in range(7):                           # voûte
            t = k / 6
            ax, az = feet[0][0] + (feet[1][0] - feet[0][0]) * t, feet[0][1] + (feet[1][1] - feet[0][1]) * t
            h = 5.2 + math.sin(t * math.pi) * 1.4
            b.add('blob', (ax, h, az), (2.2, 1.3, 1.9), rot=(0, yaw + 90, (t - .5) * 50),
                  col=shade(biomes.STRATA[(k + 2) % len(biomes.STRATA)], rng.uniform(.9, 1.05)), wobble=.16)
        b.add('blob', (x, 7.1, z), (2.2, .5, 1.6), rot=(0, yaw + 90, 0), col=color.rgb(.46, .5, .26), wobble=.2)

    def build_crystal_grove(self, x, z, r):
        """Cristaux géants du lagon."""
        b, rng = self.st.b, self.st.rng
        for k in range(5):
            a, t = k * 72 + rng.uniform(-20, 20), (0 if k == 0 else rng.uniform(1.4, r * .8))
            px, pz = polar(a, t, x, z)
            h = rng.uniform(4.5, 6.5) if k == 0 else rng.uniform(2.2, 3.8)
            c = shade(rng.choice(CRYSTAL), rng.uniform(.9, 1.1))
            b.add('cone6', (px, h * .45, pz), (1.3 if k == 0 else .9, h, 1.3 if k == 0 else .9),
                  rot=(0 if k == 0 else rng.uniform(-20, 20), rng.uniform(0, 60), 0 if k == 0 else rng.uniform(-20, 20)),
                  col=glowing(c, .5))
        for _ in range(4):
            self.st._crystals(b, *polar(rng.uniform(0, 360), rng.uniform(1, r * .9), x, z), .9)

    def build_vents(self, x, z, r):
        """Cheminées volcaniques fumantes."""
        b, rng = self.st.b, self.st.rng
        for k in range(3):
            a = k * 120 + rng.uniform(-20, 20)
            px, pz = polar(a, 0 if k == 0 else rng.uniform(1.8, r * .7), x, z)
            s = 1.5 if k == 0 else 1.0
            b.add('frustum', (px, 1.2 * s, pz), (3.2 * s, 2.4 * s, 3.2 * s), col=shade(BASALT, 1.2), grad=.3)
            b.add('cyl8', (px, 2.42 * s, pz), (.75 * s, .06, .75 * s), col=glowing(LAVA_HOT, 1))
            for j in range(3):
                b.add('blob', (px + j * .3, 3.2 * s + j * 1.2, pz + j * .2), (1.2 + j * .5,) * 3,
                      col=color.rgb(.38, .36, .36), wobble=.3)
            for _ in range(3):
                h = rng.uniform(.8, 1.8)
                ox, oz = polar(rng.uniform(0, 360), rng.uniform(1.5, 2.2) * s)
                b.add('cone4', (px + ox, h / 2, pz + oz), (.5, h, .5), rot=(rng.uniform(-15, 15), rng.uniform(0, 90), 0),
                      col=OBSIDIAN)

    def build_torterra(self, x, z, r, back, tree):
        """Antre de Torterra : grand arbre au fond du massif, racines géantes qui descendent vers le camp,
        porte de pierre en ruine couverte de mousse, fougères."""
        st, b, rng = self.st, self.st.b, self.st.rng
        tx, tz, depth = tree
        bark = color.rgb(.34, .24, .16)
        b.add('trunk', (tx, 3.2, tz), (2.6, 6.4, 2.6), col=bark, grad=.4)
        st._canopy(b, tx, 8.0, tz, min(3.6, depth + 1), 2.6, color.rgb(.14, .44, .15), n=9)
        # racines : de gros segments qui partent du tronc et plongent vers le camp
        toward = math.degrees(math.atan2(x - tx, z - tz))
        for k in range(7):
            a = toward + (k - 3) * 26 + rng.uniform(-8, 8)
            prev = (tx, 1.6, tz)
            L = rng.uniform(5.5, 8.5) if abs(k - 3) < 2 else rng.uniform(3.5, 5.5)
            for j in range(1, 5):
                t = j / 4
                px, pz = polar(a + math.sin(j * 1.7 + k) * 8, L * t + 1, tx, tz)
                cur = (px, 1.6 * (1 - t) ** 1.5 + .15, pz)
                seg = math.hypot(cur[0] - prev[0], cur[2] - prev[2])
                mid = ((prev[0] + cur[0]) / 2, (prev[1] + cur[1]) / 2, (prev[2] + cur[2]) / 2)
                w = 1.05 * (1 - t * .6)
                b.add('sphere_lo', prev, w * 1.02, col=shade(bark, .95))          # jointure (pas de coupure visible)
                b.add('cyl8', mid, (w, math.hypot(seg, prev[1] - cur[1]) + .2, w),
                      rot=(90 + math.degrees(math.atan2(prev[1] - cur[1], seg)), math.degrees(math.atan2(cur[0] - prev[0], cur[2] - prev[2])), 0),
                      col=shade(bark, rng.uniform(.9, 1.1)), cap=(color.rgb(.3, .48, .2), .7))
                prev = cur
        # porte en ruine entre le camp et l'arbre
        gx, gz = polar(back, 7.2, x, z)
        stone = color.rgb(.56, .56, .5)
        for s_ in (-1, 1):
            px, pz = polar(back + 90, 1.9 * s_, gx, gz)
            for k in range(3):
                b.add('box', (px, .7 + k * 1.3, pz), (1.1 - k * .05, 1.35, 1.1), rot=(rng.uniform(-3, 3), back + rng.uniform(-6, 6), 0),
                      col=shade(stone, rng.uniform(.85, 1.02)), cap=(color.rgb(.3, .5, .22), .9))
        b.add('box', (gx, 4.3, gz), (5.2, .9, 1.3), rot=(0, back + 90, rng.uniform(-4, 4)), col=shade(stone, .9),
              cap=(color.rgb(.3, .5, .22), .9))
        b.add('blob_lo', (gx, 4.9, gz), (3.6, .8, 1.7), rot=(0, back + 90, 0), col=color.rgb(.24, .46, .2), wobble=.3, light=.2)
        for k in range(5):                           # lianes qui pendent du linteau
            px, pz = polar(back + 90, (k - 2) * 1.0, gx, gz)
            h = rng.uniform(1.2, 2.6)
            b.add('cyl6', (px, 4.0 - h / 2, pz), (.1, h, .1), col=color.rgb(.2, .45, .16))
        for k in range(3):                           # blocs tombés, moussus
            px, pz = polar(back + rng.uniform(-70, 70), rng.uniform(6.2, 8), x, z)
            t = rng.uniform(.5, .9)
            b.add(rng.choice(ROCKS), (px, t * .3, pz), (t * 1.8, t * 1.1, t * 1.4), rot=(0, rng.uniform(0, 360), 0),
                  col=shade(stone, .9), cap=(color.rgb(.3, .5, .22), .9))
