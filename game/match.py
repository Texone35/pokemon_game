"""Une partie de Pokémon Dominion : règles, score, IA d'équipe, caméra et interface.

Deux équipes de 5 s'affrontent pour le contrôle de 5 arènes ouvertes. L'équipe
rouge compte un ou deux joueurs humains (le Pokémon choisi dans le salon), le
reste est joué par l'ordinateur. Une arène se capture en restant dans son cercle
sans adversaire (plus on est nombreux, plus c'est rapide) ; si les deux équipes
sont présentes, elle est contestée. Chaque arène contrôlée rapporte des points
Dominion chaque seconde et un bonus à toute l'équipe. Les K.O., les camps de la
jungle et les boss du Boss Pit rapportent aussi des points.
La première équipe à SCORE_TO_WIN points gagne (ou la meilleure à la fin du temps).

À deux, l'hôte (self.authority) fait tourner toute la partie ; l'invité affiche
l'état reçu (voir netsync.py). Les messages destinés aux joueurs passent par
announce() / say() / emit(), qui les envoient aussi à l'autre PC.
"""
import math
import random

from ursina import Entity, Text, Texture, Vec3, Vec4, camera, color, destroy, lerp, mouse, time

from game import config as C
from game.pokemon import kit
from game.pokemon.combat import flat, rc
from game.pokemon.creatures import Portraits
from game.world.emblems import add_emblem
from game.world.fx import ArenaWeather
from game.interface.style import key_label
from game.world.geometry import MeshBuilder, destroy_tree, flat_circle
from game.world.stadium import LANES, RIVERS, Stadium
from game.interface.widgets import Feed, MoveSlot, floating_text, hp_color
from game.pokemon.units import ALLY_BAR, BotBrain, NeutralBrain, PlayerBrain, RemotePlayerBrain, TowerBrain, Unit

TEAM_KEYS = ('rouge', 'bleu')
# couleurs de la mini-carte par biome (ordre de biomes.KEYS) : sol praticable et massifs
MAP_GROUND = [(76, 140, 70), (150, 128, 88), (70, 140, 58), (92, 146, 76), (86, 150, 112), (84, 70, 62)]
MAP_MASSIF = [(22, 52, 24), (112, 84, 56), (18, 66, 22), (30, 64, 30), (24, 78, 66), (46, 32, 30)]
NEUTRAL_RING = color.rgb(.85, .85, .85)
STAT_KEYS = ('ko', 'deaths', 'assists', 'dmg', 'taken', 'heal', 'caps', 'points')
RESULTS_DELAY = 2.5             # secondes entre la fin de la partie et la page des résultats


def v3(p):
    return Vec3(p[0], 0, p[1])


