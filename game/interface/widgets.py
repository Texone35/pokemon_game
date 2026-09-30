"""Éléments d'interface réutilisables : panneaux de PV, bannière, cases d'attaque, fil d'événements."""
from ursina import Entity, Text, camera, color, curve, destroy, lerp, time

from game.interface.style import F_BOLD, F_SEMI, Card, light, text_width

PANEL_BG = color.rgba(.97, .97, .92, .92)
PANEL_EDGE = color.rgba(.15, .15, .18, .95)


def hp_color(ratio):
    if ratio > .5:
        return color.rgb(.25, .85, .35)
    if ratio > .2:
        return color.rgb(.98, .8, .15)
    return color.rgb(.95, .25, .2)


class HPPanel(Entity):
    """Panneau façon Pokémon : nom, niveau, barre de PV animée."""

    def __init__(self, name, level, max_hp, type_name='', type_color=color.gray,
                 show_numbers=True, **kwargs):
        super().__init__(parent=camera.ui, **kwargs)
        w, h = .5, .115 if show_numbers else .09
        Entity(parent=self, model='quad', origin=(-.5, .5), scale=(w + .012, h + .012),
               position=(-.006, .006, .01), color=PANEL_EDGE)
        Entity(parent=self, model='quad', origin=(-.5, .5), scale=(w, h), color=PANEL_BG)
        Text(parent=self, text=name, position=(.02, -.012), scale=1.15, color=color.rgb(.1, .1, .12),
             origin=(-.5, .5))
        Text(parent=self, text=f'Nv.{level}', position=(w - .02, -.014), origin=(.5, .5),
             color=color.rgb(.15, .15, .2))
        if type_name:
            Entity(parent=self, model='quad', color=type_color, origin=(-.5, .5),
                   scale=(.1, .026), position=(.27, -.016, -.01))
            Text(parent=self, text=type_name.upper(), scale=.75, position=(.32, -.029, -.02),
                 origin=(0, 0), color=color.white)

        bar_y = -.058
        Text(parent=self, text='PV', position=(.02, bar_y + .012), scale=.8, origin=(-.5, .5),
             color=color.rgb(.9, .6, .1))
        bar_w = w - .09
        Entity(parent=self, model='quad', origin=(-.5, 0), scale=(bar_w + .008, .024),
               position=(.066, bar_y), color=PANEL_EDGE)
        self.lag = Entity(parent=self, model='quad', origin=(-.5, 0), scale=(bar_w, .016),
                          position=(.07, bar_y, -.01), color=color.rgb(1, .45, .35))
        self.fill = Entity(parent=self, model='quad', origin=(-.5, 0), scale=(bar_w, .016),
                           position=(.07, bar_y, -.02), color=hp_color(1))
        self.bar_w = bar_w
        self.max_hp = max_hp
        self.hp = max_hp
        self.shown = max_hp
        self.numbers = None
        if show_numbers:
            self.numbers = Text(parent=self, text='', position=(w - .02, -.078), origin=(.5, .5),
                                color=color.rgb(.1, .1, .12))
        self._refresh(max_hp)

    def set_hp(self, hp):
        self.hp = max(0, min(self.max_hp, hp))

    def _refresh(self, shown):
        ratio = max(0, shown / self.max_hp)
        self.fill.scale_x = self.bar_w * ratio
        self.fill.color = hp_color(ratio)
        if self.numbers:
            self.numbers.text = f'{int(round(shown))} / {self.max_hp}'

    def update(self):
        # la barre verte descend vite, la barre rouge "retard" suit plus lentement
        if abs(self.shown - self.hp) > .05:
            self.shown = lerp(self.shown, self.hp, min(1, time.dt * 10))
            self._refresh(self.shown)
        lag_target = self.bar_w * max(0, self.hp / self.max_hp)
        if self.lag.scale_x > lag_target:
            self.lag.scale_x = max(lag_target, self.lag.scale_x - time.dt * self.bar_w * .45)
        else:
            self.lag.scale_x = lag_target


class Banner(Entity):
    """Message central temporaire : carte arrondie avec une barre de la couleur du message. Un message
    « titre   détail » (séparé par trois espaces) s'affiche sur deux lignes."""
    FADE_IN, FADE_OUT = .15, .35

    def __init__(self):
        super().__init__(parent=camera.ui, z=-5, y=.13)
        self.card = Card(self)
        self.text = Text(parent=self.card, text='', origin=(0, 0), z=-.01, scale=1.2, **F_BOLD)
        self.sub = Text(parent=self.card, text='', origin=(0, 0), z=-.01, scale=.8, **F_SEMI)
        self.timer = 0
        self.age = 0
        self.enabled = False

    def show(self, message, duration=2.0, text_color=color.white, big=False):
        title, sub = message, ''
        if '   ' in message:
            title, sub = (x.strip() for x in message.split('   ', 1))
        self.text.text, self.sub.text = title, sub
        self.text.scale = 2.2 if big else 1.2
        self.text.color = light(text_color, .15)
        self.sub.color = color.rgba(.9, .92, 1, .92)
        limit = camera.aspect_ratio * .9
        for t in (self.text, self.sub):               # message trop long : on réduit pour qu'il tienne
            if text_width(t) > limit - .08:
                t.scale *= (limit - .08) / text_width(t)
        w = max(text_width(self.text), text_width(self.sub)) + .09
        h = (.13 if big else .07) + (.038 if sub else 0)
        self.card.set_size(w, h)
        self.card.set_accent(text_color)
        self.text.x = self.sub.x = .006
        self.text.y = .018 if sub else 0
        self.sub.y = -h / 2 + .03
        self.enabled = True
        self.timer = duration if duration else float('inf')   # None = reste affiché
        self.age = 0
        self.card.set_alpha(0)
        self.scale = .92
        self.animate_scale(1, duration=.18, curve=curve.out_back)

    def update(self):
        self.age += time.dt
        if self.age < self.FADE_IN:
            self.card.set_alpha(self.age / self.FADE_IN)
        elif self.age - time.dt < self.FADE_IN:
            self.card.set_alpha(1)
        if self.timer > 0:
            self.timer -= time.dt
            if self.timer < self.FADE_OUT:
                self.card.set_alpha(max(0, self.timer / self.FADE_OUT))
            if self.timer <= 0:
                self.enabled = False


