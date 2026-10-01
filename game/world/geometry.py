"""Géométrie procédurale et shader.

Tous les décors et les Pokémon sont construits à partir de primitives
(boîte, sphère, cylindre, cône...) fusionnées dans un seul maillage par
groupe grâce à MeshBuilder. Un maillage = un appel de rendu, ce qui garde le
jeu fluide même avec des centaines d'arbres.
"""
import math

import numpy as np

from game import config as C
from ursina import Entity, Shader, Vec3, Vec4, color


# --------------------------------------------------------------------------
# Shader : soleil avec ombres portées douces (PCF), lumière ambiante ciel/sol,
# léger liseré lumineux, brouillard, "flash" et parties lumineuses (emissive)
# --------------------------------------------------------------------------
_LIGHT_STRUCT = """
uniform struct {
    vec4 position;
    vec3 color;
    vec3 attenuation;
    vec3 spotDirection;
    float spotCosCutoff;
    float spotExponent;
    sampler2DShadow shadowMap;
    mat4 shadowViewMatrix;
} p3d_LightSource[1];
"""

toon_shader = Shader(
    name='toon_shader',
    language=Shader.GLSL,
    vertex='#version 150\n' + _LIGHT_STRUCT + """
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec4 v_color;
out vec3 v_normal;
out vec3 v_world;
out vec4 v_shadow;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_normal = normalize(mat3(p3d_ModelMatrix) * p3d_Normal);
    v_color = p3d_Color;
    v_shadow = p3d_LightSource[0].shadowViewMatrix * (p3d_ModelViewMatrix * p3d_Vertex);
}
""",
    fragment='#version 150\n' + _LIGHT_STRUCT + """
uniform vec4 p3d_ColorScale;
uniform vec3 light_dir;
uniform vec4 sun_color;
uniform vec4 sky_color;
uniform vec4 ground_color;
uniform vec4 fog_color;
uniform vec2 fog_range;
uniform vec3 cam_pos;
uniform vec4 flash;
uniform float emissive;
uniform float shadow_texel;
uniform float detail;
in vec4 v_color;
in vec3 v_normal;
in vec3 v_world;
in vec4 v_shadow;
out vec4 frag;
uniform sampler2D noise_tex;
// bruit lissé lu dans une petite texture précalculée (16 x 16 cases qui se répètent) : une lecture
// de texture au lieu de quatre calculs trigonométriques par appel (gros gain sur puce Intel)
float vnoise(vec2 p) { return texture(noise_tex, p * 0.0625).r; }
void main() {
    vec4 base = v_color * p3d_ColorScale;
    if (detail > 0.0) {
        // grain du sol et de la roche : taches larges, moyennes et fines (position dans le monde)
        vec2 q = v_world.xz + vec2(v_world.y * 0.7, -v_world.y * 0.5);
        float nd = (vnoise(q * 0.3) - 0.5) * 0.2 + (vnoise(q * 1.6) - 0.5) * 0.14 + (vnoise(q * 6.5) - 0.5) * 0.1;
        base.rgb *= 1.0 + detail * nd;
        // style peint : grandes zones plus chaudes ou plus froides, touches de pinceau étirées
        float warm = vnoise(q * 0.05 + 3.1);
        base.rgb = mix(base.rgb, base.rgb * vec3(1.12, 1.03, 0.8), detail * smoothstep(0.5, 0.85, warm) * 0.7);
        base.rgb = mix(base.rgb, base.rgb * vec3(0.86, 0.97, 1.1), detail * smoothstep(0.5, 0.15, warm) * 0.6);
        float stroke = vnoise(vec2(q.x * 1.3 + q.y * 0.5, q.y * 0.45 - q.x * 0.2));
        base.rgb *= 1.0 + detail * (stroke - 0.5) * 0.08;
    }
    // alpha > 1 dans la couleur d'un sommet : partie lumineuse (lave, cristaux...)
    float vglow = clamp(v_color.a - 1.0, 0.0, 1.0);
    vec3 n = normalize(v_normal);
    vec3 L = -normalize(light_dir);
    // décor (detail > 0) : lumière enveloppante, plus douce qu'un éclairage réaliste
    float paint = step(0.001, detail);
    float nl = dot(n, L);
    float ndl = mix(max(nl, 0.0), clamp((nl + 0.45) / 1.45, 0.0, 1.0), paint);
    // ombre douce : 4 echantillons filtres autour du point
    float sh = 0.0;
    vec4 sc = v_shadow;
    sc.z -= (0.00025 + 0.0012 * (1.0 - ndl)) * sc.w;
    vec2 o = vec2(shadow_texel * sc.w);
    sh += textureProj(p3d_LightSource[0].shadowMap, sc + vec4(-o.x, -o.y, 0.0, 0.0));
    sh += textureProj(p3d_LightSource[0].shadowMap, sc + vec4( o.x, -o.y, 0.0, 0.0));
    sh += textureProj(p3d_LightSource[0].shadowMap, sc + vec4(-o.x,  o.y, 0.0, 0.0));
    sh += textureProj(p3d_LightSource[0].shadowMap, sc + vec4( o.x,  o.y, 0.0, 0.0));
    sh *= 0.25;
    vec3 ambient = mix(ground_color.rgb, sky_color.rgb, n.y * 0.5 + 0.5);
    ambient = mix(ambient, ambient * vec3(0.92, 1.0, 1.14), paint);            // ombres légèrement bleutées
    vec3 sun = sun_color.rgb * mix(vec3(1.0), vec3(1.08, 1.0, 0.84), paint);  // soleil plus chaud
    vec3 lit = base.rgb * (ambient + ndl * sh * sun);
    vec3 V = normalize(cam_pos - v_world);
    float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0) * 0.16;
    lit += rim * sky_color.rgb * (0.35 + 0.65 * sh);
    lit = mix(lit, base.rgb, max(emissive, vglow));
    lit = mix(lit, flash.rgb, flash.a);
    float d = length(v_world - cam_pos);
    float f = clamp((d - fog_range.x) / (fog_range.y - fog_range.x), 0.0, 1.0);
    lit = mix(lit, fog_color.rgb, f * fog_color.a);
    frag = vec4(lit, min(base.a, 1.0));
}
""",
    # seules les entrées propres à chaque entité sont ici ; l'ambiance est
    # posée une fois sur `scene` et héritée par tout le graphe de scène.
    default_input={
        'flash': Vec4(1, 1, 1, 0),
        'emissive': 0.0,
        'detail': 0.0,
    },
)

