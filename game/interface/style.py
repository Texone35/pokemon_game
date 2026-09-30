"""Style commun de l'interface : polices, couleurs et formes arrondies (salon, boutique, partie)."""
import os
from pathlib import Path

from ursina import Entity, Quad, Text, application, color


def _font(name):
    """Police Windows si elle existe (Segoe UI), sinon celle d'Ursina par défaut."""
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    if (folder / name).exists():
        application.fonts_folder = folder
        return {'font': name}
    return {}


F_TITLE, F_BOLD, F_SEMI = _font('seguibl.ttf'), _font('segoeuib.ttf'), _font('seguisb.ttf')

GOLD = color.rgb(1, .82, .28)
PANEL = color.rgba(.06, .07, .15, .86)
PANEL_EDGE = color.rgba(.45, .55, .95, .35)
CARD = color.rgba(.05, .06, .13, .82)            # fond des cartes d'information en partie
DIM = color.rgba(.82, .86, 1, .72)
GOOD = color.rgb(.45, 1, .55)
BAD = color.rgb(1, .45, .4)
NEUTRAL = color.rgb(.78, .8, .88)


_KEY_LABELS = None


def key_label(key):
    """Lettre imprimée sur la touche à cette position, selon la disposition du clavier (AZERTY...)."""
    global _KEY_LABELS
    if _KEY_LABELS is None:
        _KEY_LABELS = {}
        try:
            km = application.base.win.get_keyboard_map()
            for i in range(km.get_num_buttons()):
                label = km.get_mapped_button_label(i)
                if label and len(label) == 1 and label.isalpha():
                    _KEY_LABELS[str(km.get_raw_button(i))] = label.upper()
        except Exception:            # fenêtre sans clavier (tests) : lettres QWERTY
            pass
    return _KEY_LABELS.get(key, key.upper())


def rounded(w, h, r):
    """Rectangle aux coins arrondis de rayon r (unités de l'écran)."""
    return Quad(radius=min(.5, r / h), aspect=w / h, segments=4)


def text_width(t):
    return t.width * t.scale_x


def light(c, k=.55):
    """Couleur éclaircie (textes sur fond sombre)."""
    return color.rgb(c[0] + (1 - c[0]) * k, c[1] + (1 - c[1]) * k, c[2] + (1 - c[2]) * k)


class Card(Entity):
    """Carte arrondie sombre avec un liseré et une barre d'accent colorée à gauche, qui s'adapte à
    son contenu. `set_size` la redimensionne ; `set_alpha` la fait apparaître ou s'effacer."""

    def __init__(self, parent, accent=GOLD, origin=(0, 0), **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.anchor = origin               # (-.5 : bord gauche, .5 : bord droit, 0 : centre) en x
        self.edge = Entity(parent=self, color=color.rgba(1, 1, 1, .1), z=.002)
        self.bg = Entity(parent=self, color=CARD, z=.001)
        self.bar = Entity(parent=self, color=accent)
        self.accent_col = accent
        self.w = self.h = 0
        self._alpha = 1.0

    def set_size(self, w, h):
        if (w, h) == (self.w, self.h):
            return
        self.w, self.h = w, h
        cx = -self.anchor[0] * w
        self.edge.model, self.edge.scale, self.edge.x = rounded(w + .006, h + .006, .014), (w + .006, h + .006), cx
        self.bg.model, self.bg.scale, self.bg.x = rounded(w, h, .012), (w, h), cx
        self.bar.model = rounded(.006, h * .62, .003)
        self.bar.scale = (.006, h * .62)
        self.bar.x = cx - w / 2 + .012

    def left(self):
        """Abscisse du début du contenu (après la barre d'accent)."""
        return -self.anchor[0] * self.w - self.w / 2 + .026

    def set_accent(self, col):
        self.accent_col = col
        self.bar.color = color.rgba(col[0], col[1], col[2], self._alpha)

    def set_alpha(self, a):
        self._alpha = a
        self.bg.color = color.rgba(CARD[0], CARD[1], CARD[2], CARD[3] * a)
        self.edge.color = color.rgba(1, 1, 1, .1 * a)
        c = self.accent_col
        self.bar.color = color.rgba(c[0], c[1], c[2], a)
        for t in self.children:
            if isinstance(t, Text):
                tc = t.color
                t.color = color.rgba(tc[0], tc[1], tc[2], a)
