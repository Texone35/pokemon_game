"""Modèles 3D procéduraux des Pokémon et leurs animations simples.

Chaque Pokémon est découpé en quelques groupes (corps, tête, queue...) :
chaque groupe est un seul maillage, ce qui permet de l'animer sans multiplier
les entités.
"""
import math

from panda3d.core import CullFaceAttrib
from ursina import Entity, Vec3, Vec4, color

from game.world.geometry import MeshBuilder, flat_circle

OUTLINE = .022        # épaisseur du contour sombre (0 pour le désactiver)

# Les Pokémon utilisent des primitives plus fines que le décor : silhouettes lisses.
SMOOTH = {'sphere': 'sphere_md', 'sphere_lo': 'sphere_md', 'sphere_xlo': 'sphere_md', 'cyl': 'cyl16',
          'cyl6': 'cyl16', 'cyl8': 'cyl16', 'cone': 'cone16', 'cone6': 'cone16', 'cone8': 'cone16'}


class SmoothBuilder(MeshBuilder):
    """MeshBuilder pour les Pokémon : formes lisses et léger dégradé (dessous plus sombre)."""

    def add(self, prim, pos=(0, 0, 0), scale=1, rot=(0, 0, 0), col=color.white, wobble=0.0, grad=.2):
        return super().add(SMOOTH.get(prim, prim), pos, scale, rot, col, wobble=wobble, grad=grad)

BLACK = color.rgb(.08, .06, .06)
WHITE = color.rgb(1, 1, 1)


def _eyes(b, x, y, z, sx=.12, sy=.16, iris=BLACK, shine=True):
    for side in (-1, 1):
        b.add('sphere', (side * x, y, z), (sx, sy, sx * .7), col=iris)
        if shine:
            b.add('sphere', (side * x - side * .02, y + sy * .22, z + sx * .3), sx * .35, col=WHITE)


# ---------------------------------------------------------------- espèces
def _mouth(b, y, z, w=.07, col=BLACK):
    """Petite bouche en « w »."""
    for s in (-1, 1):
        b.add('box', (s * w * .45, y, z), (w, .018, .02), rot=(0, 0, s * 28), col=col)


def build_pikachu(g):
    Y, Y2 = color.rgb(1, .86, .2), color.rgb(1, .93, .45)
    BROWN, RED = color.rgb(.52, .3, .1), color.rgb(.9, .16, .12)
    b = g['body']
    b.add('sphere', (0, .5, 0), (.74, .84, .64), col=Y)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .07, .1), (.24, .14, .34), col=Y)             # pieds
        for k in (-1, 0, 1):
            b.add('sphere', (s * .2 + k * .06, .05, .26), .06, col=Y2)          # orteils
        b.add('sphere', (s * .3, .62, .2), (.13, .24, .13), rot=(35, 0, s * 20), col=Y)   # bras
        b.add('sphere', (s * .33, .52, .3), .1, col=Y2)                        # pattes
    for y in (.74, .58):                                                        # rayures du dos
        b.add('sphere', (0, y, -.29), (.36, .06, .1), col=BROWN)
    h = g['head']
    h.add('sphere', (0, .28, .02), (.82, .72, .7), col=Y)
    for s in (-1, 1):
        axis = Vec3(s * math.sin(math.radians(22)), math.cos(math.radians(22)), 0)
        centre = Vec3(s * .24, .68, -.02) + axis * .12
        h.add('cone', tuple(centre), (.19, .66, .12), rot=(0, 0, -s * 22), col=Y)
        h.add('cone', tuple(centre + axis * .25), (.11, .2, .075), rot=(0, 0, -s * 22), col=BLACK)
        h.add('sphere', (s * .28, .17, .26), (.18, .15, .08), col=RED)          # joues
    _eyes(h, .16, .36, .3, .12, .15)
    h.add('sphere', (0, .27, .37), (.05, .035, .03), col=BLACK)                 # nez
    _mouth(h, .19, .36)
    t = g['tail']                                                               # queue en éclair
    t.add('box', (0, .06, -.1), (.07, .24, .1), rot=(-40, 0, 0), col=BROWN)
    t.add('box', (0, .24, -.24), (.08, .12, .38), rot=(25, 0, 0), col=Y)
    t.add('box', (0, .44, -.36), (.08, .3, .14), rot=(-10, 0, 0), col=Y)
    t.add('box', (0, .66, -.44), (.08, .5, .36), rot=(-15, 0, 0), col=Y)
    return {'head_pivot': (0, .95, 0), 'tail_pivot': (0, .4, -.32)}


