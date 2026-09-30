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

from ursina import Vec3, Vec4, color, held_keys

from game import config as C
from game.pokemon.combat import Beam, Projectile, Wave, Zone, cast_special, flat, heal_area
from game.pokemon.creatures import Creature
from game.pokemon.healthbar import HealthBar
from game.world import fx
from game.world.fx import burst
from game.world.geometry import flat_circle

STATUS_COLOR = {'burn': color.rgb(1, .5, .15), 'slow': color.rgb(.55, .9, 1), 'stun': color.rgb(1, .95, .3)}
LOCAL_BAR = color.rgb(.3, .95, .35)          # barre de vie de son propre Pokémon
ALLY_BAR = color.rgb(.35, .9, 1)             # barre de vie de l'autre joueur humain
LOCAL_BADGE = color.rgb(1, .62, .15)         # badge de niveau de son propre Pokémon


class Unit:
    def __init__(self, match, species, team, pos, role=None, human=None, local=False, camp=None):
        self.match = match
        self.species = species            # lignée (Pokémon choisi) : 'pikachu', 'salameche'...
        self.form = species               # forme actuelle (évolue avec le niveau) : 'raichu'...
        self.data = C.SPECIES[species]
        self.name = self.data['name']
        self.type = self.data['type']
        self.team = team                  # 'rouge', 'bleu' ou None (neutre)
        self.trait = C.TRAITS[species][0] if team and species in C.TRAITS else None   # talent de la lignée
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
        badge = LOCAL_BADGE if local else bar_col
        label = f'J{human + 1}' if self.is_player and not local else None   # nom du Pokémon de l'autre joueur
        self.hb = HealthBar(self.creature, h, w, bar_col, badge, label, ALLY_BAR)
        self.bar = self.hb.root
        self.ring = getattr(self, 'ring', None)
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

    def _aura(self, trait):
        """Vrai si un Pokémon de l'équipe ayant ce talent d'aura (lui compris) est tout près."""
        for a in self.match.auras.get(self.team, ()):
            if a.trait == trait and a.alive and (flat(a.position - self.position)).length() < C.AURA_RANGE:
                return True
        return False

    def hp_ratio(self):
        return self.hp / self.max_hp if self.max_hp else 0

    # ------------------------------------------------------------ terrain
    def zone(self):
        """Terrain où se trouve le Pokémon : type de l'arène, 'riviere' ou None (recalculé 1 fois / image)."""
        t = self.match.time
        if getattr(self, '_zone_t', None) != t:
            p = self.position
            a = self.match.arena_at(p)
            # dans l'eau (pas sur un pont : le tablier est au-dessus du niveau du sol)
            wet = p.y < 0 and self.match.stadium.in_river(p.x, p.z)
            self._zone = a['type'] if a is not None else 'riviere' if wet else None
            self._zone_t = t
        return self._zone

    def zone_mod(self, key):
        """Effet du terrain sur ce Pokémon (voir C.ZONE_EFFECTS) : 'dmg', 'taken' ou 'speed'."""
        z = self.zone()
        return C.zone_effect(z, self.type).get(key, 0.0) if z else 0.0

    def damage_mult(self):
        m = 1 + C.LEVEL_BONUS * (self.level - 1)
        if self.has('braise'):
            m *= 1.25
        if self.has('psy'):
            m *= 1.2
        t = self.trait
        if t is not None:                                    # talents
            r = self.hp_ratio()
            if (t == 'Brasier' and r < .4) or (t == 'Cran' and r < .5):
                m *= 1.25 if t == 'Brasier' else 1.3
            elif t == 'Éruption' and r > .7:
                m *= 1.2
            if self.has('impudence'):
                m *= 1.25
        if self.team and self._aura('Plus'):
            m *= 1.1
        m *= 1 + self.zone_mod('dmg')
        return m * (1 + self.match.team_bonus(self.team, 'damage'))

    def defense_mult(self):
        m = 1.0
        if self.has('bastion'):
            m *= .75
        if self.has('psy'):
            m *= .8
        if self.trait == 'Fermeté':
            m *= .85
        elif self.trait == 'Multiécaille' and self.hp_ratio() > .8:
            m *= .7
        if self.team and self._aura('Écran Neige'):
            m *= .9
        m *= 1 + self.zone_mod('taken')
        return m * (1 - self.match.team_bonus(self.team, 'defense'))

    def cooldown_mult(self):
        m = .7 if self.has('flux') else 1.0
        return m * (1 - self.match.team_bonus(self.team, 'cooldown'))

    def speed(self):
        s = self.data['speed'] * (1 + self.match.team_bonus(self.team, 'speed'))
        if self.status['slow'] > 0:
            s *= .55
        s *= 1 + self.zone_mod('speed')                 # terrain : rivière, arène d'un autre type...
        if self.trait == 'Torrent' and self.zone() == 'riviere':
            s *= 1.1
        if self.trait == 'Engrais' and self.bush:
            s *= 1.3
        return s

    def regen(self):
        """PV rendus par seconde (hors base) : récupération, bonus et talents."""
        r = 1.0 if self.team else 0
        if self.has('flux'):
            r += 4
        if self.trait == 'Photosynthèse':
            r += 3
        elif self.trait == 'Torrent' and self.zone() == 'riviere':
            r += 4
        return r + self.match.team_bonus(self.team, 'regen')

    # ------------------------------------------------------------ PV
    def _refresh_bar(self):
        self.hb.set(self.hp, self.max_hp)
        self.hb.set_level(self.level)

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
        while self.level < C.MAX_LEVEL and self.xp >= C.xp_to_next(self.level):
            self.xp -= C.xp_to_next(self.level)
            ratio = self.hp / self.max_hp
            self.level += 1
            self.hp = self.max_hp * ratio + self.data['hp'] * C.LEVEL_BONUS
            self.hp = min(self.hp, self.max_hp)
            self._refresh_bar()
            if self.alive:
                self.level_fx()
            self.match.on_level_up(self)
            self.check_evolution()

    def level_fx(self):
        burst(self.match.root, self.position + Vec3(0, 1, 0), color.rgb(1, .95, .5), n=10, speed=3, size=.2)

    # ------------------------------------------------------------ évolution
    def check_evolution(self, show=True):
        """Prend la forme correspondant au niveau (évolution, ou retour à la forme de base quand
        une nouvelle partie commence)."""
        if not self.team or self.species not in C.EVOLUTIONS:
            return
        form = C.form_for(self.species, self.level)
        if form != self.form:
            old = self.name
            self._set_form(form)
            up = show and C.evolution_line(self.species).index(form) > 0
            if up and self.alive:
                self._evolution_fx()
            self.match.on_evolve(self, old if up else None)

    def _set_form(self, form):
        """Remplace le modèle 3D et les caractéristiques par celles de la nouvelle forme."""
        from ursina import destroy
        ratio = max(0.0, self.hp / self.max_hp)
        old = self.creature
        self.form = form
        self.data = C.SPECIES[form]
        self.name, self.type, self.radius = self.data['name'], self.data['type'], self.data['radius']
        c = Creature(form, parent=self.match.root, position=old.position, scale=self.data['scale'])
        c.rotation_y = old.rotation_y
        self.bar.parent = c
        self.bar.y = self.data['scale'] * 1.5 + .5
        if self.ring is not None:
            destroy(self.ring)
            tc = C.TEAMS[self.team]['color']
            self.ring = flat_circle(c, self.radius + .35, color.rgba(tc[0], tc[1], tc[2], .75), y=.05)
        if not self.alive:
            c.knock_out()
        c.enabled, c.visible = old.enabled, old.visible
        self.creature = c
        destroy(old)
        veiled, self.veiled = self.veiled, False
        self.set_veiled(veiled)
        self.hp = self.max_hp * ratio if self.alive else 0
        self._refresh_bar()
        if hasattr(self.brain, 'set_form'):
            self.brain.set_form()

    def _evolution_fx(self):
        """Évolution : la silhouette devient blanche et lumineuse, grandit d'un coup, et une colonne
        de lumière monte dans une pluie d'étoiles."""
        c, s = self.creature, self.data['scale']
        c.hit_flash(Vec4(1, 1, 1, 1), .7)
        c.pivot.scale = s * .6
        c.pivot.animate_scale(s * 1.12, duration=.35)
        c.pivot.animate_scale(s, duration=.25, delay=.35)
        P = fx.PARTICLES
        if P is None or (flat(self.position) - flat(self.match.cam_target)).length() > 60:
            return
        p = self.position
        col = C.TYPES[self.type]['light']
        fx.ground_ring(P, (p.x, p.y + .1, p.z), (1, 1, .9), .5, 5, .7, alpha=.9)
        fx.ground_glow(P, (p.x, p.y, p.z), col, 3.5, .9, alpha=.5)
        P.emit((p.x, p.y + 1.2 * s, p.z), (1, 1, .95), size=4.5 * s, life=.35, grow=1.6, alpha=.75)
        P.emit((p.x, p.y + 3, p.z), (1, .98, .85), size=2.2, life=.9, vel=(0, 5, 0), tex='streak', mode='stretch',
               stretch=.8, alpha=.6)
        for i in range(36):
            a = math.tau * i / 36
            r = random.uniform(.3, 1.2) * s
            P.emit((p.x + math.sin(a) * r, p.y + random.uniform(.2, 1.8) * s, p.z + math.cos(a) * r), (1, 1, .9),
                   col2=(col[0], col[1], col[2]), size=random.uniform(.25, .5), life=random.uniform(.8, 1.4),
                   vel=(math.sin(a) * 1.5, random.uniform(2, 5), math.cos(a) * 1.5), tex='star', spin=fx.rnd(5))

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
                lead = getattr(self.brain, 'lead', (.2, .9))          # l'IA experte vise mieux
                err = getattr(self.brain, 'aim_error', C.AIM_ERROR)
                d = d + target.vel * t * random.uniform(*lead)
                ang = math.atan2(d.x, d.z) + math.radians(random.uniform(-err, err))
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
        status, stun = a.get('status'), 0.0
        if self.trait == 'Corps Gel':                       # talents qui touchent l'attaque de base
            status = ('slow', 1.0)
        elif self.trait == 'Statik' and random.random() < .2:
            stun = .5
        self.match.projectiles.append(Projectile(
            self.match, self, start, d * a['speed'], a['damage'], a['size'], a['color'],
            shape=a.get('shape', 'sphere'), life=(a['range'] + 4) / a['speed'], status=status, stun=stun))
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
        self.hb.tick(dt)
        self.hb.set_level(self.level)         # le niveau peut aussi changer par le réseau ou une nouvelle partie
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

        regen = self.regen()
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
            self._roll_dust()
            for u in self.match.units:
                if u.alive and id(u) not in self.charge_hit and self.match.hostile(self, u):
                    if (flat(u.position - self.position)).length() < self.radius + u.radius + .4:
                        self.charge_hit.add(id(u))
                        self.match.deal_damage(self, u, self.charge_dmg, contact=True)
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
        if self.trait == 'Spectral':                       # attaquer ne le trahit pas
            return self.match.time - self.last_hit_t < r
        return self.attack_anim > -r or self.match.time - self.last_hit_t < r

    def _status_fx(self, dt):
        self._fx_t -= dt
        if self._fx_t <= 0 and not self.veiled and fx.PARTICLES:
            self._fx_t = .07
            P, p, s = fx.PARTICLES, self.position, self.data['scale']
            for k, v in self.status.items():
                if v <= 0:
                    continue
                if k == 'burn':               # petites flammes qui lèchent le Pokémon
                    fx.flame(P, (p.x + fx.rnd(.4 * s), p.y + fx.ru(.3, 1.1) * s, p.z + fx.rnd(.4 * s)),
                             (0, 1.2, 0), s=.45 * s, life=.4, rise=2)
                elif k == 'slow':             # givre : flocons et buée froide
                    P.emit((p.x + fx.rnd(.6 * s), p.y + fx.ru(.2, 1.3) * s, p.z + fx.rnd(.6 * s)), (.85, .97, 1),
                           size=.22, life=.6, vel=(0, -.4, 0), tex='star', spin=fx.rnd(3))
                else:                         # étourdi : étoiles qui tournent au-dessus de la tête
                    a = self.match.time * 6
                    for j in range(3):
                        b = a + j * math.tau / 3
                        P.emit((p.x + math.sin(b) * .5 * s, p.y + 1.45 * s, p.z + math.cos(b) * .5 * s),
                               STATUS_COLOR[k], size=.3, life=.12, tex='star')

    def _roll_dust(self):
        """La roulade soulève la poussière."""
        if fx.PARTICLES and random.random() < .7:
            p = self.position
            fx.smoke(fx.PARTICLES, (p.x, p.y + .2, p.z), (fx.rnd(1), .6, fx.rnd(1)), s=1.2, life=.6, alpha=.35,
                     col=fx.DUST, col2=(.78, .72, .64))

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
                self._roll_dust()
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
            self._roll_dust()
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
        self.moves = C.moves_for(unit.species, unit.form)
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

    def set_form(self):
        """Évolution : nouvelles attaques (les temps de recharge en cours sont conservés)."""
        self.moves = C.moves_for(self.u.species, self.u.form)

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
        if mv.get('locked'):
            if u.local:
                m.game.banner.show(f"{mv['name']} : débloquée au niveau {mv['unlock']} (évolution)", 1.5,
                                   text_color=color.rgb(.8, .85, 1))
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
        elif kind == 'blink':                         # l'invité se téléporte tout de suite
            u.position = self._blink_target(mv, d)

    def _blink_target(self, mv, d):
        """Arrivée d'une téléportation : droit devant, sans traverser les murs."""
        u, st = self.u, self.m.stadium
        here = flat(u.position)
        dest = st.reach(here, here + d * mv['distance'])
        if (dest - here).length() > 1.2:
            dest -= d * .8                            # on s'arrête avant le mur
        else:
            dest = here
        p = st.collide(Vec3(dest.x, 0, dest.z), u.radius)
        p.y = st.walk_y(p.x, p.z)
        return p

    def _perform(self, mv, d):
        u, m, kind = self.u, self.m, mv['kind']
        start = u.position + Vec3(0, 1.0, 0) + d * .8
        if kind == 'rush':
            self.rush_t = mv['duration']
            self.rush_move = mv
            u.invuln = max(u.invuln, mv['duration'] + .1 + self.slack)
        elif kind == 'strike':
            p = self.target.position if self.target is not None else u.position + d * 7
            p = m.stadium.reach(u.position, p)            # pas de frappe au cœur d'un mur
            m.hazards.append(Zone(m, u, p, mv['radius'], mv['delay'], mv['damage'], mv['color'],
                                  status=mv.get('status'), style=mv.get('style', 'explosion'),
                                  stun=mv.get('stun', 0.0)))
        elif kind == 'beam':
            m.hazards.append(Beam(m, u, u.position + d * u.radius, d, mv['length'], mv['width'], mv['delay'],
                                  mv['damage'], mv['color'], mv.get('status')))
            u.channel = mv['delay'] + .35
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
        elif kind == 'blink':                         # téléportation : disparaît puis frappe à l'arrivée
            p = self._blink_target(mv, d)
            fx.impact(u.type, u.position + Vec3(0, 1, 0), .5)
            if not u.net_driven:
                u.position = p
            u.invuln = max(u.invuln, .25 + self.slack)
            m.hazards.append(Wave(m, u, p, 22, mv['radius'], mv['damage'], mv['color'], start=.5))
        elif kind == 'heal':
            heal_area(m, u, mv['heal'], mv['radius'], mv['color'])
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
        self.dash_t = C.PLAYER_DASH['time'] * (2 if u.trait == 'Téléport' else 1)   # talent : esquive longue
        self.dash_cd = C.PLAYER_DASH['cooldown']
        u.invuln = max(u.invuln, self.dash_t + .08)
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
                mv = self.rush_move
                self.m.deal_damage(self.u, t, mv['damage'], mv.get('status'), mv.get('stun', 0.0), contact=True)
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
            if fx.PARTICLES:                                  # traits de vitesse et poussière
                p = u.position
                fx.PARTICLES.emit((p.x + fx.rnd(.3), p.y + fx.ru(.3, 1.2), p.z + fx.rnd(.3)), (1, 1, 1),
                                  size=.12, life=.18, vel=(-d.x * 14, 0, -d.z * 14), mode='stretch', stretch=.03,
                                  alpha=.7)
                fx.smoke(fx.PARTICLES, (p.x, p.y + .2, p.z), (-d.x, .4, -d.z), s=.8, life=.4, alpha=.25,
                         col=fx.DUST, col2=(.8, .76, .7))
            self._rush_contact()
            return True
        if self.dash_t > 0:                                  # esquive
            self.dash_t -= dt
            u.move(self.dash_dir, dt, C.PLAYER_DASH['speed'] / u.speed())
            if fx.PARTICLES:                                  # esquive : traînée lumineuse et poussière
                p = u.position
                fx.PARTICLES.emit((p.x, p.y + .7, p.z), (1, .95, .6), size=.35, life=.2,
                                  vel=(-self.dash_dir.x * 8, 0, -self.dash_dir.z * 8), mode='stretch', stretch=.04,
                                  alpha=.6)
                if random.random() < .5:
                    fx.smoke(fx.PARTICLES, (p.x, p.y + .2, p.z), (0, .5, 0), s=.7, life=.4, alpha=.22,
                             col=fx.DUST, col2=(.8, .76, .7))
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
        k = 2 if self.u.trait == 'Téléport' else 1
        self.u.invuln = max(self.u.invuln, C.PLAYER_DASH['time'] * k + .08 + self.slack)

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
        self.blind = 0.0            # temps passé sans voir sa cible (mur entre les deux)

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
                if d < self.AGGRO and m.can_see(u, e):
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
            if not m.can_see(u, t):                   # un mur les sépare : on contourne, sans tirer
                self.blind += dt
                if self.blind > 2.0:                  # toujours caché : on laisse tomber
                    self.target, self.blind = None, 0.0
                moved = u.move(dirn, dt)
                u.face(dirn, dt, 14)
                return moved
            self.blind = 0.0
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
            sees = m.can_see(u, t)
            if (d > rng * .85 or not sees) and (flat(u.position) - u.home).length() < leash:
                moved = u.move(dirn, dt)
            u.face(dirn, dt, 10)
            if not sees:                              # pas d'attaque à travers les murs
                return moved
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
