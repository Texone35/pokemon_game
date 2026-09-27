"""Page d'accueil et salon : choix du mode, invitation d'un ami, choix du Pokémon.

Écrans
  'home' : Jouer seul / Créer une partie à deux / Rejoindre une partie
  'join' : l'invité colle le code d'invitation reçu
  'room' : chaque joueur choisit son Pokémon et se déclare prêt ; l'hôte lance la
           partie quand les deux sont prêts (en solo : bouton « Lancer »).

Décor : une petite scène 3D (fond dégradé, estrade lumineuse) devant la caméra du
salon. L'accueil présente les Pokémon jouables sur un carrousel ; le salon montre
le Pokémon choisi en grand sur un socle, ses statistiques et ses attaques, et des
cartes avec le portrait de chaque Pokémon pour choisir.

Messages du salon (JSON, voir net.Link) :
  hôte -> invité : hello, lobby (choix et « prêt » des deux joueurs, latence), start, reject, bye
  invité -> hôte : join (version du jeu), pick, ready, pong, leave
"""
import math
import os
import random
import re
import time
from pathlib import Path

import numpy as np
from ursina import (Button, Entity, InputField, Quad, Text, Texture, Vec3, application, camera, color, destroy,
                    lerp, time as utime)
from ursina.shaders import unlit_shader

from game import config as C
from game.network import net
from game.pokemon.creatures import Creature, Portraits
from game.world.geometry import MeshBuilder, flat_circle

GOLD = color.rgb(1, .82, .28)
GOLD_DARK = color.rgb(.55, .4, .08)
PANEL = color.rgba(.06, .07, .15, .86)
PANEL_EDGE = color.rgba(.45, .55, .95, .35)
BTN = color.rgba(.1, .12, .24, .95)
BTN_EDGE = color.rgba(.5, .6, 1, .3)
DIM = color.rgba(.82, .86, 1, .72)
OK_GREEN = color.rgb(.45, 1, .55)
ERR = color.rgb(1, .55, .5)
BG_TOP, BG_BOTTOM = np.array([9, 13, 36]), np.array([46, 32, 92])

CAM_POS, CAM_LOOK = Vec3(0, 2.1, -11), Vec3(0, 1.25, 0)
MAIN_POS = Vec3(-1.2, 0, 2.5)        # socle du Pokémon choisi (salon)
OTHER_POS = Vec3(-6.2, 0, 4.5)       # socle du Pokémon de l'autre joueur
CAROUSEL = Vec3(3.6, 0, 6.5)         # carrousel de l'accueil
CAROUSEL_R = 3.4

MOVE_KIND = {'basic': 'attaque de base', 'rush': 'ruée', 'strike': 'impact de zone', 'homing': 'tête chercheuse',
             'spin': 'onde de choc'}
SPECIAL_KIND = {'beam': 'rayon', 'wave': 'onde', 'zone': 'zone', 'nova': 'anneau', 'charge': 'charge', 'heal': 'soin'}


def _font(name):
    """Police Windows si elle existe (Segoe UI), sinon celle d'Ursina par défaut."""
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    if (folder / name).exists():
        application.fonts_folder = folder
        return {'font': name}
    return {}


F_TITLE, F_BOLD, F_SEMI = _font('seguibl.ttf'), _font('segoeuib.ttf'), _font('seguisb.ttf')


def _copy(text):
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except Exception:
        return False


def _paste():
    try:
        import pyperclip
        return pyperclip.paste() or ''
    except Exception:
        return ''


def _quad(w, h, r):
    """Rectangle aux coins arrondis de rayon r (unités de l'écran)."""
    return Quad(radius=min(.5, r / h), aspect=w / h)


def panel(parent, pos, w, h, col=PANEL, edge=PANEL_EDGE, r=.022):
    """Panneau arrondi avec un liseré clair."""
    e = Entity(parent=parent, position=(pos[0], pos[1], .02))
    if edge is not None:
        Entity(parent=e, model=_quad(w + .005, h + .005, r + .0025), scale=(w + .005, h + .005), color=edge)
    Entity(parent=e, model=_quad(w, h, r), scale=(w, h), color=col, z=-.001)
    return e


def chip(parent, text, pos, col, w=None, txt_col=color.white, size=.8, z=-.02):
    """Petite étiquette colorée (type, « PRÊT », « vous »...)."""
    w = w or .03 + len(text) * .0135 * size
    e = Entity(parent=parent, position=(pos[0], pos[1], z))
    Entity(parent=e, model=_quad(w, .032 * size / .8, .016), scale=(w, .032 * size / .8), color=col)
    Text(parent=e, text=text, origin=(0, 0), scale=size, color=txt_col, z=-.001, **F_BOLD)
    return e