def build_salameche(g):
    O, CREAM, BLUE = color.rgb(1, .52, .2), color.rgb(1, .88, .55), color.rgb(.15, .3, .6)
    CLAW = color.rgb(.98, .96, .9)
    b = g['body']
    b.add('sphere', (0, .55, 0), (.7, .86, .64), col=O)
    b.add('sphere', (0, .5, .15), (.5, .64, .42), col=CREAM)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .1, .08), (.24, .2, .36), col=O)                # pieds
        for k in (-1, 0, 1):
            b.add('cone', (s * .2 + k * .06, .06, .27), (.04, .09, .04), rot=(90, 0, 0), col=CLAW)
        b.add('sphere', (s * .33, .66, .18), (.15, .28, .15), rot=(35, 0, s * 15), col=O)   # bras
        b.add('sphere', (s * .37, .54, .3), .11, col=O)
        for k in (-1, 1):
            b.add('cone', (s * .37 + k * .03, .5, .36), (.03, .07, .03), rot=(120, 0, 0), col=CLAW)
    h = g['head']
    h.add('sphere', (0, .32, .04), (.74, .7, .72), col=O)
    h.add('sphere', (0, .2, .27), (.5, .36, .4), col=O)                          # museau
    _eyes(h, .18, .38, .29, .13, .2, iris=BLUE)
    for s in (-1, 1):
        h.add('sphere', (s * .06, .27, .46), .025, col=color.rgb(.3, .12, .05))   # narines
    h.add('box', (0, .12, .44), (.26, .025, .03), col=color.rgb(.45, .15, .08))   # bouche
    t = g['tail']
    t.add('cone', (0, .12, -.28), (.24, .72, .24), rot=(-65, 0, 0), col=O)
    t.add('sphere', (0, .02, -.08), .2, col=O)
    f = g['glow']   # flamme de la queue : trois couches
    f.add('sphere', (0, .3, -.6), (.34, .44, .34), col=color.rgb(.95, .25, .05))
    f.add('cone', (0, .52, -.6), (.28, .55, .28), col=color.rgb(1, .5, .08))
    f.add('cone', (0, .5, -.6), (.15, .45, .15), col=color.rgb(1, .9, .35))
    return {'head_pivot': (0, .98, 0), 'tail_pivot': (0, .35, -.25), 'glow_parent': 'tail'}


