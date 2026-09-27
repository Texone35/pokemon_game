"""Monde ouvert : île ronde, 5 arènes en pentagone reliées par des chemins."""
import math
import random

from ursina import (Entity, Text, Vec3, Vec4, camera, color, held_keys, lerp, mouse, time)

import config as C
from creatures import Creature
from emblems import add_emblem
from geometry import MeshBuilder

GRASS = color.rgb(.42, .72, .32)
PATH = color.rgb(.86, .76, .55)
STONE = color.rgb(.78, .76, .72)
WHITE_BALL = color.rgb(.97, .97, .97)


def _seg_dist(px, pz, ax, az, bx, bz):
    """Distance d'un point au segment [A, B] (plan XZ)."""
    dx, dz = bx - ax, bz - az
    L2 = dx * dx + dz * dz
    t = 0 if L2 == 0 else max(0, min(1, ((px - ax) * dx + (pz - az) * dz) / L2))
    cx, cz = ax + dx * t, az + dz * t
    return math.hypot(px - cx, pz - cz)


class Overworld(Entity):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.rng = random.Random(7)
        self.arenas = []
        self.segments = []      # chemins (pour éviter d'y planter des arbres)
        self.obstacles = []     # (x, z, rayon) : arbres, fontaine...

        self._layout_arenas()
        self._build_ground()
        self._build_paths()
        self._build_plaza()
        self._build_arenas()
        self._build_nature()

        self.player = Creature('pikachu', parent=self, position=(0, 0, -11))
        self.player.rotation_y = 180
        self.cam_yaw = 0.0
        self.cam_pitch = 26.0
        self.cam_dist = 12.0
        self.near_arena = None
        self._t = 0

        self._build_ui()
        self.snap_camera()

    # ================================================================ layout
    def _layout_arenas(self):
        R = C.ARENA_RING_RADIUS
        for k, type_key in enumerate(C.TYPE_ORDER):
            heading = math.radians(72 * k)          # 0 = nord (+z), sens horaire
            pos = Vec3(math.sin(heading) * R, 0, math.cos(heading) * R)
            to_centre = -pos.normalized()
            door = pos + to_centre * (C.ARENA_BUILDING_RADIUS + .6)
            self.arenas.append({'type': type_key, 'pos': pos, 'dir': to_centre, 'door': door,
                                'heading': 72 * k, 'beaten': False})

    # ================================================================ build
    def _build_ground(self):
        W = C.WORLD_RADIUS
        b = MeshBuilder()
        b.add('disc', (0, -.5, 0), (W * 2, 1, W * 2), col=GRASS)
        b.add('disc', (0, -.55, 0), (W * 2 + 8, 1, W * 2 + 8), col=color.rgb(.93, .86, .62))
        # quelques zones d'herbe plus sombre pour casser l'uniformité
        for _ in range(26):
            a, r = self.rng.uniform(0, math.tau), self.rng.uniform(12, W - 8)
            s = self.rng.uniform(6, 14)
            b.add('disc', (math.sin(a) * r, .005, math.cos(a) * r), (s, .01, s * .8),
                  rot=(0, self.rng.uniform(0, 180), 0), col=color.rgb(.37, .66, .29))
        b.entity(parent=self)
        sea = MeshBuilder().add('disc', (0, -.9, 0), (900, 1, 900), col=color.rgb(.2, .55, .85))
        sea.entity(parent=self, emissive=.35)

    def _build_paths(self):
        b = MeshBuilder()
        BR = C.ARENA_BUILDING_RADIUS
        n = len(self.arenas)

        def road(a, bpos, width=3.6):
            d = bpos - a
            length = d.length()
            mid = (a + bpos) / 2
            yaw = math.degrees(math.atan2(d.x, d.z))
            b.add('box', (mid.x, .02, mid.z), (width, .06, length), rot=(0, yaw, 0), col=PATH)
            b.add('disc', (a.x, .021, a.z), (width, .06, width), col=PATH)
            self.segments.append((a.x, a.z, bpos.x, bpos.z))

        # côtés du pentagone : chaque arène est reliée à ses deux voisines
        for i in range(n):
            A, B = self.arenas[i], self.arenas[(i + 1) % n]
            d = (B['pos'] - A['pos']).normalized()
            road(A['pos'] + d * (BR + 1), B['pos'] - d * (BR + 1))
        # routes depuis la place centrale jusqu'aux portes
        for a in self.arenas:
            road(a['dir'] * -8.5, a['door'] + a['dir'] * .5, width=3.0)
        b.entity(parent=self)

    def _build_plaza(self):
        b = MeshBuilder()
        b.add('disc', (0, .03, 0), (18, .06, 18), col=STONE)
        b.add('ring_thin', (0, .05, 0), (18.6, .1, 18.6), col=color.rgb(.6, .58, .55))
        # fontaine surmontée d'une Poké Ball
        b.add('ring', (0, .45, 0), (6.4, .9, 6.4), col=color.rgb(.7, .7, .74))
        b.add('disc', (0, .6, 0), (5.7, .05, 5.7), col=color.rgb(.35, .7, .95))
        b.add('cyl', (0, 1.4, 0), (.9, 2.8, .9), col=color.rgb(.7, .7, .74))
        by = 3.9
        b.add('dome', (0, by, 0), (2.2, 2.2, 2.2), col=color.rgb(.92, .15, .15))
        b.add('dome', (0, by, 0), (2.2, 2.2, 2.2), rot=(180, 0, 0), col=WHITE_BALL)
        b.add('cyl_hi', (0, by, 0), (2.24, .16, 2.24), col=color.rgb(.1, .1, .1))
        b.add('cyl', (0, by, 1.06), (.6, .12, .6), rot=(90, 0, 0), col=color.rgb(.1, .1, .1))
        b.add('cyl', (0, by, 1.1), (.4, .12, .4), rot=(90, 0, 0), col=WHITE_BALL)
        self.obstacles.append((0, 0, 3.6))
        # bancs et lampadaires autour de la place
        for i in range(10):
            a = math.radians(i * 36 + 18)
            x, z = math.sin(a) * 8.2, math.cos(a) * 8.2
            b.add('cyl6', (x, 1.5, z), (.18, 3, .18), col=color.rgb(.25, .25, .28))
            b.add('sphere', (x, 3.1, z), .45, col=color.rgb(1, .95, .7))
        b.entity(parent=self)

    def _build_arenas(self):
        BR = C.ARENA_BUILDING_RADIUS
        for a in self.arenas:
            t = C.TYPES[a['type']]
            b = MeshBuilder()
            p = a['pos']
            b.add('disc', (p.x, .01, p.z), ((BR + 7) * 2, .02, (BR + 7) * 2), col=t['floor'])
            b.add('cyl_hi', (p.x, .3, p.z), ((BR + 1.3) * 2, .6, (BR + 1.3) * 2), col=STONE)
            b.add('cyl_hi', (p.x, 2.6, p.z), (BR * 2, 4.2, BR * 2), col=t['color'])
            b.add('cyl_hi', (p.x, 4.8, p.z), (BR * 2 + .5, .5, BR * 2 + .5), col=t['dark'])
            b.add('dome', (p.x, 5.0, p.z), (BR * 2, BR * 1.5, BR * 2), col=t['light'])
            for i in range(12):
                ang = math.radians(i * 30 + 15)
                cx, cz = p.x + math.sin(ang) * (BR + .35), p.z + math.cos(ang) * (BR + .35)
                b.add('cyl', (cx, 2.6, cz), (.55, 4.2, .55), col=color.rgb(.95, .95, .92))
            # porte orientée vers le centre de l'île
            yaw = math.degrees(math.atan2(a['dir'].x, a['dir'].z))
            d = a['dir']
            fx = p + d * (BR + .15)
            b.add('box', (fx.x, 1.8, fx.z), (3.4, 3.6, .5), rot=(0, yaw, 0), col=color.rgb(.12, .1, .12))
            b.add('box', (fx.x, 3.9, fx.z), (4.4, .6, .8), rot=(0, yaw, 0), col=t['dark'])
            side = Vec3(d.z, 0, -d.x)
            for s in (-1, 1):
                q = fx + side * 2.0 * s
                b.add('box', (q.x, 1.9, q.z), (.6, 3.8, .9), rot=(0, yaw, 0), col=t['dark'])
            # petit logo au-dessus de la porte
            add_emblem(b, a['type'], (fx.x + d.x * .3, 5.6, fx.z + d.z * .3), .7)
            self._arena_decor(b, a['type'], p, a['dir'])
            b.entity(parent=self)

            emb = MeshBuilder()
            add_emblem(emb, a['type'], (0, 0, 0), 3.0)
            a['emblem'] = emb.entity(parent=self, position=(p.x, 17, p.z), emissive=.55)
            a['label'] = Text(parent=self, text=f"ARÈNE {t['name'].upper()}", position=(p.x, 23, p.z),
                              billboard=True, scale=90, origin=(0, 0), color=t['light'])
            a['crown'] = None

    def _arena_decor(self, b, type_key, p, d):
        r = self.rng
        BR = C.ARENA_BUILDING_RADIUS
        spots = []
        for _ in range(26):
            ang = r.uniform(0, math.tau)
            rad = r.uniform(BR + 2.5, BR + 7)
            x, z = p.x + math.sin(ang) * rad, p.z + math.cos(ang) * rad
            # garder libre l'entrée (côté centre)
            if (Vec3(x, 0, z) - p).normalized().dot(d) > .75:
                continue
            spots.append((x, z))
        for x, z in spots:
            s = r.uniform(.6, 1.3)
            if type_key == 'feu':
                if r.random() < .5:
                    b.add('disc', (x, .04, z), (2.2 * s, .03, 1.6 * s), col=color.rgb(1, .45, .05))
                else:
                    b.add('cone6', (x, .7 * s, z), (1.2 * s, 1.4 * s, 1.2 * s), col=color.rgb(.25, .18, .16))
            elif type_key == 'eau':
                if r.random() < .5:
                    b.add('disc', (x, .04, z), (2.6 * s, .03, 2.2 * s), col=color.rgb(.25, .6, .95))
                else:
                    for k in range(3):
                        b.add('cyl6', (x + k * .2, .6 * s, z), (.08, 1.2 * s, .08), col=color.rgb(.3, .55, .2))
            elif type_key == 'plante':
                b.add('sphere', (x, .5 * s, z), (1.4 * s, 1 * s, 1.4 * s), col=color.rgb(.2, .55, .2))
                b.add('sphere', (x, .9 * s, z), .3, col=r.choice([color.rgb(1, .4, .6), color.rgb(1, .9, .3), color.white]))
            elif type_key == 'roche':
                b.add('sphere', (x, .4 * s, z), (1.6 * s, 1.1 * s, 1.3 * s), rot=(0, r.uniform(0, 180), 0),
                      col=color.rgb(.55, .5, .45))
            elif type_key == 'glace':
                b.add('cone6', (x, .9 * s, z), (.6 * s, 1.8 * s, .6 * s), rot=(r.uniform(-15, 15), 0, r.uniform(-15, 15)),
                      col=color.rgb(.7, .93, 1))
            self.obstacles.append((x, z, .9 * s))

    def _build_nature(self):
        b = MeshBuilder()
        W = C.WORLD_RADIUS
        placed = 0
        tries = 0
        while placed < C.TREE_COUNT and tries < 6000:
            tries += 1
            ang = self.rng.uniform(0, math.tau)
            rad = math.sqrt(self.rng.uniform(.03, 1)) * (W - 2.5)
            x, z = math.sin(ang) * rad, math.cos(ang) * rad
            if rad < 24:   # grande clairière autour de la place centrale
                continue
            if any(_seg_dist(x, z, *s) < 4.5 for s in self.segments):
                continue
            if any(math.hypot(x - a['pos'].x, z - a['pos'].z) < C.ARENA_BUILDING_RADIUS + 8.5 for a in self.arenas):
                continue
            if any(math.hypot(x - ox, z - oz) < orad + 1.6 for ox, oz, orad in self.obstacles):
                continue
            s = self.rng.uniform(.8, 1.4)
            if self.rng.random() < .55:   # sapin
                b.add('cyl6', (x, .8 * s, z), (.45 * s, 1.6 * s, .45 * s), col=color.rgb(.45, .3, .18))
                g = color.rgb(.13, .45 + self.rng.uniform(-.06, .06), .25)
                b.add('cone', (x, 2.4 * s, z), (2.6 * s, 2.6 * s, 2.6 * s), col=g)
                b.add('cone', (x, 3.7 * s, z), (1.9 * s, 2.2 * s, 1.9 * s), col=g)
            else:                          # feuillu
                b.add('cyl6', (x, 1.0 * s, z), (.5 * s, 2 * s, .5 * s), col=color.rgb(.5, .34, .2))
                g = color.rgb(.25, .62 + self.rng.uniform(-.08, .06), .22)
                b.add('sphere', (x, 2.9 * s, z), (2.8 * s, 2.4 * s, 2.8 * s), col=g)
                b.add('sphere', (x + .6 * s, 2.5 * s, z + .3 * s), (1.6 * s, 1.4 * s, 1.6 * s), col=g)
            self.obstacles.append((x, z, .75 * s))
            placed += 1
        # fleurs et petits rochers (sans collision)
        for _ in range(260):
            ang = self.rng.uniform(0, math.tau)
            rad = self.rng.uniform(10, W - 2)
            x, z = math.sin(ang) * rad, math.cos(ang) * rad
            if self.rng.random() < .8:
                c = self.rng.choice([color.rgb(1, .4, .5), color.rgb(1, .92, .3), color.white, color.rgb(.6, .5, 1)])
                b.add('sphere', (x, .15, z), .28, col=c)
            else:
                b.add('sphere', (x, .15, z), (.9, .5, .7), rot=(0, self.rng.uniform(0, 180), 0), col=color.rgb(.6, .6, .6))
        b.entity(parent=self)

    # ================================================================ UI
    def _build_ui(self):
        self.ui = Entity(parent=camera.ui)
        self.prompt = Entity(parent=self.ui, y=-.36, enabled=False)
        Entity(parent=self.prompt, model='quad', color=color.rgba(0, 0, 0, .6), scale=(1.15, .06))
        self.prompt_text = Text(parent=self.prompt, text='', origin=(0, 0), scale=1.2, z=-.01,
                                color=color.rgb(1, .95, .6))
        Text(parent=self.ui, text='ZQSD / WASD : se déplacer   Maj : courir   Clic droit + souris : caméra   Molette : zoom',
             position=(0, .475), origin=(0, 0), scale=.85, color=color.rgba(1, 1, 1, .85))

        # badges
        self.badge_icons = {}
        Text(parent=self.ui, text='BADGES', position=(-.86, .44), scale=.9, origin=(-.5, 0))
        for i, a in enumerate(self.arenas):
            t = C.TYPES[a['type']]
            Entity(parent=self.ui, model='circle', color=color.rgba(0, 0, 0, .5), scale=.052,
                   position=(-.84 + i * .058, .4, .01))
            self.badge_icons[a['type']] = Entity(parent=self.ui, model='circle', scale=.04,
                                                 color=color.rgba(t['color'][0], t['color'][1], t['color'][2], .25),
                                                 position=(-.84 + i * .058, .4))
        self.badge_text = Text(parent=self.ui, text='0 / 5', position=(-.56, .4), origin=(-.5, 0), scale=.9)

        # mini-carte
        self.map_root = Entity(parent=self.ui, position=(-.75, -.33))
        self.map_scale = .13 / C.WORLD_RADIUS
        Entity(parent=self.map_root, model='circle', color=color.rgba(.1, .2, .35, .7), scale=.31, z=.02)
        Entity(parent=self.map_root, model='circle', color=color.rgba(.35, .6, .3, .85), scale=.26, z=.01)
        pts = [a['pos'] * self.map_scale for a in self.arenas]
        for i in range(len(pts)):
            p, q = pts[i], pts[(i + 1) % len(pts)]
            mid, d = (p + q) / 2, q - p
            Entity(parent=self.map_root, model='quad', color=color.rgba(.95, .85, .6, .9),
                   position=(mid.x, mid.z), scale=(d.length(), .006),
                   rotation_z=-math.degrees(math.atan2(d.z, d.x)))
        for a, p in zip(self.arenas, pts):
            Entity(parent=self.map_root, model='circle', color=C.TYPES[a['type']]['color'],
                   position=(p.x, p.z, -.01), scale=.03)
        self.map_player = Entity(parent=self.map_root, model='circle', color=color.yellow, scale=.018, z=-.02)

    def refresh_badges(self):
        n = 0
        for a in self.arenas:
            icon = self.badge_icons[a['type']]
            if a['beaten']:
                n += 1
                icon.color = C.TYPES[a['type']]['color']
            if a['beaten'] and a['crown'] is None:
                b = MeshBuilder()
                b.add('ring', (0, 0, 0), (7, .5, 7), col=color.rgb(1, .82, .2))
                a['crown'] = b.entity(parent=self, position=(a['pos'].x, 13.8, a['pos'].z), emissive=.6)
        self.badge_text.text = f'{n} / 5'
        return n

    # ================================================================ runtime
    def show(self):
        self.enabled = True
        self.ui.enabled = True
        self.snap_camera()

    def hide(self):
        self.enabled = False
        self.ui.enabled = False

    def place_player_at_door(self, type_key):
        a = next(a for a in self.arenas if a['type'] == type_key)
        p = a['door'] + a['dir'] * 3.5
        self.player.position = Vec3(p.x, 0, p.z)
        self.player.face((a['dir'].x, a['dir'].z))
        self.cam_yaw = self.player.rotation_y

    def snap_camera(self):
        self._place_camera(1.0)

    def _place_camera(self, k):
        # la cible suit le joueur en douceur ; la caméra est toujours exactement
        # à la bonne distance/angle de la cible (pas de décalage en tournant)
        target = self.player.world_position + Vec3(0, 1.6, 0)
        self.cam_target = target if k >= 1 or not hasattr(self, 'cam_target') else lerp(self.cam_target, target, k)
        yaw, pitch = math.radians(self.cam_yaw), math.radians(self.cam_pitch)
        offset = Vec3(-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        camera.position = self.cam_target + offset * self.cam_dist
        camera.rotation = Vec3(self.cam_pitch, self.cam_yaw, 0)

    def _collide(self, pos, radius=.5):
        W = C.WORLD_RADIUS - 1.5
        r = math.hypot(pos.x, pos.z)
        if r > W:
            pos.x *= W / r
            pos.z *= W / r
        BR = C.ARENA_BUILDING_RADIUS + 1.3 + radius
        for a in self.arenas:
            dx, dz = pos.x - a['pos'].x, pos.z - a['pos'].z
            d = math.hypot(dx, dz)
            if d < BR:
                pos.x = a['pos'].x + dx / d * BR
                pos.z = a['pos'].z + dz / d * BR
        for ox, oz, orad in self.obstacles:
            dx, dz = pos.x - ox, pos.z - oz
            if abs(dx) > 4 or abs(dz) > 4:
                continue
            d = math.hypot(dx, dz)
            m = orad + radius
            if 0 < d < m:
                pos.x = ox + dx / d * m
                pos.z = oz + dz / d * m
        return pos

    def update(self):
        dt = min(time.dt, .05)
        self._t += dt

        if mouse.right:
            self.cam_yaw += mouse.velocity[0] * 220
            self.cam_pitch = max(8, min(60, self.cam_pitch - mouse.velocity[1] * 120))

        ix = (held_keys['d'] or held_keys['right arrow']) - (held_keys['q'] or held_keys['a'] or held_keys['left arrow'])
        iz = (held_keys['z'] or held_keys['w'] or held_keys['up arrow']) - (held_keys['s'] or held_keys['down arrow'])
        yaw = math.radians(self.cam_yaw)
        fwd = Vec3(math.sin(yaw), 0, math.cos(yaw))
        right = Vec3(math.cos(yaw), 0, -math.sin(yaw))
        move = fwd * iz + right * ix
        moving = move.length() > 0
        if moving:
            speed = 9 * (1.6 if held_keys['shift'] else 1)
            move = move.normalized() * speed * dt
            self.player.position = self._collide(self.player.position + move)
            self.player.face((move.x, move.z), dt)
        self.player.animate(dt, moving)

        self._place_camera(min(1, dt * 8))

        for a in self.arenas:
            a['emblem'].rotation_y += dt * 40
            a['emblem'].y = 17 + math.sin(self._t * 1.5 + a['heading']) * .5

        # proximité d'une porte d'arène
        self.near_arena = None
        for a in self.arenas:
            if (self.player.position - a['door']).length() < C.ENTER_DISTANCE + .6:
                self.near_arena = a
                break
        if self.near_arena:
            t = C.TYPES[self.near_arena['type']]
            done = ' (déjà gagnée)' if self.near_arena['beaten'] else ''
            self.prompt_text.text = f"[E] Entrer dans l'Arène {t['name']}{done} - {t['pokemon']['name']} vous attend !"
            self.prompt.enabled = True
        else:
            self.prompt.enabled = False

        # mini-carte
        p = self.player.position * self.map_scale
        self.map_player.position = (p.x, p.z, -.02)

    def input(self, key):
        if key == 'e' and self.near_arena:
            self.game.start_battle(self.near_arena['type'])
        elif key == 'scroll up':
            self.cam_dist = max(6, self.cam_dist - 1)
        elif key == 'scroll down':
            self.cam_dist = min(28, self.cam_dist + 1)

