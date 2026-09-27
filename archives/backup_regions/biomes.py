"""Décor des 5 régions de l'île.

Chaque région (une part de 72° de l'île) a son paysage typique, un monument
visible de loin derrière le repaire du boss, et des éléments animés :
    feu    : volcans, coulées de lave qui s'écoulent, fumerolles, arbres morts
    eau    : lacs, palmiers, falaise avec cascade, coquillages
    plante : forêt dense, arbre géant, fleurs géantes, champignons
    roche  : mesas, arche rocheuse, cheminées de fée, cactus, rochers
    glace  : pic enneigé, sapins enneigés, cristaux de glace, lacs gelés, igloos

Les fonctions reçoivent `w` (le monde, voir world.Overworld) qui fournit :
    w.rng                 générateur aléatoire (déterministe)
    w.spot(h, rad, ...)   emplacement libre au hasard dans la région de cap h
    w.block(x, z, r)      déclare un obstacle (collision + plus de décor ici)
    w.flow(...)           éléments animés le long d'un trajet (lave, eau, fumée)
et trois MeshBuilder : `b` (décor éclairé), `glow` (lumineux : lave, cristaux)
et `water` (eau, légèrement lumineuse).
"""
import math

from ursina import color, lerp

import config as C
from emblems import add_emblem

R_LAIR = C.BATTLE_ARENA_RADIUS

PATH_COLORS = {
    'feu': color.rgb(.2, .17, .17),
    'eau': color.rgb(.93, .86, .64),
    'plante': color.rgb(.52, .38, .24),
    'roche': color.rgb(.86, .72, .52),
    'glace': color.rgb(.72, .82, .92),
}


def polar(h, r):
    """Point à la distance r du centre, au cap h (degrés, 0 = nord/+z, sens horaire)."""
    a = math.radians(h)
    return math.sin(a) * r, math.cos(a) * r


def shade(c, f):
    return color.rgb(min(1, c[0] * f), min(1, c[1] * f), min(1, c[2] * f))


def n(count):
    return max(0, int(count * C.DECOR_DENSITY))


def scatter(w, h, count, rad, fn, scale=(.8, 1.3), gap=1.0, solid=True, r_min=None, r_max=None):
    """Place `count` éléments : fn(x, z, s) dessine, rad * s = rayon d'encombrement."""
    for _ in range(n(count)):
        s = w.rng.uniform(*scale)
        p = w.spot(h, rad * s, r_min, r_max, gap=gap, path_clear=5.5 if solid else 2.4)
        if p is None:
            continue
        fn(p[0], p[1], s)
        if solid:
            w.block(p[0], p[1], rad * s)


def decorate(w, type_key, h, b, glow, water):
    {'feu': _feu, 'eau': _eau, 'plante': _plante, 'roche': _roche, 'glace': _glace}[type_key](w, h, b, glow, water)


def landmark_pos(h):
    return polar(h, C.LAIR_DISTANCE + R_LAIR + 22)


# =================================================================== FEU
LAVA = color.rgb(1, .42, .05)
LAVA_HOT = color.rgb(1, .78, .2)
BASALT = color.rgb(.2, .17, .17)
ASH = color.rgb(.3, .26, .25)


def volcano(w, b, glow, x, z, rb, hgt, streaks=6, smoke=10):
    """Volcan : tronc de cône, cratère de lave, coulées sur les flancs, fumée."""
    rng = w.rng
    b.add('frustum', (x, hgt / 2, z), (rb * 2, hgt, rb * 2), col=color.rgb(.27, .2, .19))
    b.add('frustum', (x, hgt * .18, z), (rb * 2.12, hgt * .36, rb * 2.12), col=color.rgb(.22, .17, .16))
    rt = rb * .28   # rayon du sommet ('frustum' : rayon haut = .14 pour un rayon bas de .5)
    b.add('ring_thin', (x, hgt + .25, z), (rt * 2, .5, rt * 2), col=color.rgb(.15, .12, .12))
    glow.add('disc', (x, hgt - .15, z), (rt * 1.9, .3, rt * 1.9), col=LAVA)
    glow.add('sphere', (x, hgt - .1, z), (rt * 1.1, .6, rt * 1.1), col=LAVA_HOT)
    # coulées de lave sur les flancs
    pitch = math.degrees(math.atan2(hgt, rb - rt))
    slant = math.hypot(rb - rt, hgt)
    for i in range(streaks):
        phi = i * 360 / streaks + rng.uniform(-20, 20)
        f = rng.uniform(.55, 1.0)
        L = slant * f
        ph = math.radians(phi)
        out = (math.sin(ph), math.cos(ph))
        # point de départ sur la lèvre du cratère, descente le long de la pente
        sx, sz = x + out[0] * rt, z + out[1] * rt
        dh = (rb - rt) / slant
        dv = hgt / slant
        mx, mz = sx + out[0] * dh * L / 2, sz + out[1] * dh * L / 2
        my = hgt - dv * L / 2
        # léger décalage vers l'extérieur (normale de la pente) pour ne pas se fondre
        nx, ny = dv * .25, dh * .25
        glow.add('box', (mx + out[0] * nx, my + ny, mz + out[1] * nx), (rng.uniform(.7, 1.3), .15, L),
                 rot=(pitch, phi, 0), col=LAVA if i % 2 else color.rgb(1, .55, .1))
        if f > .9:   # la coulée atteint le pied du volcan : petite mare
            px, pz = x + out[0] * (rb + 1.2), z + out[1] * (rb + 1.2)
            glow.add('disc', (px, .05, pz), (3.2, .06, 2.4), rot=(0, phi, 0), col=LAVA)
            w.block(px, pz, 1.4)
    w.block(x, z, rb * .95)
    if smoke:
        w.smoke((x, hgt + .5, z), rt * .8, hgt * .7 + 6, smoke, color.rgb(.32, .3, .3), size=rt * .9)


