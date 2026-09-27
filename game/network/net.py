"""Connexion réseau du mode à deux joueurs (coopération) : hôte <-> invité.

Comment ça marche
-----------------
- L'hôte ouvre un port (NET['port'], TCP + UDP) et affiche un code d'invitation qui
  contient son adresse et une clé secrète tirée au hasard. L'UPnP demande à la box
  d'ouvrir ce port toute seule.
- L'invité colle ce code dans le salon et se connecte en TCP. Il doit présenter la clé
  (message 'join') : quelqu'un qui trouve le port ouvert sans avoir le code est refusé,
  et une connexion qui ne se présente pas dans les JOIN_TIMEOUT secondes est coupée.
- TCP (fiable, dans l'ordre) : salon, événements de jeu (tirs, dégâts, messages...).
- UDP (rapide) : état du monde (hôte -> invité) et position de l'invité (invité -> hôte).
  Un paquet perdu est simplement remplacé par le suivant. Si l'UDP ne passe pas
  (pare-feu, tunnel TCP), tout passe automatiquement par TCP.
- Les messages sont en JSON ou en binaire (struct), jamais en pickle : un message reçu
  ne peut pas exécuter de code.
- Les sockets vivent dans des fils d'exécution séparés : le jeu relève les messages
  reçus à chaque image sans jamais attendre le réseau.
"""
import hashlib
import ipaddress
import json
import os
import queue
import re
import secrets
import socket
import struct
import threading
import time
import urllib.parse
import urllib.request
from xml.etree import ElementTree

from game import config as C
PROTOCOL = 1
UDP_MAGIC = b'PK'
MAX_FRAME = 1 << 20
CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ'     # 32 signes, sans 0/O ni 1/I
KEY_BITS = 20                  # clé secrète du code d'invitation (4 signes)
JOIN_TIMEOUT = 10.0            # secondes laissées à un invité pour se présenter avec la clé


# ==================================================================== outils
def game_version():
    """Empreinte du code du jeu. Les deux joueurs doivent avoir les mêmes fichiers (sinon
    la carte ou les règles diffèrent) ; seuls les réglages graphiques de config.py
    (QUALITY, taille de fenêtre, compteur d'images) peuvent différer."""
    h = hashlib.sha1()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))      # dossier game/
    files = sorted(os.path.relpath(os.path.join(d, n), root).replace(os.sep, '/')
                   for d, _, names in os.walk(root) for n in names if n.endswith('.py'))
    for name in files:
        with open(os.path.join(root, name), encoding='utf-8') as f:
            src = f.read().replace('\r\n', '\n')
        if name == 'config.py':
            src = re.sub(r'(?ms)^QUALITY = \{.*?^\}', '', src)
            src = re.sub(r'(?m)^(WINDOW_SIZE|SHOW_FPS) = .*$', '', src)
        h.update(name.encode())
        h.update(src.encode())
    return h.hexdigest()[:10]


def lan_ip():
    """Adresse de ce PC sur le réseau local (aucun paquet n'est envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def is_public(ip):
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return a.is_global and a not in ipaddress.ip_network('100.64.0.0/10')


def _encode(n, size):
    chars = []
    for _ in range(size):
        chars.append(CODE_ALPHABET[n & 31])
        n >>= 5
    return ''.join(reversed(chars))


def _decode(s):
    n = 0
    for ch in s:
        n = n * 32 + CODE_ALPHABET.index(ch)
    return n


def make_code(ip, port, key):
    """Code d'invitation (14 signes) : adresse IPv4, port et clé secrète de la partie."""
    n = (int.from_bytes(socket.inet_aton(ip) + struct.pack('>H', port), 'big') << KEY_BITS) | key
    s = _encode(n, 14)
    return f'{s[:5]}-{s[5:10]}-{s[10:]}'


