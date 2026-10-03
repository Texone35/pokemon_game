"""Lancement des attaques : le même code pour les joueurs, les IA et les Pokémon neutres.

cast(match, unit, move, target, point)
  - target : unité visée (attaques à ciblage automatique, « lock ») ;
  - point  : point visé au sol (attaques visées à la souris, « skill »), ramené à la portée.
Les dégâts sont calculés au lancement à partir des stats du lanceur (voir kit.raw_damage),
puis réduits à l'impact par la défense de la cible (voir Match.deal_damage).
"""
import math
import random

from ursina import Vec3

from game import config as C
from game.pokemon import kit
from game.pokemon.combat import Beam, Projectile, Wave, Zone, flat, heal_area
from game.world import fx


def off_stat(u, mv):
    return u.stats['atk' if mv.get('cat', 'phys') == 'phys' else 'spa']


def raw(u, mv):
    """Dégâts bruts de l'attaque lancée par u (météo et bonus sont appliqués à l'impact)."""
    return kit.raw_damage(mv['power'], off_stat(u, mv), mv.get('aim', 'lock'))


def aim(u, mv, target=None, point=None):
    """Direction (vecteur plat normalisé) et point visé, ramené à la portée de l'attaque."""
    here = flat(u.position)
    if point is not None:
        p = flat(point)
    elif target is not None:
        p = flat(target.position)
    else:
        p = here + u.facing() * min(6.0, kit.cast_range(mv))
    d = p - here
    dist = d.length()
    d = d / dist if dist > .01 else u.facing()
    rng = kit.cast_range(mv)
    if dist > rng:
        p = here + d * rng
    return d, p


def blink_target(m, u, d, distance):
    """Arrivée d'une téléportation : droit devant, sans traverser les murs."""
    st = m.stadium
    here = flat(u.position)
    dest = st.reach(here, here + d * distance)
    if (dest - here).length() > 1.2:
        dest -= d * .8                            # on s'arrête avant le mur
    else:
        dest = here
    p = st.collide(Vec3(dest.x, 0, dest.z), u.radius, u.team)
    p.y = st.walk_y(p.x, p.z)
    return p


def cast(m, u, mv, target=None, point=None, announce=True):
    """Lance l'attaque `mv` de `u` (sans vérifier la recharge : voir Unit.use_move)."""
    kind = mv['kind']
    d, p = aim(u, mv, target, point)
    u.face(d)
    u.attack_anim = .2
    if announce:
        m.announce_cast(u, mv['name'])
    col = mv.get('color', C.TYPES[u.type]['color'])
    status, stun, cat = mv.get('status'), mv.get('stun', 0.0), mv.get('cat', 'phys')
    dmg = raw(u, mv) if kind != 'heal' else 0
    if mv.get('guard'):
        u.guard_t, u.guard_red = mv['guard']
    if kind == 'rush':
        u.start_rush(mv, d, target if mv.get('aim') == 'lock' else None, dmg)
    elif kind == 'charge':
        u.start_charge(d, mv['speed'], mv['duration'], dmg, cat)
    elif kind == 'strike':
        delay = mv['delay']
        if 'sur_pluie' in mv.get('tags', ()) and m.weather_of(u) == 'pluie':
            sure = m.nearest_enemy(u, p, mv['radius'] + 4)        # sous la pluie : la foudre ne rate pas
            if sure is not None:
                p, delay = flat(sure.position), .05
        p = m.stadium.reach(u.position, p)                       # pas de frappe au cœur d'un mur
        m.hazards.append(Zone(m, u, p, mv['radius'], delay, dmg, col, status=status,
                              style=mv.get('style', 'explosion'), stun=stun, cat=cat))
    elif kind in ('shot', 'homing'):
        start = u.position + Vec3(0, 1.0, 0) + d * (u.radius + .3)
        homing = target if kind == 'homing' else None
        life = 1.8 if homing is not None else mv.get('range', 14) / mv['speed']
        m.projectiles.append(Projectile(m, u, start, d * mv['speed'], dmg, mv['size'], col,
                                        shape=mv.get('shape', 'sphere'), homing=homing, turn=.8 if homing else 0,
                                        life=life, status=status, stun=stun, cat=cat))
    elif kind == 'spin':
        u.spin()
        u.invuln = max(u.invuln, .3)
        m.hazards.append(Wave(m, u, u.position, 18, mv['radius'], dmg, col, status=status, start=.8, stun=stun,
                              cat=cat))
        for pr in m.projectiles:     # l'onde renvoie les projectiles proches
            if pr.owner is not u and m.hostile(pr.owner, u) and (flat(pr.e.position - u.position)).length() < mv['radius']:
                pr.kill()
    elif kind == 'wave':
        m.hazards.append(Wave(m, u, u.position, mv['speed'], mv['radius'], dmg, col, status, start=u.radius,
                              stun=stun, cat=cat, kind=mv.get('fx')))
        u.pulse()
    elif kind == 'beam':
        delay = mv['delay']
        if 'solaire' in mv.get('tags', ()) and m.weather_of(u) == 'soleil':
            delay *= C.SUN_SOLAR_DELAY                           # Lance-Soleil : presque instantané au soleil
        m.hazards.append(Beam(m, u, u.position + d * u.radius, d, mv['length'], mv['width'], delay, dmg, col,
                              status, stun=stun, cat=cat))
        u.channel = delay + .35
    elif kind == 'nova':
        n = mv['count']
        base = random.uniform(0, math.tau)
        origin = u.position + Vec3(0, .9, 0)
        for i in range(n):
            a = base + math.tau * i / n
            v = Vec3(math.sin(a), 0, math.cos(a)) * mv['speed']
            m.projectiles.append(Projectile(m, u, origin + v.normalized() * u.radius, v, dmg, mv.get('size', .6), col,
                                            life=2.2, status=status, cat=cat))
        u.pulse()
    elif kind == 'blink':
        dest = blink_target(m, u, d, min(mv['distance'], (p - flat(u.position)).length() + .01))
        fx.impact(u.type, u.position + Vec3(0, 1, 0), .5)
        if not u.net_driven:
            u.position = dest
        u.invuln = max(u.invuln, .25)
        m.hazards.append(Wave(m, u, dest, 22, mv['radius'], dmg, col, start=.5, stun=stun, cat=cat))
    elif kind == 'heal':
        amount = kit.heal_amount(mv['power'], u.stats['spa'])
        if 'synthese' in mv.get('tags', ()) and m.weather_of(u) == 'soleil':
            amount *= C.SUN_SYNTHESIS
        heal_area(m, u, amount, mv['radius'], col)
    return True


