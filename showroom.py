"""Showroom du décor : visite rapide des ensembles 3D (arbres, reliefs, ponts, arènes...).

Lancer :  python showroom.py            (visite libre)
          python showroom.py --galerie  (chaque élément du décor posé à la suite sur un terrain vide)
          python showroom.py --shots    (enregistre une image par vue dans captures/ puis quitte)

Touches :
  Tab / N  vue suivante        B        vue précédente       1-9   aller à la vue n°
  clic droit + souris : tourner        molette : zoom         ZQSD / WASD : déplacer
  flèches : tourner / incliner         P : capture d'écran    F5 : reconstruire (après modif du code)
  G : carte <-> galerie              H : cacher l'aide
"""
import importlib
import math
import os
import sys
import time

from panda3d.core import Filename
from ursina import (Entity, Sky, Text, Ursina, Vec3, application, camera, color, destroy, held_keys, mouse,
                    window)

from game import config as C

SHOTS = '--shots' in sys.argv
GALLERY = '--galerie' in sys.argv
app = Ursina(title='Showroom décor', size=C.WINDOW_SIZE, borderless=False, development_mode=False, vsync=True)

from ursina import time as utime                                                                # noqa: E402

from game.world import fx                                                                       # noqa: E402
from game.world.geometry import (freeze_shadows, set_environment, setup_sun, unfreeze_shadows,  # noqa: E402
                                 update_camera_uniform)

SKY = (.55, .72, .95, 1)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'captures')
# modules du décor rechargés par F5 (dans l'ordre des dépendances)
RELOAD = ['game.world.biomes', 'game.world.emblems', 'game.world.water', 'game.world.stadium',
          'game.world.arenas', 'game.world.landmarks', 'gallery']


def build_views(st):
    """Liste de (nom, x, z, lacet, inclinaison, distance) calculée à partir du décor réel."""
    from game.world import biomes
    from game.world.stadium import LANES, RIVERS, polyline_dist
    views = [("Vue d'ensemble", 0, -10, 0, 58, 250),
             ('Bas de la carte : bases et arènes du sud', 0, -75, 0, 62, 120)]
    # ponts : points où une voie traverse la rivière
    spots = []
    for pts, _w in LANES:
        for piece in st._lane_pieces(pts):
            for (ax, az), (bx, bz) in zip(piece, piece[1:]):
                L = math.hypot(bx - ax, bz - az)
                for k in range(int(L / 1.5) + 1):
                    x, z = ax + (bx - ax) * k * 1.5 / L, az + (bz - az) * k * 1.5 / L
                    if math.hypot(x, z) > C.PIT_RADIUS + 1.5 and \
                            any(polyline_dist(x, z, rp) < rw / 2 for rp, rw in RIVERS) and \
                            all(math.hypot(x - sx, z - sz) > 20 for sx, sz, _ in spots):
                        spots.append((x, z, math.degrees(math.atan2(bx - ax, bz - az))))
    for i, (x, z, yaw) in enumerate(spots[:3]):
        views.append((f'Pont {i + 1}', x, z, yaw + 90, 48, 22))   # regard le long de la rivière
    # jungle : un échantillon de chaque biome, au bord d'un massif
    for k, bk in enumerate(biomes.KEYS):
        best = None
        for gx in range(-110, 111, 4):
            for gz in range(-110, 111, 4):
                if math.hypot(gx, gz) > C.FIELD_RADIUS - 8 or st.landmarks.reserved(gx, gz):
                    continue
                w = biomes.weights_np(gx, gz)
                if int(w.argmax()) != k or float(w.max()) < .85:
                    continue
                d = st.wall_dist(gx, gz)
                if 3 < d < 9 and (best is None or d > best[0]):
                    best = (d, gx, gz)
        if best:
            _, x, z = best
            views.append((f'Jungle - biome {bk}', x, z, math.degrees(math.atan2(x, z)) + 180, 30, 26))
    # grands décors (volcan, cascades, arbre millénaire, tour Tesla, ruines, arches...)
    seen = set()
    for kind, x, z, r, data in st.landmarks.items:
        if kind in seen:
            continue
        seen.add(kind)
        yaw = data['side'] + 180 if 'side' in data else math.degrees(math.atan2(x, z))   # face à la chute, sinon depuis le terrain
        views.append((f'Décor - {kind}', x, z, yaw, 34, max(24, r * 4)))
    for a in C.ARENAS:
        views.append((a['name'], a['pos'][0], a['pos'][1], 0, 42, 48))
    for t in C.TEAMS.values():
        views.append((f'Base {t["name"]}', t['base'][0], t['base'][1], 0, 40, 34))
    views.append(('Boss Pit', 0, 0, 0, 45, 44))
    for camp in C.CAMPS[:3:2]:
        views.append((f'Camp {camp.get("buff", "")}', camp['pos'][0], camp['pos'][1], 30, 35, 22))
    return views


