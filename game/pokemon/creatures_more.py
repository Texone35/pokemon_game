"""Modèles 3D des lignées supplémentaires (voir config._line) : un constructeur par lignée,
qui reçoit l'étape d'évolution (0 : forme de base, 1 : 1re évolution, 2 : 2e évolution).

Même principe que creatures.py : groupes 'body', 'head' (repère de son articulation),
'tail' (repère de son pivot) et 'glow' (parties lumineuses).
"""
import math
import random

from ursina import Vec3, color

from game.pokemon.creatures import BLACK, WHITE, _eyes, _polar_ear

rgb = color.rgb


def _limbs(b, col, hip, leg, foot, arm_y, arm, hand, claw=None, spread=.22, arm_x=.36):
    """Jambes et bras d'un bipède (tailles relatives)."""
    for s in (-1, 1):
        b.add('cyl', (s * spread, hip, 0), (leg, hip * 1.4, leg), col=col)
        b.add('sphere', (s * spread, .07, .1), (foot, foot * .55, foot * 1.4), col=col)
        if claw is not None:
            for k in (-1, 0, 1):
                b.add('cone', (s * spread + k * foot * .3, .06, .1 + foot * .72), (.04, .09, .04), rot=(90, 0, 0),
                      col=claw)
        b.add('sphere', (s * arm_x, arm_y, .14), (arm, arm * 2.4, arm), rot=(35, 0, s * 20), col=col)
        b.add('sphere', (s * (arm_x + .04), arm_y - .16, .28), hand, col=col)


# ==================================================================== Héricendre, Feurisson, Typhlosion
def build_hericendre(g, st):
    DARK, CREAM = rgb(.2, .32, .42), rgb(1, .9, .56)
    b, h, f = g['body'], g['head'], g['glow']
    if st < 2:                                            # quadrupède au dos sombre
        k = 1 + .25 * st
        b.add('sphere', (0, .42 * k, 0), (.62 * k, .52 * k, 1.05 * k), col=CREAM)
        b.add('sphere', (0, .52 * k, -.06), (.6 * k, .38 * k, .98 * k), col=DARK)
        for sx in (-1, 1):
            for sz in (-1, 1):
                b.add('sphere', (sx * .2 * k, .1, sz * .3 * k), (.18 * k, .2 * k, .22 * k), col=CREAM)
        h.add('sphere', (0, .18, .12), (.5, .44, .6), col=CREAM)
        h.add('sphere', (0, .3, .02), (.52, .28, .56), col=DARK)
        h.add('sphere', (0, .1, .42), (.26, .18, .26), col=CREAM)
        for s in (-1, 1):
            h.add('box', (s * .13, .24, .36), (.13, .025, .02), rot=(0, 0, s * 12), col=BLACK)   # yeux plissés
        for i in range(3 + st):                           # flammes du dos
            z = -.2 * k - i * .16
            f.add('cone', (0, .72 * k + .06 * i, z), (.22, .45 + .1 * st, .22), rot=(-35, 0, 0),
                  col=rgb(1, .45 + .1 * (i % 2), .08))
        if st:                                           # Feurisson : flammes sur la tête
            f.add('cone', (0, .5 * k + .52, .5 * k + .02), (.22, .36, .22), rot=(-30, 0, 0), col=rgb(1, .5, .08))
        return {'head_pivot': (0, .5 * k, .5 * k), 'no_tail': True}
    # Typhlosion : bipède, collerette de flammes autour du cou
    b.add('sphere', (0, .95, .02), (.82, 1.25, .72), col=CREAM)
    b.add('sphere', (0, 1.0, -.1), (.86, 1.25, .62), col=DARK)
    _limbs(b, CREAM, .3, .26, .28, 1.08, .14, .12, claw=WHITE, spread=.24, arm_x=.42)
    h.add('sphere', (0, .22, .12), (.58, .5, .68), col=CREAM)
    h.add('sphere', (0, .32, .0), (.6, .3, .6), col=DARK)
    h.add('sphere', (0, .12, .44), (.3, .2, .3), col=CREAM)
    for s in (-1, 1):
        h.add('box', (s * .14, .26, .38), (.14, .03, .02), rot=(0, 0, s * 12), col=rgb(.8, .2, .15))
    for i in range(11):
        if 4 <= i <= 6:                                   # pas de flamme devant le visage
            continue
        a = math.radians(-150 + i * 30)
        f.add('cone', (math.sin(a) * .42, 1.62, math.cos(a) * .36 - .05), (.26, .7, .26),
              rot=(-math.cos(a) * 35, 0, -math.sin(a) * 35), col=rgb(1, .4 + .15 * (i % 2), .06))
    return {'head_pivot': (0, 1.56, .1), 'no_tail': True}