def lava_river(w, b, glow, x, z, heading, h, width=2.4, steps=26):
    """Rivière de lave qui serpente vers la mer ; des plaques incandescentes y dérivent."""
    rng = w.rng
    pts = [(x, z)]
    ang = heading
    for _ in range(steps):
        r = math.hypot(x, z)
        if r > C.WORLD_RADIUS + 3:
            break
        radial = math.degrees(math.atan2(x, z))
        # attirée vers l'extérieur de l'île, avec des méandres
        diff = (radial - ang + 180) % 360 - 180
        ang += diff * .25 + rng.uniform(-18, 18)
        # reste dans la région (ne coupe pas le chemin ni les régions voisines)
        off = (radial - h + 180) % 360 - 180
        if abs(off) > 31:
            ang -= math.copysign(12, off)
        x += math.sin(math.radians(ang)) * 3
        z += math.cos(math.radians(ang)) * 3
        pts.append((x, z))
    for (ax, az), (bx, bz) in zip(pts, pts[1:]):
        dx, dz = bx - ax, bz - az
        L = math.hypot(dx, dz)
        yaw = math.degrees(math.atan2(dx, dz))
        mx, mz = (ax + bx) / 2, (az + bz) / 2
        b.add('box', (mx, .03, mz), (width + 1.6, .06, L), rot=(0, yaw, 0), col=BASALT)
        b.add('disc', (ax, .031, az), (width + 1.6, .06, width + 1.6), col=BASALT)
        glow.add('box', (mx, .06, mz), (width, .06, L), rot=(0, yaw, 0), col=LAVA)
        glow.add('disc', (ax, .061, az), (width, .06, width), col=LAVA)
        for k in range(3):
            t = k / 3
            w.block(ax + dx * t, az + dz * t, width / 2 + .5)
    w.flow([(px, .1, pz) for px, pz in pts], count=len(pts) * 2, col=LAVA_HOT, size=(.9, .1, .9),
           speed=2.2, jitter=width * .3, glow=1.0)
    w.flow([(px, .09, pz) for px, pz in pts], count=len(pts), col=color.rgb(.35, .1, .05), size=(1.1, .1, .8),
           speed=1.6, jitter=width * .25, glow=.2)


def dead_tree(b, x, z, s, rng):
    wood = color.rgb(.16, .12, .1)
    b.add('cyl6', (x, 1.6 * s, z), (.35 * s, 3.2 * s, .35 * s), rot=(rng.uniform(-6, 6), 0, rng.uniform(-6, 6)), col=wood)
    for _ in range(rng.randint(2, 4)):
        yaw = rng.uniform(0, 360)
        y = rng.uniform(1.6, 3.0) * s
        L = rng.uniform(.9, 1.6) * s
        ox, oz = polar(yaw, L * .45)
        b.add('cyl6', (x + ox, y + L * .3, z + oz), (.14 * s, L, .14 * s), rot=(55, yaw, 0), col=wood)


