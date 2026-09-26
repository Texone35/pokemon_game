"""Modèles 3D procéduraux des Pokémon et leurs animations simples.

Chaque Pokémon est découpé en quelques groupes (corps, tête, queue...) :
chaque groupe est un seul maillage, ce qui permet de l'animer sans multiplier
les entités.
"""
import math

from ursina import Entity, Vec3, Vec4, color

from geometry import MeshBuilder, flat_circle

BLACK = color.rgb(.08, .06, .06)
WHITE = color.rgb(1, 1, 1)


def _eyes(b, x, y, z, sx=.12, sy=.16, iris=BLACK, shine=True):
    for side in (-1, 1):
        b.add('sphere', (side * x, y, z), (sx, sy, sx * .7), col=iris)
        if shine:
            b.add('sphere', (side * x - side * .02, y + sy * .22, z + sx * .3), sx * .35, col=WHITE)


# ---------------------------------------------------------------- espèces
def build_pikachu(g):
    Y, BROWN, RED = color.rgb(1, .84, .15), color.rgb(.55, .33, .12), color.rgb(.9, .15, .12)
    b = g['body']
    b.add('sphere', (0, .52, 0), (.72, .82, .62), col=Y)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .07, .1), (.22, .14, .32), col=Y)
        b.add('sphere', (s * .3, .62, .2), (.14, .22, .14), rot=(30, 0, 0), col=Y)
    b.add('box', (0, .72, -.28), (.34, .07, .08), col=BROWN)
    b.add('box', (0, .56, -.3), (.3, .07, .08), col=BROWN)
    h = g['head']
    h.add('sphere', (0, .28, .02), (.8, .7, .68), col=Y)
    for s in (-1, 1):
        axis = Vec3(s * math.sin(math.radians(20)), math.cos(math.radians(20)), 0)
        centre = Vec3(s * .24, .68, -.02) + axis * .12
        h.add('cone', tuple(centre), (.17, .62, .11), rot=(0, 0, -s * 20), col=Y)
        h.add('cone', tuple(centre + axis * .23), (.1, .2, .07), rot=(0, 0, -s * 20), col=BLACK)
        h.add('sphere', (s * .27, .18, .27), (.17, .14, .08), col=RED)
    _eyes(h, .16, .36, .3, .12, .15)
    h.add('sphere', (0, .28, .36), .04, col=BLACK)
    t = g['tail']
    t.add('box', (0, .06, -.1), (.07, .24, .1), rot=(-40, 0, 0), col=BROWN)
    t.add('box', (0, .26, -.26), (.08, .12, .42), rot=(25, 0, 0), col=Y)
    t.add('box', (0, .6, -.42), (.08, .6, .38), rot=(-15, 0, 0), col=Y)
    return {'head_pivot': (0, .95, 0), 'tail_pivot': (0, .4, -.32)}


def build_salameche(g):
    O, CREAM, BLUE = color.rgb(1, .55, .22), color.rgb(1, .9, .55), color.rgb(.15, .3, .6)
    b = g['body']
    b.add('sphere', (0, .55, 0), (.7, .85, .64), col=O)
    b.add('sphere', (0, .5, .14), (.5, .62, .44), col=CREAM)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .08, .1), (.22, .16, .34), col=O)
        b.add('sphere', (s * .33, .66, .18), (.14, .26, .14), rot=(35, 0, s * 15), col=O)
    h = g['head']
    h.add('sphere', (0, .3, .04), (.72, .66, .7), col=O)
    h.add('sphere', (0, .2, .26), (.46, .34, .38), col=O)
    _eyes(h, .18, .36, .28, .12, .19, iris=BLUE)
    t = g['tail']
    t.add('cone', (0, .12, -.28), (.22, .7, .22), rot=(-65, 0, 0), col=O)
    f = g['glow']   # flamme de la queue (non éclairée)
    f.add('sphere', (0, .32, -.6), (.3, .42, .3), col=color.rgb(1, .45, .05))
    f.add('cone', (0, .55, -.6), (.2, .45, .2), col=color.rgb(1, .8, .15))
    return {'head_pivot': (0, .98, 0), 'tail_pivot': (0, .35, -.25), 'glow_parent': 'tail'}