def build_carapuce(g):
    B, SHELL, BELLY = color.rgb(.46, .76, .95), color.rgb(.6, .34, .14), color.rgb(1, .88, .55)
    PLATE, RIM = color.rgb(.5, .27, .1), color.rgb(.97, .96, .9)
    b = g['body']
    b.add('sphere', (0, .55, 0), (.68, .8, .62), col=B)
    b.add('sphere', (0, .58, -.14), (.88, .92, .64), col=SHELL)                 # carapace
    for x, y in ((0, .78), (-.2, .56), (.2, .56), (0, .38), (-.18, .8), (.18, .8)):
        b.add('sphere', (x, y, -.43), (.2, .18, .06), col=PLATE)                # écailles
    b.add('sphere', (0, .55, .17), (.58, .74, .38), col=BELLY)                  # plastron
    for y in (.72, .55, .4):
        b.add('box', (0, y, .35), (.4, .02, .02), col=color.rgb(.8, .65, .35))
    b.add('cyl', (0, .58, -.12), (.92, .12, .68), col=RIM)
    for s in (-1, 1):
        b.add('sphere', (s * .2, .08, .1), (.23, .16, .33), col=B)
        b.add('sphere', (s * .37, .64, .16), (.15, .27, .15), rot=(35, 0, s * 20), col=B)
        b.add('sphere', (s * .4, .52, .27), .11, col=B)
    h = g['head']
    h.add('sphere', (0, .3, .06), (.76, .7, .72), col=B)
    _eyes(h, .17, .37, .33, .15, .2, iris=color.rgb(.45, .12, .1))
    h.add('box', (0, .17, .42), (.24, .025, .03), rot=(0, 0, 0), col=color.rgb(.2, .15, .2))
    t = g['tail']                                                               # queue en spirale
    t.add('sphere', (0, .05, -.15), (.26, .26, .34), col=B)
    t.add('sphere', (0, .2, -.3), (.26, .28, .24), col=B)
    t.add('sphere', (0, .34, -.22), (.18, .18, .18), col=B)
    t.add('sphere', (0, .3, -.12), (.12, .12, .12), col=color.rgb(.36, .62, .86))
    return {'head_pivot': (0, .98, 0), 'tail_pivot': (0, .3, -.45)}


def build_bulbizarre(g):
    T, SPOT, BULB = color.rgb(.46, .8, .7), color.rgb(.22, .55, .47), color.rgb(.32, .7, .34)
    LEAF, CLAW = color.rgb(.2, .55, .25), color.rgb(.97, .97, .95)
    b = g['body']
    b.add('sphere', (0, .5, -.05), (.95, .66, 1.1), col=T)
    for sx in (-1, 1):
        for sz in (-1, 1):
            b.add('cyl', (sx * .3, .18, sz * .32), (.27, .36, .27), col=T)
            b.add('sphere', (sx * .3, .03, sz * .32 + .06), (.28, .12, .3), col=T)
            for k in (-1, 0, 1):
                b.add('cone', (sx * .3 + k * .07, .03, sz * .32 + .2), (.04, .08, .04), rot=(90, 0, 0), col=CLAW)
    for p, sc in (((.3, .66, .1), (.18, .08, .22)), ((-.26, .7, -.26), (.22, .08, .17)),
                  ((.1, .75, -.4), (.16, .07, .14)), ((-.34, .56, .2), (.14, .07, .16))):
        b.add('sphere', p, sc, col=SPOT)
    h = g['head']
    h.add('sphere', (0, .12, .22), (.88, .66, .72), col=T)
    for s in (-1, 1):
        h.add('cone', (s * .3, .46, .12), (.17, .24, .15), rot=(0, 0, -s * 25), col=T)
        h.add('sphere', (s * .25, .2, .5), (.14, .16, .08), col=color.rgb(.85, .12, .12))
        h.add('sphere', (s * .23, .24, .54), .045, col=WHITE)
    h.add('sphere', (0, .02, .56), (.42, .08, .05), col=color.rgb(.4, .12, .14))
    for s in (-1, 1):
        h.add('cone', (s * .1, .03, .57), (.04, .06, .03), rot=(180, 0, 0), col=WHITE)   # crocs
    t = g['tail']   # le bulbe et ses feuilles (pulsation)
    t.add('sphere', (0, .1, 0), (.84, .8, .84), col=BULB)
    t.add('cone', (0, .52, 0), (.48, .36, .48), col=LEAF)
    for i in range(6):                  # feuilles recourbées qui enveloppent le bulbe
        a = math.radians(i * 60 + 30)
        t.add('sphere', (math.sin(a) * .36, .08, math.cos(a) * .36), (.3, .07, .62), rot=(-62, i * 60 + 30, 0),
              col=LEAF if i % 2 else color.rgb(.26, .62, .3))
    for i in range(3):
        a = math.radians(i * 120)
        t.add('sphere', (math.sin(a) * .42, -.24, math.cos(a) * .42), (.34, .06, .56), rot=(12, i * 120, 0), col=LEAF)
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
    return {'tail_pivot': (0, 0, 0), 'float': True, 'no_head': True}


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