def _feu(w, h, b, glow, water):
    rng = w.rng
    lx, lz = landmark_pos(h)
    volcano(w, b, glow, lx, lz, 17, 32, streaks=9, smoke=16)
    for side in (-1, 1):
        vx, vz = polar(h + 24 * side, 44)
        volcano(w, b, glow, vx, vz, 7, 11, streaks=5, smoke=7)
        sx, sz = polar(h + 24 * side + 7 * side, 51)
        lava_river(w, b, glow, sx, sz, h + 24 * side + 25 * side, h)

    def lava_pool(x, z, s):
        glow.add('disc', (x, .05, z), (3.2 * s, .06, 2.6 * s), col=LAVA)
        glow.add('sphere', (x, .06, z), (1.2 * s, .2, 1 * s), col=LAVA_HOT)
        b.add('disc', (x, .03, z), (4.2 * s, .06, 3.6 * s), col=BASALT)
    scatter(w, h, 14, 1.9, lava_pool, gap=1.5)

    def basalt(x, z, s):
        for _ in range(rng.randint(3, 6)):
            ox, oz = rng.uniform(-.9, .9) * s, rng.uniform(-.9, .9) * s
            hh = rng.uniform(1, 3.2) * s
            b.add('cyl6', (x + ox, hh / 2, z + oz), (.8 * s, hh, .8 * s), col=shade(BASALT, rng.uniform(.9, 1.3)))
    scatter(w, h, 26, 1.4, basalt)

    scatter(w, h, 22, .5, lambda x, z, s: dead_tree(b, x, z, s, rng), scale=(.9, 1.4))

    def rock(x, z, s):
        prim = rng.choice(('cone4', 'sphere_lo', 'cone6'))
        hh = rng.uniform(.8, 1.8) * s
        b.add(prim, (x, hh / 2 if prim != 'sphere_lo' else hh * .3, z), (1.6 * s, hh, 1.4 * s),
              rot=(0, rng.uniform(0, 180), 0), col=shade(ASH, rng.uniform(.7, 1.1)))
    scatter(w, h, 45, .8, rock, scale=(.6, 1.6))

    def fumarole(x, z, s):
        b.add('cone6', (x, .5 * s, z), (1.6 * s, 1 * s, 1.6 * s), col=color.rgb(.45, .4, .3))
        glow.add('disc', (x, s * .98, z), (.5 * s, .05, .5 * s), col=color.rgb(1, .8, .3))
        w.smoke((x, s, z), .3, 7, 4, color.rgb(.75, .72, .6), size=.7)
    scatter(w, h, 7, 1, fumarole)

    def crack(x, z, s):      # fissures incandescentes dans le sol
        yaw = rng.uniform(0, 360)
        for _ in range(3):
            L = rng.uniform(1, 2.2) * s
            ox, oz = polar(yaw, L / 2)
            glow.add('box', (x + ox, .035, z + oz), (.14, .02, L), rot=(0, yaw, 0), col=LAVA)
            x, z = x + ox * 2, z + oz * 2
            yaw += rng.uniform(-50, 50)
    scatter(w, h, 60, .5, crack, solid=False, gap=0)


# =================================================================== EAU
WATER = color.rgb(.22, .6, .92)
SAND = color.rgb(.93, .86, .64)


def lake(w, b, water, x, z, rx, rz, yaw=0):
    b.add('disc', (x, .02, z), (rx * 2 + 2.4, .04, rz * 2 + 2.4), rot=(0, yaw, 0), col=SAND)
    water.add('disc', (x, .05, z), (rx * 2, .04, rz * 2), rot=(0, yaw, 0), col=WATER)
    water.add('disc', (x, .052, z), (rx * 1.3, .04, rz * 1.3), rot=(0, yaw, 0), col=color.rgb(.15, .48, .85))
    # obstacle : quelques cercles couvrant l'ellipse
    ax, az = polar(yaw + 90, 1)
    big, small = max(rx, rz), min(rx, rz)
    k = int(big / small) + 1
    for i in range(-k + 1, k):
        t = i / k * (big - small)
        if rx >= rz:
            w.block(x + ax * t, z + az * t, small + .2)
        else:
            w.block(x - az * t, z + ax * t, small + .2)


def palm(b, x, z, s, rng):
    lean = rng.uniform(0, 360)
    lx, lz = polar(lean, 1)
    k = rng.uniform(.25, .5)
    top = (x, 0, z)
    for i in range(7):
        y = (i + .5) * .75 * s
        off = k * (i / 6) ** 2 * 2.2 * s
        px, pz = x + lx * off, z + lz * off
        b.add('cyl6', (px, y, pz), (.42 * s * (1 - i * .05), .8 * s, .42 * s * (1 - i * .05)),
              rot=(k * i * 5, lean, 0), col=color.rgb(.55, .42, .28) if i % 2 else color.rgb(.47, .35, .22))
        top = (px, y + .4 * s, pz)
    tx, ty, tz = top
    for i in range(7):
        yaw = i * 360 / 7 + rng.uniform(-10, 10)
        ox, oz = polar(yaw, 1.3 * s)
        b.add('box', (tx + ox, ty - .25 * s, tz + oz), (.7 * s, .06, 2.8 * s), rot=(22, yaw, 0),
              col=color.rgb(.18, .58 + rng.uniform(-.05, .05), .22))
    for i in range(3):
        ox, oz = polar(i * 120 + 40, .3 * s)
        b.add('sphere_lo', (tx + ox, ty - .45 * s, tz + oz), .32 * s, col=color.rgb(.4, .26, .12))