def build_carapuce(g):
    B, SHELL, BELLY = color.rgb(.45, .75, .95), color.rgb(.58, .33, .14), color.rgb(1, .88, .55)
    b = g['body']
    b.add('sphere', (0, .55, 0), (.68, .8, .62), col=B)
    b.add('sphere', (0, .58, -.14), (.86, .9, .62), col=SHELL)
    b.add('sphere', (0, .55, .17), (.56, .72, .38), col=BELLY)
    b.add('cyl', (0, .58, -.12), (.9, .12, .66), col=color.rgb(.95, .95, .88))
    for s in (-1, 1):
        b.add('sphere', (s * .2, .08, .1), (.22, .16, .32), col=B)
        b.add('sphere', (s * .36, .64, .16), (.14, .26, .14), rot=(35, 0, s * 20), col=B)
    h = g['head']
    h.add('sphere', (0, .3, .06), (.74, .68, .7), col=B)
    _eyes(h, .17, .37, .32, .14, .19, iris=color.rgb(.45, .12, .1))
    t = g['tail']
    t.add('sphere', (0, .05, -.15), (.26, .26, .34), col=B)
    t.add('sphere', (0, .22, -.3), (.3, .3, .26), col=B)
    t.add('sphere', (0, .3, -.18), (.16, .16, .16), col=color.rgb(.35, .6, .85))
    return {'head_pivot': (0, .98, 0), 'tail_pivot': (0, .3, -.45)}


def build_bulbizarre(g):
    T, SPOT, BULB = color.rgb(.45, .8, .68), color.rgb(.2, .52, .45), color.rgb(.3, .68, .32)
    b = g['body']
    b.add('sphere', (0, .5, -.05), (.95, .66, 1.1), col=T)
    for sx in (-1, 1):
        for sz in (-1, 1):
            b.add('cyl', (sx * .3, .18, sz * .32), (.26, .36, .26), col=T)
            b.add('sphere', (sx * .3, .03, sz * .32 + .06), (.27, .12, .3), col=T)
    b.add('sphere', (.3, .65, .1), (.16, .1, .2), col=SPOT)
    b.add('sphere', (-.25, .7, -.25), (.2, .1, .16), col=SPOT)
    h = g['head']
    h.add('sphere', (0, .12, .22), (.86, .64, .7), col=T)
    for s in (-1, 1):
        h.add('cone', (s * .3, .45, .12), (.16, .22, .14), rot=(0, 0, -s * 25), col=T)
        h.add('sphere', (s * .24, .2, .48), (.12, .15, .08), col=color.rgb(.85, .15, .15))
        h.add('sphere', (s * .22, .24, .52), .04, col=WHITE)
    h.add('sphere', (0, .02, .55), (.4, .08, .05), col=color.rgb(.35, .1, .12))
    t = g['tail']   # le bulbe (pulse)
    t.add('sphere', (0, .1, 0), (.82, .78, .82), col=BULB)
    t.add('cone', (0, .5, 0), (.5, .35, .5), col=color.rgb(.2, .55, .25))
    for i in range(5):
        a = math.radians(i * 72)
        t.add('box', (math.sin(a) * .41, .12, math.cos(a) * .41), (.03, .6, .1), rot=(0, i * 72, 0),
              col=color.rgb(.2, .5, .22))
    return {'head_pivot': (0, .6, .45), 'tail_pivot': (0, .9, -.18), 'pulse': True}


def build_racaillou(g):
    R, DARK = color.rgb(.62, .6, .56), color.rgb(.38, .36, .33)
    b = g['body']
    b.add('sphere', (0, 1.05, 0), (1.05, .92, .95), col=R)
    for p, sc in (((.35, 1.35, -.2), .35), ((-.4, .8, -.25), .3), ((.1, .65, .3), .28),
                  ((-.3, 1.4, .1), .25), ((.42, .9, .2), .22)):
        b.add('sphere', p, sc, col=R)
    for s in (-1, 1):
        b.add('box', (s * .2, 1.33, .4), (.3, .08, .1), rot=(0, 0, s * 18), col=DARK)
    _eyes(b, .2, 1.18, .44, .12, .1)
    b.add('box', (0, .9, .46), (.28, .05, .05), col=DARK)
    t = g['tail']   # les bras (coordonnées "corps", pivot au centre du rocher)
    for s in (-1, 1):
        t.add('sphere', (s * .6, 1.0, 0), (.3, .26, .26), col=R)
        t.add('cyl', (s * .8, 1.2, .05), (.16, .5, .16), rot=(0, 0, s * 30), col=R)
        t.add('sphere', (s * .98, 1.5, .1), (.38, .36, .36), col=R)
        for f in (-1, 0, 1):
            t.add('sphere', (s * .98 + f * .1, 1.72, .22), .12, col=DARK)
    return {'tail_pivot': (0, 1.0, 0), 'float': True, 'no_head': True}


def build_stalgamin(g):
    HOOD, FACE, BODY = color.rgb(.95, .92, .8), color.rgb(.06, .06, .08), color.rgb(1, .78, .3)
    b = g['body']
    b.add('sphere', (0, .32, 0), (.7, .58, .66), col=BODY)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .06, .06), (.22, .14, .3), col=FACE)
        b.add('sphere', (s * .35, .45, .08), (.14, .26, .14), rot=(20, 0, s * 25), col=FACE)
    h = g['head']
    h.add('cone', (0, .5, 0), (1.05, 1.3, 1.0), col=HOOD)
    for i in range(5):
        a = math.radians(i * 72 + 36)
        h.add('cone', (math.sin(a) * .5, -.2, math.cos(a) * .48), (.22, .35, .2), rot=(180, 0, 0), col=HOOD)
    h.add('sphere', (0, .22, .3), (.56, .46, .3), col=FACE)
    _eyes(h, .13, .26, .43, .1, .16, iris=color.rgb(.4, .95, 1), shine=False)
    return {'head_pivot': (0, .6, 0), 'no_tail': True}


