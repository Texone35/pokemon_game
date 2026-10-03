"""Thèmes des types ajoutés au tirage des arènes (en plus de roche, plante, électrik, eau et feu).

Pour chaque type : des éléments de décor (arbres et objets de la jungle, PROPS), le bord des
massifs (WALL), le style de l'arène (ARENA, construit par build_arena) et un grand décor repère
(LANDMARK, posé par Landmarks). Les palettes des sols sont dans biomes.py, la végétation des massifs
(FLORA_T, GREENS_T) dans stadium.py, la météo et le bonus dans balance/arenas.py.

Tout est fait de primitives fusionnées (MeshBuilder) : le coût reste celui des autres thèmes.
"""
import math

from ursina import color

from game import config as C
from game.world.emblems import add_emblem  # noqa: F401  (utilisé par les arènes via ArenaDecor.emblem)
from game.world.geometry import ROCKS, glowing
from game.world.stadium import BLOSSOM, polar, shade


def rgb(r, g, b):
    return color.rgb(r, g, b)


SNOW = rgb(.95, .97, 1)
ICE = [rgb(.62, .86, 1), rgb(.75, .92, 1), rgb(.55, .78, .98)]
BONE = rgb(.92, .89, .8)
STEEL = rgb(.6, .63, .68)
WOOD = rgb(.5, .35, .22)
PSY_C = [rgb(.95, .5, .9), rgb(.75, .45, 1), rgb(1, .7, .95)]
DRAGON_C = [rgb(.4, .35, 1), rgb(.3, .55, 1), rgb(.55, .4, .95)]
TOXIC = rgb(.65, 1, .35)
PASTEL = [rgb(1, .7, .85), rgb(.85, .75, 1), rgb(1, .9, .6), rgb(.7, .9, 1), rgb(1, .78, .7)]


# ==================================================================== éléments de décor
# Chaque fonction pose un élément en (x, z) (hauteur relative au sol), de taille s, et renvoie son
# rayon approximatif. b : constructeur posé sur le relief (stadium.b) ; rng : tirage du stade.
def _haystack(b, x, z, s, rng):
    hay = rgb(.86, .74, .38)
    b.add('cyl16', (x, .55 * s, z), (1.6 * s, 1.1 * s, 1.6 * s), col=hay, grad=.3)
    b.add('dome', (x, 1.1 * s, z), (1.6 * s, .9 * s, 1.6 * s), col=shade(hay, 1.05))
    if rng.random() < .5:
        b.add('box', (x + 1.3 * s, .4 * s, z), (.9 * s, .8 * s, 1.2 * s), rot=(0, rng.uniform(0, 90), 0), col=hay)
    return 1.0 * s


def _snow_pine(b, x, z, s, rng):
    b.add('trunk', (x, .9 * s, z), (.45 * s, 1.8 * s, .45 * s), col=rgb(.35, .25, .18), grad=.35)
    g = rgb(.12, .32 + rng.uniform(-.03, .03), .28)
    for i in range(5):
        r = (2.8 - i * .48) * rng.uniform(.92, 1.06)
        b.add('cone8', (x, (1.8 + i * .9) * s, z), (r * s, 1.7 * s, r * s), rot=(0, rng.uniform(0, 45), 0),
              col=shade(g, .85 + i * .07), wobble=.12, grad=.4, cap=(SNOW, .8))
    return .9 * s


def _ice_spike(b, x, z, s, rng):
    for i in range(rng.randint(3, 5)):
        h = rng.uniform(1.6, 3.6) * s * (1.3 if i == 0 else 1)
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(.4, .9) * s)
        b.add('cone6', (x + ox, h * .42, z + oz), (.7 * s, h, .7 * s),
              rot=(rng.uniform(-18, 18) if i else 0, rng.uniform(0, 60), rng.uniform(-18, 18) if i else 0),
              col=glowing(shade(rng.choice(ICE), rng.uniform(.9, 1.08)), .25))
    return .9 * s


def _snow_rock(b, x, z, s, rng):
    for _ in range(rng.randint(2, 3)):
        t = rng.uniform(.8, 1.4) * s
        ox, oz = rng.uniform(-.8, .8) * s, rng.uniform(-.8, .8) * s
        b.add(rng.choice(ROCKS), (x + ox, t * .35, z + oz), (t * 1.7, t * 1.2, t * 1.5),
              rot=(0, rng.uniform(0, 360), 0), col=shade(rgb(.55, .6, .66), rng.uniform(.85, 1.1)), grad=.3,
              cap=(SNOW, .9))
    return 1.0 * s


def _bamboo(b, x, z, s, rng):
    for _ in range(rng.randint(4, 7)):
        ox, oz = rng.uniform(-.9, .9) * s, rng.uniform(-.9, .9) * s
        h = rng.uniform(4, 6.5) * s
        c = shade(rgb(.45, .66, .22), rng.uniform(.85, 1.1))
        tilt = (rng.uniform(-6, 6), 0, rng.uniform(-6, 6))
        b.add('cyl8', (x + ox, h / 2, z + oz), (.22 * s, h, .22 * s), rot=tilt, col=c)
        for k in range(1, 4):
            b.add('cyl8', (x + ox, h * k / 4, z + oz), (.27 * s, .08, .27 * s), rot=tilt, col=shade(c, .75))
        b.add('blob_lo', (x + ox, h, z + oz), (1.2 * s, .5 * s, 1.2 * s), col=shade(c, 1.1), wobble=.3)
    return .9 * s


def _training_post(b, x, z, s, rng):
    b.add('cyl8', (x, 1.1 * s, z), (.35 * s, 2.2 * s, .35 * s), col=WOOD, grad=.3)
    b.add('box', (x, 1.7 * s, z), (1.6 * s, .2 * s, .2 * s), rot=(0, rng.uniform(0, 180), 0), col=WOOD)
    b.add('cyl16', (x, 1.15 * s, z), (.75 * s, 1.0 * s, .75 * s), col=rgb(.85, .74, .45))
    b.add('ring', (x, 1.15 * s, z), (.8 * s, .12, .8 * s), col=rgb(.75, .2, .15))
    return .5 * s


def _toxic_mushroom(b, x, z, s, rng):
    cap = shade(rng.choice((rgb(.6, .25, .7), rgb(.45, .2, .6), rgb(.7, .3, .55))), rng.uniform(.9, 1.1))
    for i in range(rng.randint(1, 3)):
        t = (1.0 if i == 0 else rng.uniform(.4, .6)) * s
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), 1.3 * s)
        h = 2.6 * t
        b.add('cyl8', (x + ox, h / 2, z + oz), (.5 * t, h, .5 * t), col=rgb(.85, .82, .72), grad=.3)
        b.add('dome', (x + ox, h * .92, z + oz), (2.6 * t, 1.3 * t, 2.6 * t), col=cap)
        for _ in range(4):
            px, pz = polar(rng.uniform(0, 360), rng.uniform(.4, 1.0) * t)
            b.add('sphere_lo', (x + ox + px, h * .92 + .9 * t, z + oz + pz), .28 * t, col=glowing(TOXIC, .9))
    return 1.1 * s


