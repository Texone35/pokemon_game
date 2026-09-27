"""Combat dynamique 1 contre 1 contre le boss d'une région, directement sur place.

Le combat se déroule dans la clairière du repaire du boss : une barrière
d'énergie délimite le terrain (cercle de rayon BATTLE_ARENA_RADIUS) et tout le
décor de la région reste visible autour. Toute la logique travaille dans le
repère local de `self.root`, centré sur le repaire et tourné vers l'extérieur
de l'île (le monument de la région est donc toujours en fond).

Tout se joue au clavier. Le joueur (Pikachu) se déplace, esquive, et dispose
de 5 attaques qui visent automatiquement l'adversaire :
    J Éclair · K Vive-Attaque · L Tonnerre · U Cage-Éclair · I Queue de Fer
L'adversaire utilise les 4 attaques de son type (voir config.py) avec une
petite IA : il tourne autour du joueur, annonce ses attaques (clignotement,
ligne ou zone au sol) puis les lance.
"""
import math
import random

from ursina import Entity, Text, Vec3, Vec4, camera, color, curve, destroy, held_keys, lerp, time

import config as C
from creatures import Creature
from geometry import MeshBuilder, flat_circle
from ui import Banner, HPPanel, floating_text

R = C.BATTLE_ARENA_RADIUS
STATUS_LABEL = {'burn': 'BRÛLÉ', 'slow': 'RALENTI', 'stun': 'PARALYSÉ'}
STATUS_COLOR = {'burn': color.rgb(1, .5, .15), 'slow': color.rgb(.55, .9, 1), 'stun': color.rgb(1, .95, .3)}


def flat(v):
    return Vec3(v.x, 0, v.z)


def input_vector():
    ix = (held_keys['d'] or held_keys['right arrow']) - (held_keys['q'] or held_keys['a'] or held_keys['left arrow'])
    iz = (held_keys['z'] or held_keys['w'] or held_keys['up arrow']) - (held_keys['s'] or held_keys['down arrow'])
    v = Vec3(ix, 0, iz)
    return v.normalized() if v.length() else v


# ============================================================== effets
def burst(parent, pos, col, n=8, speed=4.0, size=.25, life=.45):
    """Petite explosion de particules."""
    for _ in range(n):
        d = Vec3(random.uniform(-1, 1), random.uniform(.2, 1.2), random.uniform(-1, 1)).normalized()
        p = Entity(parent=parent, model='cube', color=col, position=pos, scale=size * random.uniform(.6, 1.3))
        p.animate_position(pos + d * speed * random.uniform(.4, 1), duration=life, curve=curve.out_quad)
        p.animate_scale(0, duration=life, curve=curve.in_quad)
        destroy(p, delay=life + .05)


def lightning(parent, pos, col):
    """Éclair qui tombe du ciel."""
    for w, c in ((.9, col), (.35, color.white)):
        bolt = Entity(parent=parent, model='cube', color=c, position=pos + Vec3(0, 12, 0), scale=(w, 24, w))
        bolt.fade_out(duration=.25, delay=.08)
        destroy(bolt, delay=.35)


def orient(e, v):
    """Tourne l'entité dans la direction v (repère de son parent)."""
    if v.length() > 1e-4:
        e.rotation = Vec3(-math.degrees(math.atan2(v.y, math.hypot(v.x, v.z))), math.degrees(math.atan2(v.x, v.z)), 0)


def ring_mesh(parent, col, emissive=.8):
    return MeshBuilder().add('ring_thin', (0, 0, 0), (1, .5, 1), col=col).entity(parent=parent, emissive=emissive)


# ============================================================== projectiles
class Projectile:
    def __init__(self, battle, pos, vel, damage, size, col, owner, homing=0.0, life=3.0, shape='sphere',
                 status=None, stun=0.0):
        self.battle = battle
        self.vel = Vec3(vel)
        self.damage = damage
        self.radius = size * .5
        self.owner = owner
        self.homing = homing
        self.life = life
        self.col = col
        self.shape = shape
        self.status = status
        self.stun = stun
        self.alive = True
        root = battle.root
        if shape == 'leaf':
            self.e = Entity(parent=root, model='cube', color=col, position=pos, scale=(size * 1.4, .08, size * .6))
        elif shape == 'shard':
            self.e = Entity(parent=root, model='diamond', color=col, position=pos, scale=(size * .6, size * .6, size * 1.8))
        elif shape == 'rock':
            b = MeshBuilder().add('sphere', (0, 0, 0), 1, col=col)
            b.add('sphere', (.2, .25, .1), .6, col=col)
            self.e = b.entity(parent=root, position=pos, scale=size)
        elif shape == 'cage':
            self.e = Entity(parent=root, model='sphere', color=color.rgba(col[0], col[1], col[2], .45), position=pos, scale=size)
            for rot in ((0, 0, 0), (90, 0, 0), (0, 0, 90)):
                Entity(parent=self.e, model='wireframe_cube', color=col, scale=.8, rotation=rot)
        else:
            self.e = Entity(parent=root, model='sphere', color=col, position=pos, scale=size)
            Entity(parent=self.e, model='sphere', color=color.rgba(1, 1, 1, .9), scale=.55)
        orient(self.e, self.vel)

    def update(self, dt):
        self.life -= dt
        if self.homing:
            target = self.battle.player if self.owner == 'enemy' else self.battle.enemy
            desired = (flat(target.position) + Vec3(0, .9, 0) - self.e.position).normalized() * self.vel.length()
            self.vel = lerp(self.vel, desired, min(1, self.homing * dt))
        self.e.position += self.vel * dt
        if self.shape == 'leaf':
            self.e.rotation_y += dt * 900
        elif self.shape in ('rock', 'cage'):
            self.e.rotation_x += dt * 400
            self.e.rotation_y += dt * 250
        else:
            orient(self.e, self.vel)
        p = self.e.position
        if self.life <= 0 or p.x * p.x + p.z * p.z > (R + 1.5) ** 2:
            self.kill(False)

    def kill(self, impact=True):
        if not self.alive:
            return
        self.alive = False
        if impact:
            burst(self.battle.root, self.e.position, self.col, n=6, speed=2.5, size=.18, life=.3)
        destroy(self.e)


