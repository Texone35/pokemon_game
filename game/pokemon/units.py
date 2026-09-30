"""Pokémon présents sur le terrain : joueurs, IA des deux équipes et Pokémon neutres.

Unit              : état commun (stats, PV, niveau, statuts, bonus, déplacement, attaques)
PlayerBrain       : contrôles d'un joueur (clavier + visée à la souris)
RemotePlayerBrain : chez l'hôte, le Pokémon de l'invité (positions et attaques reçues par le réseau)
BotBrain          : IA d'équipe (capture d'arènes, combats, jungle, boss, repli)
NeutralBrain      : Pokémon neutres (restent à leur camp, ripostent quand on les attaque)

Stats : calculées à partir des valeurs d'équilibrage (game/balance/, voir kit.py), puis
modifiées par les bonus (buffs de la jungle, objets...) : Unit.recalc_stats() les recalcule
quand quelque chose change (niveau, évolution, bonus gagné ou perdu).

En partie à deux, l'hôte fait autorité (dégâts, IA, score). Chez l'invité
(match.authority == False), les unités sont des « marionnettes » placées d'après
l'état reçu (voir netsync.py), sauf son propre Pokémon qu'il déplace lui-même.
"""
import math
import random

from ursina import Entity, Vec3, Vec4, color, held_keys

from game import config as C
from game.pokemon import kit, moves
from game.pokemon.combat import Projectile, flat
from game.pokemon.creatures import Creature
from game.pokemon.healthbar import HealthBar
from game.world import fx
from game.world.fx import burst
from game.world.geometry import destroy_tree, flat_circle

STATUS_COLOR = {'burn': color.rgb(1, .5, .15), 'slow': color.rgb(.55, .9, 1), 'stun': color.rgb(1, .95, .3)}
LOCAL_BAR = color.rgb(.3, .95, .35)          # barre de vie de son propre Pokémon
ALLY_BAR = color.rgb(.35, .9, 1)             # barre de vie de l'autre joueur humain
LOCAL_BADGE = color.rgb(1, .62, .15)         # badge de niveau de son propre Pokémon
ANIM_RANGE2 = 60.0 ** 2          # au-delà de cette distance de la caméra, pas d'animation ni d'effets
EFFECT_KEYS = ('dmg', 'taken', 'cdr', 'regen', 'regen_pct', 'as', 'ms', 'lifesteal', 'recoil', 'thorns', 'sash',
               'heal_boost')