def _bubble_pool(b, x, z, s, rng):
    b.add('cyl24', (x, .04, z), (3.0 * s, .08, 2.6 * s), rot=(0, rng.uniform(0, 180), 0),
          col=glowing(rgb(.45, .85, .25), .6))
    b.add('ring', (x, .06, z), (3.2 * s, .12, 2.8 * s), col=rgb(.3, .25, .3))
    for _ in range(5):
        px, pz = polar(rng.uniform(0, 360), rng.uniform(0, 1.1) * s)
        b.add('sphere_lo', (x + px, .12, z + pz), rng.uniform(.18, .38) * s, col=glowing(rgb(.75, .5, .9), .7))
    return 1.4 * s


def _boulder(b, x, z, s, rng):
    sand = rgb(.72, .55, .36)
    for _ in range(rng.randint(2, 4)):
        t = rng.uniform(1.0, 1.8) * s
        ox, oz = rng.uniform(-1, 1) * s, rng.uniform(-1, 1) * s
        b.add(rng.choice(ROCKS), (x + ox, t * .4, z + oz), (t * 1.8, t * 1.4, t * 1.6),
              rot=(rng.uniform(-8, 8), rng.uniform(0, 360), rng.uniform(-8, 8)), col=shade(sand, rng.uniform(.8, 1.1)),
              grad=.4)
    return 1.3 * s


def _cactus(b, x, z, s, rng):
    g = shade(rgb(.32, .55, .3), rng.uniform(.9, 1.1))
    h = rng.uniform(2.6, 3.6) * s
    b.add('cyl8', (x, h / 2, z), (.6 * s, h, .6 * s), col=g, grad=.3)
    b.add('sphere_lo', (x, h, z), .3 * s, col=g)
    for sd in (-1, 1):
        if rng.random() < .8:
            y0 = rng.uniform(.35, .6) * h
            b.add('cyl8', (x + sd * .55 * s, y0, z), (.4 * s, .14 * s * 6, .4 * s), rot=(0, 0, 90), col=g)
            b.add('cyl8', (x + sd * .85 * s, y0 + .55 * s, z), (.4 * s, 1.1 * s, .4 * s), col=g)
    return .7 * s


def _wind_tree(b, x, z, s, rng, greens=None):
    lean = rng.uniform(0, 360)
    dx, dz = polar(lean, 1)
    bark = rgb(.5, .4, .3)
    for i in range(3):
        b.add('cyl6', (x + dx * i * .45 * s, (.7 + i * 1.1) * s, z + dz * i * .45 * s), (.4 * s, 1.3 * s, .4 * s),
              rot=(0, lean, -(10 + i * 8)), col=bark, grad=.25)
    tx, tz = x + dx * 1.6 * s, z + dz * 1.6 * s
    g = rng.choice(greens or [rgb(.4, .65, .32), rgb(.46, .7, .36)])
    for i in range(4):
        ox, oz = polar(lean + rng.uniform(-60, 60), rng.uniform(.3, 1.2) * s)
        b.add('blob_lo', (tx + ox, 3.6 * s + rng.uniform(-.3, .3), tz + oz), (1.6 * s, .9 * s, 1.3 * s),
              rot=(0, lean, 0), col=shade(g, rng.uniform(.85, 1.1)), wobble=.25, light=.15)
    return 1.0 * s


def _wind_vane(b, x, z, s, rng):
    h = 4.2 * s
    b.add('cyl8', (x, h / 2, z), (.25 * s, h, .25 * s), col=rgb(.85, .85, .88))
    a = rng.uniform(0, 360)
    hx, hz = polar(a, .3 * s)
    b.add('sphere_lo', (x + hx, h, z + hz), .3 * s, col=rgb(.9, .9, .95))
    for k in range(3):
        b.add('box', (x + hx, h, z + hz), (.25 * s, 1.8 * s, .05 * s), rot=(k * 120, a + 90, 0),
              col=rgb(.95, .95, .98))
    return .5 * s


def _crystal_cluster(b, x, z, s, rng, palette, g=.45):
    base = rng.choice(palette)
    for i in range(rng.randint(3, 5)):
        h = rng.uniform(1.2, 2.8) * s * (1.25 if i == 0 else 1)
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(.3, .8) * s)
        b.add('cone6', (x + ox, h * .42, z + oz), (.6 * s, h, .6 * s),
              rot=(rng.uniform(-22, 22) if i else 0, rng.uniform(0, 60), rng.uniform(-22, 22) if i else 0),
              col=glowing(shade(base, rng.uniform(.9, 1.1)), g))
    return .8 * s


def _crystal_psy(b, x, z, s, rng):
    return _crystal_cluster(b, x, z, s, rng, PSY_C)


def _dragon_crystal(b, x, z, s, rng):
    return _crystal_cluster(b, x, z, s * 1.1, rng, DRAGON_C, .55)


def _floating_rock(b, x, z, s, rng):
    y = rng.uniform(2.2, 3.4) * s
    c = shade(rgb(.55, .48, .62), rng.uniform(.9, 1.1))
    b.add('cone6', (x, y - .5 * s, z), (1.6 * s, 1.5 * s, 1.6 * s), rot=(180, rng.uniform(0, 60), 0), col=c)
    b.add(rng.choice(ROCKS), (x, y, z), (1.9 * s, .7 * s, 1.7 * s), rot=(0, rng.uniform(0, 360), 0), col=c,
          cap=(rgb(.7, .5, .8), .8))
    b.add('ring_thin', (x, y - 1.6 * s, z), (1.6 * s, .1, 1.6 * s), col=glowing(rng.choice(PSY_C), .9))
    return .9 * s


def _web(b, x, y, z, r, yaw):
    """Toile d'araignée : anneaux fins et rayons, dans un plan vertical."""
    web = glowing(rgb(.92, .94, .96), .15)
    for k in (.35, .65, 1.0):
        b.add('ring_thin', (x, y, z), (r * 2 * k, .04, r * 2 * k), rot=(90, yaw, 0), col=web)
    for k in range(6):
        b.add('box', (x, y, z), (.03, r * 2, .03), rot=(0, yaw, k * 30), col=web)


def _web_tree(b, x, z, s, rng):
    trunk = rgb(.32, .26, .2)
    h = 3.4 * s
    b.add('cone8', (x, h / 2, z), (.7 * s, h, .7 * s), col=trunk, grad=.3)
    for i in range(3):
        a = i * 120 + rng.uniform(-30, 30)
        ox, oz = polar(a, .6 * s)
        b.add('cone6', (x + ox, (1.8 + i * .5) * s, z + oz), (.25 * s, 2.0 * s, .25 * s), rot=(0, a, 50), col=trunk)
    b.add('blob_lo', (x, 3.6 * s, z), (2.2 * s, 1.2 * s, 2.2 * s), col=shade(rgb(.36, .5, .14), rng.uniform(.9, 1.1)),
          wobble=.3)
    _web(b, x + .2 * s, 2.0 * s, z, 1.1 * s, rng.uniform(0, 180))
    return .9 * s