ENV = {
    'light_dir': Vec3(-0.42, -1.0, 0.38),
    'sun_color': Vec4(.8, .76, .68, 1),
    'sky_color': Vec4(0.42, 0.48, 0.6, 1),
    'ground_color': Vec4(0.28, 0.27, 0.25, 1),
    'fog_color': Vec4(0.62, 0.80, 0.95, 1),
    'fog_range': (60.0, 170.0),
    'shadow_texel': 1 / 4096,
}


def setup_sun(extent=320, resolution=4096):
    """Soleil directionnel avec carte d'ombres couvrant tout le stade."""
    from ursina import DirectionalLight, Vec2
    d = Vec3(*ENV['light_dir']).normalized()
    sun = DirectionalLight(shadow_map_resolution=Vec2(resolution, resolution), shadows=True)
    sun.position = -d * 300
    sun.lookAt(Vec3(0, 0, 0))
    lens = sun._light.get_lens()
    lens.set_film_size(extent, extent)
    lens.set_film_offset(0, 0)
    lens.set_near_far(20, 620)
    set_environment(shadow_texel=1.2 / resolution)
    return sun


def freeze_shadows(sun):
    """Le décor est immobile : on garde la carte d'ombres déjà calculée au lieu de la refaire."""
    from ursina import application
    buf = sun._light.get_shadow_buffer(application.base.win.get_gsg())
    if buf is not None:
        buf.set_active(False)
        return True
    return False


def unfreeze_shadows(sun):
    """Réactive le calcul de la carte d'ombres (retour au menu, avant une nouvelle partie)."""
    from ursina import application
    buf = sun._light.get_shadow_buffer(application.base.win.get_gsg())
    if buf is not None:
        buf.set_active(True)