def build_rattata(g):
    P, CREAM, PINK = color.rgb(.62, .45, .78), color.rgb(.95, .88, .7), color.rgb(.95, .6, .7)
    b = g['body']
    b.add('sphere', (0, .38, -.05), (.7, .6, .9), col=P)
    b.add('sphere', (0, .33, .12), (.5, .42, .5), col=CREAM)
    for sx in (-1, 1):
        for sz in (-1, 1):
            b.add('sphere', (sx * .22, .07, sz * .25), (.16, .12, .24), col=P)
    h = g['head']
    h.add('sphere', (0, .2, .1), (.62, .56, .62), col=P)
    h.add('sphere', (0, .12, .35), (.32, .26, .3), col=CREAM)
    for s in (-1, 1):
        h.add('sphere', (s * .26, .5, 0), (.3, .34, .1), col=P)
        h.add('sphere', (s * .26, .5, .03), (.2, .24, .06), col=PINK)
        h.add('box', (s * .2, .1, .45), (.3, .015, .015), rot=(0, 0, s * 10), col=BLACK)
    for s in (-1, 1):
        h.add('box', (s * .025, -.03, .46), (.04, .08, .03), col=WHITE)                # incisives
    _eyes(h, .14, .28, .36, .1, .14, iris=color.rgb(.7, .1, .15))
    t = g['tail']
    for i in range(5):
        t.add('sphere', (0, .05 + i * .07, -.1 - i * .12), .09, col=P)
    t.add('sphere', (0, .45, -.62), (.12, .12, .12), col=P)
    return {'head_pivot': (0, .55, .35), 'tail_pivot': (0, .3, -.4)}


def build_magmar(g):
    Y, R, DARK = color.rgb(1, .78, .25), color.rgb(.95, .3, .12), color.rgb(.3, .15, .1)
    b = g['body']
    b.add('sphere', (0, .75, 0), (.8, 1.0, .7), col=Y)
    b.add('sphere', (0, .72, .12), (.55, .75, .5), col=R)
    for s in (-1, 1):
        b.add('cyl', (s * .22, .22, 0), (.26, .45, .26), col=Y)
        b.add('sphere', (s * .22, .04, .08), (.26, .12, .34), col=R)
        b.add('sphere', (s * .45, .95, .1), (.2, .45, .2), rot=(30, 0, s * 25), col=Y)
        b.add('sphere', (s * .52, .7, .28), .15, col=R)
    h = g['head']
    h.add('sphere', (0, .25, .05), (.6, .55, .6), col=Y)
    h.add('box', (0, .15, .3), (.28, .12, .2), col=Y)
    _eyes(h, .14, .32, .3, .1, .08, iris=BLACK, shine=False)
    for s in (-1, 1):
        h.add('box', (s * .14, .4, .32), (.18, .04, .04), rot=(0, 0, s * 20), col=DARK)
    f = g['glow']
    for i, (x, y, z) in enumerate(((0, 1.62, -.05), (.18, 1.55, -.1), (-.18, 1.55, -.1), (0, 1.5, -.25))):
        f.add('cone', (x, y, z), (.28, .55, .28), rot=(-15, 0, x * 60), col=color.rgb(1, .45 + i * .08, .05))
    f.add('sphere', (0, .3, -.5), (.25, .25, .35), col=color.rgb(1, .5, .1))
    t = g['tail']
    t.add('cone', (0, .1, -.4), (.2, .6, .2), rot=(-70, 0, 0), col=Y)
    return {'head_pivot': (0, 1.25, 0), 'tail_pivot': (0, .4, -.2)}


