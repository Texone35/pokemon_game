"""Pokémon présents sur le terrain : joueurs, IA des deux équipes et Pokémon neutres.

Unit              : état commun (PV, niveau, statuts, bonus, déplacement, attaque de base)
PlayerBrain       : contrôles clavier d'un joueur (attaques J K L U I selon son Pokémon)
RemotePlayerBrain : chez l'hôte, le Pokémon de l'invité (positions et attaques reçues par le réseau)
BotBrain          : IA d'équipe (capture d'arènes, combats, jungle, boss, repli)
NeutralBrain      : Pokémon neutres (restent à leur camp, ripostent quand on les attaque)

En partie à deux, l'hôte fait autorité (dégâts, IA, score). Chez l'invité
(match.authority == False), les unités sont des « marionnettes » placées d'après
l'état reçu (voir netsync.py), sauf son propre Pokémon qu'il déplace lui-même.
"""
import math
import random

from ursina import Entity, Text, Vec3, Vec4, color, held_keys

from game import config as C
from game.pokemon.combat import Projectile, Wave, Zone, cast_special, flat
from game.pokemon.creatures import Creature
from game.world.fx import burst
from game.world.geometry import flat_circle

STATUS_COLOR = {'burn': color.rgb(1, .5, .15), 'slow': color.rgb(.55, .9, 1), 'stun': color.rgb(1, .95, .3)}
LOCAL_BAR = color.rgb(.3, .95, .35)          # barre de vie de son propre Pokémon
ALLY_BAR = color.rgb(.35, .9, 1)             # barre de vie de l'autre joueur humain


