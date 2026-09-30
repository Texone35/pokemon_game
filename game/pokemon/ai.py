"""IA « Expert » : des bots qui réfléchissent davantage comme des joueurs.

L'IA « Facile » (BotBrain, dans units.py) fonce sur l'adversaire le plus proche et se replie
sous 30 % de PV. L'IA experte :
  - évalue le rapport de force autour d'elle avant d'engager (PV, niveaux, terrain) ;
  - choisit sa cible : PV bas, avantage de type, cible déjà attaquée par ses alliés (focus) ;
  - achève un adversaire qui fuit, mais ne poursuit pas dans un piège ;
  - garde ses distances (tireurs), tourne autour de sa cible et esquive tirs, rayons et zones ;
  - se replie tôt quand le combat tourne mal, en tirant en reculant ;
  - choisit ses objectifs en équipe : défendre une arène attaquée, voler une arène laissée sans
    défense, éviter les arènes où son type est gêné, rejoindre un combat en infériorité numérique ;
  - tend des embuscades dans les hautes herbes près des arènes qu'elle garde ;
  - utilise ses capacités au bon moment (plusieurs adversaires touchés, cible ralentie ou affaiblie).
"""
import random

import numpy as np
from scipy import ndimage
from ursina import Vec3

from game import config as C
from game.pokemon.combat import Beam, Zone, flat
from game.pokemon.units import BotBrain

AIM_ERROR = 3.0          # imprécision des tirs (degrés), contre 7 pour l'IA facile
LEAD = (.75, 1.0)        # anticipation du déplacement de la cible (1 = parfaite)
SENSE = 18               # distance à laquelle elle repère un adversaire (14 pour l'IA facile)
CHASE = 24               # poursuite d'un adversaire affaibli
TEAM_R = 16              # rayon d'évaluation du rapport de force


def strength(u):
    """Force de combat approximative d'un Pokémon : PV x puissance d'attaque x effet du terrain."""
    if not u.alive:
        return 0.0
    st = u.stats
    k = (1 + max(st['atk'], st['spa']) / 100) * (1 + u.zone_mod('dmg')) / (1 + u.zone_mod('taken'))
    return u.hp * k


def bush_spots(m):
    """Centres des touffes de hautes herbes (calculés une fois par partie)."""
    spots = getattr(m, '_bush_spots', None)
    if spots is None:
        st = m.stadium
        grid = st.bush_grid
        n = int(grid.max())
        spots = []
        if n:
            for ci, cj in ndimage.center_of_mass(grid > 0, grid, range(1, n + 1)):
                spots.append(Vec3(st.j_min + ci * .5, 0, st.j_min + cj * .5))
        m._bush_spots = spots
    return spots


