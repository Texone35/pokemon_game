"""Effets visuels : particules, attaques par type, éclairs, météo des arènes.

Particules : toutes les particules d'une partie tiennent dans deux gros maillages recalculés à
chaque image avec numpy (un pour les lueurs qui s'additionnent : feu, étincelles, éclairs ;
un pour les particules opaques : fumée, poussière, gouttes, feuilles). Deux appels de rendu
seulement, quel que soit leur nombre : on peut en mettre beaucoup sans ralentir.

Chaque particule a une texture (lueur, fumée, anneau, étoile, feuille, éclat, goutte, trait),
une couleur de départ et d'arrivée (le feu passe du jaune au rouge puis à la fumée), une
orientation (face à la caméra, étirée dans le sens de sa vitesse, ou posée à plat au sol) et
une physique simple (gravité, freinage).

Les effets suivent le découpage classique des jeux : annonce (anticipation), impact bref et
contrasté, puis dissipation discrète (voir trail / impact / explosion).
"""
import math
import random

import numpy as np
from ursina import Vec3, color

from game.world.geometry import MeshBuilder


def ring_mesh(parent, col, emissive=.8):
    return MeshBuilder().add('ring_thin', (0, 0, 0), (1, .5, 1), col=col).entity(parent=parent, emissive=emissive)


def orient(e, v):
    """Tourne l'entité dans la direction v."""
    if v.length() > 1e-4:
        e.rotation = Vec3(-math.degrees(math.atan2(v.y, math.hypot(v.x, v.z))), math.degrees(math.atan2(v.x, v.z)), 0)


def blob(parent, col, scale, glow, prim='sphere_lo'):
    """Petit élément animé : nœud Panda3D nu (bien plus léger qu'une entité Ursina)."""
    node = MeshBuilder().add(prim, (0, 0, 0), 1, col=color.white).static(parent, emissive=glow, col=col)
    node.set_scale(*(scale if isinstance(scale, (tuple, list)) else (scale,) * 3))
    return node


# ==================================================================== halos (projectiles)
_GLOW_TEX = None
_QUAD = None


def glow_texture():
    """Texture ronde : blanche au centre, transparente sur les bords."""
    global _GLOW_TEX
    if _GLOW_TEX is None:
        from panda3d.core import PNMImage, Texture
        n = 64
        img = PNMImage(n, n, 4)
        for i in range(n):
            for j in range(n):
                r = math.hypot((i + .5) / n * 2 - 1, (j + .5) / n * 2 - 1)
                img.set_xel_a(i, j, 1, 1, 1, max(0.0, 1 - r) ** 1.7)
        tex = Texture('glow')
        tex.load(img)
        _GLOW_TEX = tex
    return _GLOW_TEX


def _quad():
    global _QUAD
    if _QUAD is None:
        from ursina import load_model
        _QUAD = load_model('quad', use_deepcopy=True)
        _QUAD.set_texture(glow_texture(), 1)
    return _QUAD


def _glow_state(node):
    from panda3d.core import ColorBlendAttrib, TransparencyAttrib
    node.set_transparency(TransparencyAttrib.M_alpha)
    node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                          ColorBlendAttrib.O_one))
    node.set_depth_write(False)
    # Ursina travaille en OpenGL moderne : il faut un shader (le sien, sans éclairage)
    from ursina import Vec2
    from ursina.shaders import unlit_shader
    if not unlit_shader.compiled:
        unlit_shader.compile()
    node.set_shader(unlit_shader._shader, 1)
    node.set_shader_input('texture_scale', Vec2(1, 1))
    node.set_shader_input('texture_offset', Vec2(0, 0))
    node.set_bin('fixed', 50)


def glow_sprite(parent, col, size):
    """Halo lumineux (toujours face à la caméra) attaché à `parent`."""
    node = _quad().copy_to(parent)
    node.set_billboard_point_eye()
    _glow_state(node)
    node.set_scale(size)
    node.set_color_scale(col[0], col[1], col[2], col[3] if len(col) > 3 else 1)
    return node


# ==================================================================== atlas des particules
TEX = {'glow': 0, 'smoke': 1, 'ring': 2, 'star': 3, 'leaf': 4, 'shard': 5, 'drop': 6, 'streak': 7}
_ATLAS = None


def _value_noise(n, cells, rng):
    g = rng.random((cells + 1, cells + 1))
    x = np.linspace(0, cells, n, endpoint=False)
    i = x.astype(int)
    f = x - i
    f = f * f * (3 - 2 * f)
    a = g[i][:, i] * (1 - f)[None, :] + g[i][:, i + 1] * f[None, :]
    b = g[i + 1][:, i] * (1 - f)[None, :] + g[i + 1][:, i + 1] * f[None, :]
    return a * (1 - f)[:, None] + b * f[:, None]


def atlas_texture():
    """Atlas 4 x 2 des formes de particules (blanches : la couleur vient de chaque particule)."""
    global _ATLAS
    if _ATLAS is None:
        from panda3d.core import SamplerState, Texture
        n = 128
        rng = np.random.default_rng(4)
        v, u = np.mgrid[0:n, 0:n]
        u = (u + .5) / n * 2 - 1
        v = (v + .5) / n * 2 - 1
        r = np.hypot(u, v)
        noise = (_value_noise(n, 5, rng) * .6 + _value_noise(n, 11, rng) * .4)
        cells = [
            np.clip(1 - r, 0, 1) ** 1.7,                                                     # lueur
            np.clip((1 - r) * 1.4, 0, 1) ** 1.3 * np.clip(.35 + noise * .9, 0, 1),           # fumée
            np.exp(-((r - .78) / .09) ** 2) * (r < 1),                                        # anneau
            np.clip(np.maximum(np.exp(-np.abs(u) * 16) * (1 - np.abs(v)), np.exp(-np.abs(v) * 16) * (1 - np.abs(u)))
                    + np.clip(1 - r, 0, 1) ** 3, 0, 1),                                        # étoile
            ((np.abs(u) < (1 - v ** 2) * .42) * np.clip(1 - np.abs(v) * .9, 0, 1)
             * np.where(np.abs(u) < .03, .7, 1.0)),                                            # feuille
            np.clip(1 - (np.abs(u) / .32 + np.abs(v)), 0, 1) ** .6,                           # éclat
            np.clip(1 - np.hypot(u / (.55 * np.clip(.4 - v, .05, 1.4) ** .5), v * .9 + .1), 0, 1) ** .8,   # goutte
            np.exp(-(u / .16) ** 2) * np.clip(1 - np.abs(v), 0, 1),                           # trait
        ]
        img = np.zeros((2 * n, 4 * n, 4), np.uint8)
        for k, a in enumerate(cells):
            row, col = k // 4, k % 4
            shade_ = (.8 + .2 * noise) if k == 1 else 1.0
            img[row * n:(row + 1) * n, col * n:(col + 1) * n, :3] = (255 * np.clip(shade_, 0, 1))[..., None] \
                if k == 1 else 255
            img[row * n:(row + 1) * n, col * n:(col + 1) * n, 3] = (np.clip(a, 0, 1) * 255).astype(np.uint8)
        tex = Texture('fx_atlas')
        tex.setup_2d_texture(4 * n, 2 * n, Texture.T_unsigned_byte, Texture.F_rgba8)
        bgra = img[..., [2, 1, 0, 3]]
        tex.set_ram_image(np.ascontiguousarray(bgra).tobytes())
        tex.set_wrap_u(SamplerState.WM_clamp)
        tex.set_wrap_v(SamplerState.WM_clamp)
        tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        tex.set_magfilter(SamplerState.FT_linear)
        _ATLAS = tex
    return _ATLAS