class Unit:
    def __init__(self, match, species, team, pos, role=None, human=None, local=False, camp=None, build=None,
                 kind=None):
        self.match = match
        self.species = species            # lignée (Pokémon choisi) : 'pikachu', 'salameche'...
        self.form = species               # forme actuelle (évolue avec le niveau) : 'raichu'...
        self.build = build or 'standard'  # façon de jouer la lignée (voir balance/moves.py : BUILDS)
        self.data = C.SPECIES[species]
        self.name = self.data['name']
        self.type = self.data['type']
        self.team = team                  # 'rouge', 'bleu' ou None (neutre)
        self.kind = kind or ('pokemon' if team else 'neutral')
        self.trait = C.TRAITS[species][0] if self.kind == 'pokemon' and species in C.TRAITS else None
        self.trait_cfg = C.TRAITS[species][2] if self.trait else {}
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
        self.buffs = {}
        self.items = []                   # objets tenus (voir balance/items.py)
        self.gold = C.START_GOLD if self.kind == 'pokemon' else 0     # Poké Dollars
        self.aggro_t = -99.0              # dernier coup porté à un Pokémon adverse (priorité des tours)
        self.transform_kind = None        # transformation en cours : 'mega', 'dynamax' ou None
        self.transform_t = 0.0            # temps restant de la transformation
        self.transform_cd = 0.0           # recharge avant la prochaine transformation
        self.size_mult = 1.0              # Dynamax : le Pokémon grandit
        self.sash_cd = 0.0                # Ceinture Force : délai avant de pouvoir resservir
        self.stats, self.mods = {}, dict.fromkeys(EFFECT_KEYS, 0.0)
        self._max_hp = 0
        self.spawn_min = 0.0              # neutres : minute de jeu à laquelle ils sont apparus
        self.cd = {}
        self.home = Vec3(pos[0], 0, pos[1])
        self.refresh_moves()
        self.recalc_stats()
        self.creature = Creature(species, parent=match.root, position=self.home, scale=self.data['scale'])
        self.ring = None
        if team:
            tc = C.TEAMS[team]['color']
            self.ring = flat_circle(self.creature, self.radius + .35, color.rgba(tc[0], tc[1], tc[2], .75), y=.05)
        h = 4.6 if self.kind == 'tower' else self.data['scale'] * 1.5 + .5
        bar_col = C.TEAMS[team]['color'] if team else color.rgb(1, .75, .2)
        if self.is_player:
            bar_col = LOCAL_BAR if local else ALLY_BAR
        w = 3.2 if self.kind == 'neutral' and self._max_hp >= 1000 else 2.4 if self.kind == 'tower' else \
            1.1 if self.kind == 'minion' else 1.6
        badge = LOCAL_BADGE if local else bar_col
        label = f'J{human + 1}' if self.is_player and not local else None   # nom du Pokémon de l'autre joueur
        self.hb = HealthBar(self.creature, h, w, bar_col, badge, label, ALLY_BAR)
        if self.kind in ('tower', 'minion'):
            self.hb.badge.enabled = False                 # pas de niveau pour les tours et les sbires
        self.bar = self.hb.root
        self.reset()

    # ------------------------------------------------------------ stats
    def _effects(self):
        """Tous les bonus actifs (buffs, objets...) : dictionnaires d'effets."""
        for k, t in self.buffs.items():
            if t > 0 and k in C.BUFFS:
                yield C.BUFFS[k].get('effects', {})
        for it in self.items:
            yield C.ITEMS[it]['effects']
        if self.transform_kind == 'dynamax':
            yield C.TRANSFORMS['dynamax']['effects']

    def recalc_stats(self):
        """Recalcule les stats (niveau, forme, bonus). Garde les PV perdus."""
        if self.kind == 'pokemon':
            st = kit.team_stats(self.species, self.form, self.level, self.build)
        elif self.kind == 'tower':
            st = kit.scaled_stats(C.TOWER['stats'], C.TOWER['growth'], self.spawn_min)
        elif self.kind == 'minion':
            cfg = C.MINIONS[self.species]
            st = kit.scaled_stats(cfg['stats'], C.MINION_GROWTH, self.spawn_min)
        else:
            st = kit.neutral_stats(self.species, self.spawn_min)
        mods = dict.fromkeys(EFFECT_KEYS, 0.0)
        pct, flat_ = dict.fromkeys(C.STATS, 0.0), dict.fromkeys(C.STATS, 0.0)
        for e in self._effects():
            for k, v in e.get('stats', {}).items():
                pct[k] += v
            for k, v in e.get('flat', {}).items():
                flat_[k] += v
            for k in EFFECT_KEYS:
                mods[k] += e.get(k, 0.0)
        self.stats = {k: (st[k] + flat_[k]) * (1 + pct[k]) for k in C.STATS}
        self.mods = mods
        old = self._max_hp
        self._max_hp = max(1, round(self.stats['hp'] * self.hp_factor))
        if old and getattr(self, 'alive', False):
            self.hp = min(self._max_hp, self.hp + max(0, self._max_hp - old))
        elif old:
            self.hp = min(getattr(self, 'hp', self._max_hp), self._max_hp)
        spe = self.stats['spe']
        self.as_mult = kit.attack_speed(spe) * (1 + mods['as'])
        if self.kind == 'pokemon':
            self.move_base = kit.move_speed(spe) * (1 + mods['ms'])
        elif self.kind == 'tower':
            self.move_base = 0.0
        elif self.kind == 'minion':
            self.move_base = C.MINIONS[self.species]['move']
        else:
            self.move_base = C.NEUTRALS[self.species]['move'] * (1 + mods['ms'])

    def refresh_moves(self):
        """Auto-attaque et attaques de la forme actuelle (débloquées selon le niveau)."""
        if self.kind == 'pokemon':
            self.auto = kit.auto_for(self.species, self.form, self.build)
            self.moves = kit.moves_for(self.species, self.form, self.level, self.build)
        elif self.kind == 'tower':
            self.auto = {'kind': 'ranged', 'range': C.TOWER['range'], 'cooldown': C.TOWER['interval'], 'power': 0}
            self.moves = []
        elif self.kind == 'minion':
            self.auto = C.MINIONS[self.species]['auto']
            self.moves = []
        else:
            self.auto = C.NEUTRALS[self.species]['auto']
            self.moves = kit.neutral_moves(self.species)
        for mv in self.moves:
            self.cd.setdefault(mv['slot'], 0.0)

    def get_move(self, slot):
        return next((mv for mv in self.moves if mv['slot'] == slot), None)

    @property
    def max_hp(self):
        return self._max_hp

    def attack_interval(self):
        return self.auto['cooldown'] / max(.1, self.as_mult)

    # ------------------------------------------------------------ état
    def reset(self, pos=None):
        if self.kind != 'pokemon':
            self.spawn_min = self.match.time / 60
            self.recalc_stats()
        self.hp = self.max_hp
        self.alive = True
        self.respawn_t = 0.0
        self.attack_cd = 0.0
        self.cast_lock = 0.0
        if self.kind != 'pokemon':
            for k in self.cd:
                self.cd[k] = random.uniform(2, 5)
        self.status = {'burn': 0.0, 'slow': 0.0, 'stun': 0.0}
        self.burn_tick = 0.0
        if self.buffs:
            self.buffs = {}
            self.recalc_stats()
        self.invuln = 0.0
        self.channel = 0.0
        self.guard_t, self.guard_red = 0.0, 0.0
        self.charge_t = 0.0
        self.charge_dir = Vec3(0, 0, 1)
        self.charge_dmg, self.charge_cat = 0, 'phys'
        self.charge_hit = set()
        self.rush_t, self.rush_mv, self.rush_dir, self.rush_target, self.rush_dmg = 0.0, None, Vec3(0, 0, 1), None, 0
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
        self.creature.pivot.scale = self.data['scale'] * self.size_mult
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

    def facing(self):
        a = math.radians(self.creature.rotation_y)
        return Vec3(math.sin(a), 0, math.cos(a))

    def face(self, d, dt=None, speed=12):
        if dt is not None and self.kind in ('minion', 'neutral'):      # loin de la caméra : inutile
            p, f = self.creature.position, self.match.cam_target
            if (p.x - f.x) ** 2 + (p.z - f.z) ** 2 > ANIM_RANGE2:
                return
        self.creature.face((d.x, d.z), dt, speed)

    def pulse(self):
        s = self.data['scale'] * self.size_mult
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

    def add_buff(self, buff, duration):
        self.buffs[buff] = max(self.buffs.get(buff, 0.0), duration)
        self.recalc_stats()

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
        """Bonus de dégâts infligés (buffs, talents, terrain, arènes) : multiplicateur."""
        m = 1 + self.mods['dmg']
        t, tc = self.trait, self.trait_cfg
        if t is not None:                                    # talents
            r = self.hp_ratio()
            if t in ('Brasier', 'Cran') and r < tc['below']:
                m *= 1 + tc['dmg']
            elif t == 'Éruption' and r > tc['above']:
                m *= 1 + tc['dmg']
        if self.team and self._aura('Plus'):
            m *= 1 + C.TRAITS['wattouat'][2]['dmg']
        m *= 1 + self.zone_mod('dmg')
        w = self.match.own_weather(self)
        if w is not None:
            m *= 1 + w.get('boost', {}).get(self.type, 0.0)
        return m * (1 + self.match.team_bonus(self.team, 'damage'))

    def defense_mult(self):
        """Bonus de réduction des dégâts subis : multiplicateur (< 1 = moins de dégâts)."""
        m = max(.3, 1 + self.mods['taken'])
        if self.guard_t > 0:
            m *= 1 - self.guard_red
        if self.trait == 'Fermeté':
            m *= 1 + self.trait_cfg['taken']
        elif self.trait == 'Multiécaille' and self.hp_ratio() > self.trait_cfg['above']:
            m *= 1 + self.trait_cfg['taken']
        if self.team and self._aura('Écran Neige'):
            m *= 1 + C.TRAITS['sorbebe'][2]['taken']
        m *= 1 + self.zone_mod('taken')
        return m * (1 - self.match.team_bonus(self.team, 'defense'))

    def cooldown_mult(self):
        return max(.4, 1 - self.mods['cdr'] - self.match.team_bonus(self.team, 'cooldown'))

    def speed(self):
        s = self.move_base * (1 + self.match.team_bonus(self.team, 'speed'))
        if self.status['slow'] > 0:
            s *= C.SLOW_FACTOR
        s *= 1 + self.zone_mod('speed')                 # terrain : rivière, arène d'un autre type...
        if self.trait == 'Torrent' and self.zone() == 'riviere':
            s *= 1 + self.trait_cfg['speed']
        if self.trait == 'Engrais' and self.bush:
            s *= 1 + self.trait_cfg['speed']
        w = self.match.own_weather(self)
        if w is not None:
            s *= 1 + w.get('ms', 0.0)
        return s

    def regen(self):
        """PV rendus par seconde (hors base) : récupération, bonus et talents."""
        r = C.REGEN if self.kind == 'pokemon' else 0
        r += self.mods['regen'] + self.mods['regen_pct'] * self.max_hp
        if self.trait == 'Photosynthèse':
            r += self.trait_cfg['regen']
        elif self.trait == 'Torrent' and self.zone() == 'riviere':
            r += self.trait_cfg['regen']
        w = self.match.own_weather(self) if self.kind == 'pokemon' else None
        if w is not None:
            r += w.get('heal_pct', 0.0) * self.max_hp
        return r + self.match.team_bonus(self.team, 'regen')

    # ------------------------------------------------------------ PV
    def _refresh_bar(self):
        self.hb.set(self.hp, self.max_hp)
        self.hb.set_level(self.level)

    def heal(self, amount):
        if not self.alive:
            return
        old = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        if int(self.hp) != int(old):             # la barre ne bouge qu'à chaque PV entier (régénération)
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
            self.rush_t = 0
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
        self.rush_t = 0
        if self.transform_kind is not None:
            self.end_transform()
        self._refresh_bar()
        self.creature.knock_out()
        self.creature.visible = True

    # ------------------------------------------------------------ progression
    def gain_xp(self, amount):
        if self.level >= C.MAX_LEVEL or self.kind != 'pokemon':
            return
        self.xp += amount
        while self.level < C.MAX_LEVEL and self.xp >= C.xp_to_next(self.level):
            self.xp -= C.xp_to_next(self.level)
            self.set_level(self.level + 1)

    def set_level(self, level, show=True):
        """Nouveau niveau : stats, évolution et attaques débloquées."""
        before = {mv['slot'] for mv in self.moves if not mv['locked']}
        self.level = level
        self.recalc_stats()
        self._refresh_bar()
        if self.alive and show:
            self.level_fx()
        self.match.on_level_up(self)
        self.check_evolution(show)
        self.refresh_moves()
        new = [mv for mv in self.moves if not mv['locked'] and mv['slot'] not in before]
        if new:
            self.match.on_moves_unlocked(self, new if show else [])

    def level_fx(self):
        burst(self.match.root, self.position + Vec3(0, 1, 0), color.rgb(1, .95, .5), n=10, speed=3, size=.2)

    # ------------------------------------------------------------ évolution
    def check_evolution(self, show=True):
        """Prend la forme correspondant au niveau (évolution, ou retour à la forme de base quand
        une nouvelle partie commence)."""
        if self.kind != 'pokemon' or self.species not in C.EVOLUTIONS or self.transform_kind == 'mega':
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
        ratio = max(0.0, self.hp / self.max_hp) if self.max_hp else 1.0
        old = self.creature
        self.form = form
        self.data = C.SPECIES[form]
        self.name, self.type, self.radius = self.data['name'], self.data['type'], self.data['radius']
        c = Creature(form, parent=self.match.root, position=old.position, scale=self.data['scale'] * self.size_mult)
        c.rotation_y = old.rotation_y
        self.bar.parent = c
        self.bar.y = self.data['scale'] * self.size_mult * 1.5 + .6
        if self.ring is not None:
            destroy(self.ring)
            tc = C.TEAMS[self.team]['color']
            self.ring = flat_circle(c, self.radius + .35, color.rgba(tc[0], tc[1], tc[2], .75), y=.05)
        if not self.alive:
            c.knock_out()
        c.enabled, c.visible = old.enabled, old.visible
        self.creature = c
        destroy_tree(old)
        self.match.ignore_passive(c)
        veiled, self.veiled = self.veiled, False
        self.set_veiled(veiled)
        self.recalc_stats()
        self.refresh_moves()
        self.hp = self.max_hp * ratio if self.alive else 0
        self._refresh_bar()
        if hasattr(self.brain, 'set_form'):
            self.brain.set_form()

    # ------------------------------------------------------------ Méga-Évolution et Dynamax
    def transform_info(self):
        """(sorte, forme Méga ou None, réglages) de la transformation de cette lignée."""
        kind, form = kit.transform_of(self.species)
        return kind, form, C.TRANSFORMS[kind]

    def can_transform(self):
        if self.kind != 'pokemon' or not self.alive or self.transform_kind is not None or self.transform_cd > 0:
            return False
        kind, form, cfg = self.transform_info()
        if self.level < cfg['level']:
            return False
        return kind != 'mega' or C.form_for(self.species, self.level) == C.evolution_line(self.species)[-1]

    def start_transform(self, show=True):
        kind, form, cfg = self.transform_info()
        self.transform_kind, self.transform_t = kind, cfg['duration']
        self.transform_cd = cfg['cooldown']
        if kind == 'mega':
            self._set_form(form)
        else:
            self.size_mult = cfg['size']
            self.creature.pivot.scale = self.data['scale'] * self.size_mult
            self.bar.y = self.data['scale'] * self.size_mult * 1.5 + .6
            self.recalc_stats()
            self._refresh_bar()
        if show and self.alive:
            self._evolution_fx()
        self.match.on_transform(self, True)

    def end_transform(self):
        kind, self.transform_kind, self.transform_t = self.transform_kind, None, 0.0
        if kind == 'mega':
            self._set_form(C.form_for(self.species, self.level))
        elif kind == 'dynamax':
            self.size_mult = 1.0
            self.creature.pivot.scale = self.data['scale']
            self.bar.y = self.data['scale'] * 1.5 + .6
            self.recalc_stats()
            self._refresh_bar()
        self.match.on_transform(self, False)

    def _evolution_fx(self):
        """Évolution : la silhouette devient blanche et lumineuse, grandit d'un coup, et une colonne
        de lumière monte dans une pluie d'étoiles."""
        c, s = self.creature, self.data['scale'] * self.size_mult
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
        return self.alive and self.status['stun'] <= 0 and self.charge_t <= 0 and self.channel <= 0 \
            and self.rush_t <= 0

    def in_attack_range(self, target, margin=0.0):
        return (flat(target.position - self.position)).length() < self.auto['range'] + target.radius + margin

    def auto_damage(self):
        k = C.AUTO_POWER if self.kind == 'pokemon' else 1.0
        return kit.raw_damage(self.auto['power'], self.stats['atk']) * k

    def basic_attack(self, target, forward=None):
        """Auto-attaque vers la cible (ou droit devant si pas de cible)."""
        if self.attack_cd > 0 or not self.can_act():
            return False
        a = self.auto
        self.attack_cd = self.attack_interval()
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
        dmg = self.auto_damage()
        status, stun = self._auto_status()
        if a['kind'] == 'melee':
            if target is None:        # coup donné à l'aveugle (dans les hautes herbes...) : il touche quand même
                target = self.match.blind_target(self, a['range'], d)
            if target is not None:
                # le coup part après un court élan : la cible peut encore s'écarter
                self.match.pending_hits.append([C.MELEE_WINDUP, self, target, dmg, status, stun])
            self.creature.pivot.rotation_x = -15
            return True
        start = self.position + Vec3(0, .9 * min(2, self.data['scale']), 0) + d * (self.radius + .3)
        self.match.projectiles.append(Projectile(
            self.match, self, start, d * a['speed'], dmg, a['size'], a['color'],
            shape=a.get('shape', 'sphere'), life=(a['range'] + 4) / a['speed'], status=status, stun=stun,
            on_hit=self.on_auto_hit))
        return True

    def _auto_status(self):
        """Effets ajoutés aux auto-attaques par les talents et les bonus."""
        status, stun = self.auto.get('status'), 0.0
        if self.trait == 'Corps Gel':
            status = ('slow', self.trait_cfg['slow'])
        elif self.trait == 'Statik' and random.random() < self.trait_cfg['chance']:
            stun = self.trait_cfg['stun']
        for e in self._effects():
            if e.get('burn_auto'):
                status = ('burn', e['burn_auto'])
        return status, stun

    def on_auto_hit(self, target):
        """Une auto-attaque a touché (effets des objets)."""

    def ready(self, mv, slack=0.0):
        return not mv['locked'] and self.cd.get(mv['slot'], 0) <= slack and self.cast_lock <= slack and self.can_act()

    def use_move(self, mv, target=None, point=None, slack=0.0):
        """Lance une attaque si elle est prête (recharge, déblocage, pas étourdi). Renvoie True si lancée."""
        if not self.ready(mv, slack):
            return False
        self.cd[mv['slot']] = mv['cooldown'] * self.cooldown_mult()
        self.cast_lock = C.CAST_LOCK
        moves.cast(self.match, self, mv, target, point)
        if self.mods['recoil'] > 0 and self.match.authority:          # Orbe Vie : chaque attaque coûte des PV
            self.hp = max(1.0, self.hp - self.max_hp * self.mods['recoil'])
            self._refresh_bar()
        return True

    def start_charge(self, d, speed, duration, dmg, cat='phys'):
        self.charge_t = duration
        self.charge_dir = d
        self.charge_speed = speed
        self.charge_dmg = dmg
        self.charge_cat = cat
        self.charge_hit = set()

    def start_rush(self, mv, d, target, dmg):
        """Ruée : fonce (vers la cible si l'attaque est à ciblage automatique) et frappe au contact."""
        self.rush_t, self.rush_mv, self.rush_dir, self.rush_target, self.rush_dmg = mv['duration'], mv, d, target, dmg
        self.invuln = max(self.invuln, mv['duration'] + .1 + getattr(self.brain, 'slack', 0.0))

    def _update_rush(self, dt):
        self.rush_t -= dt
        t = self.rush_target
        d = self.rush_dir
        if t is not None and t.alive:
            to = flat(t.position - self.position)
            if to.length() > .1:
                d = to.normalized()
        self.face(d)
        mv = self.rush_mv
        if not self.net_driven:
            self.move(d, dt, mv['speed'] / max(1, self.speed()))
        if fx.PARTICLES and not self.veiled:                   # traits de vitesse et poussière
            p = self.position
            fx.PARTICLES.emit((p.x + fx.rnd(.3), p.y + fx.ru(.3, 1.2), p.z + fx.rnd(.3)), (1, 1, 1),
                              size=.12, life=.18, vel=(-d.x * 14, 0, -d.z * 14), mode='stretch', stretch=.03, alpha=.7)
            fx.smoke(fx.PARTICLES, (p.x, p.y + .2, p.z), (-d.x, .4, -d.z), s=.8, life=.4, alpha=.25,
                     col=fx.DUST, col2=(.8, .76, .7))
        if not self.match.authority:
            return
        hit = t if t is not None and t.alive else self.match.blind_target(self, self.radius + .5, None)
        if hit is not None and (flat(hit.position - self.position)).length() < self.radius + hit.radius + .5:
            self.match.deal_damage(self, hit, self.rush_dmg, mv.get('status'), mv.get('stun', 0.0), contact=True,
                                   cat=mv.get('cat', 'phys'))
            self.rush_t = 0

    # ------------------------------------------------------------ boucle
    def _tick_timers(self, dt):
        self.sash_cd -= dt
        self.transform_cd -= dt
        if self.transform_t > 0:
            self.transform_t -= dt
            if self.transform_t <= 0:
                self.end_transform()
        self.attack_cd -= dt
        self.cast_lock -= dt
        for k in self.cd:
            self.cd[k] -= dt
        self.invuln -= dt
        self.channel -= dt
        self.guard_t -= dt
        self.attack_anim -= dt

    def update(self, dt):
        self.hb.tick(dt)
        self.hb.set_level(self.level)         # le niveau peut aussi changer par le réseau ou une nouvelle partie
        if not self.match.authority:
            self.update_view(dt)
            return
        if not self.alive:
            self.creature.animate(dt)
            return
        self._tick_timers(dt)
        expired = False
        for k in self.buffs:
            if self.buffs[k] > 0:
                self.buffs[k] -= dt
                expired |= self.buffs[k] <= 0
        if expired:
            self.buffs = {k: v for k, v in self.buffs.items() if v > 0}
            self.recalc_stats()
        for k in self.status:
            self.status[k] = max(0, self.status[k] - dt)

        regen = self.regen()
        if regen and self.hp < self.max_hp:
            self.heal(regen * dt)
        if self.status['burn'] > 0:
            self.burn_tick -= dt
            if self.burn_tick <= 0:
                self.burn_tick = C.BURN['tick']
                self.match.deal_damage(self.last_hit_by or self, self, C.BURN['damage'], raw=True)
                if not self.alive:
                    return

        self._status_fx(dt)
        net_moving = self.brain.follow(dt) if self.net_driven else False   # Pokémon de l'invité
        moving = False
        if self.rush_t > 0:                        # ruée (Vive-Attaque...)
            self._update_rush(dt)
            moving = True
        elif self.charge_t > 0:                    # Roulade / charge
            self._update_charge(dt, damage=True)
            moving = True
        elif self.status['stun'] > 0:
            self.creature.pivot.rotation_z = math.sin(self.status['stun'] * 60) * 6
            moving = net_moving
        else:
            self.creature.pivot.rotation_z = 0
            if self.brain:
                moving = self.brain.update(dt)
        self._finish_frame(dt, moving)

    def _update_charge(self, dt, damage):
        self.charge_t -= dt
        if not self.net_driven:                # l'invité fait rouler son Pokémon lui-même
            self.move(self.charge_dir, dt, self.charge_speed / max(1, self.speed()))
        self.creature.pivot.rotation_x += dt * 900
        self._roll_dust()
        if damage:
            for u in self.match.units:
                if u.alive and id(u) not in self.charge_hit and self.match.hostile(self, u):
                    if (flat(u.position - self.position)).length() < self.radius + u.radius + .4:
                        self.charge_hit.add(id(u))
                        self.match.deal_damage(self, u, self.charge_dmg, contact=True, cat=self.charge_cat)
        if self.charge_t <= 0:
            self.creature.pivot.rotation_x = 0

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
            f, p = self.match.cam_target, self.creature.position
            if (p.x - f.x) ** 2 + (p.z - f.z) ** 2 > ANIM_RANGE2:
                self._fx_t = .3
                return
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
            for k, t in self.buffs.items():   # buffs de la jungle : étincelles de leur couleur
                b = C.BUFFS.get(k)
                if t > 0 and b is not None and random.random() < .35:
                    c = b['color']
                    a = random.uniform(0, math.tau)
                    P.emit((p.x + math.sin(a) * .6 * s, p.y + fx.ru(.1, .5) * s, p.z + math.cos(a) * .6 * s),
                           (c[0], c[1], c[2]), size=.18, life=.6, vel=(0, 1.2, 0), tex='star')
            if self.guard_t > 0:              # protection (Abri, Cotogarde...) : bulle scintillante
                a = random.uniform(0, math.tau)
                P.emit((p.x + math.sin(a) * .9 * s, p.y + fx.ru(.3, 1.4) * s, p.z + math.cos(a) * .9 * s),
                       (.75, .95, 1), size=.35, life=.3, tex='star')

    def _roll_dust(self):
        """La roulade soulève la poussière."""
        if fx.PARTICLES and random.random() < .7:
            p = self.position
            fx.smoke(fx.PARTICLES, (p.x, p.y + .2, p.z), (fx.rnd(1), .6, fx.rnd(1)), s=1.2, life=.6, alpha=.35,
                     col=fx.DUST, col2=(.78, .72, .64))

    def _finish_frame(self, dt, moving):
        self.moving = moving
        p = self.creature.position
        f = self.match.cam_target
        if (p.x - f.x) ** 2 + (p.z - f.z) ** 2 < ANIM_RANGE2 or self.local:   # loin de la caméra : pas d'animation
            if self.attack_anim <= 0 and self.charge_t <= 0 and self.creature.pivot.rotation_x < 0:
                self.creature.pivot.rotation_x = 0
            self.creature.animate(dt, moving, self.attack_anim > 0 or self.channel > 0)
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
        self.cast_lock -= dt
        self.transform_cd -= dt
        for k in self.cd:
            self.cd[k] -= dt
        self.invuln -= dt
        self.channel -= dt
        self.guard_t -= dt
        moving = False
        if self.rush_t > 0:                        # ruée lancée par l'invité : il fonce tout de suite
            self._update_rush(dt)
            moving = True
        elif self.charge_t > 0:                    # roulade lancée par l'invité : il roule tout de suite
            self._update_charge(dt, damage=False)
            moving = True
        elif self.status['stun'] > 0:
            self.creature.pivot.rotation_z = math.sin(self.match.time * 60) * 6
        else:
            self.creature.pivot.rotation_z = 0
            moving = self.brain.update(dt)
        self._finish_frame(dt, moving)