# ==================================================================== Kaiminus, Crocrodil, Aligatueur
def build_kaiminus(g, st):
    BLUE, YEL, RED = rgb(.3, .58, .92), rgb(1, .88, .45), rgb(.85, .2, .2)
    k = (1.0, 1.2, 1.45)[st]
    b, h, t = g['body'], g['head'], g['tail']
    b.add('sphere', (0, .55 * k, 0), (.64 * k, .82 * k, .6 * k), col=BLUE)
    b.add('sphere', (0, .55 * k, .16 * k), (.4 * k, .56 * k, .3 * k), col=YEL)
    _limbs(b, BLUE, .2 * k, .2 * k, .22 * k, .72 * k, .12 * k, .1 * k, claw=WHITE, spread=.2 * k, arm_x=.34 * k)
    jaw = .45 + .12 * st
    h.add('sphere', (0, .28, .05), (.66, .56, .66), col=BLUE)
    h.add('sphere', (0, .2, .4), (jaw, .26, .55), col=BLUE)                      # mâchoire du haut
    h.add('sphere', (0, .02, .36), (jaw * .92, .15, .5), col=BLUE)                # mâchoire du bas
    h.add('sphere', (0, .1, .5), (jaw * .85, .06, .34), col=rgb(.6, .15, .15))
    for i in range(-2, 3):                                                        # crocs
        h.add('cone', (i * .08, .06, .64 - abs(i) * .04), (.05, .09, .04), rot=(180, 0, 0), col=WHITE)
    _eyes(h, .18, .42, .22, .11, .14, iris=rgb(.7, .1, .12))
    for i in range(1 + st):                                                       # crête rouge
        h.add('cone', (0, .6 - i * .06, -.05 - i * .16), (.1, .28, .14), rot=(-30, 0, 0), col=RED)
    t.add('cone', (0, .05, -.4), (.26 * k, .95 * k, .26 * k), rot=(-78, 0, 0), col=BLUE)
    for i in range(2 + st * 2):                                                   # piquants du dos et de la queue
        z = -.1 - i * .22 * k
        t.add('cone', (0, .2 + .45 * k - i * .08, z + .25), (.12, .3 + .05 * st, .1), rot=(-20, 0, 0), col=RED)
    return {'head_pivot': (0, .86 * k, .04), 'tail_pivot': (0, .35 * k, -.32 * k)}


