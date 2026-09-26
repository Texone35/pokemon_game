"""Attaques en jeu : projectiles, zones au sol, rayons, ondes de choc.

Chaque attaque a un propriétaire (`owner`, une Unit) et ne touche que les
unités qui lui sont hostiles (voir Match.hostile). Les dégâts passent tous
par Match.deal_damage, qui applique niveaux, bonus, types et météo.

En partie à deux, seul l'hôte (match.authority) calcule les touches et les dégâts ;
chaque attaque créée chez lui est annoncée à l'invité (match.emit), qui la rejoue
uniquement pour l'affichage.

Le rendu utilise des halos lumineux et des particules (voir fx.py) dont
l'aspect dépend du type du lanceur : flammes qui montent pour le Feu, gouttes
qui retombent pour l'Eau, étincelles pour l'Électrik, feuilles pour la Plante...
"""
import math
import random

from ursina import Entity, Vec3, color, destroy

import fx
from fx import explosion, glow_sprite, lightning, orient, rnd, style
from geometry import MeshBuilder, flat_circle


def flat(v):
    return Vec3(v.x, 0, v.z)


def r3(v):
    """Vecteur -> liste arrondie (message réseau)."""
    return [round(v[0], 3), round(v[1], 3), round(v[2], 3)]


def rc(c):
    """Couleur -> liste arrondie (message réseau)."""
    return [round(c[0], 3), round(c[1], 3), round(c[2], 3), round(c[3], 3) if len(c) > 3 else 1]


def warn_color(owner):
    """Couleur des annonces au sol : rouge si c'est dangereux pour le joueur."""
    return color.rgba(1, .95, .4, .3) if owner.team == 'rouge' else color.rgba(1, .12, .08, .32)


def _near_camera(match, pos, dist=45):
    return (flat(pos) - flat(match.cam_target)).length() < dist


def _shape_mesh(parent, shape, size, col):
    """Petit objet solide au cœur de certains projectiles (feuille, éclat de glace, rocher)."""
    b = MeshBuilder()
    if shape == 'leaf':
        b.add('sphere_md', (0, 0, 0), (size * .9, size * .12, size * 1.6), col=col, grad=.2)
        b.add('box', (0, .02, 0), (size * .05, size * .05, size * 1.4), col=color.rgb(.2, .5, .15))
    elif shape == 'shard':
        b.add('cone6', (0, 0, size * .45), (size * .5, size * 1.4, size * .5), rot=(90, 0, 0), col=col)
        b.add('cone6', (0, 0, -size * .2), (size * .5, size * .5, size * .5), rot=(-90, 0, 0), col=col)
    elif shape == 'rock':
        b.add('blob', (0, 0, 0), size * 1.1, col=col, wobble=.25, grad=.35)
    else:
        return None
    return b.entity(parent=parent, emissive=.35 if shape == 'shard' else 0)


