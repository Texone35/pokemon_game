"""Géométrie procédurale et shader.

Tous les décors et les Pokémon sont construits à partir de primitives
(boîte, sphère, cylindre, cône...) fusionnées dans un seul maillage par
groupe grâce à MeshBuilder. Un maillage = un appel de rendu, ce qui garde le
jeu fluide même avec des centaines d'arbres.
"""
import math

import numpy as np
from ursina import Entity, Mesh, Shader, Vec3, Vec4, color


# --------------------------------------------------------------------------
# Shader : éclairage diffus + ambiance hémisphérique + brouillard + "flash"
# --------------------------------------------------------------------------
toon_shader = Shader(
    name='toon_shader',
    language=Shader.GLSL,
    vertex='''#version 150
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec4 v_color;
out vec3 v_normal;
out vec3 v_world;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_normal = normalize(transpose(inverse(mat3(p3d_ModelMatrix))) * p3d_Normal);
    v_color = p3d_Color;
}
''',
    fragment='''#version 150
uniform vec4 p3d_ColorScale;
uniform vec3 light_dir;
uniform vec4 sky_color;
uniform vec4 ground_color;
uniform vec4 fog_color;
uniform vec2 fog_range;
uniform vec3 cam_pos;
uniform vec4 flash;
uniform float emissive;
in vec4 v_color;
in vec3 v_normal;
in vec3 v_world;
out vec4 frag;
void main() {
    vec4 base = v_color * p3d_ColorScale;
    vec3 n = normalize(v_normal);
    float diff = max(dot(n, -normalize(light_dir)), 0.0);
    diff = smoothstep(0.0, 1.0, diff);
    vec3 ambient = mix(ground_color.rgb, sky_color.rgb, n.y * 0.5 + 0.5);
    vec3 lit = base.rgb * (ambient + diff * vec3(0.62, 0.6, 0.55));
    lit = mix(lit, base.rgb, emissive);
    lit = mix(lit, flash.rgb, flash.a);
    float d = length(v_world - cam_pos);
    float f = clamp((d - fog_range.x) / (fog_range.y - fog_range.x), 0.0, 1.0);
    lit = mix(lit, fog_color.rgb, f * fog_color.a);
    frag = vec4(lit, base.a);
}
''',
    # seules les entrées propres à chaque entité sont ici ; l'ambiance est
    # posée une fois sur `scene` et héritée par tout le graphe de scène.
    default_input={
        'flash': Vec4(1, 1, 1, 0),
        'emissive': 0.0,
    },
)

ENV = {
    'light_dir': Vec3(-0.45, -1.0, 0.35),
    'sky_color': Vec4(0.52, 0.55, 0.62, 1),
    'ground_color': Vec4(0.30, 0.28, 0.27, 1),
    'fog_color': Vec4(0.62, 0.80, 0.95, 1),
    'fog_range': (60.0, 170.0),
}


def set_environment(**kwargs):
    """Applique (ou modifie) l'ambiance globale : lumière, ciel, brouillard."""
    from ursina import scene
    for key, value in kwargs.items():
        if key == 'fog_range':
            ENV[key] = tuple(value)
        elif key == 'light_dir':
            ENV[key] = Vec3(*value)
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


PRIMS = {
    'box': _box(),
    'sphere': _sphere(12, 8),
    'sphere_hi': _sphere(20, 14),
    'dome': _sphere(20, 14, top_only=True),
    'cyl': _cylinder(12),
    'cyl_hi': _cylinder(40),
    'cyl6': _cylinder(6),
    'cone': _cylinder(10, top_radius=0.0),
    'cone4': _cylinder(4, top_radius=0.0),
    'cone6': _cylinder(6, top_radius=0.0),
    'ring': _ring(48, .44),
    'ring_thin': _ring(64, .47),
    'disc': _cylinder(48),
}


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
        self.count = 0

    def add(self, prim, pos=(0, 0, 0), scale=1, rot=(0, 0, 0), col=color.white):
        v, t, n = PRIMS[prim]
        s = np.array(scale if isinstance(scale, (tuple, list)) else (scale,) * 3, float)
        m = _rot_matrix(rot)
        vw = (v * s) @ m.T + np.array(pos, float)
        nw = (n / np.where(s == 0, 1, s)) @ m.T
        nw /= np.maximum(np.linalg.norm(nw, axis=1, keepdims=True), 1e-6)
        self.verts.append(vw)
        self.norms.append(nw)
        self.tris.append(t + self.count)
        c = tuple(col)
        self.cols.append(np.tile(np.array(c, float), (len(v), 1)))
        self.count += len(v)
        return self

    def build(self):
        if not self.verts:
            return None
        v = np.concatenate(self.verts)
        n = np.concatenate(self.norms)
        t = np.concatenate(self.tris)
        c = np.concatenate(self.cols)
        return Mesh(
            vertices=[tuple(x) for x in v.tolist()],
            triangles=[tuple(t[i:i + 3]) for i in range(0, len(t), 3)],
            normals=[tuple(x) for x in n.tolist()],
            colors=[Vec4(*x) for x in c.tolist()],
            static=True,
        )

    def entity(self, parent=None, emissive=0.0, **kwargs):
        mesh = self.build()
        e = Entity(parent=parent, model=mesh, shader=toon_shader, double_sided=True, **kwargs)
        if emissive:
            e.set_shader_input('emissive', emissive)
        return e


def flat_circle(parent, radius, col, y=0.02, **kwargs):
    """Disque plat non éclairé (ombres portées, zones d'attaque...)."""
    from ursina import Circle
    return Entity(parent=parent, model=Circle(resolution=32, radius=radius), color=col,
                  rotation_x=90, y=y, double_sided=True, **kwargs)
