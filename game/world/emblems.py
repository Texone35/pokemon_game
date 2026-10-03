"""Symboles 3D des types (au-dessus des arènes, sur les piliers...)."""
import math

from ursina import color


def add_emblem(b, type_key, pos=(0, 0, 0), s=1.0, col=None):
    """Ajoute le symbole du type dans le MeshBuilder `b`, centré sur `pos`."""
    x, y, z = pos
    if type_key == 'feu':
        c = col or color.rgb(1, .45, .08)
        b.add('sphere', (x, y - .3 * s, z), (1.1 * s, 1.1 * s, 1.1 * s), col=c)
        b.add('cone', (x, y + .55 * s, z), (.9 * s, 1.4 * s, .9 * s), col=c)
        b.add('sphere', (x, y - .2 * s, z + .15 * s), (.6 * s, .7 * s, .6 * s), col=color.rgb(1, .85, .2))
    elif type_key == 'eau':
        c = col or color.rgb(.2, .55, 1)
        b.add('sphere', (x, y - .3 * s, z), 1.2 * s, col=c)
        b.add('cone', (x, y + .6 * s, z), (.95 * s, 1.3 * s, .95 * s), col=c)
    elif type_key == 'plante':
        c = col or color.rgb(.3, .85, .3)
        b.add('sphere', (x, y, z), (.5 * s, 1.8 * s, .9 * s), rot=(0, 0, 30), col=c)
        b.add('box', (x, y, z), (.06 * s, 1.7 * s, .95 * s), rot=(0, 0, 30), col=color.rgb(.15, .5, .15))
    elif type_key == 'roche':
        c = col or color.rgb(.65, .55, .42)
        b.add('cone4', (x, y + .45 * s, z), (1.3 * s, .9 * s, 1.3 * s), col=c)
        b.add('cone4', (x, y - .45 * s, z), (1.3 * s, .9 * s, 1.3 * s), rot=(180, 0, 0), col=c)
    elif type_key == 'glace':
        c = col or color.rgb(.65, .95, 1)
        b.add('cone6', (x, y + .55 * s, z), (.8 * s, 1.1 * s, .8 * s), col=c)
        b.add('cone6', (x, y - .55 * s, z), (.8 * s, 1.1 * s, .8 * s), rot=(180, 0, 0), col=c)
        for i in range(3):
            a = math.radians(i * 120)
            b.add('cone6', (x + math.sin(a) * .45 * s, y, z + math.cos(a) * .45 * s),
                  (.35 * s, .9 * s, .35 * s), rot=(0, i * 120, 55), col=c)
    elif type_key == 'electrik':
        c = col or color.rgb(1, .88, .15)
        b.add('box', (x + .12 * s, y + .45 * s, z), (.32 * s, .75 * s, .22 * s), rot=(0, 0, -25), col=c)
        b.add('box', (x, y, z), (.7 * s, .22 * s, .22 * s), rot=(0, 0, 20), col=c)
        b.add('box', (x - .12 * s, y - .45 * s, z), (.32 * s, .75 * s, .22 * s), rot=(0, 0, -25), col=c)
        b.add('cone4', (x - .22 * s, y - .9 * s, z), (.3 * s, .4 * s, .22 * s), rot=(180, 0, 0), col=c)
    elif type_key == 'psy':
        c = col or color.rgb(.85, .45, 1)
        b.add('sphere', (x, y, z), (1.2 * s, 1.2 * s, 1.2 * s), col=c)
        b.add('sphere', (x, y, z + .3 * s), (.6 * s, .6 * s, .7 * s), col=color.rgb(1, .8, 1))
    else:
        _more(b, type_key, x, y, z, s, col)


