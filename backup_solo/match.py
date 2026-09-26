"""Une partie de Pokémon Dominion : règles, score, IA d'équipe, caméra et interface.

Deux équipes de 5 (le joueur est Pikachu, équipe rouge) s'affrontent pour le
contrôle de 5 arènes ouvertes. Une arène se capture en restant dans son cercle
sans adversaire (plus on est nombreux, plus c'est rapide) ; si les deux équipes
sont présentes, elle est contestée. Chaque arène contrôlée rapporte des points
Dominion chaque seconde et un bonus à toute l'équipe. Les K.O., les camps de la
jungle et les boss du Boss Pit rapportent aussi des points.
La première équipe à SCORE_TO_WIN points gagne (ou la meilleure à la fin du temps).
"""
import math
import random

from ursina import Entity, Text, Vec3, Vec4, camera, color, lerp, mouse, time

import config as C
from combat import flat
from emblems import add_emblem
from fx import ArenaWeather
from geometry import MeshBuilder
from stadium import LANES, RIVERS, Stadium
from ui import Feed, MoveSlot, floating_text, hp_color
from units import BotBrain, NeutralBrain, PlayerBrain, Unit

TEAM_KEYS = ('rouge', 'bleu')
NEUTRAL_RING = color.rgb(.85, .85, .85)


def v3(p):
    return Vec3(p[0], 0, p[1])