# ==================================================================== Arcko, Massko, Jungko
def build_arcko(g, st):
    GREEN, DARK = rgb(.4, .74, .32), rgb(.18, .42, .2)
    BELLY = (rgb(.92, .35, .3), rgb(.95, .85, .4), rgb(.9, .3, .25))[st]
    k = (1.0, 1.2, 1.4)[st]
    b, h, t = g['body'], g['head'], g['tail']
    b.add('sphere', (0, .6 * k, 0), (.52 * k, .85 * k, .5 * k), col=GREEN)
    b.add('sphere', (0, .56 * k, .12 * k), (.34 * k, .6 * k, .3 * k), col=BELLY)
    _limbs(b, GREEN, .22 * k, .16 * k, .2 * k, .78 * k, .1 * k, .09 * k, spread=.16 * k, arm_x=.3 * k)
    if st:                                                # feuilles des bras (lames chez Jungko)
        for s in (-1, 1):
            b.add('sphere', (s * .42 * k, .72 * k, -.05), (.06, .12 + .1 * st, .42 + .18 * st), rot=(20, 0, s * 20),
                  col=DARK)
    if st == 2:                                           # graines sur le dos
        for i in range(3):
            for s in (-1, 1):
                b.add('sphere', (s * .12, (.9 - i * .2) * k, -.24 * k), .1, col=rgb(.85, .85, .3))
    h.add('sphere', (0, .2, .1), (.7, .46, .6), col=GREEN)
    _eyes(h, .2, .28, .28, .12, .15, iris=rgb(.95, .75, .1))
    h.add('box', (0, .08, .38), (.3, .02, .02), col=rgb(.5, .12, .12))
    if st:                                                # crête de feuille
        h.add('sphere', (0, .38, -.2), (.12, .3, .5), rot=(-30, 0, 0), col=DARK)
    if st == 0:                                           # grosse queue en éventail
        t.add('sphere', (0, .35, -.3), (.2, .75, .6), rot=(-20, 0, 0), col=DARK)
    else:
        for i in range(3 + st):
            t.add('sphere', (0, .1 + i * .08, -.25 - i * .22), (.16, .1, .5 - i * .05), rot=(-10, 0, 0),
                  col=DARK if i % 2 else rgb(.25, .52, .24))
    return {'head_pivot': (0, .96 * k, .02), 'tail_pivot': (0, .45 * k, -.22 * k)}


# ==================================================================== Abra, Kadabra, Alakazam
def build_abra(g, st):
    Y, BROWN = rgb(.95, .78, .3), rgb(.52, .34, .2)
    k = (1.0, 1.2, 1.35)[st]
    b, h, t = g['body'], g['head'], g['tail']
    b.add('sphere', (0, .6 * k, 0), (.6 * k, .85 * k, .5 * k), col=Y)
    b.add('sphere', (0, .72 * k, .02), (.66 * k, .5 * k, .56 * k), col=BROWN)     # plastron / épaules
    _limbs(b, Y, .22 * k, .16 * k, .2 * k, .8 * k, .1 * k, .09 * k, spread=.18 * k, arm_x=.36 * k)
    spoons = (0, 1, 2)[st]
    for s in (1, -1)[:spoons]:                                                    # cuillères
        b.add('cyl', (s * .44 * k, .72 * k, .42), (.035, .5, .035), rot=(60, 0, 0), col=rgb(.75, .75, .8))
        b.add('sphere', (s * .44 * k, .88 * k, .66), (.14, .05, .2), rot=(60, 0, 0), col=rgb(.8, .8, .85))
    h.add('sphere', (0, .25, .05), (.62, .56, .58), col=Y)
    h.add('sphere', (0, .16, .3), (.3, .2, .24), col=Y)
    for s in (-1, 1):
        h.add('box', (s * .14, .28, .31), (.14, .03, .02), rot=(0, 0, s * 10), col=BLACK)
        _polar_ear(h, s, (s * .2, .45, -.02), 25, .45 + .15 * st, .2, Y, inner=BROWN)
        if st:                                                                    # moustaches
            h.add('cyl', (s * .28, .05, .3), (.03, .5 + .3 * st, .03), rot=(0, 0, s * 70), col=BROWN)
    if st:                                                                        # étoile rouge du front
        for a in range(0, 360, 72):
            h.add('cone', (math.sin(math.radians(a)) * .04, .4 + math.cos(math.radians(a)) * .04, .32),
                  (.05, .08, .02), rot=(0, 0, -a), col=rgb(.9, .15, .15))
    if st < 2:
        t.add('sphere', (0, .1, -.3), (.18, .2, .6), rot=(-30, 0, 0), col=Y)
        t.add('sphere', (0, .28, -.6), (.2, .2, .2), col=BROWN)
    return {'head_pivot': (0, .96 * k, .02), 'tail_pivot': (0, .3 * k, -.2 * k),
            **({'no_tail': True} if st == 2 else {})}