def parse_code(text):
    """Code d'invitation, ou adresse directe suivie de la clé ('1.2.3.4:47650/ABCD')
    -> (hôte, port, clé)."""
    t = text.strip()
    if not t:
        raise ValueError('Collez le code donné par votre ami.')
    if '.' in t or ':' in t:
        addr, _, key = t.partition('/')
        key = key.strip().upper()
        if len(key) != 4 or any(ch not in CODE_ALPHABET for ch in key):
            raise ValueError("Il manque la clé de la partie (adresse/XXXX) : utilisez plutôt le code.")
        host, _, port = addr.rpartition(':') if ':' in addr else (addr, '', '')
        host = host.strip('[] ')
        try:
            port = int(port) if port else C.NET['port']
        except ValueError:
            raise ValueError('Adresse invalide.') from None
        if not host or not 0 < port < 65536:
            raise ValueError('Adresse invalide.')
        return host, port, _decode(key)
    s = re.sub(r'[^0-9A-Za-z]', '', t).upper()
    if len(s) != 14 or any(ch not in CODE_ALPHABET for ch in s):
        raise ValueError('Code invalide (format attendu : XXXXX-XXXXX-XXXX).')
    n = _decode(s)
    key = n & ((1 << KEY_BITS) - 1)
    b = (n >> KEY_BITS).to_bytes(6, 'big')
    return socket.inet_ntoa(b[:4]), struct.unpack('>H', b[4:])[0], key


def _udp_socket():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if hasattr(socket, 'SIO_UDP_CONNRESET'):      # Windows : ignorer les « port injoignable » ICMP
        try:
            s.ioctl(socket.SIO_UDP_CONNRESET, False)
        except (OSError, ValueError):
            pass
    return s


def _thread(target, *args):
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
    return t


# ==================================================================== UPnP
class UPnP:
    """Ouverture automatique d'un port sur la box (protocole UPnP IGD)."""

    def __init__(self):
        self.control = self.service = None
        self.mapped = []

    def discover(self, local_ip, timeout=2.5):
        msg = ('M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: "ssdp:discover"\r\n'
               'MX: 2\r\nST: {}\r\n\r\n')
        targets = ['urn:schemas-upnp-org:device:InternetGatewayDevice:1',
                   'urn:schemas-upnp-org:device:InternetGatewayDevice:2',
                   'urn:schemas-upnp-org:service:WANIPConnection:1',
                   'urn:schemas-upnp-org:service:WANPPPConnection:1']
        s = _udp_socket()
        s.settimeout(.4)
        try:
            try:
                s.bind((local_ip, 0))
            except OSError:
                pass
            for st in targets:
                s.sendto(msg.format(st).encode(), ('239.255.255.250', 1900))
            locations, end = [], time.time() + timeout
            while time.time() < end:
                try:
                    data, _ = s.recvfrom(4096)
                except (socket.timeout, ConnectionResetError):
                    continue
                m = re.search(rb'(?im)^location:\s*(\S+)', data)
                loc = m.group(1).decode('latin-1') if m else ''
                # seulement une adresse web de la box (jamais file:// ou autre)
                if loc.lower().startswith(('http://', 'https://')) and loc not in locations:
                    locations.append(loc)
        finally:
            s.close()
        return any(self._read_description(loc) for loc in locations)

    def _read_description(self, loc):
        try:
            root = ElementTree.fromstring(urllib.request.urlopen(loc, timeout=3).read())
        except Exception:
            return False

        def child(node, name):
            for c in node:
                if c.tag.split('}')[-1] == name:
                    return (c.text or '').strip()
            return ''
        base = child(root, 'URLBase') or loc
        for node in root.iter():
            if node.tag.split('}')[-1] != 'service':
                continue
            stype = child(node, 'serviceType')
            if 'WANIPConnection' in stype or 'WANPPPConnection' in stype:
                control = urllib.parse.urljoin(base, child(node, 'controlURL'))
                if not control.lower().startswith(('http://', 'https://')):
                    continue
                self.service = stype
                self.control = control
                return True
        return False

    def _soap(self, action, args=()):
        body = ''.join(f'<{k}>{v}</{k}>' for k, v in args)
        env = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
               's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
               f'<u:{action} xmlns:u="{self.service}">{body}</u:{action}></s:Body></s:Envelope>')
        req = urllib.request.Request(self.control, data=env.encode(), headers={
            'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': f'"{self.service}#{action}"'})
        return urllib.request.urlopen(req, timeout=4).read()

    def external_ip(self):
        m = re.search(rb'<NewExternalIPAddress>([^<]*)<', self._soap('GetExternalIPAddress'))
        return m.group(1).decode().strip() if m else None

    def add(self, port, proto, local_ip):
        for lease in (6 * 3600, 0):            # certaines box n'acceptent que les ouvertures permanentes
            try:
                self._soap('AddPortMapping', [
                    ('NewRemoteHost', ''), ('NewExternalPort', port), ('NewProtocol', proto),
                    ('NewInternalPort', port), ('NewInternalClient', local_ip), ('NewEnabled', 1),
                    ('NewPortMappingDescription', 'Pokemon Dominion'), ('NewLeaseDuration', lease)])
                self.mapped.append((port, proto))
                return True
            except Exception:
                continue
        return False

    def remove_all(self):
        for port, proto in self.mapped:
            try:
                self._soap('DeletePortMapping', [('NewRemoteHost', ''), ('NewExternalPort', port),
                                                 ('NewProtocol', proto)])
            except Exception:
                pass
        self.mapped = []