class Unit:
    def __init__(self, match, species, team, pos, role=None, human=None, local=False, camp=None):
        self.match = match
        self.species = species
        self.data = C.SPECIES[species]
        self.name = self.data['name']
        self.type = self.data['type']
        self.team = team                  # 'rouge', 'bleu' ou None (neutre)
        self.role = role
        self.human = human                # None (IA) ou numéro du joueur humain (0 : hôte, 1 : invité)
        self.is_player = human is not None
        self.local = local                # Pokémon contrôlé sur ce PC
        self.net_driven = False           # position imposée par le réseau (voir netsync.py)
        self.camp = camp
        self.uid = -1                     # numéro commun aux deux PC (ordre de création)
        self.radius = self.data['radius']
        self.brain = None
        self.hp_factor = 1.0
        self.level, self.xp = 1, 0.0
        self.moving = False
        self.bush = 0                     # numéro de la touffe de hautes herbes où il se trouve
        self.veiled = False               # caché (dans l'herbe) aux yeux de l'équipe de ce PC
        self.home = Vec3(pos[0], 0, pos[1])
        self.creature = Creature(species, parent=match.root, position=self.home, scale=self.data['scale'])
        if team:
            tc = C.TEAMS[team]['color']
            self.ring = flat_circle(self.creature, self.radius + .35, color.rgba(tc[0], tc[1], tc[2], .75), y=.05)
        h = self.data['scale'] * 1.5 + .5
        bar_col = C.TEAMS[team]['color'] if team else color.rgb(1, .75, .2)
        if self.is_player:
            bar_col = LOCAL_BAR if local else ALLY_BAR
        w = 1.6 if self.data['hp'] < 1000 else 3.2
        self.bar = Entity(parent=self.creature, y=h, billboard=True)
        Entity(parent=self.bar, model='quad', color=color.rgba(0, 0, 0, .7), scale=(w + .1, .24))
        self.bar_fill = Entity(parent=self.bar, model='quad', color=bar_col, origin=(-.5, 0),
                               position=(-w / 2, 0, -.01), scale=(w, .16))
        self.bar_w = w
        self.ring = getattr(self, 'ring', None)
        if self.is_player and not local:          # nom au-dessus du Pokémon de l'autre joueur
            Text(parent=self.bar, text=f'J{human + 1}', y=.42, z=-.02, origin=(0, 0), scale=12, color=ALLY_BAR)
        self.reset()

    # ------------------------------------------------------------ état
    def reset(self, pos=None):
        self.hp = self.max_hp
        self.alive = True
        self.respawn_t = 0.0
        self.attack_cd = 0.0
        self.special_cd = random.uniform(2, 5)
        self.status = {'burn': 0.0, 'slow': 0.0, 'stun': 0.0}
        self.burn_tick = 0.0
        self.buffs = {}
        self.invuln = 0.0
        self.channel = 0.0
        self.charge_t = 0.0
        self.charge_dir = Vec3(0, 0, 1)
        self.charge_dmg = 0
        self.charge_hit = set()
        self.last_hit_by = None
        self.last_hit_t = -99
        self.attack_anim = 0.0
        self.vel = Vec3(0, 0, 0)
        self.moving = False
        self._last = None
        self.creature.enabled = True
        self.creature.visible = True
        self.creature._ko = False
        self.creature.pivot.rotation_z = 0
        self.creature.pivot.rotation_x = 0
        self.creature.pivot.scale = self.data['scale']
        self.creature.set_flash(Vec4(1, 1, 1, 0))
        p = Vec3(pos) if pos is not None else Vec3(self.home)
        p.y = self.match.stadium.walk_y(p.x, p.z)
        self.creature.position = p
        self._fx_t = 0
        self._refresh_bar()

    @property
    def position(self):
        return self.creature.position

    @position.setter
    def position(self, v):
        self.creature.position = v

    @property
    def max_hp(self):
        return round(self.data['hp'] * self.hp_factor * (1 + C.LEVEL_BONUS * (self.level - 1)))

    def facing(self):
        a = math.radians(self.creature.rotation_y)
        return Vec3(math.sin(a), 0, math.cos(a))

    def face(self, d, dt=None, speed=12):
        self.creature.face((d.x, d.z), dt, speed)

    def pulse(self):
        s = self.data['scale']
        self.creature.pivot.animate_scale(s * 1.15, duration=.08)
        self.creature.pivot.animate_scale(s, duration=.15, delay=.08)
        self.match.emit('anim', self.uid, 'pulse')

    def spin(self):
        self.creature.pivot.rotation_y = 0
        self.creature.pivot.animate('rotation_y', 720, duration=.35)
        self.match.emit('anim', self.uid, 'spin')

    # ------------------------------------------------------------ bonus
    def has(self, buff):
        return self.buffs.get(buff, 0) > 0

    def damage_mult(self):
        m = 1 + C.LEVEL_BONUS * (self.level - 1)
        if self.has('braise'):
            m *= 1.25
        if self.has('psy'):
            m *= 1.2
        return m * (1 + self.match.team_bonus(self.team, 'damage'))

    def defense_mult(self):
        m = 1.0
        if self.has('bastion'):
            m *= .75
        if self.has('psy'):
            m *= .8
        return m * (1 - self.match.team_bonus(self.team, 'defense'))

    def cooldown_mult(self):
        m = .7 if self.has('flux') else 1.0
        return m * (1 - self.match.team_bonus(self.team, 'cooldown'))

    def speed(self):
        s = self.data['speed'] * (1 + self.match.team_bonus(self.team, 'speed'))
        if self.status['slow'] > 0:
            s *= .55
        if self.type == 'eau' and self.match.stadium.in_river(self.position.x, self.position.z):
            s *= 1.05
        return s

    # ------------------------------------------------------------ PV
    def _refresh_bar(self):
        ratio = max(0, self.hp / self.max_hp)
        self.bar_fill.scale_x = self.bar_w * ratio

    def heal(self, amount):
        if not self.alive:
            return
        self.hp = min(self.max_hp, self.hp + amount)
        self._refresh_bar()

    def hurt(self, dmg, source=None, status=None, stun=0.0):
        """Applique des dégâts déjà calculés. Renvoie True si l'unité est mise K.O."""
        if not self.alive or self.invuln > 0:
            return False
        self.hp -= dmg
        self.last_hit_by = source
        self.last_hit_t = self.match.time
        self.creature.hit_flash(Vec4(1, .3, .25, .7) if self.local else Vec4(1, 1, 1, .8), .12)
        if status:
            kind, duration = status
            self.status[kind] = max(self.status[kind], duration)
        if stun:
            self.status['stun'] = max(self.status['stun'], stun)
            self.charge_t = 0
            self.creature.pivot.rotation_x = 0
        self._refresh_bar()
        if self.brain:
            self.brain.on_hit(source)
        if self.hp <= 0:
            self.die()
            return True
        return False

    def die(self):
        self.alive = False
        self.hp = 0
        self.charge_t = 0
        self._refresh_bar()
        self.creature.knock_out()
        self.creature.visible = True

    # ------------------------------------------------------------ progression
    def gain_xp(self, amount):
        if self.level >= C.MAX_LEVEL or self.team is None:
            return
        self.xp += amount
        while self.level < C.MAX_LEVEL and self.xp >= self.level * C.XP_PER_LEVEL:
            self.xp -= self.level * C.XP_PER_LEVEL
            ratio = self.hp / self.max_hp
            self.level += 1
            self.hp = self.max_hp * ratio + self.data['hp'] * C.LEVEL_BONUS
            self.hp = min(self.hp, self.max_hp)
            self._refresh_bar()
            if self.alive:
                self.level_fx()
            self.match.on_level_up(self)

    def level_fx(self):
        burst(self.match.root, self.position + Vec3(0, 1, 0), color.rgb(1, .95, .5), n=10, speed=3, size=.2)

    # ------------------------------------------------------------ actions
    def move(self, direction, dt, factor=1.0):
        if direction.length() < .01:
            return False
        p = self.position + direction * self.speed() * factor * dt
        p = self.match.stadium.collide(p, self.radius)
        p.y = self.match.stadium.walk_y(p.x, p.z)
        self.position = p
        return True

    def can_act(self):
        return self.alive and self.status['stun'] <= 0 and self.charge_t <= 0 and self.channel <= 0

    def in_attack_range(self, target, margin=0.0):
        rng = self.data['attack']['range']
        return (flat(target.position - self.position)).length() < rng + target.radius + margin

    def basic_attack(self, target, forward=None):
        """Attaque de base vers la cible (ou droit devant si pas de cible)."""
        if self.attack_cd > 0 or not self.can_act():
            return False
        a = self.data['attack']
        self.attack_cd = a['cooldown']
        self.attack_anim = .2
        if target is not None:
            d = flat(target.position - self.position)
            if not self.is_player and a['kind'] == 'ranged':
                # l'IA anticipe (plus ou moins bien) le déplacement de sa cible, avec une erreur de visée
                t = d.length() / a['speed']
                d = d + target.vel * t * random.uniform(.2, .9)
                ang = math.atan2(d.x, d.z) + math.radians(random.uniform(-C.AIM_ERROR, C.AIM_ERROR))
                d = Vec3(math.sin(ang), 0, math.cos(ang))
            d = d.normalized() if d.length() > .01 else self.facing()
        else:
            d = forward or self.facing()
        self.face(d)
        if a['kind'] == 'melee':
            if target is None:        # coup donné à l'aveugle (dans les hautes herbes...) : il touche quand même
                target = self.match.blind_target(self, a['range'], d)
            if target is not None:
                # le coup part après un court élan : la cible peut encore s'écarter
                self.match.pending_hits.append([C.MELEE_WINDUP, self, target, a['damage']])
            self.creature.pivot.rotation_x = -15
            return True
        start = self.position + Vec3(0, .9 * min(2, self.data['scale']), 0) + d * (self.radius + .3)
        self.match.projectiles.append(Projectile(
            self.match, self, start, d * a['speed'], a['damage'], a['size'], a['color'],
            shape=a.get('shape', 'sphere'), life=(a['range'] + 4) / a['speed'], status=a.get('status')))
        return True

    def try_special(self, target):
        sp = self.data.get('special')
        if not sp or self.special_cd > 0 or not self.can_act():
            return False
        self.special_cd = sp['cooldown'] * self.cooldown_mult()
        cast_special(self.match, self, target)
        return True

    def start_charge(self, d, speed, duration, dmg):
        self.charge_t = duration
        self.charge_dir = d
        self.charge_speed = speed
        self.charge_dmg = dmg
        self.charge_hit = set()

    # ------------------------------------------------------------ boucle
    def update(self, dt):
        if not self.match.authority:
            self.update_view(dt)
            return
        if not self.alive:
            self.creature.animate(dt)
            return
        self.attack_cd -= dt
        self.special_cd -= dt
        self.invuln -= dt
        self.channel -= dt
        self.attack_anim -= dt
        for k in self.buffs:
            self.buffs[k] -= dt
        for k in self.status:
            self.status[k] = max(0, self.status[k] - dt)

        if self.team:
            self.gain_xp(C.XP_PASSIVE * dt)
        regen = 1.0 if self.team else 0
        if self.has('flux'):
            regen += 4
        regen += self.match.team_bonus(self.team, 'regen')
        if regen and self.hp < self.max_hp:
            self.heal(regen * dt)
        if self.status['burn'] > 0:
            self.burn_tick -= dt
            if self.burn_tick <= 0:
                self.burn_tick = .6
                self.match.deal_damage(self.last_hit_by or self, self, 4, raw=True)
                if not self.alive:
                    return

        self._status_fx(dt)
        net_moving = self.brain.follow(dt) if self.net_driven else False   # Pokémon de l'invité
        moving = False
        if self.charge_t > 0:                      # Roulade / charge
            self.charge_t -= dt
            if not self.net_driven:                # l'invité fait rouler son Pokémon lui-même
                self.move(self.charge_dir, dt, self.charge_speed / max(1, self.speed()))
            self.creature.pivot.rotation_x += dt * 900
            moving = True
            for u in self.match.units:
                if u.alive and id(u) not in self.charge_hit and self.match.hostile(self, u):
                    if (flat(u.position - self.position)).length() < self.radius + u.radius + .4:
                        self.charge_hit.add(id(u))
                        self.match.deal_damage(self, u, self.charge_dmg)
            if self.charge_t <= 0:
                self.creature.pivot.rotation_x = 0
        elif self.status['stun'] > 0:
            self.creature.pivot.rotation_z = math.sin(self.status['stun'] * 60) * 6
            moving = net_moving
        else:
            self.creature.pivot.rotation_z = 0
            if self.brain:
                moving = self.brain.update(dt)
        self._finish_frame(dt, moving)

    def set_veiled(self, veiled):
        """Cache (ou montre) le Pokémon, sa barre de vie et son cercle d'équipe."""
        if veiled == self.veiled:
            return
        self.veiled = veiled
        for e in (self.creature.pivot, self.creature.shadow, self.bar, self.ring):
            if e is not None:
                e.visible = not veiled

    def revealed(self):
        """Vrai s'il vient d'attaquer ou d'être touché : l'herbe ne le cache plus."""
        r = C.BUSH['reveal']
        return self.attack_anim > -r or self.match.time - self.last_hit_t < r

    def _status_fx(self, dt):
        self._fx_t -= dt
        if self._fx_t <= 0 and not self.veiled:
            self._fx_t = .15
            for k, v in self.status.items():
                if v > 0:
                    burst(self.match.root, self.position + Vec3(0, 1.2 * self.data['scale'], 0), STATUS_COLOR[k],
                          n=1, speed=1, size=.15)

    def _finish_frame(self, dt, moving):
        self.moving = moving
        if self.attack_anim <= 0 and self.charge_t <= 0 and self.creature.pivot.rotation_x < 0:
            self.creature.pivot.rotation_x = 0
        self.creature.animate(dt, moving, self.attack_anim > 0 or self.channel > 0)
        p = self.creature.position
        if self._last is not None and dt > 0:        # vitesse réelle (utilisée pour viser)
            self.vel = Vec3((p.x - self._last.x) / dt, 0, (p.z - self._last.z) / dt)
        self._last = Vec3(p)

    def update_view(self, dt):
        """Chez l'invité : son Pokémon bouge localement, les autres suivent l'état reçu (netsync)."""
        if not self.alive:
            self.creature.animate(dt)
            return
        self.attack_anim -= dt
        self._status_fx(dt)
        if not self.local:
            if self.charge_t > 0:
                self.creature.pivot.rotation_x += dt * 900
            elif self.status['stun'] > 0:
                self.creature.pivot.rotation_z = math.sin(self.match.time * 60) * 6
            self.creature.animate(dt, self.moving, self.attack_anim > 0)
            return
        self.attack_cd -= dt
        self.invuln -= dt
        moving = False
        if self.charge_t > 0:                      # Roulade lancée par l'invité : il roule tout de suite
            self.charge_t -= dt
            self.move(self.charge_dir, dt, self.charge_speed / max(1, self.speed()))
            self.creature.pivot.rotation_x += dt * 900
            moving = True
            if self.charge_t <= 0:
                self.creature.pivot.rotation_x = 0
        elif self.status['stun'] > 0:
            self.creature.pivot.rotation_z = math.sin(self.match.time * 60) * 6
        else:
            self.creature.pivot.rotation_z = 0
            moving = self.brain.update(dt)
        self._finish_frame(dt, moving)