_FX_SHADER = None


def _fx_shader():
    global _FX_SHADER
    if _FX_SHADER is None:
        from panda3d.core import Shader
        _FX_SHADER = Shader.make(Shader.SL_GLSL, """#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
in vec4 p3d_Color;
in vec2 p3d_MultiTexCoord0;
out vec4 v_col;
out vec2 v_uv;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_col = p3d_Color;
    v_uv = p3d_MultiTexCoord0;
}
""", """#version 150
uniform sampler2D p3d_Texture0;
in vec4 v_col;
in vec2 v_uv;
out vec4 frag;
void main() {
    frag = texture(p3d_Texture0, v_uv) * v_col;
}
""")
    return _FX_SHADER


_CORNER_UV = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], np.float32) * np.array([.25, .5], np.float32)
MODES = {'bill': 0, 'stretch': 1, 'flat': 2}


# colonnes de l'état d'une particule (tableau compact : seules les particules vivantes, en tête)
_C = {'pos': slice(0, 3), 'vel': slice(3, 6), 'col0': slice(6, 10), 'col1': slice(10, 14), 'age': 14, 'life': 15,
      'size': 16, 'grow': 17, 'grav': 18, 'drag': 19, 'stretch': 20, 'spin': 21, 'rot': 22, 'fade': 23, 'mode': 24,
      'uv0': slice(25, 27)}
_NCOL = 27


