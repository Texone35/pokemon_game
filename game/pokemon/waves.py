"""Vagues de sbires sur les voies entre deux arènes voisines (voir balance/lanes.py pour les règles).

Les sbires sont créés une fois pour toutes au début de la partie (réserve par équipe) : les deux
PC d'une partie à deux ont ainsi les mêmes numéros d'unités. Une vague « emprunte » des sbires
libres de la réserve ; un sbire K.O. ou arrivé à destination y retourne.
"""
import math
import random

from ursina import Vec3

from game import config as C
from game.pokemon.combat import flat

TEAM_KEYS = ('rouge', 'bleu')
# voies entre arènes voisines, le long de l'anneau (dans cet ordre, on fait le tour de la carte)
SEGMENTS = [('nord', 'est'), ('est', 'sud_est'), ('sud_est', 'sud_ouest'), ('sud_ouest', 'ouest'), ('ouest', 'nord')]


def _ring_paths():
    """Tracé de chaque voie (liste de points (x, z) d'une arène à l'autre), tiré de l'anneau de voies."""
    from game.world.stadium import LANES
    east, west = LANES[0][0], LANES[1][0]            # Nord -> Est -> Sud-Est -> bas ; Nord -> Ouest -> Sud-Ouest -> bas
    pos = {a['key']: tuple(a['pos']) for a in C.ARENAS}

    def cut(ring, a, b):
        i, j = ring.index(pos[a]), ring.index(pos[b])
        return ring[i:j + 1] if i <= j else ring[j:i + 1][::-1]

    # Sud-Est -> bas de l'anneau -> Sud-Ouest (au-dessus des deux bases)
    south = east[east.index(pos['sud_est']):] + west[west.index(pos['sud_ouest']):][::-1][1:]
    return {('nord', 'est'): cut(east, 'nord', 'est'), ('est', 'sud_est'): cut(east, 'est', 'sud_est'),
            ('sud_est', 'sud_ouest'): south, ('sud_ouest', 'ouest'): cut(west, 'sud_ouest', 'ouest'),
            ('ouest', 'nord'): cut(west, 'ouest', 'nord')}


class Path:
    """Trajet d'un sbire : points au sol et distances cumulées."""

    def __init__(self, pts):
        self.pts = [Vec3(x, 0, z) for x, z in pts]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + (b - a).length())
        self.length = self.cum[-1]

    def reversed(self):
        return Path([(p.x, p.z) for p in reversed(self.pts)])

    def at(self, d):
        """Point à la distance d du départ, et numéro du prochain point du trajet."""
        d = max(0.0, min(self.length, d))
        for i in range(1, len(self.pts)):
            if self.cum[i] >= d:
                a, b = self.pts[i - 1], self.pts[i]
                k = (d - self.cum[i - 1]) / max(1e-6, self.cum[i] - self.cum[i - 1])
                return a + (b - a) * k, i
        return Vec3(self.pts[-1]), len(self.pts) - 1


class Waves:
    def __init__(self, match):
        from game.pokemon.units import Unit
        self.m = match
        arenas = {a['key']: a for a in match.arenas}
        paths = _ring_paths()
        self.lanes = []
        for a, b in SEGMENTS:
            p = Path(paths[(a, b)])
            self.lanes.append({'ends': (arenas[a], arenas[b]), 'paths': (p, p.reversed()), 'timers': [None, None]})
        self.pool = {t: [] for t in TEAM_KEYS}
        comp = C.WAVES['composition']
        for team in TEAM_KEYS:
            for i in range(C.WAVES['pool']):
                u = Unit(match, comp[i % len(comp)], team, (0, 0), kind='minion')
                u.brain = MinionBrain(u, match)
                match._add_unit(u)
                match._despawn(u)
                self.pool[team].append(u)

    def reset(self):
        for lane in self.lanes:
            lane['timers'] = [None, None]
        for team in TEAM_KEYS:
            for u in self.pool[team]:
                self.m._despawn(u)

    def update(self, dt):
        for lane in self.lanes:
            for end in (0, 1):
                src, dst = lane['ends'][end], lane['ends'][1 - end]
                team = src['owner']
                if team is None or dst['owner'] == team:
                    lane['timers'][end] = None
                    continue
                if lane['timers'][end] is None:
                    lane['timers'][end] = C.WAVES['first']
                lane['timers'][end] -= dt
                if lane['timers'][end] <= 0:
                    lane['timers'][end] = C.WAVES['interval']
                    self.spawn(team, lane['paths'][end], dst)

    def spawn(self, team, path, dst):
        free = {}
        for u in self.pool[team]:
            if not u.alive and not u.creature.enabled:
                free.setdefault(u.species, []).append(u)
        comp = C.WAVES['composition']
        d0 = C.ARENA_RADIUS + 2 + (len(comp) - 1) * C.WAVES['spacing']
        for k, sp in enumerate(comp):
            if not free.get(sp):
                continue                               # réserve épuisée : vague incomplète
            u = free[sp].pop()
            pos, idx = path.at(d0 - k * C.WAVES['spacing'])
            side = (k % 2 * 2 - 1) * .6
            u.reset(pos=pos + Vec3(side, 0, 0))
            u.brain.start(path, idx, dst)