# ==================================================================== Machoc, Machopeur, Mackogneur
def build_machoc(g, st):
    SKIN = (rgb(.6, .66, .78), rgb(.56, .62, .76), rgb(.52, .6, .74))[st]
    CREST = rgb(.55, .4, .3)
    k = (1.0, 1.25, 1.45)[st]
    b, h = g['body'], g['head']
    b.add('sphere', (0, .65 * k, 0), (.66 * k, .9 * k, .52 * k), col=SKIN)
    for s in (-1, 1):                                                             # pectoraux
        b.add('sphere', (s * .15 * k, .82 * k, .16 * k), (.3 * k, .26 * k, .2 * k), col=SKIN)
    _limbs(b, SKIN, .22 * k, .2 * k, .24 * k, .9 * k, .15 * k, .14 * k, spread=.2 * k, arm_x=.38 * k)
    if st == 2:                                                                   # deux bras de plus
        for s in (-1, 1):
            b.add('sphere', (s * .5 * k, .7 * k, .1), (.14 * k, .32 * k, .14 * k), rot=(20, 0, s * 45), col=SKIN)
            b.add('sphere', (s * .66 * k, .52 * k, .2), .15 * k, col=SKIN)
    if st >= 1:                                                                   # slip noir, ceinture dorée
        b.add('sphere', (0, .36 * k, 0), (.6 * k, .24 * k, .5 * k), col=BLACK)
    if st == 2:
        b.add('cyl', (0, .46 * k, 0), (.64 * k, .08, .54 * k), col=rgb(1, .8, .2))
    h.add('sphere', (0, .2, .04), (.46, .46, .44), col=SKIN)
    _eyes(h, .1, .24, .2, .08, .08, iris=rgb(.8, .1, .1), shine=False)
    for s in (-1, 1):
        h.add('box', (s * .1, .33, .22), (.14, .03, .03), rot=(0, 0, s * 20), col=rgb(.3, .3, .35))
    h.add('box', (0, .08, .22), (.14, .02, .02), col=rgb(.3, .2, .2))
    for i in (-1, 0, 1) if st != 1 else (0,):                                     # crêtes
        h.add('cone', (i * .1, .5, 0), (.08, .25 + .1 * (st == 1), .12), rot=(-10, 0, -i * 15), col=CREST)
    return {'head_pivot': (0, 1.06 * k, .04), 'no_tail': True}