def _cocoon(b, x, z, s, rng):
    silk = rgb(.9, .88, .78)
    for i in range(rng.randint(2, 4)):
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(.6, 1.1) * s)
        t = rng.uniform(.7, 1.1) * s
        b.add('sphere', (x + ox, 1.0 * t, z + oz), (.9 * t, 2.0 * t, .9 * t), rot=(rng.uniform(-15, 15), 0, 0),
              col=shade(silk, rng.uniform(.88, 1.05)), wobble=.15)
        for k in range(3):
            b.add('ring_thin', (x + ox, (.5 + k * .5) * t, z + oz), (.95 * t, .05, .95 * t), col=shade(silk, .8))
    return .9 * s


def _tombstone(b, x, z, s, rng):
    stone = shade(rgb(.5, .5, .55), rng.uniform(.85, 1.1))
    for i in range(rng.randint(1, 3)):
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(1, 1.6) * s)
        yaw, tilt = rng.uniform(0, 360), rng.uniform(-12, 12)
        if rng.random() < .3:                      # croix
            b.add('box', (x + ox, .8 * s, z + oz), (.22 * s, 1.6 * s, .22 * s), rot=(tilt, yaw, 0), col=stone)
            b.add('box', (x + ox, 1.15 * s, z + oz), (.9 * s, .2 * s, .2 * s), rot=(tilt, yaw, 0), col=stone)
        else:
            b.add('box', (x + ox, .55 * s, z + oz), (.9 * s, 1.1 * s, .25 * s), rot=(tilt, yaw, 0), col=stone)
            b.add('cyl16', (x + ox, 1.1 * s, z + oz), (.9 * s, .25 * s, .9 * s), rot=(90 + tilt, yaw, 0), col=stone)
    return .8 * s


def _ghost_tree(b, x, z, s, rng):
    bark = rgb(.22, .2, .24)
    h = 3.6 * s
    b.add('cone8', (x, h / 2, z), (.7 * s, h, .7 * s), rot=(rng.uniform(-8, 8), 0, rng.uniform(-8, 8)), col=bark)
    for i in range(4):
        a = i * 90 + rng.uniform(-30, 30)
        ox, oz = polar(a, .55 * s)
        b.add('cone6', (x + ox, (1.6 + i * .5) * s, z + oz), (.2 * s, 2.2 * s, .2 * s), rot=(0, a, 55), col=bark)
    for _ in range(3):                            # feux follets
        px, pz = polar(rng.uniform(0, 360), rng.uniform(1, 2) * s)
        b.add('sphere_lo', (x + px, rng.uniform(1.2, 2.6) * s, z + pz), .2 * s, col=glowing(rgb(.65, .5, 1), 1))
    return .7 * s


def _lantern(b, x, z, s, rng, col=None):
    col = col or rgb(.6, .75, 1)
    b.add('cyl8', (x, 1.0 * s, z), (.16 * s, 2.0 * s, .16 * s), col=rgb(.25, .24, .28))
    b.add('box', (x, 2.1 * s, z), (.5 * s, .55 * s, .5 * s), col=rgb(.25, .24, .28))
    b.add('sphere_lo', (x, 2.1 * s, z), .3 * s, col=glowing(col, 1))
    b.add('cone4', (x, 2.55 * s, z), (.7 * s, .4 * s, .7 * s), rot=(0, 45, 0), col=rgb(.2, .2, .24))
    return .4 * s


def _bone(b, x, z, s, rng):
    yaw = rng.uniform(0, 360)
    for k in range(rng.randint(3, 5)):            # côtes qui sortent du sol
        ox, oz = polar(yaw, (k - 2) * .8 * s)
        for sd in (-1, 1):
            b.add('cone6', (x + ox, 1.1 * s, z + oz), (.25 * s, 2.6 * s, .25 * s), rot=(0, yaw + 90, sd * 35),
                  col=shade(BONE, rng.uniform(.9, 1.05)))
    return 1.4 * s


def _dark_tree(b, x, z, s, rng):
    bark = rgb(.13, .11, .14)
    h = 3.4 * s
    b.add('cone8', (x, h / 2, z), (.8 * s, h, .8 * s), col=bark, grad=.3)
    for i in range(3):
        a = i * 120 + rng.uniform(-30, 30)
        ox, oz = polar(a, .6 * s)
        b.add('cone6', (x + ox, (1.7 + i * .5) * s, z + oz), (.25 * s, 2.0 * s, .25 * s), rot=(0, a, 48), col=bark)
    g = shade(rgb(.2, .14, .28), rng.uniform(.85, 1.15))
    for i in range(3):
        ox, oz = polar(i * 120 + rng.uniform(-20, 20), .9 * s)
        b.add('blob_lo', (x + ox, 3.5 * s, z + oz), (1.6 * s, 1.1 * s, 1.6 * s), col=g, wobble=.3)
    if rng.random() < .35:                        # yeux qui brillent dans le feuillage
        ex, ez = polar(rng.uniform(0, 360), 1.3 * s)
        for sd in (-1, 1):
            b.add('sphere_xlo', (x + ex + sd * .18, 3.0 * s, z + ez), .09 * s * 2, col=glowing(rgb(1, .2, .15), 1))
    return 1.0 * s


def _thorn(b, x, z, s, rng):
    c = rgb(.12, .1, .13)
    for _ in range(rng.randint(5, 8)):
        ox, oz = rng.uniform(-.9, .9) * s, rng.uniform(-.9, .9) * s
        h = rng.uniform(1.2, 2.8) * s
        b.add('cone6', (x + ox, h * .45, z + oz), (.35 * s, h, .35 * s),
              rot=(rng.uniform(-30, 30), rng.uniform(0, 60), rng.uniform(-30, 30)), col=c)
    if rng.random() < .4:
        b.add('sphere_lo', (x, .5 * s, z), .3 * s, col=glowing(rgb(.9, .15, .2), .9))
    return .9 * s


def _girder(b, x, z, s, rng):
    yaw = rng.uniform(0, 180)
    h = rng.uniform(3, 5) * s
    for sd in (-1, 1):
        px, pz = polar(yaw + 90, .9 * s * sd, x, z)
        b.add('box', (px, h / 2, pz), (.3 * s, h, .3 * s), rot=(0, yaw, 0), col=shade(STEEL, rng.uniform(.85, 1.05)))
    for k in range(3):
        b.add('box', (x, (k + .5) * h / 3, z), (.15 * s, h / 3 * 1.3, .15 * s), rot=(0, yaw + 90, 40 * (-1) ** k),
              col=shade(STEEL, .8))
    b.add('box', (x, h, z), (2.2 * s, .3 * s, .4 * s), rot=(0, yaw + 90, 0), col=rgb(.75, .55, .2))
    return 1.0 * s


def _gear(b, x, z, s, rng):
    r = rng.uniform(1.0, 1.6) * s
    yaw = rng.uniform(0, 180)
    tilt = rng.choice((90, 70, 20))
    y = r * (.9 if tilt > 45 else .2)
    c = shade(STEEL, rng.uniform(.85, 1.05))
    b.add('ring', (x, y, z), (r * 2, .35 * s, r * 2), rot=(tilt, yaw, 0), col=c)
    b.add('cyl16', (x, y, z), (r * .7, .4 * s, r * .7), rot=(tilt, yaw, 0), col=shade(c, .8))
    return r