class Projectile:
    def __init__(self, match, owner, pos, vel, damage, size, col, shape='sphere', homing=None, turn=0.0,
                 life=2.0, status=None, stun=0.0, pid=None):
        self.match, self.owner = match, owner
        self.pid = pid
        self.vel = Vec3(vel)
        self.damage, self.radius, self.col = damage, size * .5, col
        self.homing, self.turn, self.life = homing, turn, life
        self.status, self.stun = status, stun
        self.shape = shape
        self.alive = True
        self.st = style(owner.type)
        self._trail = 0.0
        self.e = Entity(parent=match.root, position=pos)
        core = self.st['core']
        if shape == 'cage':
            self.halo = glow_sprite(self.e, (.5, .9, 1, .9), size * 2.8)
            glow_sprite(self.e, (1, 1, 1, .8), size * 1.1)
        else:
            self.halo = glow_sprite(self.e, (col[0], col[1], col[2], .95), size * 2.6)
            glow_sprite(self.e, (1, 1, 1, .9) if shape == 'sphere' else (core[0], core[1], core[2], .6), size * 1.1)
        self.mesh = _shape_mesh(self.e, shape, size, col)
        orient(self.e, self.vel)
        if match.authority and match.net is not None:
            self.pid = match.net.new_pid()
            match.emit('proj', self.pid, owner.uid, r3(pos), r3(self.vel), size, rc(col), shape,
                       homing.uid if homing is not None else -1, turn, round(life, 3))
        if _near_camera(match, pos) and fx.PARTICLES:          # petit éclat au départ du tir
            for _ in range(3):
                v = self.vel.normalized() * random.uniform(1, 3) + Vec3(rnd(), rnd(), rnd())
                fx.PARTICLES.emit(pos, self.st['hot'], size=size * 1.3, life=.18, vel=(v.x, v.y, v.z))

    def update(self, dt):
        self.life -= dt
        h = self.homing
        if h is not None and h.alive and self.turn:
            aim = Vec3(h.position.x, h.position.y + 1, h.position.z)
            desired = (aim - self.e.position).normalized() * self.vel.length()
            self.vel = self.vel + (desired - self.vel) * min(1, self.turn * dt)
        self.e.position += self.vel * dt
        if self.mesh is not None:
            if self.shape == 'leaf':
                self.mesh.rotation_y += dt * 900
            else:
                self.mesh.rotation_z += dt * 500
        else:
            orient(self.e, self.vel)
        self.halo.set_scale(self.radius * 5.2 * (1 + math.sin(self.life * 40) * .12))   # scintillement
        self._emit_trail(dt)
        if self.life <= 0:
            self.kill(False)
            return
        if not self.match.authority:          # chez l'invité, l'hôte annonce les impacts
            return
        p = self.e.position
        for u in self.match.units:
            if u.alive and self.match.hostile(self.owner, u):
                if (flat(u.position) - flat(p)).length() < self.radius + u.radius * .85:
                    self.match.deal_damage(self.owner, u, self.damage, self.status, self.stun)
                    self.kill()
                    return

    def _emit_trail(self, dt):
        P = fx.PARTICLES
        if P is None or not _near_camera(self.match, self.e.position):
            return
        self._trail -= dt
        if self._trail > 0:
            return
        self._trail = .03
        st, p, spread = self.st, self.e.position, self.st['spread']
        s = self.radius * 2
        back = -self.vel.normalized() * random.uniform(.5, 1.5)
        rise = 1 if st['gravity'] < 0 else 0
        P.emit(p + Vec3(rnd(s * .3), rnd(s * .3), rnd(s * .3)), st['trail'], size=s * 1.6, life=random.uniform(.2, .4),
               vel=(back.x + rnd(spread), back.y + rnd(spread) + rise, back.z + rnd(spread)),
               grow=.3, gravity=st['gravity'], drag=1.5)

    def kill(self, impact=True):
        if not self.alive:
            return
        self.alive = False
        if impact and self.pid is not None and self.match.authority:
            self.match.emit('pk', self.pid)
        if impact and fx.PARTICLES:
            fx.burst(None, self.e.position, self.st['hot'], n=7, speed=3, size=self.radius * .9, life=.35)
            fx.PARTICLES.emit(self.e.position, self.st['core'], size=self.radius * 5, life=.2, grow=1.5)
        destroy(self.e)


class Zone:
    """Zone annoncée au sol, puis explosion (ou éclair) qui touche tout ce qui est dedans."""

    def __init__(self, match, owner, pos, radius, delay, damage, col, status=None, style='explosion'):
        self.match, self.owner = match, owner
        self.pos, self.radius, self.delay, self.timer = flat(pos), radius, delay, delay
        self.damage, self.col, self.status, self.style = damage, col, status, style
        self.alive = True
        self.gy = gy = match.stadium.walk_y(self.pos.x, self.pos.z)
        self.outline = flat_circle(match.root, radius, warn_color(owner), position=self.pos + Vec3(0, gy + .12, 0))
        self.fill = flat_circle(match.root, radius, color.rgba(col[0], col[1], col[2], .45),
                                position=self.pos + Vec3(0, gy + .13, 0), scale=.01)
        match.emit('zone', owner.uid, round(self.pos.x, 3), round(self.pos.z, 3), radius, delay, rc(col), style)

    def update(self, dt):
        self.timer -= dt
        self.fill.scale = max(.01, 1 - max(0, self.timer) / self.delay)
        if fx.PARTICLES and random.random() < .5:       # l'attaque se prépare : lueurs au sol
            a, r = random.uniform(0, math.tau), random.uniform(0, self.radius)
            fx.PARTICLES.emit(self.pos + Vec3(math.sin(a) * r, self.gy + .2, math.cos(a) * r),
                              style(self.owner.type)['trail'], size=.5, life=.4, vel=(0, 1.5, 0))
        if self.timer <= 0:
            self.explode()

    def explode(self):
        self.cleanup()
        m = self.match
        p = self.pos + Vec3(0, self.gy, 0)
        if self.style == 'lightning':
            lightning(m.root, p, (1, .95, .45))
        else:
            explosion(p, style(self.owner.type), self.radius)
        m.shake_at(self.pos, .25)
        if not m.authority:
            return
        for u in m.units:
            if u.alive and m.hostile(self.owner, u) and (flat(u.position) - self.pos).length() < self.radius + u.radius:
                m.deal_damage(self.owner, u, self.damage, self.status)

    def cleanup(self):
        if self.alive:
            self.alive = False
            destroy(self.outline)
            destroy(self.fill)