class _Pool:
    """Une réserve de particules et son maillage (un seul appel de rendu). Les particules vivantes
    sont rangées en tête du tableau : on ne calcule et n'envoie à la carte graphique que celles-là."""

    def __init__(self, parent, cap, additive):
        from panda3d.core import (ColorBlendAttrib, Geom, GeomNode, GeomTriangles, GeomVertexArrayFormat,
                                  GeomVertexData, GeomVertexFormat, OmniBoundingVolume, TransparencyAttrib)
        self.cap = cap
        self.n = 0                  # particules vivantes
        self.drawn = 0              # quads envoyés à la carte graphique à l'image précédente
        self.S = np.zeros((cap, _NCOL), np.float32)
        self.additive = additive
        a = GeomVertexArrayFormat()
        a.add_column('vertex', 3, Geom.NT_float32, Geom.C_point)
        a.add_column('color', 4, Geom.NT_float32, Geom.C_color)
        a.add_column('texcoord', 2, Geom.NT_float32, Geom.C_texcoord)
        fmt = GeomVertexFormat.register_format(a)
        self.vdata = GeomVertexData('fx', fmt, Geom.UH_dynamic)
        self.vdata.unclean_set_num_rows(cap * 4)
        self.buf = np.zeros((cap, 4, 9), np.float32)
        self.vdata.modify_array_handle(0).copy_data_from(self.buf)
        prim = GeomTriangles(Geom.UH_static)
        prim.set_index_type(Geom.NT_uint32)
        q = np.arange(cap, dtype=np.uint32)[:, None] * 4
        idx = (q + np.array([0, 1, 2, 0, 2, 3], np.uint32)).ravel()
        arr = prim.modify_vertices()
        arr.unclean_set_num_rows(len(idx))
        arr.modify_handle().copy_data_from(idx)
        geom = Geom(self.vdata)
        geom.add_primitive(prim)
        node = GeomNode('fx_additive' if additive else 'fx_alpha')
        node.add_geom(geom)
        node.set_bounds(OmniBoundingVolume())
        node.set_final(True)
        self.np = parent.attach_new_node(node)
        self.np.set_shader(_fx_shader(), 10)
        self.np.set_texture(atlas_texture(), 10)
        self.np.set_depth_write(False)
        self.np.set_two_sided(True)
        self.np.set_light_off(10)
        self.np.set_transparency(TransparencyAttrib.M_alpha)
        if additive:
            self.np.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                                     ColorBlendAttrib.O_one))
            self.np.set_bin('fixed', 52)
        else:
            self.np.set_bin('fixed', 51)

    def emit(self, pos, col, col2, size, life, vel, grow, gravity, drag, alpha, tex, mode, stretch, spin, rot, fade):
        if self.n < self.cap:
            i = self.n
            self.n += 1
        else:                                      # réserve pleine : on remplace une particule au hasard
            i = random.randrange(self.cap)
        c2 = col2 if col2 is not None else col
        k = TEX[tex]
        self.S[i] = (pos[0], pos[1], pos[2], vel[0], vel[1], vel[2], col[0], col[1], col[2], alpha,
                     c2[0], c2[1], c2[2], alpha, 0.0, max(life, .01), size, grow, gravity, drag, stretch, spin,
                     random.uniform(0, math.tau) if rot is None else rot, fade, MODES[mode],
                     (k % 4) * .25, (k // 4) * .5)

    def update(self, dt, cam_pos, right, up):
        n = self.n
        if n:
            S = self.S[:n]
            S[:, 14] += dt
            keep = S[:, 14] < S[:, 15]
            if not keep.all():                     # on retire les mortes (compactage)
                S = S[keep]
                n = self.n = len(S)
                self.S[:n] = S
                S = self.S[:n]
        if n:
            vel = S[:, 3:6]
            vel[:, 1] -= S[:, 18] * dt
            vel *= np.clip(1 - S[:, 19] * dt, 0, 1)[:, None]
            S[:, 0:3] += vel * dt
            age, life = S[:, 14], S[:, 15]
            t = np.clip(age / life, 0, 1)
            half = (S[:, 16] * (1 + (S[:, 17] - 1) * t) * .5)[:, None]
            col = S[:, 6:10] + (S[:, 10:14] - S[:, 6:10]) * t[:, None]
            fin = np.clip(age / np.maximum(life * (.02 if self.additive else .12), 1e-3), 0, 1)
            col[:, 3] *= fin * (1 - t) ** S[:, 23]
            ang = S[:, 22] + S[:, 21] * age
            ca, sa = np.cos(ang)[:, None], np.sin(ang)[:, None]
            R = (right[None, :] * ca + up[None, :] * sa) * half
            U = (up[None, :] * ca - right[None, :] * sa) * half
            m = S[:, 24]
            st = m == 1
            if st.any():                           # étirées dans le sens de la vitesse
                v = vel[st]
                sp = np.linalg.norm(v, axis=1, keepdims=True)
                ax = np.where(sp > 1e-4, v / np.maximum(sp, 1e-4), up[None, :])
                side = np.cross(ax, S[st, 0:3] - cam_pos[None, :])
                side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-4)
                h = half[st]
                U[st] = ax * (h + sp * S[st, 20][:, None] * .5)
                R[st] = side * h * .7
            fl = m == 2
            if fl.any():                           # à plat sur le sol
                h = half[fl]
                c, s_ = ca[fl], sa[fl]
                zero = np.zeros_like(c)
                R[fl] = np.concatenate([c, zero, s_], 1) * h
                U[fl] = np.concatenate([-s_, zero, c], 1) * h
            p = S[:, 0:3]
            b = self.buf[:n]
            b[:, 0, :3] = p - R - U
            b[:, 1, :3] = p + R - U
            b[:, 2, :3] = p + R + U
            b[:, 3, :3] = p - R + U
            b[:, :, 3:7] = col[:, None, :]
            b[:, :, 7:9] = S[:, 25:27][:, None, :] + _CORNER_UV[None, :, :]
        top = max(n, self.drawn)
        if top:
            self.buf[n:top] = 0                    # les quads des particules mortes disparaissent
            nbytes = top * 4 * 9 * 4
            self.vdata.modify_array_handle(0).copy_subdata_from(0, nbytes, self.buf[:top], 0, nbytes)
        self.drawn = n

    @property
    def alive(self):
        """Masque des particules vivantes (pour les statistiques)."""
        return np.arange(self.cap) < self.n

    def clear(self):
        self.n = 0


class Particles:
    """Toutes les particules de la partie : lueurs additives et particules opaques (fumée...).
    Les éclairs (petits maillages éphémères) sont aussi gérés ici."""

    def __init__(self, parent, cap_add=2400, cap_alpha=2000):
        self.root = parent.attach_new_node('particles')
        self.add = _Pool(self.root, cap_add, True)
        self.alpha = _Pool(self.root, cap_alpha, False)
        self.transient = []                        # [nœud, temps restant]
        for kind in _BOLT_SPEC:                    # éclairs types construits dès le chargement
            _bolt_variants(kind)

    def emit(self, pos, col, size=.4, life=.5, vel=(0, 0, 0), grow=1.0, gravity=0.0, drag=0.0, alpha=1.0,
             col2=None, tex='glow', blend='add', mode='bill', stretch=0.0, spin=0.0, rot=None, fade=1.2):
        pool = self.add if blend == 'add' else self.alpha
        pool.emit(pos, col, col2, size, life, vel, grow, gravity, drag, alpha, tex, mode, stretch, spin, rot, fade)

    def keep(self, node, life):
        """Garde un nœud éphémère (éclair...) `life` secondes puis le supprime."""
        self.transient.append([node, life])

    def update(self, dt):
        from ursina import camera
        q = camera.get_quat(self.root)
        right, up = q.get_right(), q.get_up()
        cp = camera.get_pos(self.root)
        cam = np.array((cp[0], cp[1], cp[2]), np.float32)
        r = np.array((right[0], right[1], right[2]), np.float32)
        u = np.array((up[0], up[1], up[2]), np.float32)
        self.add.update(dt, cam, r, u)
        self.alpha.update(dt, cam, r, u)
        keep = []
        for item in self.transient:
            item[1] -= dt
            if item[1] <= 0:
                item[0].remove_node()
            else:
                keep.append(item)
        self.transient = keep

    def clear(self):
        self.add.clear()
        self.alpha.clear()
        for node, _ in self.transient:
            node.remove_node()
        self.transient = []


PARTICLES = None        # réserve globale, créée par la partie (Match)


def rnd(a=1.0):
    return random.uniform(-a, a)


def ru(a, b):
    return random.uniform(a, b)


# Apparence des attaques selon le type du Pokémon qui les lance.
FX_STYLE = {
    'feu': {'core': (1, .6, .15), 'trail': (1, .38, .05), 'hot': (1, .85, .3), 'gravity': -2.5, 'spread': .4},
    'eau': {'core': (.35, .7, 1), 'trail': (.55, .85, 1), 'hot': (.85, .95, 1), 'gravity': 7, 'spread': .5},
    'electrik': {'core': (1, .92, .3), 'trail': (1, 1, .55), 'hot': (1, 1, .9), 'gravity': 0, 'spread': 1.4},
    'plante': {'core': (.45, .95, .3), 'trail': (.55, 1, .35), 'hot': (.85, 1, .6), 'gravity': 1, 'spread': .5},
    'glace': {'core': (.7, .92, 1), 'trail': (.8, .96, 1), 'hot': (1, 1, 1), 'gravity': .5, 'spread': .4},
    'roche': {'core': (.8, .68, .5), 'trail': (.65, .56, .45), 'hot': (.95, .9, .8), 'gravity': 2, 'spread': .5},
    'psy': {'core': (.85, .45, 1), 'trail': (.9, .6, 1), 'hot': (1, .85, 1), 'gravity': -.5, 'spread': .8},
    'normal': {'core': (1, .95, .85), 'trail': (.95, .9, .8), 'hot': (1, 1, 1), 'gravity': 1, 'spread': .5},
    'combat': {'core': (1, .55, .3), 'trail': (1, .75, .5), 'hot': (1, .95, .8), 'gravity': 1, 'spread': .6},
    'spectre': {'core': (.55, .3, .85), 'trail': (.35, .2, .55), 'hot': (.85, .7, 1), 'gravity': -.5, 'spread': .7},
    'dragon': {'core': (.5, .45, 1), 'trail': (.4, .35, .95), 'hot': (.85, .85, 1), 'gravity': -1.5, 'spread': .6},
}


def style(type_key):
    return FX_STYLE.get(type_key, FX_STYLE['normal'])


# ==================================================================== briques d'effets
FIRE, FIRE_END = (1, .92, .55), (.85, .18, .03)
SMOKE, SMOKE_END = (.22, .2, .19), (.42, .4, .39)
WATER, MIST = (.78, .92, 1), (.85, .93, 1)
DUST = (.62, .54, .42)
LEAVES = [(.35, .72, .22), (.45, .82, .25), (.28, .6, .2), (.6, .85, .3)]


def flame(P, p, vel=(0, 0, 0), s=1.0, life=.45, rise=3.0):
    """Langue de feu : jaune orangé au départ, rouge sombre à la fin, qui monte ; un cœur lumineux
    (additif) sur une flamme sur deux. Le corps est opaque : il garde sa couleur même sur un sol clair
    au lieu de tourner au blanc."""
    lf = life * ru(.7, 1.2)
    P.emit(p, (1, .72, .22), col2=(.62, .1, .02), size=s * ru(.8, 1.2), life=lf, vel=vel, grow=1.5,
           gravity=-rise, drag=1.8, tex='smoke', blend='alpha', spin=rnd(2), alpha=.9, fade=1.4)
    if random.random() < .5:
        P.emit(p, (1, .8, .35), col2=(1, .3, .05), size=s * ru(.5, .8), life=lf * .6, vel=vel, grow=1.2,
               gravity=-rise, drag=1.8, tex='glow', alpha=.45)


def smoke(P, p, vel=(0, 1.2, 0), s=1.0, life=1.2, alpha=.45, col=SMOKE, col2=SMOKE_END):
    P.emit(p, col, col2=col2, size=s * ru(.8, 1.2), life=life * ru(.8, 1.2), vel=vel, grow=2.4, gravity=-.4,
           drag=1.2, tex='smoke', blend='alpha', spin=rnd(.8), alpha=alpha)


def spark(P, p, vel, col=(1, .9, .5), col2=(1, .45, .1), s=.14, life=.35, gravity=6.0, stretch=.045):
    P.emit(p, col, col2=col2, size=s, life=life * ru(.7, 1.2), vel=vel, gravity=gravity, drag=1.2,
           mode='stretch', stretch=stretch, fade=.8)


def droplet(P, p, vel, s=.2, life=.5, alpha=.85):
    P.emit(p, WATER, size=s * ru(.7, 1.2), life=life * ru(.8, 1.2), vel=vel, gravity=13, drag=.4, tex='drop',
           blend='alpha', mode='stretch', stretch=.035, alpha=alpha, fade=.6)


def ground_ring(P, p, col, r0, r1, life, alpha=.8, blend='add', width_tex='ring'):
    """Anneau à plat qui s'élargit de r0 à r1 (onde de choc, ride sur l'eau...)."""
    P.emit(p, col, size=2 * r0, life=life, grow=r1 / max(r0, .01), tex=width_tex, blend=blend, mode='flat',
           alpha=alpha, fade=1.0, rot=0)


def ground_glow(P, p, col, r, life, alpha=.6):
    """Lueur posée au sol : fausse lumière d'une explosion ou d'un éclair."""
    P.emit((p[0], p[1] + .08, p[2]), col, size=2 * r, life=life, grow=1.2, mode='flat', alpha=alpha, rot=0)


def leaf(P, p, vel, s=.35, life=.9, col=None):
    P.emit(p, col or random.choice(LEAVES), size=s * ru(.8, 1.2), life=life * ru(.8, 1.2), vel=vel, gravity=2.0,
           drag=1.5, tex='leaf', blend='alpha', spin=rnd(9), alpha=1.0, fade=.6)


def _v(x, y, z):
    return (x, y, z)


def trail(kind, p, vel, s):
    """Traînée d'un projectile (appelée ~40 fois par seconde près de la caméra)."""
    P = PARTICLES
    if P is None:
        return
    sp = vel.length() or 1
    bx, by, bz = -vel.x / sp, -vel.y / sp, -vel.z / sp
    if kind == 'feu':
        for _ in range(2):
            flame(P, (p.x + rnd(s * .3), p.y + rnd(s * .3), p.z + rnd(s * .3)),
                  _v(bx * 2 + rnd(.6), by * 2 + rnd(.4) + .5, bz * 2 + rnd(.6)), s=s * 2.2, life=.35)
        if random.random() < .35:
            smoke(P, (p.x, p.y + .2, p.z), _v(bx, 1.0, bz), s=s * 1.8, life=.8, alpha=.3)
    elif kind == 'eau':
        for _ in range(2):
            droplet(P, (p.x + rnd(s * .4), p.y + rnd(s * .4), p.z + rnd(s * .4)),
                    _v(bx * 3 + rnd(1), by * 3 + ru(0, 1.5), bz * 3 + rnd(1)), s=s * .55, life=.35)
        P.emit((p.x, p.y, p.z), MIST, size=s * 2, life=.3, grow=1.8, tex='smoke', blend='alpha', alpha=.22)
    elif kind == 'electrik':
        for _ in range(2):
            spark(P, (p.x, p.y, p.z), _v(rnd(6), rnd(6), rnd(6)), col=(1, 1, .75), col2=(1, .85, .2), s=.1,
                  life=.14, gravity=0, stretch=.03)
        P.emit((p.x, p.y, p.z), (1, .95, .5), size=s * 2.4, life=.16, vel=_v(bx, by, bz), tex='star', spin=rnd(6))
    elif kind == 'plante':
        leaf(P, (p.x + rnd(.2), p.y + rnd(.2), p.z + rnd(.2)), _v(bx * 1.5 + rnd(1), rnd(1) + .3, bz * 1.5 + rnd(1)),
             s=s * .9, life=.6)
        P.emit((p.x, p.y, p.z), (.5, 1, .35), size=s * 1.6, life=.2, alpha=.5)
    elif kind == 'glace':
        P.emit((p.x, p.y, p.z), (.85, .95, 1), size=s * 1.8, life=.45, vel=_v(bx, by + .3, bz), grow=1.8,
               tex='smoke', blend='alpha', alpha=.3)
        if random.random() < .6:
            P.emit((p.x + rnd(s), p.y + rnd(s), p.z + rnd(s)), (.9, 1, 1), size=.3, life=.35, tex='star', spin=rnd(4))
    elif kind == 'roche':
        smoke(P, (p.x, p.y, p.z), _v(bx, .6, bz), s=s * 1.5, life=.5, alpha=.35, col=DUST, col2=(.7, .64, .56))
    elif kind == 'psy':
        P.emit((p.x, p.y, p.z), (.85, .5, 1), col2=(.4, .15, .8), size=s * 2.4, life=.35, grow=.3)
        if random.random() < .5:
            P.emit((p.x + rnd(s), p.y + rnd(s), p.z + rnd(s)), (1, .8, 1), size=.3, life=.4, tex='star', spin=rnd(4))
    elif kind == 'combat':                          # traits de vitesse et souffle d'air
        P.emit((p.x, p.y, p.z), (1, .9, .75), size=s * 1.2, life=.18, vel=_v(bx * 10, by * 10, bz * 10),
               mode='stretch', stretch=.05, alpha=.7)
        if random.random() < .3:
            smoke(P, (p.x, p.y, p.z), _v(bx, .3, bz), s=s * 1.4, life=.4, alpha=.2, col=(.95, .9, .85),
                  col2=(1, .97, .95))
    elif kind == 'spectre':                         # volutes d'ombre violette
        P.emit((p.x, p.y, p.z), (.3, .15, .45), col2=(.12, .05, .2), size=s * 2.2, life=.5,
               vel=_v(bx + rnd(.5), .4, bz + rnd(.5)), grow=1.8, tex='smoke', blend='alpha', spin=rnd(2), alpha=.55)
        if random.random() < .5:
            P.emit((p.x + rnd(s), p.y + rnd(s), p.z + rnd(s)), (.8, .6, 1), size=.25, life=.35, tex='star')
    elif kind == 'dragon':                          # flammes bleu-violet
        for _ in range(2):
            P.emit((p.x + rnd(s * .3), p.y + rnd(s * .3), p.z + rnd(s * .3)), (.65, .6, 1), col2=(.25, .15, .7),
                   size=s * 2 * ru(.8, 1.2), life=.35, vel=_v(bx * 2 + rnd(.5), .6, bz * 2 + rnd(.5)), grow=1.4,
                   gravity=-2, drag=1.8, tex='smoke', blend='alpha', spin=rnd(2), alpha=.8, fade=1.3)
        P.emit((p.x, p.y, p.z), (.75, .75, 1), size=s * 1.4, life=.2, alpha=.5)
    else:
        P.emit((p.x, p.y, p.z), (1, .97, .9), size=s * 1.8, life=.2, vel=_v(bx, by, bz), alpha=.6)


def impact(kind, p, s=.5, ground=None, strength=1.0):
    """Impact d'une attaque : éclair bref au cœur, débris propres au type, courte dissipation."""
    P = PARTICLES
    if P is None:
        return
    st = style(kind)
    k = strength
    x, y, z = p.x, p.y, p.z
    gy = y - .9 if ground is None else ground
    P.emit((x, y, z), st['hot'], size=s * 3.2 * k, life=.1, grow=1.6, alpha=.8)             # flash
    P.emit((x, y, z), st['core'], size=s * 4.5 * k, life=.2, grow=1.3, alpha=.4)
    ground_glow(P, (x, gy, z), st['core'], s * 3 * k, .3, alpha=.35)
    n = int(10 * k)
    if kind == 'feu':
        for _ in range(n):
            flame(P, (x, y, z), _v(rnd(4), ru(1, 4), rnd(4)), s=s * 2 * k, life=.5)
        for _ in range(int(3 * k)):
            smoke(P, (x, y + .3, z), _v(rnd(1), ru(1, 2), rnd(1)), s=s * 3 * k, life=1.3, alpha=.4)
        for _ in range(n):
            spark(P, (x, y, z), _v(rnd(7), ru(2, 7), rnd(7)))
    elif kind == 'eau':
        for _ in range(int(n * 1.6)):
            droplet(P, (x, y, z), _v(rnd(4), ru(2, 6), rnd(4)), s=s * .6)
        ground_ring(P, (x, gy + .06, z), (.85, .95, 1), .3, s * 5 * k, .45, alpha=.7, blend='alpha')
        for _ in range(3):
            P.emit((x + rnd(.4), y, z + rnd(.4)), MIST, size=s * 3 * k, life=.5, vel=_v(rnd(1), 1, rnd(1)),
                   grow=2, tex='smoke', blend='alpha', alpha=.3)
    elif kind == 'electrik':
        for _ in range(int(n * 1.4)):
            spark(P, (x, y, z), _v(rnd(10), rnd(8) + 2, rnd(10)), col=(1, 1, .8), col2=(1, .8, .2), s=.12,
                  life=.25, gravity=3, stretch=.03)
        P.emit((x, y, z), (1, 1, .7), size=s * 5 * k, life=.2, tex='star', spin=rnd(3))
        for _ in range(3):
            a = random.uniform(0, math.tau)
            bolt(Vec3(x, y, z), Vec3(x + math.sin(a) * 1.8 * k, gy + .1, z + math.cos(a) * 1.8 * k), 'short', life=.1)
    elif kind == 'plante':
        for _ in range(n):
            leaf(P, (x, y, z), _v(rnd(4), ru(1, 4), rnd(4)), s=s * .9)
        for _ in range(4):
            P.emit((x, y, z), (.7, 1, .5), size=.4, life=.5, vel=_v(rnd(2), ru(.5, 2), rnd(2)), tex='star')
    elif kind == 'glace':
        for _ in range(n):
            P.emit((x, y, z), (.85, .97, 1), size=s * .7, life=.6, vel=_v(rnd(5), ru(1, 5), rnd(5)), gravity=10,
                   drag=.5, tex='shard', blend='alpha', spin=rnd(8), alpha=.95, fade=.5)
        for _ in range(3):
            P.emit((x, y, z), (.9, .97, 1), size=s * 3, life=.7, vel=_v(rnd(1.5), .5, rnd(1.5)), grow=2,
                   tex='smoke', blend='alpha', alpha=.35)
        ground_ring(P, (x, gy + .06, z), (.8, .95, 1), .3, s * 4 * k, .4, alpha=.6)
    elif kind == 'roche':
        for _ in range(int(4 * k)):
            smoke(P, (x, y - .3, z), _v(rnd(2), ru(.5, 1.5), rnd(2)), s=s * 3 * k, life=1.1, alpha=.45,
                  col=DUST, col2=(.72, .66, .58))
        for _ in range(n):
            P.emit((x, y, z), (.38, .32, .26), size=s * ru(.3, .6), life=.7, vel=_v(rnd(5), ru(2, 6), rnd(5)),
                   gravity=16, drag=.3, tex='shard', blend='alpha', spin=rnd(10), alpha=1, fade=.3)
    elif kind == 'psy':
        ground_ring(P, (x, gy + .08, z), (.85, .5, 1), .4, s * 5 * k, .4, alpha=.8)
        for _ in range(n):
            P.emit((x, y, z), (1, .75, 1), col2=(.6, .3, 1), size=.35, life=.5, vel=_v(rnd(4), rnd(4), rnd(4)),
                   tex='star', drag=2, spin=rnd(5))
    elif kind == 'combat':                          # coup de poing : étoile d'impact et onde d'air
        P.emit((x, y, z), (1, .95, .8), size=s * 4 * k, life=.14, tex='star', spin=rnd(2), alpha=.9)
        ground_ring(P, (x, y, z), (1, .9, .75), .3, s * 4 * k, .25, alpha=.7)
        for _ in range(n):
            spark(P, (x, y, z), _v(rnd(7), ru(1, 6), rnd(7)), col=(1, .95, .8), col2=(1, .5, .25), s=.12, life=.25)
        smoke(P, (x, gy + .3, z), _v(0, .5, 0), s=s * 2.5 * k, life=.6, alpha=.25, col=DUST, col2=(.85, .8, .72))
    elif kind == 'spectre':                         # l'ombre éclate puis se dissipe
        ground_ring(P, (x, gy + .08, z), (.6, .35, .95), .4, s * 4.5 * k, .45, alpha=.8)
        for _ in range(int(5 * k)):
            P.emit((x + rnd(.5), y, z + rnd(.5)), (.25, .12, .38), col2=(.1, .04, .16), size=s * 2.6 * k, life=.9,
                   vel=_v(rnd(1.5), ru(.5, 1.5), rnd(1.5)), grow=2, tex='smoke', blend='alpha', spin=rnd(2), alpha=.6)
        for _ in range(n):
            P.emit((x, y, z), (.85, .65, 1), size=.3, life=.5, vel=_v(rnd(4), ru(1, 4), rnd(4)), tex='star',
                   drag=2, spin=rnd(5))
    elif kind == 'dragon':                          # gerbe de flammes draconiques
        for _ in range(n):
            P.emit((x, y, z), (.7, .65, 1), col2=(.25, .12, .7), size=s * 2 * k, life=.5,
                   vel=_v(rnd(4), ru(1, 4), rnd(4)), grow=1.5, gravity=-2.5, drag=1.8, tex='smoke', blend='alpha',
                   spin=rnd(2), alpha=.85, fade=1.3)
        for _ in range(n):
            spark(P, (x, y, z), _v(rnd(7), ru(2, 7), rnd(7)), col=(.85, .85, 1), col2=(.45, .3, 1))
    else:
        for _ in range(n):
            spark(P, (x, y, z), _v(rnd(5), ru(1, 5), rnd(5)), col=(1, 1, .95), col2=(.9, .85, .7))
        smoke(P, (x, gy + .3, z), _v(0, .6, 0), s=s * 2.5, life=.6, alpha=.3, col=DUST, col2=(.8, .76, .7))


def burst(parent, pos, col, n=8, speed=4.0, size=.25, life=.45):
    """Gerbe de particules lumineuses (niveau, soins, messages réseau...)."""
    P = PARTICLES
    if P is None:
        return
    for _ in range(n):
        d = Vec3(rnd(), random.uniform(.2, 1.2), rnd()).normalized() * speed * random.uniform(.5, 1.1)
        P.emit(pos, col, size=size * random.uniform(1.6, 2.6), life=life * random.uniform(.7, 1.2),
               vel=(d.x, d.y, d.z), grow=.4, gravity=speed * .8, drag=2.5)


def explosion(pos, st, radius, kind=None):
    """Grosse explosion au sol (zones annoncées) : forme propre au type."""
    P = PARTICLES
    if P is None:
        return
    x, y, z = pos.x, pos.y, pos.z
    R = radius
    k = kind or 'normal'
    P.emit((x, y + .8, z), st['hot'], size=R * 2.2, life=.15, grow=1.5, alpha=.8)
    ground_glow(P, (x, y, z), st['core'], R * 1.6, .45, alpha=.5)
    ground_ring(P, (x, y + .1, z), st['hot'], R * .3, R * 1.5, .35, alpha=.9)
    if k == 'feu':                              # boule de feu, champignon de fumée, braises, sol brûlé
        for i in range(34):
            a = random.uniform(0, math.tau)
            sp = ru(1, 5) * R * .5
            flame(P, (x + math.sin(a) * R * .3, y + .4, z + math.cos(a) * R * .3),
                  _v(math.sin(a) * sp, ru(2, 7), math.cos(a) * sp), s=R * .9, life=.7, rise=4)
        for _ in range(9):
            smoke(P, (x + rnd(R * .4), y + ru(.5, 2), z + rnd(R * .4)), _v(rnd(1), ru(2, 4), rnd(1)), s=R * 1.2,
                  life=2.2, alpha=.5)
        for _ in range(26):
            spark(P, (x, y + .5, z), _v(rnd(9), ru(4, 12), rnd(9)), s=.16, life=.9, gravity=9)
        P.emit((x, y + .06, z), (.08, .06, .05), size=R * 2.1, life=3.5, tex='smoke', blend='alpha', mode='flat',
               alpha=.55, fade=2)
    elif k == 'eau':                            # geyser et pluie de gouttes
        for _ in range(50):
            droplet(P, (x + rnd(R * .4), y, z + rnd(R * .4)), _v(rnd(3), ru(6, 14), rnd(3)), s=.35, life=1.2)
        for _ in range(6):
            P.emit((x, y + ru(0, 3), z), MIST, size=R * 1.4, life=1, vel=_v(rnd(1), 1.5, rnd(1)), grow=2,
                   tex='smoke', blend='alpha', alpha=.35)
        ground_ring(P, (x, y + .08, z), (.9, .97, 1), R * .4, R * 1.6, .7, alpha=.7, blend='alpha')
    elif k == 'glace':                          # blizzard : nuage de givre, éclats, flocons
        for _ in range(10):
            P.emit((x + rnd(R * .6), y + ru(.3, 2), z + rnd(R * .6)), (.9, .97, 1), size=R * 1.2, life=1.4,
                   vel=_v(rnd(2), .4, rnd(2)), grow=2, tex='smoke', blend='alpha', alpha=.45, spin=rnd(1))
        for _ in range(26):
            P.emit((x, y + .4, z), (.8, .95, 1), size=ru(.4, .8), life=.9, vel=_v(rnd(7), ru(2, 7), rnd(7)),
                   gravity=12, drag=.4, tex='shard', blend='alpha', spin=rnd(9), fade=.5)
        for _ in range(30):
            P.emit((x + rnd(R), y + ru(.5, 4), z + rnd(R)), (1, 1, 1), size=ru(.15, .3), life=1.6,
                   vel=_v(rnd(2), -ru(.5, 1.5), rnd(2)), tex='star', spin=rnd(3))
        P.emit((x, y + .06, z), (.85, .95, 1), size=R * 2, life=3, tex='smoke', blend='alpha', mode='flat', alpha=.5,
               fade=2)
    elif k == 'roche':                          # pluie de rochers : poussière épaisse, éclats
        for _ in range(12):
            smoke(P, (x + rnd(R * .7), y + ru(.2, 1), z + rnd(R * .7)), _v(rnd(2), ru(.5, 2), rnd(2)), s=R * 1.1,
                  life=1.8, alpha=.55, col=DUST, col2=(.75, .7, .62))
        for _ in range(30):
            P.emit((x, y + .5, z), (.36, .3, .25), size=ru(.3, .75), life=1, vel=_v(rnd(7), ru(3, 9), rnd(7)),
                   gravity=18, drag=.2, tex='shard', blend='alpha', spin=rnd(10), fade=.3)
    elif k == 'electrik':
        for _ in range(30):
            spark(P, (x, y + .4, z), _v(rnd(12), ru(2, 9), rnd(12)), col=(1, 1, .8), col2=(1, .8, .2), s=.14,
                  life=.4, gravity=6)
    else:
        for _ in range(24):
            spark(P, (x, y + .4, z), _v(rnd(8), ru(2, 8), rnd(8)), col=st['hot'], col2=st['core'])
        for _ in range(5):
            smoke(P, (x, y + .5, z), _v(rnd(1.5), 1.5, rnd(1.5)), s=R, life=1, alpha=.3, col=st['trail'],
                  col2=st['core'])


# ==================================================================== éclairs
def _bolt_mesh(a, b, width, jitter, branches, rng):
    mb = MeshBuilder()

    def seg(p, q, w):
        flat_ = math.hypot(q[0] - p[0], q[2] - p[2])
        L = math.hypot(flat_, q[1] - p[1])
        rot = (-math.degrees(math.atan2(q[1] - p[1], flat_)), math.degrees(math.atan2(q[0] - p[0], q[2] - p[2])), 0)
        mid = tuple((p[k] + q[k]) / 2 for k in range(3))
        mb.add('box', mid, (w * 3, w * 3, L + w), rot=rot, col=color.rgba(.35, .5, 1, .55))  # halo bleuté
        mb.add('box', mid, (w, w, L + w), rot=rot, col=color.rgb(1, 1, 1))                  # cœur blanc

    def path(p, q, w, jit, depth):
        L = math.dist(p, q)
        n = max(3, int(L / 1.4))
        pts = [p]
        for i in range(1, n):
            t = i / n
            j = jit * (.35 + math.sin(t * math.pi) * .65)
            pts.append(tuple(p[k] + (q[k] - p[k]) * t + rng.uniform(-j, j) * (.4 if k == 1 else 1) for k in range(3)))
        pts.append(q)
        for i, (u, v) in enumerate(zip(pts, pts[1:])):
            seg(u, v, w * (1 - .5 * i / n))
            if depth and rng.random() < branches and i < n - 1:          # ramifications
                d = (v[0] - u[0], v[1] - u[1], v[2] - u[2])
                end = (v[0] + d[0] * 2 + rng.uniform(-2, 2), v[1] + d[1] * 1.5, v[2] + d[2] * 2 + rng.uniform(-2, 2))
                path(v, end, w * .5, jit * .6, depth - 1)

    path(tuple(a), tuple(b), width, jitter, 2)
    return mb


_BOLTS = {}
_BOLT_SPEC = {'sky': (24.0, .14, 2.2, .35), 'sky_thin': (24.0, .07, 1.6, .2), 'short': (2.0, .045, .35, .2)}


def _additive(node):
    """La lumière s'ajoute au décor (éclairs) : lueur au lieu d'un tube opaque."""
    from panda3d.core import ColorBlendAttrib, TransparencyAttrib
    node.set_transparency(TransparencyAttrib.M_alpha)
    node.set_attrib(ColorBlendAttrib.make(ColorBlendAttrib.M_add, ColorBlendAttrib.O_incoming_alpha,
                                          ColorBlendAttrib.O_one))
    node.set_depth_write(False)
    node.set_bin('fixed', 53)
    return node


def _bolt_variants(kind):
    """Quelques éclairs types (le long de +Y, longueur fixe), construits une seule fois : en jeu on
    ne fait que les placer, orienter et étirer (construire un maillage à chaque coup coûte cher)."""
    v = _BOLTS.get(kind)
    if v is None:
        from panda3d.core import NodePath
        L, w, jit, br = _BOLT_SPEC[kind]
        rng = random.Random(len(_BOLTS) + 3)
        v = _BOLTS[kind] = []
        for _ in range(5):
            holder = NodePath('bolt')
            _additive(_bolt_mesh((0, 0, 0), (0, L, 0), w, jit, br, rng).static(holder, emissive=1.0))
            v.append(holder)
    return v


def bolt(a, b, kind='short', life=.18):
    """Éclair ramifié éphémère de a vers b (Vec3)."""
    P = PARTICLES
    if P is None:
        return
    L = _BOLT_SPEC[kind][0]
    node = P.root.attach_new_node('bolt')
    random.choice(_bolt_variants(kind)).instance_to(node)
    node.set_pos(a)
    node.look_at(b, Vec3(0, 1, 0) if abs(b.y - a.y) < .9 * (b - a).length() else Vec3(1, 0, 0))
    node.set_p(node.get_p() - 90)                   # l'éclair est construit le long de +Y
    node.set_scale(1, (b - a).length() / L, 1)
    P.keep(node, life)


def lightning(parent, pos, col, height=24):
    """Foudre qui tombe du ciel : éclair ramifié, flash, lueur et étincelles au sol, fumée."""
    P = PARTICLES
    if P is None:
        return
    top = Vec3(pos.x + rnd(3), pos.y + height, pos.z + rnd(3))
    ground = Vec3(pos.x, pos.y + .1, pos.z)
    bolt(top, ground, 'sky', life=.22)
    bolt(top, ground, 'sky_thin', life=.12)
    P.emit((pos.x, pos.y + 1.5, pos.z), (1, 1, .95), size=6, life=.18, grow=1.3, alpha=.8)
    P.emit((pos.x, pos.y + 1, pos.z), col, size=4, life=.3, alpha=.6)
    ground_glow(P, (pos.x, pos.y, pos.z), (.6, .75, 1), 4.5, .4, alpha=.55)
    ground_ring(P, (pos.x, pos.y + .1, pos.z), (1, 1, .85), .5, 4.5, .35, alpha=.9)
    for _ in range(26):
        spark(P, (pos.x, pos.y + .3, pos.z), _v(rnd(9), ru(2, 8), rnd(9)), col=(1, 1, .85), col2=(.6, .8, 1), s=.13,
              life=.45, gravity=7, stretch=.03)
    for _ in range(3):
        smoke(P, (pos.x + rnd(.5), pos.y + .3, pos.z + rnd(.5)), _v(rnd(.6), .9, rnd(.6)), s=1.6, life=1.2, alpha=.3)
    P.emit((pos.x, pos.y + .05, pos.z), (.1, .08, .08), size=2.6, life=2.5, tex='smoke', blend='alpha', mode='flat',
           alpha=.5, fade=2)


# ==================================================================== arcs électriques (tours Tesla)
class Arcs:
    """Arcs électriques qui crépitent entre des points (tours Tesla) : pour chaque liaison, quelques
    éclairs figés dont un seul s'affiche à la fois, tiré au hasard plusieurs fois par seconde."""

    def __init__(self, parent, rng):
        self.parent, self.rng = parent, rng
        self.links = []

    def _bolt(self, a, b, width, jitter):
        node = _additive(_bolt_mesh(a, b, width, jitter, .18, self.rng).static(self.parent, emissive=1.0))
        node.set_color_scale(.95, .8, 1, 1)
        node.hide()
        return node

    def add(self, links, ground=(), y0=0.0):
        """links : paires de points reliés en permanence ; ground : (point, (x, z)) décharges au sol, plus rares."""
        for a, b in links:
            self.links.append({'nodes': [self._bolt(a, b, .07, 1.0) for _ in range(3)], 'on': None, 't': 0.0,
                               'rate': self.rng.uniform(.06, .12), 'chance': .75})
        for a, (x, z) in ground:
            self.links.append({'nodes': [self._bolt(a, (x, y0 + .2, z), .06, 1.4) for _ in range(2)], 'on': None,
                               't': self.rng.uniform(0, 2), 'rate': .12, 'chance': .12})

    def update(self, dt):
        for ln in self.links:
            ln['t'] -= dt
            if ln['t'] > 0:
                continue
            ln['t'] = ln['rate']
            if ln['on'] is not None:
                ln['on'].hide()
                ln['on'] = None
            if self.rng.random() < ln['chance']:
                ln['on'] = self.rng.choice(ln['nodes'])
                ln['on'].show()


# ==================================================================== météo des arènes
class ArenaWeather:
    """Météo d'une arène, dessinée avec les particules de la partie. Elle ne tombe que lorsque
    l'arène est contrôlée par une équipe, sur tout son quartier (rayon `radius`), mais les
    particules ne sont émises qu'autour de la caméra (disque de rayon LOCAL) : le coût reste
    celui d'une seule arène, quelle que soit la taille du quartier.

      pluie  : averse en traits fins, éclaboussures et ronds dans l'eau au sol, brume basse
      orage  : averse plus forte et oblique, foudre ramifiée avec flash et impact au sol
      sable  : tempête de sable : nappes de poussière qui défilent avec le vent, grains en traits
      pollen : pollen lumineux qui flotte, pétales et feuilles qui tombent en tournoyant
      soleil : chaleur écrasante : braises qui montent, cendres qui tombent, air qui tremble"""
    LOCAL = 16.0

    def __init__(self, parent, centre, radius, kind, type_color, count=40, rng=random, base=0.0, ground=None,
                 arena_radius=14.0):
        self.parent = parent
        self.base = base            # hauteur du sol de l'arène (arène perchée)
        self.centre, self.radius, self.kind = Vec3(centre[0], 0, centre[1]), radius, kind
        self.arena_radius = arena_radius
        self.ground = ground        # hauteur du sol en (x, z) (le quartier n'est pas plat)
        self.rng = rng
        self.type_color = type_color
        self._acc = {}
        self._warm = 0.0            # à l'arrivée de la caméra : la météo lente est déjà installée
        self._active = False
        self._focus = self.centre
        self._bolt = rng.uniform(2, 5)
        self.wind = Vec3(math.cos(rng.uniform(0, math.tau)), 0, math.sin(rng.uniform(0, math.tau)))

    def _rate(self, key, per_s, dt):
        """Nombre de particules à émettre cette image pour un débit donné."""
        if self._warm and per_s < 20:
            dt = self._warm
        v = self._acc.get(key, 0.0) + per_s * dt
        n = int(v)
        self._acc[key] = v - n
        return n

    def _spot(self, extra=0.0):
        """Point au hasard autour de la caméra, dans le quartier de l'arène."""
        f, R = self._focus, self.radius + max(0.0, extra)
        for _ in range(4):
            a, r = self.rng.uniform(0, math.tau), math.sqrt(self.rng.random()) * (self.LOCAL + extra)
            x, z = f.x + math.sin(a) * r, f.z + math.cos(a) * r
            if (x - self.centre.x) ** 2 + (z - self.centre.z) ** 2 < R * R:
                return x, z
        return x, z

    def _y(self, x, z):
        return self.ground(x, z) if self.ground is not None else self.base

    def update(self, dt, focus=None, owned=True, view=70):
        P = PARTICLES
        if P is None or not owned or focus is None:
            self._active = False
            return
        f = Vec3(focus.x, 0, focus.z)
        d = (f - self.centre).length()
        if d > self.radius + 8:
            self._active = False
            return
        if d > self.radius - 4:                 # caméra au bord du quartier : on émet plutôt vers l'intérieur
            f = self.centre + (f - self.centre).normalized() * (self.radius - 4)
        self._focus = f
        if not self._active:
            self._active, self._warm = True, 3.0
        getattr(self, '_' + self.kind)(P, dt)
        self._warm = 0.0

    def _pluie(self, P, dt, heavy=1.0):
        rng = self.rng
        wx, wz = self.wind.x * 3 * heavy, self.wind.z * 3 * heavy
        for _ in range(self._rate('drop', 340 * heavy, dt)):
            x, z = self._spot(6)
            h = rng.uniform(9, 14)
            P.emit((x - wx * .5, self._y(x, z) + h, z - wz * .5), (.5, .58, .7), size=.15, life=h / 26, vel=(wx, -26, wz),
                   tex='streak', blend='alpha', mode='stretch', stretch=.06, alpha=.85, fade=.2)
        for _ in range(self._rate('cloud', .9, dt)):                   # ombre des nuages : l'arène s'assombrit
            x, z = self._spot(-6)
            P.emit((x, self._y(x, z) + .25, z), (.1, .12, .18), size=rng.uniform(20, 26), life=5, grow=1.1, tex='smoke',
                   blend='alpha', mode='flat', alpha=.26 * heavy, fade=1.0)
        for _ in range(self._rate('splash', 110 * heavy, dt)):
            x, z = self._spot(4)
            P.emit((x, self._y(x, z) + .2, z), (.88, .94, 1), size=.25, life=.45, grow=5, tex='ring', blend='alpha', mode='flat',
                   alpha=.7, rot=0)
            for _ in range(2):
                P.emit((x, self._y(x, z) + .2, z), (.9, .95, 1), size=.14, life=.3, vel=(rnd(1.4), ru(1.8, 3), rnd(1.4)),
                       gravity=14, tex='drop', blend='alpha', mode='stretch', stretch=.03, alpha=.8)
        for _ in range(self._rate('mist', 2.5, dt)):                   # brume basse
            x, z = self._spot()
            P.emit((x, self._y(x, z) + .6, z), (.78, .84, .9), size=rng.uniform(6, 9), life=4, vel=(wx * .2, 0, wz * .2),
                   grow=1.3, tex='smoke', blend='alpha', alpha=.2)

    def _orage(self, P, dt):
        self._pluie(P, dt, 1.35)
        self._bolt -= dt
        if self._bolt <= 0:
            self._bolt = self.rng.uniform(2.5, 6)
            x, z = self._spot(-3)
            lightning(self.parent, Vec3(x, self._y(x, z), z), (1, .95, .4), height=30)

    def _sable(self, P, dt):
        rng, w = self.rng, self.wind
        for _ in range(self._rate('cloud', 12, dt)):                    # nappes de poussière qui défilent
            x, z = self._spot(6)
            sp = rng.uniform(5, 8)
            P.emit((x - w.x * 6, self._y(x, z) + rng.uniform(1, 4.5), z - w.z * 6), (.97, .86, .64), col2=(.9, .78, .58),
                   size=rng.uniform(4, 7), life=3, vel=(w.x * sp, rng.uniform(-.2, .3), w.z * sp), grow=1.6,
                   tex='smoke', blend='alpha', spin=rnd(.6), alpha=.55, fade=1.0)
        for _ in range(self._rate('shadow', .8, dt)):                  # la poussière voile le soleil
            x, z = self._spot(-6)
            P.emit((x, self._y(x, z) + .25, z), (.35, .22, .1), size=rng.uniform(18, 24), life=5, grow=1.1, tex='smoke',
                   blend='alpha', mode='flat', alpha=.24, fade=1.0)
        for _ in range(self._rate('grain', 140, dt)):                   # grains de sable en traits
            x, z = self._spot(4)
            sp = rng.uniform(10, 15)
            P.emit((x, self._y(x, z) + rng.uniform(.2, 3), z), (1, .93, .74), size=.14, life=.5,
                   vel=(w.x * sp + rnd(1), rnd(.6), w.z * sp + rnd(1)), tex='streak', blend='alpha', mode='stretch',
                   stretch=.05, alpha=.8)
        for _ in range(self._rate('swirl', 1.2, dt)):                   # petit tourbillon de poussière
            x, z = self._spot()
            for k in range(6):
                a = k * math.tau / 6
                P.emit((x + math.sin(a) * .8, self._y(x, z) + .3 + k * .35, z + math.cos(a) * .8), (.84, .72, .52), size=1.4,
                       life=1.6, vel=(math.cos(a) * 2 + w.x * 2, .9, -math.sin(a) * 2 + w.z * 2), grow=1.8,
                       tex='smoke', blend='alpha', alpha=.3, spin=4)

    def _pollen(self, P, dt):
        rng = self.rng
        for _ in range(self._rate('mote', 26, dt)):
            x, z = self._spot(4)
            P.emit((x, self._y(x, z) + rng.uniform(.5, 5), z), (1, .95, .5), col2=(.75, 1, .45), size=rng.uniform(.2, .38),
                   life=rng.uniform(3, 5), vel=(rnd(.4) + self.wind.x * .3, rnd(.25), rnd(.4) + self.wind.z * .3),
                   alpha=.9, fade=.7)
        for _ in range(self._rate('petal', 10, dt)):
            x, z = self._spot(5)
            col = rng.choice(((1, .7, .82), (1, .82, .9), (.55, .85, .35), (1, .95, .7)))
            P.emit((x, self._y(x, z) + rng.uniform(3, 7), z), col, size=rng.uniform(.4, .6), life=6,
                   vel=(self.wind.x * .8 + rnd(.3), -1.1, self.wind.z * .8 + rnd(.3)), drag=.1, tex='leaf',
                   blend='alpha', spin=rnd(4), alpha=1, fade=.4)
        for _ in range(self._rate('ray', .5, dt)):                      # rais de lumière très doux
            x, z = self._spot(-2)
            P.emit((x, self._y(x, z) + 5, z), (1, .95, .7), size=1.6, life=5, vel=(0, .01, 0), tex='streak', mode='stretch',
                   stretch=0, alpha=.07, grow=1.2)

    def _soleil(self, P, dt):
        rng = self.rng
        for _ in range(self._rate('ember', 40, dt)):
            x, z = self._spot(6)
            P.emit((x, self._y(x, z) + .2, z), (1, .8, .35), col2=(1, .25, .05), size=rng.uniform(.16, .28),
                   life=rng.uniform(1.8, 3), vel=(rnd(.8), rng.uniform(1.5, 3.5), rnd(.8)), gravity=-.6, drag=.6,
                   mode='stretch', stretch=.05, fade=.8)
        for _ in range(self._rate('ash', 8, dt)):
            x, z = self._spot(6)
            P.emit((x, self._y(x, z) + rng.uniform(5, 9), z), (.35, .33, .32), size=rng.uniform(.2, .32), life=5,
                   vel=(rnd(.4), -.7, rnd(.4)), tex='leaf', blend='alpha', spin=rnd(3), alpha=.8)
        for _ in range(self._rate('haze', 1.5, dt)):                    # air chaud qui tremble
            x, z = self._spot()
            P.emit((x, self._y(x, z) + .8, z), (1, .55, .25), size=rng.uniform(4, 6), life=2.5, vel=(0, .6, 0), grow=1.3,
                   tex='smoke', alpha=.07)
        for _ in range(self._rate('fume', 1.2, dt)):                    # fumerolles au bord de l'arène
            a = rng.uniform(0, math.tau)
            ar = self.arena_radius + 2.6
            x, z = self.centre.x + math.sin(a) * ar, self.centre.z + math.cos(a) * ar
            smoke(P, (x, self._y(x, z) + .3, z), (rnd(.3), 1.2, rnd(.3)), s=1.6, life=3, alpha=.25)
            P.emit((x, self._y(x, z) + .2, z), (1, .5, .1), size=1.6, life=1, alpha=.4)
