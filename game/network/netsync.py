"""Synchronisation d'une partie à deux joueurs.

Hôte (HostSync)
  - fait tourner toute la simulation (IA, dégâts, captures, score), comme en solo ;
  - reçoit la position du Pokémon de l'invité (qui se déplace chez lui sans attendre le
    réseau) et ses attaques (touche + cible + direction), qu'il exécute ;
  - envoie 20 fois par seconde un état compact du monde (~1 Ko, UDP) et, à chaque
    image, la liste des événements visibles (tirs, zones, dégâts, messages) par TCP.

Invité (ClientSync)
  - ne simule pas l'IA : il affiche les Pokémon aux positions reçues, avec un léger
    retard (NET['interp_delay']) pour les faire glisser en douceur entre deux paquets ;
  - rejoue les tirs et effets reçus pour l'affichage seulement (sans dégâts) ;
  - déplace son propre Pokémon localement : aucune latence sur les déplacements.
"""
import math
import struct
import time

from ursina import Vec3, color

from game import config as C
from game.world import fx
from game.pokemon.combat import Beam, Projectile, Wave, Zone, heal_fx

# ---------------------------------------------------------------- format des paquets
HEAD = struct.Struct('<IdB')          # numéro, horloge de l'hôte, contient l'état général ?
WORLD = struct.Struct('<fffB')        # temps de jeu, score rouge, score bleu, fin de partie
ARENA = struct.Struct('<hBB')         # contrôle (x10000), propriétaire, contestée
HUMAN = struct.Struct('<Hff4f')       # joueur humain : n°, XP, réapparition, 4 bonus
UNIT = struct.Struct('<HhhHHBH')      # n°, x, z, orientation, PV, niveau, drapeaux
PSTATE = struct.Struct('<IHhhHB')     # invité -> hôte : numéro, vie, x, z, orientation, drapeaux
COUNT = struct.Struct('<H')
POS = 64.0                            # précision des positions : 1/64 d'unité
ROT = 65536 / 360                     # orientation = rotation_y d'Ursina (= -cap de Panda3D)
PER_PACKET = 80                       # unités par paquet (reste sous ~1100 octets)
OWNER = {None: 0, 'rouge': 1, 'bleu': 2}
OWNER_KEY = {0: None, 1: 'rouge', 2: 'bleu'}
BUFFS = ('braise', 'flux', 'bastion', 'psy')
ALIVE, ENABLED, VISIBLE, MOVING, ATTACK, CHARGE, STUN, BURN, SLOW = (1 << i for i in range(9))


def _num(v, lim=C.FIELD_RADIUS + 10):
    """Nombre reçu de l'invité : fini et borné (sinon ValueError, le message est ignoré)."""
    v = float(v)
    if not math.isfinite(v):
        raise ValueError
    return max(-lim, min(lim, v))


def col_in(c):
    return color.rgba(*c)


def _q(v):
    return max(-32767, min(32767, int(round(v * POS))))


def unit_record(u):
    c = u.creature
    f = 0
    if u.alive:
        f |= ALIVE
    if c.enabled:
        f |= ENABLED
    if c.visible:
        f |= VISIBLE
    if u.moving:
        f |= MOVING
    if u.attack_anim > 0 or u.channel > 0:
        f |= ATTACK
    if u.charge_t > 0:
        f |= CHARGE
    st = u.status
    if st['stun'] > 0:
        f |= STUN
    if st['burn'] > 0:
        f |= BURN
    if st['slow'] > 0:
        f |= SLOW
    return (_q(c.get_x()), _q(c.get_z()), int((-c.get_h() % 360) * ROT) & 0xFFFF,
            max(0, min(65535, int(math.ceil(u.hp)))), u.level, f)