class Btn(Entity):
    """Bouton arrondi : fond, liseré, barre d'accent colorée à gauche, texte (et sous-titre)."""

    def __init__(self, parent, text, pos, on_click, w=.42, h=.072, col=BTN, accent=None, size=1.05,
                 align='center', sub=None):
        super().__init__(parent=parent, position=(pos[0], pos[1], 0))
        self.base_col = col
        Entity(parent=self, model=_quad(w + .005, h + .005, .02), scale=(w + .005, h + .005), color=BTN_EDGE, z=.002)
        self.bg = Button(parent=self, scale=(w, h), radius=min(.5, .018 / h), color=col,
                         highlight_color=col.tint(.1), pressed_color=col.tint(-.08), on_click=on_click)
        left = align == 'left'
        x = -w / 2 + (.045 if accent else .03) if left else 0
        self.label = Text(parent=self, text=text, position=(x, .012 if sub else .002, -.01),
                          origin=(-.5 if left else 0, 0), scale=size, **F_BOLD)
        if sub:
            Text(parent=self, text=sub, position=(x, -.016, -.01), origin=(-.5 if left else 0, 0), scale=.72,
                 color=DIM, **F_SEMI)
        self.accent = None
        if accent is not None:
            self.accent = Entity(parent=self, model=_quad(.007, h * .56, .0035), scale=(.007, h * .56),
                                 position=(-w / 2 + .02, 0, -.01), color=accent)

    def set(self, text=None, col=None):
        if text is not None and self.label.text != text:
            self.label.text = text
        if col is not None:
            self.bg.color = col
            self.bg.highlight_color = col.tint(.1)
            self.bg.pressed_color = col.tint(-.08)


# ==================================================================== décor 3D
def _backdrop_texture():
    """Fond dégradé nuit, avec un halo clair derrière l'estrade."""
    from PIL import Image
    n = 256
    y = np.linspace(0, 1, n)[:, None, None]
    x = np.linspace(-1, 1, n)[None, :, None]
    col = BG_TOP * (1 - y) + BG_BOTTOM * y
    glow = np.exp(-((x * 1.1) ** 2 + ((y - .7) * 2.4) ** 2))
    col = col + np.array([55, 75, 150]) * glow * .55
    return Texture(Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), 'RGB'))


def _floor(parent):
    """Sol en disque : clair au centre, qui se fond dans le bas du fond dégradé."""
    radii = np.linspace(0, 34, 40)
    ang = np.linspace(0, math.tau, 65)
    rr, aa = np.meshgrid(radii, ang, indexing='ij')
    x, z = np.sin(aa) * rr, np.cos(aa) * rr
    t = np.clip(rr / 30, 0, 1)[..., None]
    centre, edge = np.array([.2, .2, .4, 1]), np.append(BG_BOTTOM / 255, 1)
    col = centre * (1 - t) + edge * t
    verts = np.stack([x, np.zeros_like(x), z], -1).reshape(-1, 3)
    nr, na = rr.shape
    idx = np.arange(nr * na).reshape(nr, na)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    tris = np.stack([a, c, b, b, c, d], -1).reshape(-1)
    norms = np.tile([0, 1, 0], (len(verts), 1))
    return MeshBuilder().add_raw(verts, tris, norms, col.reshape(-1, 4)).entity(parent=parent, emissive=.8)


class Podium:
    """Socle lumineux (anneau aux couleurs du type) sur lequel un Pokémon tourne lentement."""

    def __init__(self, parent, pos, size=1.0):
        self.root = Entity(parent=parent, position=pos, scale=size)
        mb = MeshBuilder()
        mb.add('cyl_hi', (0, .12, 0), (3.9, .24, 3.9), col=color.rgb(.15, .16, .28))
        mb.add('cyl_hi', (0, .3, 0), (3.3, .14, 3.3), col=color.rgb(.86, .87, .93))
        mb.add('cyl_hi', (0, .38, 0), (2.5, .03, 2.5), col=color.rgb(.93, .94, .98))
        mb.entity(parent=self.root)
        self.ring = MeshBuilder().add('ring_97', (0, .25, 0), (3.6, .12, 3.6), col=color.white).entity(
            parent=self.root, emissive=1.0)
        self.halo = flat_circle(self.root, 2.6, color.rgba(1, 1, 1, .12), y=.01)
        self.species = None
        self.creature = None
        self.spin = 22

    def show(self, species):
        if species == self.species:
            return
        self.species = species
        if self.creature is not None:
            destroy(self.creature)
            self.creature = None
        if species:
            t = C.TYPES[C.SPECIES[species]['type']]
            self.ring.color = t['light']
            self.halo.color = color.rgba(t['color'][0], t['color'][1], t['color'][2], .22)
            s = C.SPECIES[species]['scale']
            self.creature = Creature(species, parent=self.root, scale=s, y=.4)
            self.creature.rotation_y = 200
            self.creature.pivot.scale = .01
            self.creature.pivot.animate_scale(s, duration=.3)

    def update(self, dt):
        if self.creature is not None:
            self.creature.rotation_y += dt * self.spin
            self.creature.animate(dt)


class Carousel:
    """Accueil : les Pokémon jouables tournent sur un plateau ; celui de devant est mis en avant."""

    def __init__(self, parent):
        self.root = Entity(parent=parent, position=CAROUSEL)
        self.table = Entity(parent=self.root)
        self.slots = []
        n = len(C.PLAYABLE)
        for i, sp in enumerate(C.PLAYABLE):
            a = math.tau * i / n
            p = Podium(self.table, (math.sin(a) * CAROUSEL_R, 0, math.cos(a) * CAROUSEL_R), size=.6)
            p.show(sp)
            p.creature.pivot.animate_scale(C.SPECIES[sp]['scale'], duration=.01)
            self.slots.append(p)
        self.angle = 180.0
        self.front = None

    def update(self, dt):
        self.angle += dt * 14
        self.table.rotation_y = self.angle
        best, bd = None, 1e9
        for p in self.slots:
            p.creature.animate(dt)
            p.creature.rotation_y = 180 - self.angle           # toujours tournés vers la caméra
            d = (p.root.world_position - CAM_POS).length()
            k = min(1, max(0, (CAROUSEL.z - CAM_POS.z + CAROUSEL_R - d) / (2 * CAROUSEL_R)))
            p.root.scale = .5 + .4 * k * k                     # celui de devant est plus grand
            p.ring.scale = 1 + .08 * k
            if d < bd:
                best, bd = p, d
        self.front = best.species