def _metal_block(b, x, z, s, rng):
    for k in range(rng.randint(2, 4)):
        w = rng.uniform(1.0, 1.6) * s
        ox, oz = rng.uniform(-.6, .6) * s, rng.uniform(-.6, .6) * s
        y = k * .9 * s
        b.add('box', (x + ox, y + w * .4, z + oz), (w, w * .8, w), rot=(0, rng.uniform(0, 90), 0),
              col=shade(rng.choice((STEEL, rgb(.5, .54, .6), rgb(.62, .5, .3))), rng.uniform(.9, 1.1)), grad=.2)
    return 1.0 * s


def _giant_flower(b, x, z, s, rng):
    col = rng.choice(PASTEL)
    h = rng.uniform(2.4, 3.6) * s
    b.add('cyl8', (x, h / 2, z), (.25 * s, h, .25 * s), col=rgb(.35, .65, .3))
    b.add('blob', (x + .5 * s, h * .4, z), (1.0 * s, .15 * s, .5 * s), rot=(0, rng.uniform(0, 360), -20),
          col=rgb(.4, .72, .35))
    for k in range(6):
        px, pz = polar(k * 60, .7 * s)
        b.add('blob', (x + px, h, z + pz), (.9 * s, .2 * s, .55 * s), rot=(-15, k * 60 + 90, 0),
              col=shade(col, rng.uniform(.95, 1.08)), wobble=.1)
    b.add('sphere_lo', (x, h + .1, z), .45 * s, col=glowing(rgb(1, .9, .5), .4))
    return .9 * s


def _fairy_mushroom(b, x, z, s, rng):
    for i in range(rng.randint(3, 6)):
        ox, oz = (0, 0) if i == 0 else polar(rng.uniform(0, 360), rng.uniform(.5, 1.3) * s)
        t = rng.uniform(.4, .8) * s * (1.4 if i == 0 else 1)
        cap = rng.choice((rgb(1, .55, .75), rgb(.85, .6, 1), rgb(1, .75, .85)))
        b.add('cyl8', (x + ox, .6 * t, z + oz), (.3 * t, 1.2 * t, .3 * t), col=rgb(.95, .93, .88))
        b.add('dome', (x + ox, 1.1 * t, z + oz), (1.4 * t, .8 * t, 1.4 * t), col=glowing(cap, .35))
        b.add('sphere_xlo', (x + ox, 1.5 * t, z + oz), .12 * t * 2, col=glowing(rgb(1, 1, 1), .8))
    return .9 * s


PROPS = {'haystack': _haystack, 'snow_pine': _snow_pine, 'ice_spike': _ice_spike, 'snow_rock': _snow_rock,
         'bamboo': _bamboo, 'training_post': _training_post, 'toxic_mushroom': _toxic_mushroom,
         'bubble_pool': _bubble_pool, 'boulder': _boulder, 'cactus': _cactus, 'wind_tree': _wind_tree,
         'wind_vane': _wind_vane, 'crystal_psy': _crystal_psy, 'floating_rock': _floating_rock,
         'web_tree': _web_tree, 'cocoon': _cocoon, 'tombstone': _tombstone, 'ghost_tree': _ghost_tree,
         'lantern': _lantern, 'dragon_crystal': _dragon_crystal, 'bone': _bone, 'dark_tree': _dark_tree,
         'thorn': _thorn, 'girder': _girder, 'gear': _gear, 'metal_block': _metal_block,
         'giant_flower': _giant_flower, 'fairy_mushroom': _fairy_mushroom}


def prop(b, kind, x, z, s, rng):
    return PROPS[kind](b, x, z, s, rng)


# ==================================================================== bords des massifs
# type -> (style, couleur de la falaise, dessus, élément au pied du mur, probabilité, essences des rideaux d'arbres)
WALL = {
    'normal': ('mixed', None, None, 'haystack', .04, ('broadleaf', 'broadleaf', 'conifer')),
    'glace': ('cliff', rgb(.74, .82, .9), SNOW, 'ice_spike', .25, ()),
    'combat': ('cliff', rgb(.6, .52, .46), rgb(.36, .5, .24), 'bamboo', .25, ()),
    'poison': ('grove', None, None, 'toxic_mushroom', .2, ('dead', 'toxic_mushroom')),
    'sol': ('cliff', rgb(.74, .56, .38), rgb(.84, .7, .5), 'boulder', .2, ()),
    'vol': ('cliff', rgb(.82, .82, .8), rgb(.5, .72, .4), 'wind_tree', .14, ()),
    'psy': ('cliff', rgb(.6, .5, .7), rgb(.85, .6, .9), 'crystal_psy', .2, ()),
    'insecte': ('grove', None, None, 'cocoon', .1, ('broadleaf', 'web_tree')),
    'spectre': ('grove', None, None, 'tombstone', .18, ('ghost_tree', 'dead')),
    'dragon': ('cliff', rgb(.42, .38, .55), rgb(.3, .48, .4), 'dragon_crystal', .18, ()),
    'tenebres': ('grove', None, None, 'thorn', .25, ('dark_tree',)),
    'acier': ('cliff', rgb(.56, .58, .62), rgb(.42, .44, .48), 'girder', .12, ()),
    'fee': ('grove', None, None, 'fairy_mushroom', .25, ('blossom', 'giant_flower')),
}


def wall(st, b, x, z, nx, nz, k, bio, t):
    """Bord de massif d'un thème ajouté : falaise teintée ou rideau d'arbres, et ses éléments au pied."""
    rng = st.rng
    style, rock, top, accent, chance, kinds = WALL[t]
    if style == 'mixed':
        style = 'cliff' if math.sin(x * .045 + math.sin(z * .03) * 2) * math.cos(z * .05) > -.2 else 'grove'
    if style == 'cliff':
        _cliff(st, b, x, z, nx, nz, rock or rgb(.6, .57, .52), top or rgb(.33, .52, .22))
    else:
        st._grove(b, x, z, nx, nz, k, bio, kinds=kinds or None)
    if accent and rng.random() < chance:
        prop(b, accent, x + nx * .6, z + nz * .6, rng.uniform(.6, .85), rng)


def _cliff(st, b, x, z, nx, nz, rock, top):
    rng = st.rng
    yaw = math.degrees(math.atan2(nx, nz))
    h = rng.uniform(2.8, 3.9)
    c = shade(rock, rng.uniform(.82, 1.12))
    b.add(rng.choice(ROCKS), (x + nx * .7, h * .42, z + nz * .7), (rng.uniform(3.2, 4.0), h * 1.2, 2.8),
          rot=(rng.uniform(-6, 6), yaw + rng.uniform(-18, 18), rng.uniform(-6, 6)), col=c, grad=.45, cap=(top, .9))
    if rng.random() < .55:
        h2 = h * rng.uniform(1.1, 1.4)
        b.add(rng.choice(ROCKS), (x + nx * 2.6, h2 * .45, z + nz * 2.6), (3.6, h2 * 1.2, 3.2),
              rot=(0, yaw + rng.uniform(-30, 30), 0), col=shade(c, .9), grad=.45, cap=(top, .9))


