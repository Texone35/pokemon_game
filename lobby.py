"""Page d'accueil et salon : choix du mode, invitation d'un ami, choix du Pokémon.

Écrans
  'home' : Jouer seul / Créer une partie à deux / Rejoindre une partie
  'join' : l'invité colle le code d'invitation reçu
  'room' : chaque joueur choisit son Pokémon et se déclare prêt ; l'hôte lance la
           partie quand les deux sont prêts (en solo : bouton « Lancer »).

Messages du salon (JSON, voir net.Link) :
  hôte -> invité : hello, lobby (choix et « prêt » des deux joueurs, latence), start, reject, bye
  invité -> hôte : join (version du jeu), pick, ready, pong, leave
"""
import re
import time

from ursina import Button, Entity, InputField, Text, Vec3, camera, color, destroy, time as utime

import config as C
import net
from creatures import Creature
from geometry import flat_circle

GOLD = color.rgb(1, .85, .3)
PANEL = color.rgba(.04, .05, .1, .78)
DIM = color.rgba(1, 1, 1, .7)
OK_GREEN = color.rgb(.45, 1, .5)
ERR = color.rgb(1, .55, .5)


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


def _button(parent, text, pos, on_click, w=.34, h=.065, col=color.rgba(.15, .2, .35, .95), scale=1.0):
    b = Button(parent=parent, text=text, position=pos, scale=(w, h), color=col,
               highlight_color=col.tint(.18), pressed_color=col.tint(-.1), on_click=on_click)
    b.text_entity.scale *= scale
    return b