class Wave:
    """Onde de choc circulaire qui s'élargit ; touche une fois chaque cible."""

    def __init__(self, match, owner, centre, speed, max_radius, damage, col, status=None, start=1.0):
        self.match, self.owner = match, owner
        self.centre, self.speed, self.max_radius = flat(centre), speed, max_radius
        self.damage, self.status, self.col = damage, status, col
        self.r = start
        self.hit = set()
        self.alive = True
        self.gy = match.stadium.walk_y(self.centre.x, self.centre.z)
        self._emit = 0.0
        match.emit('wave', owner.uid, round(self.centre.x, 3), round(self.centre.z, 3), speed, max_radius,
                   rc(col), start)

    def update(self, dt):
        self.r += self.speed * dt
        m = self.match
        self._emit -= dt
        if self._emit <= 0 and fx.PARTICLES and _near_camera(m, self.centre, 55):
            self._emit = .035
            hot = style(self.owner.type)['hot']
            n = int(6 + self.r * 1.2)
            for i in range(n):
                a = math.tau * (i + random.random()) / n
                fx.PARTICLES.emit(self.centre + Vec3(math.sin(a) * self.r, self.gy + .35, math.cos(a) * self.r),
                                  self.col if i % 2 else hot, size=.8, life=.25,
                                  vel=(math.sin(a) * 2, random.uniform(.5, 2), math.cos(a) * 2), grow=.5)
        for u in m.units if m.authority else ():
            if u.alive and id(u) not in self.hit and m.hostile(self.owner, u):
                d = (flat(u.position) - self.centre).length()
                if abs(d - self.r) < .9 + u.radius * .5:
                    self.hit.add(id(u))
                    m.deal_damage(self.owner, u, self.damage, self.status)
        if self.r >= self.max_radius:
            self.cleanup()

    def cleanup(self):
        self.alive = False


class Beam:
    """Rayon : une bande au sol annonce la trajectoire, puis un jet de lumière part."""

    def __init__(self, match, owner, origin, direction, length, width, delay, damage, col, status=None):
        self.match, self.owner = match, owner
        self.origin, self.dir = flat(origin), flat(direction).normalized()
        self.length, self.width, self.delay, self.timer = length, width, delay, delay
        self.damage, self.col, self.status = damage, col, status
        self.fire_t = 0
        self.hit = set()
        self.alive = True
        self.yaw = math.degrees(math.atan2(self.dir.x, self.dir.z))
        self.mid = self.origin + self.dir * (length / 2)
        self.y = owner.position.y
        self.tele = Entity(parent=match.root, model='cube', color=warn_color(owner),
                           position=self.mid + Vec3(0, self.y + .12, 0), scale=(width * .2, .02, length),
                           rotation_y=self.yaw)
        self.beam = None
        self.sprites = []
        match.emit('beam', owner.uid, round(self.origin.x, 3), round(self.origin.z, 3), round(self.dir.x, 4),
                   round(self.dir.z, 4), length, width, delay, rc(col))

    def update(self, dt):
        if self.beam is None:
            if not self.owner.alive:
                self.cleanup()
                return
            self.timer -= dt
            k = 1 - max(0, self.timer) / self.delay
            self.tele.scale_x = self.width * (.2 + .8 * k)
            if self.timer <= 0:
                destroy(self.tele)
                self.tele = None
                self._fire()
            return
        self.fire_t -= dt
        k = max(0.0, self.fire_t / .45)
        for i, s in enumerate(self.sprites):
            s.set_scale(self.width * (1.6 if i % 2 else .8) * (.3 + .7 * k) * (1 + math.sin(self.fire_t * 50 + i) * .15))
        if fx.PARTICLES and _near_camera(self.match, self.mid, 50):
            st = style(self.owner.type)
            for _ in range(4):
                t = random.random() * self.length
                p = self.origin + self.dir * t + Vec3(rnd(self.width * .4), self.y + .9 + rnd(.3), rnd(self.width * .4))
                fx.PARTICLES.emit(p, st['trail'], size=.8, life=.3,
                                  vel=(self.dir.x * 6 + rnd(), -st['gravity'] * .3 + rnd(), self.dir.z * 6 + rnd()),
                                  grow=.4)
        m = self.match
        for u in m.units if m.authority else ():
            if u.alive and id(u) not in self.hit and m.hostile(self.owner, u):
                rel = flat(u.position) - self.origin
                along = rel.x * self.dir.x + rel.z * self.dir.z
                perp = (rel - self.dir * along).length()
                if 0 < along < self.length and perp < self.width / 2 + u.radius * .8:
                    self.hit.add(id(u))
                    m.deal_damage(self.owner, u, self.damage, self.status)
        if self.fire_t <= 0:
            self.cleanup()

    def _fire(self):
        st = style(self.owner.type)
        self.beam = Entity(parent=self.match.root)
        n = int(self.length / .7)
        for i in range(n):
            p = self.origin + self.dir * (i * .7 + .35) + Vec3(0, self.y + .9, 0)
            col = st['hot'] if i % 2 == 0 else (self.col[0], self.col[1], self.col[2])
            s = glow_sprite(self.beam, (col[0], col[1], col[2], .85), self.width)
            s.set_pos(p.x, p.y, p.z)
            self.sprites.append(s)
        self.fire_t = .45
        self.match.shake_at(self.mid, .3)

    def cleanup(self):
        if self.alive:
            self.alive = False
            if self.tele:
                destroy(self.tele)
            if self.beam:
                destroy(self.beam)