def noise_texture(cells=16, res=256, seed=7):
    """Texture de bruit lissé qui se répète (même aspect que l'ancien bruit calculé dans le shader)."""
    from panda3d.core import SamplerState, Texture as PTexture
    rng = np.random.default_rng(seed)
    lat = rng.random((cells, cells)).astype(np.float32)
    t = (np.arange(res) + .5) / res * cells
    i0 = np.floor(t).astype(int) % cells
    i1 = (i0 + 1) % cells
    f = t - np.floor(t)
    u = f * f * (3 - 2 * f)
    rows = lat[i0][:, i0] * (1 - u)[None, :] + lat[i0][:, i1] * u[None, :]
    rows1 = lat[i1][:, i0] * (1 - u)[None, :] + lat[i1][:, i1] * u[None, :]
    img = rows * (1 - u)[:, None] + rows1 * u[:, None]
    tex = PTexture('bruit')
    tex.setup_2d_texture(res, res, PTexture.T_unsigned_byte, PTexture.F_luminance)
    tex.set_ram_image(np.ascontiguousarray((img * 255).astype(np.uint8)).tobytes())
    tex.set_wrap_u(SamplerState.WM_repeat)
    tex.set_wrap_v(SamplerState.WM_repeat)
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    tex.set_magfilter(SamplerState.FT_linear)
    return tex


def set_environment(**kwargs):
    """Applique (ou modifie) l'ambiance globale : lumière, ciel, brouillard."""
    from ursina import scene
    if 'noise_tex' not in ENV:
        ENV['noise_tex'] = noise_texture()
    for key, value in kwargs.items():
        if key == 'fog_range':
            ENV[key] = tuple(value)
        elif key == 'light_dir':
            ENV[key] = Vec3(*value)
        elif key == 'shadow_texel':
            ENV[key] = float(value)
        else:
            ENV[key] = Vec4(*value)
    for key, value in ENV.items():
        scene.set_shader_input(key, value)


def update_camera_uniform():
    """A appeler chaque frame (une seule fois pour toute la scène)."""
    from ursina import camera, scene
    scene.set_shader_input('cam_pos', camera.world_position)


# --------------------------------------------------------------------------
# Primitives (sommets, triangles, normales) de taille unité, centrées
# --------------------------------------------------------------------------
def _box():
    v, n, t = [], [], []
    faces = [
        ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
        ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
        ((0, 1, 0), (0, 0, 1), (1, 0, 0)),
        ((0, -1, 0), (0, 0, -1), (1, 0, 0)),
        ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
        ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
    ]
    for normal, up, right in faces:
        nn, uu, rr = np.array(normal), np.array(up), np.array(right)
        c = nn * .5
        base = len(v)
        for su, sr in ((-1, -1), (-1, 1), (1, 1), (1, -1)):
            v.append(c + uu * .5 * su + rr * .5 * sr)
            n.append(nn)
        t += [base, base + 1, base + 2, base, base + 2, base + 3]
    return np.array(v, float), np.array(t, int), np.array(n, float)


def _sphere(seg=12, rings=8, top_only=False):
    v, n, t = [], [], []
    ring_end = rings // 2 if top_only else rings
    for r in range(ring_end + 1):
        phi = math.pi * r / rings
        for s in range(seg + 1):
            th = 2 * math.pi * s / seg
            p = np.array([math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th)])
            v.append(p * .5)
            n.append(p)
    w = seg + 1
    for r in range(ring_end):
        for s in range(seg):
            a, b = r * w + s, r * w + s + 1
            c, d = (r + 1) * w + s, (r + 1) * w + s + 1
            t += [a, c, b, b, c, d]
    if top_only:  # disque de fermeture
        centre = len(v)
        v.append(np.zeros(3))
        n.append(np.array([0, -1, 0]))
        start = ring_end * w
        for s in range(seg):
            t += [centre, start + s, start + s + 1]
    return np.array(v, float), np.array(t, int), np.array(n, float)


def _cylinder(seg=12, top_radius=.5, bottom_radius=.5):
    v, n, t = [], [], []
    slope = (bottom_radius - top_radius)
    for s in range(seg + 1):
        th = 2 * math.pi * s / seg
        cx, cz = math.cos(th), math.sin(th)
        nrm = np.array([cx, slope, cz])
        nrm /= np.linalg.norm(nrm)
        v.append([cx * bottom_radius, -.5, cz * bottom_radius]); n.append(nrm)
        v.append([cx * top_radius, .5, cz * top_radius]); n.append(nrm)
    for s in range(seg):
        a = s * 2
        t += [a, a + 1, a + 2, a + 1, a + 3, a + 2]
    for y, rad, ny in ((.5, top_radius, 1), (-.5, bottom_radius, -1)):
        if rad <= 0.0001:
            continue
        centre = len(v)
        v.append([0, y, 0]); n.append([0, ny, 0])
        for s in range(seg + 1):
            th = 2 * math.pi * s / seg
            v.append([math.cos(th) * rad, y, math.sin(th) * rad]); n.append([0, ny, 0])
        for s in range(seg):
            t += [centre, centre + 1 + s, centre + 2 + s]
    return np.array(v, float), np.array(t, int), np.array(n, float)