# ==================================================================== liaison
class Link:
    """Connexion établie avec l'autre joueur (même fonctionnement chez l'hôte et l'invité).

    Messages reçus (relevés par poll()) :
      ('msg', dict)   message JSON
      ('S', bytes)    état du monde (hôte -> invité)
      ('P', bytes)    position de l'invité (invité -> hôte)
      ('lost', None)  connexion perdue
    """

    def __init__(self, tcp, udp, role, token=None, udp_peer=None):
        self.tcp, self.udp, self.role = tcp, udp, role
        self.token = token
        self.udp_peer = udp_peer
        self.udp_ok = False               # l'UDP passe dans les deux sens
        self.closed = False
        self.inbox = queue.SimpleQueue()
        self._out = queue.SimpleQueue()
        tcp.settimeout(None)
        tcp.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        _thread(self._read_tcp)
        self._writer = _thread(self._write_tcp)
        if role == 'guest':
            _thread(self._read_udp)

    # ------------------------------------------------------------ envoi
    def send(self, msg):
        self._frame(b'J', json.dumps(msg, separators=(',', ':'), ensure_ascii=False).encode())

    def send_bin(self, kind, data):
        """Paquet fréquent (b'S' ou b'P') : par UDP si possible, sinon par TCP."""
        if self.udp_ok and self.udp_peer is not None and self.token:
            try:
                self.udp.sendto(UDP_MAGIC + kind + self.token + data, self.udp_peer)
                return
            except OSError:
                pass
        self._frame(kind, data)

    def _frame(self, kind, payload):
        if not self.closed:
            self._out.put(struct.pack('>I', len(payload) + 1) + kind + payload)

    def _write_tcp(self):
        while True:
            data = self._out.get()
            if data is None:
                return
            try:
                self.tcp.sendall(data)
            except OSError:
                self._lost()
                return

    # ------------------------------------------------------------ réception
    def poll(self):
        items = []
        while True:
            try:
                items.append(self.inbox.get_nowait())
            except queue.Empty:
                return items

    def _recv_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.tcp.recv(n - len(buf))
            if not chunk:
                raise ConnectionError
            buf += chunk
        return buf

    def _read_tcp(self):
        try:
            while True:
                n = struct.unpack('>I', self._recv_exact(4))[0]
                if not 1 <= n <= MAX_FRAME:
                    raise ConnectionError
                data = self._recv_exact(n)
                kind, payload = data[:1], data[1:]
                if kind != b'J':
                    self.inbox.put((kind.decode('latin-1'), payload))
                    continue
                msg = json.loads(payload.decode())
                if not isinstance(msg, dict):
                    continue
                t = msg.get('t')
                if t == 'udp_ok':
                    self.udp_ok = True
                    continue
                if t == 'hello' and self.role == 'guest':
                    try:
                        self.token = bytes.fromhex(msg.get('token', ''))[:4]
                    except ValueError:
                        self.token = None
                    if self.token:
                        _thread(self._probe_udp)
                self.inbox.put(('msg', msg))
        except (OSError, ConnectionError, ValueError, TypeError, struct.error):
            self._lost()

    def _lost(self):
        if not self.closed:
            self.closed = True
            self.inbox.put(('lost', None))
            self._out.put(None)

    # ------------------------------------------------------------ UDP
    def _probe_udp(self):
        """Invité : envoie quelques « bonjour » UDP jusqu'à ce que l'hôte réponde."""
        for _ in range(20):
            if self.udp_ok or self.closed:
                return
            try:
                self.udp.sendto(UDP_MAGIC + b'H' + self.token, self.udp_peer)
            except OSError:
                pass
            time.sleep(.25)

    def _read_udp(self):
        """Invité : paquets UDP de l'hôte."""
        while not self.closed:
            try:
                data, addr = self.udp.recvfrom(65536)
            except (ConnectionResetError, socket.timeout):
                continue
            except OSError:
                return
            if len(data) < 7 or data[:2] != UDP_MAGIC or data[3:7] != self.token:
                continue
            kind = data[2:3]
            if kind == b'A':
                if not self.udp_ok:
                    self.udp_ok = True
                    self.send({'t': 'udp_ok'})
            elif kind == b'S':
                self.inbox.put(('S', data[7:]))

    def host_udp(self, kind, data, addr):
        """Hôte : paquet UDP reçu de l'invité (relayé par Host)."""
        self.udp_peer = addr                      # suit un éventuel changement de port (box)
        if kind == b'H':
            for _ in range(3):
                try:
                    self.udp.sendto(UDP_MAGIC + b'A' + self.token, addr)
                except OSError:
                    pass
        elif kind == b'P':
            self.inbox.put(('P', data))

    def close(self):
        """Ferme la connexion après avoir laissé partir les derniers messages (0,3 s au plus)."""
        was_closed = self.closed
        self.closed = True
        self._out.put(None)
        if not was_closed and threading.current_thread() is not self._writer:
            self._writer.join(.3)
        try:
            self.tcp.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.tcp.close()
        except OSError:
            pass
        if self.role == 'guest':
            try:
                self.udp.close()
            except OSError:
                pass


