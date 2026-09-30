"""Barre de vie au-dessus des Pokémon : badge de niveau, cadre arrondi, graduations et traînée
claire qui fond après un coup (on voit ce qu'on vient de perdre)."""
from ursina import Circle, Entity, Quad, Text, color

TICK_HP = 500                  # une graduation tous les 500 PV (1000 pour les très gros Pokémon)
SIZE = 1.35                    # taille à l'écran (la caméra de partie est assez haute)
LAG_DELAY = .35                # la traînée attend un instant avant de fondre
FRAME = color.rgba(.05, .06, .09, .85)
EMPTY = color.rgba(.16, .17, .22, .95)
LAG = color.rgb(1, .93, .75)


def _rounded(w, h, r):
    """Quadrilatère aux coins arrondis de taille (w, h). Un modèle par barre : Ursina déplace un
    modèle partagé d'une entité à l'autre au lieu de le dupliquer."""
    return Quad(radius=r / h, aspect=w / h, segments=4)


def _hexagon():
    return Circle(resolution=6)


class HealthBar:
    def __init__(self, parent, y, width, fill_col, badge_col=None, label=None, label_col=None):
        self.w = w = width
        self.root = Entity(parent=parent, y=y + .1, billboard=True, scale=SIZE)
        h = .2                                   # hauteur de la jauge
        frame = Entity(parent=self.root, model=_rounded(w + .1, h + .1, .06), color=FRAME, z=.01)
        frame.scale = (w + .1, h + .1)
        Entity(parent=self.root, model='quad', color=EMPTY, scale=(w, h))
        self.lag = Entity(parent=self.root, model='quad', color=LAG, origin=(-.5, 0),
                          position=(-w / 2, 0, -.005), scale=(w, h))
        self.fill = Entity(parent=self.root, model='quad', color=fill_col, origin=(-.5, 0),
                           position=(-w / 2, 0, -.01), scale=(w, h))
        # reflet sur le haut de la jauge et ombre en bas (volume) : suivent la largeur de la jauge
        Entity(parent=self.fill, model='quad', origin=(-.5, 0), y=.3, z=-.001, scale=(1, .28),
               color=color.rgba(1, 1, 1, .32))
        Entity(parent=self.fill, model='quad', origin=(-.5, 0), y=-.38, z=-.001, scale=(1, .24),
               color=color.rgba(0, 0, 0, .22))
        self.ticks = []
        self.tick_hp = None
        # badge de niveau (hexagone) à gauche de la jauge
        bc = badge_col or fill_col
        self.badge = Entity(parent=self.root, x=-w / 2 - .24, z=-.02)
        Entity(parent=self.badge, model=_hexagon(), color=FRAME, scale=.56, z=.002)
        Entity(parent=self.badge, model=_hexagon(), color=bc, scale=.48, z=.001)
        Entity(parent=self.badge, model=_hexagon(), color=color.rgb(.1, .11, .16), scale=.38)
        self.level_text = Text(parent=self.badge, text='1', origin=(0, 0), scale=11, z=-.01,
                               color=color.white)
        self.level = 1
        if label:
            Text(parent=self.root, text=label, y=.34, z=-.02, origin=(0, 0), scale=10, color=label_col or bc)
        self.ratio = self.shown_lag = 1.0
        self.lag_wait = 0.0

    # ------------------------------------------------------------ mise à jour
    def set(self, hp, max_hp):
        ratio = max(0.0, min(1.0, hp / max_hp)) if max_hp else 0.0
        if ratio < self.ratio:
            self.lag_wait = LAG_DELAY
        else:
            self.shown_lag = max(self.shown_lag, ratio)
        self.ratio = ratio
        self.fill.scale_x = self.w * ratio
        self._ticks(max_hp)
        self._apply_lag()

    def set_level(self, level):
        if level != self.level:
            self.level = level
            self.level_text.text = str(level)

    def tick(self, dt):
        """A chaque image : la traînée claire rattrape la jauge."""
        if self.shown_lag <= self.ratio:
            return
        if self.lag_wait > 0:
            self.lag_wait -= dt
            return
        self.shown_lag = max(self.ratio, self.shown_lag - dt * .8)
        self._apply_lag()

    def _apply_lag(self):
        self.lag.scale_x = self.w * max(self.ratio, self.shown_lag)

    def _ticks(self, max_hp):
        step = TICK_HP if max_hp < 6000 else TICK_HP * 2
        n = int((max_hp - 1) // step)
        if n == len(self.ticks) and step == self.tick_hp:
            if max_hp != getattr(self, 'tick_max', max_hp):         # même nombre : on les replace
                self.tick_max = max_hp
                for i, t in enumerate(self.ticks):
                    t.x = -self.w / 2 + self.w * (i + 1) * step / max_hp
            return
        from ursina import destroy
        for t in self.ticks:
            destroy(t)
        self.tick_hp = step
        self.ticks = [Entity(parent=self.root, model='quad', color=color.rgba(0, 0, 0, .55), z=-.015,
                             x=-self.w / 2 + self.w * (i + 1) * step / max_hp, y=-.03, scale=(.025, .14), ignore=True)
                      for i in range(n)]
        self.tick_max = max_hp