def build_lokhlass(g):
    B, CREAM, SHELL = color.rgb(.35, .62, .9), color.rgb(.95, .92, .8), color.rgb(.55, .6, .7)
    b = g['body']
    b.add('sphere', (0, .6, -.2), (1.3, .9, 1.6), col=B)
    b.add('dome', (0, .78, -.35), (1.35, .9, 1.5), col=SHELL)
    for x, z in ((0, -.3), (.35, -.1), (-.35, -.1), (.3, -.65), (-.3, -.65)):
        b.add('cone', (x, 1.15, z - .05), (.18, .3, .18), col=color.rgb(.4, .42, .5))
    b.add('sphere', (0, .45, .15), (.9, .6, .9), col=CREAM)
    for s in (-1, 1):
        b.add('sphere', (s * .7, .35, .2), (.7, .12, .35), rot=(0, s * 30, s * -15), col=B)
        b.add('sphere', (s * .5, .25, -.9), (.5, .1, .3), rot=(0, s * -30, 0), col=B)
    b.add('cyl', (0, 1.0, .45), (.35, .9, .35), rot=(30, 0, 0), col=B)
    h = g['head']
    h.add('sphere', (0, .15, .1), (.55, .5, .65), col=B)
    h.add('cone', (0, .5, .05), (.14, .35, .14), col=color.rgb(.8, .85, .9))
    for s in (-1, 1):
        h.add('sphere', (s * .24, .3, -.02), (.14, .2, .1), col=B)
    _eyes(h, .16, .2, .33, .1, .12, iris=color.rgb(.1, .1, .2))
    return {'head_pivot': (0, 1.5, .75), 'no_tail': True}


def build_torterra(g):
    G, BROWN = color.rgb(.45, .62, .35), color.rgb(.5, .35, .2)
    ROCK, LEAF = color.rgb(.55, .5, .45), color.rgb(.2, .55, .2)
    b = g['body']
    b.add('sphere', (0, .6, 0), (1.5, .9, 1.9), col=G)
    b.add('dome', (0, .85, -.1), (1.6, .9, 1.9), col=BROWN)
    for sx in (-1, 1):
        for sz in (-1, 1):
            b.add('cyl', (sx * .55, .25, sz * .55), (.45, .5, .45), col=G)
    for x, z in ((.45, .3), (-.5, .2), (.4, -.6), (-.45, -.55)):
        b.add('cone4', (x, 1.35, z), (.4, .5, .4), col=ROCK)
    b.add('cyl6', (0, 1.6, -.15), (.22, .9, .22), col=color.rgb(.45, .3, .18))
    for p, r in (((0, 2.2, -.15), .8), ((.3, 2.05, 0), .55), ((-.3, 2.05, -.3), .55), ((0, 2.5, -.2), .5)):
        b.add('sphere', p, r, col=LEAF)
    h = g['head']
    h.add('sphere', (0, .1, .15), (.6, .5, .65), col=G)
    h.add('sphere', (0, .32, .05), (.55, .15, .5), col=color.rgb(.3, .3, .3))
    _eyes(h, .18, .16, .38, .09, .1, iris=color.rgb(.9, .75, .2), shine=False)
    return {'head_pivot': (0, .7, .95), 'no_tail': True}


def build_mewtwo(g):
    L, P = color.rgb(.85, .8, .88), color.rgb(.6, .4, .75)
    b = g['body']
    b.add('sphere', (0, 1.1, 0), (.5, .7, .42), col=L)
    b.add('sphere', (0, .75, -.02), (.55, .55, .5), col=P)
    for s in (-1, 1):
        b.add('cyl', (s * .16, .3, 0), (.18, .6, .18), col=L)
        b.add('sphere', (s * .16, .02, .08), (.18, .1, .3), col=L)
        b.add('cyl', (s * .38, 1.1, .1), (.12, .6, .12), rot=(30, 0, s * 35), col=L)
        b.add('sphere', (s * .5, .85, .3), .13, col=L)
    b.add('cyl', (0, 1.45, -.15), (.1, .5, .1), rot=(-50, 0, 0), col=L)
    h = g['head']
    h.add('sphere', (0, .15, .02), (.4, .36, .42), col=L)
    for s in (-1, 1):
        h.add('cone', (s * .15, .38, -.02), (.12, .25, .1), rot=(0, 0, -s * 25), col=L)
    _eyes(h, .09, .17, .19, .08, .06, iris=color.rgb(.5, .15, .6), shine=False)
    t = g['tail']
    for i in range(6):
        t.add('sphere', (0, .05 + i * .12, -.15 - i * .15), .22 - i * .015, col=P)
    f = g['glow']
    f.add('sphere', (0, 1.0, .3), .12, col=color.rgb(.9, .6, 1))
    return {'head_pivot': (0, 1.5, .05), 'tail_pivot': (0, .5, -.2)}