def _blade(rows=(0.0, .4, .75, 1.0)):
    """Longue feuille d'herbe : effilée, pliée en V au milieu et courbée vers +z (hauteur 1,
    de y = -.5 à .5 ; l'échelle z règle la courbure). Peu de triangles : on en pose des milliers."""
    v = []
    for t in rows:
        w = .5 * (1 - t) ** .55                    # demi-largeur : feuille pleine, pointe au sommet
        y, z = t - .5, t * t
        v += [(-w, y, z), (0, y, z - .12 * w), (w, y, z)]
    v = np.array(v, float)
    t = []
    for r in range(len(rows) - 1):
        l0, l1 = 3 * r, 3 * r + 3
        t += [l0, l0 + 1, l1 + 1, l0, l1 + 1, l1, l0 + 1, l0 + 2, l1 + 2, l0 + 1, l1 + 2, l1 + 1]
    t = np.array(t, int)
    n = np.zeros_like(v)
    tri = t.reshape(-1, 3)
    fn = np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]])
    for k in range(3):
        np.add.at(n, tri[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    n[-3:] = n[-6:-3]                              # la pointe (triangles plats) prend la normale voisine
    # normales tournées vers le ciel (face intérieure de la courbure, penchées vers le haut) :
    # l'herbe prend la lumière du soleil de façon douce et régulière, sans faces noires
    n = -n + np.array((0, 1.3, 0))
    n /= np.linalg.norm(n, axis=1, keepdims=True)
    return v, t, n


def _ring(seg=32, inner=.4):
    """Mur circulaire (anneau épais) de hauteur 1, rayon extérieur .5."""
    v, n, t = [], [], []
    for rad, sign in ((.5, 1), (inner, -1)):
        base = len(v)
        for s in range(seg + 1):
            th = 2 * math.pi * s / seg
            cx, cz = math.cos(th), math.sin(th)
            v.append([cx * rad, -.5, cz * rad]); n.append([cx * sign, 0, cz * sign])
            v.append([cx * rad, .5, cz * rad]); n.append([cx * sign, 0, cz * sign])
        for s in range(seg):
            a = base + s * 2
            t += [a, a + 1, a + 2, a + 1, a + 3, a + 2]
    base = len(v)
    for s in range(seg + 1):
        th = 2 * math.pi * s / seg
        cx, cz = math.cos(th), math.sin(th)
        v.append([cx * .5, .5, cz * .5]); n.append([0, 1, 0])
        v.append([cx * inner, .5, cz * inner]); n.append([0, 1, 0])
    for s in range(seg):
        a = base + s * 2
        t += [a, a + 1, a + 2, a + 1, a + 3, a + 2]
    return np.array(v, float), np.array(t, int), np.array(n, float)


def _outward(prim):
    """Oriente tous les triangles vers l'extérieur (même sens que les normales) :
    indispensable pour le contour des Pokémon (on n'affiche que les faces arrière)."""
    v, t, n = prim
    tri = t.reshape(-1, 3).copy()
    a, b, c = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    geo = np.cross(b - a, c - a)
    ref = n[tri[:, 0]] + n[tri[:, 1]] + n[tri[:, 2]]
    flip = (geo * ref).sum(axis=1) < 0
    tri[flip] = tri[flip][:, [0, 2, 1]]
    return v, tri.reshape(-1), n


PRIMS = {
    'box': _box(),
    'sphere': _sphere(12, 8),
    'sphere_hi': _sphere(20, 14),
    'sphere_lo': _sphere(8, 6),
    'sphere_xlo': _sphere(6, 4),
    'sphere_md': _sphere(16, 11),    # Pokémon : sphères lisses sans être trop lourdes
    'blob': _sphere(12, 9),          # base des formes organiques (feuillages, rochers)
    'frustum': _cylinder(18, top_radius=.14),
    'dome': _sphere(20, 14, top_only=True),
    'cyl': _cylinder(12),
    'cyl_hi': _cylinder(40),
    'cyl6': _cylinder(6),
    'cone': _cylinder(10, top_radius=0.0),
    'cone4': _cylinder(4, top_radius=0.0),
    'cone6': _cylinder(6, top_radius=0.0),
    'cone8': _cylinder(8, top_radius=0.0),
    'cone16': _cylinder(16, top_radius=0.0),
    'cyl16': _cylinder(16),
    'cyl8': _cylinder(8),
    'cyl24': _cylinder(24),
    'ring': _ring(48, .44),
    'ring_thin': _ring(64, .47),
    'ring_97': _ring(96, .485),     # anneaux très fins pour les grands rayons (tribunes)
    'ring_99': _ring(128, .495),
    'disc': _cylinder(48),
    'blade': _blade(),               # feuille des hautes herbes
}
PRIMS = {k: _outward(p) for k, p in PRIMS.items()}


def _faceted(prim):
    """Version à facettes (une normale par triangle) : rochers et prismes aux arêtes nettes."""
    v, t, n = prim
    tri = t.reshape(-1, 3)
    pv = v[tri].reshape(-1, 3)
    a, b, c = v[tri[:, 0]], v[tri[:, 1]], v[tri[:, 2]]
    fn = np.cross(b - a, c - a)
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
    return pv, np.arange(len(pv)), np.repeat(fn, 3, axis=0)


def _smooth_normals(v, t):
    """Normales lissées (les sommets confondus, comme la couture d'une sphère, sont soudés)."""
    key = np.unique(np.round(v, 4), axis=0, return_inverse=True)[1].ravel()
    tri = t.reshape(-1, 3)
    fn = np.cross(v[tri[:, 1]] - v[tri[:, 0]], v[tri[:, 2]] - v[tri[:, 0]])
    acc = np.zeros((key.max() + 1, 3))
    for k in range(3):
        np.add.at(acc, key[tri[:, k]], fn)
    n = acc[key]
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def _rock(seed):
    """Rocher de base : galet arrondi aux formes douces (grosses bosses, quelques plans à peine
    marqués), la base aplatie et posée au sol. Chaque graine donne une forme."""
    rng = np.random.default_rng(seed)
    v, t, n = _sphere(11, 8)
    dirs = rng.normal(size=(5, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    u = v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)
    bumps = sum(rng.uniform(.05, .12) * np.clip(u @ d, 0, 1) ** 3 for d in dirs)     # bosses larges
    cuts = rng.normal(size=(6, 3))
    cuts /= np.linalg.norm(cuts, axis=1, keepdims=True)
    flats = sum(np.clip(u @ d - .55, 0, 1) for d in cuts) * .8                        # pans taillés, arêtes adoucies
    v = v * (1 + bumps - flats)[:, None]
    v[:, 1] = np.where(v[:, 1] < -.2, -.2 + (v[:, 1] + .2) * .35, v[:, 1])
    v, t, _ = _outward((v, t, n))
    return v, t, _smooth_normals(v, t)


for _i in range(4):
    PRIMS[f'rock{_i}'] = _rock(_i + 3)
PRIMS['prism6'] = _faceted(_outward(_cylinder(6)))       # colonne de roche (basalte, grès)
PRIMS['prism5'] = _faceted(_outward(_cylinder(5, top_radius=.42)))
PRIMS['blob_lo'] = _outward(_sphere(10, 7))             # touffe de feuillage légère
PRIMS['trunk'] = _outward(_cylinder(8, top_radius=.3))   # tronc qui s'affine
ROCKS = ('rock0', 'rock1', 'rock2', 'rock3')


def glowing(col, g):
    """Couleur à passer à MeshBuilder.add pour une primitive lumineuse à `g` (0 à 1) : le
    shader lit la lueur dans l'alpha (> 1), sans maillage séparé."""
    return Vec4(col[0], col[1], col[2], 1 + g)


def _rot_matrix(rot):
    rx, ry, rz = (math.radians(a) for a in rot)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return my @ mx @ mz


class MeshBuilder:
    """Accumule des primitives transformées puis produit un Mesh unique."""

    def __init__(self):
        self.verts, self.norms, self.tris, self.cols = [], [], [], []
        self.sizes = []           # taille de chaque primitive (pour ignorer les détails au contour)
        self.count = 0

    def add(self, prim, pos=(0, 0, 0), scale=1, rot=(0, 0, 0), col=color.white, wobble=0.0, grad=0.0,
            light=0.0, cap=None, tip=None, volume=None):
        """Ajoute une primitive.

        wobble : bosselle la surface (formes organiques : feuillages, rochers)
        grad   : assombrit le bas de la forme (dégradé vertical, effet de volume)
        light  : éclaircit le haut de la forme (sommet des feuillages au soleil)
        cap    : (couleur, force) : recouvre les faces tournées vers le ciel (mousse, herbe, sable)
        tip    : (couleur, force) : dégradé vers cette couleur au sommet (pointe des feuilles d'herbe)
        volume : (x, y, z, force) : oriente les normales depuis ce centre ; plusieurs touffes d'un même
                 feuillage s'éclairent alors comme un seul volume doux (au lieu d'une grappe de boules)
        """
        v, t, n = PRIMS[prim]
        s = np.array(scale if isinstance(scale, (tuple, list)) else (scale,) * 3, float)
        m = _rot_matrix(rot)
        vw = (v * s) @ m.T + np.array(pos, float)
        nw = (n / np.where(s == 0, 1, s)) @ m.T
        nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-6)
        if volume is not None:
            cx, cy, cz, kv = volume
            d = vw - np.array((cx, cy, cz), float)
            d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-6)
            nw = nw * (1 - kv) + d * kv
            nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-6)
        if wobble:
            k = (np.sin(vw[:, 0] * 1.9 + vw[:, 1] * 1.3 + pos[2]) + np.sin(vw[:, 2] * 2.3 - vw[:, 0] * 1.1 + pos[0])
                 + np.sin(vw[:, 1] * 2.7 + vw[:, 2] * 1.7)) / 3
            vw = vw + nw * (k * wobble * float(np.mean(np.abs(s))))[:, None]
        self.verts.append(vw)
        self.norms.append(nw)
        self.tris.append(t + self.count)
        col = tuple(col)
        c = np.tile(np.array(col if len(col) == 4 else col + (1,), float), (len(v), 1))
        if grad:
            f = 1 - grad * np.clip(.5 - v[:, 1], 0, 1)
            c[:, :3] *= f[:, None]
        if light:
            c[:, :3] *= (1 + light * np.clip(v[:, 1] * 2, 0, 1))[:, None]
        if cap is not None:
            cc, amount = cap
            m = amount * np.clip((nw[:, 1] - .5) / .3, 0, 1)[:, None]
            c[:, :3] = c[:, :3] * (1 - m) + np.array(tuple(cc)[:3], float) * m
        if tip is not None:            # dégradé vers une autre teinte en haut de la forme
            tc, amount = tip
            m = amount * np.clip(v[:, 1] + .5, 0, 1)[:, None] ** 1.6
            c[:, :3] = c[:, :3] * (1 - m) + np.array(tuple(tc)[:3], float) * m
        self.cols.append(c)
        self.sizes.append(float(np.sort(np.abs(s))[1]))
        self.count += len(v)
        return self

    def add_raw(self, verts, tris, norms, cols):
        """Ajoute un maillage libre (tableaux numpy) avec une couleur par sommet."""
        self.verts.append(np.asarray(verts, float))
        self.norms.append(np.asarray(norms, float))
        self.tris.append(np.asarray(tris, int) + self.count)
        self.cols.append(np.asarray(cols, float))
        self.count += len(verts)
        return self

    def build(self):
        """Construit directement la géométrie Panda3D à partir des tableaux numpy (rapide)."""
        if not self.verts:
            return None
        from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, NodePath
        data = np.hstack([np.concatenate(self.verts), np.concatenate(self.norms),
                          np.concatenate(self.cols)]).astype(np.float32)
        idx = np.concatenate(self.tris).astype(np.uint32)
        vdata = GeomVertexData('mesh', _vertex_format(), Geom.UH_static)
        vdata.unclean_set_num_rows(len(data))
        vdata.modify_array_handle(0).copy_data_from(np.ascontiguousarray(data))
        prim = GeomTriangles(Geom.UH_static)
        prim.set_index_type(Geom.NT_uint32)
        arr = prim.modify_vertices()
        arr.unclean_set_num_rows(len(idx))
        arr.modify_handle().copy_data_from(np.ascontiguousarray(idx))
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('mesh')
        node.add_geom(geom)
        return NodePath(node)

    def static(self, parent, emissive=0.0, col=None, transparent=False, detail=0.0):
        """Comme entity(), mais crée un simple nœud Panda3D (pas une entité Ursina).

        Ursina parcourt toutes ses entités à chaque image : pour le décor immobile
        et les petits éléments animés à la main, un nœud nu est bien plus léger.
        """
        from panda3d.core import TransparencyAttrib
        node = self.build()
        if node is None:
            return None
        if not toon_shader.compiled:
            toon_shader.compile()
        node.reparent_to(parent)
        node.set_shader(toon_shader._shader)
        node.set_shader_input('flash', Vec4(1, 1, 1, 0))
        node.set_shader_input('emissive', float(emissive))
        node.set_shader_input('detail', float(detail))
        # faces arrière non dessinées : le décor est fait de volumes fermés, et ne pas dessiner leur
        # intérieur divise presque par deux le travail de la carte graphique (gros gain sur puce Intel)
        if C.QUALITY.get('two_sided', False):
            node.set_two_sided(True)
        else:                       # nos maillages tournent dans le sens horaire : on écarte l'autre sens
            from panda3d.core import CullFaceAttrib
            node.set_attrib(CullFaceAttrib.make(CullFaceAttrib.M_cull_counter_clockwise))
        node.set_transparency(TransparencyAttrib.M_alpha if transparent else TransparencyAttrib.M_none)
        if col is not None:
            node.set_color_scale(Vec4(*col))
        return node

    def outline(self, thickness, col=(0.08, 0.07, 0.1, 1), min_size=.1):
        """Coque légèrement gonflée le long des normales : affichée par l'arrière, elle dessine
        un fin contour sombre autour du modèle (style des jeux Pokémon en 3D)."""
        o = MeshBuilder()
        sizes = self.sizes if len(self.sizes) == len(self.verts) else [1.0] * len(self.verts)
        start = 0
        for v, n, t, size in zip(self.verts, self.norms, self.tris, sizes):
            if size >= min_size:          # les petits détails (yeux, narines...) n'ont pas de contour
                o.verts.append(v + n * thickness)
                o.norms.append(n)
                o.tris.append(t - start + o.count)
                o.cols.append(np.tile(np.array(col, float), (len(v), 1)))
                o.count += len(v)
            start += len(v)
        return o

    def entity(self, parent=None, emissive=0.0, transparent=False, double_sided=True, **kwargs):
        e = Entity(parent=parent, model=self.build(), shader=toon_shader, double_sided=double_sided, **kwargs)
        if not transparent:
            # Ursina active par défaut une transparence qui dessine tout deux fois : inutile ici
            from panda3d.core import TransparencyAttrib
            e.model.setTransparency(TransparencyAttrib.M_none)
        if emissive:
            e.set_shader_input('emissive', emissive)
        return e


