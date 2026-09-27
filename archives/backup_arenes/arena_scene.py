"""Décor 3D de l'intérieur d'une arène de combat (sol, gradins, public...)."""
import math
import random

from ursina import color, lerp

import config as C
from emblems import add_emblem
from geometry import MeshBuilder

R = C.BATTLE_ARENA_RADIUS


def build_battle_arena(root, type_key):
    t = C.TYPES[type_key]
    b = MeshBuilder()
    glow = MeshBuilder()
    b.add('disc', (0, -.2, 0), ((R + 1.5) * 2, .4, (R + 1.5) * 2), col=t['floor'])
    b.add('ring_thin', (0, .012, 0), (R * 2, .02, R * 2), col=color.rgb(1, 1, 1))
    b.add('ring_thin', (0, .012, 0), (7, .02, 7), col=color.rgb(1, 1, 1))
    b.add('box', (0, .012, 0), (R * 2 - 1, .02, .22), col=color.rgb(1, 1, 1))
    b.add('disc', (0, .006, 0), (R * 1.25, .01, R * 1.25), col=lerp(t['floor'], t['light'], .18))
    # murs et gradins
    b.add('ring_thin', (0, .6, 0), ((R + 1.2) * 2, 1.2, (R + 1.2) * 2), col=t['dark'])
    rng = random.Random(3)
    for i in range(4):
        outer = R + 3.2 + i * 2.2
        h = 1.6 + i * 1.3
        b.add('ring', (0, h / 2, 0), (outer * 2, h, outer * 2),
              col=t['color'] if i % 2 == 0 else lerp(t['color'], color.white, .35))
        # spectateurs
        for _ in range(60):
            a = rng.uniform(0, math.tau)
            rr = outer - 1.1
            col = rng.choice([color.rgb(.9, .3, .3), color.rgb(.3, .5, .9), color.rgb(.95, .85, .3),
                              color.rgb(.35, .8, .4), color.rgb(.9, .9, .9), color.rgb(.6, .4, .8)])
            b.add('cyl6', (math.sin(a) * rr, h + .4, math.cos(a) * rr), (.45, .8, .45), col=col)
            b.add('sphere', (math.sin(a) * rr, h + 1.0, math.cos(a) * rr), .4, col=color.rgb(1, .85, .7))
    # piliers avec symbole du type
    for i in range(6):
        a = math.radians(i * 60 + 30)
        x, z = math.sin(a) * (R + 2.2), math.cos(a) * (R + 2.2)
        b.add('cyl', (x, 2.2, z), (1.1, 4.4, 1.1), col=color.rgb(.92, .9, .86))
        b.add('box', (x, 4.5, z), (1.6, .3, 1.6), col=t['dark'])
        add_emblem(glow, type_key, (x, 5.6, z), .55)
    _type_props(type_key, b, glow, rng)
    b.entity(parent=root)
    glow.entity(parent=root, emissive=.8)


def _type_props(k, b, glow, rng):
    for _ in range(10):
        a = rng.uniform(0, math.tau)
        rr = R + .5 + rng.uniform(0, .6)
        x, z = math.sin(a) * rr, math.cos(a) * rr
        if k == 'feu':
            glow.add('disc', (math.sin(a) * (R - .8), .02, math.cos(a) * (R - .8)), (2, .02, 1.2),
                     rot=(0, math.degrees(a), 0), col=color.rgb(1, .45, .05))
        elif k == 'eau':
            b.add('disc', (math.sin(a) * (R - 1), .015, math.cos(a) * (R - 1)), (2.6, .02, 2),
                  col=color.rgb(.3, .6, .95))
        elif k == 'plante':
            b.add('sphere', (x, .7, z), (1.8, 1.4, 1.8), col=color.rgb(.2, .55, .2))
            b.add('sphere', (x, 1.3, z), .35, col=color.rgb(1, .45, .6))
        elif k == 'roche':
            b.add('sphere', (x, .6, z), (1.8, 1.3, 1.5), rot=(0, rng.uniform(0, 180), 0), col=color.rgb(.5, .45, .4))
        elif k == 'glace':
            b.add('cone6', (x, 1.2, z), (.9, 2.4, .9), rot=(rng.uniform(-15, 15), 0, rng.uniform(-15, 15)),
                  col=color.rgb(.7, .93, 1))
    if k == 'feu':   # braseros
        for i in range(4):
            a = math.radians(i * 90 + 45)
            x, z = math.sin(a) * (R - 1.5), math.cos(a) * (R - 1.5)
            b.add('cyl', (x, .5, z), (1.2, 1, 1.2), col=color.rgb(.3, .25, .25))
            glow.add('cone', (x, 1.6, z), (1.1, 1.6, 1.1), col=color.rgb(1, .5, .1))