# ==================================================================== joueur
def input_vector():
    ix = (held_keys['d'] or held_keys['right arrow']) - (held_keys['q'] or held_keys['a'] or held_keys['left arrow'])
    iz = (held_keys['z'] or held_keys['w'] or held_keys['up arrow']) - (held_keys['s'] or held_keys['down arrow'])
    return Vec3(ix, 0, iz)


class PlayerBrain:
    """Contrôles clavier. Chez l'invité, les attaques sont envoyées à l'hôte (qui les
    exécute) ; les mouvements (déplacement, esquive, ruée, roulade) restent locaux."""
    slack = 0.0               # tolérance sur les temps de recharge (utile pour le joueur distant)

    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.moves = C.MOVESETS[unit.species]
        self.cd = {mv['key']: 0.0 for mv in self.moves}
        self.dash_cd = 0.0
        self.dash_t = 0.0
        self.dash_dir = Vec3(0, 0, 1)
        self.rush_t = 0.0
        self.rush_move = None
        self.target = None
        self.aim = None           # direction imposée (attaque reçue du joueur distant)

    def on_hit(self, source):
        pass

    def world_input(self):
        v = input_vector()
        if v.length() < .01:
            return v
        yaw = math.radians(self.m.cam_yaw)
        fwd = Vec3(math.sin(yaw), 0, math.cos(yaw))
        right = Vec3(math.cos(yaw), 0, -math.sin(yaw))
        return (fwd * v.z + right * v.x).normalized()

    def _dir_to_target(self):
        if self.aim is not None:
            return self.aim
        if self.target is not None:
            d = flat(self.target.position - self.u.position)
            if d.length() > .01:
                return d.normalized()
        return self.u.facing()

    def use(self, mv):
        u, m = self.u, self.m
        if not u.can_act() or self.rush_t > 0 or self.dash_t > 0:
            return
        kind = mv['kind']
        if kind == 'basic':
            if u.attack_cd > self.slack:
                return
            t = self.target if self.target is not None and u.in_attack_range(self.target, self.slack * 6) else None
            if not m.authority:                  # invité : l'hôte tirera pour nous
                u.attack_cd = u.data['attack']['cooldown']
                u.attack_anim = .2
                u.face(self._dir_to_target())
                m.net.send_use(mv['key'], t, self._dir_to_target())
                return
            u.attack_cd = min(u.attack_cd, 0)
            u.basic_attack(t, forward=self._dir_to_target())
            return
        if self.cd[mv['key']] > self.slack:
            return
        self.cd[mv['key']] = mv['cooldown'] * u.cooldown_mult()
        u.attack_anim = .2
        d = self._dir_to_target()
        u.face(d)
        m.announce_cast(u, mv['name'])
        if not m.authority:
            self._predict(mv, d)
            m.net.send_use(mv['key'], self.target, d)
            return
        self._perform(mv, d)

    def _predict(self, mv, d):
        """Invité : la partie « mouvement » de l'attaque se joue tout de suite chez lui."""
        u, kind = self.u, mv['kind']
        if kind == 'rush':
            self.rush_t, self.rush_move = mv['duration'], mv
        elif kind == 'spin':
            u.creature.pivot.rotation_y = 0
            u.creature.pivot.animate('rotation_y', 720, duration=.35)
        elif kind == 'special' and u.data['special']['kind'] == 'charge':
            sp = u.data['special']
            u.start_charge(d, sp['speed'], sp['duration'], 0)

    def _perform(self, mv, d):
        u, m, kind = self.u, self.m, mv['kind']
        start = u.position + Vec3(0, 1.0, 0) + d * .8
        if kind == 'rush':
            self.rush_t = mv['duration']
            self.rush_move = mv
            u.invuln = max(u.invuln, mv['duration'] + .1 + self.slack)
        elif kind == 'strike':
            p = self.target.position if self.target is not None else u.position + d * 7
            m.hazards.append(Zone(m, u, p, mv['radius'], mv['delay'], mv['damage'], mv['color'],
                                  status=mv.get('status'), style=mv.get('style', 'explosion')))
        elif kind == 'homing':
            m.projectiles.append(Projectile(m, u, start, d * mv['speed'], mv['damage'], mv['size'], mv['color'],
                                            shape=mv.get('shape', 'sphere'), homing=self.target, turn=.8, life=1.8,
                                            status=mv.get('status'), stun=mv.get('stun', 0.0)))
        elif kind == 'spin':
            u.spin()
            u.invuln = max(u.invuln, .3)
            m.hazards.append(Wave(m, u, u.position, 18, mv['radius'], mv['damage'],
                                  mv.get('color', color.rgb(.85, .85, .9)), status=mv.get('status'), start=.8))
            for p in m.projectiles:     # l'onde renvoie les projectiles proches
                if p.owner is not u and m.hostile(p.owner, u) and (flat(p.e.position - u.position)).length() < mv['radius']:
                    p.kill()
        elif kind == 'special':
            if self.aim is not None:
                u.face(self.aim)
            cast_special(m, u, self.target)

    def dash(self):
        u = self.u
        if self.dash_cd > 0 or not u.can_act() or self.rush_t > 0:
            return
        d = self.world_input()
        self.dash_dir = d if d.length() else u.facing()
        self.dash_t = C.PLAYER_DASH['time']
        self.dash_cd = C.PLAYER_DASH['cooldown']
        u.invuln = max(u.invuln, C.PLAYER_DASH['time'] + .08)
        u.face(self.dash_dir)
        if not self.m.authority:
            self.m.net.send_dash()

    def input(self, key):
        if key in ('space', 'shift', 'left shift', 'right shift'):
            self.dash()
            return
        for mv in self.moves:
            if key == mv['key']:
                self.use(mv)

    def _rush_contact(self):
        t = self.target
        if t is None:                 # ruée sans cible visible : on percute qui se trouve là (même caché)
            t = self.m.blind_target(self.u, self.u.radius + .5, None)
        if t is not None and t.alive and (flat(t.position - self.u.position)).length() < self.u.radius + t.radius + .5:
            if self.m.authority:
                self.m.deal_damage(self.u, t, self.rush_move['damage'])
            self.rush_t = 0

    def update(self, dt):
        u, m = self.u, self.m
        for k in self.cd:
            self.cd[k] -= dt
        self.dash_cd -= dt
        self.target = m.find_target(u, C.TARGET_RANGE)
        move = self.world_input()
        moving = move.length() > 0
        if self.rush_t > 0:                                  # ruée (Vive-Attaque...)
            self.rush_t -= dt
            d = self._dir_to_target()
            u.face(d)
            u.move(d, dt, self.rush_move['speed'] / u.speed())
            burst(m.root, u.position + Vec3(0, .6, 0), color.white, n=1, speed=.5, size=.2, life=.2)
            self._rush_contact()
            return True
        if self.dash_t > 0:                                  # esquive
            self.dash_t -= dt
            u.move(self.dash_dir, dt, C.PLAYER_DASH['speed'] / u.speed())
            if random.random() < .6:
                burst(m.root, u.position + Vec3(0, .5, 0), color.rgb(1, .95, .5), n=1, speed=.5, size=.2, life=.25)
            return True
        u.move(move, dt)
        if held_keys['j']:
            self.use(self.moves[0])
        if u.attack_anim > 0:
            u.face(self._dir_to_target())
        elif moving:
            u.face(move, dt, 16)
        return moving