def build_regigigas(g):
    W, STRIPE, GREEN = color.rgb(.92, .9, .85), color.rgb(.2, .18, .2), color.rgb(.35, .6, .3)
    b = g['body']
    b.add('sphere', (0, 1.25, 0), (1.3, 1.3, 1.0), col=W)
    b.add('box', (0, 1.25, 0), (1.34, .12, 1.04), col=STRIPE)
    for s in (-1, 1):
        b.add('cyl', (s * .38, .35, 0), (.45, .75, .45), col=W)
        b.add('cyl', (s * .38, .38, 0), (.5, .12, .5), col=STRIPE)
        b.add('sphere', (s * .38, .02, .1), (.5, .16, .6), col=GREEN)
    h = g['head']
    h.add('sphere', (0, .15, .05), (.6, .45, .5), col=W)
    dots = (color.rgb(1, .85, .2), color.rgb(.95, .25, .2), color.rgb(.3, .5, 1),
            color.rgb(.95, .25, .2), color.rgb(1, .85, .2))
    for i, c in enumerate(dots):
        h.add('sphere', ((i - 2) * .1, .2 + (abs(i - 2) == 1) * .06, .28), .08, col=c)
    t = g['tail']   # bras (coordonnées "corps", pivot au centre du torse)
    for s in (-1, 1):
        t.add('sphere', (s * .75, 1.5, 0), (.5, .45, .45), col=W)
        t.add('cyl', (s * .95, .95, .05), (.4, 1.0, .4), rot=(0, 0, s * 10), col=W)
        t.add('box', (s * 1.0, 1.1, .05), (.44, .1, .44), col=STRIPE)
        t.add('sphere', (s * 1.02, .35, .1), (.55, .45, .5), col=W)
    return {'head_pivot': (0, 1.9, .1), 'tail_pivot': (0, 0, 0), 'pulse': True}

def build_chenipan(g):
    G, Y, R = color.rgb(.45, .8, .3), color.rgb(1, .9, .45), color.rgb(.95, .3, .2)
    b = g['body']
    for i in range(4):
        z = -.15 - i * .26
        b.add('sphere', (0, .22 + (i % 2) * .03, z), (.42 - i * .03, .4 - i * .03, .36), col=G)
        b.add('sphere', (0, .12, z + .04), (.2, .12, .12), col=Y)
    h = g['head']
    h.add('sphere', (0, .15, .08), (.5, .5, .48), col=G)
    h.add('sphere', (0, .05, .28), (.28, .18, .1), col=Y)
    h.add('cone6', (0, .5, .02), (.1, .3, .1), col=R)
    for s in (-1, 1):
        h.add('sphere', (s * .17, .2, .26), (.14, .18, .08), col=BLACK)
        h.add('sphere', (s * .17, .2, .3), (.06, .08, .04), col=Y)
    return {'head_pivot': (0, .35, .1), 'no_tail': True}


