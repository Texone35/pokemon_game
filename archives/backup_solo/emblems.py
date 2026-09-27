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