class ExpertBrain(BotBrain):
    AGGRO = SENSE
    aim_error = AIM_ERROR
    lead = LEAD

    def __init__(self, unit, match):
        super().__init__(unit, match)
        self.fight_ok = True
        self.lurk = None             # cachette (hautes herbes) où attendre près de son arène
        self.lurk_t = 0.0
        self.dodge = None            # direction d'esquive en cours
        self.dodge_t = 0.0
        self.orbit_t = 0.0

    # ------------------------------------------------------------ lecture de la situation
    def _enemies(self, pos, r):
        """Adversaires visibles par l'équipe près de pos."""
        u, m = self.u, self.m
        out = []
        for e in m.units:
            if e.alive and e.kind == 'pokemon' and e.team != u.team and e not in m.hidden[u.team]                     and m.in_vision(u.team, e):
                if (flat(e.position) - flat(pos)).length() < r:
                    out.append(e)
        return out

    def _allies(self, pos, r):
        u, m = self.u, self.m
        return [a for a in m.team_units[u.team] if a.alive and (flat(a.position) - flat(pos)).length() < r]

    def balance(self, pos=None):
        """Rapport de force autour de pos (> 1 : on est plus forts)."""
        pos = self.u.position if pos is None else pos
        mine = sum(strength(a) for a in self._allies(pos, TEAM_R))
        theirs = sum(strength(e) for e in self._enemies(pos, TEAM_R + 4))
        return mine / theirs if theirs else 9.0

    def _focus_count(self, e):
        """Nombre d'alliés qui attaquent déjà cet adversaire."""
        return sum(1 for a in self.m.team_units[self.u.team]
                   if a is not self.u and a.alive and a.brain is not None and getattr(a.brain, 'target', None) is e)

    def _score_target(self, e, d):
        u = self.u
        eff = C.TYPE_CHART.get((u.type, e.type), 1.0)
        s = d * .6 + 22 * e.hp_ratio()
        s -= 40 * (eff - 1)                      # avantage de type (+25 % -> -10)
        s -= 5 * min(2, self._focus_count(e))    # on concentre les tirs de l'équipe
        s += 2.5 * max(0, e.level - u.level)
        if e.brain is not None and getattr(e.brain, 'target', None) is u:
            s -= 4                               # celui qui nous attaque
        return s

    # ------------------------------------------------------------ décisions
    def think(self):
        u, m = self.u, self.m
        near = self._enemies(u.position, 14)
        bal = self.balance()
        # repli : plus tôt quand le combat tourne mal, plus tard quand on domine
        limit = .45 if near and bal < 1 else .3 if near else .22
        if self.mode != 'retreat' and u.hp_ratio() < limit and not (bal > 2.5 and near and near[0].hp_ratio() < .2):
            self.mode = 'retreat'
            self.lurk = None
        if self.mode == 'retreat':
            if u.hp_ratio() > .85:
                self.mode = None
            else:
                self.target = None
                self.goal = self._safe_goal()
                return
        # choix de la cible
        best, score = None, 1e9
        for e in self._enemies(u.position, self.AGGRO):
            d = (flat(e.position - u.position)).length()
            if not m.can_see(u, e):
                continue
            s = self._score_target(e, d)
            if s < score:
                best, score = e, s
        t = self.target
        if t is not None and t.alive and t.kind == 'pokemon' and t.hp_ratio() < .3 and t not in m.hidden[u.team] \
                and (flat(t.position - u.position)).length() < CHASE:
            best = t                             # on achève un adversaire affaibli
        if best is not None:
            self.fight_ok = bal >= .8 or best.hp_ratio() < .3 or u.last_hit_by is best
            if self.fight_ok:
                self.target = best
                self.lurk = None
                return
            # combat perdu d'avance : on recule vers ses alliés sans lâcher la cible des yeux
            self.target = best
            self.goal = self._safe_goal()
            return
        if self.target is not None and self.target.team is not None:
            self.target = None
        if self.target is not None and (not self.target.alive
                                        or (flat(self.target.position - u.position)).length() > 18):
            self.target = None
        self.fight_ok = True
        self.goal = expert_goal(m, u, self.goal)
        self._neutral_targets()
        self._maybe_lurk()

    def _neutral_targets(self):
        u, m = self.u, self.m
        if self.target is not None or not self.goal:
            return
        tower = m.enemy_tower_near(u, 18)
        if tower is not None and self.balance() >= 1:
            self.target = tower
            return
        minion = m.enemy_minion_near(u, 9)
        if minion is not None:
            self.target = minion
            return
        if self.goal[0].startswith(('camp', 'wild', 'pit')):
            gp = self.goal[1]
            if (flat(u.position) - gp).length() < 14:
                for n in m.units:
                    if n.alive and n.team is None and (flat(n.position) - gp).length() < 12:
                        self.target = n
                        return
        elif self.goal[0].startswith('arena') and u.hp_ratio() > .6:
            wild = m.nearest_wild(u.position, 11)          # un sauvage sur le chemin : de l'expérience facile
            if wild is not None:
                self.target = wild

    def _safe_goal(self):
        """Où se replier : une arène alliée sûre et proche (on s'y regroupe), sinon la base (soins)."""
        u, m = self.u, self.m
        base = m.base_goal(u.team)
        if u.hp_ratio() < .3:
            return self.heal_goal()
        enemy = 'bleu' if u.team == 'rouge' else 'rouge'
        best, bd = base, (base[1] - flat(u.position)).length()
        for a in m.arenas:
            if a['owner'] == u.team and a['count'][enemy] == 0 and self.balance(a['pos']) > 1.2:
                d = (a['pos'] - flat(u.position)).length()
                if d < bd:
                    best, bd = (a['nav'], a['pos'], C.ARENA_RADIUS - 5), d
        return best

    def _maybe_lurk(self):
        """Arène tenue et calme : on attend caché dans les hautes herbes voisines."""
        u, m = self.u, self.m
        g = self.goal
        if not g or not g[0].startswith('arena') or self.target is not None:
            self.lurk = None
            return
        a = next((a for a in m.arenas if a['nav'] == g[0]), None)
        enemy = 'bleu' if u.team == 'rouge' else 'rouge'
        if a is None or a['owner'] != u.team or a['count'][enemy] > 0:
            self.lurk = None
            return
        if self.lurk is None and random.random() < .35:
            spots = [s for s in bush_spots(m) if (s - a['pos']).length() < C.ARENA_RADIUS + 8]
            if spots:
                self.lurk = min(spots, key=lambda s: (s - flat(u.position)).length())
                self.lurk_t = random.uniform(8, 16)

    # ------------------------------------------------------------ esquive
    def _threat(self):
        """Direction d'esquive si un tir, un rayon ou une zone ennemie va nous toucher, sinon None."""
        u, m = self.u, self.m
        p = flat(u.position)
        for pr in m.projectiles:
            if not pr.alive or not m.hostile(pr.owner, u) or getattr(pr, 'homing', None) is not None:
                continue
            v = flat(pr.vel)
            v2 = v.x * v.x + v.z * v.z
            if v2 < 1:
                continue
            rel = p - flat(pr.e.position)
            t = (rel.x * v.x + rel.z * v.z) / v2
            if 0 < t < .7:
                miss = rel - v * t
                if miss.length() < u.radius + pr.radius + .5:
                    side = Vec3(v.z, 0, -v.x).normalized()
                    return side if side.dot(miss) >= 0 else -side
        for h in m.hazards:
            if not getattr(h, 'alive', False) or not m.hostile(h.owner, u):
                continue
            if isinstance(h, Zone) and h.timer > 0:
                d = p - h.pos
                if d.length() < h.radius + u.radius + .3:
                    return d.normalized() if d.length() > .1 else Vec3(1, 0, 0)
            elif isinstance(h, Beam) and h.beam is None:
                rel = p - h.origin
                along = rel.x * h.dir.x + rel.z * h.dir.z
                if 0 < along < h.length:
                    off = rel - h.dir * along
                    if off.length() < h.width / 2 + u.radius + .4:
                        side = Vec3(h.dir.z, 0, -h.dir.x)
                        return side if side.dot(off) >= 0 else -side
        return None

    # ------------------------------------------------------------ action
    def update(self, dt):
        u, m = self.u, self.m
        self.think_t -= dt
        self.move_t -= dt
        if self.think_t <= 0:
            self.think_t = .22 + random.random() * .12            # réagit plus vite que l'IA facile
            self.think()
        self.dodge_t -= dt
        if self.dodge_t <= 0:
            self.dodge = self._threat()
            self.dodge_t = .12 if self.dodge is None else .3
        t = self.target
        if t is not None and (not t.alive or (t.team is None and self.mode == 'retreat') or t in m.hidden[u.team]):
            self.target = t = None
        # repli (ou combat perdu d'avance) : on court vers l'abri en tirant sur le poursuivant
        if self.mode == 'retreat' or (t is not None and t.kind == 'pokemon' and not self.fight_ok):
            moved = self._go(self.goal, dt) if self.goal else False
            chaser = t or next(iter(self._enemies(u.position, u.auto['range'] + 1)), None)
            if chaser is not None and m.can_see(u, chaser) and u.in_attack_range(chaser):
                u.basic_attack(chaser)
            self.use_moves(chaser, (flat(chaser.position - u.position)).length() if chaser is not None else 0)
            return moved
        if t is not None:
            return self._fight(t, dt)
        if self.dodge is not None:
            return u.move(self.dodge, dt)
        if self.lurk is not None:                                # embuscade dans les hautes herbes
            self.lurk_t -= dt
            to = flat(self.lurk - u.position)
            if self.lurk_t <= 0:
                self.lurk = None
            elif to.length() > 1.2:
                d = to.normalized()
                moved = u.move(d, dt, .8)
                u.face(d, dt, 8)
                return moved
            return False
        return super().update(dt) if self.goal else False

    def _go(self, goal, dt):
        u, m = self.u, self.m
        key, gp, gr = goal
        if (flat(u.position) - gp).length() <= gr:
            return False
        dirn = m.stadium.direction(key, gp, u.position, u.team)
        if self.dodge is not None:
            dirn = (dirn + self.dodge * 1.5).normalized()
        moved = u.move(dirn, dt)
        if moved:
            u.face(dirn, dt, 10)
        return moved

    def _fight(self, t, dt):
        u, m = self.u, self.m
        to_t = flat(t.position - u.position)
        d = to_t.length()
        dirn = to_t.normalized() if d > .01 else u.facing()
        if not m.can_see(u, t):
            self.blind += dt
            if self.blind > 1.5:
                self.target, self.blind = None, 0.0
            moved = u.move(dirn, dt)
            u.face(dirn, dt, 14)
            return moved
        self.blind = 0.0
        a = u.auto
        rng = a['range'] + t.radius
        side = Vec3(dirn.z, 0, -dirn.x)
        self.orbit_t -= dt
        if self.orbit_t <= 0:                   # change de sens de rotation de façon imprévisible
            self.orbit_t = random.uniform(.5, 1.4)
            self.strafe = random.choice((-1, 1))
        if self.dodge is not None:
            move = self.dodge
        elif a['kind'] == 'ranged':
            ideal = rng * (.62 if t.auto['kind'] == 'melee' else .8)   # hors de portée d'un corps-à-corps
            if d > rng * .92:
                move = dirn + side * self.strafe * .3
            elif d < ideal - 1.5:
                move = -dirn + side * self.strafe * .6
            else:
                move = side * self.strafe
        else:
            move = dirn + side * self.strafe * (.35 if d < rng * 1.5 else 0)
        moved = u.move(move.normalized(), dt, 1.0 if a['kind'] == 'melee' or d > rng * .92 else .8)
        u.face(dirn, dt, 16)
        if d < rng:
            u.basic_attack(t)
        self.use_moves(t, d)
        return moved