def predict(m, u, mv, target=None, point=None):
    """Invité : la partie « mouvement » de l'attaque se joue tout de suite chez lui (sans dégâts)."""
    kind = mv['kind']
    d, p = aim(u, mv, target, point)
    u.face(d)
    u.attack_anim = .2
    if kind == 'rush':
        u.start_rush(mv, d, target if mv.get('aim') == 'lock' else None, 0)
    elif kind == 'spin':
        u.creature.pivot.rotation_y = 0
        u.creature.pivot.animate('rotation_y', 720, duration=.35)
    elif kind == 'charge':
        u.start_charge(d, mv['speed'], mv['duration'], 0)
    elif kind == 'blink':
        u.position = blink_target(m, u, d, min(mv['distance'], (p - flat(u.position)).length() + .01))
    elif kind == 'beam':
        u.channel = mv['delay'] + .35


# ==================================================================== IA : quand et où lancer
def lead_point(u, mv, t, lead=(.2, .9), err=7.0):
    """Point visé par une IA : la cible, là où elle sera à l'impact (anticipation imparfaite)."""
    here, tp = flat(u.position), flat(t.position)
    dist = (tp - here).length()
    k = mv['kind']
    if k == 'strike':
        delay = mv['delay']
    elif k in ('shot', 'homing', 'nova'):
        delay = dist / max(1.0, mv['speed'])
    elif k == 'beam':
        delay = mv['delay']
    elif k in ('rush', 'charge'):
        delay = dist / max(1.0, mv['speed'])
    else:
        delay = 0.0
    p = tp + flat(t.vel) * delay * random.uniform(*lead)
    d = p - here
    ang = math.atan2(d.x, d.z) + math.radians(random.uniform(-err, err))
    r = d.length()
    return here + Vec3(math.sin(ang) * r, 0, math.cos(ang) * r)


def worth_casting(brain, mv, t, d):
    """Vrai si l'IA a intérêt à lancer cette attaque maintenant sur la cible t (distance d)."""
    u, m = brain.u, brain.m
    k = mv['kind']
    rng = kit.cast_range(mv)
    ult = mv['slot'] == 'ult'
    if k == 'heal':
        return any(a.alive and a.hp < a.max_hp * .65 and (flat(a.position - u.position)).length() < mv['radius']
                   for a in m.team_units.get(u.team, ()))
    if t is None:
        return False
    if ult and t.kind != 'pokemon':
        return t.kind == 'neutral' and t.max_hp > 2000 and t.hp_ratio() > .3     # ultime sur un boss seulement
    if k in ('spin', 'wave'):
        ok = d < mv['radius'] * .85
    elif k == 'nova':
        ok = d < 9
    elif k == 'beam':
        ok = d < mv['length'] * .9
    elif k in ('rush', 'charge'):
        ok = 2.5 < d < rng * 1.1 or (d < 2.5 and k == 'rush')
    elif k == 'blink':
        ok = 3 < d < rng + mv['radius']
    else:
        ok = d < rng + mv.get('radius', 1)
    if not ok:
        return False
    if ult:
        weak = t.hp_ratio() < .5 or len(m.enemies_near(u, t.position, 6)) >= 2
        return weak or u.hp_ratio() < .35
    return True