class RemotePlayerBrain(PlayerBrain):
    """Chez l'hôte : le Pokémon de l'invité. Sa position arrive par le réseau (l'invité se
    déplace chez lui sans attendre) ; ses attaques arrivent sous forme de « touche + cible »
    et sont exécutées ici, là où se calculent les dégâts."""
    slack = .25

    def __init__(self, unit, match):
        super().__init__(unit, match)
        unit.net_driven = True
        self.net_pos = None
        self.net_rot = 0.0
        self.net_moving = False
        self.life = 0             # augmente à chaque téléportation (réapparition) : ignore les vieux paquets

    def receive(self, life, x, z, rot, moving):
        if life == self.life:
            self.net_pos = (x, z)
            self.net_rot = rot
            self.net_moving = moving

    def teleport(self, pos):
        self.life += 1
        self.net_pos = (pos.x, pos.z)
        self.net_moving = False

    def follow(self, dt):
        """Rejoint en douceur la dernière position reçue."""
        if self.net_pos is None:
            return False
        u = self.u
        p = u.creature.position
        x, z = self.net_pos
        dx, dz = x - p.x, z - p.z
        if dx * dx + dz * dz > 64:                # trop loin : on se place directement
            k = 1.0
        else:
            k = min(1.0, dt * 20)
        nx, nz = p.x + dx * k, p.z + dz * k
        u.creature.set_pos(nx, self.m.stadium.walk_y(nx, nz), nz)
        diff = (self.net_rot - u.creature.rotation_y + 180) % 360 - 180
        u.creature.rotation_y += diff * min(1.0, dt * 20)
        return self.net_moving

    def remote_use(self, key, target_uid, dx, dz):
        mv = next((m for m in self.moves if m['key'] == key), None)
        if mv is None:
            return
        m = self.m
        t = m.units[target_uid] if 0 <= target_uid < len(m.units) else None
        self.target = t if t is not None and t.alive and m.hostile(self.u, t) else None
        d = Vec3(dx, 0, dz)
        self.aim = d.normalized() if d.length() > .01 else None
        try:
            self.use(mv)
        finally:
            self.aim = None

    def remote_dash(self):
        self.u.invuln = max(self.u.invuln, C.PLAYER_DASH['time'] + .08 + self.slack)

    def update(self, dt):
        for k in self.cd:
            self.cd[k] -= dt
        self.dash_cd -= dt
        if self.rush_t > 0:                       # la ruée est jouée chez l'invité ; ici, les dégâts
            self.rush_t -= dt
            self._rush_contact()
        return self.net_moving