class Sparkles:
    """Petites lueurs qui montent doucement autour de l'estrade."""

    def __init__(self, parent, count=26):
        self.rng = random.Random(4)
        mb = MeshBuilder().add('sphere_lo', (0, 0, 0), .09, col=color.white)
        self.items = []
        for _ in range(count):
            e = mb.entity(parent=parent, emissive=1.0, color=self.rng.choice(
                (color.rgb(1, .9, .5), color.rgb(.6, .8, 1), color.rgb(.9, .7, 1))))
            self._reset(e, self.rng.uniform(0, 5))
            self.items.append(e)

    def _reset(self, e, y=0.0):
        e.position = (self.rng.uniform(-9, 9), y, self.rng.uniform(-2, 7))
        e.speed = self.rng.uniform(.25, .6)

    def update(self, dt):
        for e in self.items:
            e.y += e.speed * dt
            e.x += math.sin(e.y * 2 + e.z) * dt * .15
            if e.y > 6:
                self._reset(e)


def _stats(species):
    """Statistiques normalisées (0-1) parmi les Pokémon jouables, pour les jauges du salon."""
    def raw(sp):
        d = C.SPECIES[sp]
        a = d['attack']
        return {'PV': d['hp'], 'Vitesse': d['speed'], 'Portée': a['range'], 'Puissance': a['damage'] / a['cooldown']}
    vals = [raw(sp) for sp in C.PLAYABLE]
    me = raw(species)
    out = []
    for k in me:
        lo, hi = min(v[k] for v in vals), max(v[k] for v in vals)
        out.append((k, .2 + .8 * (me[k] - lo) / ((hi - lo) or 1)))
    return out


def _move_kind(species, mv):
    if mv['kind'] == 'special':
        return SPECIAL_KIND.get(C.SPECIES[species]['special']['kind'], 'capacité spéciale')
    return MOVE_KIND.get(mv['kind'], '')