_FORMAT = None


def _vertex_format():
    global _FORMAT
    if _FORMAT is None:
        from panda3d.core import Geom, GeomVertexArrayFormat, GeomVertexFormat
        a = GeomVertexArrayFormat()
        a.add_column('vertex', 3, Geom.NT_float32, Geom.C_point)
        a.add_column('normal', 3, Geom.NT_float32, Geom.C_normal)
        a.add_column('color', 4, Geom.NT_float32, Geom.C_color)
        _FORMAT = GeomVertexFormat.register_format(a)
    return _FORMAT


class ChunkedBuilder:
    """Comme MeshBuilder, mais répartit les primitives en carrés de `size` unités.

    Chaque carré devient un maillage séparé : ce qui est hors du champ de la
    caméra n'est alors pas dessiné du tout (gros gain sur les petites cartes
    graphiques).
    """

    def __init__(self, size=40.0, lift=None):
        self.size = size
        self.parts = {}
        self.lift = lift          # fonction (x, z) -> hauteur du sol, pour poser le décor sur le relief

    @property
    def count(self):
        return sum(b.count for b in self.parts.values())

    def add(self, prim, pos=(0, 0, 0), scale=1, rot=(0, 0, 0), col=color.white, **kw):
        key = (int(math.floor(pos[0] / self.size)), int(math.floor(pos[2] / self.size)))
        b = self.parts.get(key)
        if b is None:
            b = self.parts[key] = MeshBuilder()
        if self.lift is not None:
            pos = (pos[0], pos[1] + self.lift(pos[0], pos[2]), pos[2])
        b.add(prim, pos, scale, rot, col, **kw)
        return self

    def add_raw(self, verts, tris, norms, cols):
        """Maillage libre (positions absolues, sans relief ajouté), rangé dans le carré de son 1er sommet."""
        key = (int(math.floor(verts[0][0] / self.size)), int(math.floor(verts[0][2] / self.size)))
        self.parts.setdefault(key, MeshBuilder()).add_raw(verts, tris, norms, cols)
        return self

    def entity(self, parent=None, emissive=0.0, **kwargs):
        return [b.entity(parent=parent, emissive=emissive, **kwargs) for b in self.parts.values() if b.count]

    def static(self, parent, emissive=0.0, **kw):
        return [b.static(parent, emissive, **kw) for b in self.parts.values() if b.count]