# ==================================================================== arènes
# rim : bordure dallée autour ; joint : sol sous le pavage ; floor : ('pave' | 'hex', teintes, taille) ;
# medal : médaillon central ; border : bordure ; post : (forme, couleur, lueur) des piliers d'entrée ;
# props : éléments autour de l'arène ; glow : liseré lumineux.
ARENA = {
    'normal': dict(rim=rgb(.78, .76, .7), joint=rgb(.52, .5, .46), floor=('pave', [rgb(.86, .84, .78), rgb(.8, .78, .7),
                   rgb(.9, .88, .82)], 2.2), medal=rgb(.7, .66, .58), border=rgb(.95, .95, .92),
                   post=('pillar', rgb(.95, .94, .9), rgb(1, .9, .6)), props=['haystack', 'lantern'],
                   glow=rgb(1, .92, .7)),
    'glace': dict(rim=rgb(.82, .9, .96), joint=rgb(.55, .7, .82), floor=('hex', [rgb(.78, .9, 1), rgb(.85, .94, 1),
                  rgb(.7, .84, .96)], .95), medal=rgb(.5, .75, .95), border=rgb(.7, .88, 1),
                  post=('crystal', rgb(.7, .9, 1), rgb(.6, .9, 1)), props=['ice_spike', 'snow_rock'],
                  glow=rgb(.55, .9, 1)),
    'combat': dict(rim=rgb(.62, .45, .3), joint=rgb(.38, .26, .18), floor=('hex', [rgb(.82, .72, .5), rgb(.76, .66, .44),
                   rgb(.86, .76, .54)], 1.1), medal=rgb(.75, .25, .2), border=rgb(.8, .2, .15),
                   post=('torii', rgb(.82, .2, .15), rgb(1, .6, .3)), props=['training_post', 'bamboo'],
                   glow=rgb(1, .45, .3)),
    'poison': dict(rim=rgb(.36, .3, .38), joint=rgb(.2, .15, .22), floor=('pave', [rgb(.42, .34, .46), rgb(.36, .28, .4),
                   rgb(.48, .38, .5)], 2.0), medal=rgb(.55, .25, .65), border=rgb(.3, .22, .34),
                   post=('totem', rgb(.38, .26, .44), rgb(.65, 1, .35)), props=['toxic_mushroom', 'bubble_pool'],
                   glow=rgb(.65, 1, .35)),
    'sol': dict(rim=rgb(.74, .58, .38), joint=rgb(.46, .34, .22), floor=('pave', [rgb(.8, .64, .42), rgb(.74, .58, .38),
                rgb(.86, .7, .48)], 2.6), medal=rgb(.6, .44, .26), border=rgb(.62, .48, .32),
                post=('obelisk', rgb(.76, .6, .4), rgb(1, .8, .45)), props=['boulder', 'cactus'],
                glow=rgb(1, .78, .4)),
    'vol': dict(rim=rgb(.88, .9, .94), joint=rgb(.6, .66, .76), floor=('hex', [rgb(.92, .94, 1), rgb(.8, .88, 1),
                rgb(.86, .9, .98)], 1.0), medal=rgb(.55, .68, .95), border=rgb(.95, .96, 1),
                post=('pillar', rgb(.96, .96, 1), rgb(.6, .8, 1)), props=['wind_vane', 'wind_tree'],
                glow=rgb(.7, .85, 1)),
    'psy': dict(rim=rgb(.6, .48, .7), joint=rgb(.32, .22, .42), floor=('hex', [rgb(.7, .5, .82), rgb(.82, .6, .9),
                rgb(.6, .44, .78)], .95), medal=rgb(.9, .45, .85), border=rgb(.5, .36, .62),
                post=('obelisk', rgb(.45, .32, .58), rgb(1, .55, .95)), props=['crystal_psy', 'floating_rock'],
                glow=rgb(1, .5, .9)),
    'insecte': dict(rim=rgb(.5, .5, .3), joint=rgb(.3, .3, .16), floor=('pave', [rgb(.56, .62, .3), rgb(.5, .56, .26),
                    rgb(.62, .66, .34)], 1.9), medal=rgb(.55, .7, .15), border=rgb(.42, .34, .2),
                    post=('totem', rgb(.45, .36, .22), rgb(.8, 1, .3)), props=['cocoon', 'web_tree'],
                    glow=rgb(.8, 1, .3)),
    'spectre': dict(rim=rgb(.4, .4, .45), joint=rgb(.22, .22, .26), floor=('pave', [rgb(.46, .46, .52),
                    rgb(.4, .4, .46), rgb(.52, .52, .58)], 2.1), medal=rgb(.4, .3, .6), border=rgb(.32, .32, .36),
                    post=('obelisk', rgb(.3, .3, .34), rgb(.65, .5, 1)), props=['tombstone', 'lantern'],
                    glow=rgb(.65, .5, 1)),
    'dragon': dict(rim=rgb(.38, .36, .5), joint=rgb(.18, .16, .3), floor=('hex', [rgb(.35, .34, .6), rgb(.42, .4, .7),
                   rgb(.3, .3, .52)], 1.05), medal=rgb(.5, .45, 1), border=rgb(.55, .5, .7),
                   post=('obelisk', rgb(.3, .28, .45), rgb(.5, .55, 1)), props=['dragon_crystal', 'bone'],
                   glow=rgb(.5, .55, 1)),
    'tenebres': dict(rim=rgb(.22, .2, .24), joint=rgb(.1, .09, .11), floor=('pave', [rgb(.24, .22, .26),
                     rgb(.2, .18, .22), rgb(.28, .26, .3)], 2.0), medal=rgb(.45, .12, .15), border=rgb(.14, .12, .15),
                     post=('obelisk', rgb(.14, .12, .16), rgb(1, .2, .2)), props=['thorn', 'dark_tree'],
                     glow=rgb(1, .25, .25)),
    'acier': dict(rim=rgb(.55, .57, .62), joint=rgb(.3, .32, .36), floor=('hex', [rgb(.66, .68, .74), rgb(.58, .6, .66),
                  rgb(.72, .74, .8)], 1.15), medal=rgb(.45, .5, .6), border=rgb(.75, .55, .2),
                  post=('pillar', rgb(.55, .58, .64), rgb(.4, .9, 1)), props=['gear', 'metal_block'],
                  glow=rgb(.4, .9, 1)),
    'fee': dict(rim=rgb(.95, .85, .9), joint=rgb(.7, .55, .66), floor=('pave', [rgb(1, .88, .94), rgb(.96, .8, .9),
                rgb(.98, .92, .96)], 1.9), medal=rgb(1, .6, .85), border=rgb(1, .75, .88),
                post=('crystal', rgb(1, .7, .9), rgb(1, .7, .95)), props=['giant_flower', 'fairy_mushroom'],
                glow=rgb(1, .7, .95)),
}