def floating_text(message, world_pos, col=color.white, scale=1.2, **font):
    """Petit texte qui monte puis disparaît (dégâts, 'super efficace'...)."""
    font = font or F_BOLD
    anchor = Entity(position=world_pos)
    x, y = anchor.screen_position
    destroy(anchor)
    t = Text(text=message, parent=camera.ui, color=col, scale=scale, origin=(0, 0), position=(x, y, -1), **font)
    t.animate_y(y + .08, duration=.8, curve=curve.out_quad)
    t.fade_out(duration=.35, delay=.45)
    destroy(t, delay=.85)
    return t


class MoveSlot(Entity):
    """Case d'attaque avec touche, nom et voile de recharge."""
    W, H = .12, .085

    def __init__(self, key_label, name, locked=None, **kwargs):
        """locked : niveau qui débloque l'attaque (case grisée avec un cadenas), ou None."""
        kwargs.setdefault('parent', camera.ui)
        super().__init__(**kwargs)
        self.locked = locked
        Entity(parent=self, model='quad', color=color.rgba(.05, .05, .08, .8), scale=(self.W, self.H))
        self.shade = Entity(parent=self, model='quad', color=color.rgba(0, 0, 0, .65), origin=(0, -.5),
                            position=(0, -self.H / 2, -.02), scale=(self.W, 0))
        self.count = None
        if not locked:
            self.key_text = Text(parent=self, text=key_label, origin=(0, 0), y=.013, z=-.01,
                                 scale=1.4 if len(key_label) == 1 else .9, color=color.rgb(1, .92, .35), **F_BOLD)
            Text(parent=self, text=name, origin=(0, 0), y=-.025, z=-.01, scale=.6, color=color.rgb(.92, .92, .92),
                 **F_SEMI)
            self.count = Text(parent=self, text='', origin=(0, 0), y=.012, z=-.03, scale=1.2, color=color.white,
                              **F_BOLD)
            return
        # attaque pas encore débloquée : cadenas, nom grisé et niveau d'évolution requis
        lock = Entity(parent=self, position=(0, .02, -.01))
        Entity(parent=lock, model='circle', color=color.rgb(.8, .76, .6), scale=.02, y=.008)
        Entity(parent=lock, model='circle', color=color.rgba(.05, .05, .08, 1), scale=.011, y=.008, z=-.001)
        Entity(parent=lock, model='quad', color=color.rgb(.8, .76, .6), scale=(.024, .016), z=-.002)
        Text(parent=self, text=name, origin=(0, 0), y=-.01, z=-.01, scale=.58, color=color.rgb(.55, .56, .62))
        Text(parent=self, text=f'Nv {locked}', origin=(0, 0), y=-.03, z=-.01, scale=.72, color=color.rgb(1, .9, .55))

    def set_ratio(self, ratio, seconds=0.0):
        """Voile de recharge (ratio 0-1) et, pour les longues recharges, secondes restantes."""
        if self.locked:
            return
        self.shade.scale_y = self.H * max(0, min(1, ratio))
        label = f'{int(seconds) + 1}' if seconds > 1.5 else ''
        if self.count is not None and self.count.text != label:
            self.count.text = label
            self.key_text.enabled = not label           # pendant la recharge : les secondes à la place de la touche


class Feed(Entity):
    """Fil des événements (K.O., captures, objectifs) : des cartes alignées à droite, avec une barre
    de la couleur de l'événement, qui s'effacent seules."""
    STEP, H = .04, .032

    def __init__(self, count=6, **kwargs):
        kwargs.setdefault('parent', camera.ui)
        super().__init__(**kwargs)
        self.lines = []
        for i in range(count):
            card = Card(self, origin=(.5, 0), y=-i * self.STEP)
            txt = Text(parent=card, text='', origin=(-.5, 0), z=-.01, scale=.7, **F_SEMI)
            card.enabled = False
            self.lines.append((card, txt))
        self.items = []

    def push(self, message, col=color.white, duration=6.0):
        self.items.insert(0, [message, col, duration])
        del self.items[len(self.lines):]
        self._refresh(full=True)

    def _refresh(self, full=False):
        for i, (card, txt) in enumerate(self.lines):
            if i < len(self.items):
                msg, col, t = self.items[i]
                if full or txt.text != msg:
                    txt.text = msg
                    txt.color = light(col, .3)
                    card.set_size(text_width(txt) + .045, self.H)
                    card.set_accent(col)
                    txt.x = card.left()
                    card.set_alpha(min(1, t))
                card.enabled = True
                if t < 1:
                    card.set_alpha(t)
            elif card.enabled:
                card.enabled = False

    def update(self):
        if not self.items:
            return
        n = len(self.items)
        for it in self.items:
            it[2] -= time.dt
        self.items = [it for it in self.items if it[2] > 0]
        if len(self.items) != n:
            self._refresh(full=True)
        elif self.items[-1][2] < 1:
            self._refresh()