def _eau(w, h, b, glow, water):
    rng = w.rng
    # falaise en arc de cercle avec une cascade qui tombe dans un bassin
    cr = C.LAIR_DISTANCE + R_LAIR + 24
    for i in range(-5, 6):
        a = h + i * 5.2
        x, z = polar(a, cr + abs(i) * .6 + rng.uniform(-1, 1))
        hh = 17 - abs(i) * 1.1 + rng.uniform(-1.5, 1.5)
        b.add('box', (x, hh / 2, z), (9.5, hh, 8), rot=(0, a, 0), col=shade(color.rgb(.46, .5, .56), rng.uniform(.9, 1.1)))
        b.add('box', (x, hh + .3, z), (9.8, .8, 8.3), rot=(0, a, 0), col=color.rgb(.3, .58, .3))
        w.block(x, z, 5)
    fx, fz = polar(h, cr - 4.1)
    fh = 16.5
    water.add('box', (fx, fh / 2, fz), (5.2, fh, .4), rot=(0, h, 0), col=color.rgb(.55, .82, 1))
    bx, bz = polar(h, cr - 10)
    lake(w, b, water, bx, bz, 6.5, 5, yaw=h)
    tx, tz = polar(h, cr - 4.5)
    w.flow([(tx, fh, tz), (tx, .3, tz)], count=26, col=color.rgb(.9, .97, 1),
           size=(.35, 1.4, .35), speed=9, jitter=2.2, glow=.9, jitter_axis=(math.cos(math.radians(h)), -math.sin(math.radians(h))))
    w.smoke((bx + (fx - bx) * .45, .2, bz + (fz - bz) * .45), 2.5, 3.5, 10, color.rgb(.92, .97, 1), size=1.1)

    # lacs, dont un avec un îlot et son palmier
    for i in range(n(5)):
        rx, rz = rng.uniform(4.5, 9), rng.uniform(3.5, 7)
        p = w.spot(h, max(rx, rz) + 1.5, gap=2)
        if p is None:
            continue
        yaw = rng.uniform(0, 180)
        lake(w, b, water, p[0], p[1], rx, rz, yaw)
        for _ in range(rng.randint(3, 7)):   # nénuphars
            a, d = rng.uniform(0, 360), rng.uniform(0, min(rx, rz) * .8)
            ox, oz = polar(a, d)
            b.add('cyl', (p[0] + ox, .08, p[1] + oz), (.9, .04, .9), col=color.rgb(.25, .6, .25))
            if rng.random() < .3:
                b.add('sphere_lo', (p[0] + ox, .2, p[1] + oz), .3, col=color.rgb(1, .6, .8))
        if i == 0:
            b.add('disc', (p[0], .06, p[1]), (3.2, .15, 3.2), col=SAND)
            palm(b, p[0], p[1], .8, rng)

    scatter(w, h, 55, .45, lambda x, z, s: palm(b, x, z, s, rng), scale=(.9, 1.3), gap=1.5)

    def reeds(x, z, s):
        for _ in range(rng.randint(4, 8)):
            ox, oz = rng.uniform(-.6, .6), rng.uniform(-.6, .6)
            hh = rng.uniform(.8, 1.6) * s
            b.add('cyl6', (x + ox, hh / 2, z + oz), (.07, hh, .07), rot=(rng.uniform(-8, 8), 0, rng.uniform(-8, 8)),
                  col=color.rgb(.35, .55, .2))
            if rng.random() < .4:
                b.add('cyl6', (x + ox, hh, z + oz), (.14, .35, .14), col=color.rgb(.45, .3, .15))
    scatter(w, h, 50, .5, reeds, solid=False, gap=0)

    def mossy_rock(x, z, s):
        b.add('sphere_lo', (x, .35 * s, z), (1.8 * s, 1.1 * s, 1.5 * s), rot=(0, rng.uniform(0, 180), 0),
              col=color.rgb(.52, .56, .6))
        b.add('sphere_lo', (x, .72 * s, z), (1.2 * s, .35 * s, 1 * s), col=color.rgb(.35, .6, .3))
    scatter(w, h, 22, .9, mossy_rock)

    def tide_pool(x, z, s):
        water.add('disc', (x, .04, z), (1.8 * s, .03, 1.4 * s), col=WATER)
    scatter(w, h, 18, 1, tide_pool, solid=False, gap=0)

    def shell(x, z, s):
        if rng.random() < .5:     # étoile de mer
            c = rng.choice((color.rgb(1, .45, .35), color.rgb(1, .65, .2)))
            for i in range(5):
                ox, oz = polar(i * 72, .18 * s)
                b.add('box', (x + ox, .05, z + oz), (.12 * s, .05, .36 * s), rot=(0, i * 72, 0), col=c)
        else:
            b.add('dome', (x, .02, z), (.45 * s, .3 * s, .4 * s), col=color.rgb(1, .88, .82))
    scatter(w, h, 40, .3, shell, solid=False, gap=0, r_min=C.WORLD_RADIUS - 14)