class Showroom(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgba(*SKY)
        window.exit_button.enabled = False
        window.fps_counter.enabled = True
        Sky(texture='sky_default')
        set_environment(fog_color=SKY, fog_range=(140, 420))
        self.sun = setup_sun(resolution=C.QUALITY['shadow_resolution'])
        camera.fov = 60
        self.help = Text(parent=camera.ui, position=window.top_left + Vec3(.02, -.02, 0), scale=.9,
                         color=color.white, background=True)
        self.root = None
        self.gallery = GALLERY
        self.i = 0
        self.shot_wait = 0
        self.build()
        if SHOTS:
            os.makedirs(OUT, exist_ok=True)
            self.help.enabled = False

    def build(self):
        from game.world.stadium import Stadium
        if self.root is not None:
            destroy(self.root)
        unfreeze_shadows(self.sun)
        t0 = time.time()
        self.root = Entity()
        if self.gallery:
            from gallery import Gallery
            self.st = Gallery(self.root)
        else:
            self.st = Stadium(self.root)
            self.st.vortex.show()
        fx.PARTICLES = self.particles = fx.Particles(self.root)
        self.build_time = time.time() - t0
        self.views = self.st.views() if self.gallery else build_views(self.st)
        self.i = min(self.i, len(self.views) - 1)
        self.freeze_in = 4                      # calcule la carte d'ombres puis la fige (comme en partie)
        self.go(self.i)

    def go(self, i):
        self.i = i % len(self.views)
        _name, x, z, yaw, pitch, dist = self.views[self.i]
        self.target = Vec3(x, self.st.ground_y(x, z) + 1.5, z)
        self.yaw, self.pitch, self.dist = yaw, pitch, dist
        name = self.views[self.i][0]
        self.help.text = (f'[{self.i + 1}/{len(self.views)}] {name}   (construit en {self.build_time:.1f} s)\n'
                          'Tab/N suivante  B précédente  1-9 aller  |  clic droit: tourner  molette: zoom  '
                          'ZQSD: déplacer\nP: capture  F5: reconstruire  H: cacher')

    def place_camera(self):
        camera.rotation = Vec3(self.pitch, self.yaw, 0)
        pos = self.target - camera.forward * self.dist
        pos.y = max(pos.y, self.st.ground_y(pos.x, pos.z) + 4)       # jamais sous le relief
        camera.position = pos

    def capture(self):
        os.makedirs(OUT, exist_ok=True)
        name = f'{"galerie_" if self.gallery else ""}{self.i + 1:02d}_{self.views[self.i][0]}'
        safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in name)
        path = os.path.join(OUT, safe + '.png')
        application.base.win.save_screenshot(Filename.from_os_specific(path))
        print('capture :', path)

    def input(self, key):
        if key in ('tab', 'n'):
            self.go(self.i + 1)
        elif key == 'b':
            self.go(self.i - 1)
        elif key.isdigit() and key != '0':
            self.go(int(key) - 1)
        elif key == 'scroll up':
            self.dist = max(4, self.dist * .88)
        elif key == 'scroll down':
            self.dist = min(400, self.dist * 1.14)
        elif key == 'p':
            self.capture()
        elif key == 'g':
            self.gallery = not self.gallery
            self.i = 0
            self.build()
        elif key == 'h':
            self.help.enabled = not self.help.enabled
        elif key == 'f5':
            for m in RELOAD:
                if m in sys.modules:
                    importlib.reload(sys.modules[m])
            self.build()
        elif key == 'escape':
            application.quit()

    def update(self):
        dt = min(utime.dt, .05)
        if mouse.right:
            self.yaw += mouse.velocity[0] * 200
            self.pitch = max(5, min(89, self.pitch - mouse.velocity[1] * 200))
        self.yaw += (held_keys['right arrow'] - held_keys['left arrow']) * 70 * dt
        self.pitch = max(5, min(89, self.pitch + (held_keys['up arrow'] - held_keys['down arrow']) * 40 * dt))
        fwd = Vec3(math.sin(math.radians(self.yaw)), 0, math.cos(math.radians(self.yaw)))
        right = Vec3(fwd.z, 0, -fwd.x)
        move = fwd * (held_keys['w'] + held_keys['z'] - held_keys['s']) + \
            right * (held_keys['d'] - held_keys['a'] - held_keys['q'])
        self.target += move * max(8, self.dist * .8) * dt
        self.place_camera()
        update_camera_uniform()
        self.st.update(dt, self.target)
        if self.freeze_in:
            self.freeze_in -= 1
            if not self.freeze_in:
                freeze_shadows(self.sun)
        if SHOTS:                               # visite automatique : une image par vue
            self.shot_wait += 1
            if self.shot_wait == 12:
                self.capture()
            elif self.shot_wait > 14:
                self.shot_wait = 0
                if self.i + 1 >= len(self.views):
                    application.quit()
                else:
                    self.go(self.i + 1)


Showroom()
app.run()
