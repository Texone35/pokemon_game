"""Carte tirée et écran de chargement.

MapFigure : petite carte stylisée du stade (voies, chemins, rivière, bases, Boss Pit) avec les arènes
aux couleurs de leur type ; servie au salon (carte tirée pour la partie) et à l'écran de chargement.
LoadingScreen : écran plein qui montre la carte tirée, la météo et le bonus de chaque arène, une barre
de progression qui avance en douceur, l'étape en cours et des conseils de jeu.
"""
import math

from ursina import Circle, Entity, Quad, Text, camera, color, lerp

from game import config as C
from game.interface.style import DIM, F_BOLD, F_SEMI, F_TITLE, GOLD, key_label
from game.world.stadium import LANES, RIVERS

FIELD = color.rgb(.13, .3, .17)
FIELD_EDGE = color.rgb(.32, .5, .36)
ROAD = color.rgba(.85, .85, .8, .75)
WATER = color.rgba(.35, .65, 1, .65)
PIT = color.rgb(.6, .32, .9)

TIPS = [
    f"Dans le cercle d'une arène, appuyez sur {key_label(C.CAPTURE_KEY)} pour la capturer : la tour ne vous vise plus.",
    "Chaque arène tenue installe sa météo sur tout son quartier : vos attaques du bon type y sont renforcées.",
    "Les hautes herbes vous cachent aux yeux de l'équipe adverse.",
    "Le champ de force d'une base empêche l'équipe adverse d'y entrer.",
    "Mewtwo apparaît au Boss Pit à 3 min 30, Regigigas à 7 min : de gros points pour qui les bat.",
    "Les petits Pokémon sauvages autour de chaque arène donnent de quoi monter de niveau sur sa voie.",
    "Les Baies Sitrus de la jungle soignent tout de suite une bonne partie des PV.",
    "Espace : une esquive rapide, rare mais décisive.",
]


def _rounded(w, h, r):
    return Quad(radius=min(.5, r / h), aspect=w / h)


def weather_of(t):
    return C.WEATHERS[C.WEATHER_OF[t]]


class MapFigure:
    """Carte stylisée du stade, de rayon `size` (unités de l'écran), centrée sur parent."""

    def __init__(self, parent, types, size, position=(0, 0), labels=True, z=0):
        self.root = Entity(parent=parent, position=(position[0], position[1], z))
        self.k = size / C.FIELD_RADIUS
        k = self.k
        Entity(parent=self.root, model=Circle(64), color=FIELD_EDGE, scale=size * 2.06, z=.004)
        Entity(parent=self.root, model=Circle(64), color=FIELD, scale=size * 2, z=.003)
        for pts, w in RIVERS:
            self._polyline(pts, max(.0025, w * k * .8), WATER, .002)
        for pts, w in LANES:
            self._polyline(pts, max(.003, w * k * .7), ROAD, .001)
        Entity(parent=self.root, model=Circle(24), color=PIT, scale=C.PIT_RADIUS * 2 * k)
        for team in C.TEAMS.values():
            bx, bz = team['base']
            Entity(parent=self.root, model=Circle(24), color=color.white, scale=C.BASE_RADIUS * 2.6 * k,
                   position=(bx * k, bz * k, -.001))
            Entity(parent=self.root, model=Circle(24), color=team['color'], scale=C.BASE_RADIUS * 2.2 * k,
                   position=(bx * k, bz * k, -.002))
        self.hexes = {}
        r = C.ARENA_RADIUS * 2.3 * k
        for a in C.ARENAS:
            t = C.TYPES[types[a['key']]]
            x, z = a['pos'][0] * k, a['pos'][1] * k
            h = Entity(parent=self.root, position=(x, z, -.004))
            h.glow = Entity(parent=h, model=Circle(6), rotation_z=30, scale=r * 1.45,
                            color=color.rgba(t['light'][0], t['light'][1], t['light'][2], 0), z=.002)
            Entity(parent=h, model=Circle(6), rotation_z=30, scale=r * 1.12, color=t['dark'], z=.001)
            h.fill = Entity(parent=h, model=Circle(6), rotation_z=30, scale=r, color=t['color'])
            if labels:
                Text(parent=h, text=t['name'], origin=(0, 0), y=-r * .95, z=-.002, scale=size * 3.2,
                     color=t['light'], **F_BOLD)
            self.hexes[a['key']] = h

    def _polyline(self, pts, width, col, z):
        k = self.k
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            dx, dz = (bx - ax) * k, (bz - az) * k
            L = math.hypot(dx, dz)
            if L < 1e-6:
                continue
            Entity(parent=self.root, model='quad', color=col, z=z, scale=(L + width, width),
                   position=((ax + bx) * k / 2, (az + bz) * k / 2), rotation_z=-math.degrees(math.atan2(dz, dx)))

    def pulse(self, t, keys=None):
        """Halo qui palpite autour des arènes `keys` (toutes si None)."""
        a = .25 + .2 * math.sin(t * 4)
        for key, h in self.hexes.items():
            on = keys is None or key in keys
            c = h.glow.color
            h.glow.color = color.rgba(c[0], c[1], c[2], a if on else 0)