# ==================================================================== joueur
def input_vector():
    """Déplacement au clavier : les flèches (les lettres servent aux attaques)."""
    ix = held_keys['right arrow'] - held_keys['left arrow']
    iz = held_keys['up arrow'] - held_keys['down arrow']
    return Vec3(ix, 0, iz)


class AimIndicator:
    """Visée à la souris : portée de l'attaque autour du Pokémon, et zone ou trajectoire visée."""
    COL = color.rgba(1, .95, .6, .28)
    EDGE = color.rgba(1, .95, .6, .7)

    def __init__(self, match):
        self.m = match
        self.root = Entity(parent=match.root, enabled=False)
        self.range_ring = flat_circle(self.root, 1, color.rgba(1, 1, 1, .09))
        self.area = flat_circle(self.root, 1, self.COL)
        self.line = Entity(parent=self.root, model='quad', color=self.COL, rotation_x=90, double_sided=True)

    def show(self, u, mv, point):
        from game.pokemon.kit import cast_range
        self.root.enabled = True
        here = flat(u.position)
        y = u.position.y + .15
        rng = cast_range(mv)
        self.range_ring.position = Vec3(here.x, y - .01, here.z)
        self.range_ring.scale = rng
        d, p = moves.aim(u, mv, None, point)
        k = mv['kind']
        if k in ('strike', 'blink'):
            r = mv['radius']
            self.area.enabled, self.line.enabled = True, False
            self.area.position = Vec3(p.x, self.m.stadium.walk_y(p.x, p.z) + .16, p.z)
            self.area.scale = r
        elif k in ('spin', 'wave', 'heal', 'nova'):
            self.area.enabled, self.line.enabled = True, False
            self.area.position = Vec3(here.x, y + .01, here.z)
            self.area.scale = mv.get('radius', rng)
        else:                                       # rayon, tir, ruée : trajectoire
            self.area.enabled, self.line.enabled = False, True
            w = mv.get('width', mv.get('size', 1.0) * 1.4) if k in ('beam', 'shot') else u.radius * 2
            self.line.position = Vec3(here.x, y + .01, here.z) + d * rng / 2
            self.line.rotation_y = math.degrees(math.atan2(d.x, d.z))
            self.line.scale = (w, rng)

    def hide(self):
        self.root.enabled = False