# ==================================================================== hôte
class Host:
    """Partie hébergée : attend un invité et prépare le code d'invitation."""

    def __init__(self, port=None):
        port = port or C.NET['port']
        self.token = secrets.token_bytes(4)
        self.key = secrets.randbelow(1 << KEY_BITS)   # clé secrète, contenue dans le code d'invitation
        self.closed = False
        self.link = None
        self.upnp = None
        for p in range(port, port + 10):          # port occupé : on essaie les suivants
            tcp, udp = socket.socket(socket.AF_INET, socket.SOCK_STREAM), _udp_socket()
            try:
                tcp.bind(('', p))
                udp.bind(('', p))
                break
            except OSError:
                tcp.close()
                udp.close()
        else:
            raise OSError(f'Ports {port} à {port + 9} déjà utilisés.')
        tcp.listen(2)
        self.tcp, self.udp, self.port = tcp, udp, p
        self.info = {'lan': lan_ip(), 'public': None, 'upnp': None, 'status': 'Recherche de la box...'}
        _thread(self._accept)
        _thread(self._read_udp)
        _thread(self._open_internet)

    @property
    def lan_code(self):
        return make_code(self.info['lan'], self.port, self.key)

    @property
    def public_code(self):
        ip = self.info['public']
        return make_code(ip, self.port, self.key) if ip else None

    def _open_internet(self):
        """Ouvre le port sur la box (UPnP) et trouve l'adresse publique."""
        info, local = self.info, self.info['lan']
        ext = None
        if C.NET.get('upnp', True):
            try:
                u = UPnP()
                if u.discover(local):
                    ok = u.add(self.port, 'TCP', local) and u.add(self.port, 'UDP', local)
                    self.upnp = u
                    info['upnp'] = ok
                    try:
                        ext = u.external_ip()
                    except Exception:
                        ext = None
                else:
                    info['upnp'] = False
            except Exception:
                info['upnp'] = False
        if self.closed:
            if self.upnp:
                self.upnp.remove_all()
            return
        if ext and not is_public(ext):
            # box elle-même derrière un NAT de l'opérateur : l'ouverture ne sert à rien
            info['status'] = ("Votre box n'a pas d'adresse publique (CGNAT) : jouez en réseau local "
                              "ou via un VPN (Radmin VPN, Tailscale...).")
            info['upnp'] = False
            ext = None
        if not ext:
            try:
                ext = urllib.request.urlopen('https://api.ipify.org', timeout=4).read().decode().strip()
                socket.inet_aton(ext)
            except Exception:
                ext = None
        info['public'] = ext
        if info['upnp']:
            info['status'] = 'Port ouvert automatiquement sur la box (UPnP).'
        elif not info['status'].startswith('Votre box'):
            info['status'] = (f"Ouverture auto impossible : ouvrez le port {self.port} (TCP et UDP) sur la box, "
                              "ou jouez en réseau local / via un VPN.")

    def _accept(self):
        while not self.closed:
            try:
                conn, addr = self.tcp.accept()
            except OSError:
                return
            if self.link is not None and not self.link.closed:
                try:                                   # déjà deux joueurs
                    data = json.dumps({'t': 'full'}).encode()
                    conn.sendall(struct.pack('>I', len(data) + 1) + b'J' + data)
                    conn.close()
                except OSError:
                    pass
                continue
            link = Link(conn, self.udp, 'host', token=self.token)
            link.since = time.time()             # doit se présenter avec la clé avant JOIN_TIMEOUT
            link.joined = False
            link.send({'t': 'hello', 'proto': PROTOCOL, 'version': game_version(), 'token': self.token.hex()})
            self.link = link

    def _read_udp(self):
        while not self.closed:
            try:
                data, addr = self.udp.recvfrom(65536)
            except (ConnectionResetError, socket.timeout):
                continue
            except OSError:
                return
            link = self.link
            if link is None or link.closed or len(data) < 7 or data[:2] != UDP_MAGIC or data[3:7] != self.token:
                continue
            link.host_udp(data[2:3], data[7:], addr)

    def check_key(self, key):
        return isinstance(key, int) and key == self.key

    def drop_link(self):
        if self.link is not None:
            self.link.close()
            self.link = None

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.drop_link()
        for s in (self.tcp, self.udp):
            try:
                s.close()
            except OSError:
                pass
        if self.upnp is not None:                 # refermer le port de la box (sans bloquer le jeu)
            t = _thread(self.upnp.remove_all)
            t.join(1.5)


# ==================================================================== invité
class Guest:
    """Connexion en cours vers un hôte. `state` : 'connecting', 'connected' ou 'error'."""

    def __init__(self, code):
        self.state, self.error, self.link = 'connecting', None, None
        try:
            self.host, self.port, self.key = parse_code(code)
        except ValueError as e:
            self.state, self.error = 'error', str(e)
            return
        _thread(self._connect)

    def _connect(self):
        try:
            ip = socket.gethostbyname(self.host)
            tcp = socket.create_connection((ip, self.port), timeout=6)
        except socket.timeout:
            self.state, self.error = 'error', "Pas de réponse de l'hôte : port fermé sur sa box ou mauvais code."
            return
        except ConnectionRefusedError:
            self.state, self.error = 'error', "L'hôte refuse la connexion : sa partie est-elle ouverte ?"
            return
        except OSError as e:
            self.state, self.error = 'error', f'Connexion impossible ({e.strerror or e}).'
            return
        udp = _udp_socket()
        udp.bind(('', 0))
        self.link = Link(tcp, udp, 'guest', udp_peer=(ip, self.port))
        self.state = 'connected'

    def close(self):
        if self.link is not None:
            self.link.close()