# ==================================================================== Fantominus, Spectrum, Ectoplasma
def build_fantominus(g, st):
    b, f = g['body'], g['glow']
    if st == 0:                                           # boule noire dans un halo de gaz
        b.add('sphere', (0, .9, 0), .78, col=rgb(.12, .1, .14))
        for s in (-1, 1):
            b.add('sphere', (s * .15, 1.0, .3), (.2, .22, .1), col=WHITE)
            b.add('sphere', (s * .13, 1.0, .35), (.08, .1, .04), col=BLACK)
        b.add('sphere', (0, .8, .34), (.36, .14, .08), col=rgb(.85, .3, .45))
        for i in range(10):
            a = math.tau * i / 10
            f.add('sphere', (math.sin(a) * .62, .9 + math.cos(a * 3) * .1, math.cos(a) * .4 - .28),
                  (.26, .24, .24), col=rgb(.5, .3, .7))
        return {'float': True, 'no_head': True, 'no_tail': True}
    if st == 1:                                           # Spectrum : mains flottantes, traîne de gaz
        P = rgb(.52, .36, .68)
        b.add('sphere', (0, 1.0, 0), (.8, .72, .7), col=P)
        for i in range(-2, 3):
            b.add('cone', (i * .16, 1.35 - abs(i) * .05, -.05), (.14, .32, .14), rot=(-10, 0, -i * 18), col=P)
        b.add('cone', (0, .5, -.12), (.45, .6, .45), rot=(160, 0, 0), col=P)
        for s in (-1, 1):
            b.add('sphere', (s * .72, .95, .25), (.2, .22, .16), col=P)
            for fgr in (-1, 0, 1):
                b.add('cone', (s * .78 + fgr * .07, 1.12, .3), (.05, .16, .05), col=P)
            b.add('sphere', (s * .18, 1.1, .33), (.18, .12, .06), rot=(0, 0, -s * 15), col=WHITE)
            b.add('sphere', (s * .16, 1.1, .36), (.06, .06, .03), col=BLACK)
        b.add('sphere', (0, .9, .33), (.4, .1, .06), col=rgb(.8, .25, .4))
        return {'float': True, 'no_head': True, 'no_tail': True}
    P = rgb(.45, .3, .62)                                  # Ectoplasma : trapu, épines, grand sourire
    b.add('sphere', (0, .78, 0), (1.15, 1.05, .95), col=P)
    for i in range(7):
        a = math.radians(-60 + i * 20)
        b.add('cone', (math.sin(a) * .4, 1.15 + math.cos(a) * .1, -.35), (.16, .38, .16),
              rot=(-40, 0, -math.degrees(a)), col=P)
    for s in (-1, 1):
        b.add('sphere', (s * .24, .1, .1), (.26, .16, .36), col=P)
        b.add('sphere', (s * .6, .7, .2), (.16, .34, .16), rot=(30, 0, s * 30), col=P)
        b.add('cone', (s * .2, 1.05, .43), (.2, .14, .05), rot=(0, 0, s * 105), col=rgb(.9, .1, .12))   # yeux
    b.add('sphere', (0, .72, .44), (.66, .24, .1), col=rgb(.95, .92, .95))                  # sourire
    b.add('box', (0, .72, .5), (.6, .015, .02), col=rgb(.3, .15, .3))
    return {'no_head': True, 'no_tail': True}


# ==================================================================== Minidraco, Draco, Dracolosse
def build_minidraco(g, st):
    b, h, t, f = g['body'], g['head'], g['tail'], g['glow']
    if st < 2:                                            # serpent bleu au ventre blanc
        BLUE, BELLY = rgb(.42, .58, .95), rgb(.96, .94, .92)
        n = 5 + 2 * st
        for i in range(n):                                # corps en S, du cou vers la queue
            z = .3 - i * .28
            x = math.sin(i * .9) * .18
            r = .34 - i * .02
            (b if i < 3 else t).add('sphere', (x, .28 + max(0, 2 - i) * .18, z + (0 if i < 3 else .6)),
                                    (r * 1.1, r, r * 1.2), col=BLUE)
            if i < 3:
                b.add('sphere', (x, .2 + max(0, 2 - i) * .18, z + .12), (r * .8, r * .7, r * .6), col=BELLY)
        h.add('sphere', (0, .15, .08), (.48, .44, .5), col=BLUE)
        h.add('sphere', (0, .06, .28), (.28, .2, .26), col=BLUE)
        _eyes(h, .13, .2, .26, .09, .12, iris=rgb(.35, .15, .5))
        for s in (-1, 1):                                  # ailerons blancs
            h.add('sphere', (s * .28, .22, -.05), (.05, .22, .18), rot=(0, 0, -s * 30), col=WHITE)
        if st:
            h.add('cone', (0, .42, .12), (.08, .22, .08), rot=(10, 0, 0), col=WHITE)             # corne
            f.add('sphere', (0, .72, .12), .1, col=rgb(.4, .6, 1))                                   # cristaux
            for i in range(2):
                f.add('sphere', (0, .28, -1.3 - i * .35 + .6), .09, col=rgb(.4, .6, 1))
        return {'head_pivot': (0, .72, .5), 'tail_pivot': (0, .0, -.6)}
    # Dracolosse : grand dragon orange, petites ailes, antennes
    O, CREAM, WING = rgb(1, .7, .3), rgb(1, .9, .65), rgb(.3, .58, .48)
    b.add('sphere', (0, .95, 0), (.95, 1.3, .8), col=O)
    b.add('sphere', (0, .9, .18), (.66, 1.0, .5), col=CREAM)
    for y in (.6, .8, 1.0, 1.2):
        b.add('box', (0, y, .43), (.46, .02, .03), col=rgb(.85, .7, .45))
    _limbs(b, O, .3, .3, .3, 1.1, .14, .13, claw=WHITE, spread=.26, arm_x=.46)
    for s in (-1, 1):
        b.add('sphere', (s * .55, 1.45, -.4), (.5, .36, .05), rot=(0, s * -20, -s * 25), col=WING)
    h.add('sphere', (0, .2, .1), (.52, .46, .58), col=O)
    h.add('sphere', (0, .1, .34), (.34, .24, .3), col=O)
    _eyes(h, .14, .27, .3, .1, .12, iris=rgb(.2, .1, .1))
    for s in (-1, 1):
        h.add('cyl', (s * .12, .6, 0), (.03, .45, .03), rot=(-10, 0, -s * 15), col=O)       # antennes
        h.add('sphere', (s * .18, .82, -.04), .06, col=O)
    t.add('cone', (0, .1, -.45), (.4, 1.0, .4), rot=(-75, 0, 0), col=O)
    return {'head_pivot': (0, 1.55, .12), 'tail_pivot': (0, .4, -.3)}