# =================================================================== PLANTE
LEAF = color.rgb(.2, .5, .18)


def big_tree(b, x, z, s, rng):
    b.add('cyl6', (x, 1.4 * s, z), (.7 * s, 2.8 * s, .7 * s), col=color.rgb(.4, .27, .16))
    g = color.rgb(.12 + rng.uniform(-.03, .05), .42 + rng.uniform(-.08, .1), .14)
    b.add('sphere', (x, 3.6 * s, z), (3.6 * s, 2.8 * s, 3.6 * s), col=g)
    for _ in range(3):
        ox, oz = polar(rng.uniform(0, 360), 1.1 * s)
        b.add('sphere', (x + ox, 3.2 * s + rng.uniform(0, 1) * s, z + oz), 2.2 * s, col=shade(g, rng.uniform(.9, 1.2)))


def giant_flower(b, glow, x, z, s, rng):
    b.add('cyl6', (x, 1.2 * s, z), (.18 * s, 2.4 * s, .18 * s), col=color.rgb(.2, .55, .2))
    for side in (-1, 1):
        b.add('sphere_lo', (x + .45 * s * side, .8 * s, z), (.9 * s, .12, .45 * s), rot=(0, 0, -25 * side), col=LEAF)
    petal = rng.choice((color.rgb(1, .4, .6), color.rgb(.95, .25, .3), color.rgb(.75, .45, 1),
                        color.rgb(1, .95, .95), color.rgb(1, .7, .2)))
    top = 2.4 * s
    for i in range(6):
        ox, oz = polar(i * 60, .55 * s)
        b.add('sphere_lo', (x + ox, top, z + oz), (.75 * s, .18 * s, .75 * s), col=petal)
    glow.add('sphere_lo', (x, top + .08, z), .45 * s, col=color.rgb(1, .9, .3))


def mushroom(b, x, z, s, rng):
    b.add('cyl6', (x, .4 * s, z), (.35 * s, .8 * s, .35 * s), col=color.rgb(.95, .92, .85))
    cap = rng.choice((color.rgb(.9, .15, .12), color.rgb(.95, .55, .15), color.rgb(.6, .35, .85)))
    b.add('dome', (x, .75 * s, z), (1.3 * s, .9 * s, 1.3 * s), col=cap)
    for i in range(5):
        ox, oz = polar(i * 72 + 20, .38 * s)
        b.add('sphere_lo', (x + ox, .98 * s, z + oz), .16 * s, col=color.white)