def _more(b, t, x, y, z, s, col):
    """Symboles des autres types (silhouettes dans le plan x-y, comme les précédents)."""
    def P(dx, dy):
        return (x + dx * s, y + dy * s, z)
    if t == 'normal':                          # disque cerclé
        c = col or color.rgb(.85, .82, .75)
        b.add('cyl24', P(0, 0), (1.5 * s, .3 * s, 1.5 * s), rot=(90, 0, 0), col=c)
        b.add('ring', P(0, 0), (2.0 * s, .3 * s, 2.0 * s), rot=(90, 0, 0), col=c)
    elif t == 'combat':                        # poing
        c = col or color.rgb(.9, .4, .25)
        b.add('box', P(0, -.15), (1.2 * s, 1.0 * s, .5 * s), col=c)
        for i in range(4):
            b.add('sphere', P(-.45 + i * .3, .45), (.36 * s, .4 * s, .4 * s), col=c)
        b.add('sphere', P(-.68, -.05), (.4 * s, .6 * s, .4 * s), col=c)
    elif t == 'poison':                        # goutte et bulles
        c = col or color.rgb(.75, .4, .9)
        b.add('sphere', P(0, -.25), 1.1 * s, col=c)
        b.add('cone', P(0, .5), (.8 * s, 1.0 * s, .8 * s), col=c)
        b.add('sphere', P(.6, .7), .35 * s, col=c)
        b.add('sphere', P(.8, .25), .22 * s, col=c)
    elif t == 'sol':                           # butte et faille
        c = col or color.rgb(.9, .7, .38)
        b.add('dome', P(0, -.4), (2.0 * s, 1.6 * s, 1.0 * s), rot=(-90, 0, 0), col=c)
        b.add('box', P(.05, 0), (.14 * s, 1.2 * s, .6 * s), rot=(0, 0, 18), col=color.rgb(.45, .3, .15))
    elif t == 'vol':                           # aile
        c = col or color.rgb(.75, .85, 1)
        for i in range(4):
            b.add('sphere', P(-.1 + i * .22, .35 - i * .28), (1.5 * s - i * .25 * s, .38 * s, .4 * s),
                  rot=(0, 0, 25), col=c)
    elif t == 'insecte':                       # scarabée
        c = col or color.rgb(.7, .82, .2)
        b.add('sphere', P(-.3, -.1), (.6 * s, 1.4 * s, .4 * s), rot=(0, 0, 8), col=c)
        b.add('sphere', P(.3, -.1), (.6 * s, 1.4 * s, .4 * s), rot=(0, 0, -8), col=c)
        b.add('sphere', P(0, .75), .45 * s, col=c)
        for sx in (-1, 1):
            b.add('box', P(sx * .25, 1.15), (.08 * s, .5 * s, .1 * s), rot=(0, 0, -sx * 25), col=c)
    elif t == 'spectre':                       # fantôme
        c = col or color.rgb(.6, .45, .9)
        b.add('sphere', P(0, .3), 1.2 * s, col=c)
        b.add('cone', P(.2, -.6), (.8 * s, 1.2 * s, .5 * s), rot=(0, 0, 160), col=c)
        for sx in (-1, 1):
            b.add('sphere', P(sx * .25, .4), .22 * s, col=color.rgb(.15, .1, .25))
    elif t == 'dragon':                        # crocs
        c = col or color.rgb(.5, .45, 1)
        for sx in (-1, 1):
            b.add('cone6', P(sx * .35, 0), (.5 * s, 1.8 * s, .4 * s), rot=(0, 0, sx * 15 + 180), col=c)
        b.add('box', P(0, .75), (1.5 * s, .3 * s, .4 * s), col=c)
    elif t == 'tenebres':                      # croissant de lune
        c = col or color.rgb(.55, .45, .42)
        b.add('cyl24', P(0, 0), (1.6 * s, .3 * s, 1.6 * s), rot=(90, 0, 0), col=c)
        b.add('cyl24', P(.35, .2), (1.3 * s, .32 * s, 1.3 * s), rot=(90, 0, 0), col=color.rgb(.1, .08, .1))
    elif t == 'acier':                         # engrenage
        c = col or color.rgb(.78, .8, .88)
        b.add('ring', P(0, 0), (1.6 * s, .3 * s, 1.6 * s), rot=(90, 0, 0), col=c)
        for i in range(8):
            a = math.radians(i * 45)
            b.add('box', P(math.sin(a) * .85, math.cos(a) * .85), (.32 * s, .32 * s, .3 * s),
                  rot=(0, 0, -i * 45), col=c)
    elif t == 'fee':                           # étoile à quatre branches
        c = col or color.rgb(1, .7, .9)
        for i in range(4):
            b.add('cone4', P(0, 0), (.6 * s, 2.0 * s, .3 * s), rot=(0, 0, i * 90), col=c)
        b.add('sphere', P(0, 0), .5 * s, col=color.rgb(1, .92, .97))