def hex_points(cx, cz, r):
    """Sommets d'un hexagone (côtés plats au nord et au sud) de rayon r, dans l'ordre du dallage."""
    pts = [(cx + math.sin(math.radians(30 + 60 * k)) * r, cz + math.cos(math.radians(30 + 60 * k)) * r)
           for k in range(6)]
    return sorted(pts, key=lambda p: math.atan2(p[1] - cz, p[0] - cx))


def add_hex_slab(b, cx, y, cz, r, h, col):
    """Dalle hexagonale (dessus + flancs) dans le constructeur b."""
    c = (col[0], col[1], col[2], col[3] if len(col) > 3 else 1)
    top = hex_points(cx, cz, r)
    verts = [(cx, y + h / 2, cz)] + [(x, y + h / 2, z) for x, z in top]
    tris = []
    for i in range(6):
        tris += [0, 1 + (i + 1) % 6, 1 + i]
    norms = [(0, 1, 0)] * 7
    base = len(verts)
    for i in range(6):                                   # flancs (dans les deux sens : toujours visibles)
        (x0, z0), (x1, z1) = top[i], top[(i + 1) % 6]
        nx, nz = (x0 + x1) / 2 - cx, (z0 + z1) / 2 - cz
        ln = math.hypot(nx, nz) or 1
        k = base + i * 4
        verts += [(x0, y + h / 2, z0), (x1, y + h / 2, z1), (x1, y - h / 2, z1), (x0, y - h / 2, z0)]
        norms += [(nx / ln, 0, nz / ln)] * 4
        tris += [k, k + 1, k + 2, k, k + 2, k + 3, k, k + 2, k + 1, k, k + 3, k + 2]
    b.add_raw(np.array(verts), np.array(tris), np.array(norms), np.array([c] * len(verts)))


