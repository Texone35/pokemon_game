"""Géométrie procédurale et shader.

Tous les décors et les Pokémon sont construits à partir de primitives
(boîte, sphère, cylindre, cône...) fusionnées dans un seul maillage par
groupe grâce à MeshBuilder. Un maillage = un appel de rendu, ce qui garde le
jeu fluide même avec des centaines d'arbres.
"""
import math

import numpy as np
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
in vec4 v_color;
in vec3 v_normal;
in vec3 v_world;
in vec4 v_shadow;
out vec4 frag;
void main() {
    vec4 base = v_color * p3d_ColorScale;
    vec3 n = normalize(v_normal);
    vec3 L = -normalize(light_dir);
    float ndl = max(dot(n, L), 0.0);
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
    vec3 lit = base.rgb * (ambient + ndl * sh * sun_color.rgb);
    vec3 V = normalize(cam_pos - v_world);
    float rim = pow(1.0 - max(dot(n, V), 0.0), 3.0) * 0.16;
    lit += rim * sky_color.rgb * (0.35 + 0.65 * sh);
    lit = mix(lit, base.rgb, emissive);
    lit = mix(lit, flash.rgb, flash.a);
    float d = length(v_world - cam_pos);
    float f = clamp((d - fog_range.x) / (fog_range.y - fog_range.x), 0.0, 1.0);
    lit = mix(lit, fog_color.rgb, f * fog_color.a);
    frag = vec4(lit, base.a);
}
""",
    # seules les entrées propres à chaque entité sont ici ; l'ambiance est
    # posée une fois sur `scene` et héritée par tout le graphe de scène.
    default_input={
        'flash': Vec4(1, 1, 1, 0),
        'emissive': 0.0,
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


def set_environment(**kwargs):
    """Applique (ou modifie) l'ambiance globale : lumière, ciel, brouillard."""
    from ursina import scene
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
}
PRIMS = {k: _outward(p) for k, p in PRIMS.items()}


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

    def add(self, prim, pos=(0, 0, 0), scale=1, rot=(0, 0, 0), col=color.white, wobble=0.0, grad=0.0):
        """Ajoute une primitive.

        wobble : bosselle la surface (formes organiques : feuillages, rochers)
        grad   : assombrit le bas de la forme (dégradé vertical, effet de volume)
        """
        v, t, n = PRIMS[prim]
        s = np.array(scale if isinstance(scale, (tuple, list)) else (scale,) * 3, float)
        m = _rot_matrix(rot)
        vw = (v * s) @ m.T + np.array(pos, float)
        nw = (n / np.where(s == 0, 1, s)) @ m.T
        nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-6)
        if wobble:
            k = (np.sin(vw[:, 0] * 1.9 + vw[:, 1] * 1.3 + pos[2]) + np.sin(vw[:, 2] * 2.3 - vw[:, 0] * 1.1 + pos[0])
                 + np.sin(vw[:, 1] * 2.7 + vw[:, 2] * 1.7)) / 3
            vw = vw + nw * (k * wobble * float(np.mean(np.abs(s))))[:, None]
        self.verts.append(vw)
        self.norms.append(nw)
        self.tris.append(t + self.count)
        c = np.tile(np.array(tuple(col), float), (len(v), 1))
        if grad:
            f = 1 - grad * np.clip(.5 - v[:, 1], 0, 1)
            c[:, :3] *= f[:, None]
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

    def static(self, parent, emissive=0.0, col=None, transparent=False):
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
        node.set_two_sided(True)
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

    def entity(self, parent=None, emissive=0.0, **kwargs):
        return [b.entity(parent=parent, emissive=emissive, **kwargs) for b in self.parts.values() if b.count]

    def static(self, parent, emissive=0.0, **kw):
        return [b.static(parent, emissive, **kw) for b in self.parts.values() if b.count]


def flat_circle(parent, radius, col, y=0.02, **kwargs):
    """Disque plat non éclairé (ombres portées, zones d'attaque...)."""
    from ursina import Circle
    return Entity(parent=parent, model=Circle(resolution=32, radius=radius), color=col,
                  rotation_x=90, y=y, double_sided=True, **kwargs)