def cast_special(match, u, target):
    """Lance la capacité spéciale de l'unité `u` (définie dans config.SPECIES)."""
    sp = u.data['special']
    kind = sp['kind']
    col = sp.get('color', color.white)
    dmg = sp.get('damage', 0)
    status = sp.get('status')
    origin = u.position + Vec3(0, .9, 0)
    to_t = flat(target.position - u.position) if target else flat(u.facing())
    d = to_t.normalized() if to_t.length() > .01 else Vec3(0, 0, 1)
    u.face(d)
    match.announce_cast(u, sp['name'])
    if kind == 'beam':
        match.hazards.append(Beam(match, u, u.position + d * u.radius, d, sp['length'], sp['width'], sp['delay'],
                                  dmg, col, status))
        u.channel = sp['delay'] + .35
    elif kind == 'wave':
        match.hazards.append(Wave(match, u, u.position, sp['speed'], sp['radius'], dmg, col, status, start=u.radius))
        u.pulse()
    elif kind == 'zone':
        p = target.position if target else u.position + d * 6
        match.hazards.append(Zone(match, u, p, sp['radius'], sp['delay'], dmg, col, status))
    elif kind == 'nova':
        n = sp['count']
        base = random.uniform(0, math.tau)
        for i in range(n):
            a = base + math.tau * i / n
            v = Vec3(math.sin(a), 0, math.cos(a)) * sp['speed']
            match.projectiles.append(Projectile(match, u, origin + v.normalized() * u.radius, v, dmg,
                                                sp.get('size', .6), col, life=2.2, status=status))
        u.pulse()
    elif kind == 'charge':
        u.start_charge(d, sp['speed'], sp['duration'], dmg)
    elif kind == 'heal':
        for a in match.units:
            if a.alive and a.team == u.team and (flat(a.position - u.position)).length() < sp['radius']:
                a.heal(sp['heal'])
        heal_fx(match, u, sp['radius'], col)
        match.emit('healfx', u.uid, sp['radius'], rc(col))


def heal_fx(match, u, radius, col):
    """Effet de soin : anneau qui s'étend et lueurs qui montent sur les alliés proches."""
    P = fx.PARTICLES
    if not P:
        return
    for a in match.units:
        if a.alive and a.team == u.team and (flat(a.position - u.position)).length() < radius:
            for _ in range(8):
                P.emit(a.position + Vec3(rnd(.6), random.uniform(.2, 1.5), rnd(.6)), col, size=.6,
                       life=.8, vel=(0, 1.8, 0), grow=.5)
    for i in range(28):
        ang = math.tau * i / 28
        v = Vec3(math.sin(ang), 0, math.cos(ang)) * radius * 2.2
        P.emit(u.position + Vec3(0, .4, 0), col, size=.9, life=.45, vel=(v.x, .5, v.z), drag=2, grow=.6)