# ==================================================================== Wattouat, Lainergie, Pharamp
def build_wattouat(g, st):
    b, h, t, f = g['body'], g['head'], g['tail'], g['glow']
    WOOL = rgb(.98, .97, .9)
    if st == 0:                                           # mouton de laine au visage bleu
        FACE = rgb(.4, .62, .95)
        b.add('sphere', (0, .5, 0), (.75, .6, .85), col=WOOL)
        rng = random.Random(4)
        for _ in range(14):
            a, y = rng.uniform(0, math.tau), rng.uniform(.3, .75)
            b.add('sphere', (math.sin(a) * .34, y, math.cos(a) * .38), .22, col=WOOL)
        for sx in (-1, 1):
            for sz in (-1, 1):
                b.add('cyl', (sx * .2, .12, sz * .22), (.12, .24, .12), col=FACE)
        h.add('sphere', (0, .1, .12), (.44, .4, .44), col=FACE)
        _eyes(h, .1, .14, .3, .08, .1)
        for s in (-1, 1):                                  # cornes enroulées
            h.add('sphere', (s * .24, .22, -.02), (.12, .14, .12), col=rgb(1, .85, .3))
            h.add('sphere', (s * .3, .08, .1), (.14, .06, .1), col=FACE)
        h.add('sphere', (0, .32, .02), .16, col=WOOL)
        t.add('cyl', (0, .05, -.15), (.06, .3, .06), rot=(-60, 0, 0), col=rgb(1, .85, .3))
        t.add('sphere', (0, .15, -.3), .1, col=rgb(1, .85, .3))
        return {'head_pivot': (0, .72, .45), 'tail_pivot': (0, .5, -.42)}
    COL = rgb(1, .72, .82) if st == 1 else rgb(1, .85, .3)
    k = 1.2 if st == 1 else 1.4
    b.add('sphere', (0, .6 * k, 0), (.56 * k, .85 * k, .5 * k), col=COL)
    if st == 1:                                           # collerette de laine
        b.add('sphere', (0, .95 * k, 0), (.66 * k, .3 * k, .6 * k), col=WOOL)
    else:
        b.add('sphere', (0, .56 * k, .14), (.38 * k, .6 * k, .3 * k), col=WOOL)
    _limbs(b, COL, .2 * k, .16 * k, .2 * k, .78 * k, .1 * k, .09 * k, spread=.16 * k, arm_x=.32 * k)
    h.add('sphere', (0, .2, .06), (.44, .42, .44), col=COL)
    _eyes(h, .1, .22, .22, .08, .1)
    for s in (-1, 1):
        _polar_ear(h, s, (s * .16, .36, -.02), 40, .34, .12, COL, tip=BLACK)
    if st == 2:
        f.add('sphere', (0, .98 * k + .42, .12), .09, col=rgb(1, .25, .15))            # orbe du front
    for i in range(2 + st):                                # queue rayée noir et couleur
        t.add('sphere', (0, .05 + i * .1, -.15 - i * .14), .09, col=BLACK if i % 2 else COL)
    f.add('sphere', tuple(Vec3(0, .05 + (2 + st) * .1, -.15 - (2 + st) * .14) + Vec3(0, .4 * k, -.25 * k)),
          .14, col=rgb(1, .3, .15))                        # orbe au bout de la queue (coordonnées du corps)
    return {'head_pivot': (0, .98 * k, .02), 'tail_pivot': (0, .4 * k, -.25 * k), 'glow_parent': 'tail'}