# ============================================================== dangers au sol
class Zone:
    """Zone annoncée au sol puis explosion (ennemi) ou foudre (joueur)."""

    def __init__(self, battle, pos, radius, delay, damage, col, owner='enemy', heal=0, status=None):
        self.battle, self.pos, self.radius = battle, flat(pos), radius
        self.delay, self.timer, self.damage, self.col = delay, delay, damage, col
        self.owner, self.heal, self.status = owner, heal, status
        self.alive = True
        edge = color.rgba(1, .12, .08, .3) if owner == 'enemy' else color.rgba(1, 1, .4, .3)
        self.outline = flat_circle(battle.root, radius, edge, position=self.pos + Vec3(0, .04, 0))
        self.fill = flat_circle(battle.root, radius, color.rgba(col[0], col[1], col[2], .7),
                                position=self.pos + Vec3(0, .05, 0), scale=.01)

    def update(self, dt):
        self.timer -= dt
        self.fill.scale = max(.01, 1 - max(0, self.timer) / self.delay)
        if self.timer <= 0:
            self.explode()

    def explode(self):
        self.cleanup()
        b = self.battle
        if self.owner == 'player':
            lightning(b.root, self.pos, self.col)
        else:
            pillar = Entity(parent=b.root, model='sphere', color=self.col, position=self.pos,
                            scale=(self.radius * 2, .5, self.radius * 2))
            pillar.animate_scale((self.radius * 2.2, self.radius * 2.5, self.radius * 2.2), duration=.18,
                                 curve=curve.out_quad)
            pillar.fade_out(duration=.3, delay=.1)
            destroy(pillar, delay=.45)
        burst(b.root, self.pos + Vec3(0, .5, 0), self.col, n=10, speed=self.radius * 1.4, size=.35)
        b.shake(.25)
        if self.owner == 'player':
            if (flat(b.enemy.position) - self.pos).length() < self.radius + b.e_radius:
                b.hurt_enemy(self.damage)
        elif (flat(b.player.position) - self.pos).length() < self.radius + .3:
            if b.hurt_player(self.damage, self.status) and self.heal:
                b.heal_enemy(self.heal)

    def cleanup(self):
        if self.alive:
            self.alive = False
            destroy(self.outline)
            destroy(self.fill)


class Wave:
    """Onde de choc circulaire : il faut l'esquiver (dash) au bon moment."""

    def __init__(self, battle, centre, speed, damage, col, start_radius=1.0, owner='enemy', max_radius=R + 1,
                 status=None):
        self.battle, self.centre, self.speed = battle, flat(centre), speed
        self.damage, self.owner, self.max_radius, self.status = damage, owner, max_radius, status
        self.r = start_radius
        self.hit = False
        self.alive = True
        self.e = ring_mesh(battle.root, col)
        self.e.position = self.centre + Vec3(0, .25, 0)
        self._resize()

    def _resize(self):
        self.e.scale = (self.r * 2, 1, self.r * 2)

    def update(self, dt):
        self.r += self.speed * dt
        self._resize()
        if not self.hit and self.owner == 'enemy':
            d = (flat(self.battle.player.position) - self.centre).length()
            if abs(d - self.r) < .8 and self.battle.hurt_player(self.damage, self.status):
                self.hit = True
        if self.r >= self.max_radius:
            self.cleanup()

    def cleanup(self):
        if self.alive:
            self.alive = False
            destroy(self.e)