class PlayerBrain:
    """Contrôles (façon MOBA) : clic au sol pour se déplacer (le Pokémon contourne les murs), clic
    sur un adversaire pour l'attaquer ; Z Q S D pour bouger au clavier ; J (maintenu) pour
    l'auto-attaque, K pour l'attaque à ciblage automatique, L U I O pour les attaques visées à la
    souris (maintenir pour viser, relâcher pour lancer ; clic gauche : lancer tout de suite ;
    clic droit : annuler). À l'arrêt, le Pokémon auto-attaque tout seul l'adversaire à portée.
    Chez l'invité, les attaques sont envoyées à l'hôte (qui les exécute) ; les mouvements
    (déplacement, esquive, ruée, roulade, téléportation) restent locaux."""
    slack = 0.0               # tolérance sur les temps de recharge (utile pour le joueur distant)

    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.dash_cd = 0.0
        self.dash_t = 0.0
        self.dash_dir = Vec3(0, 0, 1)
        self.target = None
        self.aim = None           # direction imposée (attaque reçue du joueur distant)
        self.aiming = None        # emplacement de l'attaque en cours de visée
        self.indicator = AimIndicator(match) if unit.local else None
        self.order = None         # ordre au clic : ('move', [points]) ou ('attack', unité)
        self.click_t = 0.0        # temps depuis le dernier clic (bouton maintenu : on suit la souris)
        self.repath_t = 0.0

    @property
    def moves(self):
        return self.u.moves

    def on_hit(self, source):
        pass

    def set_form(self):
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

    def cursor(self):
        """Point du sol sous la souris."""
        return self.m.mouse_ground(self.u.position.y)

    # ------------------------------------------------------------ attaques
    def use_auto(self):
        u, m = self.u, self.m
        if u.attack_cd > self.slack or not u.can_act() or self.dash_t > 0:
            return
        t = self.target if self.target is not None and u.in_attack_range(self.target, self.slack * 6) else None
        if not m.authority:                  # invité : l'hôte tirera pour nous
            u.attack_cd = u.attack_interval()
            u.attack_anim = .2
            u.face(self._dir_to_target())
            m.net.send_use(C.KEYS['auto'], t, self._dir_to_target(), None)
            return
        u.attack_cd = min(u.attack_cd, 0)
        u.basic_attack(t, forward=self._dir_to_target())

    def press(self, mv):
        """Touche d'attaque enfoncée : attaque à ciblage auto lancée tout de suite, sinon visée."""
        u, m = self.u, self.m
        if mv['locked']:
            if u.local:
                m.game.banner.show(f"{mv['name']} : débloquée au niveau {mv['unlock']}", 1.5,
                                   text_color=color.rgb(.8, .85, 1))
            return
        if mv['kind'] in C.SELF_CAST:              # autour du Pokémon : pas besoin de viser
            self.cast(mv, self.target, None)
            return
        self.aiming = mv['slot']

    def release(self, cast=True):
        slot, self.aiming = self.aiming, None
        if self.indicator is not None:
            self.indicator.hide()
        mv = self.u.get_move(slot) if slot is not None else None
        if cast and mv is not None:
            p = self.cursor()
            t = self.target
            if mv['aim'] == 'lock':                     # attaque à tête chercheuse : l'adversaire visé
                t = self.pick(p) or self.m.nearest_enemy(self.u, p, 4.0) or t
            self.cast(mv, t, p)

    def cast(self, mv, target, point):
        u, m = self.u, self.m
        if not u.ready(mv, self.slack) or self.dash_t > 0:
            return False
        if m.authority:
            return u.use_move(mv, target, point, self.slack)
        # invité : le mouvement se joue tout de suite ici, les dégâts chez l'hôte
        u.cd[mv['slot']] = mv['cooldown'] * u.cooldown_mult()
        u.cast_lock = C.CAST_LOCK
        m.announce_cast(u, mv['name'])
        moves.predict(m, u, mv, target, point)
        d, p = moves.aim(u, mv, target, point)
        m.net.send_use(mv['key'], target, d, p)
        return True

    # ------------------------------------------------------------ déplacement au clic
    def pick(self, p):
        """Adversaire sous le curseur (point p au sol), ou None."""
        u, m = self.u, self.m
        best, bd = None, 1e9
        for e in m.units:
            if e.alive and m.hostile(u, e) and e not in m.hidden[u.team] and not e.veiled:
                d = (flat(e.position) - flat(p)).length() - e.radius
                if d < C.CONTROLS['pick_radius'] and d < bd:
                    best, bd = e, d
        return best

    def click(self, drag=False):
        """Clic au sol (se déplacer) ou sur un adversaire (l'attaquer)."""
        u, m = self.u, self.m
        if not u.alive:
            return
        p = self.cursor()
        self.click_t = 0.0
        t = None if drag else self.pick(p)
        if t is not None:
            self.order = ('attack', t)
            self._marker(t.position, (1, .35, .3))
            return
        path = m.stadium.path(u.position, p, u.team, u.radius)
        self.order = ('move', path)
        if not drag:
            end = path[-1]
            self._marker(Vec3(end.x, m.stadium.walk_y(end.x, end.z), end.z), (.5, 1, .55))

    def _marker(self, p, col):
        if fx.PARTICLES:
            fx.ground_ring(fx.PARTICLES, (p.x, p.y + .12, p.z), col, .2, 1.2, .35, alpha=.9)

    def _follow_order(self, dt):
        """Exécute l'ordre donné au clic. Renvoie True si le Pokémon bouge."""
        u, m = self.u, self.m
        kind, what = self.order
        if kind == 'attack':
            t = what
            if not t.alive or t in m.hidden[u.team]:
                self.order = None
                return False
            self.target = t                           # l'auto-attaque et K visent cet adversaire
            if u.in_attack_range(t) and m.can_see(u, t):
                u.face(flat(t.position - u.position).normalized() if (flat(t.position - u.position)).length() > .1
                       else u.facing())
                self.use_auto()
                return False
            self.repath_t -= dt
            to = flat(t.position - u.position)
            if self.repath_t <= 0:                    # l'adversaire bouge : on recalcule de temps en temps
                self.repath_t = .4
                self.chase = m.stadium.path(u.position, t.position, u.team, u.radius)
            pts = getattr(self, 'chase', None) or [flat(t.position)]
            nxt = flat(pts[0]) - flat(u.position)
            if nxt.length() < .6 and len(pts) > 1:
                pts.pop(0)
                nxt = flat(pts[0]) - flat(u.position)
            d = nxt.normalized() if nxt.length() > .05 else to.normalized()
            u.move(d, dt)
            u.face(d, dt, 16)
            return True
        pts = what
        while pts and (flat(pts[0]) - flat(u.position)).length() < .5:
            pts.pop(0)
        if not pts:
            self.order = None
            return False
        to = flat(pts[0]) - flat(u.position)
        d = to.normalized()
        before = flat(u.position)
        u.move(d, dt, min(1.0, to.length() / max(.01, u.speed() * dt)))
        if (flat(u.position) - before).length() < u.speed() * dt * .15:
            self.stuck_t = getattr(self, 'stuck_t', 0) + dt         # bloqué (un autre Pokémon...) : on abandonne
            if self.stuck_t > .6:
                self.order, self.stuck_t = None, 0
        else:
            self.stuck_t = 0
        u.face(d, dt, 16)
        return True

    def dash(self):
        u = self.u
        if self.dash_cd > 0 or not u.can_act():
            return
        d = self.world_input()
        if not d.length() and u.local:                     # sans touche de direction : vers la souris
            c = flat(self.cursor() - u.position)
            d = c.normalized() if c.length() > .5 else Vec3(0, 0, 0)
        self.dash_dir = d if d.length() else u.facing()
        self.dash_t = C.PLAYER_DASH['time'] * (u.trait_cfg['dash'] if u.trait == 'Téléport' else 1)
        self.dash_cd = C.PLAYER_DASH['cooldown']
        u.invuln = max(u.invuln, self.dash_t + .08)
        u.face(self.dash_dir)
        if not self.m.authority:
            self.m.net.send_dash()

    def transform(self):
        u, m = self.u, self.m
        if not u.can_transform():
            kind, form, cfg = u.transform_info()
            if u.local and u.transform_kind is None and u.level < cfg['level']:
                m.game.banner.show(f"{cfg['name']} : disponible au niveau {cfg['level']}", 1.5,
                                   text_color=color.rgb(.8, .85, 1))
            return
        if m.authority:
            u.start_transform()
        else:
            m.net.send_use(C.TRANSFORM_KEY, None, u.facing(), None)

    def input(self, key):
        if key in ('space', 'shift', 'left shift', 'right shift'):
            self.dash()
            return
        if key == C.TRANSFORM_KEY:
            self.transform()
            return
        if self.aiming is not None:
            if key == 'right mouse down':
                self.release(cast=False)             # annule la visée (et donne l'ordre ci-dessous)
            elif key == 'left mouse down':
                self.release()
                return
        if key.endswith(' down') and key[:-5] in C.CONTROLS['move_buttons']:
            from ursina import mouse
            if mouse.hovered_entity is None:         # pas sur un bouton de l'interface (boutique...)
                self.click()
            return
        for mv in self.moves:
            if key == mv['key']:
                if self.aiming is not None:
                    self.release(cast=False)
                self.press(mv)
            elif key == mv['key'] + ' up' and self.aiming == mv['slot']:
                self.release()

    def update(self, dt):
        u, m = self.u, self.m
        self.dash_cd -= dt
        self.target = m.find_target(u, C.TARGET_RANGE)
        if self.aiming is not None and self.indicator is not None:
            mv = u.get_move(self.aiming)
            if mv is None or not u.alive:
                self.release(cast=False)
            else:
                self.indicator.show(u, mv, self.cursor())
        move = self.world_input()
        if m.shop is not None and u.local:                   # boutique ouverte : pas de déplacement
            move, self.order = Vec3(0, 0, 0), None
        moving = move.length() > 0
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
        if moving:
            self.order = None                         # le clavier reprend la main
            u.move(move, dt)
        elif self.order is not None:
            moving = self._follow_order(dt)
        self.click_t += dt
        if self.order is not None and self.order[0] == 'move' and u.local and self.aiming is None \
                and self.click_t > C.CONTROLS['drag_repeat'] \
                and any(held_keys[b] for b in C.CONTROLS['move_buttons']):
            self.click(drag=True)                     # bouton maintenu : la destination suit la souris
        if held_keys[C.KEYS['auto']]:
            self.use_auto()
        elif not moving and self.order is None and C.CONTROLS['auto_acquire'] and self.target is not None \
                and self.target.team and u.in_attack_range(self.target):
            self.use_auto()                           # à l'arrêt : attaque l'adversaire à portée
        if u.attack_anim > 0:
            u.face(self._dir_to_target())
        elif moving and self.order is None:
            u.face(move, dt, 16)
        return moving