# ==================================================================== Embrylex, Ymphect, Tyranocif
def build_embrylex(g, st):
    b, h, t = g['body'], g['head'], g['tail']
    if st == 1:                                           # Ymphect : cocon gris percé
        C_ = rgb(.55, .62, .78)
        b.add('sphere', (0, .75, 0), (1.0, 1.4, .9), col=C_)
        for p in ((0, .9, .44), (-.24, .55, .38), (.24, .55, .38), (0, .35, .42)):
            b.add('sphere', p, (.14, .12, .05), col=rgb(.2, .22, .3))
        for s in (-1, 1):
            b.add('sphere', (s * .42, .7, .2), (.12, .2, .12), col=C_)
            b.add('box', (s * .18, 1.1, .42), (.18, .04, .03), rot=(0, 0, s * 15), col=rgb(.2, .2, .25))
            b.add('sphere', (s * .18, 1.02, .44), (.07, .05, .03), col=rgb(.85, .15, .15))
        b.add('cone', (0, 1.55, 0), (.2, .35, .2), col=C_)
        return {'no_head': True, 'no_tail': True}
    G = rgb(.55, .74, .4) if st == 0 else rgb(.46, .66, .42)
    k = 1.0 if st == 0 else 1.5
    b.add('sphere', (0, .55 * k, 0), (.62 * k, .8 * k, .56 * k), col=G)
    b.add('cone4', (0, .55 * k, .28 * k), (.26 * k, .3 * k, .08), rot=(0, 45, 0) if st == 0 else (0, 0, 180),
          col=rgb(.25, .35, .7) if st == 0 else rgb(.45, .55, .82))                  # losange du ventre
    _limbs(b, G, .2 * k, .2 * k, .24 * k, .74 * k, .12 * k, .11 * k, claw=WHITE if st else None,
           spread=.2 * k, arm_x=.36 * k)
    if st == 2:                                           # épines du dos
        for i in range(4):
            for s in (-1, 1):
                b.add('cone', (s * .2, (1.35 - i * .25) * 1, -.35 - i * .02), (.14, .4, .14), rot=(-45, 0, -s * 20),
                      col=G)
    h.add('sphere', (0, .2, .06), (.5, .46, .52), col=G)
    h.add('sphere', (0, .1, .3), (.34, .24, .3), col=G)
    _eyes(h, .13, .26, .3, .08, .09, iris=rgb(.75, .12, .12))
    h.add('cone', (0, .5, 0), (.12, .32, .14), rot=(-15, 0, 0), col=G)                # corne
    if st == 2:
        for s in (-1, 1):
            h.add('cone', (s * .2, .42, -.12), (.08, .24, .08), rot=(-40, 0, -s * 30), col=G)
    t.add('cone', (0, .05, -.35), (.26 * k, .7 * k, .26 * k), rot=(-78, 0, 0), col=G)
    return {'head_pivot': (0, .9 * k, .05), 'tail_pivot': (0, .35 * k, -.3 * k)}