class Match(Entity):
    def __init__(self, game):
        super().__init__()
        self.game = game
        self.root = Entity(parent=self)
        self.stadium = Stadium(self.root)
        import fx
        fx.PARTICLES = self.particles = fx.Particles(self.root)
        self.projectiles, self.hazards = [], []
        self.pending_hits = []          # coups au contact en cours d'élan
        self.time = 0.0
        self.score = {'rouge': 0.0, 'bleu': 0.0}
        self.state = 'play'
        self.shake_amount = 0.0
        self._bonus = {'rouge': {}, 'bleu': {}, None: {}}

        self._build_arenas()
        self.units = []
        self.team_units = {'rouge': [], 'bleu': []}
        for team in TEAM_KEYS:
            for i, entry in enumerate(C.ROSTERS[team]):
                u = Unit(self, entry['species'], team, self._spawn_point(team, i), role=entry['role'],
                         is_player=entry.get('player', False))
                u.brain = PlayerBrain(u, self) if u.is_player else BotBrain(u, self)
                self.units.append(u)
                self.team_units[team].append(u)
                if u.is_player:
                    self.player = u
        self._build_camps()
        self._build_bosses()

        self._warmup = 4
        for u in self.units:          # pas d'ombre figée des Pokémon dans la carte d'ombres
            u.creature.enabled = False
        self.cam_yaw, self.cam_pitch, self.cam_dist = 0.0, 56.0, 24.0
        self.cam_mode = 'follow'          # 'follow' (suit Pikachu), 'free' (libre) ou 'map' (toute la carte)
        self.cam_view = Vec3(self.cam_yaw, self.cam_pitch, self.cam_dist)
        self.cam_map_target = Vec3(0, 0, 0)
        self.cam_target = Vec3(self.player.position)
        self._build_hud()
        self._place_camera(1)
        self.game.banner.show('Dominez les arènes ! Capturez-les en restant dans leur cercle.', 4)

    # ================================================================ construction
    def _spawn_point(self, team, i):
        bx, bz = C.TEAMS[team]['base']
        a = math.radians(i * 72)
        return bx + math.sin(a) * 3, bz + math.cos(a) * 3

    def _build_arenas(self):
        self.arenas = []
        R = C.ARENA_RADIUS
        for cfg in C.ARENAS:
            p = v3(cfg['pos'])
            t = C.TYPES[cfg['type']]
            ring = MeshBuilder().add('ring_thin', (0, 0, 0), (1, 1, 1), col=color.white).entity(
                parent=self.root, emissive=1.0, position=p + Vec3(0, .15, 0), scale=(R * 2, .25, R * 2),
                color=NEUTRAL_RING)
            crystal = MeshBuilder()
            crystal.add('cone4', (0, .6, 0), (1.2, 1.2, 1.2), col=color.white)
            crystal.add('cone4', (0, -.6, 0), (1.2, 1.2, 1.2), rot=(180, 0, 0), col=color.white)
            crystal = crystal.entity(parent=self.root, emissive=.7, position=p + Vec3(0, 6, 0), color=NEUTRAL_RING)
            emb = MeshBuilder()
            add_emblem(emb, cfg['type'], (0, 0, 0), 1.6)
            emblem = emb.entity(parent=self.root, emissive=.6, position=p + Vec3(0, 9.5, 0))
            label = Text(parent=self.root, text=cfg['name'].upper(), position=p + Vec3(0, 13, 0), billboard=True,
                         scale=26, origin=(0, 0), color=t['light'])
            weather = ArenaWeather(self.root, cfg['pos'], R, cfg['weather'], t['color'])
            self.arenas.append({'key': cfg['key'], 'name': cfg['name'], 'type': cfg['type'], 'pos': p,
                                'nav': 'arena:' + cfg['key'], 'control': 0.0, 'owner': None, 'contested': False,
                                'count': {'rouge': 0, 'bleu': 0}, 'ring': ring, 'crystal': crystal,
                                'emblem': emblem, 'label': label, 'weather': weather})

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
                self.units.append(u)
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
                u.hp = u.max_hp
                u._refresh_bar()
            u.brain = NeutralBrain(u, self)
            camp['units'].append(u)
            self.units.append(u)
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

    def _build_bosses(self):
        self.bosses = {}
        for key, cfg in (('legendary', C.LEGENDARY), ('final', C.FINAL_BOSS)):
            camp = {'cfg': cfg, 'key': 'pit', 'pos': Vec3(0, 0, 0), 'units': [], 'alive': False,
                    'respawn_t': 0.0, 'boss': True, 'kind': key}
            u = Unit(self, cfg['species'], None, (0, 2), camp=camp)
            u.brain = NeutralBrain(u, self)
            camp['units'].append(u)
            self.units.append(u)
            self._despawn(u)
            self.bosses[key] = camp
        self.next_legendary = C.LEGENDARY['first_spawn']
        self.final_spawned = False
        self.boss_squad = {'rouge': [], 'bleu': []}

    def _despawn(self, u):
        u.alive = False
        u.creature.enabled = False

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

    def deal_damage(self, src, tgt, base, status=None, stun=0.0, raw=False):
        if not tgt.alive:
            return
        eff = 1.0
        if raw:
            dmg = base
        else:
            eff = C.TYPE_CHART.get((src.type, tgt.type), 1.0)
            dmg = base * src.damage_mult() * eff * tgt.defense_mult()
            a = self.arena_at(src.position)
            if a is not None and a['type'] == src.type:
                dmg *= C.WEATHER_BONUS
            dmg *= random.uniform(.92, 1.08)
        dmg = max(1, round(dmg))
        if tgt.invuln > 0:
            return
        killed = tgt.hurt(dmg, src if src is not tgt else tgt.last_hit_by, status, stun)
        if (flat(tgt.position) - flat(self.cam_target)).length() < 26:
            col = color.rgb(1, .4, .35) if tgt.is_player else (
                color.rgb(1, .95, .3) if eff > 1 else color.rgb(.8, .8, .8) if eff < 1 else color.white)
            floating_text(f'-{dmg}', tgt.creature.world_position + Vec3(0, tgt.data['scale'] * 1.6 + 1, 0), col,
                          1.0 if (src.is_player or tgt.is_player) else .75)
        if tgt.is_player:
            self.shake(.25)
        if killed:
            self.on_ko(tgt, tgt.last_hit_by)

    def on_ko(self, victim, killer):
        if killer is victim:
            killer = None
        kteam = killer.team if killer is not None else None
        if victim.team:                                           # joueur ou IA d'équipe
            victim.respawn_t = C.RESPAWN_TIME + .25 * self.time / 60
            if kteam and kteam != victim.team:
                self.score[kteam] += C.POINTS_KO
                self._share_xp(killer, C.XP_KO)
                self.feed.push(f"{killer.name} ({C.TEAMS[kteam]['name']}) a mis K.O. {victim.name}",
                               C.TEAMS[kteam]['light'])
            else:
                self.feed.push(f"{victim.name} ({C.TEAMS[victim.team]['name']}) est K.O.", color.rgb(.8, .8, .8))
            if victim.is_player:
                self.game.banner.show('Pikachu est K.O. !', 2, text_color=color.rgb(1, .5, .45))
            return
        camp = victim.camp
        victim.respawn_t = 1.5                                    # disparition après l'animation
        cfg = camp['cfg']
        if kteam:
            n = len(camp['units'])
            self.score[kteam] += cfg['points'] / n
            self._share_xp(killer, cfg['xp'] / n)
        if all(not u.alive for u in camp['units']):
            camp['alive'] = False
            if camp['boss']:
                self._boss_defeated(camp, killer)
            else:
                camp['respawn_t'] = cfg['respawn']
                if cfg.get('buff') and killer is not None and kteam:
                    b = C.BUFFS[cfg['buff']]
                    killer.buffs[cfg['buff']] = b['duration']
                    self.feed.push(f"{killer.name} obtient {b['name']} ({b['desc']})", b['color'])
                    if killer.is_player:
                        self.game.banner.show(f"{b['name']} : {b['desc']} !", 2.5, text_color=b['color'])

    def _boss_defeated(self, camp, killer):
        cfg = camp['cfg']
        name = C.SPECIES[cfg['species']]['name']
        kteam = killer.team if killer is not None else None
        if camp['kind'] == 'legendary':
            self.next_legendary = self.time + cfg['respawn']
        if not kteam:
            return
        self.score[kteam] += cfg['points']
        b = C.BUFFS[cfg['buff']]
        for u in self.team_units[kteam]:
            u.gain_xp(cfg['xp'])
            if u.alive:
                u.buffs[cfg['buff']] = b['duration']
        tname = C.TEAMS[kteam]['name']
        self.game.banner.show(f"L'équipe {tname} a vaincu {name} ! +{cfg['points']} points et {b['name']}", 4,
                              text_color=C.TEAMS[kteam]['light'])
        self.boss_squad = {'rouge': [], 'bleu': []}

    def _share_xp(self, killer, amount):
        if killer is None or not killer.team:
            return
        killer.gain_xp(amount)
        for u in self.team_units[killer.team]:
            if u is not killer and u.alive and (flat(u.position - killer.position)).length() < 16:
                u.gain_xp(amount * .5)

    def on_level_up(self, u):
        if u.is_player:
            self.feed.push(f'Pikachu passe au niveau {u.level} !', color.rgb(1, .95, .5))

    def announce_cast(self, u, name):
        if (flat(u.position) - flat(self.cam_target)).length() < 24:
            floating_text(name + ' !', u.creature.world_position + Vec3(0, u.data['scale'] * 1.6 + 1.8, 0),
                          color.rgb(1, .95, .45) if u.team == 'rouge' else color.rgb(1, .7, .6), .8)

    def shake(self, amount):
        self.shake_amount = max(self.shake_amount, amount)

    def shake_at(self, pos, amount):
        if (flat(pos) - flat(self.cam_target)).length() < 18:
            self.shake(amount)

    def find_target(self, u, rng):
        """Cible de la visée automatique : l'adversaire le plus proche (les Pokémon d'équipe d'abord)."""
        best, score = None, 1e9
        for e in self.units:
            if e.alive and self.hostile(u, e):
                d = (flat(e.position - u.position)).length()
                if d < rng:
                    s = d + (8 if e.team is None else 0)
                    if s < score:
                        best, score = e, s
        return best

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
            from geometry import freeze_shadows
            freeze_shadows(self.game.sun)
            for u in self.units:
                if u.alive:
                    u.creature.enabled = True
            self.root.enabled = True
            self._ignore_passive_entities()

    def _ignore_passive_entities(self):
        """Ursina parcourt chaque image toutes ses entités : celles qui n'ont ni update()
        ni input() (pièces des Pokémon, barres de vie, décor de l'interface...) sont
        marquées `ignore` pour être sautées tout de suite."""
        from ursina import scene
        for e in scene.entities:
            if not hasattr(type(e), 'update') and not hasattr(type(e), 'input') and not getattr(e, 'scripts', None):
                e.ignore = True

    def update(self):
        if self._warmup > 0:
            self._warmup_step()
            return
        dt = min(time.dt, .05)
        if self.state == 'end':
            dt *= .25
        self.time += dt
        self.shake_amount = max(0, self.shake_amount - dt * 2)
        self.stadium.update(dt, self.cam_target)
        for a in self.arenas:
            a['weather'].update(dt, self.cam_target)
            a['emblem'].rotation_y += dt * 40
            a['emblem'].y = 9.5 + math.sin(self.time * 1.5 + a['pos'].x) * .4
            a['crystal'].rotation_y -= dt * 60

        for u in self.units:
            if u.alive:
                u.update(dt)
            elif u.creature.enabled:
                u.update(dt)
                u.respawn_t -= dt
                if u.team is None:
                    if u.respawn_t <= 0:
                        u.creature.enabled = False
                elif u.respawn_t <= C.RESPAWN_TIME - 1.8:
                    u.creature.visible = False
                if u.team and u.respawn_t <= 0:
                    self._respawn(u)
        self._separate_units()
        self._update_attacks(dt)
        if self.state == 'play':
            self._update_base_zones(dt)
            self._update_capture(dt)
            self._update_spawns(dt)
            self._check_end()
        self._update_hud(dt)
        self._place_camera(min(1, dt * 8))

    def _respawn(self, u):
        i = self.team_units[u.team].index(u)
        u.reset(pos=v3(self._spawn_point(u.team, i)))
        u.invuln = 2.0
        if not u.is_player:
            u.brain.target = None
            u.brain.mode = None

    def _separate_units(self):
        """Empêche les Pokémon de se superposer (positions lues une seule fois)."""
        items = [[u, u.creature.get_x(), u.creature.get_z(), False] for u in self.units if u.alive]
        for i, a in enumerate(items):
            ua = a[0]
            for b in items[i + 1:]:
                m = ua.radius + b[0].radius
                dx, dz = b[1] - a[1], b[2] - a[2]
                if -m < dx < m and -m < dz < m:
                    d = math.hypot(dx, dz)
                    if 0 < d < m:
                        push = (m - d) / 2 / d
                        a[1] -= dx * push
                        a[2] -= dz * push
                        b[1] += dx * push
                        b[2] += dz * push
                        a[3] = b[3] = True
        gy = self.stadium.walk_y
        for u, x, z, moved in items:
            if moved:
                u.creature.set_pos(x, gy(x, z), z)

    def _update_melee(self, dt):
        import fx
        keep = []
        for hit in self.pending_hits:
            hit[0] -= dt
            if hit[0] > 0:
                keep.append(hit)
                continue
            _, src, tgt, dmg = hit
            if src.alive and tgt.alive and src.status['stun'] <= 0:
                reach = src.data['attack']['range'] + tgt.radius + .3
                if (flat(tgt.position - src.position)).length() < reach:
                    self.deal_damage(src, tgt, dmg)
                    fx.burst(None, tgt.position + Vec3(0, 1, 0), fx.style(src.type)['hot'], n=6, speed=2.5, size=.25)
        self.pending_hits = keep

    def _update_attacks(self, dt):
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
                    else:
                        u.hurt(C.BASE_DAMAGE * dt, None)
                        if not u.alive:
                            u.respawn_t = C.RESPAWN_TIME

    def _update_capture(self, dt):
        R = C.ARENA_RADIUS
        changed = False
        for a in self.arenas:
            cnt = {'rouge': 0, 'bleu': 0}
            for u in self.units:
                if u.alive and u.team and (flat(u.position) - a['pos']).length() < R:
                    cnt[u.team] += 1
            a['count'] = cnt
            nr, nb = cnt['rouge'], cnt['bleu']
            rate = dt / C.CAPTURE_TIME
            a['contested'] = nr > 0 and nb > 0
            if nr and not nb:
                a['control'] = min(1.0, a['control'] + rate * (1 + C.CAPTURE_BONUS_PER_UNIT * (nr - 1)))
            elif nb and not nr:
                a['control'] = max(-1.0, a['control'] - rate * (1 + C.CAPTURE_BONUS_PER_UNIT * (nb - 1)))
            elif not nr and not nb:        # sans personne, l'arène revient à l'état de son propriétaire
                goal = 1.0 if a['owner'] == 'rouge' else -1.0 if a['owner'] == 'bleu' else 0.0
                step = rate * .3
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
            if a['owner']:
                self.score[a['owner']] += C.POINTS_PER_ARENA * dt
            # couleur de l'anneau et du cristal selon l'avancement de la capture
            c = a['control']
            lead = C.TEAMS['rouge' if c > 0 else 'bleu']['color']
            col = lerp(NEUTRAL_RING, lead, abs(c))
            if a['contested'] and int(self.time * 6) % 2:
                col = color.rgb(1, 1, 1)
            a['ring'].color = col
            a['crystal'].color = C.TEAMS[a['owner']]['color'] if a['owner'] else lerp(NEUTRAL_RING, lead, abs(c) * .6)
        if changed:
            self._refresh_bonus()

    def _arena_event(self, a, old):
        if a['owner']:
            t = C.TEAMS[a['owner']]
            _, _, desc = C.ARENA_BONUS[a['type']]
            msg = f"L'équipe {t['name']} contrôle l'{a['name']} ({desc})"
            self.feed.push(msg, t['light'])
            if a['owner'] == self.player.team or (self.player.alive and self.arena_at(self.player.position) is a):
                self.game.banner.show(msg, 2.5, text_color=t['light'])
        elif old:
            self.feed.push(f"L'{a['name']} est neutralisée", color.rgb(.9, .9, .9))

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
        self.game.banner.show(f'{name} est apparu dans le Boss Pit !', 3.5, text_color=C.TYPES[u.type]['light'])
        self.feed.push(f'{name} est apparu dans le Boss Pit', C.TYPES[u.type]['light'])

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
            self.game.banner.show(msg, None, text_color=col, big=True)
            self.end_text.text = f'Rouge {int(r)}  -  {int(b)} Bleue        [R] rejouer'
            self.end_text.enabled = True

    def restart(self):
        self.pending_hits = []
        self.particles.clear()
        for p in self.projectiles:
            p.kill(False)
        for h in self.hazards:
            h.cleanup()
        self.projectiles, self.hazards = [], []
        self.time = 0.0
        self.score = {'rouge': 0.0, 'bleu': 0.0}
        for a in self.arenas:
            a['control'], a['owner'], a['contested'] = 0.0, None, False
        self._refresh_bonus()
        for team in TEAM_KEYS:
            for i, u in enumerate(self.team_units[team]):
                u.level, u.xp = 1, 0.0
                u.reset(pos=v3(self._spawn_point(team, i)))
                if not u.is_player:
                    u.brain.target, u.brain.goal, u.brain.mode = None, None, None
        for camp in self.camps:
            camp['alive'] = True
            for u in camp['units']:
                u.reset()
                u.brain.target = None
        for camp in self.bosses.values():
            camp['alive'] = False
            self._despawn(camp['units'][0])
        self.next_legendary = C.LEGENDARY['first_spawn']
        self.final_spawned = False
        self.state = 'play'
        self.end_text.enabled = False
        self.game.banner.show('Nouvelle partie !', 2)

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
                              'free': 'Caméra libre   -   C : recentrer sur Pikachu',
                              'follow': ''}[self.cam_mode]

    def input(self, key):
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
            self.restart()
        elif self.state == 'play' and self.player.alive:
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
        self.timer_text = Text(parent=ui, text='30:00', position=(0, .455, -.02), origin=(0, 0), scale=1.1,
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
        self.map_root = Entity(parent=ui, position=(.72, .2))
        self.map_s = .2 / C.FIELD_RADIUS
        Entity(parent=self.map_root, model='circle', color=color.rgba(.1, .12, .25, .85), scale=.43, z=.03)
        Entity(parent=self.map_root, model='circle', color=color.rgba(.3, .55, .28, .95), scale=.4, z=.02)
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
        self.map_units = {}
        for u in self.units:
            if u.team:
                col = color.rgb(1, .95, .2) if u.is_player else C.TEAMS[u.team]['light']
                self.map_units[u] = Entity(parent=self.map_root, model='circle', color=col,
                                           scale=.02 if u.is_player else .014, z=-.01 if u.is_player else 0)
        # --- joueur
        p = Entity(parent=ui, position=(.36, -.33))
        Entity(parent=p, model='quad', color=color.rgba(.05, .05, .08, .8), origin=(-.5, .5), scale=(.5, .13))
        self.p_title = Text(parent=p, text='', position=(.015, -.012, -.01), origin=(-.5, .5), scale=1.1)
        Entity(parent=p, model='quad', color=color.rgba(0, 0, 0, .8), origin=(-.5, 0), position=(.015, -.06, -.01),
               scale=(.47, .026))
        self.p_hp = Entity(parent=p, model='quad', color=hp_color(1), origin=(-.5, 0), position=(.017, -.06, -.02),
                           scale=(.466, .02))
        self.p_hp_text = Text(parent=p, text='', position=(.25, -.06, -.03), origin=(0, 0), scale=.75)
        Entity(parent=p, model='quad', color=color.rgba(0, 0, 0, .8), origin=(-.5, 0), position=(.015, -.09, -.01),
               scale=(.47, .012))
        self.p_xp = Entity(parent=p, model='quad', color=color.rgb(.45, .8, 1), origin=(-.5, 0),
                           position=(.017, -.09, -.02), scale=(0, .008))
        self.p_buffs = Text(parent=p, text='', position=(.015, -.105, -.01), origin=(-.5, .5), scale=.72)
        # --- attaques
        self.slots = {}
        x0, step = -.8, .132
        self.dash_slot = MoveSlot('ESPACE', 'Esquive', parent=ui, position=(x0, -.4))
        for i, mv in enumerate(C.PLAYER_MOVES):
            self.slots[mv['key']] = MoveSlot(mv['key'].upper(), mv['name'], parent=ui, position=(x0 + step * (i + 1), -.4))
        Text(parent=ui, text='ZQSD : bouger   Maintenir J : attaque   Clic droit : tourner   Molette : zoom   '
                              'Clic molette + glisser : déplacer la vue   Tab : carte',
             position=(x0 - .06, -.465), scale=.74, color=color.rgba(1, 1, 1, .8))
        self.cam_hint = Text(parent=ui, text='', position=(0, .24), origin=(0, 0), scale=1.0,
                             color=color.rgb(.7, .9, 1))
        self.center_text = Text(parent=ui, text='', position=(0, .12), origin=(0, 0), scale=1.4)
        self.end_text = Text(parent=ui, text='', position=(0, -.08), origin=(0, 0), scale=1.4, enabled=False)
        self.feed = Feed(parent=ui, position=(.86, -.06))
        self.arena_text = Text(parent=ui, text='', position=(0, .27), origin=(0, 0), scale=.95)

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
        for u, dot in self.map_units.items():
            dot.enabled = u.alive
            if u.alive:
                dot.position = (u.position.x * self.map_s, u.position.z * self.map_s, dot.z)
        # joueur
        pl = self.player
        self._set_text(self.p_title, f'Pikachu   Nv.{pl.level}')
        ratio = max(0, pl.hp / pl.max_hp)
        self.p_hp.scale_x = .466 * ratio
        self.p_hp.color = hp_color(ratio)
        self._set_text(self.p_hp_text, f'{int(pl.hp)} / {pl.max_hp}')
        need = pl.level * C.XP_PER_LEVEL
        self.p_xp.scale_x = .466 * (1 if pl.level >= C.MAX_LEVEL else pl.xp / need)
        buffs = [f"{C.BUFFS[k]['name']} {int(t)}s" for k, t in pl.buffs.items() if t > 0]
        self._set_text(self.p_buffs, '  '.join(buffs))
        br = pl.brain
        for mv in C.PLAYER_MOVES:
            cd = br.cd[mv['key']] / max(.01, mv['cooldown'] * pl.cooldown_mult()) if mv['cooldown'] else 0
            self.slots[mv['key']].set_ratio(cd)
        self.dash_slot.set_ratio(br.dash_cd / C.PLAYER_DASH['cooldown'])
        # messages
        if not pl.alive and self.state == 'play':
            self._set_text(self.center_text, f'Retour dans {max(0, pl.respawn_t):.0f} s')
        else:
            self._set_text(self.center_text, '')
        a = self.arena_at(pl.position) if pl.alive else None
        if a is not None:
            st = 'contestée !' if a['contested'] else (
                f"contrôlée par l'équipe {C.TEAMS[a['owner']]['name']}" if a['owner'] else 'neutre')
            self._set_text(self.arena_text, f"{a['name']} ({C.TYPES[a['type']]['name']}) : {st}   "
                                            f"capture {int(abs(a['control']) * 100)} %")
            self.arena_text.color = C.TYPES[a['type']]['light']
        else:
            self._set_text(self.arena_text, '')