class RemotePlayerBrain(PlayerBrain):
    """Chez l'hôte : le Pokémon de l'invité. Sa position arrive par le réseau (l'invité se
    déplace chez lui sans attendre) ; ses attaques arrivent sous forme de « touche + cible +
    point visé » et sont exécutées ici, là où se calculent les dégâts."""
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

    def remote_use(self, key, target_uid, dx, dz, point=None):
        m = self.m
        t = m.units[target_uid] if 0 <= target_uid < len(m.units) else None
        self.target = t if t is not None and t.alive and m.hostile(self.u, t) else None
        d = Vec3(dx, 0, dz)
        self.aim = d.normalized() if d.length() > .01 else None
        try:
            if key == C.KEYS['auto']:
                self.use_auto()
                return
            if key == C.TRANSFORM_KEY:
                if self.u.can_transform():
                    self.u.start_transform()
                return
            mv = next((mv for mv in self.moves if mv['key'] == key), None)
            if mv is not None:
                if self.aim is not None:
                    self.u.face(self.aim)
                self.u.use_move(mv, self.target, point, self.slack)
        finally:
            self.aim = None

    def remote_dash(self):
        k = self.u.trait_cfg['dash'] if self.u.trait == 'Téléport' else 1
        self.u.invuln = max(self.u.invuln, C.PLAYER_DASH['time'] * k + .08 + self.slack)

    def update(self, dt):
        self.dash_cd -= dt
        return self.net_moving