class Lobby(Entity):
    def __init__(self, game, message=None):
        super().__init__()
        self.game = game
        self.ui = None
        self.host = None                   # net.Host (on héberge)
        self.guest = None                  # net.Guest (on rejoint)
        self.link = None                   # connexion avec l'autre joueur
        self.mode = None                   # 'solo', 'host' ou 'guest'
        self.pick = {'me': 'pikachu', 'other': None}
        self.ready = {'me': False, 'other': False}
        self.ping_ms = None
        self._ping_t = 0.0
        self._starting = False
        self.cards = None
        self._info_species = None
        # scène 3D : fond, sol, estrade, socles, carrousel
        from game.world.geometry import unfreeze_shadows
        unfreeze_shadows(self.game.sun)        # quelques objets seulement : ombres calculées en direct
        self.scene = Entity()
        Entity(parent=self.scene, model='quad', texture=_backdrop_texture(), shader=unlit_shader,
               position=(0, 5, 36), scale=(96, 54))
        _floor(self.scene)
        MeshBuilder().add('ring_99', (0, .02, 1.5), (19, .04, 19), col=color.rgb(.35, .6, 1)).entity(
            parent=self.scene, emissive=1.0)
        self.previews = [Podium(self.scene, MAIN_POS), Podium(self.scene, OTHER_POS, size=.8)]
        self.carousel = Carousel(self.scene)
        self.sparkles = Sparkles(self.scene)
        self.portraits = Portraits(C.PLAYABLE)
        self.game.sky.enabled = False
        camera.position = CAM_POS
        camera.look_at(CAM_LOOK)
        camera.fov = 40
        self.show_home(message)

    # ================================================================ écrans
    def _clear_ui(self):
        if self.ui is not None:
            destroy(self.ui)
        self.ui = Entity(parent=camera.ui)
        self.cards = None
        self._info_species = None
        self.front_label = None
        for p in self.previews:
            p.show(None)
            p.root.enabled = False
        self.carousel.root.enabled = False

    def _logo(self, ui, x, y, scale=1.0):
        Text(parent=ui, text='POKÉMON', position=(x + .004, y - .005, .01), origin=(-.5, 0), scale=4.2 * scale,
             color=GOLD_DARK, **F_TITLE)
        Text(parent=ui, text='POKÉMON', position=(x, y), origin=(-.5, 0), scale=4.2 * scale, color=GOLD, **F_TITLE)
        Text(parent=ui, text='D O M I N I O N', position=(x + .006, y - .075 * scale), origin=(-.5, 0),
             scale=1.9 * scale, color=color.white, **F_BOLD)
        Entity(parent=ui, model='quad', color=GOLD, scale=(.07 * scale, .004), origin=(-.5, 0),
               position=(x + .006, y - .115 * scale))

    def _carousel_screen(self):
        """Carrousel des Pokémon à droite, avec le nom de celui qui passe devant."""
        self.carousel.root.enabled = True
        self.front_label = Entity(parent=self.ui, position=(.36, -.33))
        self.front_name = Text(parent=self.front_label, text='', origin=(0, 0), scale=1.7, **F_BOLD)
        self.front_type = None
        self.front_role = Text(parent=self.front_label, text='', y=-.075, origin=(0, 0), scale=.85, color=DIM,
                               **F_SEMI)
        self._front = None

    def _refresh_front(self):
        sp = self.carousel.front
        if self.front_label is None or sp == self._front:
            return
        self._front = sp
        d = C.SPECIES[sp]
        t = C.TYPES[d['type']]
        self.front_name.text = d['name']
        if self.front_type is not None:
            destroy(self.front_type)
        self.front_type = chip(self.front_label, t['name'].upper(), (0, -.042), t['color'], size=.75)
        self.front_role.text = C.PLAYABLE_ROLE[sp]

    def show_home(self, message=None):
        self._clear_ui()
        ui = self.ui
        self._carousel_screen()
        x = -.78
        self._logo(ui, x, .33)
        Text(parent=ui, text="Bataille d'arènes en 3D  ·  5 contre 5", position=(x + .006, .165), origin=(-.5, 0),
             scale=1.05, color=DIM, **F_SEMI)
        bx = x + .225
        Btn(ui, 'Jouer seul', (bx, .04), self.start_solo, w=.45, h=.085, accent=GOLD, align='left',
            sub='Avec des alliés contrôlés par l\'ordinateur', col=color.rgba(.16, .15, .3, .96))
        Btn(ui, 'Créer une partie à deux', (bx, -.065), self.start_host, w=.45, h=.085,
            accent=C.TEAMS['rouge']['color'], align='left', sub='Invitez un ami avec un code')
        Btn(ui, 'Rejoindre une partie', (bx, -.17), self.show_join, w=.45, h=.085,
            accent=C.TEAMS['bleu']['light'], align='left', sub="Collez le code reçu d'un ami")
        Btn(ui, 'Quitter', (x + .08, -.29), self._quit, w=.16, h=.052, size=.9, col=color.rgba(.12, .12, .18, .9))
        Text(parent=ui, text='ZQSD : bouger   ·   J K L U I : attaques   ·   Espace : esquive', position=(0, -.465),
             origin=(0, 0), scale=.78, color=DIM, **F_SEMI)
        if message:
            m = panel(ui, (bx, .245 - .12), .45, .055, col=color.rgba(.35, .08, .1, .9), edge=color.rgba(1, .5, .5, .4))
            Text(parent=m, text=message, origin=(0, 0), scale=.85, color=color.rgb(1, .85, .82), z=-.01, **F_SEMI)

    def show_join(self, error=None):
        self._clear_ui()
        self.mode = None
        ui = self.ui
        self._carousel_screen()
        x = -.78
        self._logo(ui, x, .38, .7)
        p = panel(ui, (x + .245, -.03), .52, .42)
        Text(parent=p, text='REJOINDRE UNE PARTIE', position=(-.235, .17, -.01), origin=(-.5, 0), scale=1.45,
             color=GOLD, **F_BOLD)
        Text(parent=p, text="Collez le code d'invitation envoyé par votre ami :", position=(-.235, .115, -.01),
             origin=(-.5, 0), scale=.85, color=DIM, **F_SEMI)
        self.code_field = InputField(parent=ui, position=(x + .19, .03), scale=(.35, .065), character_limit=40,
                                     color=color.rgba(0, 0, 0, .55))
        self.code_field.text_field.text_entity.color = color.white
        self.code_field.active = True
        self.code_field.submit_on = ['enter']
        self.code_field.on_submit = self.connect
        Btn(ui, 'Coller', (x + .44, .03), self._paste_code, w=.11, h=.065, size=.85)
        Btn(ui, 'Rejoindre', (x + .37, -.07), self.connect, w=.25, h=.07, accent=OK_GREEN,
            col=color.rgba(.1, .32, .2, .96))
        Btn(ui, 'Retour', (x + .1, -.07), self.back, w=.17, h=.07, size=.95, col=color.rgba(.12, .12, .18, .9))
        self.join_status = Text(parent=ui, text=error or '', position=(x + .245, -.145), origin=(0, 0), scale=.85,
                                color=ERR if error else DIM, **F_SEMI)
        Text(parent=ui, text='Même box / même Wi-Fi : utilisez son code « réseau local ».',
             position=(x + .245, -.205), origin=(0, 0), scale=.72, color=DIM, **F_SEMI)
        text = _paste().strip()
        if re.fullmatch(r'[0-9A-Za-z]{5}-?[0-9A-Za-z]{5}-?[0-9A-Za-z]{4}|[\w.-]+(:\d{2,5})?/\w{4}', text):
            try:                               # un code valide dans le presse-papiers : on le propose
                net.parse_code(text)
                self.code_field.text = text
            except ValueError:
                pass

    def show_room(self):
        self._clear_ui()
        ui = self.ui
        self.previews[0].root.enabled = True
        title = {'solo': 'PARTIE SOLO', 'host': 'PARTIE À DEUX', 'guest': 'PARTIE À DEUX'}[self.mode]
        sub = {'solo': 'Vous et 4 alliés contrôlés par l\'ordinateur contre 5 adversaires',
               'host': 'Vous hébergez la partie', 'guest': 'Vous avez rejoint la partie'}[self.mode]
        Text(parent=ui, text=title, position=(-.8, .44), origin=(-.5, 0), scale=1.9, color=GOLD, **F_BOLD)
        Text(parent=ui, text=sub, position=(-.8, .395), origin=(-.5, 0), scale=.85, color=DIM, **F_SEMI)
        me, other = ('J1', 'J2') if self.mode != 'guest' else ('J2', 'J1')
        self.me_tag, self.other_tag = me, other
        self.me_label = Entity(parent=ui, position=(-.12, -.19))
        self.other_label = Entity(parent=ui, position=(-.56, -.15))
        # invitation (hôte, tant que personne n'a rejoint)
        self.invite = panel(ui, (-.6, .1), .44, .36)
        Text(parent=self.invite, text='INVITEZ UN AMI', position=(0, .14, -.01), origin=(0, 0), scale=1.15,
             color=GOLD, **F_BOLD)
        Text(parent=self.invite, text='Envoyez-lui ce code :', position=(0, .1, -.01), origin=(0, 0), scale=.8,
             color=DIM, **F_SEMI)
        self.code_text = Text(parent=self.invite, text='...', position=(0, .045, -.01), origin=(0, 0), scale=2.4,
                              color=color.white, **F_BOLD)
        light = color.rgba(.2, .22, .4, .97)
        self.copy_btn = Btn(self.invite, 'Copier le code', (-.103, -.025), self._copy_public, w=.195, h=.055,
                            size=.8, accent=GOLD, col=light)
        Btn(self.invite, 'Code local', (.103, -.025), self._copy_lan, w=.195, h=.055, size=.8, col=light)
        self.lan_text = Text(parent=self.invite, text='', position=(0, -.085, -.01), origin=(0, 0), scale=.75,
                             color=DIM, **F_SEMI)
        self.net_status = Text(parent=self.invite, text='', position=(0, -.13, -.01), origin=(0, 0), scale=.68,
                               color=DIM, **F_SEMI)
        self.invite.enabled = self.mode == 'host'
        # fiche du Pokémon choisi
        self.info_panel = panel(ui, (.53, .08), .6, .6)
        self.info = Entity(parent=self.info_panel, z=-.01)
        # cartes de choix
        self.cards = {}
        n = len(C.PLAYABLE)
        w, h, gap = .15, .165, .016
        for i, sp in enumerate(C.PLAYABLE):
            self.cards[sp] = self._card(ui, sp, ((i - (n - 1) / 2) * (w + gap), -.33), w, h)
        # actions
        Btn(ui, 'Retour', (-.75, -.455), self.back, w=.15, h=.05, size=.85, col=color.rgba(.12, .12, .18, .9))
        label = 'LANCER LA PARTIE' if self.mode == 'solo' else 'PRÊT !'
        self.ready_btn = Btn(ui, label, (.66, -.455), self.toggle_ready, w=.3, h=.06, size=1.05,
                             col=color.rgba(.12, .45, .24, .97), accent=OK_GREEN)
        self.status = Text(parent=ui, text='', position=(0, -.455), origin=(0, 0), scale=.85, color=DIM, **F_SEMI)
        self.ping_text = Text(parent=ui, text='', position=(.83, .44), origin=(.5, 0), scale=.8, color=DIM,
                              **F_SEMI)
        self._refresh_room()

    def _card(self, ui, sp, pos, w, h):
        """Carte d'un Pokémon : portrait, nom et type ; cliquer pour le choisir."""
        d = C.SPECIES[sp]
        t = C.TYPES[d['type']]
        card = Entity(parent=ui, position=(pos[0], pos[1], 0))
        card.base_y = pos[1]
        card.border = Entity(parent=card, model=_quad(w + .008, h + .008, .02), scale=(w + .008, h + .008),
                             color=BTN_EDGE, z=.002)
        card.bg = Button(parent=card, scale=(w, h), radius=min(.5, .016 / h), color=BTN,
                         highlight_color=BTN.tint(.1), pressed_color=BTN.tint(-.08),
                         on_click=lambda s=sp: self.choose(s))
        Entity(parent=card, model=_quad(w - .018, h * .6, .012), scale=(w - .018, h * .6), y=h * .15,
               color=lerp(t['dark'], color.black, .25), z=-.005)
        Entity(parent=card, model=_quad(w - .018, .006, .003), scale=(w - .018, .006), y=h * .15 - h * .3 + .003,
               color=t['color'], z=-.006)
        self.portraits.icon(card, sp, scale=h * .62, y=h * .15, z=-.01)
        Text(parent=card, text=d['name'], y=-h * .27, origin=(0, 0), scale=.88, z=-.01, **F_BOLD)
        Text(parent=card, text=t['name'], y=-h * .4, origin=(0, 0), scale=.65, z=-.01, color=t['light'], **F_SEMI)
        card.tag = None
        return card

    def _build_info(self, sp):
        """Fiche du Pokémon choisi : nom, type, rôle, jauges et attaques."""
        destroy(self.info)
        self.info = info = Entity(parent=self.info_panel, z=-.01)
        d = C.SPECIES[sp]
        t = C.TYPES[d['type']]
        x0 = -.265
        Text(parent=info, text=d['name'], position=(x0, .25), origin=(-.5, 0), scale=2.2, **F_BOLD)
        chip(info, t['name'].upper(), (x0 + .06, .195), t['color'], w=.12, size=.78)
        Text(parent=info, text=C.PLAYABLE_ROLE[sp], position=(x0, .145), origin=(-.5, 0), scale=.82, color=DIM,
             **F_SEMI)
        y = .085
        for name, v in _stats(sp):
            Text(parent=info, text=name, position=(x0, y), origin=(-.5, 0), scale=.78, **F_SEMI)
            bw = .38
            Entity(parent=info, model=_quad(bw, .014, .007), scale=(bw, .014), origin=(-.5, 0), position=(x0 + .14, y),
                   color=color.rgba(1, 1, 1, .1))
            Entity(parent=info, model=_quad(bw * v, .014, .007), scale=(bw * v, .014), origin=(-.5, 0),
                   position=(x0 + .14, y, -.001), color=t['light'])
            y -= .037
        y -= .012
        Text(parent=info, text='ATTAQUES', position=(x0, y), origin=(-.5, 0), scale=.85, color=GOLD, **F_BOLD)
        y -= .042
        for mv in C.MOVESETS[sp]:
            k = mv['key'].upper()
            Entity(parent=info, model=_quad(.032, .032, .007), scale=(.032, .032), position=(x0 + .016, y),
                   color=GOLD)
            Text(parent=info, text=k, position=(x0 + .016, y, -.001), origin=(0, 0), scale=.85,
                 color=color.rgb(.12, .1, .05), **F_BOLD)
            Text(parent=info, text=mv['name'], position=(x0 + .045, y), origin=(-.5, 0), scale=.85, **F_SEMI)
            Text(parent=info, text=_move_kind(sp, mv), position=(.265, y), origin=(.5, 0), scale=.72, color=DIM,
                 **F_SEMI)
            y -= .04

    # ================================================================ actions
    def start_solo(self):
        self.mode = 'solo'
        self.show_room()

    def start_host(self):
        try:
            self.host = net.Host()
        except OSError as e:
            self.show_home(f"Impossible d'ouvrir la partie : {e}")
            return
        self.mode = 'host'
        self.show_room()

    def _paste_code(self):
        self.code_field.text = _paste().strip()[:40]

    def connect(self):
        code = self.code_field.text.strip()
        if self.guest is not None:
            self.guest.close()
        self.guest = net.Guest(code)
        if self.guest.state == 'error':
            self._join_msg(self.guest.error, ERR)
            self.guest = None
        else:
            self._join_msg('Connexion...', DIM)

    def _join_msg(self, text, col):
        if getattr(self, 'join_status', None) is not None and self.mode is None:
            self.join_status.text = text
            self.join_status.color = col

    def _copy_public(self):
        code = self.host.public_code if self.host else None
        if code and _copy(code):
            self.game.banner.show('Code copié ! Collez-le à votre ami (Discord, SMS...)', 2.5)

    def _copy_lan(self):
        if self.host and _copy(self.host.lan_code):
            self.game.banner.show('Code réseau local copié (même box / même Wi-Fi)', 2.5)

    def choose(self, species):
        if self.ready['me'] and self.mode != 'solo':
            return                               # on a déjà validé : repasser « pas prêt » pour changer
        self.pick['me'] = species
        if self.mode == 'guest' and self.link:
            self.link.send({'t': 'pick', 'sp': species})
        self._sync()
        self._refresh_room()

    def toggle_ready(self):
        if self.mode == 'solo':
            self._launch([self.pick['me']], 0, 'solo')
            return
        self.ready['me'] = not self.ready['me']
        if self.mode == 'guest' and self.link:
            self.link.send({'t': 'ready', 'v': self.ready['me']})
        self._sync()
        self._refresh_room()

    def back(self):
        self._close_net(notify=True)
        self.mode = None
        self.show_home()

    def _quit(self):
        from ursina import application
        self._close_net(notify=True)
        application.quit()

    def _close_net(self, notify=False):
        if self.link is not None and notify and not self.link.closed:
            self.link.send({'t': 'bye' if self.mode == 'host' else 'leave'})
            self.link.close()                    # laisse partir le message avant de fermer
        if self.host is not None:
            self.host.close()
        if self.guest is not None:
            self.guest.close()
        self.host = self.guest = self.link = None
        self.pick['other'] = None
        self.ready = {'me': False, 'other': False}

    # ================================================================ réseau du salon
    def _sync(self):
        """Hôte : envoie l'état du salon à l'invité."""
        if self.mode == 'host' and self.link is not None and self.link.joined and not self.link.closed:
            self.link.send({'t': 'lobby', 'host': {'sp': self.pick['me'], 'ready': self.ready['me']},
                            'guest': {'sp': self.pick['other'], 'ready': self.ready['other']},
                            'ping': self.ping_ms})
            if self.ready['me'] and self.ready['other'] and self.pick['other']:
                self._host_start()

    def _host_start(self):
        humans = [self.pick['me'], self.pick['other']]
        world = {'tree_spacing': C.QUALITY['tree_spacing'], 'relief': C.QUALITY['relief']}
        self.link.send({'t': 'start', 'humans': humans, 'map': world})
        self._launch(humans, 0, 'host')

    def _launch(self, humans, local, role):
        if self._starting:
            return
        self._starting = True
        setup = {'humans': humans, 'local': local, 'role': role, 'host': self.host, 'link': self.link}
        self.host = self.guest = self.link = None      # la partie prend la main sur la connexion
        self.game.start_match(setup)

    def _poll_host(self):
        h = self.host
        link = h.link
        if link is not self.link:                      # nouvelle connexion (pas encore présentée)
            self.link = link
            self.pick['other'] = None
            self.ready = {'me': False, 'other': False}
            self._refresh_room()
        if self.link is None:
            return
        if not self.link.joined and time.time() - self.link.since > net.JOIN_TIMEOUT:
            self._drop_guest()                          # ne s'est pas présentée : on libère la place
            return
        for kind, msg in self.link.poll():
            if kind == 'lost':
                self.game.banner.show('Le joueur 2 est parti', 2.5, text_color=ERR)
                h.drop_link()
                self.link = None
                self.pick['other'] = None
                self.ready = {'me': False, 'other': False}
                self.ping_ms = None
                self._refresh_room()
                return
            if kind != 'msg':
                continue
            t = msg.get('t')
            if not self.link.joined and t != 'join':
                continue                                # rien n'est accepté avant la présentation
            if t == 'join':
                if self.link.joined:
                    continue
                if not h.check_key(msg.get('key')):
                    self.link.send({'t': 'reject', 'why': "Code d'invitation incorrect : demandez le code à l'hôte."})
                    self._drop_guest()
                    return
                if msg.get('version') != net.game_version():
                    self.link.send({'t': 'reject', 'why': 'Versions du jeu différentes : copiez les mêmes '
                                                          'fichiers chez les deux joueurs.'})
                    self.game.banner.show('Un joueur avec une autre version du jeu a été refusé', 3, text_color=ERR)
                    self._drop_guest()
                    return
                self.link.joined = True
                self.pick['other'] = msg.get('sp') if msg.get('sp') in C.PLAYABLE else 'salameche'
                self.game.banner.show('Le joueur 2 a rejoint la partie !', 2.5, text_color=OK_GREEN)
            elif t == 'pick' and msg.get('sp') in C.PLAYABLE:
                self.pick['other'] = msg['sp']
                self.ready['other'] = False
            elif t == 'ready':
                self.ready['other'] = bool(msg.get('v')) and self.pick['other'] is not None
            elif t == 'pong':
                try:
                    self.ping_ms = int((time.perf_counter() - float(msg.get('c'))) * 1000)
                except (TypeError, ValueError):
                    pass
            elif t == 'leave':
                self.link.close()
                continue
            self._sync()
            if self._starting:
                return
            self._refresh_room()

    def _drop_guest(self):
        """Hôte : ferme la connexion en cours (refusée ou restée muette) et rouvre l'invitation."""
        self.host.drop_link()
        self.link = None
        self.pick['other'] = None
        self.ready = {'me': False, 'other': False}
        self._refresh_room()

    def _poll_guest(self):
        g = self.guest
        if self.link is None:
            if g.state == 'error':
                self._join_msg(g.error, ERR)
                self.guest = None
                return
            if g.state != 'connected':
                return
            self.link = g.link
        for kind, msg in self.link.poll():
            if kind == 'lost':
                self._close_net()
                self.show_home("La connexion avec l'hôte a été perdue.")
                return
            if kind != 'msg':
                continue
            t = msg.get('t')
            if t == 'hello':
                if msg.get('version') != net.game_version():
                    self._close_net()
                    self.show_join("Versions du jeu différentes : copiez les mêmes fichiers chez les deux joueurs.")
                    return
                self.link.send({'t': 'join', 'version': net.game_version(), 'sp': self.pick['me'],
                                'key': g.key})
                self.mode = 'guest'
                self.show_room()
            elif t == 'full':
                self._close_net()
                self.show_join('Cette partie est déjà complète.')
                return
            elif t == 'reject':
                self._close_net()
                self.show_join(str(msg.get('why', 'Connexion refusée.')))
                return
            elif t == 'bye':
                self._close_net()
                self.show_home("L'hôte a fermé la partie.")
                return
            elif t == 'ping':
                self.link.send({'t': 'pong', 'c': msg.get('c')})
            elif t == 'lobby' and self.mode == 'guest':
                hs, gs = msg.get('host') or {}, msg.get('guest') or {}
                self.pick['other'] = hs.get('sp') if hs.get('sp') in C.PLAYABLE else None
                self.ready['other'] = bool(hs.get('ready'))
                self.ready['me'] = bool(gs.get('ready'))
                self.ping_ms = msg.get('ping')
                self._refresh_room()
            elif t == 'start' and self.mode == 'guest':
                humans = [s for s in msg.get('humans', ()) if s in C.PLAYABLE]
                if len(humans) != 2:
                    continue
                for k, v in (msg.get('map') or {}).items():
                    if k in ('tree_spacing', 'relief') and isinstance(v, (int, float)):
                        C.QUALITY[k] = float(v)     # même jungle et même relief que l'hôte
                self._launch(humans, 1, 'client')
                return

    # ================================================================ affichage
    def _player_tag(self, parent, who, sp, ready, you):
        """Étiquette sous un socle : « J1 (vous) · Pikachu » et « PRÊT »."""
        for c in list(parent.children):
            destroy(c)
        name = C.SPECIES[sp]['name'] if sp else '...'
        Text(parent=parent, text=f"{who}{'  (vous)' if you else ''}  ·  {name}", origin=(0, 0), scale=1.0,
             color=OK_GREEN if ready else color.white, **F_BOLD)
        if ready:
            chip(parent, 'PRÊT', (0, -.038), color.rgb(.15, .55, .3), size=.72)

    def _refresh_room(self):
        if self.mode not in ('solo', 'host', 'guest') or self.cards is None:
            return
        me, other = self.pick['me'], self.pick['other']
        self.previews[0].show(me)
        self.previews[1].show(other)
        duo = self.mode != 'solo'
        for sp, card in self.cards.items():
            sel = sp == me
            card.border.color = GOLD if sel else BTN_EDGE
            card.bg.color = color.rgba(.2, .2, .36, .98) if sel else BTN
            card.bg.highlight_color = card.bg.color.tint(.1)
            card.animate_y(card.base_y + (.014 if sel else 0), duration=.12)
            if card.tag is not None:
                destroy(card.tag)
                card.tag = None
            if duo and sp == other:                  # choix de l'autre joueur
                card.tag = chip(card, self.other_tag, (.052, .066), C.TEAMS['rouge']['light'], w=.04,
                                txt_col=color.rgb(.2, .05, .05), size=.7, z=-.03)
        if self._info_species != me:
            self._info_species = me
            self._build_info(me)
        self._player_tag(self.me_label, self.me_tag, me, self.ready['me'] and duo, True)
        if not duo:
            for c in list(self.other_label.children):
                destroy(c)
            self.previews[1].root.enabled = False
            self.status.text = '← →  ou clic : choisir   ·   Entrée : lancer   ·   Échap : retour'
            return
        waiting = self.mode == 'host' and (self.link is None or not self.link.joined)
        self.invite.enabled = waiting
        self.previews[1].root.enabled = not waiting
        self.other_label.enabled = not waiting
        if not waiting:
            self._player_tag(self.other_label, self.other_tag, other, self.ready['other'], False)
        self.ready_btn.set('PAS PRÊT' if self.ready['me'] else 'PRÊT !',
                           color.rgba(.45, .28, .1, .97) if self.ready['me'] else color.rgba(.12, .45, .24, .97))
        if waiting:
            self.status.text = "En attente d'un ami...  Vous pouvez déjà choisir votre Pokémon."
        elif self.ready['me'] and self.ready['other']:
            self.status.text = 'La partie commence !'
        elif self.ready['me']:
            self.status.text = "En attente de l'autre joueur..."
        else:
            self.status.text = 'Choisissez votre Pokémon puis appuyez sur PRÊT.'

    def _refresh_invite(self):
        h = self.host
        if h is None or not self.invite.enabled:
            return
        code = h.public_code
        text = code or '...'
        if self.code_text.text != text:
            self.code_text.text = text
        self.copy_btn.enabled = code is not None
        lan = f'Réseau local : {h.lan_code}'
        if self.lan_text.text != lan:
            self.lan_text.text = lan
        st = h.info['status']
        if self.net_status.text != st:
            self.net_status.text = st
            self.net_status.color = OK_GREEN if h.info['upnp'] else DIM

    # ================================================================ boucle
    def update(self):
        dt = utime.dt
        self.portraits.tick()
        for p in self.previews:
            if p.root.enabled:
                p.update(dt)
        if self.carousel.root.enabled:
            self.carousel.update(dt)
            self._refresh_front()
        self.sparkles.update(dt)
        if self._starting:
            return
        if self.mode == 'host' and self.host is not None:
            self._poll_host()
            if self.host is None:
                return
            self._refresh_invite()
            self._ping_t -= dt
            if self.link is not None and self.link.joined and self._ping_t <= 0:
                self._ping_t = 1.0
                self.link.send({'t': 'ping', 'c': time.perf_counter()})
        elif self.guest is not None:
            self._poll_guest()
        if self.mode in ('host', 'guest') and getattr(self, 'ping_text', None) is not None:
            txt = f'Latence : {self.ping_ms} ms' if self.ping_ms is not None and self.link else ''
            if self.ping_text.text != txt:
                self.ping_text.text = txt

    def input(self, key):
        if self.mode in ('solo', 'host', 'guest') and not self._starting:
            i = C.PLAYABLE.index(self.pick['me'])
            if key in ('left arrow', 'q', 'a'):
                self.choose(C.PLAYABLE[(i - 1) % len(C.PLAYABLE)])
            elif key in ('right arrow', 'd'):
                self.choose(C.PLAYABLE[(i + 1) % len(C.PLAYABLE)])
            elif key == 'enter':
                self.toggle_ready()
            elif key == 'escape':
                self.back()
        elif key == 'escape' and self.mode is None and getattr(self, 'code_field', None) is not None \
                and self.ui is not None and self.code_field.parent is self.ui:
            self.back()

    def close(self):
        """Supprime le salon (la connexion, elle, a été confiée à la partie)."""
        self._close_net()
        self.portraits.dispose()
        self.game.sky.enabled = True
        destroy(self.ui)
        destroy(self.scene)
        destroy(self)