def _plante(w, h, b, glow, water):
    rng = w.rng
    # arbre géant millénaire
    lx, lz = landmark_pos(h)
    b.add('cyl', (lx, 13, lz), (9, 26, 9), col=color.rgb(.42, .29, .18))
    for i in range(7):                     # racines-contreforts
        yaw = i * 360 / 7 + rng.uniform(-10, 10)
        ox, oz = polar(yaw, 5.5)
        b.add('box', (lx + ox, 2.2, lz + oz), (1.4, 5, 5), rot=(0, yaw, 0), col=color.rgb(.38, .26, .16))
    for i in range(9):
        yaw, d = rng.uniform(0, 360), rng.uniform(3, 10)
        ox, oz = polar(yaw, d)
        r = rng.uniform(9, 14)
        b.add('sphere', (lx + ox, 29 + rng.uniform(-3, 5), lz + oz), (r * 2, r * 1.3, r * 2),
              col=color.rgb(.12, .4 + rng.uniform(-.06, .08), .14))
    for i in range(14):                    # lianes et fruits lumineux
        yaw, d = rng.uniform(0, 360), rng.uniform(8, 16)
        ox, oz = polar(yaw, d)
        L = rng.uniform(5, 10)
        b.add('box', (lx + ox, 24 - L / 2, lz + oz), (.15, L, .15), col=color.rgb(.2, .45, .15))
        glow.add('sphere_lo', (lx + ox, 24 - L, lz + oz), .5, col=color.rgb(1, .85, .35))
    w.block(lx, lz, 8)

    scatter(w, h, 120, .6, lambda x, z, s: big_tree(b, x, z, s, rng), scale=(.9, 1.6), gap=1.4)

    def bush(x, z, s):
        g = color.rgb(.18, .5 + rng.uniform(-.06, .06), .18)
        b.add('sphere_lo', (x, .5 * s, z), (1.7 * s, 1.2 * s, 1.7 * s), col=g)
        if rng.random() < .5:
            for _ in range(3):
                ox, oz = polar(rng.uniform(0, 360), .6 * s)
                b.add('sphere_lo', (x + ox, .9 * s, z + oz), .22, col=rng.choice((color.rgb(.9, .15, .2), color.rgb(.3, .3, .9))))
    scatter(w, h, 60, .8, bush)

    scatter(w, h, 32, .6, lambda x, z, s: giant_flower(b, glow, x, z, s, rng), scale=(.9, 1.8))
    scatter(w, h, 34, .5, lambda x, z, s: mushroom(b, x, z, s, rng), scale=(.7, 2.2))

    def log(x, z, s):
        yaw = rng.uniform(0, 360)
        b.add('cyl', (x, .45 * s, z), (.9 * s, 4 * s, .9 * s), rot=(90, yaw, 0), col=color.rgb(.42, .3, .18))
        b.add('sphere_lo', (x, .85 * s, z), (1.2 * s, .3, 2 * s), rot=(0, yaw, 0), col=color.rgb(.25, .55, .2))
        ox, oz = polar(yaw, 1.3 * s)
        w.block(x + ox, z + oz, .6 * s)
        w.block(x - ox, z - oz, .6 * s)
    scatter(w, h, 12, 1.2, log, solid=False)

    def fern(x, z, s):
        for i in range(5):
            yaw = i * 72 + rng.uniform(-15, 15)
            ox, oz = polar(yaw, .45 * s)
            b.add('box', (x + ox, .3 * s, z + oz), (.35 * s, .04, 1.2 * s), rot=(-30, yaw, 0), col=color.rgb(.2, .58, .22))
    scatter(w, h, 110, .4, fern, solid=False, gap=0)

    def flowers(x, z, s):
        c = rng.choice((color.rgb(1, .4, .5), color.rgb(1, .92, .3), color.white, color.rgb(.6, .5, 1)))
        for _ in range(4):
            b.add('sphere_lo', (x + rng.uniform(-.7, .7), .15, z + rng.uniform(-.7, .7)), .24, col=c)
    scatter(w, h, 90, .3, flowers, solid=False, gap=0)


# =================================================================== ROCHE
OCHRE = color.rgb(.72, .45, .28)
STRATA = [color.rgb(.78, .5, .3), color.rgb(.66, .38, .24), color.rgb(.85, .62, .4), color.rgb(.6, .35, .22)]


def mesa(b, x, z, rad, hgt, rng):
    layers = rng.randint(3, 5)
    for i in range(layers):
        k = 1 - i * .06
        lh = hgt / layers
        b.add('cyl', (x, lh * (i + .5), z), (rad * 2 * k, lh, rad * 2 * k), rot=(0, rng.uniform(0, 30), 0),
              col=STRATA[i % len(STRATA)])
    b.add('cyl', (x, hgt + .05, z), (rad * 2 * (1 - layers * .06), .15, rad * 2 * (1 - layers * .06)),
          col=color.rgb(.62, .55, .3))


def hoodoo(b, x, z, s, rng):
    y = 0
    r = 1.1 * s
    for i in range(rng.randint(3, 5)):
        hh = rng.uniform(.9, 1.5) * s
        b.add('sphere_lo', (x, y + hh / 2, z), (r * 2, hh * 1.2, r * 2), col=STRATA[i % len(STRATA)])
        y += hh * .9
        r *= .82
    b.add('cyl6', (x, y + .2 * s, z), (r * 3.2, .5 * s, r * 3.2), rot=(0, rng.uniform(0, 60), 4), col=color.rgb(.45, .32, .24))


def cactus(b, x, z, s, rng):
    g = color.rgb(.3, .55, .3)
    hh = rng.uniform(2.2, 3.4) * s
    b.add('cyl', (x, hh / 2, z), (.55 * s, hh, .55 * s), col=g)
    b.add('sphere_lo', (x, hh, z), .55 * s, col=g)
    yaw = rng.uniform(0, 360)
    for side in (-1, 1):
        if rng.random() < .75:
            ax, az = polar(yaw + 90 * side, .55 * s)
            y = rng.uniform(.35, .6) * hh
            b.add('cyl', (x + ax, y, z + az), (.3 * s, .7 * s, .3 * s), rot=(90, yaw + 90 * side, 0), col=g)
            ex, ez = polar(yaw + 90 * side, .9 * s)
            b.add('cyl', (x + ex, y + .5 * s, z + ez), (.34 * s, 1.1 * s, .34 * s), col=g)
            b.add('sphere_lo', (x + ex, y + 1.05 * s, z + ez), .34 * s, col=g)
    if rng.random() < .4:
        b.add('sphere_lo', (x, hh + .3 * s, z), .25 * s, col=color.rgb(1, .45, .6))