def build_roucool(g):
    B, CREAM, BEAK = color.rgb(.62, .45, .28), color.rgb(.95, .88, .7), color.rgb(.35, .3, .28)
    b = g['body']
    b.add('sphere', (0, .45, 0), (.62, .62, .66), col=B)
    b.add('sphere', (0, .42, .14), (.44, .5, .4), col=CREAM)
    for s in (-1, 1):
        b.add('sphere', (s * .3, .5, -.05), (.14, .36, .42), rot=(20, 0, s * 15), col=color.rgb(.5, .35, .2))
        b.add('cone6', (s * .12, .08, .08), (.06, .2, .06), rot=(180, 0, 0), col=color.rgb(.85, .6, .45))
    h = g['head']
    h.add('sphere', (0, .15, .05), (.48, .46, .48), col=B)
    h.add('cone6', (0, .12, .32), (.12, .22, .12), rot=(90, 0, 0), col=BEAK)
    h.add('sphere', (0, .38, 0), (.14, .22, .2), rot=(-20, 0, 0), col=color.rgb(.75, .55, .35))
    _eyes(h, .13, .2, .22, .08, .1)
    t = g['tail']
    t.add('box', (0, 0, -.2), (.3, .05, .35), rot=(-20, 0, 0), col=color.rgb(.45, .3, .18))
    return {'head_pivot': (0, .78, .1), 'tail_pivot': (0, .35, -.3)}


def build_mystherbe(g):
    BL, L = color.rgb(.3, .4, .75), color.rgb(.3, .7, .3)
    b = g['body']
    b.add('sphere', (0, .32, 0), (.6, .58, .56), col=BL)
    for s in (-1, 1):
        b.add('sphere', (s * .16, .04, .05), (.18, .1, .24), col=BL)
    _eyes(b, .12, .38, .25, .08, .1, iris=color.rgb(.8, .1, .1))
    t = g['tail']      # feuilles sur la tête (pulsation)
    for i in range(5):
        a = math.radians(i * 72)
        t.add('sphere', (math.sin(a) * .16, .25, math.cos(a) * .16), (.16, .5, .1), rot=(0, i * 72, 25), col=L)
    return {'tail_pivot': (0, .6, 0), 'pulse': True, 'no_head': True}


BUILDERS = {
    'pikachu': build_pikachu,
    'salameche': build_salameche,
    'carapuce': build_carapuce,
    'bulbizarre': build_bulbizarre,
    'racaillou': build_racaillou,
    'stalgamin': build_stalgamin,
    'rattata': build_rattata,
    'magmar': build_magmar,
    'lokhlass': build_lokhlass,
    'torterra': build_torterra,
    'mewtwo': build_mewtwo,
    'regigigas': build_regigigas,
    'chenipan': build_chenipan,
    'roucool': build_roucool,
    'mystherbe': build_mystherbe,
}