# ==================================================================== IA d'équipe
class BotBrain:
    AGGRO = 14
    lead = (.2, .9)            # anticipation du déplacement de la cible (1 = parfaite)
    aim_error = C.AIM_ERROR    # imprécision de la visée (degrés)

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
        self.move_t = random.uniform(0, .2)

    def on_hit(self, source):
        if source is not None and source.alive and self.mode != 'retreat' and self.target is None:
            self.target = source

    # ------------------------------------------------------------ décisions
    def heal_goal(self):
        """Où aller se soigner : une Baie Sitrus proche (plus proche que la base), sinon la base."""
        u, m = self.u, self.m
        base = m.base_goal(u.team)
        dbase = (base[1] - flat(u.position)).length()
        pad = m.nearest_pad(u.position, min(35.0, dbase))
        return (pad['key'], pad['pos'], .8) if pad is not None else base

    def think(self):
        u, m = self.u, self.m
        if u.hp < u.max_hp * .3:
            self.mode = 'retreat'
        if self.mode == 'retreat':
            if u.hp > u.max_hp * .9:
                self.mode = None
            else:
                self.target = None
                self.goal = self.heal_goal()
                return
        # adversaires proches
        best, score = None, 1e9
        for e in m.units:
            if e.alive and e.team and e.team != u.team and e.kind == 'pokemon' and e not in m.hidden[u.team]:
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
        if self.target is None:
            self.target = m.enemy_tower_near(u, 18) or m.enemy_minion_near(u, 9)
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
        self.move_t -= dt
        if self.think_t <= 0:
            self.think_t = .35 + random.random() * .25
            self.think()
        t = self.target
        if t is not None and (not t.alive or (t.team is None and self.mode == 'retreat')
                              or t in m.hidden[u.team]):       # perdu de vue dans les hautes herbes
            self.target = t = None
        if self.mode == 'retreat':
            self.use_moves(None, 0)                            # soins, même en repli
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
            rng = u.auto['range'] + t.radius
            moved = False
            if d > rng * .85:
                moved = u.move(dirn, dt)
            elif u.auto['kind'] == 'ranged' and d < rng * .4:
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
            self.use_moves(t, d)
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

    def use_moves(self, t, d):
        """Lance la meilleure attaque prête (ultime d'abord), visée avec plus ou moins d'adresse."""
        u = self.u
        if t is not None and t.kind == 'pokemon' and d < 12 and u.can_transform():
            u.start_transform()
        if u.cast_lock > 0 or self.move_t > 0 or not u.can_act():
            return False
        self.move_t = random.uniform(.05, .25)                # temps de réaction
        for mv in reversed(u.moves):
            if mv['locked'] or u.cd.get(mv['slot'], 0) > 0:
                continue
            if not moves.worth_casting(self, mv, t, d):
                continue
            point = None
            if t is not None and mv['aim'] == 'skill':
                point = moves.lead_point(u, mv, t, self.lead, self.aim_error)
            if u.use_move(mv, t, point):
                return True
        return False