# ==================================================================== IA d'équipe
class BotBrain:
    AGGRO = 14

    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.target = None
        self.goal = None            # (clé de navigation, position, rayon)
        self.mode = None
        self.think_t = random.uniform(0, .5)
        self.wander = None
        self.wander_t = 0
        self.strafe = random.choice((-1, 1))
        self.stuck_t = 0

    def on_hit(self, source):
        if source is not None and source.alive and self.mode != 'retreat' and self.target is None:
            self.target = source

    # ------------------------------------------------------------ décisions
    def think(self):
        u, m = self.u, self.m
        if u.hp < u.max_hp * .3:
            self.mode = 'retreat'
        if self.mode == 'retreat':
            if u.hp > u.max_hp * .9:
                self.mode = None
            else:
                self.target = None
                self.goal = m.base_goal(u.team)
                return
        # adversaires proches
        best, score = None, 1e9
        for e in m.units:
            if e.alive and e.team and e.team != u.team and e not in m.hidden[u.team]:
                d = (flat(e.position - u.position)).length()
                if d < self.AGGRO:
                    s = d + 12 * e.hp / e.max_hp
                    if s < score:
                        best, score = e, s
        if best is not None:
            self.target = best
            return
        if self.target is not None and (not self.target.alive or self.target.team is not None):
            # une cible neutre n'est gardée que si elle fait partie de l'objectif en cours
            if not self.target.alive or (flat(self.target.position - u.position)).length() > 18:
                self.target = None
        self.goal = m.choose_goal(u, self.goal)
        if self.target is None and self.goal and self.goal[0].startswith('arena') and random.random() < .5:
            wild = m.nearest_wild(u.position, 13)
            if wild is not None:
                self.target = wild
        # arrivé sur un camp ou au Boss Pit : on attaque les neutres présents
        if self.target is None and self.goal and self.goal[0].startswith(('camp', 'wild', 'pit')):
            gp = self.goal[1]
            if (flat(u.position) - gp).length() < 14:
                for n in m.units:
                    if n.alive and n.team is None and (flat(n.position) - gp).length() < 12:
                        self.target = n
                        break

    # ------------------------------------------------------------ action
    def update(self, dt):
        u, m = self.u, self.m
        self.think_t -= dt
        if self.think_t <= 0:
            self.think_t = .35 + random.random() * .25
            self.think()
        t = self.target
        if t is not None and (not t.alive or (t.team is None and self.mode == 'retreat')
                              or t in m.hidden[u.team]):       # perdu de vue dans les hautes herbes
            self.target = t = None
        if t is not None:
            to_t = flat(t.position - u.position)
            d = to_t.length()
            dirn = to_t.normalized() if d > .01 else u.facing()
            rng = u.data['attack']['range'] + t.radius
            moved = False
            if d > rng * .85:
                moved = u.move(dirn, dt)
            elif u.data['attack']['kind'] == 'ranged' and d < rng * .4:
                moved = u.move(-dirn + Vec3(dirn.z, 0, -dirn.x) * self.strafe * .5, dt, .8)
            else:
                self.wander_t -= dt
                if self.wander_t <= 0:
                    self.wander_t = random.uniform(.8, 1.8)
                    self.strafe = random.choice((-1, 1))
                moved = u.move(Vec3(dirn.z, 0, -dirn.x) * self.strafe, dt, .5)
            u.face(dirn, dt, 14)
            if d < rng:
                u.basic_attack(t)
            self._use_special(t, d)
            return moved
        # pas de cible : objectif
        if self.goal is None:
            return False
        key, gp, gr = self.goal
        dist = (flat(u.position) - gp).length()
        if dist > gr:
            dirn = m.stadium.direction(key, gp, u.position, u.team)
            moved = u.move(dirn, dt)
            if moved:
                u.face(dirn, dt, 10)
            return moved
        # sur place : on se promène dans la zone (capture d'arène, attente au camp)
        self.wander_t -= dt
        if self.wander is None or self.wander_t <= 0 or (flat(u.position) - self.wander).length() < 1:
            a, r = random.uniform(0, math.tau), random.uniform(0, gr * .8)
            self.wander = gp + Vec3(math.sin(a) * r, 0, math.cos(a) * r)
            self.wander_t = random.uniform(1.5, 3)
        dv = flat(self.wander - u.position)
        if dv.length() > .5:
            u.move(dv.normalized(), dt, .6)
            u.face(dv.normalized(), dt, 8)
            return True
        return False

    def _use_special(self, t, d):
        u = self.u
        sp = u.data.get('special')
        if not sp or u.special_cd > 0:
            return
        k = sp['kind']
        ok = {'beam': d < sp.get('length', 12) * .9, 'wave': d < sp.get('radius', 8) * .8, 'zone': d < 13,
              'nova': d < 10, 'charge': 3 < d < 12}.get(k, False)
        if k == 'heal':
            ok = any(a.alive and a.team == u.team and a.hp < a.max_hp * .7 and
                     (flat(a.position - u.position)).length() < sp['radius'] for a in self.m.units)
        if ok:
            u.try_special(t)


