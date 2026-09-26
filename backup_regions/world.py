"""Monde ouvert : île découpée en 5 régions typiques, chacune gardée par un boss.

La place centrale (neutre) est reliée par un chemin au repaire du boss de
chaque région. Le boss attend dans une clairière ; on le défie sur place et le
combat se déroule dans cette clairière (voir battle.py). Le décor propre à
chaque région est construit par biomes.py.
"""
import bisect
import math
import random

import numpy as np
from ursina import Entity, Mesh, Text, Vec3, Vec4, camera, color, held_keys, lerp, mouse, time

import biomes
import config as C
from biomes import polar
from creatures import Creature
from emblems import add_emblem
from geometry import MeshBuilder, set_environment

HUB_GRASS = color.rgb(.42, .72, .32)
HUB_GRASS2 = color.rgb(.36, .64, .28)
STONE = color.rgb(.78, .76, .72)
WHITE_BALL = color.rgb(.97, .97, .97)
GOLD = color.rgb(1, .82, .2)
HUB_SKY = (.62, .8, .95, 1)
R = C.BATTLE_ARENA_RADIUS
CELL = 8.0        # taille des cases de la grille de collision


def _seg_dist(px, pz, ax, az, bx, bz):
    """Distance d'un point au segment [A, B] (plan XZ)."""
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / L2))
    cx, cz = ax + dx * t, az + dz * t
    return math.hypot(px - cx, pz - cz)


def _smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _blob(parent, col, scale, glow):
    return MeshBuilder().add('sphere_lo', (0, 0, 0), 1, col=color.white).entity(
        parent=parent, emissive=glow, color=col, scale=scale)