class Beam:
    """Rayon : une ligne rouge annonce la trajectoire, puis le tir part."""

    def __init__(self, battle, origin, direction, move):
        self.battle, self.origin, self.dir, self.move = battle, flat(origin), direction.normalized(), move
        self.width = move['width']
        self.length = R * 2 + 4
        self.delay = self.timer = move['delay']
        self.fire_t = 0
        self.hit = False
        self.alive = True
        self.yaw = math.degrees(math.atan2(self.dir.x, self.dir.z))
        self.mid = self.origin + self.dir * (self.length / 2)
        self.tele = Entity(parent=battle.root, model='cube', color=color.rgba(1, .12, .08, .35),
                           position=self.mid + Vec3(0, .05, 0), scale=(self.width * .2, .02, self.length),
                           rotation_y=self.yaw)
        self.beam = None

    def update(self, dt):
        if self.beam is None:
            self.timer -= dt
            k = 1 - max(0, self.timer) / self.delay
            self.tele.scale_x = self.width * (.2 + .8 * k)
            if self.timer <= 0:
                destroy(self.tele)
                self.tele = None
                col = self.move['color']
                self.beam = Entity(parent=self.battle.root, model='cube', color=col, rotation_y=self.yaw,
                                   position=self.mid + Vec3(0, .9, 0), scale=(self.width * .8, 1.2, self.length))
                Entity(parent=self.beam, model='cube', color=color.rgba(1, 1, 1, .9), scale=(.4, .5, 1))
                self.fire_t = .35
                self.battle.shake(.3)
            return
        self.fire_t -= dt
        self.beam.scale_x = self.width * .8 * max(.05, self.fire_t / .35)
        if not self.hit:
            rel = flat(self.battle.player.position) - self.origin
            along = rel.x * self.dir.x + rel.z * self.dir.z
            perp = (rel - self.dir * along).length()
            if 0 < along < self.length and perp < self.width / 2 + .4:
                if self.battle.hurt_player(self.move['damage'], self.move.get('status')):
                    self.hit = True
        if self.fire_t <= 0:
            self.cleanup()

    def cleanup(self):
        if self.alive:
            self.alive = False
            if self.tele:
                destroy(self.tele)
            if self.beam:
                destroy(self.beam)


# ============================================================== interface
class MoveSlot(Entity):
    W, H = .12, .085

    def __init__(self, key_label, name, **kwargs):
        kwargs.setdefault('parent', camera.ui)
        super().__init__(**kwargs)
        Entity(parent=self, model='quad', color=color.rgba(.05, .05, .08, .8), scale=(self.W, self.H))
        self.key = Text(parent=self, text=key_label, origin=(0, 0), y=.013, z=-.01, scale=1.5 if len(key_label) == 1 else 1,
                        color=color.rgb(1, .92, .35))
        Text(parent=self, text=name, origin=(0, 0), y=-.025, z=-.01, scale=.62, color=color.rgb(.92, .92, .92))
        self.shade = Entity(parent=self, model='quad', color=color.rgba(0, 0, 0, .65), origin=(0, -.5),
                            position=(0, -self.H / 2, -.02), scale=(self.W, 0))

    def set_ratio(self, ratio):
        self.shade.scale_y = self.H * max(0, min(1, ratio))


# ============================================================== combat
def build_barrier(root, type_key):
    """Barrière d'énergie translucide qui se lève autour du terrain de combat."""
    t = C.TYPES[type_key]
    wall = MeshBuilder().add('ring_thin', (0, .5, 0), (R * 2 + .6, 1, R * 2 + .6), col=t['light']).entity(
        parent=root, emissive=.9, color=color.rgba(1, 1, 1, .28), scale_y=.01)
    wall.animate_scale_y(3.5, duration=.7, curve=curve.out_back)
    edge = MeshBuilder().add('ring_thin', (0, .06, 0), (R * 2 + .6, .08, R * 2 + .6), col=t['light']).entity(
        parent=root, emissive=1.0)
    return wall, edge