class Creature(Entity):
    """Un Pokémon 3D animé. Racine = position au sol, regarde vers +z."""

    def __init__(self, species, scale=1.0, **kwargs):
        super().__init__(**kwargs)
        groups = {k: SmoothBuilder() for k in ('body', 'head', 'tail', 'glow')}
        info = BUILDERS[species](groups)
        self.info = info
        self.species = species

        self.pivot = Entity(parent=self, scale=scale)      # reçoit bob / inclinaison
        self.parts = []

        def part(group, parent, offset=Vec3(0, 0, 0), emissive=0.0):
            # tête et queue sont modélisées dans le repère de leur pivot (articulation)
            e = group.entity(parent=parent, emissive=emissive, position=offset)
            self.parts.append(e)
            if OUTLINE and not emissive and group.outline(OUTLINE).count:
                o = group.outline(OUTLINE).entity(parent=parent, emissive=1.0, position=offset, double_sided=False)
                o.setAttrib(CullFaceAttrib.make(CullFaceAttrib.M_cull_clockwise))
            return e

        self.body = part(groups['body'], self.pivot)

        self.head = None
        if groups['head'].count:
            hp = Vec3(*info.get('head_pivot', (0, 1, 0)))
            self.head = Entity(parent=self.pivot, position=hp)
            part(groups['head'], self.head)

        self.tail = None
        if groups['tail'].count:
            tp = Vec3(*info.get('tail_pivot', (0, .5, -.3)))
            self.tail = Entity(parent=self.pivot, position=tp)
            part(groups['tail'], self.tail)

        self.glow = None
        if groups['glow'].count:
            parent = self.tail if info.get('glow_parent') == 'tail' and self.tail else self.pivot
            origin = Vec3(*info.get('tail_pivot', (0, 0, 0))) if parent is self.tail else Vec3(0, 0, 0)
            self.glow = part(groups['glow'], parent, -origin, emissive=1.0)

        self.shadow = flat_circle(self, .55 * scale * (1.4 if species in ('bulbizarre', 'racaillou', 'lokhlass', 'torterra', 'regigigas') else 1),
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


class Portraits:
    """Portraits des Pokémon (vus de trois quarts face) rendus une fois hors écran dans une
    seule texture, côte à côte : pour les icônes de la mini-carte."""
    SIZE = 128

    def __init__(self, species):
        from panda3d.core import NodePath, OrthographicLens, Texture as PandaTexture
        from ursina import Texture, application
        from game.world.geometry import ENV
        base = application.base
        self.species = list(dict.fromkeys(species))
        n = len(self.species)
        tex = PandaTexture('portraits')
        self.buffer = base.win.make_texture_buffer('portraits', self.SIZE * n, self.SIZE, tex)
        self.buffer.set_clear_color((0, 0, 0, 0))
        self.buffer.set_clear_color_active(True)
        self.scene = NodePath('portraits')
        for k, v in ENV.items():
            self.scene.set_shader_input(k, v)
        self.scene.set_shader_input('fog_color', Vec4(0, 0, 0, 0))
        self.scene.set_shader_input('sky_color', Vec4(1.05, 1.05, 1.1, 1))     # pas de soleil ici : ambiance claire
        self.scene.set_shader_input('ground_color', Vec4(.7, .68, .66, 1))
        lens = OrthographicLens()
        lens.set_film_size(2.0 * n, 2.0)
        cam = base.make_camera(self.buffer, lens=lens, scene=self.scene)
        cam.reparent_to(self.scene)
        # la caméra est devant les Pokémon (qui regardent vers +z) : la case k est à x = -2k
        cam.set_pos(1 - n, 1.4, 9)
        cam.look_at(1 - n, 1.0, 0)
        self.scene.set_shader_input('cam_pos', cam.get_pos())
        self.cam = cam
        self.models = []
        for k, sp in enumerate(self.species):
            c = Creature(sp)
            c.reparent_to(self.scene)
            c.shadow.detach_node()
            lo, hi = c.get_tight_bounds(self.scene)
            c.set_scale(1.9 / max(hi.x - lo.x, hi.y - lo.y, .01))
            c.set_h(-25)                      # trois quarts face
            lo, hi = c.get_tight_bounds(self.scene)
            c.set_pos(c.get_x() - k * 2 - (lo.x + hi.x) / 2, c.get_y() + 1.0 - (lo.y + hi.y) / 2, 0)
            self.models.append(c)
        self.texture = Texture(tex)
        self._frames = 4                      # quelques images de rendu, puis on fige la texture

    def tick(self):
        """A appeler à chaque image tant que les modèles existent."""
        if not self.models:
            return
        self._frames -= 1
        if self._frames > 0:
            return
        from ursina import destroy
        self.buffer.set_active(False)
        for c in self.models:
            destroy(c)
        self.models = []

    def dispose(self):
        from ursina import application
        self._frames = 0
        self.tick()
        application.base.graphicsEngine.remove_window(self.buffer)

    def icon(self, parent, species, **kwargs):
        """Quad affichant le portrait de `species`."""
        n, k = len(self.species), self.species.index(species)
        e = Entity(parent=parent, model='quad', texture=self.texture, texture_scale=(1 / n, 1),
                   texture_offset=(k / n, 0), **kwargs)
        e.set_transparency(True)
        return e