# ==================================================================== Sorbébé, Sorboul, Sorbouboul
def _ice_cream(b, x, y, s, eyes=True):
    """Boule de glace en spirale avec un visage."""
    WHITE_ICE, BLUE_ICE = rgb(.97, .98, 1), rgb(.72, .88, 1)
    for i in range(4):
        r = (.52 - i * .1) * s
        b.add('sphere', (x, y + i * .18 * s, 0), (r * 1.1, .22 * s, r), col=WHITE_ICE if i % 2 == 0 else BLUE_ICE)
    b.add('cone', (x + .05 * s, y + .78 * s, 0), (.12 * s, .3 * s, .12 * s), rot=(0, 0, -40), col=WHITE_ICE)
    if eyes:
        for sd in (-1, 1):
            b.add('sphere', (x + sd * .14 * s, y + .1 * s, .44 * s), (.07 * s, .1 * s, .05), col=BLACK)
        b.add('sphere', (x, y - .02 * s, .5 * s), (.1 * s, .05 * s, .04), col=rgb(.5, .2, .35))


def build_sorbebe(g, st):
    CONE, ICE = rgb(.86, .68, .42), rgb(.8, .93, 1)
    b = g['body']
    k = (1.0, 1.2, 1.3)[st]
    b.add('cone', (0, .38 * k, 0), (.62 * k, .8 * k, .62 * k), rot=(180, 0, 0), col=CONE)   # cornet
    for i in range(3):
        b.add('cyl', (0, (.2 + i * .18) * k, 0), (.6 * k * (1 - (2 - i) * .25), .02, .6 * k * (1 - (2 - i) * .25)),
              col=rgb(.7, .52, .3))
    for i in range(6):                                                           # glaçons
        a = math.tau * i / 6
        b.add('cone', (math.sin(a) * .3 * k, .7 * k, math.cos(a) * .3 * k), (.1, .3, .1), rot=(180, 0, 0), col=ICE)
    if st < 2:
        _ice_cream(b, 0, .95 * k, (1.0, 1.25)[st])
        if st:
            for s in (-1, 1):
                b.add('sphere', (s * .55, .75 * k, .1), (.12, .22, .12), rot=(0, 0, s * 40), col=ICE)   # mains
    else:                                                # Sorbouboul : deux têtes
        for s in (-1, 1):
            _ice_cream(b, s * .34, 1.2, .95)
        for s in (-1, 1):
            b.add('sphere', (s * .7, .9, .1), (.14, .26, .14), rot=(0, 0, s * 40), col=ICE)
    return {'no_head': True, 'no_tail': True, 'float': st == 0}


LINES = {
    'hericendre': (build_hericendre, ('hericendre', 'feurisson', 'typhlosion')),
    'kaiminus': (build_kaiminus, ('kaiminus', 'crocrodil', 'aligatueur')),
    'arcko': (build_arcko, ('arcko', 'massko', 'jungko')),
    'abra': (build_abra, ('abra', 'kadabra', 'alakazam')),
    'machoc': (build_machoc, ('machoc', 'machopeur', 'mackogneur')),
    'fantominus': (build_fantominus, ('fantominus', 'spectrum', 'ectoplasma')),
    'minidraco': (build_minidraco, ('minidraco', 'draco', 'dracolosse')),
    'wattouat': (build_wattouat, ('wattouat', 'lainergie', 'pharamp')),
    'embrylex': (build_embrylex, ('embrylex', 'ymphect', 'tyranocif')),
    'sorbebe': (build_sorbebe, ('sorbebe', 'sorboul', 'sorbouboul')),
}
BUILDERS_MORE = {form: (lambda g, fn=fn, st=st: fn(g, st)) for fn, forms in LINES.values()
                 for st, form in enumerate(forms)}
BIG = ('typhlosion', 'aligatueur', 'mackogneur', 'ectoplasma', 'dracolosse', 'tyranocif', 'ymphect', 'sorbouboul')