class Battle(Entity):
    def __init__(self, game, type_key, centre, heading, player_pos):
        super().__init__()
        self.game = game
        self.type_key = type_key
        self.t = C.TYPES[type_key]
        self.pdata = C.PLAYER
        self.edata = self.t['pokemon']
        self.heading = heading
        self.root = Entity(parent=self, position=centre, rotation_y=heading)
        self.projectiles = []
        self.hazards = []           # zones, ondes, rayons
        self.state = 'intro'
        self.state_timer = 2.4
        self.shake_amount = 0.0
        self.result = None

        self.wall, self.edge = build_barrier(self.root, type_key)

        # ---- joueur : il commence là où il se trouvait, face au boss
        local = self._to_local(player_pos)
        d = local.length()
        local = (local / d if d > .01 else Vec3(0, 0, -1)) * max(8.5, min(R * .75, d))
        self.player = Creature('pikachu', parent=self.root, position=local, scale=1.4)
        self.player.face((-local.x, -local.z))
        self.p_hp = self.pdata['max_hp']
        self.p_radius = .75
        self.p_moves = self.pdata['moves']
        self.p_cd = {m['key']: 0.0 for m in self.p_moves}
        self.p_dash_cd = 0.0
        self.p_dash_t = 0.0
        self.p_dash_dir = Vec3(0, 0, 1)
        self.p_rush_t = 0.0
        self.p_rush_move = None
        self.p_invuln = 0.0
        self.p_attack_anim = 0.0
        self.p_status = {'burn': 0.0, 'slow': 0.0}
        self.p_burn_tick = 0.0
        self.fx_timer = 0.0

        # ---- adversaire : le boss, au centre de son repaire
        self.enemy = Creature(self.edata['species'], parent=self.root, position=(0, 0, 0),
                              scale=self.edata['scale'])
        self.enemy.face((local.x, local.z))
        self._pulse_enemy()
        self.e_hp = self.edata['max_hp']
        self.e_radius = self.edata['radius']
        self.e_state = 'move'
        self.e_timer = random.uniform(*self.edata['attack_interval']) + .5
        self.e_strafe = random.choice((-1, 1))
        self.e_strafe_timer = 1.5
        self.e_move = None
        self.e_last_move = None
        self.e_shots = 0
        self.e_shot_timer = 0.0
        self.e_angle = 0.0
        self.e_charge_dir = Vec3(0, 0, 0)
        self.e_charge_hit = False
        self.e_stun = 0.0

        self._build_ui()
        self._place_camera(1)

    # ------------------------------------------------------------ interface
    def _build_ui(self):
        self.ui = Entity(parent=camera.ui)
        self.enemy_panel = HPPanel(self.edata['name'], self.edata['level'], self.edata['max_hp'],
                                   type_name=self.t['name'], type_color=self.t['color'],
                                   show_numbers=False, position=(-.84, .46))
        self.enemy_panel.parent = self.ui
        self.player_panel = HPPanel(self.pdata['name'], self.pdata['level'], self.pdata['max_hp'],
                                    type_name='Électrik', type_color=color.rgb(.95, .75, .1),
                                    position=(.33, -.3))
        self.player_panel.parent = self.ui
        self.e_status_text = Text(parent=self.ui, text='', position=(-.83, .33), scale=.9)
        self.p_status_text = Text(parent=self.ui, text='', position=(.34, -.255), scale=.9)

        self.move_bg = Entity(parent=self.ui, model='quad', color=color.rgba(0, 0, 0, .55),
                              scale=(.62, .05), y=.36, z=.01, enabled=False)
        self.move_text = Text(parent=self.ui, text='', origin=(0, 0), y=.36, scale=1.3, color=self.t['light'])

        # barre d'attaques (clavier)
        self.slots = {}
        x0, step = -.8, .132
        self.dash_slot = MoveSlot('ESPACE', 'Esquive', parent=self.ui, position=(x0, -.4))
        for i, m in enumerate(self.p_moves):
            self.slots[m['key']] = MoveSlot(m['key'].upper(), m['name'], parent=self.ui,
                                            position=(x0 + step * (i + 1), -.4))
        Text(parent=self.ui, text='ZQSD / WASD : bouger     Maintenir J : tir continu     Échap : fuir',
             position=(x0 - .06, -.465), scale=.8, color=color.rgba(1, 1, 1, .8))

        self.banner = Banner()
        self.banner.parent = self.ui
        self.banner.show(f"{self.edata['name']}, boss de la région {self.t['name']}, vous attaque !", 2.2)

    def _refresh_ui(self):
        for m in self.p_moves:
            self.slots[m['key']].set_ratio(self.p_cd[m['key']] / m['cooldown'])
        self.dash_slot.set_ratio(self.p_dash_cd / self.pdata['dash_cooldown'])
        p = [STATUS_LABEL[k] for k, v in self.p_status.items() if v > 0]
        self.p_status_text.text = '  '.join(p)
        self.p_status_text.color = STATUS_COLOR['burn'] if self.p_status['burn'] > 0 else STATUS_COLOR['slow']
        self.e_status_text.text = STATUS_LABEL['stun'] if self.e_stun > 0 else ''
        self.e_status_text.color = STATUS_COLOR['stun']

    def _announce(self, text, col):
        self.move_text.text = text
        self.move_text.color = col
        self.move_bg.enabled = True
        self.move_text.scale = 1.1
        self.move_text.animate_scale(1.3, duration=.15, curve=curve.out_back)

    # ------------------------------------------------------------ caméra
    def shake(self, amount):
        self.shake_amount = max(self.shake_amount, amount)

    def _to_world(self, v):
        """Repère local du terrain -> monde (rotation autour de y + translation)."""
        a = math.radians(self.heading)
        c, s = math.cos(a), math.sin(a)
        return self.root.position + Vec3(v.x * c + v.z * s, v.y, -v.x * s + v.z * c)

    def _to_local(self, v):
        a = math.radians(self.heading)
        c, s = math.cos(a), math.sin(a)
        d = Vec3(v.x - self.root.x, 0, v.z - self.root.z)
        return Vec3(d.x * c - d.z * s, 0, d.x * s + d.z * c)

    def _place_camera(self, k):
        p = self.player.position
        focus = Vec3(p.x * .55, 0, p.z * .55 + 3.5)
        target = self._to_world(focus + Vec3(0, 17, -19))
        camera.position = lerp(camera.position, target, k)
        if self.shake_amount > 0:
            camera.position += Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0) * self.shake_amount
        camera.rotation = Vec3(math.degrees(math.atan2(17, 19)), self.heading, 0)

    # ------------------------------------------------------------ dégâts
    def _damage_player(self, dmg, col=color.rgb(1, .4, .35)):
        self.p_hp -= dmg
        self.player_panel.set_hp(self.p_hp)
        floating_text(f'-{dmg}', self.player.world_position + Vec3(0, 2.4, 0), col)
        if self.p_hp <= 0:
            self._finish(False)

    def hurt_player(self, dmg, status=None):
        """Renvoie True si le coup a porté (pas d'invincibilité / esquive)."""
        if self.p_invuln > 0 or self.state != 'fight':
            return False
        self.player.hit_flash(Vec4(1, .25, .2, .8), .15)
        self.p_invuln = C.INVULNERABILITY
        self.shake(.35)
        self._damage_player(max(1, round(dmg * random.uniform(.9, 1.1))))
        if status and self.state == 'fight':
            kind, duration = status
            self.p_status[kind] = max(self.p_status[kind], duration)
        return True

    def hurt_enemy(self, dmg, stun=0.0):
        if self.state != 'fight':
            return
        eff = C.EFFECTIVENESS.get(self.type_key, 1.0)
        dmg = max(1, round(dmg * eff * random.uniform(.9, 1.1)))
        self.e_hp -= dmg
        self.enemy_panel.set_hp(self.e_hp)
        self.enemy.hit_flash()
        col = color.rgb(1, .95, .3) if eff > 1 else (color.rgb(.75, .75, .75) if eff < 1 else color.white)
        floating_text(f'-{dmg}', self.enemy.world_position + Vec3(0, 3.4, 0), col, 1.1)
        if eff > 1 and random.random() < .25:
            floating_text("C'est super efficace !", self.enemy.world_position + Vec3(0, 4.4, 0), col, .9)
        elif eff < 1 and random.random() < .15:
            floating_text("Ce n'est pas très efficace...", self.enemy.world_position + Vec3(0, 4.4, 0), col, .9)
        if stun:
            self.e_stun = max(self.e_stun, stun)
            if self.e_state == 'charge':
                self.enemy.pivot.rotation_x = 0
            if self.e_state not in ('channel',):
                self.e_state = 'move'
            floating_text('Paralysé !', self.enemy.world_position + Vec3(0, 4.4, 0), STATUS_COLOR['stun'], 1.0)
        if self.e_hp <= 0:
            self._finish(True)

    def heal_enemy(self, amount):
        self.e_hp = min(self.edata['max_hp'], self.e_hp + amount)
        self.enemy_panel.set_hp(self.e_hp)
        floating_text(f'+{amount}', self.enemy.world_position + Vec3(0, 3.4, 0), color.rgb(.4, 1, .4), 1.0)

    def _clear_field(self):
        for p in self.projectiles:
            p.kill(False)
        for h in self.hazards:
            h.cleanup()
        self.projectiles, self.hazards = [], []

    def _finish(self, won):
        if self.state != 'fight':
            return
        self.state = 'end'
        self.state_timer = 3.2
        self.result = won
        self._clear_field()
        self.move_bg.enabled = False
        self.move_text.text = ''
        if won:
            self.enemy.knock_out()
            self.banner.show(f"{self.edata['name']} est K.O. !  La région {self.t['name']} est libérée !", 3.2,
                             text_color=color.rgb(1, .9, .3), big=True)
        else:
            self.player.knock_out()
            self.banner.show(f"{self.pdata['name']} est K.O...", 3.2,
                             text_color=color.rgb(1, .5, .45), big=True)

    # ------------------------------------------------------------ joueur
    def _player_facing(self):
        """Direction du regard du joueur dans le repère local du terrain."""
        a = math.radians(self.player.rotation_y)
        return Vec3(math.sin(a), 0, math.cos(a))

    def _dir_to_enemy(self):
        d = flat(self.enemy.position - self.player.position)
        return d.normalized() if d.length() > .01 else self._player_facing()

    def _use_move(self, m):
        if self.state != 'fight' or self.p_cd[m['key']] > 0 or self.p_rush_t > 0 or self.p_dash_t > 0:
            return
        self.p_cd[m['key']] = m['cooldown']
        self.p_attack_anim = .2
        d = self._dir_to_enemy()
        self.player.face((d.x, d.z))
        start = self.player.position + Vec3(0, 1.0, 0) + d * .8
        kind = m['kind']
        if kind != 'bolt':
            floating_text(m['name'] + ' !', self.player.world_position + Vec3(0, 3.2, 0), color.rgb(1, .95, .45), .9)

        if kind == 'bolt':
            self.projectiles.append(Projectile(self, start, d * m['speed'], m['damage'], m['size'], m['color'],
                                               'player', life=1.2))
        elif kind == 'stun':
            self.projectiles.append(Projectile(self, start, d * m['speed'], m['damage'], m['size'], m['color'],
                                               'player', life=2.0, shape='cage', homing=1.2, stun=m['stun']))
        elif kind == 'rush':
            self.p_rush_t = m['duration']
            self.p_rush_move = m
            self.p_invuln = max(self.p_invuln, m['duration'] + .1)
        elif kind == 'strike':
            self.hazards.append(Zone(self, self.enemy.position, m['radius'], m['delay'], m['damage'], m['color'],
                                     owner='player'))
        elif kind == 'spin':
            self.player.pivot.rotation_y = 0
            self.player.pivot.animate('rotation_y', 720, duration=.35)
            self.p_invuln = max(self.p_invuln, .3)
            wave = Wave(self, self.player.position, 18, 0, color.rgb(.85, .85, .9), start_radius=.8,
                        owner='player', max_radius=m['radius'])
            self.hazards.append(wave)
            # la queue renvoie les projectiles proches et frappe l'adversaire au contact
            pp = flat(self.player.position)
            for p in self.projectiles:
                if p.owner == 'enemy' and (flat(p.e.position) - pp).length() < m['radius'] + p.radius:
                    p.kill()
            if (flat(self.enemy.position) - pp).length() < m['radius'] + self.e_radius:
                self.hurt_enemy(m['damage'])
                self._push_enemy(self._dir_to_enemy() * 2.5)

    def _dash(self):
        if self.p_dash_cd > 0 or self.state != 'fight' or self.p_rush_t > 0:
            return
        d = input_vector()
        self.p_dash_dir = d if d.length() else self._player_facing()
        self.p_dash_t = self.pdata['dash_time']
        self.p_dash_cd = self.pdata['dash_cooldown']
        self.p_invuln = max(self.p_invuln, self.pdata['dash_time'] + .08)
        self.player.face((self.p_dash_dir.x, self.p_dash_dir.z))

    def _update_player(self, dt):
        move = input_vector()
        moving = move.length() > 0
        for k in self.p_cd:
            self.p_cd[k] -= dt
        self.p_dash_cd -= dt
        self.p_invuln -= dt
        self.p_attack_anim -= dt

        # statuts
        for k in self.p_status:
            self.p_status[k] = max(0, self.p_status[k] - dt)
        if self.p_status['burn'] > 0:
            self.p_burn_tick -= dt
            if self.p_burn_tick <= 0:
                self.p_burn_tick = .6
                self._damage_player(2, STATUS_COLOR['burn'])
                if self.state != 'fight':
                    return
        self.fx_timer -= dt
        if self.fx_timer <= 0:
            self.fx_timer = .12
            for k, v in self.p_status.items():
                if v > 0:
                    burst(self.root, self.player.position + Vec3(0, 1.2, 0), STATUS_COLOR[k], n=1, speed=1, size=.15)
            if self.e_stun > 0:
                burst(self.root, self.enemy.position + Vec3(0, 2, 0), STATUS_COLOR['stun'], n=2, speed=2, size=.15)

        speed = self.pdata['speed'] * (.55 if self.p_status['slow'] > 0 else 1)
        if self.p_rush_t > 0:                              # Vive-Attaque
            self.p_rush_t -= dt
            d = self._dir_to_enemy()
            vel = d * self.p_rush_move['speed']
            self.player.face((d.x, d.z))
            burst(self.root, self.player.position + Vec3(0, .6, 0), color.white, n=1, speed=.5, size=.2, life=.2)
            if (flat(self.enemy.position - self.player.position)).length() < self.p_radius + self.e_radius + .4:
                self.hurt_enemy(self.p_rush_move['damage'])
                self._push_enemy(d * 3)
                self.shake(.3)
                self.p_rush_t = 0
                self.p_invuln = max(self.p_invuln, .3)
        elif self.p_dash_t > 0:                            # esquive
            self.p_dash_t -= dt
            vel = self.p_dash_dir * self.pdata['dash_speed']
            if random.random() < .6:
                burst(self.root, self.player.position + Vec3(0, .5, 0), color.rgb(1, .95, .5), n=1, speed=.5, size=.2, life=.25)
        else:
            vel = move * speed

        pos = self.player.position + vel * dt
        r = math.hypot(pos.x, pos.z)
        lim = R - self.p_radius
        if r > lim:
            pos.x *= lim / r
            pos.z *= lim / r
        d = flat(pos - self.enemy.position)
        min_d = self.p_radius + self.e_radius
        if 0 < d.length() < min_d:
            pos = flat(self.enemy.position) + d.normalized() * min_d
        self.player.position = pos

        # J maintenu = tir continu
        bolt = self.p_moves[0]
        if held_keys[bolt['key']]:
            self._use_move(bolt)

        if self.p_attack_anim > 0 and self.p_rush_t <= 0:
            d = self._dir_to_enemy()
            self.player.face((d.x, d.z))
        elif moving and self.p_rush_t <= 0 and self.p_dash_t <= 0:
            self.player.face((move.x, move.z), dt, 16)

        blink = self.p_invuln > 0 and self.p_dash_t <= 0 and self.p_rush_t <= 0 and int(self.p_invuln * 20) % 2 == 0
        self.player.visible = not blink
        self.player.animate(dt, moving or self.p_dash_t > 0 or self.p_rush_t > 0, self.p_attack_anim > 0)

    # ------------------------------------------------------------ adversaire
    def _push_enemy(self, delta):
        self._move_enemy(delta)

    def _enemy_fire(self, move, angle_offset=0.0):
        e = self.enemy
        origin = e.position + Vec3(0, .85 * self.edata['scale'], 0)
        to_p = flat(self.player.position - e.position)
        base = math.atan2(to_p.x, to_p.z) if to_p.length() else 0
        kind = move['kind']
        shape = {"Tranch'Herbe": 'leaf', 'Éclats Glace': 'shard', 'Vent Glace': 'shard',
                 'Jet-Pierres': 'rock'}.get(move['name'], 'sphere')

        def shoot(angle, speed, homing=0.0, life=3.0):
            v = Vec3(math.sin(angle), 0, math.cos(angle)) * speed
            self.projectiles.append(Projectile(self, origin + v.normalized() * self.e_radius, v, move['damage'],
                                               move['size'], move['color'], 'enemy', homing=homing, life=life,
                                               shape=shape, status=move.get('status')))

        if kind in ('spread', 'homing'):
            n, total = move['count'], math.radians(move.get('angle', 0))
            for i in range(n):
                off = 0 if n == 1 else -total / 2 + total * i / (n - 1)
                shoot(base + off, move['speed'], homing=move.get('turn', 0), life=move.get('life', 3.0))
        elif kind == 'stream':
            shoot(base + math.radians(random.uniform(-4, 4)), move['speed'])
        elif kind == 'nova':
            n = move['count']
            for i in range(n):
                shoot(base + angle_offset + math.tau * i / n, move['speed'], life=4)
        elif kind == 'spiral':
            arms = move.get('arms', 1)
            for i in range(arms):
                shoot(self.e_angle + math.tau * i / arms, move['speed'], life=4)

    def _enemy_start_move(self, move):
        kind = move['kind']
        self._announce(f"{self.edata['name']} utilise {move['name']} !", self.t['light'])
        if kind in ('stream', 'nova', 'spiral', 'wave'):
            self.e_state = kind
            self.e_shots = move.get('count', 1) if kind in ('stream', 'spiral') else move.get('waves', 1)
            self.e_shot_timer = 0
            to_p = flat(self.player.position - self.enemy.position)
            self.e_angle = math.atan2(to_p.x, to_p.z)
        elif kind == 'zone':
            p = flat(self.player.position)
            for i in range(move['count']):
                if i == 0:
                    pos = p
                else:
                    a = random.uniform(0, math.tau)
                    pos = p + Vec3(math.sin(a), 0, math.cos(a)) * random.uniform(2, move.get('scatter', 5))
                if pos.length() > R - 1:
                    pos = pos.normalized() * (R - 1)
                self.hazards.append(Zone(self, pos, move['radius'], move['delay'] + i * .12, move['damage'],
                                         move['color'], heal=move.get('heal', 0), status=move.get('status')))
            self.e_state, self.e_timer = 'recover', .5
        elif kind == 'beam':
            d = flat(self.player.position - self.enemy.position)
            d = d.normalized() if d.length() else Vec3(0, 0, -1)
            self.enemy.face((d.x, d.z))
            self.hazards.append(Beam(self, self.enemy.position + d * self.e_radius, d, move))
            self.e_state, self.e_timer = 'channel', move['delay'] + .45
        elif kind == 'charge':
            to_p = flat(self.player.position - self.enemy.position)
            self.e_charge_dir = to_p.normalized() if to_p.length() else Vec3(0, 0, 1)
            self.e_state, self.e_timer = 'charge', move['duration']
            self.e_charge_hit = False
        else:
            self._enemy_fire(move)
            self.e_state, self.e_timer = 'recover', .35

    def _update_enemy(self, dt):
        e = self.enemy
        to_p = flat(self.player.position - e.position)
        dist = to_p.length()
        dir_p = to_p.normalized() if dist > 0 else Vec3(0, 0, 1)
        speed = self.edata['speed']
        moving = False
        m = self.e_move

        if self.e_stun > 0:                          # paralysé : ne fait rien
            self.e_stun -= dt
            e.pivot.rotation_z = math.sin(self.e_stun * 60) * 6 if self.e_stun > 0 else 0
            e.animate(dt, False)
            return

        if self.e_state == 'move':
            self.e_strafe_timer -= dt
            if self.e_strafe_timer <= 0:
                self.e_strafe = random.choice((-1, 1))
                self.e_strafe_timer = random.uniform(1.0, 2.2)
            tangent = Vec3(dir_p.z, 0, -dir_p.x) * self.e_strafe
            want = 8.5
            radial = dir_p * (1 if dist > want + 1.5 else (-1 if dist < want - 2 else 0))
            v = tangent * .8 + radial
            if v.length():
                self._move_enemy(v.normalized() * speed * dt)
            moving = True
            e.face((dir_p.x, dir_p.z), dt, 8)
            self.e_timer -= dt
            if self.e_timer <= 0:
                choices = [mv for mv in self.t['moves'] if mv is not self.e_last_move] or self.t['moves']
                self.e_move = self.e_last_move = random.choice(choices)
                self.e_state, self.e_timer = 'windup', .5
                e.hit_flash(Vec4(self.t['light'][0], self.t['light'][1], self.t['light'][2], .55), .5)

        elif self.e_state == 'windup':
            e.face((dir_p.x, dir_p.z), dt, 10)
            self.e_timer -= dt
            if self.e_timer <= 0:
                self._enemy_start_move(m)

        elif self.e_state == 'stream':
            e.face((dir_p.x, dir_p.z), dt, 10)
            self.e_shot_timer -= dt
            if self.e_shot_timer <= 0:
                self._enemy_fire(m)
                self.e_shots -= 1
                self.e_shot_timer = m['interval']
                if self.e_shots <= 0:
                    self.e_state, self.e_timer = 'recover', .4

        elif self.e_state == 'spiral':
            self.e_shot_timer -= dt
            e.rotation_y += dt * 500
            if self.e_shot_timer <= 0:
                self._enemy_fire(m)
                self.e_angle += math.radians(m['spin'])
                self.e_shots -= 1
                self.e_shot_timer = m['interval']
                if self.e_shots <= 0:
                    self.e_state, self.e_timer = 'recover', .5

        elif self.e_state == 'nova':
            self.e_shot_timer -= dt
            if self.e_shot_timer <= 0:
                done = m.get('waves', 1) - self.e_shots
                self._enemy_fire(m, angle_offset=done * math.pi / m['count'])
                self._pulse_enemy()
                self.e_shots -= 1
                self.e_shot_timer = .4
                if self.e_shots <= 0:
                    self.e_state, self.e_timer = 'recover', .5

        elif self.e_state == 'wave':
            self.e_shot_timer -= dt
            if self.e_shot_timer <= 0:
                self.hazards.append(Wave(self, e.position, m['speed'], m['damage'], m['color'],
                                         start_radius=self.e_radius, status=m.get('status')))
                self._pulse_enemy()
                self.shake(.3)
                self.e_shots -= 1
                self.e_shot_timer = m['interval']
                if self.e_shots <= 0:
                    self.e_state, self.e_timer = 'recover', .6

        elif self.e_state == 'charge':
            self._move_enemy(self.e_charge_dir * m['speed'] * dt, bounce=True)
            e.face((self.e_charge_dir.x, self.e_charge_dir.z))
            e.pivot.rotation_x += dt * 900
            moving = True
            if random.random() < .5:
                burst(self.root, e.position + Vec3(0, .2, 0), color.rgb(.6, .5, .4), n=1, speed=1, size=.3, life=.3)
            if not self.e_charge_hit and dist < self.e_radius + self.p_radius + .3:
                if self.hurt_player(m['damage']):
                    self.e_charge_hit = True
            self.e_timer -= dt
            if self.e_timer <= 0:
                e.pivot.rotation_x = 0
                self.e_state, self.e_timer = 'recover', .7

        elif self.e_state in ('recover', 'channel'):
            if self.e_state == 'recover':
                e.face((dir_p.x, dir_p.z), dt, 6)
            self.e_timer -= dt
            if self.e_timer <= 0:
                self.e_state = 'move'
                self.move_text.text = ''
                self.move_bg.enabled = False
                rage = .6 + .4 * (self.e_hp / self.edata['max_hp'])   # blessé = plus agressif
                self.e_timer = random.uniform(*self.edata['attack_interval']) * rage

        if self.e_state != 'charge' and dist < self.e_radius + self.p_radius - .05:
            self.hurt_player(5)

        e.animate(dt, moving, self.e_state in ('windup', 'stream', 'nova', 'spiral', 'wave', 'channel'))

    def _pulse_enemy(self):
        s = self.edata['scale']
        self.enemy.pivot.animate_scale(s * 1.15, duration=.08)
        self.enemy.pivot.animate_scale(s, duration=.15, delay=.08)

    def _move_enemy(self, delta, bounce=False):
        pos = self.enemy.position + delta
        r = math.hypot(pos.x, pos.z)
        lim = R - self.e_radius
        if r > lim:
            pos.x *= lim / r
            pos.z *= lim / r
            if bounce:
                self.e_timer = min(self.e_timer, .05)
                self.shake(.3)
        self.enemy.position = pos

    # ------------------------------------------------------------ boucle
    def update(self):
        dt = min(time.dt, .05)
        self.shake_amount = max(0, self.shake_amount - dt * 2)

        if self.state == 'intro':
            self.state_timer -= dt
            self.player.animate(dt)
            self.enemy.animate(dt)
            if self.state_timer <= 0:
                self.state = 'fight'
                self.banner.show('COMBAT !', .9, text_color=color.rgb(1, .95, .4), big=True)

        elif self.state == 'fight':
            self._update_player(dt)
            if self.state == 'fight':
                self._update_enemy(dt)
            if self.state == 'fight':
                self._update_field(dt)
            self._refresh_ui()

        elif self.state == 'end':
            self.state_timer -= dt
            if self.result:
                self.player.animate(dt)
                self.player.pivot.y = abs(math.sin(self.state_timer * 8)) * .6   # saute de joie
            else:
                self.enemy.animate(dt)
            self.player.visible = True
            if self.state_timer <= 0:
                self.state = 'done'
                self.game.end_battle(self.type_key, self.result)
                return

        self._place_camera(min(1, dt * 6))

    def _update_field(self, dt):
        pp = flat(self.player.position) + Vec3(0, 1, 0)
        ep = flat(self.enemy.position) + Vec3(0, 1.2, 0)
        for p in self.projectiles:
            if not p.alive:
                continue
            p.update(dt)
            if not p.alive:
                continue
            pos = p.e.position
            if p.owner == 'player':
                if (pos - ep).length() < p.radius + self.e_radius + .2:
                    p.kill()
                    self.hurt_enemy(p.damage, stun=p.stun)
            elif (pos - pp).length() < p.radius + self.p_radius and self.p_invuln <= 0:
                p.kill()
                self.hurt_player(p.damage, p.status)
            if self.state != 'fight':
                return
        self.projectiles = [p for p in self.projectiles if p.alive]
        for h in list(self.hazards):
            if h.alive:
                h.update(dt)
            if self.state != 'fight':
                return
        self.hazards = [h for h in self.hazards if h.alive]

    def input(self, key):
        if key in ('space', 'shift', 'left shift', 'right shift'):
            self._dash()
        elif key == 'escape' and self.state in ('intro', 'fight'):
            self.state = 'done'
            self.game.end_battle(self.type_key, None)
        else:
            for m in self.p_moves:
                if key == m['key']:
                    self._use_move(m)

    def cleanup(self):
        self._clear_field()
        destroy(self.ui)
        destroy(self)

    def player_world_position(self):
        return self._to_world(self.player.position)