def add_hex_band(b, cx, y, cz, r_out, r_in, h, col):
    """Bande (anneau) hexagonale entre les rayons r_in et r_out."""
    c = (col[0], col[1], col[2], col[3] if len(col) > 3 else 1)
    po, pi = hex_points(cx, cz, r_out), hex_points(cx, cz, r_in)
    yy = y + h / 2
    verts = [(x, yy, z) for x, z in po] + [(x, yy, z) for x, z in pi]
    tris = []
    for i in range(6):
        j = (i + 1) % 6
        tris += [i, j, 6 + j, i, 6 + j, 6 + i, i, 6 + j, j, i, 6 + i, 6 + j]     # les deux sens
    b.add_raw(np.array(verts), np.array(tris), np.array([(0, 1, 0)] * 12), np.array([c] * 12))


def destroy_tree(entity):
    """Détruit une entité ET toutes ses entités enfants. (destroy d'Ursina laisse les enfants dans
    la liste des entités parcourues à chaque image : ils ralentiraient la partie peu à peu.)"""
    from ursina import destroy
    stack, order = [entity], []
    while stack:
        e = stack.pop()
        order.append(e)
        stack.extend(e.children)
    for e in reversed(order):
        destroy(e)


def flat_circle(parent, radius, col, y=0.02, **kwargs):
    """Disque plat non éclairé (ombres portées, zones d'attaque...)."""
    from ursina import Circle
    return Entity(parent=parent, model=Circle(resolution=32, radius=radius), color=col,
                  rotation_x=90, y=y, double_sided=True, **kwargs)
