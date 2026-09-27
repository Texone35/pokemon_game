"""Effets visuels : particules lumineuses, explosions, éclairs, flux animés, météo des arènes."""
import bisect
import math
import random

from ursina import Entity, Vec3, color, curve, destroy

from game.world.geometry import MeshBuilder


def ring_mesh(parent, col, emissive=.8):
    return MeshBuilder().add('ring_thin', (0, 0, 0), (1, .5, 1), col=col).entity(parent=parent, emissive=emissive)


def orient(e, v):
    """Tourne l'entité dans la direction v."""
    if v.length() > 1e-4:
        e.rotation = Vec3(-math.degrees(math.atan2(v.y, math.hypot(v.x, v.z))), math.degrees(math.atan2(v.x, v.z)), 0)


def blob(parent, col, scale, glow, prim='sphere_lo'):
    """Petit élément animé : nœud Panda3D nu (bien plus léger qu'une entité Ursina)."""
    node = MeshBuilder().add(prim, (0, 0, 0), 1, col=color.white).static(parent, emissive=glow, col=col)
    node.set_scale(*(scale if isinstance(scale, (tuple, list)) else (scale,) * 3))
    return node


class Flow:
    """Éléments qui glissent en boucle le long d'un trajet (courant de la rivière...)."""

    def __init__(self, parent, pts, count, col, size, speed, jitter=0.0, glow=1.0, rng=random):
        self.pts = [Vec3(*p) for p in pts]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + (b - a).length())
        self.length = max(self.cum[-1], .01)
        self.speed = speed
        self.t = 0.0
        self.centre = sum(self.pts, Vec3(0, 0, 0)) / len(self.pts)
        self.reach = max((p - self.centre).length() for p in self.pts)
        self.items = []
        for i in range(count):
            e = blob(parent, col, size, glow)
            self.items.append((e, self.length * (i + rng.random()) / count, rng.uniform(-jitter, jitter)))
        self.update(0)

    def _at(self, d):
        i = min(bisect.bisect_right(self.cum, d) - 1, len(self.pts) - 2)
        a, b = self.pts[i], self.pts[i + 1]
        seg = self.cum[i + 1] - self.cum[i]
        k = (d - self.cum[i]) / seg if seg else 0
        return a + (b - a) * k, (b - a) / seg if seg else Vec3(0, 0, 1)

    def update(self, dt, focus=None, view=70):
        self.t += dt * self.speed
        if focus is not None and (Vec3(focus.x, 0, focus.z) - self.centre).length() > self.reach + view:
            return          # trop loin de la caméra : inutile d'animer
        for e, off, j in self.items:
            p, d = self._at((self.t + off) % self.length)
            if j:
                p = p + Vec3(d.z, 0, -d.x) * j
            e.set_pos(p.x, p.y, p.z)


# ---------------------------------------------------------------- météo
WEATHER = {
    # couleur, taille (x, y, z), vitesse verticale, dérive horizontale, lumineux
    'sable': (color.rgb(.9, .78, .55), (.12, .12, .12), -.3, 5.0, False),
    'pollen': (color.rgb(.7, 1, .35), (.22, .04, .14), -.9, 1.4, True),
    'orage': (color.rgb(.75, .95, 1), (.06, .7, .06), -22, .4, True),
    'pluie': (color.rgb(.6, .8, 1), (.05, .8, .05), -26, .3, True),
    'soleil': (color.rgb(1, .6, .15), (.14, .14, .14), 2.2, .6, True),
}


class ArenaWeather:
    """Particules météo limitées au cercle d'une arène (+ éclairs pour l'orage)."""

    def __init__(self, parent, centre, radius, kind, type_color, count=40, rng=random):
        self.parent = parent
        self.centre, self.radius, self.kind = Vec3(centre[0], 0, centre[1]), radius, kind
        col, size, self.vy, self.drift, glow = WEATHER[kind]
        self.top = 9 if kind in ('orage', 'pluie') else 6
        self.rng = rng
        self.items = []
        for _ in range(count):
            e = blob(parent, col, size, 1.0 if glow else .4, prim='box')
            self.items.append([e, self._random_pos(), rng.uniform(0, math.tau)])
        self.type_color = type_color
        self._t = 0
        self._bolt = rng.uniform(2, 5)

    def _random_pos(self, y=None):
        a, r = self.rng.uniform(0, math.tau), math.sqrt(self.rng.random()) * self.radius
        return Vec3(self.centre.x + math.sin(a) * r, self.rng.uniform(0, self.top) if y is None else y,
                    self.centre.z + math.cos(a) * r)

    def update(self, dt, focus=None, view=70):
        self._t += dt
        if focus is not None and (Vec3(focus.x, 0, focus.z) - self.centre).length() > self.radius + view:
            return
        for it in self.items:
            e, p, ph = it
            p.y += self.vy * dt
            p.x += math.sin(self._t * 1.3 + ph) * self.drift * dt
            p.z += math.cos(self._t * .9 + ph) * self.drift * .5 * dt
            if p.y < 0 or p.y > self.top or (p.x - self.centre.x) ** 2 + (p.z - self.centre.z) ** 2 > self.radius ** 2:
                it[1] = p = self._random_pos(self.top if self.vy < 0 else 0)
            e.set_pos(p.x, p.y, p.z)
            if self.kind == 'pollen':
                e.set_h(e.get_h() + dt * 180)
        if self.kind == 'orage':
            self._bolt -= dt
            if self._bolt <= 0:
                self._bolt = self.rng.uniform(2.5, 6)
                lightning(self.parent, self._random_pos(0), color.rgb(1, .95, .4), height=30)