def _roche(w, h, b, glow, water):
    rng = w.rng
    # grande arche rocheuse encadrant le repaire, avec une mesa derrière
    lx, lz = landmark_pos(h)
    sx, sz = polar(h + 90, 1)
    for side in (-1, 1):
        px, pz = lx + sx * 11 * side, lz + sz * 11 * side
        for i in range(6):
            b.add('cyl', (px, 2.5 + i * 4.4, pz), (7 - i * .3, 4.6, 6.4 - i * .3), rot=(0, h + i * 7, 0),
                  col=STRATA[i % len(STRATA)])
        w.block(px, pz, 3.6)
    for i in range(9):
        t = (i - 4) / 4
        b.add('sphere_lo', (lx + sx * 11 * t, 28 - abs(t) ** 2 * 3, lz + sz * 11 * t), (7, 5.5, 6.5), rot=(0, h, 0),
              col=STRATA[i % len(STRATA)])
    mx, mz = polar(h, C.LAIR_DISTANCE + R_LAIR + 34)
    mesa(b, mx, mz, 12, 22, rng)
    w.block(mx, mz, 12)

    # crêtes de rochers le long des bords de la région (façon canyon)
    for side in (-1, 1):
        for i in range(10):
            r = 38 + i * 6.5
            if i in (3, 7):     # passages vers les régions voisines
                continue
            x, z = polar(h + 33 * side, r)
            hh = rng.uniform(4, 8)
            b.add('sphere_lo', (x, hh * .4, z), (6, hh, 5.5), rot=(0, rng.uniform(0, 180), 0), col=shade(OCHRE, rng.uniform(.85, 1.1)))
            w.block(x, z, 2.8)

    def small_mesa(x, z, s):
        mesa(b, x, z, 4.5 * s, rng.uniform(5, 10) * s, rng)
    scatter(w, h, 9, 4.6, small_mesa, scale=(.8, 1.5), gap=3)
    scatter(w, h, 28, 1.1, lambda x, z, s: hoodoo(b, x, z, s, rng), scale=(.8, 1.5), gap=1.5)

    def boulder(x, z, s):
        b.add('sphere_lo', (x, .45 * s, z), (1.9 * s, 1.4 * s, 1.6 * s), rot=(rng.uniform(-20, 20), rng.uniform(0, 180), 0),
              col=shade(OCHRE, rng.uniform(.75, 1.05)))
    scatter(w, h, 70, .9, boulder, scale=(.5, 1.8))
    scatter(w, h, 32, .5, lambda x, z, s: cactus(b, x, z, s, rng), scale=(.8, 1.3))

    def dry_bush(x, z, s):
        b.add('sphere_lo', (x, .3 * s, z), (1 * s, .6 * s, 1 * s), col=color.rgb(.6, .52, .3))
    scatter(w, h, 70, .4, dry_bush, solid=False, gap=0)

    def pebbles(x, z, s):
        for _ in range(4):
            b.add('sphere_lo', (x + rng.uniform(-.8, .8), .08, z + rng.uniform(-.8, .8)), (.35, .2, .3),
                  col=shade(OCHRE, rng.uniform(.7, 1)))
    scatter(w, h, 60, .3, pebbles, solid=False, gap=0)


# =================================================================== GLACE
SNOW = color.rgb(.95, .97, 1)
ICE = color.rgb(.62, .9, 1)
PINE = color.rgb(.1, .32, .25)


def snowy_pine(b, x, z, s, rng):
    b.add('cyl6', (x, .7 * s, z), (.4 * s, 1.4 * s, .4 * s), col=color.rgb(.4, .28, .18))
    for i, (r, y) in enumerate(((2.8, 2.0), (2.2, 3.2), (1.5, 4.3))):
        b.add('cone', (x, y * s, z), (r * s, 1.8 * s, r * s), col=PINE)
        b.add('cone', (x, (y + .35) * s, z), (r * .78 * s, 1.2 * s, r * .78 * s), col=SNOW)


def ice_spikes(glow, x, z, s, rng):
    for _ in range(rng.randint(3, 6)):
        ox, oz = rng.uniform(-.8, .8) * s, rng.uniform(-.8, .8) * s
        hh = rng.uniform(1.4, 3.6) * s
        glow.add('cone6', (x + ox, hh / 2, z + oz), (.7 * s, hh, .7 * s),
                 rot=(rng.uniform(-18, 18), 0, rng.uniform(-18, 18)), col=lerp(ICE, color.white, rng.uniform(0, .5)))