class Preview:
    """Pokémon 3D qui tourne sur un socle (dans la scène, devant la caméra du salon)."""

    def __init__(self, root, x, ring_col):
        self.root = Entity(parent=root, position=(x, 0, 0))
        flat_circle(self.root, 1.35, color.rgba(0, 0, 0, .35), y=.01)
        flat_circle(self.root, 1.2, ring_col, y=.02)
        flat_circle(self.root, 1.0, color.rgb(.93, .93, .88), y=.03)
        self.species = None
        self.creature = None
        self.t = 0

    def show(self, species):
        if species == self.species:
            return
        self.species = species
        if self.creature is not None:
            destroy(self.creature)
            self.creature = None
        if species:
            s = C.SPECIES[species]['scale'] * 1.1
            self.creature = Creature(species, parent=self.root, scale=s, y=.03)
            self.creature.rotation_y = 200
            self.creature.pivot.scale = .01
            self.creature.pivot.animate_scale(s, duration=.25)

    def update(self, dt):
        if self.creature is not None:
            self.creature.rotation_y += dt * 30
            self.creature.animate(dt)


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
        # petite scène 3D : sol, socles et Pokémon. Elle n'apparaît qu'une fois la carte
        # d'ombres figée (vide) : le salon ne recalcule pas les ombres à chaque image.
        self.scene = Entity(enabled=False)
        flat_circle(self.scene, 60, color.rgb(.36, .6, .3), y=-.01)
        flat_circle(self.scene, 9, color.rgb(.42, .68, .34), y=0)
        self.previews = [Preview(self.scene, -3.3, C.TEAMS['rouge']['color']),
                         Preview(self.scene, 3.3, C.TEAMS['rouge']['light'])]
        self.hero = Preview(self.scene, 0, GOLD)
        self._frozen = False
        camera.position = Vec3(0, 1.2, -17)
        camera.rotation = Vec3(3, 0, 0)
        camera.fov = 50
        self.show_home(message)

    # ================================================================ écrans
    def _clear_ui(self):
        if self.ui is not None:
            destroy(self.ui)
        self.ui = Entity(parent=camera.ui)
        for p in self.previews + [self.hero]:
            p.show(None)
            p.root.enabled = False

    def show_home(self, message=None):
        self._clear_ui()
        ui = self.ui
        self.hero.root.enabled = True
        self.hero.show('pikachu')
        Text(parent=ui, text='POKÉMON DOMINION', position=(0, .42), origin=(0, 0), scale=3.2, color=GOLD)
        Text(parent=ui, text='Bataille d\'arènes en 3D', position=(0, .355), origin=(0, 0), scale=1.2, color=DIM)
        _button(ui, 'Jouer seul', (0, -.14), self.start_solo, w=.44)
        _button(ui, 'Créer une partie à deux', (0, -.225), self.start_host, w=.44,
                col=color.rgba(.55, .18, .15, .95))
        _button(ui, 'Rejoindre une partie', (0, -.31), self.show_join, w=.44, col=color.rgba(.15, .35, .55, .95))
        _button(ui, 'Quitter', (0, -.41), self._quit, w=.2, h=.05, col=color.rgba(.2, .2, .22, .9), scale=.9)
        if message:
            Text(parent=ui, text=message, position=(0, .27), origin=(0, 0), scale=1, color=ERR)

    def show_join(self, error=None):
        self._clear_ui()
        self.mode = None
        ui = self.ui
        self.hero.root.enabled = True
        self.hero.show('carapuce')
        Text(parent=ui, text='REJOINDRE UNE PARTIE', position=(0, .41), origin=(0, 0), scale=2.2, color=GOLD)
        Entity(parent=ui, model='quad', color=PANEL, scale=(.9, .36), position=(0, -.24, .01))
        Text(parent=ui, text="Collez le code d'invitation envoyé par votre ami :", position=(0, -.1), origin=(0, 0),
             scale=1.05)
        self.code_field = InputField(parent=ui, position=(-.07, -.18), scale=(.5, .06), character_limit=40,
                                     color=color.rgba(0, 0, 0, .7))
        self.code_field.text_field.text_entity.color = color.white
        self.code_field.active = True
        self.code_field.submit_on = ['enter']
        self.code_field.on_submit = self.connect
        _button(ui, 'Coller', (.28, -.18), self._paste_code, w=.13, h=.06, col=color.rgba(.25, .25, .3, .95), scale=.9)
        _button(ui, 'Rejoindre', (.1, -.29), self.connect, w=.26, col=color.rgba(.15, .45, .25, .95))
        _button(ui, 'Retour', (-.2, -.29), self.back, w=.2, col=color.rgba(.25, .25, .3, .95))
        self.join_status = Text(parent=ui, text=error or '', position=(0, -.37), origin=(0, 0), scale=.95,
                                color=ERR if error else DIM)
        Text(parent=ui, text='Même réseau Wi-Fi/box : utilisez son code « réseau local ».', position=(0, -.46),
             origin=(0, 0), scale=.8, color=DIM)
        text = _paste().strip()
        if re.fullmatch(r'[0-9A-Za-z]{5}-?[0-9A-Za-z]{5}|[\w.-]+:\d{2,5}', text):
            try:                               # un code valide dans le presse-papiers : on le propose
                net.parse_code(text)
                self.code_field.text = text
            except ValueError:
                pass

    def show_room(self):
        self._clear_ui()
        ui = self.ui
        for p in self.previews:
            p.root.enabled = True
        title = {'solo': 'PARTIE SOLO', 'host': 'PARTIE À DEUX  -  vous hébergez',
                 'guest': 'PARTIE À DEUX  -  vous avez rejoint'}[self.mode]
        Text(parent=ui, text=title, position=(0, .45), origin=(0, 0), scale=1.8, color=GOLD)
        me, other = ('J1', 'J2') if self.mode != 'guest' else ('J2', 'J1')
        self.me_label = Text(parent=ui, text='', position=(-.36, -.065), origin=(0, 0), scale=1.15)
        self.other_label = Text(parent=ui, text='', position=(.36, -.065), origin=(0, 0), scale=1.15)
        self.me_tag, self.other_tag = me, other
        # invitation (hôte, tant que personne n'a rejoint)
        self.invite = Entity(parent=ui, position=(.4, .15))
        Entity(parent=self.invite, model='quad', color=PANEL, scale=(.56, .42), z=.01)
        Text(parent=self.invite, text='Invitez un ami : envoyez-lui ce code', y=.17, origin=(0, 0), scale=.95)
        self.code_text = Text(parent=self.invite, text='...', y=.105, origin=(0, 0), scale=2.4, color=GOLD)
        self.copy_btn = _button(self.invite, 'Copier le code', (-.12, .035), self._copy_public, w=.22, h=.05,
                                col=color.rgba(.55, .18, .15, .95), scale=.85)
        _button(self.invite, 'Copier code local', (.13, .035), self._copy_lan, w=.22, h=.05,
                col=color.rgba(.25, .25, .3, .95), scale=.8)
        self.lan_text = Text(parent=self.invite, text='', y=-.03, origin=(0, 0), scale=.8, color=DIM)
        self.net_status = Text(parent=self.invite, text='', y=-.1, origin=(0, 0), scale=.72, color=DIM)
        self.invite.enabled = self.mode == 'host'
        # choix du Pokémon
        Text(parent=ui, text='Choisissez votre Pokémon  (flèches ou clic)', position=(0, -.115), origin=(0, 0),
             scale=.95, color=DIM)
        self.cards = {}
        n = len(C.PLAYABLE)
        for i, sp in enumerate(C.PLAYABLE):
            t = C.TYPES[C.SPECIES[sp]['type']]
            x = (i - (n - 1) / 2) * .2
            b = _button(ui, C.SPECIES[sp]['name'], (x, -.18), lambda s=sp: self.choose(s), w=.185, h=.07,
                        col=color.rgba(.1, .1, .16, .95), scale=.95)
            Entity(parent=b, model='quad', color=t['color'], scale=(1, .12), y=-.44, z=-.01)
            self.cards[sp] = b
        self.desc = Text(parent=ui, text='', position=(0, -.25), origin=(0, 0), scale=.9)
        self.moves_text = Text(parent=ui, text='', position=(0, -.29), origin=(0, 0), scale=.78, color=DIM)
        # actions
        _button(ui, 'Retour', (-.62, -.4), self.back, w=.18, h=.06, col=color.rgba(.25, .25, .3, .95))
        label = 'LANCER LA PARTIE' if self.mode == 'solo' else 'PRÊT !'
        self.ready_btn = _button(ui, label, (0, -.38), self.toggle_ready, w=.36, h=.08,
                                 col=color.rgba(.15, .5, .25, .95), scale=1.2)
        self.status = Text(parent=ui, text='', position=(0, -.46), origin=(0, 0), scale=.9, color=DIM)
        self.ping_text = Text(parent=ui, text='', position=(.62, -.4), origin=(0, 0), scale=.85, color=DIM)
        self._refresh_room()

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
        if self.mode == 'host' and self.link is not None and not self.link.closed:
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
        if link is not self.link:                      # nouvel invité
            self.link = link
            self.pick['other'] = None
            self.ready = {'me': False, 'other': False}
            self._refresh_room()
        if self.link is None:
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
            if t == 'join':
                if msg.get('version') != net.game_version():
                    self.link.send({'t': 'reject', 'why': 'Versions du jeu différentes : copiez les mêmes '
                                                          'fichiers chez les deux joueurs.'})
                    self.game.banner.show('Un joueur avec une autre version du jeu a été refusé', 3, text_color=ERR)
                    continue
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
                self.link.send({'t': 'join', 'version': net.game_version(), 'sp': self.pick['me']})
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
    def _refresh_room(self):
        if self.mode not in ('solo', 'host', 'guest') or getattr(self, 'cards', None) is None:
            return
        me, other = self.pick['me'], self.pick['other']
        self.previews[0].show(me)
        self.previews[1].show(other)
        for sp, b in self.cards.items():
            b.color = color.rgba(.85, .65, .15, .95) if sp == me else color.rgba(.1, .1, .16, .95)
            b.highlight_color = b.color.tint(.15)
        d = C.SPECIES[me]
        self.desc.text = f"{d['name']}  ({C.TYPES[d['type']]['name']})  -  {C.PLAYABLE_ROLE[me]}"
        self.moves_text.text = '    '.join(f"{mv['key'].upper()} : {mv['name']}" for mv in C.MOVESETS[me])

        def tag(who, sp, ready, you):
            name = C.SPECIES[sp]['name'] if sp else '...'
            mark = '   PRÊT' if ready else ''
            return f"{who}{' (vous)' if you else ''}  -  {name}{mark}"
        self.me_label.text = tag(self.me_tag, me, self.ready['me'] and self.mode != 'solo', True)
        self.me_label.color = OK_GREEN if self.ready['me'] and self.mode != 'solo' else color.white
        if self.mode == 'solo':
            self.other_label.text = ''
            self.previews[1].root.enabled = False
        else:
            waiting = self.mode == 'host' and self.link is None
            self.invite.enabled = waiting
            self.previews[1].root.enabled = not waiting
            self.other_label.text = '' if waiting else tag(self.other_tag, other, self.ready['other'], False)
            self.other_label.color = OK_GREEN if self.ready['other'] else color.white
            self.ready_btn.text = 'PAS PRÊT' if self.ready['me'] else 'PRÊT !'
            self.ready_btn.color = color.rgba(.5, .3, .1, .95) if self.ready['me'] else color.rgba(.15, .5, .25, .95)
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
        if not self._frozen:                  # 1re image rendue : on fige la carte d'ombres vide
            from geometry import freeze_shadows
            self._frozen = freeze_shadows(self.game.sun)
            self.scene.enabled = self._frozen
        for p in self.previews + [self.hero]:
            if p.root.enabled:
                p.update(dt)
        if self._starting:
            return
        if self.mode == 'host' and self.host is not None:
            self._poll_host()
            if self.host is None:
                return
            self._refresh_invite()
            self._ping_t -= dt
            if self.link is not None and self._ping_t <= 0:
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
        destroy(self.ui)
        destroy(self.scene)
        destroy(self)