# ==================================================================== tours
class TowerBrain:
    """Tour d'une arène : tire sur les adversaires à portée. Priorité à ceux qui viennent
    d'attaquer un Pokémon allié, puis aux sbires, puis au plus proche."""

    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.target = None
        self.think_t = 0.0
        self.shot_t = 1.0

    def on_hit(self, source):
        pass

    def choose(self):
        u, m = self.u, self.m
        best, bs = None, 1e9
        R = C.TOWER['range']
        for e in m.units:
            if e.alive and e.team and e.team != u.team and e.kind in ('pokemon', 'minion'):
                d = (flat(e.position - u.position)).length()
                if d < R + e.radius:
                    if e.kind == 'pokemon' and m.time - e.aggro_t < 2.0:
                        s = d                                  # attaque un Pokémon allié : cible prioritaire
                    elif e.kind == 'minion':
                        s = 100 + d
                    else:
                        s = 200 + d
                    if s < bs:
                        best, bs = e, s
        return best

    def update(self, dt):
        u, m = self.u, self.m
        self.think_t -= dt
        self.shot_t -= dt
        if self.think_t <= 0:
            self.think_t = .25
            self.target = self.choose()
        t = self.target
        if t is None or not t.alive or self.shot_t > 0:
            return False
        self.shot_t = C.TOWER['interval']
        top = u.position + Vec3(0, 3.5, 0)
        aim = t.position + Vec3(0, 1, 0)
        d = (aim - top).normalized()
        dmg = C.TOWER['damage'] + C.TOWER['damage_per_min'] * m.time / 60
        u.attack_anim = .2
        col = C.TEAMS[u.team]['light']
        m.projectiles.append(Projectile(m, u, top, d * 26, dmg, .6, col, homing=t, turn=4, life=2.0, cat='true'))
        return False


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
        leash = C.WILD['leash'] if self.wild else C.CAMP_LEASH + (10 if u.max_hp > 2000 else 0)
        if t is not None and (not t.alive or (flat(t.position) - u.home).length() > leash):
            self.target = t = None
        if t is not None:
            to_t = flat(t.position - u.position)
            d = to_t.length()
            dirn = to_t.normalized() if d > .01 else u.facing()
            rng = u.auto['range'] + t.radius
            moved = False
            sees = m.can_see(u, t)
            if (d > rng * .85 or not sees) and (flat(u.position) - u.home).length() < leash:
                moved = u.move(dirn, dt)
            u.face(dirn, dt, 10)
            if not sees:                              # pas d'attaque à travers les murs
                return moved
            if d < rng:
                u.basic_attack(t)
            for mv in u.moves:
                reach = {'wave': mv.get('radius', 8) * .8, 'strike': 12, 'nova': 11, 'beam': 14}.get(mv['kind'], 0)
                if d < reach:
                    u.use_move(mv, t)
            return moved
        # retour au camp ; soins seulement après quelques secondes sans combat
        calm = m.time - u.last_hit_t > C.NEUTRAL_CALM
        back = flat(u.home - u.position)
        if back.length() > (C.WILD['wander'] + 1 if self.wild else .8):
            u.move(back.normalized(), dt, 1.3)
            u.face(back.normalized(), dt, 10)
            if calm:
                u.heal(u.max_hp * C.NEUTRAL_REGEN * dt)
            return True
        if calm:
            u.heal(u.max_hp * C.NEUTRAL_REGEN * dt)
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