BUILDERS = {
    'pikachu': build_pikachu,
    'salameche': build_salameche,
    'carapuce': build_carapuce,
    'bulbizarre': build_bulbizarre,
    'racaillou': build_racaillou,
    'stalgamin': build_stalgamin,
}


class Creature(Entity):
    """Un Pokémon 3D animé. Racine = position au sol, regarde vers +z."""

    def __init__(self, species, scale=1.0, **kwargs):
        super().__init__(**kwargs)
        groups = {k: MeshBuilder() for k in ('body', 'head', 'tail', 'glow')}
        info = BUILDERS[species](groups)
        self.info = info
        self.species = species

        self.pivot = Entity(parent=self, scale=scale)      # reçoit bob / inclinaison
        self.parts = []

        self.body = groups['body'].entity(parent=self.pivot)
        self.parts.append(self.body)

        self.head = None
        if groups['head'].count:
            self.head = Entity(parent=self.pivot, position=info.get('head_pivot', (0, 1, 0)))
            self.parts.append(groups['head'].entity(parent=self.head))

        self.tail = None
        if groups['tail'].count:
            self.tail = Entity(parent=self.pivot, position=info.get('tail_pivot', (0, .5, -.3)))
            self.parts.append(groups['tail'].entity(parent=self.tail))

        self.glow = None
        if groups['glow'].count:
            parent = self.tail if info.get('glow_parent') == 'tail' and self.tail else self.pivot
            origin = Vec3(*info.get('tail_pivot', (0, 0, 0))) if parent is self.tail else Vec3(0, 0, 0)
            self.glow = groups['glow'].entity(parent=parent, emissive=1.0, position=-origin)
            self.parts.append(self.glow)

        # Les pièces sont modélisées en coordonnées "corps" : on compense le pivot.
        for grp in (self.head, self.tail):
            if grp is not None:
                grp.children[0].position = -grp.position

        self.shadow = flat_circle(self, .55 * scale * (1.4 if species in ('bulbizarre', 'racaillou') else 1),
                                  color.rgba(0, 0, 0, .28), y=.03)
        self._t = 0
        self._flash_timer = 0
        self._ko = False

    # ---------------------------------------------------------------- anims
    def animate(self, dt, moving=False, attacking=False):
        if self._ko:
            return
        self._t += dt
        t = self._t
        floating = self.info.get('float')
        if floating:
            self.pivot.y = .35 + math.sin(t * 2.5) * .15
        elif moving:
            self.pivot.y = abs(math.sin(t * 12)) * .12
            self.pivot.rotation_z = math.sin(t * 12) * 4
        else:
            self.pivot.y = math.sin(t * 2) * .02
            self.pivot.rotation_z = 0
        self.pivot.rotation_x = -12 if attacking else 0

        if self.head is not None:
            self.head.rotation_z = math.sin(t * 1.7) * 5
        if self.tail is not None:
            if self.info.get('pulse'):
                s = 1 + math.sin(t * 3) * .05
                self.tail.scale = (s, s, s)
            elif floating:
                self.tail.rotation_x = math.sin(t * 3) * 15 - (40 if attacking else 0)
            else:
                self.tail.rotation_y = math.sin(t * (14 if moving else 4)) * 18
        if self.glow is not None:
            s = 1 + math.sin(t * 20) * .12 + math.sin(t * 33) * .06
            self.glow.scale = (s, s * 1.1, s)

        if self._flash_timer > 0:
            self._flash_timer -= dt
            if self._flash_timer <= 0:
                self.set_flash(Vec4(1, 1, 1, 0))

    def set_flash(self, value):
        for p in self.parts:
            p.set_shader_input('flash', value)

    def hit_flash(self, col=Vec4(1, 1, 1, .85), duration=.1):
        self.set_flash(col)
        self._flash_timer = duration

    def knock_out(self):
        self._ko = True
        self.pivot.animate('rotation_z', 90, duration=.6)
        self.pivot.animate('y', 0, duration=.6)
        self.set_flash(Vec4(.2, .2, .25, .35))

    def face(self, direction, dt=None, speed=12):
        """Tourne la créature vers une direction (x, z)."""
        if direction[0] == 0 and direction[1] == 0:
            return
        target = math.degrees(math.atan2(direction[0], direction[1]))
        if dt is None:
            self.rotation_y = target
            return
        diff = (target - self.rotation_y + 180) % 360 - 180
        self.rotation_y += diff * min(1, dt * speed)