# ==================================================================== particules lumineuses
# Toutes les attaques sont dessinées avec des halos lumineux doux (texture ronde
# en dégradé, mélange additif) plutôt qu'avec des cubes ou des sphères pleines.

_GLOW_TEX = None
_QUAD = None


def glow_texture():
    """Texture ronde : blanche au centre, transparente sur les bords."""
    global _GLOW_TEX
    if _GLOW_TEX is None:
        from panda3d.core import PNMImage, Texture
        n = 64
        img = PNMImage(n, n, 4)
        for i in range(n):
            for j in range(n):
                r = math.hypot((i + .5) / n * 2 - 1, (j + .5) / n * 2 - 1)
                img.set_xel_a(i, j, 1, 1, 1, max(0.0, 1 - r) ** 1.7)
        tex = Texture('glow')
        tex.load(img)
        _GLOW_TEX = tex
    return _GLOW_TEX


def _quad():
    global _QUAD
    if _QUAD is None:
        from ursina import load_model
        _QUAD = load_model('quad', use_deepcopy=True)
        _QUAD.set_texture(glow_texture(), 1)
    return _QUAD


def _glow_state(node):
    from panda3d.core import ColorBlendAttrib, TransparencyAttrib
    node.set_transparency(TransparencyAttrib.M_alpha)
    node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                          ColorBlendAttrib.O_one))
    node.set_depth_write(False)
    # Ursina travaille en OpenGL moderne : il faut un shader (le sien, sans éclairage)
    from ursina import Vec2
    from ursina.shaders import unlit_shader
    if not unlit_shader.compiled:
        unlit_shader.compile()
    node.set_shader(unlit_shader._shader, 1)
    node.set_shader_input('texture_scale', Vec2(1, 1))
    node.set_shader_input('texture_offset', Vec2(0, 0))
    node.set_bin('fixed', 50)


def glow_sprite(parent, col, size):
    """Halo lumineux (toujours face à la caméra) attaché à `parent`."""
    node = _quad().copy_to(parent)
    node.set_billboard_point_eye()
    _glow_state(node)
    node.set_scale(size)
    node.set_color_scale(col[0], col[1], col[2], col[3] if len(col) > 3 else 1)
    return node


class Particles:
    """Réserve de halos lumineux recyclés : étincelles, flammes, gouttes, poussière..."""

    def __init__(self, parent, pool=420):
        self.root = parent.attach_new_node('particles')
        _glow_state(self.root)
        self.free, self.active = [], []
        for _ in range(pool):
            n = _quad().copy_to(self.root)
            n.set_billboard_point_eye()
            n.stash()
            self.free.append(n)

    def emit(self, pos, col, size=.4, life=.5, vel=(0, 0, 0), grow=1.0, gravity=0.0, drag=0.0, alpha=1.0):
        if self.free:
            n = self.free.pop()
            n.unstash()
        elif self.active:
            n = self.active.pop(0)[0]
        else:
            return
        self.active.append([n, pos[0], pos[1], pos[2], vel[0], vel[1], vel[2], life, 0.0, size, grow,
                            col[0], col[1], col[2], alpha, gravity, drag])

    def update(self, dt):
        keep = []
        for p in self.active:
            p[8] += dt
            t = p[8] / p[7]
            if t >= 1:
                p[0].stash()
                self.free.append(p[0])
                continue
            p[5] -= p[15] * dt
            if p[16]:
                k = max(0.0, 1 - p[16] * dt)
                p[4] *= k
                p[5] *= k
                p[6] *= k
            p[1] += p[4] * dt
            p[2] += p[5] * dt
            p[3] += p[6] * dt
            n = p[0]
            n.set_pos(p[1], p[2], p[3])
            n.set_scale(p[9] * (1 + (p[10] - 1) * t))
            n.set_color_scale(p[11], p[12], p[13], p[14] * (1 - t) ** 1.2)
            keep.append(p)
        self.active = keep

    def clear(self):
        for p in self.active:
            p[0].stash()
            self.free.append(p[0])
        self.active = []