# ==================================================================== objectifs d'équipe
def expert_goal(m, u, current):
    """Objectif d'un bot expert : pensé pour l'équipe, pas seulement pour lui."""
    team = u.team
    enemy = 'bleu' if team == 'rouge' else 'rouge'
    here = flat(u.position)
    if m.wants_shop(u):
        return m.base_goal(team)
    boss = m.active_boss()
    if boss is not None:
        at_pit = sum(1 for e in m.team_units[enemy] if e.alive and (flat(e.position)).length() < 20)
        mine = sum(1 for a in m.team_units[team] if a.alive and (flat(a.position)).length() < 25)
        if u in m.boss_squad[team] or (at_pit and mine >= at_pit and here.length() < 45):
            return ('pit', Vec3(0, 0, 0), 7)
    # retard d'expérience : on va chercher un sauvage proche
    avg = np.mean([e.level for e in m.team_units[enemy]]) if m.team_units[enemy] else u.level
    if u.level + 2 <= avg:
        wild = m.nearest_wild(u.position, 28)
        if wild is not None:
            camp = wild.camp
            return (camp['key'], camp['pos'], 4)
    if u.role == 'jungle':
        best, bs = None, 1e9
        for camp in m.camps:
            if camp['alive'] and not camp.get('wild'):
                s = (camp['pos'] - here).length() - (30 if camp['cfg'].get('buff') else 0)
                contest = sum(1 for e in m.team_units[enemy] if e.alive and (flat(e.position) - camp['pos']).length() < 14)
                s += 25 * contest
                if s < bs:
                    best, bs = camp, s
        if best is not None and bs < 40:
            return (best['key'], best['pos'], 4)
    behind = m.score[team] < m.score[enemy] - 60
    best, bs = None, 1e9
    for a in m.arenas:
        d = (a['pos'] - here).length()
        s = d / 28
        mine, theirs = a['count'][team], a['count'][enemy]
        heading = m._goal_count(team, a['nav'], u)
        if a['owner'] == team:
            if theirs > 0:
                s -= 6 - min(3, max(0, mine + heading - theirs - 1) * 1.5)   # défendre, sans s'entasser
            else:
                s += 3.5
        elif a['owner'] is None:
            s -= 1.2
        else:
            s -= 1.5 if theirs == 0 else .3                  # une arène ennemie laissée sans défense
            if behind:
                s -= 1.2
        if theirs >= 3 and mine + heading < 2:
            s += 2.5                                         # ne pas y aller seul contre trois
        eff = C.zone_effect(a['type'], u.type)
        s -= 5 * (eff.get('dmg', 0) + eff.get('speed', 0) - eff.get('taken', 0))   # terrain favorable
        if a['key'] == u.role:
            s -= 1.0
        if current and current[0] == a['nav']:
            s -= 1.0
        s += 1.4 * max(0, heading - max(theirs, 1) + 1)
        if s < bs:
            best, bs = a, s
    return (best['nav'], best['pos'], C.ARENA_RADIUS - 4)
