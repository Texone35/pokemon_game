"""Cartes d'information de la partie : état de l'arène où l'on se trouve, météo et terrain, bonus
et objets tenus, réapparition. Même style que la bannière et le fil des événements (style.py).
Les textes ne sont recréés que lorsqu'ils changent (coûteux avec Ursina)."""
from ursina import Entity, Text, color

from game.interface.style import CARD, DIM, F_BOLD, F_SEMI, NEUTRAL, Card, light, rounded, text_width


def _set(t, value):
    if t.text != value:
        t.text = value


class Bar(Entity):
    """Petite jauge arrondie (fond sombre + remplissage)."""

    def __init__(self, parent, w, h, col, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.w = w
        Entity(parent=self, model=rounded(w, h, h / 2), scale=(w, h), color=color.rgba(1, 1, 1, .1), origin=(-.5, 0))
        self.fill = Entity(parent=self, model='quad', scale=(0, h * .7), color=col, origin=(-.5, 0), z=-.001)

    def set(self, ratio, col=None):
        self.fill.scale_x = self.w * max(0.0, min(1.0, ratio))
        if col is not None:
            self.fill.color = col


class ArenaCard(Entity):
    """Arène où se trouve le joueur : nom et type, qui la contrôle, avancement de la capture,
    PV de la tour. Sert aussi à signaler les hautes herbes (caché / repéré)."""
    W, H = .5, .082

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.card = Card(self)
        self.card.set_size(self.W, self.H)
        x0 = self.card.left()
        self.title = Text(parent=self.card, text='', position=(x0, .02, -.01), origin=(-.5, 0), scale=.95, **F_BOLD)
        self.state = Text(parent=self.card, text='', position=(self.W / 2 - .02, .02, -.01), origin=(.5, 0), scale=.8,
                          **F_BOLD)
        self.cap_label = Text(parent=self.card, text='capture', position=(x0, -.016, -.01), origin=(-.5, 0),
                              scale=.62, color=DIM, **F_SEMI)
        self.cap = Bar(self.card, .19, .014, NEUTRAL, position=(x0 + .075, -.016, -.01))
        self.tower_label = Text(parent=self.card, text='tour', position=(x0 + .3, -.016, -.01), origin=(-.5, 0),
                                scale=.62, color=DIM, **F_SEMI)
        self.tower = Bar(self.card, .11, .014, color.rgb(.9, .9, .95), position=(x0 + .34, -.016, -.01))
        self.mode = None

    def show_arena(self, a, teams, types, tower):
        self.enabled = True
        self._mode('arena')
        tcol = types[a['type']]['light']
        _set(self.title, f"{a['name'].upper()}  ·  {types[a['type']]['name']}")
        self.title.color = tcol
        self.card.set_accent(tcol)
        c = a['control']
        lead = teams['rouge' if c > 0 else 'bleu']
        if a['contested']:
            _set(self.state, 'CONTESTÉE')
            self.state.color = color.rgb(1, .85, .35)
        elif a['owner']:
            _set(self.state, f"ÉQUIPE {teams[a['owner']]['name'].upper()}")
            self.state.color = light(teams[a['owner']]['color'], .35)
        else:
            _set(self.state, 'NEUTRE')
            self.state.color = NEUTRAL
        self.cap.set(abs(c), lead['color'] if c else NEUTRAL)
        on = tower is not None
        self.tower.enabled = self.tower_label.enabled = on
        if on:
            self.tower.set(tower.hp / max(1, tower.max_hp), light(teams[tower.team]['color'], .2))

    def show_message(self, title, sub, col):
        self.enabled = True
        self._mode('msg')
        _set(self.title, title)
        _set(self.state, '')
        self.title.color = light(col, .25)
        _set(self.cap_label, sub)
        self.card.set_accent(col)

    def _mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        arena = mode == 'arena'
        self.cap.enabled = self.tower.enabled = self.tower_label.enabled = arena
        if arena:
            _set(self.cap_label, 'capture')

    def hide(self):
        self.enabled = False


class InfoCard(Entity):
    """Carte à deux lignes (titre en gras, détail) ancrée à gauche : météo, terrain..."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.card = Card(self, origin=(-.5, 0))
        self.title = Text(parent=self.card, text='', origin=(-.5, 0), y=.012, z=-.01, scale=.78, **F_BOLD)
        self.sub = Text(parent=self.card, text='', origin=(-.5, 0), y=-.013, z=-.01, scale=.64, **F_SEMI)
        self.key = None

    def show(self, key, title, sub, col):
        self.enabled = True
        if key == self.key:
            return
        self.key = key
        self.title.text, self.sub.text = title, sub
        self.title.color = light(col, .2)
        self.sub.color = color.rgba(.88, .9, 1, .9)
        w = max(text_width(self.title), text_width(self.sub)) + .05
        self.card.set_size(w, .052)
        self.card.set_accent(col)
        self.title.x = self.sub.x = self.card.left()

    def hide(self):
        self.enabled = False
        self.key = None


class PillRow(Entity):
    """Rangée de pastilles (bonus actifs avec leur durée, objets tenus), alignée à gauche."""
    H = .03

    def __init__(self, parent, max_w=.5, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.pills = []
        self.sig = None
        self.max_w = max_w
        self.height = 0.0              # hauteur occupée (les pastilles passent à la ligne vers le haut)

    def set(self, items):
        """items : liste de (texte, couleur)."""
        sig = tuple((t, tuple(round(v, 3) for v in c)) for t, c in items)
        if sig == self.sig:
            return
        if self.sig is not None and len(sig) == len(self.sig) and all(a[1] == b[1] for a, b in zip(sig, self.sig)):
            for (t, c), (card, txt) in zip(items, self.pills):     # même pastilles : on change le texte
                if txt.text != t:
                    txt.text = t
                    card.set_size(text_width(txt) + .04, self.H)
            self._layout()
            self.sig = sig
            return
        self.sig = sig
        from ursina import destroy
        for card, txt in self.pills:
            destroy(txt)
            for e in card.children:
                destroy(e)
            destroy(card)
        self.pills = []
        for t, c in items:
            card = Card(self, accent=c, origin=(-.5, 0))
            txt = Text(parent=card, text=t, origin=(-.5, 0), z=-.01, scale=.66, color=light(c, .45), **F_SEMI)
            card.set_size(text_width(txt) + .04, self.H)
            txt.x = card.left()
            self.pills.append((card, txt))
        self._layout()

    def _layout(self):
        x, y = 0.0, 0.0
        for card, txt in self.pills:
            if x > 0 and x + card.w > self.max_w:
                x, y = 0.0, y + self.H + .007
            card.x, card.y = x, y
            x += card.w + .008
        self.height = y + self.H if self.pills else 0.0


class CountdownCard(Entity):
    """K.O. : grande carte « Retour dans 12 s » au centre de l'écran."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.card = Card(self, accent=color.rgb(1, .45, .4))
        self.card.set_size(.42, .1)
        self.title = Text(parent=self.card, text='K.O.', origin=(0, 0), y=.022, z=-.01, scale=1.3,
                          color=color.rgb(1, .6, .55), **F_BOLD)
        self.sub = Text(parent=self.card, text='', origin=(0, 0), y=-.022, z=-.01, scale=.85, color=DIM, **F_SEMI)
        self.enabled = False

    def show(self, seconds, hint):
        self.enabled = True
        _set(self.title, f'Retour dans {seconds} s')
        _set(self.sub, hint)


__all__ = ['ArenaCard', 'InfoCard', 'PillRow', 'CountdownCard', 'Bar', 'CARD']