PARTICLES = None        # réserve globale, créée par la partie (Match)


def rnd(a=1.0):
    return random.uniform(-a, a)


# Apparence des attaques selon le type du Pokémon qui les lance.
FX_STYLE = {
    'feu': {'core': (1, .6, .15), 'trail': (1, .38, .05), 'hot': (1, .85, .3), 'gravity': -2.5, 'spread': .4},
    'eau': {'core': (.35, .7, 1), 'trail': (.55, .85, 1), 'hot': (.85, .95, 1), 'gravity': 7, 'spread': .5},
    'electrik': {'core': (1, .92, .3), 'trail': (1, 1, .55), 'hot': (1, 1, .9), 'gravity': 0, 'spread': 1.4},
    'plante': {'core': (.45, .95, .3), 'trail': (.55, 1, .35), 'hot': (.85, 1, .6), 'gravity': 1, 'spread': .5},
    'glace': {'core': (.7, .92, 1), 'trail': (.8, .96, 1), 'hot': (1, 1, 1), 'gravity': .5, 'spread': .4},
    'roche': {'core': (.8, .68, .5), 'trail': (.65, .56, .45), 'hot': (.95, .9, .8), 'gravity': 2, 'spread': .5},
    'psy': {'core': (.85, .45, 1), 'trail': (.9, .6, 1), 'hot': (1, .85, 1), 'gravity': -.5, 'spread': .8},
    'normal': {'core': (1, .95, .85), 'trail': (.95, .9, .8), 'hot': (1, 1, 1), 'gravity': 1, 'spread': .5},
}


def style(type_key):
    return FX_STYLE.get(type_key, FX_STYLE['normal'])


def burst(parent, pos, col, n=8, speed=4.0, size=.25, life=.45):
    """Gerbe de particules lumineuses."""
    P = PARTICLES
    if P is None:
        return
    for _ in range(n):
        d = Vec3(rnd(), random.uniform(.2, 1.2), rnd()).normalized() * speed * random.uniform(.5, 1.1)
        P.emit(pos, col, size=size * random.uniform(1.6, 2.6), life=life * random.uniform(.7, 1.2),
               vel=(d.x, d.y, d.z), grow=.4, gravity=speed * .8, drag=2.5)


def explosion(pos, st, radius):
    """Explosion : éclair central, anneau qui s'étend et gerbe d'étincelles."""
    P = PARTICLES
    if P is None:
        return
    P.emit(pos + Vec3(0, .6, 0), st['hot'], size=radius * 2.6, life=.3, grow=1.4)
    P.emit(pos + Vec3(0, .4, 0), st['core'], size=radius * 3.4, life=.45, grow=1.2, alpha=.8)
    for i in range(18):
        a = math.tau * i / 18
        v = Vec3(math.sin(a), 0, math.cos(a)) * radius * 3.2
        P.emit(pos + Vec3(0, .3, 0), st['trail'], size=.9, life=.45, vel=(v.x, random.uniform(.5, 2), v.z),
               grow=.5, drag=3)
    for _ in range(14):
        v = Vec3(rnd(), random.uniform(.6, 1.6), rnd()).normalized() * random.uniform(3, 7)
        P.emit(pos + Vec3(0, .5, 0), st['hot'], size=.45, life=random.uniform(.4, .8), vel=(v.x, v.y, v.z),
               gravity=st['gravity'] * .6 + 4, drag=1.5, grow=.3)


def lightning(parent, pos, col, height=24):
    """Éclair en zigzag qui tombe du ciel, avec un flash au sol."""
    P = PARTICLES
    if P is None:
        return
    x, z = pos.x, pos.z
    y = pos.y + height
    while y > pos.y:
        ny = y - random.uniform(.8, 1.6)
        nx, nz = x + rnd(.7), z + rnd(.7)
        for k in range(3):
            t = k / 3
            P.emit((x + (nx - x) * t, y + (ny - y) * t, z + (nz - z) * t), col, size=.9, life=.28, grow=.6)
            P.emit((x + (nx - x) * t, y + (ny - y) * t, z + (nz - z) * t), (1, 1, 1), size=.35, life=.22)
        x, y, z = nx, ny, nz
    P.emit(pos + Vec3(0, .5, 0), (1, 1, .8), size=7, life=.25, grow=1.3)