# ==================================================================== animations
class Flow:
    """Éléments qui glissent en boucle le long d'un trajet (lave, cascade...)."""

    def __init__(self, parent, pts, count, col, size, speed, jitter=0.0, glow=1.0, jitter_axis=None, rng=random):
        self.pts = [Vec3(*p) for p in pts]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + (b - a).length())
        self.length = max(self.cum[-1], .01)
        self.speed = speed
        self.t = 0.0
        self.axis = Vec3(jitter_axis[0], 0, jitter_axis[1]) if jitter_axis else None
        self.items = []
        for i in range(count):
            e = _blob(parent, col, size, glow)
            off = self.length * (i + rng.random()) / count
            self.items.append((e, off, rng.uniform(-jitter, jitter)))
        self.update(0)

    def _at(self, d):
        i = min(bisect.bisect_right(self.cum, d) - 1, len(self.pts) - 2)
        a, b = self.pts[i], self.pts[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        k = (d - self.cum[i]) / seg if seg else 0
        return a + (b - a) * k, (b - a) / seg if seg else Vec3(0, 0, 1)

    def update(self, dt):
        self.t += dt * self.speed
        for e, off, j in self.items:
            p, d = self._at((self.t + off) % self.length)
            if j:
                side = self.axis if self.axis is not None else Vec3(d.z, 0, -d.x)
                p = p + side * j
            e.position = p


class Smoke:
    """Panache de fumée / vapeur : des bouffées montent, grossissent et s'estompent."""

    def __init__(self, parent, pos, spread, height, count, col, size, rng=random):
        self.pos, self.height, self.size = Vec3(*pos), height, size
        self.col = col
        self.items = []
        for i in range(count):
            e = _blob(parent, col, size, .25)
            ox, oz = rng.uniform(-spread, spread), rng.uniform(-spread, spread)
            self.items.append([e, i / count, ox, oz, rng.uniform(.8, 1.2)])
        self.update(0)

    def update(self, dt):
        c = self.col
        for it in self.items:
            e, k, ox, oz, sp = it
            k = (k + dt * .12 * sp) % 1
            it[1] = k
            e.position = self.pos + Vec3(ox * (1 + k) + k * 3, k * self.height, oz * (1 + k) + k * 1.5)
            e.scale = self.size * (.6 + 1.8 * k)
            e.color = color.rgba(c[0], c[1], c[2], (1 - k) * .6 * min(1, k * 8))


class Ambient:
    """Particules d'ambiance autour du joueur (braises, neige, pollen, poussière...)."""

    def __init__(self, parent, count=80, extent=18.0):
        self.extent = extent
        self.items = []
        rng = random.Random(3)
        for _ in range(count):
            e = MeshBuilder().add('box', (0, 0, 0), 1, col=color.white).entity(parent=parent, emissive=1.0)
            e.enabled = False
            self.items.append([e, Vec3(rng.uniform(-extent, extent), rng.uniform(0, 12), rng.uniform(-extent, extent)),
                               rng.uniform(0, math.tau), rng.uniform(.7, 1.3)])
        self.kind = None
        self._t = 0

    def set_kind(self, type_key):
        if type_key == self.kind:
            return
        self.kind = type_key
        for it in self.items:
            it[0].enabled = type_key is not None
        if type_key is None:
            return
        p = C.TYPES[type_key]['particles']
        for it in self.items:
            it[0].color = p['color']
            it[0].scale = p['size'] * it[3]
            it[0].set_shader_input('emissive', 1.0 if p['glow'] else .3)

    def update(self, dt, focus):
        if self.kind is None:
            return
        self._t += dt
        p = C.TYPES[self.kind]['particles']
        E = self.extent
        for it in self.items:
            e, pos, ph, sp = it
            pos.y += p['rise'] * sp * dt
            pos.x += math.sin(self._t * .9 + ph) * p['drift'] * dt
            pos.z += math.cos(self._t * .7 + ph * 1.3) * p['drift'] * dt
            # rebouclage dans un cube centré sur le joueur
            rx, rz = pos.x - focus.x, pos.z - focus.z
            if rx > E:
                pos.x -= 2 * E
            elif rx < -E:
                pos.x += 2 * E
            if rz > E:
                pos.z -= 2 * E
            elif rz < -E:
                pos.z += 2 * E
            if pos.y > 12:
                pos.y -= 12
            elif pos.y < 0:
                pos.y += 12
            e.position = pos
            if self.kind == 'plante':
                e.rotation_y += dt * 200


# ==================================================================== monde
class Overworld(Entity):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.rng = random.Random(7)
        self.regions = []
        self.segments = []      # chemins (pour éviter d'y mettre du décor)
        self.obstacles = []     # (x, z, rayon) : arbres, rochers, volcans...
        self.reserved = []      # zones sans décor mais praticables (lacs gelés)
        self.grid = {}
        self.flows, self.smokes = [], []
        self.in_battle = False

        set_environment(fog_range=(70, 240))
        self._layout()
        self._build_ground()
        self._build_paths()
        self._build_hub()
        self._build_lairs()
        self._build_regions()
        self._build_hub_nature()
        self.ambient = Ambient(self)

        self.player = Creature('pikachu', parent=self, position=(0, 0, -12))
        self.player.rotation_y = 180
        self.cam_yaw = 0.0
        self.cam_pitch = 24.0
        self.cam_dist = 13.0
        self.near_boss = None
        self.current = 'start'
        self.fog = Vec4(*HUB_SKY)
        self._t = 0

        self._build_ui()
        self.snap_camera()

    # ================================================================ layout
    def _layout(self):
        for k, type_key in enumerate(C.TYPE_ORDER):
            h = 72 * k                          # 0 = nord (+z), sens horaire
            d = Vec3(math.sin(math.radians(h)), 0, math.cos(math.radians(h)))
            self.regions.append({'type': type_key, 'heading': h, 'dir': d, 'lair': d * C.LAIR_DISTANCE,
                                 'beaten': False, 'boss': None, 'crown': None})

    def region(self, type_key):
        return next(r for r in self.regions if r['type'] == type_key)

    def region_at(self, x, z):
        if math.hypot(x, z) < C.HUB_RADIUS:
            return None
        a = math.degrees(math.atan2(x, z)) % 360
        return self.regions[int(((a + 36) % 360) // 72) % 5]

    # ================================================================ placement (utilisé par biomes.py)
    def _cells(self, x, z, r):
        for i in range(int(math.floor((x - r) / CELL)), int(math.floor((x + r) / CELL)) + 1):
            for j in range(int(math.floor((z - r) / CELL)), int(math.floor((z + r) / CELL)) + 1):
                yield i, j

    def block(self, x, z, r):
        o = (x, z, r)
        self.obstacles.append(o)
        for c in self._cells(x, z, r):
            self.grid.setdefault(c, []).append(o)

    def reserve(self, x, z, r):
        self.reserved.append((x, z, r))

    def _nearby(self, x, z, r):
        seen = set()
        for c in self._cells(x, z, r):
            for o in self.grid.get(c, ()):
                if id(o) not in seen:
                    seen.add(id(o))
                    yield o

    def free(self, x, z, rad, gap=1.0, path_clear=5.5):
        r = math.hypot(x, z)
        if r + rad > C.WORLD_RADIUS - 1.5 or r - rad < C.HUB_RADIUS + 1:
            return False
        for reg in self.regions:
            if math.hypot(x - reg['lair'].x, z - reg['lair'].z) < R + 4 + rad:
                return False
        if any(_seg_dist(x, z, *s) < path_clear + rad for s in self.segments):
            return False
        if any(math.hypot(x - ox, z - oz) < orad + rad for ox, oz, orad in self.reserved):
            return False
        return not any(math.hypot(x - ox, z - oz) < orad + rad + gap for ox, oz, orad in self._nearby(x, z, rad + gap))

    def spot(self, h, rad, r_min=None, r_max=None, gap=1.0, tries=30, path_clear=5.5):
        """Emplacement libre au hasard dans la région de cap h (ou None).

        path_clear : largeur laissée libre de chaque côté des chemins (la caméra y passe).
        """
        r_min = r_min or C.HUB_RADIUS + 2
        r_max = r_max or C.WORLD_RADIUS - 2
        for _ in range(tries):
            r = math.sqrt(self.rng.uniform(r_min ** 2, r_max ** 2))
            x, z = polar(h + self.rng.uniform(-36, 36), r)
            if self.free(x, z, rad, gap, path_clear):
                return x, z
        return None

    def flow(self, pts, count, col, size, speed, jitter=0.0, glow=1.0, jitter_axis=None):
        self.flows.append(Flow(self, pts, count, col, size, speed, jitter, glow, jitter_axis, self.rng))

    def smoke(self, pos, spread, height, count, col, size=1.0):
        self.smokes.append(Smoke(self, pos, spread, height, count, col, size, self.rng))

    # ================================================================ construction
    def _build_ground(self):
        """Sol en grille polaire : chaque région a ses couleurs, fondues aux frontières."""
        W = C.WORLD_RADIUS
        radii = np.arange(0, W + 12.01, 2.0)
        S = 288
        rr, aa = np.meshgrid(radii, np.linspace(0, 360, S + 1), indexing='ij')
        x = np.sin(np.radians(aa)) * rr
        z = np.cos(np.radians(aa)) * rr
        y = np.where(rr > W, -(rr - W) / 8 * 1.6, 0.0)
        noise = np.clip(.5 + .3 * np.sin(x * .13 + np.sin(z * .07) * 2) * np.cos(z * .11 + np.sin(x * .05) * 1.5)
                        + .2 * np.sin(x * .41 + z * .37), 0, 1)[..., None]

        g1 = np.array([tuple(C.TYPES[k]['ground']) for k in C.TYPE_ORDER])
        g2 = np.array([tuple(C.TYPES[k]['ground2']) for k in C.TYPE_ORDER])
        sh = np.array([tuple(C.TYPES[k]['shore']) for k in C.TYPE_ORDER])
        rel = (aa + 36) % 360
        k = (rel // 72).astype(int) % 5
        delta = rel - k * 72 - 36                         # -36..36 dans la région
        arc = (36 - np.abs(delta)) * math.pi / 180 * np.maximum(rr, 1)
        w_self = (.5 + .5 * _smoothstep(0, 10, arc))[..., None]
        nb = np.where(delta > 0, (k + 1) % 5, (k - 1) % 5)

        def pick(a, b, idx):
            return a[idx] * (1 - noise) + b[idx] * noise

        col = pick(g1, g2, k) * w_self + pick(g1, g2, nb) * (1 - w_self)
        shore = sh[k] * w_self + sh[nb] * (1 - w_self)
        ws = _smoothstep(W - 8, W - 1, rr)[..., None]
        col = col * (1 - ws) + shore * ws
        wu = (_smoothstep(W + 1, W + 9, rr) * .6)[..., None]
        col = col * (1 - wu) + np.array([.2, .42, .55, 1]) * wu
        hub = np.array(tuple(HUB_GRASS)) * (1 - noise) + np.array(tuple(HUB_GRASS2)) * noise
        wh = (1 - _smoothstep(C.HUB_RADIUS - 4, C.HUB_RADIUS + 6, rr))[..., None]
        col = col * (1 - wh) + hub * wh
        col[..., 3] = 1

        NR, NA = rr.shape
        verts = np.stack([x, y, z], -1).reshape(-1, 3)
        idx = np.arange(NR * NA).reshape(NR, NA)
        a, b = idx[:-1, :-1], idx[:-1, 1:]
        c, d = idx[1:, :-1], idx[1:, 1:]
        tris = np.stack([a, c, b, b, c, d], -1).reshape(-1)
        norms = np.tile([0.0, 1.0, 0.0], (len(verts), 1))
        MeshBuilder().add_raw(verts, tris, norms, col.reshape(-1, 4)).entity(parent=self)

        sea = MeshBuilder().add('disc', (0, -.9, 0), (1200, 1, 1200), col=color.rgb(.2, .55, .85))
        sea.entity(parent=self, emissive=.35)

    def _build_paths(self):
        for k, reg in enumerate(self.regions):
            b = MeshBuilder()
            col = biomes.PATH_COLORS[reg['type']]
            h = reg['heading']
            r0, r1 = 8.6, C.LAIR_DISTANCE - R + 1.5
            side = Vec3(math.cos(math.radians(h)), 0, -math.sin(math.radians(h)))
            pts = []
            steps = int((r1 - r0) / 5) + 1
            for i in range(steps + 1):
                r = r0 + (r1 - r0) * i / steps
                taper = math.sin(math.pi * i / steps)
                p = reg['dir'] * r + side * (3.2 * math.sin(r * .11 + k * 1.7) * taper)
                pts.append(p)
            width = 3.4
            for a, c in zip(pts, pts[1:]):
                dv = c - a
                mid = (a + c) / 2
                yaw = math.degrees(math.atan2(dv.x, dv.z))
                b.add('box', (mid.x, .02, mid.z), (width, .06, dv.length()), rot=(0, yaw, 0), col=col)
                b.add('disc', (c.x, .021, c.z), (width, .06, width), col=col)
                self.segments.append((a.x, a.z, c.x, c.z))
            b.entity(parent=self)

    def _build_hub(self):
        b = MeshBuilder()
        glow = MeshBuilder()
        b.add('disc', (0, .03, 0), (18, .06, 18), col=STONE)
        b.add('ring_thin', (0, .05, 0), (18.6, .1, 18.6), col=color.rgb(.6, .58, .55))
        # fontaine surmontée d'une Poké Ball
        b.add('ring', (0, .45, 0), (6.4, .9, 6.4), col=color.rgb(.7, .7, .74))
        b.add('disc', (0, .6, 0), (5.7, .05, 5.7), col=color.rgb(.35, .7, .95))
        b.add('cyl', (0, 1.4, 0), (.9, 2.8, .9), col=color.rgb(.7, .7, .74))
        by = 3.9
        b.add('dome', (0, by, 0), (2.2, 2.2, 2.2), col=color.rgb(.92, .15, .15))
        b.add('dome', (0, by, 0), (2.2, 2.2, 2.2), rot=(180, 0, 0), col=WHITE_BALL)
        b.add('cyl_hi', (0, by, 0), (2.24, .16, 2.24), col=color.rgb(.1, .1, .1))
        b.add('cyl', (0, by, 1.06), (.6, .12, .6), rot=(90, 0, 0), col=color.rgb(.1, .1, .1))
        b.add('cyl', (0, by, 1.1), (.4, .12, .4), rot=(90, 0, 0), col=WHITE_BALL)
        self.block(0, 0, 3.6)
        # lampadaires autour de la place
        for i in range(10):
            x, z = polar(i * 36 + 18, 8.2)
            b.add('cyl6', (x, 1.5, z), (.18, 3, .18), col=color.rgb(.25, .25, .28))
            glow.add('sphere', (x, 3.1, z), .45, col=color.rgb(1, .95, .7))
            self.block(x, z, .3)
        # panneaux indiquant chaque région, au départ des chemins
        for reg in self.regions:
            x, z = polar(reg['heading'] + 17, 12)
            biomes.signpost(b, glow, reg['type'], x, z, reg['heading'])
            self.block(x, z, .4)
        b.entity(parent=self)
        glow.entity(parent=self, emissive=.8)

    def _build_hub_nature(self):
        """Quelques arbres et fleurs sur la prairie centrale."""
        b = MeshBuilder()
        rng = self.rng
        placed = 0
        for _ in range(400):
            if placed >= 26:
                break
            x, z = polar(rng.uniform(0, 360), rng.uniform(12.5, C.HUB_RADIUS + 1))
            if any(_seg_dist(x, z, *s) < 3.5 for s in self.segments):
                continue
            if any(math.hypot(x - ox, z - oz) < orad + 2 for ox, oz, orad in self._nearby(x, z, 2)):
                continue
            s = rng.uniform(.8, 1.2)
            b.add('cyl6', (x, 1.0 * s, z), (.5 * s, 2 * s, .5 * s), col=color.rgb(.5, .34, .2))
            g = color.rgb(.25, .62 + rng.uniform(-.08, .06), .22)
            b.add('sphere', (x, 2.9 * s, z), (2.8 * s, 2.4 * s, 2.8 * s), col=g)
            b.add('sphere', (x + .6 * s, 2.5 * s, z + .3 * s), (1.6 * s, 1.4 * s, 1.6 * s), col=g)
            self.block(x, z, .75 * s)
            placed += 1
        for _ in range(90):
            x, z = polar(rng.uniform(0, 360), rng.uniform(10, C.HUB_RADIUS))
            c = rng.choice([color.rgb(1, .4, .5), color.rgb(1, .92, .3), color.white, color.rgb(.6, .5, 1)])
            b.add('sphere_lo', (x, .15, z), .28, col=c)
        b.entity(parent=self)

    def _build_lairs(self):
        """Clairière du boss : sol du type, cercle de combat, piliers à emblème."""
        for reg in self.regions:
            t = C.TYPES[reg['type']]
            p, h = reg['lair'], reg['heading']
            b = MeshBuilder()
            glow = MeshBuilder()
            b.add('disc', (p.x, .025, p.z), ((R + 1.5) * 2, .04, (R + 1.5) * 2), col=t['floor'])
            b.add('disc', (p.x, .03, p.z), (R * 1.25, .04, R * 1.25), col=lerp(t['floor'], t['light'], .15))
            b.add('ring_thin', (p.x, .05, p.z), (R * 2, .04, R * 2), col=color.white)
            b.add('ring_thin', (p.x, .05, p.z), (7, .04, 7), col=color.white)
            b.add('box', (p.x, .05, p.z), (R * 2 - 1, .04, .22), rot=(0, h, 0), col=color.white)
            for i in range(6):
                x, z = polar(h + 30 + i * 60, R + 2.6)
                x, z = p.x + x, p.z + z
                b.add('cyl', (x, 2.2, z), (1.1, 4.4, 1.1), col=color.rgb(.92, .9, .86))
                b.add('box', (x, 4.5, z), (1.6, .3, 1.6), rot=(0, h, 0), col=t['dark'])
                add_emblem(glow, reg['type'], (x, 5.6, z), .55)
                self.block(x, z, .8)
            b.entity(parent=self)
            glow.entity(parent=self, emissive=.8)

            emb = MeshBuilder()
            add_emblem(emb, reg['type'], (0, 0, 0), 2.4)
            reg['emblem'] = emb.entity(parent=self, position=(p.x, 13, p.z), emissive=.55)
            e = t['pokemon']
            reg['label'] = Text(parent=self, text=f"BOSS : {e['name']}  Nv.{e['level']}", position=(p.x, 17.5, p.z),
                                billboard=True, scale=60, origin=(0, 0), color=t['light'])
            boss = Creature(e['species'], parent=self, position=(p.x, 0, p.z), scale=e['scale'])
            boss.face((-reg['dir'].x, -reg['dir'].z))
            reg['boss'] = boss

    def _build_regions(self):
        for reg in self.regions:
            b, glow, water = MeshBuilder(), MeshBuilder(), MeshBuilder()
            biomes.decorate(self, reg['type'], reg['heading'], b, glow, water)
            b.entity(parent=self)
            reg['glow'] = glow.entity(parent=self, emissive=.9) if glow.count else None
            if water.count:
                water.entity(parent=self, emissive=.35)

    # ================================================================ UI
    def _build_ui(self):
        self.ui = Entity(parent=camera.ui)
        self.prompt = Entity(parent=self.ui, y=-.36, enabled=False)
        Entity(parent=self.prompt, model='quad', color=color.rgba(0, 0, 0, .6), scale=(1.15, .06))
        self.prompt_text = Text(parent=self.prompt, text='', origin=(0, 0), scale=1.2, z=-.01,
                                color=color.rgb(1, .95, .6))
        Text(parent=self.ui, text='ZQSD / WASD : se déplacer   Maj : courir   Clic droit + souris : caméra   '
                                  'Molette : zoom   E : défier un boss',
             position=(0, .475), origin=(0, 0), scale=.85, color=color.rgba(1, 1, 1, .85))
        self.region_text = Text(parent=self.ui, text='', position=(.86, .44), origin=(.5, 0), scale=1.1)

        # boss vaincus
        self.badge_icons = {}
        Text(parent=self.ui, text='BOSS VAINCUS', position=(-.86, .44), scale=.9, origin=(-.5, 0))
        for i, reg in enumerate(self.regions):
            t = C.TYPES[reg['type']]
            Entity(parent=self.ui, model='circle', color=color.rgba(0, 0, 0, .5), scale=.052,
                   position=(-.84 + i * .058, .4, .01))
            self.badge_icons[reg['type']] = Entity(parent=self.ui, model='circle', scale=.04,
                                                   color=color.rgba(t['color'][0], t['color'][1], t['color'][2], .25),
                                                   position=(-.84 + i * .058, .4))
        self.badge_text = Text(parent=self.ui, text='0 / 5', position=(-.56, .4), origin=(-.5, 0), scale=.9)

        # mini-carte : une part colorée par région
        self.map_root = Entity(parent=self.ui, position=(-.75, -.31))
        rad = .13
        self.map_scale = rad / C.WORLD_RADIUS
        Entity(parent=self.map_root, model='circle', color=color.rgba(.1, .2, .35, .75), scale=rad * 2.35, z=.02)
        verts, tris, cols = [], [], []
        for k, reg in enumerate(self.regions):
            c = lerp(C.TYPES[reg['type']]['ground'], C.TYPES[reg['type']]['color'], .45)
            centre = len(verts)
            verts.append((0, 0, 0))
            cols.append(c)
            for i in range(19):
                a = math.radians(reg['heading'] - 36 + i * 4)
                verts.append((math.sin(a) * rad, math.cos(a) * rad, 0))
                cols.append(c)
            for i in range(18):
                tris.append((centre, centre + 1 + i, centre + 2 + i))
        Entity(parent=self.map_root, model=Mesh(vertices=verts, triangles=tris, colors=cols), z=.01, double_sided=True)
        Entity(parent=self.map_root, model='circle', color=HUB_GRASS, scale=C.HUB_RADIUS * self.map_scale * 2, z=.005)
        for reg in self.regions:
            q = reg['lair'] * self.map_scale
            reg['map_dot'] = Entity(parent=self.map_root, model='circle', color=C.TYPES[reg['type']]['light'],
                                    position=(q.x, q.z, -.01), scale=.024)
            Entity(parent=self.map_root, model='circle', color=color.rgba(0, 0, 0, .6), position=(q.x, q.z, -.005), scale=.03)
        self.map_player = Entity(parent=self.map_root, model='circle', color=color.yellow, scale=.016, z=-.02)

    def refresh_badges(self):
        n = 0
        for reg in self.regions:
            if reg['beaten']:
                n += 1
                self.badge_icons[reg['type']].color = C.TYPES[reg['type']]['color']
                reg['map_dot'].color = GOLD
            if reg['beaten'] and reg['crown'] is None:
                b = MeshBuilder()
                b.add('ring', (0, 0, 0), (6, .45, 6), col=GOLD)
                reg['crown'] = b.entity(parent=self, position=(reg['lair'].x, 10.4, reg['lair'].z), emissive=.6)
                reg['label'].text = f"{C.TYPES[reg['type']]['pokemon']['name']} vaincu !"
                reg['label'].color = GOLD
        self.badge_text.text = f'{n} / 5'
        return n

    # ================================================================ combat sur place
    def enter_battle(self, reg):
        """Prépare le monde pour un combat dans le repaire : renvoie la position du joueur."""
        self.in_battle = True
        self.ui.enabled = False
        self.player.enabled = False
        if reg['boss']:
            reg['boss'].enabled = False
        return Vec3(self.player.position)

    def exit_battle(self, type_key, won, player_pos=None):
        reg = self.region(type_key)
        self.in_battle = False
        self.ui.enabled = True
        self.player.enabled = True
        if won:
            if reg['boss']:
                reg['boss'].disable()
                reg['boss'] = None
            reg['beaten'] = True
            p = player_pos if player_pos is not None else reg['lair'] - reg['dir'] * 8
        else:
            if reg['boss']:
                reg['boss'].enabled = True
            p = reg['lair'] - reg['dir'] * (R + 3)
        self.player.position = Vec3(p.x, 0, p.z)
        self.player.face((reg['dir'].x, reg['dir'].z))
        self.cam_yaw = reg['heading']
        self.snap_camera()

    # ================================================================ caméra / collisions
    def snap_camera(self):
        self._place_camera(1.0)

    def _place_camera(self, k):
        # la cible suit le joueur en douceur ; la caméra est toujours exactement
        # à la bonne distance/angle de la cible (pas de décalage en tournant)
        target = self.player.world_position + Vec3(0, 1.6, 0)
        self.cam_target = target if k >= 1 or not hasattr(self, 'cam_target') else lerp(self.cam_target, target, k)
        yaw, pitch = math.radians(self.cam_yaw), math.radians(self.cam_pitch)
        offset = Vec3(-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        camera.position = self.cam_target + offset * self.cam_dist
        camera.rotation = Vec3(self.cam_pitch, self.cam_yaw, 0)

    def _collide(self, pos, radius=.5):
        W = C.WORLD_RADIUS - 1.5
        r = math.hypot(pos.x, pos.z)
        if r > W:
            pos.x *= W / r
            pos.z *= W / r
        for ox, oz, orad in self._nearby(pos.x, pos.z, radius):
            dx, dz = pos.x - ox, pos.z - oz
            d = math.hypot(dx, dz)
            m = orad + radius
            if 0 < d < m:
                pos.x = ox + dx / d * m
                pos.z = oz + dz / d * m
        for reg in self.regions:
            boss = reg['boss']
            if boss is None:
                continue
            dx, dz = pos.x - boss.x, pos.z - boss.z
            d = math.hypot(dx, dz)
            m = C.TYPES[reg['type']]['pokemon']['radius'] + radius
            if 0 < d < m:
                pos.x = boss.x + dx / d * m
                pos.z = boss.z + dz / d * m
        return pos

    # ================================================================ boucle
    def _update_ambience(self, dt, reg):
        target = Vec4(*(C.TYPES[reg['type']]['sky'] if reg else HUB_SKY))
        if (self.fog - target).length() > .002:
            self.fog = lerp(self.fog, target, min(1, dt * 1.2))
            set_environment(fog_color=self.fog)
            self.game.sky.color = color.rgba(*self.fog)

    def update(self):
        dt = min(time.dt, .05)
        self._t += dt

        # --- décor animé (continue pendant les combats)
        for f in self.flows:
            f.update(dt)
        for s in self.smokes:
            s.update(dt)
        for reg in self.regions:
            reg['emblem'].rotation_y += dt * 40
            reg['emblem'].y = 13 + math.sin(self._t * 1.5 + reg['heading']) * .5
            if reg['crown']:
                reg['crown'].rotation_y -= dt * 30
            if reg['type'] == 'feu' and reg['glow']:   # la lave "respire"
                k = .5 + .5 * math.sin(self._t * 2.2)
                reg['glow'].set_shader_input('flash', Vec4(1, .85, .35, .12 * k))

        focus = self.player.position
        if self.in_battle and self.game.battle:
            focus = self.game.battle.root.position
        reg = self.region_at(focus.x, focus.z)
        self.ambient.set_kind(reg['type'] if reg else None)
        self.ambient.update(dt, focus)
        self._update_ambience(dt, reg)

        if self.in_battle:
            return

        # --- entrée dans une région
        if reg is not self.current:
            self.current = reg
            if reg:
                t = C.TYPES[reg['type']]
                self.region_text.text = f"{t['region']}  -  Région {t['name']}"
                self.region_text.color = t['light']
                self.game.banner.show(f"{t['region']}  -  Région {t['name']}", 2.5, text_color=t['light'])
            else:
                self.region_text.text = 'Place centrale'
                self.region_text.color = color.white

        # --- déplacement du joueur
        if mouse.right:
            self.cam_yaw += mouse.velocity[0] * 220
            self.cam_pitch = max(8, min(60, self.cam_pitch - mouse.velocity[1] * 120))

        ix = (held_keys['d'] or held_keys['right arrow']) - (held_keys['q'] or held_keys['a'] or held_keys['left arrow'])
        iz = (held_keys['z'] or held_keys['w'] or held_keys['up arrow']) - (held_keys['s'] or held_keys['down arrow'])
        yaw = math.radians(self.cam_yaw)
        fwd = Vec3(math.sin(yaw), 0, math.cos(yaw))
        right = Vec3(math.cos(yaw), 0, -math.sin(yaw))
        move = fwd * iz + right * ix
        moving = move.length() > 0
        if moving:
            speed = 9 * (1.6 if held_keys['shift'] else 1)
            move = move.normalized() * speed * dt
            self.player.position = self._collide(self.player.position + move)
            self.player.face((move.x, move.z), dt)
        self.player.animate(dt, moving)
        self._place_camera(min(1, dt * 8))

        # --- boss : il observe le joueur qui entre dans son repaire
        self.near_boss = None
        pp = self.player.position
        for r in self.regions:
            boss = r['boss']
            if boss is None:
                continue
            d = Vec3(pp.x - boss.x, 0, pp.z - boss.z)
            dist = d.length()
            boss.animate(dt)
            if dist < R + 4:
                boss.face((d.x, d.z), dt, 4)
            if dist < C.CHALLENGE_DISTANCE:
                self.near_boss = r
        if self.near_boss:
            t = C.TYPES[self.near_boss['type']]
            self.prompt_text.text = f"[E] Défier {t['pokemon']['name']}, boss de la région {t['name']} !"
            self.prompt.enabled = True
        else:
            self.prompt.enabled = False

        # --- mini-carte
        p = self.player.position * self.map_scale
        self.map_player.position = (p.x, p.z, -.02)

    def input(self, key):
        if self.in_battle:
            return
        if key == 'e' and self.near_boss:
            self.game.start_battle(self.near_boss['type'])
        elif key == 'scroll up':
            self.cam_dist = max(6, self.cam_dist - 1)
        elif key == 'scroll down':
            self.cam_dist = min(30, self.cam_dist + 1)