class Match(Entity):
    def __init__(self, game, setup=None):
        """setup : {'humans': [espèce de J1, espèce de J2...], 'local': n° du joueur de ce PC,
        'role': 'solo' | 'host' | 'client', 'host': net.Host, 'link': net.Link}."""
        super().__init__()
        setup = setup or {'humans': ['pikachu'], 'local': 0, 'role': 'solo'}
        self.game = game
        self.role = setup['role']
        self.authority = self.role != 'client'   # l'hôte (ou le solo) décide de tout
        self.ai_level = setup.get('ai', 'facile')   # 'facile' (BotBrain) ou 'expert' (ai.ExpertBrain)
        self.net = None
        self.root = Entity(parent=self)
        self.stadium = Stadium(self.root)
        from game.world import fx
        fx.PARTICLES = self.particles = fx.Particles(self.root)
        self.projectiles, self.hazards = [], []
        self.pending_hits = []          # coups au contact en cours d'élan
        self._los = {}                  # lignes de vue récentes entre Pokémon (voir can_see)
        self.time = 0.0
        self.score = {'rouge': 0.0, 'bleu': 0.0}
        self.state = 'play'
        self.shake_amount = 0.0
        self._bonus = {'rouge': {}, 'bleu': {}, None: {}}
        self.hidden = {'rouge': set(), 'bleu': set(), None: set()}   # Pokémon cachés dans l'herbe, par équipe qui regarde

        self._build_arenas()
        self.units = []
        self.team_units = {'rouge': [], 'bleu': []}
        self.humans = []
        local = setup['local']
        for team in TEAM_KEYS:
            for i, entry in enumerate(C.build_roster(team, setup['humans'], setup.get('seed'), setup.get('builds'))):
                human = entry.get('human')
                u = Unit(self, entry['species'], team, self._spawn_point(team, i), role=entry['role'],
                         human=human, local=human is not None and human == local, build=entry.get('build'))
                if human is None:
                    u.brain = self.bot_brain(u)
                elif u.local:
                    u.brain = PlayerBrain(u, self)
                    self.player = u
                elif self.authority:
                    u.brain = RemotePlayerBrain(u, self)
                self._add_unit(u)
                self.team_units[team].append(u)
                if human is not None:
                    self.humans.append(u)
        self.remote = next((h for h in self.humans if not h.local), None)
        self.auras = {t: [u for u in self.team_units[t] if u.trait in ('Plus', 'Écran Neige')] for t in TEAM_KEYS}
        self._reset_stats()
        self.results = None             # page de fin de partie
        self._end_t = 0.0
        self._build_camps()
        self._build_bosses()
        self._build_towers()
        from game.pokemon.waves import Waves
        self.waves = Waves(self)
        self._build_pads()
        if self.role == 'host':
            from game.network.netsync import HostSync
            self.net = HostSync(self, setup['host'])
        elif self.role == 'client':
            from game.network.netsync import ClientSync
            self.net = ClientSync(self, setup['link'])
        self._quit_t = 0.0
        self._last_bush = 0
        self.shop = None

        self._warmup = 4
        for u in self.units:          # pas d'ombre figée des Pokémon dans la carte d'ombres
            u.creature.enabled = False
        self.cam_yaw, self.cam_pitch, self.cam_dist = 0.0, 56.0, 24.0
        self.cam_mode = 'follow'          # 'follow' (suit son Pokémon), 'free' (libre) ou 'map' (toute la carte)
        self.cam_view = Vec3(self.cam_yaw, self.cam_pitch, self.cam_dist)
        self.cam_map_target = Vec3(0, 0, 0)
        self.cam_target = Vec3(self.player.position)
        self._build_hud()
        self._place_camera(1)
        self.game.banner.show('Dominez les arènes ! Capturez-les en restant dans leur cercle.', 4)

    def bot_brain(self, u):
        """Cerveau d'un Pokémon contrôlé par l'ordinateur, selon le niveau choisi dans le salon."""
        if self.ai_level == 'expert':
            from game.pokemon.ai import ExpertBrain
            return ExpertBrain(u, self)
        return BotBrain(u, self)

    def _add_unit(self, u):
        u.uid = len(self.units)           # même numéro sur les deux PC (même ordre de création)
        self.units.append(u)

    # ================================================================ construction
    def _reset_stats(self):
        """Statistiques de chaque Pokémon des équipes, pour la page de fin de partie."""
        self.stats = {u.uid: dict.fromkeys(STAT_KEYS, 0) for u in self.units if u.kind == 'pokemon'}
        self._hitters = {}              # victime -> {attaquant: moment du dernier coup} (aides)

    def add_stat(self, u, key, value):
        if u is not None and u.kind == 'pokemon':
            self.stats[u.uid][key] += value

    def _spawn_point(self, team, i):
        bx, bz = C.TEAMS[team]['base']
        a = math.radians(i * 72)
        return bx + math.sin(a) * 3, bz + math.cos(a) * 3

    def _build_arenas(self):
        self.arenas = []
        R = C.ARENA_RADIUS
        for cfg in C.ARENAS:
            p = v3(cfg['pos'])
            y0 = self.stadium.arena_floor(cfg['key'])          # arène perchée sur un plateau
            t = C.TYPES[cfg['type']]
            ring = MeshBuilder().add('ring_thin', (0, 0, 0), (1, 1, 1), col=color.white).entity(
                parent=self.root, emissive=1.0, position=p + Vec3(0, y0 + .15, 0), scale=(R * 2, .25, R * 2),
                color=NEUTRAL_RING)
            crystal = MeshBuilder()
            crystal.add('cone4', (0, .6, 0), (1.2, 1.2, 1.2), col=color.white)
            crystal.add('cone4', (0, -.6, 0), (1.2, 1.2, 1.2), rot=(180, 0, 0), col=color.white)
            crystal = crystal.entity(parent=self.root, emissive=.7, position=p + Vec3(0, y0 + 6, 0), color=NEUTRAL_RING)
            emb = MeshBuilder()
            add_emblem(emb, cfg['type'], (0, 0, 0), 1.6)
            emblem = emb.entity(parent=self.root, emissive=.6, position=p + Vec3(0, y0 + 9.5, 0))
            label = Text(parent=self.root, text=cfg['name'].upper(), position=p + Vec3(0, y0 + 13, 0), billboard=True,
                         scale=26, origin=(0, 0), color=t['light'])
            weather = ArenaWeather(self.root, cfg['pos'], C.WEATHER_RADIUS, cfg['weather'], t['color'], base=y0,
                                   ground=self.stadium.walk_y, arena_radius=R)
            self.arenas.append({'key': cfg['key'], 'name': cfg['name'], 'type': cfg['type'], 'pos': p, 'y0': y0,
                                'nav': 'arena:' + cfg['key'], 'control': 0.0, 'owner': None, 'contested': False,
                                'count': {'rouge': 0, 'bleu': 0}, 'ring': ring, 'crystal': crystal,
                                'emblem': emblem, 'label': label, 'weather': weather,
                                'wx_key': cfg['weather'], 'wx': C.WEATHERS[cfg['weather']],
                                'towers': {}, 'tower_t': 0.0, 'wx_tick': 0.0})

    def _build_camps(self):
        self.camps = []
        for i, cfg in enumerate(C.CAMPS):
            camp = {'cfg': cfg, 'key': f'camp:{i}', 'pos': v3(cfg['pos']), 'units': [], 'alive': True,
                    'respawn_t': 0.0, 'boss': False}
            n = cfg.get('count', 1)
            for k in range(n):
                a = math.radians(k * 360 / n + 30)
                off = 1.8 if n > 1 else 0
                u = Unit(self, cfg['species'], None, (cfg['pos'][0] + math.sin(a) * off, cfg['pos'][1] + math.cos(a) * off),
                         camp=camp)
                u.brain = NeutralBrain(u, self)
                camp['units'].append(u)
                self._add_unit(u)
            self.camps.append(camp)
        self._build_wild()

    def _wild_spots(self, count):
        """Emplacements des petits sauvages : dans la jungle, accessibles, bien espacés."""
        rng = random.Random(21)
        st = self.stadium
        field = st.field('base:rouge', *C.TEAMS['rouge']['base'], 'rouge')
        taken = [c['pos'] for c in self.camps] + [a['pos'] for a in self.arenas]
        spots = []
        for _ in range(4000):
            if len(spots) >= count:
                break
            a, r = rng.uniform(0, math.tau), math.sqrt(rng.random()) * (C.FIELD_RADIUS - 8)
            x, z = math.sin(a) * r, math.cos(a) * r
            if math.hypot(x, z) < C.PIT_RADIUS + 10 or st.blocked(x, z, 1.3):
                continue
            if any(math.hypot(x - tx, z - tz) < C.BASE_RADIUS + 12 for tx, tz in (t['base'] for t in C.TEAMS.values())):
                continue
            p = Vec3(x, 0, z)
            if any((p - q).length() < (C.ARENA_RADIUS + 6 if q in [ar['pos'] for ar in self.arenas] else 9)
                   for q in taken):
                continue
            i, j = st.cell_of(x, z)
            if not st.walk[i, j] or not math.isfinite(field[i, j]):
                continue
            spots.append(p)
            taken.append(p)
        return spots

    def _build_wild(self):
        cfg_w = C.WILD
        rng = random.Random(5)
        for i, p in enumerate(self._wild_spots(cfg_w['count'])):
            species = rng.choice(cfg_w['species'])
            cfg = {'species': species, 'respawn': cfg_w['respawn'], 'xp': cfg_w['xp'], 'points': cfg_w['points']}
            camp = {'cfg': cfg, 'key': f'wild:{i}', 'pos': p, 'units': [], 'alive': True, 'respawn_t': 0.0,
                    'boss': False, 'wild': True}
            u = Unit(self, species, None, (p.x, p.z), camp=camp)
            if species == 'rattata':
                u.hp_factor = cfg_w['hp_factor']
                u.recalc_stats()
                u.hp = u.max_hp
                u._refresh_bar()
            u.brain = NeutralBrain(u, self)
            camp['units'].append(u)
            self._add_unit(u)
            self.camps.append(camp)

    def nearest_wild(self, pos, rng):
        best, bd = None, rng
        for camp in self.camps:
            if camp.get('wild') and camp['alive']:
                u = camp['units'][0]
                d = (flat(u.position) - flat(pos)).length()
                if u.alive and d < bd:
                    best, bd = u, d
        return best

    def _build_towers(self):
        """Une tour par équipe et par arène (celle de l'équipe qui tient l'arène se dresse)."""
        for a in self.arenas:
            for team in TEAM_KEYS:
                u = Unit(self, 'tour', team, (a['pos'].x, a['pos'].z), kind='tower')
                u.type = a['type']
                u.name = f"Tour de l'{a['name']}"
                u.arena = a
                u.brain = TowerBrain(u, self)
                if u.creature.glow is not None:
                    u.creature.glow.color = C.TEAMS[team]['light']
                self._add_unit(u)
                self._despawn(u)
                a['towers'][team] = u

    def _spawn_tower(self, a, team):
        u = a['towers'][team]
        u.reset(pos=Vec3(a['pos']))
        self.fx_burst(u.position + Vec3(0, 2, 0), C.TEAMS[team]['light'], n=16, speed=4, size=.3)
        self.say(f"Une tour se dresse sur l'{a['name']} ({C.TEAMS[team]['name']})", C.TEAMS[team]['light'])

    def _update_towers(self, dt):
        for a in self.arenas:
            owner = a['owner']
            for team, u in a['towers'].items():
                if team != owner and u.alive:          # l'arène a changé de mains : la tour s'effondre
                    self._despawn(u)
            if owner is None:
                continue
            u = a['towers'][owner]
            if not u.alive and not u.creature.enabled:
                a['tower_t'] -= dt
                if a['tower_t'] <= 0:
                    self._spawn_tower(a, owner)

    def release_minion(self, u):
        """Un sbire quitte le terrain (arrivé à destination) : il retourne dans la réserve."""
        u.brain.path = None
        self._despawn(u)

    def enemy_minion_near(self, u, r):
        best, bd = None, r
        for e in self.units:
            if e.alive and e.kind == 'minion' and e.team != u.team:
                d = (flat(e.position - u.position)).length()
                if d < bd:
                    best, bd = e, d
        return best

    def tower_up(self, a):
        return a['owner'] is not None and a['towers'][a['owner']].alive

    def enemy_tower_near(self, u, r):
        """Tour adverse à abattre : à portée, et aucun Pokémon adverse ne la défend à côté."""
        for a in self.arenas:
            if a['owner'] and a['owner'] != u.team and self.tower_up(a):
                t = a['towers'][a['owner']]
                if (flat(t.position - u.position)).length() < r and a['count'][a['owner']] == 0:
                    return t
        return None

    # ---------------------------------------------------------------- météo des arènes
    def weather_zone(self, u):
        """Arène contrôlée dont le quartier (météo) contient ce Pokémon, ou None (1 calcul / image)."""
        if getattr(u, '_wz_t', None) == self.time:
            return u._wz
        p = flat(u.position)
        z = None
        for a in self.arenas:
            if a['owner'] and (p - a['pos']).length() < C.WEATHER_RADIUS:
                z = a
                break
        u._wz, u._wz_t = z, self.time
        return z

    def own_weather(self, u):
        """Effets de la météo d'une arène tenue par l'équipe de u, s'il se trouve dans son quartier."""
        if not u.team:
            return None
        a = self.weather_zone(u)
        return a['wx'] if a is not None and a['owner'] == u.team else None

    def weather_of(self, u):
        """Clé de la météo active pour u (celle d'une arène que son équipe contrôle), ou None."""
        a = self.weather_zone(u) if u.team else None
        return a['wx_key'] if a is not None and a['owner'] == u.team else None

    def _update_weather(self, dt):
        """Tempête de sable : blesse les adversaires de l'équipe qui tient l'arène."""
        for a in self.arenas:
            dps = a['wx'].get('enemy_dps')
            if not dps or not a['owner']:
                continue
            a['wx_tick'] -= dt
            if a['wx_tick'] > 0:
                continue
            a['wx_tick'] = C.WEATHER_TICK
            for u in self.units:
                if u.alive and u.kind in ('pokemon', 'minion') and u.team and u.team != a['owner'] \
                        and (flat(u.position) - a['pos']).length() < C.WEATHER_RADIUS:
                    self.deal_damage(None, u, u.max_hp * dps * C.WEATHER_TICK, raw=True)

    def _build_pads(self):
        """Zones de soin de la jungle : buissons de Baies Sitrus (voir jungle.py : HEAL_PADS)."""
        self.pads = []
        rng = random.Random(8)
        for i, (x, z) in enumerate(C.HEAL_PADS['positions']):
            y = self.stadium.walk_y(x, z)
            bush = MeshBuilder()
            greens = [color.rgb(.16, .42, .18), color.rgb(.2, .5, .2), color.rgb(.13, .36, .16)]
            for k in range(7):                                   # touffe de feuilles arrondie
                a = k * math.tau / 7 + rng.uniform(-.3, .3)
                r = rng.uniform(.35, .6)
                bush.add('blob', (math.sin(a) * r, .35 + rng.uniform(0, .2), math.cos(a) * r),
                         (rng.uniform(.55, .75), rng.uniform(.4, .55), rng.uniform(.55, .75)),
                         col=rng.choice(greens), wobble=.25, grad=.35)
            bush.add('blob', (0, .6, 0), (.7, .55, .7), col=greens[1], wobble=.2, grad=.3)
            body = bush.entity(parent=self.root, position=(x, y, z))
            berries = MeshBuilder()
            for k in range(9):                                   # baies jaunes, bien visibles
                a = k * math.tau / 9 + rng.uniform(-.2, .2)
                r = rng.uniform(.35, .7)
                p = (math.sin(a) * r, rng.uniform(.5, 1.05), math.cos(a) * r)
                berries.add('sphere_md', p, rng.uniform(.17, .22), col=color.rgb(1, .86, .25), grad=.25)
                berries.add('sphere_md', (p[0], p[1] + .15, p[2]), .05, col=color.rgb(.35, .5, .2))
            fruit = berries.entity(parent=self.root, position=(x, y, z), emissive=.25)
            glow = flat_circle(self.root, C.HEAL_PADS['radius'], color.rgba(1, .9, .4, .18), y=y + .06,
                               position=(x, y + .06, z))
            self.pads.append({'pos': Vec3(x, 0, z), 'alive': True, 'respawn_t': 0.0, 'body': body,
                              'fruit': fruit, 'glow': glow, 'key': f'pad:{i}'})

    def _set_pad(self, pad, alive):
        pad['alive'] = alive
        pad['fruit'].enabled = alive
        pad['glow'].enabled = alive

    def _update_pads(self, dt):
        cfg = C.HEAL_PADS
        for pad in self.pads:
            if not pad['alive']:
                pad['respawn_t'] -= dt
                if pad['respawn_t'] <= 0:
                    self._set_pad(pad, True)
                continue
            for u in self.units:
                if u.alive and u.kind == 'pokemon' and u.hp < u.max_hp * (1 - cfg['min_missing']) \
                        and (flat(u.position) - pad['pos']).length() < cfg['radius'] + u.radius:
                    amount = (u.max_hp * cfg['heal_pct'] + cfg['heal_flat']) * (1 + u.mods['heal_boost'])
                    u.heal(amount)
                    self._set_pad(pad, False)
                    pad['respawn_t'] = cfg['respawn']
                    self.fx_burst(u.position + Vec3(0, 1, 0), color.rgb(1, .9, .4), n=14, speed=3, size=.25)
                    if u is self.player or u is self.remote:
                        self.tell(u, f'Baie Sitrus : +{int(amount)} PV', color.rgb(.6, 1, .5))
                    break

    def nearest_pad(self, pos, rng):
        best, bd = None, rng
        for pad in self.pads:
            if pad['alive']:
                d = (pad['pos'] - flat(pos)).length()
                if d < bd:
                    best, bd = pad, d
        return best

    def _build_bosses(self):
        self.bosses = {}
        for key, cfg in (('legendary', C.LEGENDARY), ('final', C.FINAL_BOSS)):
            camp = {'cfg': cfg, 'key': 'pit', 'pos': Vec3(0, 0, 0), 'units': [], 'alive': False,
                    'respawn_t': 0.0, 'boss': True, 'kind': key}
            u = Unit(self, cfg['species'], None, (0, 2), camp=camp)
            u.brain = NeutralBrain(u, self)
            camp['units'].append(u)
            self._add_unit(u)
            self._despawn(u)
            self.bosses[key] = camp
        self.next_legendary = C.LEGENDARY['first_spawn']
        self.final_spawned = False
        self.boss_squad = {'rouge': [], 'bleu': []}

    def _despawn(self, u):
        u.alive = False
        u.creature.enabled = False

    # ================================================================ messages (les deux PC)
    def emit(self, *e):
        """Événement visible à rejouer chez l'invité (tir, zone, dégâts...)."""
        if self.net is not None and self.authority:
            self.net.event(e)

    def say(self, message, col):
        """Ligne dans le fil des événements, chez les deux joueurs."""
        self.feed.push(message, col)
        self.emit('feed', message, rc(col))

    def announce(self, message, duration, col=color.white, big=False, to=None):
        """Bannière centrale, pour tout le monde (to=None) ou pour un seul joueur humain."""
        if to is None or to is self.player:
            self.game.banner.show(message, duration, text_color=col, big=big)
        if to is None or (to is self.remote and self.remote is not None):
            self.emit('ban', message, duration, rc(col), big)

    def tell(self, unit, message, col):
        """Ligne du fil des événements pour un seul joueur humain."""
        if unit is self.player:
            self.feed.push(message, col)
        elif unit is self.remote:
            self.emit('feed', message, rc(col))

    def fx_impact(self, kind, pos, size=.4):
        """Impact d'un coup (au contact...), aussi montré sur l'autre PC."""
        from game.world import fx
        fx.impact(kind, pos, size, ground=self.stadium.walk_y(pos.x, pos.z))
        self.emit('impact', kind, round(pos.x, 2), round(pos.y, 2), round(pos.z, 2), size)

    def fx_burst(self, pos, col, n=8, speed=4.0, size=.25):
        from game.world import fx
        fx.burst(None, pos, col, n=n, speed=speed, size=size)
        self.emit('burst', round(pos.x, 2), round(pos.y, 2), round(pos.z, 2), rc(col), n, speed, size)

    # ================================================================ règles
    def hostile(self, a, b):
        return a is not b and a.team != b.team and not (a.team is None and b.team is None)

    def team_bonus(self, team, kind):
        return self._bonus.get(team, {}).get(kind, 0.0)

    def _refresh_bonus(self):
        self._bonus = {'rouge': {}, 'bleu': {}, None: {}}
        for a in self.arenas:
            if a['owner']:
                kind, value, _ = C.ARENA_BONUS[a['type']]
                self._bonus[a['owner']][kind] = self._bonus[a['owner']].get(kind, 0) + value

    def arena_at(self, pos):
        for a in self.arenas:
            if (flat(pos) - a['pos']).length() < C.ARENA_RADIUS:
                return a
        return None

    def deal_damage(self, src, tgt, base, status=None, stun=0.0, raw=False, contact=False, cat='phys'):
        """Inflige des dégâts. `base` : dégâts bruts de l'attaque (voir kit.raw_damage), réduits ici par
        la défense de la cible (Défense ou Défense spéciale selon `cat`), les types et les bonus.
        raw=True : dégâts fixes (brûlure, base...)."""
        if not tgt.alive:
            return
        eff = 1.0
        if src is None:
            raw = True
        if raw:
            dmg = base
        else:
            eff = C.TYPE_CHART.get((src.type, tgt.type), 1.0)
            mit = 1.0 if cat == 'true' else kit.mitigation(tgt.stats['def' if cat == 'phys' else 'spd'])
            dmg = base * src.damage_mult() * eff * mit * tgt.defense_mult()
            if src.kind == 'pokemon' and tgt.kind == 'pokemon':
                src.aggro_t = self.time
            dmg *= random.uniform(1 - C.DAMAGE_SPREAD, 1 + C.DAMAGE_SPREAD)
        dmg = max(1, round(dmg))
        if tgt.invuln > 0:
            return
        if dmg >= tgt.hp and tgt.mods['sash'] > 0 and tgt.sash_cd <= 0 and tgt.hp > 1:
            dmg = max(1, int(tgt.hp) - 1)                  # Ceinture Force : survit avec 1 PV
            tgt.sash_cd = tgt.mods['sash']
            if tgt.local or tgt is self.remote:
                self.announce('Ceinture Force !', 1.5, color.rgb(1, .8, .4), to=tgt)
        hp0 = tgt.hp
        killed = tgt.hurt(dmg, src if src is not None and src is not tgt else tgt.last_hit_by, status, stun)
        done = min(dmg, max(0, hp0))
        if src is not None and src is not tgt and src.kind == 'pokemon' and tgt.kind == 'pokemon' \
                and src.team != tgt.team:
            self.add_stat(src, 'dmg', done)
            if tgt.team:
                self._hitters.setdefault(tgt.uid, {})[src.uid] = self.time
        self.add_stat(tgt, 'taken', done)
        if contact and src is not None and src is not tgt and tgt.mods['thorns'] > 0 and src.alive:
            self.deal_damage(tgt, src, done * tgt.mods['thorns'], raw=True)          # Casque Brut
        if contact and src is not None and src.trait == 'Mâchoire' and src.alive:     # talent : vol de vie
            src.heal(done * src.trait_cfg['drain'])
        if not raw and src is not None and src is not tgt and src.alive and src.mods['lifesteal'] > 0:
            src.heal(done * src.mods['lifesteal'])
        code = 1 if eff > 1 else 2 if eff < 1 else 0
        self._damage_text(tgt, dmg, code, src)
        self.emit('hit', tgt.uid, dmg, code, src.uid if src is not None else -1)
        if killed:
            self.on_ko(tgt, tgt.last_hit_by)

    def _damage_text(self, tgt, dmg, code, src):
        if (flat(tgt.position) - flat(self.cam_target)).length() < 26:
            col = color.rgb(1, .4, .35) if tgt.local else (
                color.rgb(1, .95, .3) if code == 1 else color.rgb(.8, .8, .8) if code == 2 else color.white)
            floating_text(f'-{dmg}', tgt.creature.world_position + Vec3(0, tgt.data['scale'] * 1.6 + 1, 0), col,
                          1.0 if ((src is not None and src.local) or tgt.local) else .75)
        if tgt.local:
            self.shake(.25)

    def show_hit(self, tgt, dmg, code, src):
        """Invité : dégâts annoncés par l'hôte."""
        tgt.last_hit_t = self.time
        if tgt.alive:
            tgt.creature.hit_flash(Vec4(1, .3, .25, .7) if tgt.local else Vec4(1, 1, 1, .8), .12)
        self._damage_text(tgt, dmg, code, src)

    def on_ko(self, victim, killer):
        if killer is victim:
            killer = None
        kteam = killer.team if killer is not None else None
        if victim.kind == 'pokemon':                              # joueur ou IA d'équipe
            victim.respawn_t = C.RESPAWN_TIME + C.RESPAWN_PER_MIN * self.time / 60
            victim.ko_time = self.time
            self.add_stat(victim, 'deaths', 1)
            hitters = self._hitters.pop(victim.uid, {})
            if kteam and kteam != victim.team:
                self.add_stat(killer, 'ko', 1)
                if killer.trait == 'Impudence':                  # talent : chaque K.O. l'enrage
                    killer.add_buff('impudence', C.BUFFS['impudence']['duration'])
                self.add_stat(killer, 'points', C.POINTS_KO)
                for uid, t in hitters.items():
                    if uid != killer.uid and self.time - t < C.ASSIST_TIME:
                        self.add_stat(self.units[uid], 'assists', 1)
                        self.reward(self.units[uid], C.XP_ASSIST, C.GOLD_ASSIST)
                self.score[kteam] += C.POINTS_KO
                bounty = 1 + C.BOUNTY * max(0, victim.level - killer.level)     # prime : adversaire plus fort
                self.reward(killer, 0, C.GOLD_KO * bounty)
                self._share_xp(killer, C.XP_KO * bounty)
                self.say(f"{self.label(killer)} ({C.TEAMS[kteam]['name']}) a mis K.O. {self.label(victim)}",
                         C.TEAMS[kteam]['light'])
            else:
                self.say(f"{self.label(victim)} ({C.TEAMS[victim.team]['name']}) est K.O.", color.rgb(.8, .8, .8))
            if victim.is_player:
                self.announce(f'{victim.name} est K.O. !   B : boutique', 2, color.rgb(1, .5, .45), to=victim)
            else:
                self.bot_shop(victim)
            return
        if victim.kind == 'tower':
            self._tower_destroyed(victim, kteam)
            return
        if victim.kind == 'minion':
            victim.respawn_t = 1.2
            cfg = C.MINIONS[victim.species]
            if killer is not None and killer.kind == 'pokemon':
                self.reward(killer, 0, cfg['gold'])
                self._share_xp(killer, cfg['xp'])
            elif kteam:                               # tué par un sbire ou une tour : un peu d'XP aux Pokémon proches
                for u in self.team_units[kteam]:
                    if u.alive and (flat(u.position - victim.position)).length() < C.MINION_XP_SHARE:
                        self._gain(u, cfg['xp'] * C.XP_SHARE)
            return
        camp = victim.camp
        victim.respawn_t = 1.5                                    # disparition après l'animation
        cfg = camp['cfg']
        if kteam:
            n = len(camp['units'])
            self.score[kteam] += cfg['points'] / n
            self.add_stat(killer, 'points', cfg['points'] / n)
            self.reward(killer, 0, cfg.get('gold', 0) / n)
            self._share_xp(killer, cfg['xp'] / n)
        if all(not u.alive for u in camp['units']):
            camp['alive'] = False
            if camp['boss']:
                self._boss_defeated(camp, killer)
            else:
                camp['respawn_t'] = cfg['respawn']
                if cfg.get('buff') and killer is not None and kteam:
                    b = C.BUFFS[cfg['buff']]
                    killer.add_buff(cfg['buff'], b['duration'])
                    self.say(f"{self.label(killer)} obtient {b['name']} ({b['desc']})", b['color'])
                    if killer.is_player:
                        self.announce(f"{b['name']} : {b['desc']} !", 2.5, b['color'], to=killer)

    def _tower_destroyed(self, tower, kteam):
        a = tower.arena
        tower.respawn_t = 1.5
        a['tower_t'] = C.TOWER['respawn']
        self.shake_at(tower.position, .4)
        if not kteam or kteam == tower.team:
            return
        self.score[kteam] += C.TOWER['points']
        for u in self.team_units[kteam]:
            if u.alive and (flat(u.position - tower.position)).length() < 20:
                self.reward(u, C.TOWER['xp'], C.TOWER['gold'])
                self.add_stat(u, 'points', C.TOWER['points'] / 2)
        t = C.TEAMS[kteam]
        self.say(f"L'équipe {t['name']} a abattu la tour de l'{a['name']}", t['light'])
        for h in self.humans:
            if h.team == kteam or (flat(h.position) - a['pos']).length() < 40:
                self.announce(f"Tour de l'{a['name']} abattue !", 2, t['light'], to=h)

    def _boss_defeated(self, camp, killer):
        cfg = camp['cfg']
        name = C.SPECIES[cfg['species']]['name']
        kteam = killer.team if killer is not None else None
        if camp['kind'] == 'legendary':
            self.next_legendary = self.time + cfg['respawn']
        if not kteam:
            return
        self.score[kteam] += cfg['points']
        self.add_stat(killer, 'points', cfg['points'])
        b = C.BUFFS[cfg['buff']]
        for u in self.team_units[kteam]:
            self.reward(u, cfg['xp'], cfg.get('gold', 0))
            if u.alive:
                u.add_buff(cfg['buff'], b['duration'])
        tname = C.TEAMS[kteam]['name']
        self.announce(f"L'équipe {tname} a vaincu {name} ! +{cfg['points']} points et {b['name']}", 4,
                      C.TEAMS[kteam]['light'])
        self.boss_squad = {'rouge': [], 'bleu': []}

    def reward(self, u, xp=0.0, gold=0.0):
        """Donne de l'XP et des Poké Dollars à un Pokémon d'équipe."""
        if u is None or u.kind != 'pokemon':
            return
        if gold:
            u.gold += gold
            if u is self.player and u.alive:
                from game.interface.lobby import F_BOLD
                floating_text(f'+{int(round(gold))} ₽', u.creature.world_position
                              + Vec3(.8, u.data['scale'] * 1.6 + .9, 0), color.rgb(1, .85, .3), .7, **F_BOLD)
        if xp:
            self._gain(u, xp)

    def _share_xp(self, killer, amount):
        """XP d'un K.O. : tout pour le vainqueur, une part pour ses alliés proches."""
        if killer is None or killer.kind != 'pokemon':
            return
        self._gain(killer, amount)
        for u in self.team_units[killer.team]:
            if u is not killer and u.alive and (flat(u.position - killer.position)).length() < C.XP_SHARE_RADIUS:
                self._gain(u, amount * C.XP_SHARE)

    def _gain(self, u, amount):
        """Donne de l'XP (plus s'il est en retard sur les adversaires) ; le joueur voit « +XP » monter
        au-dessus de son Pokémon."""
        enemy = 'bleu' if u.team == 'rouge' else 'rouge'
        foes = self.team_units.get(enemy, ())
        if foes:
            behind = sum(e.level for e in foes) / len(foes) - u.level
            amount *= 1 + min(C.CATCHUP_MAX, C.CATCHUP_XP * max(0.0, behind))
        if u.level < C.MAX_LEVEL and u is self.player and u.alive:
            floating_text(f'+{int(round(amount))} XP', u.creature.world_position + Vec3(0, u.data['scale'] * 1.6 + 1.4, 0),
                          color.rgb(.55, .85, 1), .75)
        u.gain_xp(amount)

    # ================================================================ boutique
    def can_shop(self, u):
        """La boutique est ouverte dans sa base, ou pendant qu'on est K.O."""
        if u.kind != 'pokemon':
            return False
        if not u.alive:
            return True
        return (flat(u.position) - v3(C.TEAMS[u.team]['base'])).length() < C.BASE_RADIUS + C.SHOP_RANGE

    def buy(self, u, key):
        it = C.ITEMS.get(key)
        if it is None or key in u.items or len(u.items) >= C.ITEM_SLOTS or u.gold < it['price'] \
                or not self.can_shop(u):
            return False
        u.gold -= it['price']
        u.items.append(key)
        u.recalc_stats()
        if u.is_player:
            self.tell(u, f"{u.name} tient maintenant : {it['name']}", color.rgb(1, .85, .4))
        return True

    def sell(self, u, index):
        if not (0 <= index < len(u.items)) or not self.can_shop(u):
            return False
        key = u.items.pop(index)
        u.gold += int(C.ITEMS[key]['price'] * C.SELL_RATIO)
        u.recalc_stats()
        return True

    def request_buy(self, key):
        if self.authority:
            self.buy(self.player, key)
        else:
            self.net.link.send({'t': 'buy', 'i': key})

    def request_sell(self, index):
        if self.authority:
            self.sell(self.player, index)
        else:
            self.net.link.send({'t': 'sell', 'n': index})

    def next_bot_item(self, u):
        """Prochain objet que l'ordinateur veut acheter pour ce Pokémon (ou None)."""
        if len(u.items) >= C.ITEM_SLOTS:
            return None
        for key in C.BOT_ITEMS[kit.line_role(u.species, u.build)]:
            if key == 'attaque':
                phys = sum(1 for mv in u.moves if mv.get('cat') == 'phys')
                key = 'bandeau_choix' if phys * 2 >= len(u.moves) else 'lunettes_choix'
            if key not in u.items:
                return key
        return None

    def wants_shop(self, u):
        """L'IA a de quoi acheter son prochain objet et n'est pas trop loin : elle rentre à pied."""
        if u.is_player:
            return False
        key = self.next_bot_item(u)
        if key is None or u.gold < C.ITEMS[key]['price'] + C.BOT_SHOP_MARGIN:
            return False
        return (flat(u.position) - v3(C.TEAMS[u.team]['base'])).length() < C.BOT_SHOP_DISTANCE

    def bot_shop(self, u):
        """Achats de l'ordinateur : les objets de son rôle, dans l'ordre (voir items.py : BOT_ITEMS)."""
        if u.is_player or not self.can_shop(u):
            return
        key = self.next_bot_item(u)
        while key is not None and u.gold >= C.ITEMS[key]['price']:
            self.buy(u, key)
            key = self.next_bot_item(u)

    def toggle_shop(self):
        from game.interface.shop import Shop
        if self.shop is not None:
            destroy_tree(self.shop)
            self.shop = None
        else:
            self.shop = Shop(self)
            br = self.player.brain                   # la boutique fige le Pokémon : ordre et visée annulés
            if isinstance(br, PlayerBrain):
                br.order = None
                if br.aiming is not None:
                    br.release(cast=False)

    def label(self, u):
        """Nom affiché dans le fil : « Pikachu (J2) » pour un joueur humain à deux."""
        if u.is_player and len(self.humans) > 1:
            return f'{u.name} (J{u.human + 1})'
        return u.name

    def on_level_up(self, u):
        if u.is_player:
            self.tell(u, f'{u.name} passe au niveau {u.level} !', color.rgb(1, .95, .5))
            kind, form, cfg = u.transform_info()
            if u.level == cfg['level']:
                if u is self.player and hasattr(self, 'slots'):
                    self._build_slots()
                self.announce(f"{cfg['name']} disponible !   Touche {key_label(C.TRANSFORM_KEY)}", 3,
                              color.rgb(1, .7, .9), to=u)

    def on_transform(self, u, active):
        """Début ou fin d'une Méga-Évolution / d'un Dynamax."""
        face = self.map_faces.get(u) if hasattr(self, 'map_faces') else None
        if face is not None:
            self.portraits.show(face, u.form)
        if u is self.player and hasattr(self, 'slots'):
            self._build_slots()
        if not active or not self.authority:
            return
        kind, form, cfg = u.transform_info()
        t = C.TEAMS[u.team]
        if kind == 'mega':
            before = C.SPECIES[C.form_for(u.species, u.level)]['name']
            self.say(f"{before} ({t['name']}) Méga-Évolue en {u.name} !", t['light'])
        else:
            self.say(f"{self.label(u)} ({t['name']}) passe en Dynamax !", t['light'])
        if u.is_player:
            self.announce(f"{cfg['name']} ! ({int(cfg['duration'])} s)", 2.5, color.rgb(1, .7, .9), to=u)

    def on_moves_unlocked(self, u, new):
        """Nouvelles attaques débloquées par un passage de niveau."""
        if u is self.player:
            self._build_slots()
        if u.is_player and new and self.authority:
            names = ', '.join(f"{mv['name']} ({key_label(mv['key'])})" for mv in new)
            ult = any(mv['slot'] == 'ult' for mv in new)
            self.announce(('ULTIME DÉBLOQUÉE : ' if ult else 'Nouvelle attaque : ') + names, 3,
                          color.rgb(1, .85, .4) if ult else color.rgb(.8, .95, 1), to=u)

    # ---------------------------------------------------------------- attaques : aides
    def enemies_near(self, u, pos, r):
        p = flat(pos)
        return [e for e in self.units if e.alive and self.hostile(u, e) and e.team and
                (flat(e.position) - p).length() < r]

    def nearest_enemy(self, u, pos, r):
        best, bd = None, r
        p = flat(pos)
        for e in self.units:
            if e.alive and self.hostile(u, e) and e not in self.hidden.get(u.team, ()):
                d = (flat(e.position) - p).length()
                if d < bd:
                    best, bd = e, d
        return best

    def mouse_ground(self, y=0.0):
        """Point du sol (à la hauteur y) sous le curseur de la souris."""
        from panda3d.core import Point2, Point3
        from ursina import application, scene
        base = application.base
        mx = my = 0.0
        if base.mouseWatcherNode is not None and base.mouseWatcherNode.has_mouse():
            mp = base.mouseWatcherNode.get_mouse()
            mx, my = mp.x, mp.y
        near, far = Point3(), Point3()
        if not base.camLens.extrude(Point2(mx, my), near, far):
            return Vec3(self.player.position)
        a = scene.get_relative_point(base.cam, near)
        b = scene.get_relative_point(base.cam, far)
        dy = b.y - a.y
        if abs(dy) < 1e-6:
            return Vec3(self.player.position)
        k = (y - a.y) / dy
        return Vec3(a.x + (b.x - a.x) * k, y, a.z + (b.z - a.z) * k)

    def announce_cast(self, u, name):
        if (flat(u.position) - flat(self.cam_target)).length() < 24:
            floating_text(name + ' !', u.creature.world_position + Vec3(0, u.data['scale'] * 1.6 + 1.8, 0),
                          color.rgb(1, .95, .45) if u.team == 'rouge' else color.rgb(1, .7, .6), .8)
        self.emit('cast', u.uid, name)

    def shake(self, amount):
        self.shake_amount = max(self.shake_amount, amount)

    def shake_at(self, pos, amount):
        if (flat(pos) - flat(self.cam_target)).length() < 18:
            self.shake(amount)

    def find_target(self, u, rng):
        """Cible de la visée automatique : l'adversaire le plus proche (les Pokémon d'équipe d'abord)."""
        best, score = None, 1e9
        hidden = self.hidden[u.team]
        for e in self.units:
            if e.alive and self.hostile(u, e) and e not in hidden:
                d = (flat(e.position - u.position)).length()
                if d < rng:
                    s = d + (0 if e.kind == 'pokemon' else 8)
                    if s < score and self.can_see(u, e):        # pas de visée à travers les murs
                        best, score = e, s
        return best

    def can_see(self, a, b):
        """Ligne de vue entre deux Pokémon (rien ne s'interpose), gardée en mémoire 0,15 s."""
        key = (a.uid, b.uid) if a.uid < b.uid else (b.uid, a.uid)
        hit = self._los.get(key)
        if hit is not None and 0 <= self.time - hit[0] < .15:
            return hit[1]
        ok = self.stadium.sees(a.position, b.position)
        self._los[key] = (self.time, ok)
        return ok

    def blind_target(self, u, reach, forward):
        """Adversaire touché par un coup porté sans cible : le plus proche à portée (devant u si
        `forward` est donné), qu'il soit visible ou caché dans les hautes herbes."""
        best, bd = None, 1e9
        for e in self.units:
            if e.alive and self.hostile(u, e):
                to_e = flat(e.position - u.position)
                d = to_e.length() - e.radius
                if d < reach and d < bd and (forward is None or d < .5 or to_e.normalized().dot(forward) > .5) \
                        and self.can_see(u, e):
                    best, bd = e, d
        return best

    def in_vision(self, team, u):
        """Vrai si l'équipe `team` voit u : près d'un de ses Pokémon, de sa base ou d'une arène
        qu'elle contrôle (et pas caché dans les hautes herbes)."""
        if u.team == team:
            return True
        if u in self.hidden[team]:
            return False
        p = flat(u.position)
        if (p - v3(C.TEAMS[team]['base'])).length() < C.BASE_RADIUS + 8:
            return True
        if any(a['owner'] == team and (p - a['pos']).length() < C.ARENA_RADIUS + 4 for a in self.arenas):
            return True
        return any(o.alive and (flat(o.position) - p).length() < C.VISION for o in self.team_units[team])

    # ================================================================ IA : objectifs
    def base_goal(self, team):
        return ('base:' + team, v3(C.TEAMS[team]['base']), C.BASE_RADIUS - 3)

    def _goal_count(self, team, key, exclude):
        return sum(1 for u in self.team_units[team]
                   if u is not exclude and not u.is_player and u.alive and u.brain.goal and u.brain.goal[0] == key)

    def active_boss(self):
        for camp in self.bosses.values():
            if camp['alive']:
                return camp
        return None

    def choose_goal(self, u, current):
        team = u.team
        if self.wants_shop(u):
            return self.base_goal(team)
        boss = self.active_boss()
        if boss is not None and u in self.boss_squad[team]:
            return ('pit', Vec3(0, 0, 0), 7)
        if u.role == 'jungle':
            best, bs = None, 1e9
            for camp in self.camps:
                if camp['alive']:
                    s = (camp['pos'] - flat(u.position)).length() - (30 if camp['cfg'].get('buff') else 0) \
                        + (12 if camp.get('wild') else 0)
                    if s < bs:
                        best, bs = camp, s
            if best is not None and random.random() < .85:
                return (best['key'], best['pos'], 4)
        best, bs = None, 1e9
        for a in self.arenas:
            d = (a['pos'] - flat(u.position)).length()
            s = d / 30
            enemy = 'bleu' if team == 'rouge' else 'rouge'
            if a['owner'] == team:
                s += 3.5
                if a['count'][enemy] > 0:
                    s -= 5                      # défendre une arène attaquée
            if a['key'] == u.role:
                s -= 1.5
            if current and current[0] == a['nav']:
                s -= .8                         # garder son objectif (évite les hésitations)
            s += 1.2 * self._goal_count(team, a['nav'], u)
            if s < bs:
                best, bs = a, s
        return (best['nav'], best['pos'], C.ARENA_RADIUS - 4)

    def _assign_boss_squads(self, size):
        for team in TEAM_KEYS:
            bots = [u for u in self.team_units[team] if not u.is_player]
            bots.sort(key=lambda u: (u.role != 'jungle', (flat(u.position)).length()))
            self.boss_squad[team] = bots[:size]

    # ================================================================ boucle
    def _warmup_step(self):
        """Premières images : on calcule la carte d'ombres du décor seul, puis on la fige."""
        self._warmup -= 1
        if self._warmup == 0:
            from game.world.geometry import freeze_shadows
            freeze_shadows(self.game.sun)
            self.stadium.vortex.show()
            for u in self.units:
                if u.alive:
                    u.creature.enabled = True
            self.root.enabled = True
            self._ignore_passive_entities()
            if self.role == 'client':
                self.net.loaded()

    def _purge_entities(self):
        """Retire de la liste d'Ursina les entités qui ne sont plus dans la scène (restes d'objets
        détruits) : Ursina les parcourrait sinon à chaque image jusqu'à la fin de la partie."""
        from ursina import scene
        tops = {scene.get_top(), camera.ui.get_top()}
        keep = []
        for e in scene.entities:
            try:
                if not e.is_empty() and e.get_top() in tops:
                    keep.append(e)
            except Exception:
                pass
        scene.entities = keep

    def ignore_passive(self, root):
        """Entités créées en cours de partie (nouvelle forme après une évolution...) : celles qui n'ont
        rien à faire à chaque image sont marquées `ignore` (voir _ignore_passive_entities)."""
        stack = [root]
        while stack:
            e = stack.pop()
            if not hasattr(type(e), 'update') and not hasattr(type(e), 'input') and not getattr(e, 'scripts', None):
                e.ignore = True
            stack.extend(e.children)

    def _ignore_passive_entities(self):
        """Ursina parcourt chaque image toutes ses entités : celles qui n'ont ni update()
        ni input() (pièces des Pokémon, barres de vie, décor de l'interface...) sont
        marquées `ignore` pour être sautées tout de suite."""
        from ursina import scene
        for e in scene.entities:
            if not hasattr(type(e), 'update') and not hasattr(type(e), 'input') and not getattr(e, 'scripts', None):
                e.ignore = True

    def update(self):
        self.portraits.tick()
        if self._warmup > 0:
            self._warmup_step()
            return
        self._quit_t -= time.dt
        self._purge_t = getattr(self, '_purge_t', 3.0) - time.dt
        if self._purge_t <= 0:
            self._purge_t = 3.0
            self._purge_entities()
        if self.net is not None:
            self.net.poll()
        if self.role == 'host' and not self.net.guest_ready:        # l'invité charge encore la carte
            self._set_text(self.center_text, 'En attente du joueur 2 (chargement de la carte)...')
            self._place_camera(1)
            self.net.flush()
            return
        dt = min(time.dt, .05)
        if self.state == 'end':
            dt *= .25
        self.time += dt
        self.shake_amount = max(0, self.shake_amount - dt * 2)
        self.stadium.update(dt, self.cam_target)
        for a in self.arenas:
            a['weather'].update(dt, self.cam_target, owned=a['owner'] is not None)
            a['emblem'].rotation_y += dt * 40
            a['emblem'].y = a['y0'] + 9.5 + math.sin(self.time * 1.5 + a['pos'].x) * .4
            a['crystal'].rotation_y -= dt * 60

        if self.authority:
            self._update_units(dt)
            self._separate_units()
        else:
            self.net.render()
            for u in self.units:
                if u.creature.enabled:
                    u.update(dt)
            self._separate_local()
        self._update_bushes()
        self._update_attacks(dt)
        if self.authority and self.state == 'play':
            self._update_base_zones(dt)
            self._update_capture(dt)
            self._update_spawns(dt)
            self._update_pads(dt)
            self._update_towers(dt)
            self._update_weather(dt)
            self.waves.update(dt)
            self._check_end()
        self._update_hud(dt)
        self._update_results()
        self._place_camera(min(1, dt * 8))
        if self.net is not None:
            self.net.flush()

    def _update_units(self, dt):
        for u in self.units:
            if u.alive:
                u.update(dt)
            elif u.creature.enabled:
                u.update(dt)
                u.respawn_t -= dt
                if u.kind != 'pokemon':
                    if u.respawn_t <= 0:
                        u.creature.enabled = False
                elif self.time - getattr(u, 'ko_time', self.time) > 1.8:          # le corps disparaît
                    u.creature.visible = False
                if u.kind == 'pokemon' and u.respawn_t <= 0:
                    self._respawn(u)

    def _update_bushes(self):
        """Hautes herbes : qui est caché à quelle équipe, et affichage pour l'équipe de ce PC."""
        st = self.stadium
        for u in self.units:
            u.bush = st.bush_at(u.position.x, u.position.z) if u.alive else 0
        sight = C.BUSH['sight']
        for team in TEAM_KEYS:
            watchers = [o for o in self.team_units[team] if o.alive]
            self.hidden[team] = {u for u in self.units
                                 if u.bush and u.team not in (None, team) and not u.revealed()
                                 and not any(o.bush == u.bush or (flat(o.position - u.position)).length() < sight
                                             for o in watchers)}
        me = self.player
        for u in self.units:
            u.set_veiled(u in self.hidden[me.team])
        if me.bush and me.bush != self._last_bush:          # on entre dans l'herbe : froissement
            from game.world import fx
            fx.burst(None, me.position + Vec3(0, .8, 0), color.rgb(.3, .7, .4), n=6, speed=2.5, size=.2)
        self._last_bush = me.bush

    def _respawn(self, u):
        i = self.team_units[u.team].index(u)
        pos = v3(self._spawn_point(u.team, i))
        if u.is_player:
            self._teleport_human(u, pos)
        else:
            u.reset(pos=pos)
            u.brain.target = None
            u.brain.mode = None
        u.invuln = C.RESPAWN_INVULN

    def _teleport_human(self, u, pos):
        """Remet un joueur humain à un endroit précis (réapparition, nouvelle partie)."""
        u.reset(pos=pos)
        if isinstance(u.brain, RemotePlayerBrain):
            u.brain.teleport(pos)
            self.emit('tp', u.uid, round(pos.x, 3), round(pos.z, 3), u.brain.life)

    def _separate_units(self):
        """Empêche les Pokémon de se superposer (positions lues une seule fois).
        Le Pokémon de l'invité ne bouge pas ici : c'est lui qui décide de sa position."""
        items = [[u, u.creature.get_x(), u.creature.get_z(), False, 0 if u.net_driven or u.kind == 'tower' else 1]
                 for u in self.units if u.alive]
        items.sort(key=lambda it: it[1])
        n = len(items)
        for i, a in enumerate(items):
            ua = a[0]
            for j in range(i + 1, n):
                b = items[j]
                m = ua.radius + b[0].radius
                dx, dz = b[1] - a[1], b[2] - a[2]
                if dx >= 4.5:                     # triés selon x : les suivants sont encore plus loin
                    break
                if -m < dx < m and -m < dz < m:
                    d = math.hypot(dx, dz)
                    wa, wb = a[4], b[4]
                    if 0 < d < m and wa + wb:
                        push = (m - d) / (wa + wb) / d
                        a[1] -= dx * push * wa
                        a[2] -= dz * push * wa
                        b[1] += dx * push * wb
                        b[2] += dz * push * wb
                        a[3] = b[3] = True
        gy = self.stadium.walk_y
        for u, x, z, moved, w in items:
            if moved and w:
                u.creature.set_pos(x, gy(x, z), z)

    def _separate_local(self):
        """Invité : seul son propre Pokémon s'écarte des autres."""
        u = self.player
        if not u.alive:
            return
        x, z = u.creature.get_x(), u.creature.get_z()
        moved = False
        for o in self.units:
            if o is u or not o.alive or (o.kind == 'minion' and o.team == u.team):
                continue
            m = u.radius + o.radius
            dx, dz = x - o.creature.get_x(), z - o.creature.get_z()
            if -m < dx < m and -m < dz < m:
                d = math.hypot(dx, dz)
                if 0 < d < m:
                    x += dx / d * (m - d)
                    z += dz / d * (m - d)
                    moved = True
        if moved:
            u.creature.set_pos(x, self.stadium.walk_y(x, z), z)

    def _update_melee(self, dt):
        keep = []
        for hit in self.pending_hits:
            hit[0] -= dt
            if hit[0] > 0:
                keep.append(hit)
                continue
            _, src, tgt, dmg, status, stun = hit
            if src.alive and tgt.alive and src.status['stun'] <= 0:
                reach = src.auto['range'] + tgt.radius + .3
                if (flat(tgt.position - src.position)).length() < reach and self.can_see(src, tgt):
                    self.deal_damage(src, tgt, dmg, status, stun, contact=True)
                    src.on_auto_hit(tgt)
                    self.fx_impact(src.type, tgt.position + Vec3(0, 1, 0), .4)
        self.pending_hits = keep

    def _update_attacks(self, dt):
        if self.authority:
            self._update_melee(dt)
        self.particles.update(dt)
        for p in self.projectiles:
            if p.alive:
                p.update(dt)
        self.projectiles = [p for p in self.projectiles if p.alive]
        for h in list(self.hazards):
            if h.alive:
                h.update(dt)
        self.hazards = [h for h in self.hazards if h.alive]

    def _update_base_zones(self, dt):
        for team in TEAM_KEYS:
            bp = v3(C.TEAMS[team]['base'])
            for u in self.units:
                if u.alive and u.team and (flat(u.position) - bp).length() < C.BASE_RADIUS + 1:
                    if u.team == team:
                        u.heal(C.BASE_HEAL * dt)
                        if not u.is_player and u.kind == 'pokemon':
                            self.bot_shop(u)
                    else:
                        u.hurt(C.BASE_DAMAGE * dt, None)
                        if not u.alive:
                            u.respawn_t = C.RESPAWN_TIME

    def _update_capture(self, dt):
        R = C.ARENA_RADIUS
        changed = False
        for a in self.arenas:
            cnt = {'rouge': 0, 'bleu': 0}
            mins = {'rouge': 0, 'bleu': 0}
            for u in self.units:
                if u.alive and u.team and u.kind in ('pokemon', 'minion') \
                        and (flat(u.position) - a['pos']).length() < R:
                    (cnt if u.kind == 'pokemon' else mins)[u.team] += 1
            a['count'] = cnt
            nr, nb = cnt['rouge'], cnt['bleu']
            mr, mb = mins['rouge'], mins['bleu']
            rate = dt / C.CAPTURE_TIME
            if self.tower_up(a) and ((a['owner'] == 'rouge' and nb) or (a['owner'] == 'bleu' and nr)):
                rate *= C.TOWER['capture_slow']          # la tour gêne la capture adverse
            # contestée : les deux équipes sont présentes (les sbires qui défendent comptent)
            a['contested'] = bool((nr or nb) and (nr or mr) and (nb or mb))
            if nr and not nb and not mb:
                bonus = 1 + C.CAPTURE_BONUS_PER_UNIT * (nr - 1) + C.MINION_CAPTURE * mr
                a['control'] = min(1.0, a['control'] + rate * bonus)
            elif nb and not nr and not mr:
                bonus = 1 + C.CAPTURE_BONUS_PER_UNIT * (nb - 1) + C.MINION_CAPTURE * mb
                a['control'] = max(-1.0, a['control'] - rate * bonus)
            elif not nr and not nb:        # sans personne, l'arène revient à l'état de son propriétaire
                goal = 1.0 if a['owner'] == 'rouge' else -1.0 if a['owner'] == 'bleu' else 0.0
                step = rate * C.CAPTURE_DECAY
                a['control'] += max(-step, min(step, goal - a['control']))
            old = a['owner']
            if a['control'] >= 1 and a['owner'] != 'rouge':
                a['owner'] = 'rouge'
            elif a['control'] <= -1 and a['owner'] != 'bleu':
                a['owner'] = 'bleu'
            elif (a['owner'] == 'rouge' and a['control'] <= 0) or (a['owner'] == 'bleu' and a['control'] >= 0):
                a['owner'] = None
            if a['owner'] != old:
                changed = True
                self._arena_event(a, old)
                if a['owner']:                   # capture : comptée pour chaque Pokémon présent
                    for u in self.team_units[a['owner']]:
                        if u.alive and (flat(u.position) - a['pos']).length() < R:
                            self.add_stat(u, 'caps', 1)
                            self.reward(u, C.XP_CAPTURE, C.GOLD_CAPTURE)
                        else:
                            self.reward(u, 0, C.GOLD_CAPTURE_TEAM)
            self._paint_arena(a)
        for team in TEAM_KEYS:                   # points des arènes tenues (rendement décroissant)
            n = sum(1 for a in self.arenas if a['owner'] == team)
            self.score[team] += C.ARENA_POINTS[n] * dt
        if changed:
            self._refresh_bonus()

    def _paint_arena(self, a):
        """Couleur de l'anneau et du cristal selon l'avancement de la capture."""
        c = a['control']
        lead = C.TEAMS['rouge' if c > 0 else 'bleu']['color']
        col = lerp(NEUTRAL_RING, lead, abs(c))
        if a['contested'] and int(self.time * 6) % 2:
            col = color.rgb(1, 1, 1)
        a['ring'].color = col
        a['crystal'].color = C.TEAMS[a['owner']]['color'] if a['owner'] else lerp(NEUTRAL_RING, lead, abs(c) * .6)

    def _arena_event(self, a, old):
        if a['owner']:
            a['tower_t'] = C.TOWER['build']
            t = C.TEAMS[a['owner']]
            _, _, desc = C.ARENA_BONUS[a['type']]
            msg = f"L'équipe {t['name']} contrôle l'{a['name']} ({desc}) : {a['wx']['name']} sur le quartier"
            self.say(msg, t['light'])
            for h in self.humans:
                if a['owner'] == h.team or (h.alive and self.arena_at(h.position) is a):
                    self.announce(msg, 2.5, t['light'], to=h)
        elif old:
            self.say(f"L'{a['name']} est neutralisée", color.rgb(.9, .9, .9))

    def _update_spawns(self, dt):
        for camp in self.camps:
            if not camp['alive']:
                camp['respawn_t'] -= dt
                if camp['respawn_t'] <= 0:
                    camp['alive'] = True
                    for u in camp['units']:
                        u.reset()
                        u.brain.target = None
        # boss légendaire et boss final
        final = self.bosses['final']
        if not self.final_spawned and self.time >= C.FINAL_BOSS['spawn']:
            self.final_spawned = True
            leg = self.bosses['legendary']
            if leg['alive']:
                leg['alive'] = False
                self._despawn(leg['units'][0])
            self._spawn_boss(final, 4)
        elif not final['alive'] and not self.bosses['legendary']['alive'] and self.time >= self.next_legendary:
            self._spawn_boss(self.bosses['legendary'], 3)

    def _spawn_boss(self, camp, squad):
        u = camp['units'][0]
        u.reset(pos=Vec3(0, 0, 2))
        u.brain.target = None
        camp['alive'] = True
        self._assign_boss_squads(squad)
        name = u.name
        self.announce(f'{name} est apparu dans le Boss Pit !', 3.5, C.TYPES[u.type]['light'])
        self.say(f'{name} est apparu dans le Boss Pit', C.TYPES[u.type]['light'])

    def _check_end(self):
        r, b = self.score['rouge'], self.score['bleu']
        if max(r, b) >= C.SCORE_TO_WIN or self.time >= C.MATCH_TIME:
            self.state = 'end'
            if r > b:
                msg, col = 'VICTOIRE ! Votre équipe domine le stade !', color.rgb(1, .85, .3)
            elif b > r:
                msg, col = "DÉFAITE... L'équipe Bleue domine le stade.", color.rgb(.6, .75, 1)
            else:
                msg, col = 'MATCH NUL !', color.white
            self.announce(msg, None, col, big=True)
            self._show_end_text()
            self.emit('stats', [[uid] + [round(s[k], 1) for k in STAT_KEYS] for uid, s in self.stats.items()])

    def _show_end_text(self):
        r, b = self.score['rouge'], self.score['bleu']
        self.end_text.text = f'Rouge {int(r)}  -  {int(b)} Bleue        [R] rejouer   [Échap] menu'
        self.end_text.enabled = True

    def receive_stats(self, rows):
        """Invité : statistiques de fin de partie envoyées par l'hôte."""
        for row in rows:
            s = self.stats.get(int(row[0]))
            if s is not None:
                for k, v in zip(STAT_KEYS, row[1:]):
                    s[k] = float(v)

    def _update_results(self):
        """Fin de partie : la page des résultats s'affiche après la bannière de victoire."""
        if self.state != 'end' or self.results is not None:
            return
        self._end_t += time.dt
        if self._end_t >= RESULTS_DELAY:
            from game.interface.results import Results
            self.game.banner.enabled = False
            self.ui.enabled = False
            self.results = Results(self)

    def _hide_results(self):
        self._end_t = 0.0
        if self.results is not None:
            destroy_tree(self.results)
            self.results = None
        self.ui.enabled = True

    def _clear_attacks(self):
        self.pending_hits = []
        self.particles.clear()
        for p in self.projectiles:
            p.kill(False)
        for h in self.hazards:
            h.cleanup()
        self.projectiles, self.hazards = [], []

    def restart(self):
        self.emit('restart')
        self._clear_attacks()
        self.time = 0.0
        self.score = {'rouge': 0.0, 'bleu': 0.0}
        self._reset_stats()
        self._hide_results()
        for a in self.arenas:
            a['control'], a['owner'], a['contested'] = 0.0, None, False
        self._refresh_bonus()
        for team in TEAM_KEYS:
            for i, u in enumerate(self.team_units[team]):
                if u.transform_kind is not None:
                    u.end_transform()
                u.transform_cd = 0.0
                u.xp = 0.0
                u.buffs = {}
                u.items = []
                u.gold = C.START_GOLD
                u.set_level(1, show=False)              # retour à la forme de base
                for k in u.cd:
                    u.cd[k] = 0.0
                pos = v3(self._spawn_point(team, i))
                if u.is_player:
                    self._teleport_human(u, pos)
                else:
                    u.reset(pos=pos)
                    u.brain.target, u.brain.goal, u.brain.mode = None, None, None
        for camp in self.camps:
            camp['alive'] = True
            for u in camp['units']:
                u.reset()
                u.brain.target = None
        for camp in self.bosses.values():
            camp['alive'] = False
            self._despawn(camp['units'][0])
        for pad in self.pads:
            self._set_pad(pad, True)
        for a in self.arenas:
            a['tower_t'] = 0.0
            for u in a['towers'].values():
                self._despawn(u)
        self.waves.reset()
        self.next_legendary = C.LEGENDARY['first_spawn']
        self.final_spawned = False
        self.state = 'play'
        self.end_text.enabled = False
        self.announce('Nouvelle partie !', 2)

    # ================================================================ invité (affichage de l'état reçu)
    def apply_world(self, t, score_r, score_b, end, arenas):
        self.time = t
        self.score = {'rouge': score_r, 'bleu': score_b}
        changed = False
        for a, (control, owner, contested) in zip(self.arenas, arenas):
            a['control'], a['contested'] = control, contested
            if a['owner'] != owner:
                a['owner'] = owner
                changed = True
            self._paint_arena(a)
        if changed:
            self._refresh_bonus()
        if end and self.state == 'play':
            self.state = 'end'
            self._show_end_text()

    def teleport_local(self, pos):
        self.player.reset(pos=pos)
        self.player.invuln = C.RESPAWN_INVULN

    def restart_view(self):
        self._clear_attacks()
        self._reset_stats()
        self._hide_results()
        self.state = 'play'
        self.end_text.enabled = False
        for k in self.player.cd:
            self.player.cd[k] = 0.0

    def connection_lost(self):
        self.state = 'lost'
        self.game.banner.show("Connexion avec l'hôte perdue", None, text_color=color.rgb(1, .6, .5), big=True)
        self.end_text.text = '[Échap] retour au menu'
        self.end_text.enabled = True

    def guest_left(self):
        """Hôte : l'invité est parti, l'ordinateur reprend son Pokémon."""
        u = self.remote
        if u is None:
            return
        u.net_driven = False
        u.is_player = False
        u.role = 'libre'
        u.brain = self.bot_brain(u)
        self.remote = None
        self.humans = [self.player]
        self.announce("Le joueur 2 a quitté la partie : l'ordinateur prend le relais.", 3.5, color.rgb(1, .8, .5))

    def dispose(self):
        """Quitte la partie : supprime la scène et ferme la connexion."""
        from game.world import fx
        if self.net is not None:
            self.net.close()
        self._clear_attacks()
        if self.results is not None:
            destroy_tree(self.results)
        fx.PARTICLES = None
        self.portraits.dispose()
        if self.shop is not None:
            destroy_tree(self.shop)
        destroy_tree(self.ui)
        destroy_tree(self.root)
        destroy(self)

    # ================================================================ caméra
    def _place_camera(self, k):
        if self.cam_mode == 'map':             # vue de toute la carte
            yaw, pitch, dist = 0.0, 64.0, 215.0
            target = Vec3(0, 0, -6)
            self.cam_view = lerp(self.cam_view, Vec3(yaw, pitch, dist), min(1, k * .8))
            yaw, pitch, dist = self.cam_view
            yr, pr = math.radians(yaw), math.radians(pitch)
            off = Vec3(-math.sin(yr) * math.cos(pr), math.sin(pr), -math.cos(yr) * math.cos(pr))
            self.cam_map_target = lerp(self.cam_map_target, target, min(1, k * .8))
            camera.position = self.cam_map_target + off * dist
            camera.rotation = Vec3(pitch, yaw, 0)
            return
        if self.cam_mode == 'free':            # caméra détachée : on la déplace à la souris
            if mouse.middle:
                yr = math.radians(self.cam_yaw)
                fwd, right = Vec3(math.sin(yr), 0, math.cos(yr)), Vec3(math.cos(yr), 0, -math.sin(yr))
                speed = self.cam_dist * 2.2
                self.cam_target -= (right * mouse.velocity[0] + fwd * mouse.velocity[1]) * speed
                lim = C.FIELD_RADIUS
                r = math.hypot(self.cam_target.x, self.cam_target.z)
                if r > lim:
                    self.cam_target = Vec3(self.cam_target.x * lim / r, self.cam_target.y, self.cam_target.z * lim / r)
                self.cam_target.y = self.stadium.walk_y(self.cam_target.x, self.cam_target.z) + 1.5
        else:
            focus = self.player.position if self.player.alive else v3(C.TEAMS[self.player.team]['base'])
            self.cam_target = lerp(self.cam_target, Vec3(focus.x, focus.y + 1.5, focus.z), k)
        self.cam_view = Vec3(self.cam_yaw, self.cam_pitch, self.cam_dist)
        self.cam_map_target = Vec3(self.cam_target)
        yaw, pitch = math.radians(self.cam_yaw), math.radians(self.cam_pitch)
        offset = Vec3(-math.sin(yaw) * math.cos(pitch), math.sin(pitch), -math.cos(yaw) * math.cos(pitch))
        camera.position = self.cam_target + offset * self.cam_dist
        if self.shake_amount > 0:
            camera.position += Vec3(random.uniform(-1, 1), random.uniform(-1, 1), 0) * self.shake_amount
        camera.rotation = Vec3(self.cam_pitch, self.cam_yaw, 0)

    def _refresh_cam_hint(self):
        self.cam_hint.text = {'map': 'CARTE   -   Tab : revenir au jeu',
                              'free': f'Caméra libre   -   C : recentrer sur {self.player.name}',
                              'follow': ''}[self.cam_mode]

    def input(self, key):
        if self._warmup > 0:
            return
        if key == 'b' and self.state == 'play':
            self.toggle_shop()
            return
        if key == 'escape' and self.shop is not None:
            self.toggle_shop()
            return
        if key == 'escape':
            if self.state in ('end', 'lost') or self._quit_t > 0:
                self.game.back_to_menu()
            else:
                self._quit_t = 2.5
                self.game.banner.show('Appuyez encore sur Échap pour quitter la partie', 2.5)
            return
        if key == 'tab':
            self.cam_mode = 'follow' if self.cam_mode == 'map' else 'map'
            self._refresh_cam_hint()
            return
        if key == 'middle mouse down' and self.cam_mode == 'follow':
            self.cam_mode = 'free'
            self._refresh_cam_hint()
        elif key == 'c' and self.cam_mode != 'follow':
            self.cam_mode = 'follow'
            self._refresh_cam_hint()
        if key == 'scroll up':
            self.cam_dist = max(10, self.cam_dist - 1.5)
        elif key == 'scroll down':
            self.cam_dist = min(40, self.cam_dist + 1.5)
        elif key == 'r' and self.state == 'end':
            if self.authority:
                self.restart()
            else:
                self.net.request_restart()
        elif self.state == 'play' and self.player.alive and self.shop is None:   # boutique ouverte : on ne bouge pas
            self.player.brain.input(key)

    # ================================================================ interface
    def _build_hud(self):
        ui = self.ui = Entity(parent=camera.ui)
        # --- score
        W = .64
        Entity(parent=ui, model='quad', color=color.rgba(0, 0, 0, .6), scale=(W + .02, .06), position=(0, .455))
        self.bar_max = .19
        for sx in (-1, 1):
            Entity(parent=ui, model='quad', color=color.rgba(1, 1, 1, .12), origin=(.5 * sx, 0),
                   position=(-.065 * sx, .455, -.005), scale=(self.bar_max, .036))
        self.bar_r = Entity(parent=ui, model='quad', color=C.TEAMS['rouge']['color'], origin=(.5, 0),
                            position=(-.065, .455, -.01), scale=(0, .036))
        self.bar_b = Entity(parent=ui, model='quad', color=C.TEAMS['bleu']['color'], origin=(-.5, 0),
                            position=(.065, .455, -.01), scale=(0, .036))
        self.score_r = Text(parent=ui, text='0', position=(-.27, .455, -.02), origin=(.5, 0), scale=1.2,
                            color=C.TEAMS['rouge']['light'])
        self.score_b = Text(parent=ui, text='0', position=(.27, .455, -.02), origin=(-.5, 0), scale=1.2,
                            color=C.TEAMS['bleu']['light'])
        self.timer_text = Text(parent=ui, text=f'{C.MATCH_TIME // 60:02d}:00', position=(0, .455, -.02), origin=(0, 0), scale=1.1,
                               color=color.rgb(1, .95, .6))
        Text(parent=ui, text=f'Objectif : {C.SCORE_TO_WIN} points Dominion', position=(0, .41), origin=(0, 0),
             scale=.75, color=color.rgba(1, 1, 1, .8))
        # --- arènes
        self.arena_icons = []
        labels = {'nord': 'N', 'ouest': 'O', 'est': 'E', 'sud_ouest': 'SO', 'sud_est': 'SE'}
        for i, a in enumerate(self.arenas):
            x = (i - 2) * .075
            Entity(parent=ui, model='circle', color=color.rgba(0, 0, 0, .6), scale=.06, position=(x, .36, .01))
            fill = Entity(parent=ui, model='circle', color=NEUTRAL_RING, scale=.048, position=(x, .36))
            Entity(parent=ui, model='circle', color=C.TYPES[a['type']]['color'], scale=.022, position=(x, .36, -.01))
            Text(parent=ui, text=labels[a['key']], position=(x, .318), origin=(0, 0), scale=.7)
            prog = Entity(parent=ui, model='quad', color=color.white, origin=(-.5, 0), position=(x - .025, .302),
                          scale=(0, .006))
            self.arena_icons.append((fill, prog))
        # --- mini-carte
        # mini-carte réduite, calée dans le coin supérieur droit (elle ne masque plus le jeu)
        self.map_root = Entity(parent=ui, position=(.735, .345), scale=.66)
        self.map_s = .2 / C.FIELD_RADIUS
        Entity(parent=self.map_root, model='circle', color=color.rgba(.1, .12, .25, .85), scale=.43, z=.03)
        Entity(parent=self.map_root, model='circle', color=color.rgba(.3, .55, .28, .95), scale=.4, z=.02)
        Entity(parent=self.map_root, model='quad', texture=self._jungle_map_texture(), scale=.4, z=.018)
        for pts, w, col in [(p, w, color.rgba(.9, .88, .8, .9)) for p, w in LANES] + \
                           [(p, w, color.rgba(.3, .65, 1, .9)) for p, w in RIVERS]:
            for (ax, az), (bx, bz) in zip(pts, pts[1:]):
                mx, mz = (ax + bx) / 2 * self.map_s, (az + bz) / 2 * self.map_s
                L = math.hypot(bx - ax, bz - az) * self.map_s
                Entity(parent=self.map_root, model='quad', color=col, position=(mx, mz, .015),
                       scale=(L, max(.003, w * self.map_s)), rotation_z=-math.degrees(math.atan2(bz - az, bx - ax)))
        for team in TEAM_KEYS:
            bx, bz = C.TEAMS[team]['base']
            Entity(parent=self.map_root, model='circle', color=C.TEAMS[team]['color'],
                   position=(bx * self.map_s, bz * self.map_s, .01), scale=C.BASE_RADIUS * 2 * self.map_s)
        self.map_weather = [Entity(parent=self.map_root, model='circle', color=color.rgba(1, 1, 1, 0),
                                   position=(a['pos'].x * self.map_s, a['pos'].z * self.map_s, .016),
                                   scale=C.WEATHER_RADIUS * 2 * self.map_s) for a in self.arenas]
        self.map_arenas = []
        for a in self.arenas:
            self.map_arenas.append(Entity(parent=self.map_root, model='circle', color=NEUTRAL_RING,
                                          position=(a['pos'].x * self.map_s, a['pos'].z * self.map_s, .01),
                                          scale=C.ARENA_RADIUS * 2 * self.map_s))
        self.map_pit = Entity(parent=self.map_root, model='circle', color=color.rgb(.35, .3, .45), scale=.03, z=.005)
        self.map_camps = [Entity(parent=self.map_root, model='circle',
                                 color=color.rgb(.85, .95, .7) if c.get('wild') else color.rgb(1, .75, .2),
                                 scale=.007 if c.get('wild') else .012,
                                 position=(c['pos'].x * self.map_s, c['pos'].z * self.map_s, .005)) for c in self.camps]
        self.map_pads = [Entity(parent=self.map_root, model='circle', color=color.rgb(1, .9, .35), scale=.009,
                                position=(p['pos'].x * self.map_s, p['pos'].z * self.map_s, .004)) for p in self.pads]
        self.map_minions = {u: Entity(parent=self.map_root, model='quad', color=C.TEAMS[u.team]['light'], scale=.006,
                                      z=-.005, enabled=False) for u in self.units if u.kind == 'minion'}
        # Pokémon des équipes : leur portrait dans un médaillon aux couleurs de l'équipe
        self.portraits = Portraits([f for u in self.units if u.kind == 'pokemon'
                                    for f in C.evolution_line(u.species) + ([C.MEGA_FORMS[u.species]]
                                                                            if u.species in C.MEGA_FORMS else [])])
        self.map_units, self.map_faces = {}, {}
        for u in self.units:
            if u.kind == 'pokemon':
                col = color.rgb(1, .95, .2) if u.local else ALLY_BAR if u.is_player else C.TEAMS[u.team]['color']
                s = .054 if u.is_player else .046          # icônes un peu plus grosses : carte réduite
                icon = Entity(parent=self.map_root, z=-.02 if u.local else -.01 if u.is_player else 0)
                Entity(parent=icon, model='circle', color=col, scale=s)
                Entity(parent=icon, model='circle', color=color.rgb(.08, .09, .14), scale=s * .8, z=-.001)
                self.map_faces[u] = self.portraits.icon(icon, u.form, scale=s * .95, z=-.002)
                self.map_units[u] = icon
        # --- joueur
        from game.interface.hud import ArenaCard, CountdownCard, InfoCard, PillRow
        from game.interface.style import F_BOLD, F_SEMI, rounded
        p = Entity(parent=ui, position=(.36, -.31))
        Entity(parent=p, model=rounded(.506, .161, .014), color=color.rgba(1, 1, 1, .1), origin=(-.5, .5),
               position=(-.003, .003, .002), scale=(.506, .161))
        Entity(parent=p, model=rounded(.5, .155, .012), color=color.rgba(.05, .06, .13, .85), origin=(-.5, .5),
               scale=(.5, .155), z=.001)
        self.p_title = Text(parent=p, text='', position=(.015, -.01, -.01), origin=(-.5, .5), scale=1.05, **F_BOLD)
        Entity(parent=p, model='quad', color=color.rgba(0, 0, 0, .8), origin=(-.5, 0), position=(.015, -.06, -.01),
               scale=(.47, .026))
        self.p_hp = Entity(parent=p, model='quad', color=hp_color(1), origin=(-.5, 0), position=(.017, -.06, -.02),
                           scale=(.466, .02))
        self.p_hp_text = Text(parent=p, text='', position=(.25, -.06, -.03), origin=(0, 0), scale=.72, **F_BOLD)
        Entity(parent=p, model='quad', color=color.rgba(0, 0, 0, .8), origin=(-.5, 0), position=(.015, -.09, -.01),
               scale=(.47, .012))
        self.p_xp = Entity(parent=p, model='quad', color=color.rgb(.45, .8, 1), origin=(-.5, 0),
                           position=(.017, -.09, -.02), scale=(0, .008))
        self.p_stats = Text(parent=p, text='', position=(.015, -.104, -.01), origin=(-.5, .5), scale=.7,
                            color=color.rgb(.8, .85, .95), **F_SEMI)
        self.p_role = Text(parent=p, text='', position=(.015, -.13, -.01), origin=(-.5, .5), scale=.64,
                           color=color.rgba(.82, .86, 1, .7), **F_SEMI)
        self.p_gold = Text(parent=p, text='', position=(.485, -.012, -.01), origin=(.5, .5), scale=1.0,
                           color=color.rgb(1, .85, .3), **F_BOLD)
        # bonus actifs et objets tenus (pastilles), météo ou terrain où se trouve le Pokémon (carte)
        self.p_pills = PillRow(p, position=(0, .024, -.01))
        self.p_zone = InfoCard(p, position=(0, .075, -.01))
        self.p_zone.hide()
        self._zone_shown = None
        # --- l'autre joueur (partie à deux)
        self.ally_panel = None
        if self.remote is not None:
            a = self.ally_panel = Entity(parent=ui, position=(-.87, .3))
            Entity(parent=a, model='quad', color=color.rgba(.05, .05, .08, .75), origin=(-.5, .5), scale=(.3, .07))
            self.ally_title = Text(parent=a, text='', position=(.012, -.01, -.01), origin=(-.5, .5), scale=.85,
                                   color=ALLY_BAR)
            Entity(parent=a, model='quad', color=color.rgba(0, 0, 0, .8), origin=(-.5, 0), position=(.012, -.05, -.01),
                   scale=(.276, .018))
            self.ally_hp = Entity(parent=a, model='quad', color=hp_color(1), origin=(-.5, 0),
                                  position=(.014, -.05, -.02), scale=(.272, .012))
        self.ping_text = Text(parent=ui, text='', position=(-.87, .215), origin=(-.5, 0), scale=.75,
                              color=color.rgba(1, 1, 1, .7)) if self.net is not None else None
        # --- attaques
        self.slots = {}
        x0 = -.8
        self.dash_slot = MoveSlot('ESPACE', 'Esquive', parent=ui, position=(x0, -.4))
        self._build_slots()
        K = {k: key_label(v) for k, v in C.KEYS.items()}
        Text(parent=ui, text=f"Clic : se déplacer / attaquer   {K['auto']} auto-attaque   "
                             f"{K[1]} {K[2]} {K[3]} {K[4]} attaques, {K['ult']} ultime "
                             f"(maintenir pour viser, relâcher pour lancer)   {key_label(C.TRANSFORM_KEY)} transformation"
                             "   Espace esquive   B boutique   Tab carte",
             position=(x0 - .06, -.478), scale=.62, color=color.rgba(1, 1, 1, .7), **F_SEMI)
        self.cam_hint = Text(parent=ui, text='', position=(0, .215), origin=(0, 0), scale=.9,
                             color=color.rgb(.7, .9, 1), **F_BOLD)
        self.center_text = Text(parent=ui, text='', position=(0, .12), origin=(0, 0), scale=1.3, **F_BOLD)
        self.respawn_card = CountdownCard(ui, position=(0, .12, -.02))
        self.end_text = Text(parent=ui, text='', position=(0, -.08), origin=(0, 0), scale=1.4, enabled=False)
        self.feed = Feed(parent=ui, position=(.875, .15))
        self.arena_card = ArenaCard(ui, position=(0, .245, -.01))
        self.arena_card.hide()

    def _build_slots(self):
        """Cases des attaques du joueur (reconstruites à chaque évolution)."""
        for s in self.slots.values():
            destroy_tree(s)
        x0, step = -.8, .132
        self.slots = {}
        for i, mv in enumerate(self.player.moves):
            name = mv['name']
            self.slots[mv['slot']] = MoveSlot(key_label(mv['key']), name, parent=self.ui,
                                              position=(x0 + step * (i + 1), -.4),
                                              locked=mv['unlock'] if mv['locked'] else None)
        pl = self.player
        kind, form, cfg = pl.transform_info()
        self.slots['transform'] = MoveSlot(key_label(C.TRANSFORM_KEY), cfg['name'], parent=self.ui,
                                           position=(x0 + step * (len(pl.moves) + 1), -.4),
                                           locked=cfg['level'] if pl.level < cfg['level'] else None)

    def on_evolve(self, u, old_name):
        """Un Pokémon d'équipe vient d'évoluer (old_name) ou de reprendre sa forme de base (None)."""
        face = self.map_faces.get(u)
        if face is not None:
            self.portraits.show(face, u.form)
        if u is self.player:
            self._build_slots()
        if old_name is None or not self.authority:
            return
        t = C.TEAMS[u.team]
        self.say(f"{old_name} ({t['name']}) évolue en {u.name} !", t['light'])
        if u.is_player:
            self.announce(f'{old_name} évolue en {u.name} !   Stats et attaques renforcées', 4,
                          color.rgb(1, .95, .55), to=u)

    def _jungle_map_texture(self):
        """Image de la mini-carte : sol et massifs aux couleurs de chaque biome, hautes herbes."""
        import numpy as np
        from PIL import Image
        from game.world import biomes
        st = self.stadium
        n = 256
        xs = (np.arange(n) + .5) / n * 2 * C.FIELD_RADIUS - C.FIELD_RADIUS
        X, Z = np.meshgrid(xs, xs[::-1])                  # ligne 0 de l'image = nord
        sdf = st._jsample_np(st.wall_sdf, X, Z)
        i = np.clip(np.round((X - st.j_min) / .5).astype(int), 0, st.j_n - 1)
        j = np.clip(np.round((Z - st.j_min) / .5).astype(int), 0, st.j_n - 1)
        W = biomes.weights_np(X, Z)[..., None]
        ground = (np.array(MAP_GROUND) * W).sum(-2)
        massif = (np.array(MAP_MASSIF) * W).sum(-2)
        img = np.zeros((n, n, 4), np.uint8)
        img[..., :3] = np.where((sdf > 0)[..., None], massif, ground).astype(np.uint8)
        img[..., 3] = np.where(sdf > 0, 245, 235)
        img[st.bush_grid[i, j] > 0] = (70, 170, 120, 235)
        img[np.hypot(X, Z) > C.FIELD_RADIUS - 1] = 0
        return Texture(Image.fromarray(img, 'RGBA'))

    @staticmethod
    def _set_text(t, value):
        if t.text != value:          # recréer un texte Ursina est coûteux : seulement s'il change
            t.text = value

    def _update_hud(self, dt):
        r, b = self.score['rouge'], self.score['bleu']
        self.bar_r.scale_x = self.bar_max * min(1, r / C.SCORE_TO_WIN)
        self.bar_b.scale_x = self.bar_max * min(1, b / C.SCORE_TO_WIN)
        self._set_text(self.score_r, str(int(r)))
        self._set_text(self.score_b, str(int(b)))
        left = max(0, C.MATCH_TIME - self.time)
        self._set_text(self.timer_text, f'{int(left // 60):02d}:{int(left % 60):02d}')
        for a, wx in zip(self.arenas, self.map_weather):
            c = C.TEAMS[a['owner']]['color'] if a['owner'] else None
            wx.color = color.rgba(c[0], c[1], c[2], .16) if c else color.rgba(1, 1, 1, 0)
        for a, (fill, prog), dot in zip(self.arenas, self.arena_icons, self.map_arenas):
            c = a['control']
            col = C.TEAMS[a['owner']]['color'] if a['owner'] else lerp(NEUTRAL_RING, C.TEAMS['rouge' if c > 0 else 'bleu']['color'], abs(c) * .5)
            fill.color = col
            dot.color = col
            prog.scale_x = .05 * abs(c)
            prog.color = C.TEAMS['rouge' if c > 0 else 'bleu']['light']
        boss = self.active_boss()
        self.map_pit.color = color.rgb(.85, .45, 1) if boss else color.rgb(.35, .3, .45)
        self.map_pit.scale = .04 if boss else .03
        for camp, dot in zip(self.camps, self.map_camps):
            dot.enabled = camp['alive']
        for pad, dot in zip(self.pads, self.map_pads):
            dot.enabled = pad['alive']
        me = self.player.team
        for u, dot in self.map_minions.items():
            on = u.alive and (u.team == me or self.in_vision(me, u))
            if dot.enabled != on:
                dot.enabled = on
            if on:
                dot.position = (u.position.x * self.map_s, u.position.z * self.map_s, dot.z)
        for u, dot in self.map_units.items():
            dot.enabled = u.alive and self.in_vision(me, u)      # adversaires : seulement s'ils sont vus
            if u.alive:
                dot.position = (u.position.x * self.map_s, u.position.z * self.map_s, dot.z)
        # joueur
        pl = self.player
        self._set_text(self.p_title, f'{pl.name}   Nv.{pl.level}')
        ratio = max(0, pl.hp / pl.max_hp)
        self.p_hp.scale_x = .466 * ratio
        self.p_hp.color = hp_color(ratio)
        self._set_text(self.p_hp_text, f'{int(pl.hp)} / {pl.max_hp}')
        need = C.xp_to_next(pl.level)
        self.p_xp.scale_x = .466 * (1 if pl.level >= C.MAX_LEVEL else pl.xp / need)
        shop = self.can_shop(pl)
        self._set_text(self.p_gold, f'{int(pl.gold)} ₽' + ('   [B] boutique' if shop else ''))
        if self.shop is not None:
            self.shop.refresh()
        pills = [(f"{C.BUFFS[k]['name']}  {int(t) + 1} s", C.BUFFS[k]['color']) for k, t in pl.buffs.items()
                 if t > 0 and k in C.BUFFS]
        if pl.transform_kind is not None:
            kind, form, cfg = pl.transform_info()
            pills.insert(0, (f"{cfg['name']}  {int(pl.transform_t) + 1} s", color.rgb(1, .55, .85)))
        pills += [(C.ITEMS[k]['name'], color.rgb(1, .82, .35)) for k in pl.items]
        self.p_pills.set(pills)
        self.p_zone.y = .024 + self.p_pills.height + (.03 if pills else .005)
        zone = pl.zone() if pl.alive else None
        eff = C.zone_effect(zone, pl.type) if zone else {}
        wz = self.weather_zone(pl) if pl.alive else None
        key = (zone, pl.type, wz['key'] if wz else None, wz['owner'] if wz else None)
        if key != self._zone_shown:
            self._zone_shown = key
            if wz is not None:
                w = wz['wx']
                mine = wz['owner'] == pl.team
                bad = not mine and w.get('enemy_dps')
                who = 'BONUS DE VOTRE ÉQUIPE' if mine else 'MALUS ADVERSE' if bad else "MÉTÉO ADVERSE (sans effet pour vous)"
                col = color.rgb(.45, 1, .55) if mine else color.rgb(1, .45, .4) if bad else color.rgb(.75, .78, .88)
                self.p_zone.show(key, f"{w['name'].upper()}  ·  {who}", w['desc'][0].upper() + w['desc'][1:], col)
            elif eff:
                gain = eff.get('dmg', 0) + eff.get('speed', 0) - eff.get('taken', 0)
                col = color.rgb(.45, 1, .55) if gain > 0 else color.rgb(1, .45, .4)
                self.p_zone.show(key, f"{C.ZONE_NAMES[zone].upper()}  ·  {'BONUS' if gain > 0 else 'MALUS'}",
                                 C.zone_text(eff)[0].upper() + C.zone_text(eff)[1:], col)
            else:
                self.p_zone.hide()
        if self.ally_panel is not None:
            al = self.remote or next((h for h in self.team_units['rouge'] if h.human is not None and not h.local), None)
            if al is not None:
                state = f'Nv.{al.level}' if al.alive else 'K.O.'
                self._set_text(self.ally_title, f'J{al.human + 1}  {al.name}   {state}' + ('' if self.remote else '  (IA)'))
                ar = max(0, al.hp / al.max_hp)
                self.ally_hp.scale_x = .272 * ar
                self.ally_hp.color = hp_color(ar)
        if self.ping_text is not None and self.net.rtt is not None:
            self._set_text(self.ping_text, f'Ping : {self.net.rtt} ms')
        br = pl.brain
        for mv in pl.moves:
            slot = self.slots.get(mv['slot'])
            if slot is not None:
                cd = pl.cd.get(mv['slot'], 0)
                slot.set_ratio(cd / max(.01, mv['cooldown'] * pl.cooldown_mult()), cd)
        self.dash_slot.set_ratio(br.dash_cd / C.PLAYER_DASH['cooldown'], br.dash_cd)
        ts = self.slots.get('transform')
        if ts is not None:
            kind, form, cfg = pl.transform_info()
            ts.set_ratio(0 if pl.transform_kind else pl.transform_cd / cfg['cooldown'],
                         0 if pl.transform_kind else pl.transform_cd)
        st = pl.stats
        self._set_text(self.p_stats, '    '.join(f'{C.STAT_SHORT[k]} {st[k]:.0f}' for k in C.STATS[1:]))
        self._set_text(self.p_role, f"{C.ROLES[kit.line_role(pl.species, pl.build)]['name']}  ·  "
                                    f"build {dict((k, n) for k, n, _ in kit.builds_for(pl.species))[pl.build]}")
        # messages
        if self.state == 'play' and not pl.alive:
            self.respawn_card.show(int(max(0, pl.respawn_t)) + 1, 'B : boutique pendant l\'attente')
        elif self.respawn_card.enabled:
            self.respawn_card.enabled = False
        a = self.arena_at(pl.position) if pl.alive else None
        if a is not None:
            tw = a['towers'][a['owner']] if self.tower_up(a) else None
            self.arena_card.show_arena(a, C.TEAMS, C.TYPES, tw)
        elif pl.alive and pl.bush:
            enemy = 'bleu' if pl.team == 'rouge' else 'rouge'
            if pl in self.hidden[enemy]:
                self.arena_card.show_message('CACHÉ DANS LES HAUTES HERBES', 'Invisible pour l\'adversaire',
                                             color.rgb(.45, 1, .6))
            else:
                self.arena_card.show_message('HAUTES HERBES : REPÉRÉ !', 'Vous venez d\'attaquer, ou un adversaire '
                                             'est tout près', color.rgb(1, .7, .3))
        elif self.arena_card.enabled:
            self.arena_card.hide()