# ==================================================================== hôte
class HostSync:
    def __init__(self, match, host):
        self.m, self.host = match, host
        self.link = host.link
        self.events = []
        self.pid = 0
        self.seq = 0
        self.sent = {}
        self.t0 = time.perf_counter()
        self.next_snap = 0.0
        self.guest_ready = False              # l'invité a fini de charger la carte
        self.rtt = None                       # aller-retour réseau (ms)
        self.next_ping = 0.0

    def new_pid(self):
        self.pid += 1
        return self.pid

    def event(self, e):
        self.events.append(e)

    # ------------------------------------------------------------ réception
    def poll(self):
        if self.link is None:
            return
        for kind, data in self.link.poll():
            try:
                if kind == 'P':
                    self._guest_state(data)
                elif kind == 'msg':
                    self._message(data)
                elif kind == 'lost':
                    self._guest_left()
                    return
            except (TypeError, ValueError, KeyError, IndexError, struct.error):
                pass                          # message malformé : ignoré

    def _message(self, msg):
        t = msg.get('t')
        r = self.m.remote
        if t == 'loaded':
            self.guest_ready = True
        elif t == 'use' and r is not None and r.alive:
            p = msg.get('p')
            if p:
                r.brain.receive(r.brain.life, _num(p[0]), _num(p[1]), r.brain.net_rot, r.brain.net_moving)
                r.brain.follow(1.0)           # l'attaque part d'où l'invité l'a lancée
            d = msg.get('d') or (0, 0)
            r.brain.remote_use(str(msg.get('k')), int(msg.get('tg', -1)), _num(d[0], 1), _num(d[1], 1))
        elif t == 'dash' and r is not None:
            r.brain.remote_dash()
        elif t == 'pong':
            self.rtt = int((time.perf_counter() - float(msg.get('c'))) * 1000)
        elif t == 'restart' and self.m.state == 'end':
            self.m.restart()
        elif t == 'leave':
            self._guest_left()

    def _guest_state(self, data):
        r = self.m.remote
        if r is None:
            return
        seq, life, x, z, rot, flags = PSTATE.unpack(data)
        if seq <= getattr(self, '_pseq', -1):
            return                            # paquet arrivé en retard
        self._pseq = seq
        r.brain.receive(life, x / POS, z / POS, rot / ROT, bool(flags & 1))

    def _guest_left(self):
        if self.link is not None:
            self.link.close()
        self.link = None
        self.guest_ready = True
        self.m.guest_left()

    # ------------------------------------------------------------ envoi
    def flush(self):
        if self.link is None:
            self.events = []
            return
        if self.events:
            self.link.send({'t': 'ev', 'e': self.events})
            self.events = []
        now = time.perf_counter()
        if now >= self.next_snap:
            self.next_snap = max(self.next_snap + 1 / C.NET['snapshot_rate'], now)
            self._send_snapshot(now)
        if now >= self.next_ping:
            self.next_ping = now + 2.0
            self.link.send({'t': 'ping', 'c': now, 'rtt': self.rtt})

    def _send_snapshot(self, now):
        m = self.m
        self.seq += 1
        seq = self.seq
        world = [WORLD.pack(m.time, m.score['rouge'], m.score['bleu'], 1 if m.state == 'end' else 0)]
        for a in m.arenas:
            world.append(ARENA.pack(int(a['control'] * 10000), OWNER[a['owner']], 1 if a['contested'] else 0))
        camps = m.camps + list(m.bosses.values())
        bits = bytearray((len(camps) + 7) // 8)
        for i, camp in enumerate(camps):
            if camp['alive']:
                bits[i >> 3] |= 1 << (i & 7)
        world.append(bytes(bits))
        world.append(bytes([len(m.humans)]))
        for h in m.humans:
            world.append(HUMAN.pack(h.uid, h.xp, max(0.0, h.respawn_t), *(max(0.0, h.buffs.get(b, 0.0)) for b in BUFFS)))
        records = []
        for u in m.units:
            r = unit_record(u)
            if self.sent.get(u.uid) != r or (seq + u.uid) % 10 == 0:   # changé, ou rappel régulier
                self.sent[u.uid] = r
                records.append(UNIT.pack(u.uid, *r))
        clock = now - self.t0
        parts = [records[i:i + PER_PACKET] for i in range(0, len(records), PER_PACKET)] or [[]]
        for i, part in enumerate(parts):
            data = HEAD.pack(seq, clock, 1 if i == 0 else 0)
            if i == 0:
                data += b''.join(world)
            data += COUNT.pack(len(part)) + b''.join(part)
            self.link.send_bin(b'S', data)

    def close(self):
        """Fin de partie côté hôte : prévient l'invité et ferme la partie hébergée."""
        if self.link is not None and not self.link.closed:
            self.link.send({'t': 'bye'})
        self.link = None
        self.host.close()


# ==================================================================== invité
class ClientSync:
    def __init__(self, match, link):
        self.m, self.link = match, link
        self.offset = None                    # horloge de l'hôte - horloge locale
        self.world_seq = -1
        self.projs = {}
        self.active = set()                   # unités en cours de glissement
        self.seq = 0
        self.life = 0
        self.next_send = 0.0
        self.lost = False
        self.delay = C.NET['interp_delay']
        self.rate = C.NET['snapshot_rate']
        self.loaded_sent = False
        self.rtt = None

    def unit(self, uid):
        units = self.m.units
        return units[uid] if isinstance(uid, int) and 0 <= uid < len(units) else None

    # ------------------------------------------------------------ envoi
    def send_use(self, key, target, d):
        p = self.m.player.position
        self.link.send({'t': 'use', 'k': key, 'tg': target.uid if target is not None else -1,
                        'd': [round(d.x, 3), round(d.z, 3)], 'p': [round(p.x, 3), round(p.z, 3)]})

    def send_dash(self):
        self.link.send({'t': 'dash'})

    def request_restart(self):
        self.link.send({'t': 'restart'})

    def loaded(self):
        if not self.loaded_sent:
            self.loaded_sent = True
            self.link.send({'t': 'loaded'})

    def flush(self):
        if self.lost:
            return
        now = time.perf_counter()
        if now < self.next_send:
            return
        self.next_send = max(self.next_send + 1 / C.NET['input_rate'], now)
        u = self.m.player
        c = u.creature
        self.seq += 1
        flags = 1 if u.moving else 0
        self.link.send_bin(b'P', PSTATE.pack(self.seq, self.life, _q(c.get_x()), _q(c.get_z()),
                                             int((-c.get_h() % 360) * ROT) & 0xFFFF, flags))

    # ------------------------------------------------------------ réception
    def poll(self):
        if self.lost:
            return
        for kind, data in self.link.poll():
            try:
                if kind == 'S':
                    self._snapshot(data)
                elif kind == 'msg':
                    if data.get('t') == 'ev':
                        for e in data.get('e', ()):
                            self._event(e)
                    elif data.get('t') == 'ping':
                        self.link.send({'t': 'pong', 'c': data.get('c')})
                        self.rtt = data.get('rtt')
                    elif data.get('t') == 'bye':
                        self._lost()
                        return
                elif kind == 'lost':
                    self._lost()
                    return
            except (TypeError, ValueError, KeyError, IndexError, struct.error):
                pass                          # message malformé : ignoré

    def _lost(self):
        self.lost = True
        self.link.close()
        self.m.connection_lost()

    def _snapshot(self, data):
        seq, clock, has_world = HEAD.unpack_from(data, 0)
        off = HEAD.size
        now = time.perf_counter()
        sample = clock - now
        if self.offset is None:
            self.offset = sample
        elif sample > self.offset:            # paquet arrivé vite : on rattrape vite
            self.offset += (sample - self.offset) * .5
        else:                                 # paquet retardé : on n'en tient compte que lentement
            self.offset += (sample - self.offset) * .02
        m = self.m
        if has_world:
            t, sr, sb, end = WORLD.unpack_from(data, off)
            off += WORLD.size
            arenas = []
            for _ in m.arenas:
                arenas.append(ARENA.unpack_from(data, off))
                off += ARENA.size
            camps = m.camps + list(m.bosses.values())
            nbits = (len(camps) + 7) // 8
            bits = data[off:off + nbits]
            off += nbits
            nh = data[off]
            off += 1
            humans = []
            for _ in range(nh):
                humans.append(HUMAN.unpack_from(data, off))
                off += HUMAN.size
            if seq > self.world_seq:
                self.world_seq = seq
                for i, camp in enumerate(camps):
                    camp['alive'] = bool(bits[i >> 3] & (1 << (i & 7)))
                for uid, xp, respawn_t, *buffs in humans:
                    h = self.unit(uid)
                    if h is not None:
                        h.xp, h.respawn_t = xp, respawn_t
                        h.buffs = {b: v for b, v in zip(BUFFS, buffs) if v > 0}
                m.apply_world(t, sr, sb, end, [(c / 10000, OWNER_KEY.get(o), bool(k)) for c, o, k in arenas])
        n = COUNT.unpack_from(data, off)[0]
        off += COUNT.size
        for _ in range(n):
            uid, x, z, rot, hp, level, flags = UNIT.unpack_from(data, off)
            off += UNIT.size
            u = self.unit(uid)
            if u is None or seq <= getattr(u, 'net_seq', -1):
                continue
            u.net_seq = seq
            self._apply_unit(u, clock, x / POS, z / POS, rot / ROT, hp, level, flags)

    def _apply_unit(self, u, clock, x, z, rot, hp, level, flags):
        alive = bool(flags & ALIVE)
        local = u is self.m.player
        if u.alive and not alive:                                  # mis K.O.
            u.alive = False
            u.hp = 0
            u.charge_t = 0
            u._refresh_bar()
            u.creature.knock_out()
        elif alive and not u.alive and not local:                  # réapparition
            u.reset(pos=Vec3(x, 0, z))
            u.creature.set_h(-rot)
            u.net_buf = [(clock, x, z, rot)]
        if level != u.level:
            up = level > u.level
            u.level = level
            if up and u.alive:
                u.level_fx()
        if hp != int(math.ceil(u.hp)):
            u.hp = hp
            u._refresh_bar()
        c = u.creature
        if c.enabled != bool(flags & ENABLED):
            c.enabled = bool(flags & ENABLED)
        if c.visible != bool(flags & VISIBLE):
            c.visible = bool(flags & VISIBLE)
        st = u.status
        st['stun'] = .3 if flags & STUN else 0.0
        st['burn'] = .3 if flags & BURN else 0.0
        st['slow'] = .3 if flags & SLOW else 0.0
        if local:
            return                             # position : c'est l'invité qui la décide
        u.moving = bool(flags & MOVING)
        if flags & ATTACK:
            u.attack_anim = .12
        u.charge_t = 1.0 if flags & CHARGE else 0.0
        if not u.alive:
            return
        buf = getattr(u, 'net_buf', None)
        if not buf:
            u.net_buf = [(clock, x, z, rot)]
        else:
            last = buf[-1]
            if clock <= last[0]:
                return
            if (x - last[1]) ** 2 + (z - last[2]) ** 2 > 100:        # téléportation : pas de glissement
                buf[:] = [(clock, x, z, rot)]
            else:
                if clock - last[0] > 1.5 / self.rate:               # était immobile : départ juste avant
                    buf.append((clock - 1 / self.rate, last[1], last[2], last[3]))
                buf.append((clock, x, z, rot))
                if len(buf) > 10:
                    del buf[:-10]
        self.active.add(u)

    # ------------------------------------------------------------ affichage
    def render(self):
        """Place les Pokémon des autres joueurs/IA entre les deux états reçus qui encadrent
        l'instant affiché (légèrement dans le passé)."""
        if self.offset is None or not self.active:
            return
        rt = time.perf_counter() + self.offset - self.delay
        wy = self.m.stadium.walk_y
        done = []
        for u in self.active:
            buf = u.net_buf
            if rt >= buf[-1][0]:
                _, x, z, r = buf[-1]
                del buf[:-1]
                done.append(u)
            elif rt <= buf[0][0]:
                _, x, z, r = buf[0]
            else:
                i = 0
                while buf[i + 1][0] <= rt:
                    i += 1
                if i:
                    del buf[:i]
                t0, x0, z0, r0 = buf[0]
                t1, x1, z1, r1 = buf[1]
                k = (rt - t0) / (t1 - t0)
                x, z = x0 + (x1 - x0) * k, z0 + (z1 - z0) * k
                r = r0 + ((r1 - r0 + 180) % 360 - 180) * k
            c = u.creature
            c.set_pos(x, wy(x, z), z)
            c.set_h(-r)
        for u in done:
            self.active.discard(u)

    # ------------------------------------------------------------ événements
    def _event(self, e):
        kind, m = e[0], self.m
        if kind == 'proj':
            _, pid, owner, pos, vel, size, col, shape, homing, turn, life = e
            o = self.unit(owner)
            if o is not None:
                p = Projectile(m, o, Vec3(*pos), Vec3(*vel), 0, size, col_in(col), shape=shape,
                               homing=self.unit(homing), turn=turn, life=life, pid=pid)
                m.projectiles.append(p)
                self.projs[pid] = p
                if len(self.projs) > 300:
                    self.projs = {k: v for k, v in self.projs.items() if v.alive}
        elif kind == 'pk':
            p = self.projs.pop(e[1], None)
            if p is not None and p.alive:
                p.kill()
        elif kind == 'zone':
            _, owner, x, z, radius, delay, col, style = e
            o = self.unit(owner)
            if o is not None:
                m.hazards.append(Zone(m, o, Vec3(x, 0, z), radius, delay, 0, col_in(col), style=style))
        elif kind == 'wave':
            _, owner, x, z, speed, max_r, col, start = e
            o = self.unit(owner)
            if o is not None:
                m.hazards.append(Wave(m, o, Vec3(x, 0, z), speed, max_r, 0, col_in(col), start=start))
        elif kind == 'beam':
            _, owner, ox, oz, dx, dz, length, width, delay, col = e
            o = self.unit(owner)
            if o is not None:
                m.hazards.append(Beam(m, o, Vec3(ox, 0, oz), Vec3(dx, 0, dz), length, width, delay, 0, col_in(col)))
        elif kind == 'healfx':
            o = self.unit(e[1])
            if o is not None:
                heal_fx(m, o, e[2], col_in(e[3]))
        elif kind == 'anim':
            o = self.unit(e[1])
            if o is None or (o is m.player and e[2] == 'spin'):      # déjà joué localement
                return
            if e[2] == 'spin':
                o.spin()
            elif e[2] == 'pulse':
                o.pulse()
        elif kind == 'hit':
            tgt, src = self.unit(e[1]), self.unit(e[4])
            if tgt is not None:
                m.show_hit(tgt, int(e[2]), int(e[3]), src)
        elif kind == 'cast':
            o = self.unit(e[1])
            if o is not None and o is not m.player:
                m.announce_cast(o, str(e[2]))
        elif kind == 'burst':
            _, x, y, z, col, n, speed, size = e
            fx.burst(None, Vec3(x, y, z), col_in(col), n=n, speed=speed, size=size)
        elif kind == 'feed':
            m.feed.push(str(e[1]), col_in(e[2]))
        elif kind == 'ban':
            m.game.banner.show(str(e[1]), e[2], text_color=col_in(e[3]), big=bool(e[4]))
        elif kind == 'tp':
            _, uid, x, z, n = e
            if self.unit(uid) is m.player:
                self.life = n
                m.teleport_local(Vec3(x, 0, z))
        elif kind == 'restart':
            m.restart_view()

    def close(self):
        if not self.lost:
            self.link.send({'t': 'leave'})
            self.link.close()