class MinionBrain:
    """Sbire : suit sa voie, se bat contre ce qu'il croise (sbires d'abord), puis attaque l'arène
    d'arrivée (tour comprise). Il ne s'éloigne pas de sa voie."""

    def __init__(self, unit, match):
        self.u, self.m = unit, match
        self.target = None
        self.path, self.idx, self.dst = None, 0, None
        self.think_t = 0.0
        self.linger = 0.0
        self.anchor = None             # point de la voie d'où il est parti en poursuite

    def start(self, path, idx, dst):
        self.path, self.idx, self.dst = path, idx, dst
        self.target, self.anchor = None, None
        self.linger = C.WAVES['linger']
        self.think_t = random.uniform(0, .3)

    def on_hit(self, source):
        if source is not None and source.alive and source.team and source.team != self.u.team and self.target is None:
            self.target = source

    def _choose(self):
        u, m = self.u, self.m
        best, bs = None, 1e9
        for e in m.units:
            if not e.alive or not e.team or e.team == u.team:
                continue
            d = (flat(e.position - u.position)).length()
            if e.kind == 'minion' and d < C.MINION_AGGRO:
                s = d
            elif e.kind == 'tower' and d < u.auto['range'] + e.radius + 4:
                s = 50 + d
            elif e.kind == 'pokemon' and d < C.MINION_AGGRO * .75 and e not in m.hidden[u.team]:
                s = 100 + d
            else:
                continue
            if s < bs:
                best, bs = e, s
        return best

    def arrived(self):
        return self.dst is not None and (flat(self.u.position) - self.dst['pos']).length() < C.ARENA_RADIUS - 3

    def update(self, dt):
        u, m = self.u, self.m
        if self.path is None:
            return False
        self.think_t -= dt
        at_dst = self.arrived()
        if at_dst:
            if self.dst['owner'] == u.team:                  # arène prise par son équipe : mission accomplie
                m.release_minion(u)
                return False
            self.linger -= dt
            if self.linger <= 0:
                m.release_minion(u)
                return False
        if self.think_t <= 0:
            self.think_t = .4 + random.random() * .2
            if self.target is None or not self.target.alive:
                self.target = self._choose()
        t = self.target
        if t is not None and (not t.alive or (flat(t.position - u.position)).length() > C.MINION_AGGRO + 4):
            self.target = t = None
        if t is not None:
            if self.anchor is None:
                self.anchor = Vec3(u.position)
            if (flat(u.position) - flat(self.anchor)).length() > C.MINION_LEASH and not at_dst:
                self.target = None                           # trop loin de sa voie : il y retourne
                return self._walk(dt)
            to = flat(t.position - u.position)
            d = to.length()
            dirn = to / d if d > .01 else u.facing()
            moved = False
            if d > u.auto['range'] + t.radius - .3:
                moved = u.move(dirn, dt)
            u.face(dirn, dt, 10)
            if u.in_attack_range(t):
                u.basic_attack(t)
            return moved
        self.anchor = None
        if at_dst:                                           # dans l'arène d'en face : il attend en garde
            return False
        return self._walk(dt)

    def _walk(self, dt):
        u, p = self.u, self.path
        while self.idx < len(p.pts):
            to = flat(p.pts[self.idx] - u.position)
            if to.length() > 1.2:
                d = to.normalized()
                moved = u.move(d, dt)
                u.face(d, dt, 8)
                return moved
            self.idx += 1
        return False
