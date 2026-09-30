"""Boutique : achat et revente des objets tenus (touche B, dans sa base ou pendant un K.O.)."""
from ursina import Entity, Text, camera, color

from game import config as C
from game.interface.lobby import DIM, F_BOLD, F_SEMI, GOLD, Btn, panel

CAN = color.rgba(.1, .16, .3, .95)
CANT = color.rgba(.1, .1, .14, .9)
OWNED = color.rgba(.12, .3, .18, .95)


def _nothing():
    pass


class Shop(Entity):
    def __init__(self, match):
        super().__init__(parent=camera.ui, z=-3)
        self.m = match
        self.state = None
        self.body = None
        self.refresh()

    def refresh(self):
        """Reconstruit la page si l'argent, les objets ou l'accès à la boutique ont changé."""
        u = self.m.player
        state = (int(u.gold), tuple(u.items), self.m.can_shop(u))
        if state == self.state:
            return
        self.state = state
        if self.body is not None:
            from game.world.geometry import destroy_tree
            destroy_tree(self.body)
        self.body = b = Entity(parent=self)
        gold, items, open_ = state
        panel(b, (0, .02), 1.12, .74)
        Text(parent=b, text='BOUTIQUE', position=(-.52, .35, -.01), origin=(-.5, 0), scale=1.6, color=GOLD, **F_BOLD)
        Text(parent=b, text=f'{gold} ₽', position=(.52, .35, -.01), origin=(.5, 0), scale=1.5, color=GOLD, **F_BOLD)
        hint = ('Cliquez sur un objet pour l\'acheter' if open_ else
                'Boutique fermée : revenez dans votre base (ou attendez d\'être K.O.)')
        Text(parent=b, text=hint + f'   -   {C.ITEM_SLOTS} objets maximum   -   B : fermer',
             position=(0, .31, -.01), origin=(0, 0), scale=.75, color=DIM if open_ else color.rgb(1, .6, .5), **F_SEMI)
        full = len(items) >= C.ITEM_SLOTS
        for i, (key, it) in enumerate(C.ITEMS.items()):
            x, y = (-.275 if i % 2 == 0 else .275), .24 - (i // 2) * .085
            have = key in items
            ok = open_ and not have and not full and gold >= it['price']
            col = OWNED if have else CAN if ok else CANT
            label = f"{it['name']}   {it['price']} ₽" + ('   (tenu)' if have else '')
            Btn(b, label, (x, y), (lambda k=key: self.m.request_buy(k)) if ok else _nothing, w=.53, h=.074, col=col,
                accent=GOLD if ok else None, size=.85, align='left', sub=it['desc'])
        Text(parent=b, text='OBJETS TENUS', position=(-.52, -.2, -.01), origin=(-.5, 0), scale=.9, color=GOLD, **F_BOLD)
        for i in range(C.ITEM_SLOTS):
            x = -.36 + i * .36
            if i < len(items):
                it = C.ITEMS[items[i]]
                refund = int(it['price'] * C.SELL_RATIO)
                Btn(b, it['name'], (x, -.27), (lambda n=i: self.m.request_sell(n)) if open_ else _nothing, w=.33, h=.07,
                    col=OWNED, size=.85, sub=f'Revendre : +{refund} ₽' if open_ else '')
            else:
                Btn(b, 'emplacement libre', (x, -.27), _nothing, w=.33, h=.07, col=CANT, size=.75)