def _glace(w, h, b, glow, water):
    rng = w.rng
    # pic enneigé (deux sommets) avec des cristaux géants à sa base
    lx, lz = landmark_pos(h)
    for dx, rb, hh in ((0, 17, 38), (-12, 11, 24), (13, 10, 20)):
        sx, sz = polar(h + 90, dx)
        px, pz = lx + sx, lz + sz
        b.add('cone', (px, hh / 2, pz), (rb * 2, hh, rb * 2), col=color.rgb(.5, .56, .66))
        k = .5
        b.add('cone', (px, hh - hh * k / 2 + .05, pz), (rb * 2 * k + .2, hh * k, rb * 2 * k + .2), col=SNOW)
        w.block(px, pz, rb * .9)
    for i in range(8):
        a = h + rng.uniform(-40, 40)
        ox, oz = polar(a, 17)
        ice_spikes(glow, lx - ox * .2 + rng.uniform(-9, 9), lz - oz * .2 + rng.uniform(-9, 9), 2.4, rng)

    # lacs gelés (on peut marcher dessus)
    for _ in range(n(3)):
        rx = rng.uniform(6, 10)
        p = w.spot(h, rx, gap=2)
        if p is None:
            continue
        water.add('disc', (p[0], .04, p[1]), (rx * 2, .04, rx * 1.6), col=color.rgb(.7, .88, .98))
        for _ in range(4):
            yaw = rng.uniform(0, 360)
            b.add('box', (p[0] + rng.uniform(-rx / 2, rx / 2), .07, p[1] + rng.uniform(-rx / 3, rx / 3)),
                  (.06, .02, rng.uniform(1.5, 4)), rot=(0, yaw, 0), col=color.white)
        w.reserve(p[0], p[1], rx)

    scatter(w, h, 110, .6, lambda x, z, s: snowy_pine(b, x, z, s, rng), scale=(.8, 1.5), gap=1.2)
    scatter(w, h, 32, 1.0, lambda x, z, s: ice_spikes(glow, x, z, s, rng), scale=(.7, 1.6))

    def snowman(x, z, s):
        yaw = rng.uniform(0, 360)
        b.add('sphere', (x, .55 * s, z), 1.2 * s, col=SNOW)
        b.add('sphere', (x, 1.4 * s, z), .85 * s, col=SNOW)
        b.add('sphere', (x, 2.05 * s, z), .6 * s, col=SNOW)
        fx, fz = polar(yaw, .3 * s)
        b.add('cone6', (x + fx * 1.2, 2.05 * s, z + fz * 1.2), (.1 * s, .5 * s, .1 * s), rot=(90, yaw, 0),
              col=color.rgb(1, .5, .1))
        for side in (-1, 1):
            ex, ez = polar(yaw + 25 * side, .27 * s)
            b.add('sphere_lo', (x + ex, 2.15 * s, z + ez), .08 * s, col=color.rgb(.1, .1, .1))
        b.add('cyl', (x, 2.4 * s, z), (.5 * s, .35 * s, .5 * s), col=color.rgb(.15, .15, .18))
    scatter(w, h, 6, .7, snowman)

    def igloo(x, z, s):
        yaw = rng.uniform(0, 360)
        b.add('dome', (x, 0, z), (4 * s, 3.2 * s, 4 * s), col=SNOW)
        ox, oz = polar(yaw, 2 * s)
        b.add('cyl', (x + ox, .5 * s, z + oz), (1.3 * s, 1.4 * s, 1.3 * s), rot=(90, yaw, 0), col=SNOW)
        ox, oz = polar(yaw, 2.72 * s)
        b.add('disc', (x + ox, .5 * s, z + oz), (.9 * s, .02, .9 * s), rot=(90, yaw, 0), col=color.rgb(.1, .12, .2))
    scatter(w, h, 3, 2.3, igloo, gap=3)

    def drift(x, z, s):
        b.add('sphere_lo', (x, 0, z), (2.2 * s, .7 * s, 1.6 * s), rot=(0, rng.uniform(0, 180), 0), col=SNOW)
    scatter(w, h, 70, .6, drift, solid=False, gap=0)

    # icebergs au large
    for _ in range(n(9)):
        a = h + rng.uniform(-34, 34)
        x, z = polar(a, C.WORLD_RADIUS + rng.uniform(8, 20))
        s = rng.uniform(1.5, 3.5)
        b.add('cone4', (x, 0, z), (3 * s, 3.4 * s, 2.6 * s), rot=(0, rng.uniform(0, 90), 0), col=color.rgb(.88, .96, 1))
        b.add('sphere_lo', (x, -.6, z), (4 * s, 1.5, 3.6 * s), col=color.rgb(.7, .9, 1))


# =================================================================== repères
def signpost(b, glow, type_key, x, z, yaw):
    t = C.TYPES[type_key]
    b.add('cyl6', (x, 1.3, z), (.25, 2.6, .25), col=color.rgb(.45, .32, .2))
    b.add('box', (x, 2.3, z), (1.8, .8, .15), rot=(0, yaw, 0), col=t['color'])
    add_emblem(glow, type_key, (x, 3.3, z), .45)