class LoadingScreen(Entity):
    """Écran de chargement de la partie (la carte se termine, puis les Pokémon, puis l'interface)."""

    def __init__(self, types):
        super().__init__(parent=camera.ui, z=-5)
        self.map_types = types
        self.shown = 0.0              # progression affichée (rattrape la vraie en douceur)
        self.target = 0.0
        self.t = 0.0
        self.tip_i, self.tip_t = 0, 0.0
        # fond : dégradé nuit, deux halos colorés
        Entity(parent=self, model='quad', scale=(4, 2), color=color.rgb(.03, .04, .1), z=.05)
        Entity(parent=self, model=Circle(48), scale=1.05, position=(-.38, 0, .04), color=color.rgba(.25, .4, 1, .07))
        Text(parent=self, text='POKÉMON DOMINION', position=(0, .44), origin=(0, 0), scale=2.6, color=GOLD, **F_TITLE)
        Text(parent=self, text='Le stade se prépare : voici la carte tirée pour cette partie', position=(0, .385),
             origin=(0, 0), scale=.95, color=DIM, **F_SEMI)
        # carte tirée
        self.figure = MapFigure(self, types, .3, position=(-.38, -.0), z=-.01)
        # arènes : type, météo, bonus d'équipe
        y = .27
        for a in C.ARENAS:
            t = types[a['key']]
            tc = C.TYPES[t]
            wx = weather_of(t)
            row = Entity(parent=self, position=(.06, y, -.01))
            Entity(parent=row, model=_rounded(.012, .085, .006), scale=(.012, .085), color=tc['color'], x=-.01)
            Text(parent=row, text=f"Arène {tc['name']}", position=(.01, .025), origin=(-.5, 0), scale=1.2,
                 color=tc['light'], **F_BOLD)
            Text(parent=row, text=a['place'], position=(.75, .025), origin=(.5, 0), scale=.8, color=DIM, **F_SEMI)
            Text(parent=row, text=f"{wx['name']} : {wx['desc']}", position=(.01, -.008), origin=(-.5, 0),
                 scale=.78, color=color.rgba(1, 1, 1, .85), **F_SEMI)
            Text(parent=row, text=f"Bonus d'équipe : {C.ARENA_BONUS[t][2]}", position=(.01, -.036),
                 origin=(-.5, 0), scale=.72, color=DIM, **F_SEMI)
            y -= .118
        # progression
        w = 1.2
        self.bar_w = w
        Entity(parent=self, model=_rounded(w + .012, .03, .015), scale=(w + .012, .03), y=-.36, z=-.01,
               color=color.rgba(1, 1, 1, .12))
        self.bar = Entity(parent=self, model='quad', origin=(-.5, 0), scale=(.001, .018), position=(-w / 2, -.36, -.02),
                          color=GOLD)
        self.bar_tip = Entity(parent=self, model=Circle(16), scale=.03, position=(-w / 2, -.36, -.03),
                              color=color.rgba(1, .95, .7, .9))
        self.pct = Text(parent=self, text='0 %', position=(w / 2, -.325, -.02), origin=(.5, 0), scale=1.1,
                        color=color.white, **F_BOLD)
        self.step = Text(parent=self, text='', position=(-w / 2, -.325, -.02), origin=(-.5, 0), scale=.9,
                         color=DIM, **F_SEMI)
        self.tip = Text(parent=self, text='', position=(0, -.43, -.02), origin=(0, 0), scale=.85,
                        color=color.rgb(.75, .85, 1), **F_SEMI)
        # roue qui tourne (Poké Ball stylisée)
        self.spin = Entity(parent=self, position=(.8, .44, -.02))
        Entity(parent=self.spin, model=Circle(32), scale=.06, color=color.white)
        Entity(parent=self.spin, model=Quad(), origin=(0, -.5), scale=(.06, .03), color=color.rgb(.9, .2, .2), z=-.001)
        Entity(parent=self.spin, model='quad', scale=(.06, .006), color=color.rgb(.1, .1, .12), z=-.002)
        Entity(parent=self.spin, model=Circle(24), scale=.02, color=color.rgb(.1, .1, .12), z=-.003)
        Entity(parent=self.spin, model=Circle(24), scale=.012, color=color.white, z=-.004)
        self._next_tip()

    def _next_tip(self):
        self.tip.text = 'Conseil : ' + TIPS[self.tip_i % len(TIPS)]
        self.tip_i += 1
        self.tip_t = 6.0

    def set(self, progress, label):
        self.target = max(self.target, min(1.0, progress))
        if self.step.text != label:
            self.step.text = label

    def tick(self, dt):
        """À chaque image (dt plafonné : une grosse étape ne fait pas sauter l'animation)."""
        dt = min(dt, .05)
        self.t += dt
        self.shown += (self.target - self.shown) * min(1.0, dt * 5)
        w = max(.001, self.bar_w * self.shown)
        self.bar.scale_x = w
        self.bar_tip.x = -self.bar_w / 2 + w
        self.bar.color = lerp(GOLD, color.rgb(1, .95, .6), .5 + .5 * math.sin(self.t * 3))
        pct = f'{int(self.shown * 100)} %'
        if self.pct.text != pct:
            self.pct.text = pct
        self.spin.rotation_z += dt * 220
        # les arènes s'allument une à une au fil du chargement
        keys = [a['key'] for i, a in enumerate(C.ARENAS) if self.shown > (i + .5) / (len(C.ARENAS) + 1)]
        self.figure.pulse(self.t, keys)
        self.tip_t -= dt
        if self.tip_t <= 0:
            self._next_tip()