def _post(d, x, z, ang, style, col, glow):
    """Pilier d'entrée d'une arène (de part et d'autre de chaque voie)."""
    b = d.b
    if style == 'pillar':
        b.add('cyl16', (x, 1.8, z), (.9, 3.6, .9), col=col, grad=.3)
        b.add('box', (x, 3.75, z), (1.3, .3, 1.3), rot=(0, ang, 0), col=shade(col, .85))
        b.add('sphere', (x, 4.2, z), .55, col=glowing(glow, .9))
    elif style == 'crystal':
        b.add('cone6', (x, 2.0, z), (1.2, 4.2, 1.2), rot=(0, ang, 0), col=glowing(col, .45))
        b.add('cone6', (x + .5, 1.0, z), (.6, 2.0, .6), rot=(0, 20, 15), col=glowing(glow, .5))
    elif style == 'torii':
        b.add('cyl16', (x, 2.0, z), (.6, 4.0, .6), col=col)
        b.add('box', (x, 4.1, z), (1.6, .35, .7), rot=(0, ang, 0), col=rgb(.15, .12, .12))
        b.add('box', (x, 3.4, z), (1.2, .2, .4), rot=(0, ang, 0), col=col)
        b.add('cyl8', (x, .15, z), (.8, .3, .8), col=rgb(.2, .18, .18))
    elif style == 'totem':
        for k in range(3):
            b.add('cyl8', (x, .6 + k * 1.15, z), (.9 - k * .1, 1.1, .9 - k * .1), col=shade(col, 1 - k * .08), grad=.2)
            b.add('box', (x, .7 + k * 1.15, z), (.95, .18, .2), rot=(0, ang + 90, 0), col=glowing(glow, .8))
        b.add('cone6', (x, 4.0, z), (.9, .8, .9), col=shade(col, .8))
    else:                                         # obélisque
        b.add('prism5', (x, 2.0, z), (1.0, 4.0, 1.0), rot=(0, ang, 0), col=col, grad=.3)
        b.add('cone4', (x, 4.3, z), (.8, .7, .8), rot=(0, ang + 45, 0), col=glowing(glow, .9))
        b.add('box', (x, 2.4, z), (.12, 1.4, 1.02), rot=(0, ang, 0), col=glowing(glow, .7))


def build_arena(d, t):
    """Arène d'un thème ajouté : sol (dallage ou tomettes hexagonales), médaillon et emblème, bordure,
    piliers aux entrées, liseré lumineux et éléments du thème autour."""
    spec = ARENA[t]
    b, glow, rng, R = d.b, d.glow, d.rng, d.R
    d.disc(b, R + 3.1, .03, .06, spec['rim'])
    d.disc(b, R + .3, .06, .06, spec['joint'])
    kind, pal, size = spec['floor']
    if kind == 'pave':
        d.paving(R - .2, size, .1, lambda x, z: shade(rng.choice(pal), rng.uniform(.92, 1.06)), gap=.12, r_in=2.6)
    else:
        d.hex_tiles(b, size, .1, .06, lambda x, z: shade(rng.choice(pal), rng.uniform(.94, 1.05)), r_in=2.6)
    d.disc(b, 2.9, .09, .12, spec['medal'])
    d.ring(b, 2.6, .16, .02, spec['glow'], 'ring_thin')
    d.emblem()
    n = 36                                        # bordure de blocs
    for i in range(n):
        ang = i * 360 / n
        x, z = d.hpolar(ang, R + 1.1)
        b.add('box', (x, .14, z), (2 * math.pi * (R + 1.1) / n * .82, .24, 1.0), rot=(0, C.hex_normal(ang), 0),
              col=shade(spec['border'], rng.uniform(.9, 1.06)))
    d.ring(glow, R + .5, .1, .03, spec['glow'])    # liseré lumineux
    style, col, gl = spec['post']
    d.gate(lambda x, z, ang: _post(d, x, z, ang, style, col, gl))
    for k, (x, z, ang) in enumerate(d.spots(8, R + 3.4, R + 5.6, 1.8, 1.2)):
        kind = spec['props'][k % len(spec['props'])]
        r = prop(b, kind, x, z, rng.uniform(.6, .8), rng)
        d.st.block(x, z, min(r, .8))


# ==================================================================== grands décors
def _mark_hill(lm, x, z, r, h):
    from game.world.stadium import _smoothstep
    lm.st.terrain_marks.append((x, z, r, lambda t: h * _smoothstep(1, .35, t), 'add'))


def _plan(lm, main, side, inner, kind, size=7.0, hill=0.0, small=()):
    """Plan commun : grand décor `kind` au cœur du massif le plus profond près de l'emplacement principal
    (son rayon r ne dépasse jamais la profondeur : rien ne déborde sur les passages), bouquets d'éléments
    ailleurs. Massif trop mince : un simple bouquet à la place du grand décor."""
    x, z, d = lm._deep(*main, 14)
    r = min(d - .4, size)
    if r >= 3.0:
        lm._add(kind, x, z, r)
        if hill:
            _mark_hill(lm, x, z, r, hill)
    elif d > 2.0 and small:
        lm._add('cluster', x, z, d - .4, kinds=small)
    for p in (side, inner):
        if p is not None and small:
            px, pz, dd = lm._deep(*p, 6)
            if dd > 2.0:
                lm._add('cluster', px, pz, min(dd - .4, 4.5), kinds=small)


def build_cluster(lm, x, z, r, kinds):
    rng = lm.st.rng
    for i in range(int(2 + r)):
        px, pz = polar(rng.uniform(0, 360), rng.uniform(0, r * .55), x, z)
        prop(lm.st.b, kinds[i % len(kinds)], px, pz, rng.uniform(.75, 1.05), rng)