# ==================================================================== neutres
class NeutralBrain:
    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.target = None
        self.idle_dir = Vec3(random.uniform(-1, 1), 0, random.uniform(-1, 1)).normalized()
        self.wild = bool(unit.camp and unit.camp.get('wild'))
        self.stroll = None
        self.stroll_t = random.uniform(1, 4)

    def on_hit(self, source):
        if source is not None and source.team and self.target is None:
            self.target = source
            # tout le camp se réveille
            for n in self.m.units:
                if n is not self.u and n.alive and n.camp is not None and n.camp is self.u.camp and n.brain.target is None:
                    n.brain.target = source

    def update(self, dt):
        u, m = self.u, self.m
        t = self.target
        leash = C.WILD['leash'] if self.wild else C.CAMP_LEASH + (10 if u.data['hp'] > 2000 else 0)
        if t is not None and (not t.alive or (flat(t.position) - u.home).length() > leash):
            self.target = t = None
        if t is not None:
            to_t = flat(t.position - u.position)
            d = to_t.length()
            dirn = to_t.normalized() if d > .01 else u.facing()
            rng = u.data['attack']['range'] + t.radius
            moved = False
            if d > rng * .85 and (flat(u.position) - u.home).length() < leash:
                moved = u.move(dirn, dt)
            u.face(dirn, dt, 10)
            if d < rng:
                u.basic_attack(t)
            sp = u.data.get('special')
            if sp and d < {'wave': sp.get('radius', 8) * .8, 'zone': 12, 'nova': 11, 'beam': 14}.get(sp['kind'], 0):
                u.try_special(t)
            return moved
        # retour au camp ; soins seulement après quelques secondes sans combat
        calm = m.time - u.last_hit_t > 3
        back = flat(u.home - u.position)
        if back.length() > (C.WILD['wander'] + 1 if self.wild else .8):
            u.move(back.normalized(), dt, 1.3)
            u.face(back.normalized(), dt, 10)
            if calm:
                u.heal(u.max_hp * .15 * dt)
            return True
        if calm:
            u.heal(u.max_hp * .15 * dt)
        if self.wild:                   # les petits sauvages se promènent autour de leur coin
            self.stroll_t -= dt
            if self.stroll_t <= 0:
                self.stroll_t = random.uniform(2.5, 6)
                a, r = random.uniform(0, math.tau), random.uniform(0, C.WILD['wander'])
                self.stroll = u.home + Vec3(math.sin(a) * r, 0, math.cos(a) * r)
            if self.stroll is not None:
                dv = flat(self.stroll - u.position)
                if dv.length() > .4:
                    u.move(dv.normalized(), dt, .45)
                    u.face(dv.normalized(), dt, 6)
                    return True
                self.stroll = None
            return False
        u.face(self.idle_dir, dt, 3)
        return False