def build_windmill(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    stone, roof = rgb(.88, .85, .78), rgb(.6, .25, .18)
    b.add('cyl16', (x, 3.5, z), (3.8, 7.0, 3.8), col=stone, grad=.3)
    b.add('cone16', (x, 8.0, z), (4.6, 2.4, 4.6), col=roof)
    yaw = rng.uniform(0, 360)
    hx, hz = polar(yaw, 2.1, x, z)
    b.add('cyl8', (hx, 6.6, hz), (.5, .8, .5), rot=(90, yaw, 0), col=WOOD)
    for k in range(4):
        b.add('box', (hx, 6.6, hz), (.9, 6.4, .12), rot=(0, yaw, k * 90 + 20), col=rgb(.92, .9, .85))
    b.add('box', polar(yaw, 1.95, x, z)[:1] + (1.2,) + polar(yaw, 1.95, x, z)[1:], (1.1, 2.2, .2), rot=(0, yaw, 0),
          col=WOOD)
    for i in range(3):
        px, pz = polar(rng.uniform(0, 360), r * .65, x, z)
        _haystack(b, px, pz, rng.uniform(.7, .9), rng)


def build_ice_peak(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    b.add('blob', (x, .5, z), (r * 1.8, 2.2, r * 1.8), col=SNOW, wobble=.2)
    for i in range(7):
        h = (12 if i == 0 else rng.uniform(5, 9)) * min(1, r / 6)
        ox, oz = (0, 0) if i == 0 else polar(i * 60 + rng.uniform(-15, 15), r * rng.uniform(.35, .6))
        b.add('cone6', (x + ox, h * .45, z + oz), (2.6 if i == 0 else 1.6, h, 2.6 if i == 0 else 1.6),
              rot=(0 if i == 0 else rng.uniform(-15, 15), rng.uniform(0, 60), 0 if i == 0 else rng.uniform(-15, 15)),
              col=glowing(shade(rng.choice(ICE), rng.uniform(.95, 1.1)), .35))


def build_pagoda(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    red, dark, wall_ = rgb(.75, .18, .14), rgb(.18, .14, .14), rgb(.92, .88, .78)
    yaw = rng.uniform(0, 90)
    w, y = min(r * 1.1, 6.0), 0.0
    for k in range(3):
        h = 2.2 - k * .3
        b.add('box', (x, y + h / 2, z), (w, h, w), rot=(0, yaw, 0), col=wall_)
        for c in range(4):
            px, pz = polar(yaw + 45 + c * 90, w * .7, x, z)
            b.add('cyl8', (px, y + h / 2, pz), (.35, h, .35), col=red)
        y += h
        b.add('cone4', (x, y + .35, z), (w * 1.9, 1.0, w * 1.9), rot=(0, yaw + 45, 0), col=dark)
        y += .5
        w *= .72
    b.add('cyl8', (x, y + 1.0, z), (.15, 2.0, .15), col=rgb(.85, .7, .3))
    px, pz = polar(yaw + 180, r * .8, x, z)                  # portique rouge devant
    for sd in (-1, 1):
        qx, qz = polar(yaw + 90, 1.6 * sd, px, pz)
        b.add('cyl16', (qx, 1.8, qz), (.45, 3.6, .45), col=red)
    b.add('box', (px, 3.7, pz), (4.4, .35, .6), rot=(0, yaw + 90, 0), col=dark)
    b.add('box', (px, 3.1, pz), (3.6, .22, .35), rot=(0, yaw + 90, 0), col=red)


def build_giant_shrooms(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    _bubble_pool(b, x, z, min(r * .45, 2.5), rng)
    for i in range(3):
        px, pz = polar(i * 120 + rng.uniform(-20, 20), r * .45, x, z)
        _toxic_mushroom(b, px, pz, r * rng.uniform(.3, .38), rng)


def build_spires(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    sand = rgb(.78, .58, .38)
    for i in range(6):
        px, pz = (x, z) if i == 0 else polar(i * 72 + rng.uniform(-15, 15), r * .55, x, z)
        h = (9 if i == 0 else rng.uniform(4, 7)) * min(1, r / 6)
        w = 2.4 if i == 0 else rng.uniform(1.3, 1.9)
        b.add('prism5', (px, h / 2, pz), (w, h, w), rot=(0, rng.uniform(0, 90), 0),
              col=shade(sand, rng.uniform(.88, 1.08)), grad=.4)
        b.add(rng.choice(ROCKS), (px, h + .2, pz), (w * 1.3, .9, w * 1.2), rot=(0, rng.uniform(0, 180), 0),
              col=shade(sand, .85), cap=(rgb(.86, .74, .55), .7))


def build_floating_isles(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    rock, grass = rgb(.6, .56, .52), rgb(.45, .7, .38)
    for i in range(3):
        px, pz = (x, z) if i == 0 else polar(i * 140 + rng.uniform(-20, 20), r * .6, x, z)
        y = 7 + i * 1.8
        s = (2.6 if i == 0 else 1.6) * min(1, r / 5)
        b.add('cone8', (px, y - s * .8, pz), (s * 2, s * 2, s * 2), rot=(180, rng.uniform(0, 45), 0), col=rock, grad=.3)
        b.add('cyl16', (px, y + .1, pz), (s * 2.1, .5, s * 2.1), col=grass)
        b.add('blob_lo', (px, y + s * .9, pz), (s * 1.1, s * .9, s * 1.1), col=rgb(.4, .65, .34), wobble=.25)
    _wind_vane(b, x + 1.5, z + 1.5, 1.4, rng)


def build_obelisk(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    stone = rgb(.42, .32, .52)
    b.add('cyl16', (x, .3, z), (5, .6, 5), col=shade(stone, .85))
    b.add('prism5', (x, 4.5, z), (1.8, 9.0, 1.8), rot=(0, 18, 0), col=stone, grad=.4)
    b.add('cone6', (x, 11.2, z), (1.6, 2.6, 1.6), col=glowing(rgb(1, .55, .95), 1))
    b.add('cone6', (x, 9.7, z), (1.6, 1.2, 1.6), rot=(180, 0, 0), col=glowing(rgb(1, .55, .95), 1))
    for k, h in enumerate((3.0, 6.0, 9.0)):
        b.add('ring_thin', (x, h, z), (4.2 - k * .8, .15, 4.2 - k * .8), rot=(12 * (-1) ** k, k * 40, 0),
              col=glowing(rgb(.85, .5, 1), .9))
    for i in range(4):
        px, pz = polar(i * 90 + 45, r * .65, x, z)
        _crystal_psy(b, px, pz, 1.0, rng)


def build_hive(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    bark = rgb(.36, .28, .2)
    b.add('cyl16', (x, 2.0, z), (min(r, 6), 4.0, min(r, 6)), col=bark, grad=.35)
    b.add('cyl16', (x, 4.05, z), (min(r, 6) * .92, .1, min(r, 6) * .92), col=rgb(.6, .48, .32))
    for i in range(5):                            # racines
        a = i * 72 + rng.uniform(-15, 15)
        px, pz = polar(a, min(r, 6) * .5, x, z)
        b.add('cone6', (px, .6, pz), (1.2, 2.6, 1.2), rot=(0, a, 70), col=bark)
    for k in range(3):                            # ruche
        b.add('sphere', (x, 4.8 + k * 1.0, z), (3.0 - k * .7, 1.2, 3.0 - k * .7), col=rgb(.85, .66, .22), wobble=.1)
    b.add('sphere_lo', (x + .9, 5.2, z), .4, col=glowing(rgb(1, .8, .3), 1))
    for i in range(3):
        px, pz = polar(i * 120 + 60, r * .7, x, z)
        _cocoon(b, px, pz, 1.0, rng)
    _web(b, x, 3.0, z - min(r, 6) * .55, 2.2, 0)


def build_haunted_tower(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    stone = rgb(.38, .37, .42)
    b.add('cyl16', (x, 4.5, z), (4.0, 9.0, 4.0), col=stone, grad=.4)
    for k in range(6):                            # créneaux brisés
        a = k * 60
        px, pz = polar(a, 1.8, x, z)
        b.add('box', (px, 9.3 + rng.uniform(0, .8), pz), (1.0, rng.uniform(.6, 1.6), .7), rot=(0, a, 0), col=stone)
    for k in range(3):                            # fenêtres hantées
        px, pz = polar(rng.uniform(0, 360), 2.02, x, z)
        b.add('box', (px, 3 + k * 2.2, pz), (.5, .9, .1), rot=(0, math.degrees(math.atan2(px - x, pz - z)), 0),
              col=glowing(rgb(.65, .5, 1), 1))
    for i in range(5):
        px, pz = polar(i * 72 + rng.uniform(-10, 10), r * .7, x, z)
        _tombstone(b, px, pz, 1.0, rng)
    _ghost_tree(b, *polar(200, r * .5, x, z), 1.3, rng)


def build_skeleton(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    yaw = rng.uniform(0, 360)
    k = r / 7.5                                   # tout le squelette tient dans le rayon r
    n = 7
    for i in range(n):                            # colonne et côtes
        px, pz = polar(yaw, (i - n / 2) * 1.2 * k, x, z)
        b.add('sphere_lo', (px, .5 * k, pz), (.9 * k, .8 * k, .9 * k), col=BONE)
        if 0 < i < n - 1:
            for sd in (-1, 1):
                b.add('cone6', (px, 1.6 * k, pz), (.35 * k, (3.6 - abs(i - n / 2) * .3) * k, .35 * k),
                      rot=(0, yaw + 90, sd * 30), col=shade(BONE, .95))
    hx, hz = polar(yaw, (n / 2 * 1.2 + 1.0) * k, x, z)    # crâne
    b.add('sphere', (hx, 1.2 * k, hz), (2.2 * k, 1.6 * k, 2.8 * k), rot=(0, yaw, 0), col=BONE)
    jx, jz = polar(yaw, 1.4 * k, hx, hz)
    b.add('cone4', (jx, .9 * k, jz), (1.4 * k, 2.0 * k, .9 * k), rot=(90, yaw, 0), col=shade(BONE, .9))
    for sd in (-1, 1):                            # cornes et yeux
        qx, qz = polar(yaw + 90, .7 * sd * k, hx, hz)
        b.add('cone6', (qx, 2.3 * k, qz), (.4 * k, 2.2 * k, .4 * k), rot=(-30, yaw, sd * 20), col=rgb(.3, .28, .4))
        ex, ez = polar(yaw + 90, .5 * sd * k, jx, jz)
        b.add('sphere_xlo', (ex, 1.5 * k, ez), .35 * k, col=glowing(rgb(.5, .55, 1), 1))
    for i in range(2):
        px, pz = polar(yaw + 90 + i * 180, r * .55, x, z)
        _dragon_crystal(b, px, pz, 1.0, rng)


def build_dark_spire(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    black = rgb(.1, .09, .12)
    for k in range(5):
        h = 10 - k * 1.6
        b.add('cone6', (x + rng.uniform(-.4, .4), h * .5 + k * 1.4, z + rng.uniform(-.4, .4)), (2.6 - k * .35, h, 2.6 - k * .35),
              rot=(rng.uniform(-8, 8), k * 25, rng.uniform(-8, 8)), col=black)
    b.add('sphere', (x, 6.5, z), .9, col=glowing(rgb(1, .15, .2), 1))
    for i in range(6):
        px, pz = polar(i * 60 + rng.uniform(-15, 15), r * .6, x, z)
        _thorn(b, px, pz, 1.0, rng)


def build_iron_tower(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    H = 12.0
    for sx in (-1, 1):
        for sz in (-1, 1):
            b.add('box', (x + sx * 1.3, H / 2, z + sz * 1.3), (.35, H + .6, .35), rot=(sz * -6, 0, sx * 6), col=STEEL)
    for k in range(6):
        y = 1.6 + k * 1.8
        w = 3.2 - k * .3
        for rot in (0, 90):
            b.add('box', (x, y, z), (w, .2, .2), rot=(0, rot, 0), col=shade(STEEL, .85))
            b.add('box', (x, y + .9, z), (w * 1.3, .14, .14), rot=(0, rot + 45, 35), col=shade(STEEL, .75))
    b.add('cyl16', (x, H + .4, z), (1.4, .8, 1.4), col=rgb(.75, .55, .2))
    b.add('sphere', (x, H + 1.2, z), .8, col=glowing(rgb(.4, .9, 1), 1))
    for i in range(3):
        px, pz = polar(i * 120 + 30, r * .6, x, z)
        _gear(b, px, pz, .9, rng)
        _metal_block(b, *polar(i * 120 + 80, r * .55, x, z), .9, rng)


def build_fairy_ring(lm, x, z, r):
    b, rng = lm.st.b, lm.st.rng
    trunk = rgb(.55, .4, .45)
    b.add('cone8', (x, 2.5, z), (1.2, 5.0, 1.2), col=trunk)
    for i in range(7):
        ox, oz = polar(i * 51 + rng.uniform(-10, 10), 1.6)
        b.add('blob_lo', (x + ox, 5.2 + rng.uniform(-.4, .6), z + oz), 1.9, col=rng.choice(BLOSSOM), wobble=.25)
    b.add('cone6', (x, 1.0, z + 1.4), (1.0, 2.4, 1.0), col=glowing(rgb(1, .7, .95), .6))
    n = 9
    for i in range(n):                            # cercle de fleurs géantes et de champignons
        px, pz = polar(i * 360 / n, r * .65, x, z)
        (_giant_flower if i % 2 else _fairy_mushroom)(b, px, pz, 1.0, rng)


LANDMARK = {
    'normal': ('windmill', 6.0, 0.0, ('haystack', 'lantern')),
    'glace': ('ice_peak', 7.0, 2.5, ('ice_spike', 'snow_rock')),
    'combat': ('pagoda', 6.0, 0.0, ('bamboo', 'training_post')),
    'poison': ('giant_shrooms', 7.0, 0.0, ('toxic_mushroom', 'bubble_pool')),
    'sol': ('spires', 7.0, 1.5, ('boulder', 'cactus')),
    'vol': ('floating_isles', 6.0, 0.0, ('wind_tree', 'wind_vane')),
    'psy': ('obelisk', 6.0, 0.0, ('crystal_psy', 'floating_rock')),
    'insecte': ('hive', 6.0, 0.0, ('cocoon', 'web_tree')),
    'spectre': ('haunted_tower', 6.0, 0.0, ('tombstone', 'ghost_tree')),
    'dragon': ('skeleton', 7.0, 0.0, ('dragon_crystal', 'bone')),
    'tenebres': ('dark_spire', 6.0, 0.0, ('thorn', 'dark_tree')),
    'acier': ('iron_tower', 6.0, 0.0, ('gear', 'metal_block')),
    'fee': ('fairy_ring', 7.0, 0.0, ('fairy_mushroom', 'giant_flower')),
}
BUILDERS = {'windmill': build_windmill, 'ice_peak': build_ice_peak, 'pagoda': build_pagoda,
            'giant_shrooms': build_giant_shrooms, 'spires': build_spires, 'floating_isles': build_floating_isles,
            'obelisk': build_obelisk, 'hive': build_hive, 'haunted_tower': build_haunted_tower,
            'skeleton': build_skeleton, 'dark_spire': build_dark_spire, 'iron_tower': build_iron_tower,
            'fairy_ring': build_fairy_ring, 'cluster': build_cluster}


# ==================================================================== branchement
def install_arenas(cls):
    """Ajoute à ArenaDecor un build_<type> pour chaque thème ajouté."""
    for t in ARENA:
        setattr(cls, 'build_' + t, lambda self, t=t: build_arena(self, t))


def install_landmarks(cls):
    """Ajoute à Landmarks un plan_<type> par thème ajouté et un build_<genre> par grand décor."""
    for t, (kind, size, hill, small) in LANDMARK.items():
        setattr(cls, 'plan_' + t, lambda self, main, side, inner, k=kind, s=size, h=hill, sm=small:
                _plan(self, main, side, inner, k, s, h, sm))
    for kind, fn in BUILDERS.items():
        setattr(cls, 'build_' + kind, lambda self, x, z, r, fn=fn, **kw: fn(self, x, z, r, **kw))
