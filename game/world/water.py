"""Eau et lave animées : un shader dédié et un constructeur de surfaces.

Chaque sommet d'une surface porte :
  couleur r : profondeur relative (0 au bord, 1 au plus profond) -> teinte, transparence, écume
  couleur g : vitesse du courant
  couleur b : genre (0 eau, 0.5 chute d'eau, 1 lave)
  couleur a : opacité de base
  normale   : direction du courant (x, z) ou de la chute (x, y, z)

Eau : turquoise transparente sur les hauts-fonds, bleu profond au milieu ; petites vagues qui
suivent le courant (normale calculée dans le shader), reflet du ciel selon l'angle de vue,
reflets du soleil, écume sur les berges et en traînées dans le courant, ombres des arbres.
Chute d'eau : rideau strié de filets blancs qui descendent, écume en bas.
Lave : croûte sombre qui dérive et se fissure sur un fond jaune-orange lumineux.

Tout est calculé à partir de la position dans le monde : pas de texture, et une seule surface
pour toutes les rivières.
"""
import math

import numpy as np
from ursina import Shader

_LIGHT = """
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

water_shader = Shader(
    name='water_shader',
    language=Shader.GLSL,
    vertex='#version 150\n' + _LIGHT + """
uniform mat4 p3d_ModelViewProjectionMatrix;
uniform mat4 p3d_ModelViewMatrix;
uniform mat4 p3d_ModelMatrix;
in vec4 p3d_Vertex;
in vec3 p3d_Normal;
in vec4 p3d_Color;
out vec4 v_data;
out vec3 v_flow;
out vec3 v_world;
out vec4 v_shadow;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    v_world = (p3d_ModelMatrix * p3d_Vertex).xyz;
    v_flow = p3d_Normal;
    v_data = p3d_Color;
    v_shadow = p3d_LightSource[0].shadowViewMatrix * (p3d_ModelViewMatrix * p3d_Vertex);
}
""",
    fragment='#version 150\n' + _LIGHT + """
uniform vec3 light_dir;
uniform vec4 sun_color;
uniform vec4 sky_color;
uniform vec4 fog_color;
uniform vec2 fog_range;
uniform vec3 cam_pos;
uniform float wtime;
in vec4 v_data;
in vec3 v_flow;
in vec3 v_world;
in vec4 v_shadow;
out vec4 frag;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void main() {
    float depth = clamp(v_data.r, 0.0, 1.0);
    float speed = v_data.g;
    float kind = v_data.b;
    vec2 p = v_world.xz;
    vec3 V = normalize(cam_pos - v_world);
    float d = length(v_world - cam_pos);
    float fogk = clamp((d - fog_range.x) / (fog_range.y - fog_range.x), 0.0, 1.0) * fog_color.a;
    float t = wtime;

    if (kind > 0.75) {                                   // ---------- lave
        vec2 fl = v_flow.xz;
        vec2 q = p * 0.55 - fl * t * 0.25;
        float n = noise(q) * 0.6 + noise(q * 2.3 + vec2(t * 0.07, -t * 0.05)) * 0.4;
        float crack = smoothstep(0.42, 0.5, abs(n - 0.5) * 2.0);          // croûte (1) / fissure (0)
        float pulse = 0.85 + 0.15 * sin(t * 2.0 + n * 9.0);
        vec3 hot = mix(vec3(1.0, 0.36, 0.04), vec3(1.0, 0.86, 0.35), smoothstep(0.35, 0.0, abs(n - 0.5)));
        vec3 crust = mix(vec3(0.16, 0.08, 0.06), vec3(0.32, 0.12, 0.06), noise(p * 3.1));
        float edge = smoothstep(0.0, 0.35, depth);                        // le bord refroidit
        float c = max(crack * 0.85, 1.0 - edge);
        vec3 col = mix(hot * pulse, crust, c);
        col = mix(col, fog_color.rgb, fogk * 0.6);
        frag = vec4(col, 1.0);
        return;
    }

    // ombre (un seul échantillon filtré suffit sur l'eau)
    vec4 sc = v_shadow;
    sc.z -= 0.0015 * sc.w;
    float sh = textureProj(p3d_LightSource[0].shadowMap, sc);

    if (kind > 0.25) {                                   // ---------- chute d'eau
        vec3 dir = normalize(v_flow);
        vec3 side = normalize(cross(dir, vec3(0.0, 1.0, 0.0)) + vec3(1e-4));
        float along = dot(v_world, dir), across = dot(v_world, side);
        float s1 = noise(vec2(across * 3.2, along * 0.35 - t * 2.6));
        float s2 = noise(vec2(across * 7.0 + 3.0, along * 0.8 - t * 4.0));
        float streak = smoothstep(0.55, 0.8, s1 * 0.6 + s2 * 0.4);
        vec3 col = mix(vec3(0.42, 0.72, 0.86), vec3(0.95, 0.98, 1.0), streak * 0.85 + (1.0 - depth) * 0.5);
        col *= 0.75 + 0.25 * sh;
        col = mix(col, fog_color.rgb, fogk);
        frag = vec4(col, clamp(v_data.a * (0.75 + 0.25 * streak), 0.0, 1.0));
        return;
    }

    // ---------- eau calme ou courante
    vec2 fl = length(v_flow.xz) > 0.01 ? normalize(v_flow.xz) : vec2(0.0, 1.0);
    vec2 pr = vec2(-fl.y, fl.x);
    float a = dot(p, fl), b = dot(p, pr);
    float mv = t * (0.35 + speed);
    // petites vagues : somme de sinus dans le sens du courant et en travers (dérivées analytiques)
    float w1 = 1.7, w2 = 2.9, w3 = 5.3;
    float ph1 = a * w1 - mv * 2.0 + b * 0.6, ph2 = a * 0.9 + b * w2 - t * 1.3, ph3 = (a + b) * w3 - mv * 3.5;
    vec2 g = fl * (cos(ph1) * w1 * 0.05 + cos(ph2) * 0.9 * 0.035 + cos(ph3) * w3 * 0.012)
           + pr * (cos(ph1) * 0.6 * 0.05 + cos(ph2) * w2 * 0.035 + cos(ph3) * w3 * 0.012);
    float nn = noise(p * 1.4 + fl * mv);
    g += (vec2(noise(p * 2.1 + vec2(t * 0.3, 0.0)), noise(p * 2.1 + vec2(0.0, t * 0.3))) - 0.5) * 0.25;
    vec3 n = normalize(vec3(-g.x, 1.0, -g.y));

    vec3 shallow = vec3(0.30, 0.72, 0.74), deep = vec3(0.04, 0.26, 0.44);
    vec3 base = mix(shallow, deep, smoothstep(0.0, 0.85, depth));
    vec3 L = -normalize(light_dir);
    float ndl = max(dot(n, L), 0.0);
    vec3 col = base * (0.55 + 0.45 * ndl * (0.4 + 0.6 * sh));
    // reflet du ciel (Fresnel) et reflets du soleil
    float fres = pow(1.0 - max(dot(n, V), 0.0), 4.0);
    col = mix(col, sky_color.rgb * 1.6 + vec3(0.12), clamp(fres * 0.7, 0.0, 0.6));
    vec3 H = normalize(L + V);
    float spec = pow(max(dot(n, H), 0.0), 140.0) * 1.6 + pow(max(dot(n, H), 0.0), 22.0) * 0.12;
    col += sun_color.rgb * spec * sh;
    // écume : sur les berges et en traînées dans le courant
    float fn = noise(vec2(a * 0.9 - mv * 1.6, b * 2.4)) * 0.65 + noise(p * 3.7 + fl * mv * 1.3) * 0.35;
    float cut = mix(0.35, 0.8, smoothstep(0.02, 0.35, depth));
    float foam = smoothstep(cut, cut + 0.05, fn) * (0.45 + 0.55 * smoothstep(0.35, 0.0, depth));
    foam += smoothstep(0.1, 0.0, depth) * 0.5 * (0.6 + 0.4 * nn);
    foam = clamp(foam * (0.35 + speed * 0.9 + smoothstep(0.3, 0.0, depth)), 0.0, 1.0);
    col = mix(col, vec3(0.93, 0.97, 1.0) * (0.8 + 0.2 * sh), foam);
    col = mix(col, fog_color.rgb, fogk);
    float alpha = v_data.a * mix(0.55, 0.93, smoothstep(0.0, 0.6, depth));
    alpha = max(alpha, foam * 0.95) * smoothstep(0.0, 0.04, depth + 0.02);
    frag = vec4(col, alpha);
}
""",
    default_input={'wtime': 0.0},
)

KIND = {'water': 0.0, 'fall': .5, 'lava': 1.0}


class WaterBuilder:
    """Accumule des surfaces d'eau et de lave, puis en fait un seul maillage animé."""

    def __init__(self):
        self.verts, self.norms, self.cols, self.tris = [], [], [], []
        self.count = 0

    def add_raw(self, verts, tris, flow, depth, speed=.3, kind='water', alpha=1.0):
        verts = np.asarray(verts, np.float32)
        n = len(verts)
        flow = np.asarray(flow, np.float32)
        if flow.ndim == 1:
            flow = np.tile(flow, (n, 1))
        depth = np.broadcast_to(np.asarray(depth, np.float32), (n,))
        cols = np.stack([depth, np.full(n, speed, np.float32), np.full(n, KIND[kind], np.float32),
                         np.full(n, alpha, np.float32)], -1)
        self.verts.append(verts)
        self.norms.append(flow)
        self.cols.append(cols)
        self.tris.append(np.asarray(tris, np.int64).ravel() + self.count)
        self.count += n
        return self

    def disc(self, x, y, z, r, kind='water', depth=1.0, speed=.05, alpha=1.0, seg=36, flow=(0, 0, 0), sx=1.0,
             hexa=False):
        """Bassin rond (ou ovale avec sx, ou hexagonal avec hexa) : profond au centre, peu profond au bord."""
        from game import config as C
        rings = (0.0, .45, .8, 1.0)
        v, dd = [], []
        for k, t in enumerate(rings):
            for i in range(seg if k else 1):
                a = math.tau * i / seg
                h = C.hex_factor(math.degrees(a)) if hexa else 1.0
                v.append((x + math.sin(a) * r * t * sx * h, y, z + math.cos(a) * r * t * h))
                dd.append(depth * (1 - t ** 2.2))
        tris = []
        for i in range(seg):
            tris += [0, 1 + i, 1 + (i + 1) % seg]
        for k in range(1, len(rings) - 1):
            o0, o1 = 1 + (k - 1) * seg, 1 + k * seg
            for i in range(seg):
                j = (i + 1) % seg
                tris += [o0 + i, o1 + i, o1 + j, o0 + i, o1 + j, o0 + j]
        return self.add_raw(v, tris, flow, dd, speed, kind, alpha)

    def ring(self, x, y, z, r0, r1, kind='water', depth=1.0, speed=.25, alpha=1.0, seg=96, hexa=False):
        """Canal circulaire (ou hexagonal avec hexa) : le courant tourne autour du centre."""
        from game import config as C
        v, dd, fl = [], [], []
        for i in range(seg):
            a = math.tau * i / seg
            h = C.hex_factor(math.degrees(a)) if hexa else 1.0
            for k, t in enumerate((0, .5, 1)):
                r = (r0 + (r1 - r0) * t) * h
                v.append((x + math.sin(a) * r, y, z + math.cos(a) * r))
                dd.append(depth * (1 - abs(t - .5) * 2) ** .6)
                fl.append((math.cos(a), 0, -math.sin(a)))
        tris = []
        for i in range(seg):
            j = (i + 1) % seg
            for k in range(2):
                a0, a1, b0, b1 = i * 3 + k, i * 3 + k + 1, j * 3 + k, j * 3 + k + 1
                tris += [a0, b0, b1, a0, b1, a1]
        return self.add_raw(v, tris, fl, dd, speed, kind, alpha)

    def curtain(self, pts, width, alpha=.92, kind='fall', speed=1.0):
        """Rideau (chute d'eau ou de lave) le long d'une suite de points 3D."""
        v, dd, fl = [], [], []
        for i, p in enumerate(pts):
            q = pts[min(i + 1, len(pts) - 1)] if i < len(pts) - 1 else p
            o = pts[max(i - 1, 0)]
            d = np.array(q if i < len(pts) - 1 else p, float) - np.array(o if i else p, float)
            if i == len(pts) - 1:
                d = np.array(p, float) - np.array(pts[i - 1], float)
            d /= max(np.linalg.norm(d), 1e-6)
            side = np.cross(d, (0, 1, 0))
            side /= max(np.linalg.norm(side), 1e-6)
            w = width * (1 + .3 * i / max(len(pts) - 1, 1))
            for s in (-.5, .5):
                v.append(tuple(np.array(p, float) + side * w * s))
                dd.append(1 - i / max(len(pts) - 1, 1) * .6 if kind == 'fall' else 1.0)
                fl.append(tuple(d))
        tris = []
        for i in range(len(pts) - 1):
            a, b = i * 2, i * 2 + 2
            tris += [a, b, b + 1, a, b + 1, a + 1]
        return self.add_raw(v, tris, fl, dd, speed, kind, alpha)

    def build(self, parent):
        """Crée le nœud (un seul appel de rendu) sous `parent`."""
        if not self.verts:
            return None
        from panda3d.core import Geom, GeomNode, GeomTriangles, GeomVertexData, TransparencyAttrib
        from game.world.geometry import _vertex_format
        data = np.hstack([np.concatenate(self.verts), np.concatenate(self.norms),
                          np.concatenate(self.cols)]).astype(np.float32)
        idx = np.concatenate(self.tris).astype(np.uint32)
        vdata = GeomVertexData('water', _vertex_format(), Geom.UH_static)
        vdata.unclean_set_num_rows(len(data))
        vdata.modify_array_handle(0).copy_data_from(np.ascontiguousarray(data))
        prim = GeomTriangles(Geom.UH_static)
        prim.set_index_type(Geom.NT_uint32)
        arr = prim.modify_vertices()
        arr.unclean_set_num_rows(len(idx))
        arr.modify_handle().copy_data_from(np.ascontiguousarray(idx))
        geom = Geom(vdata)
        geom.add_primitive(prim)
        node = GeomNode('water')
        node.add_geom(geom)
        np_ = parent.attach_new_node(node)
        if not water_shader.compiled:
            water_shader.compile()
        np_.set_shader(water_shader._shader)
        np_.set_shader_input('wtime', 0.0)
        np_.set_two_sided(True)
        np_.set_transparency(TransparencyAttrib.M_alpha)
        np_.set_depth_write(False)
        np_.set_bin('transparent', 10)
        return np_


def river_surface(st, rivers, water_y, res=.6):
    """Surface de toutes les rivières : grille sur le lit, profondeur lue dans le relief,
    courant le long du tracé le plus proche."""
    from game.world.stadium import polyline_dist_grid
    from game import config as C
    F = C.FIELD_RADIUS
    n = abs(st.hm_min)
    xs = np.arange(-n, n + res / 2, res)
    cap = 8
    near = np.full((len(xs), len(xs)), float(cap))
    for pts, w in rivers:
        near = np.minimum(near, polyline_dist_grid(xs, pts, cap) - w / 2)
    X, Z = np.meshgrid(xs, xs, indexing='ij')
    ground = st._sample_np(st.hm, X, Z)
    wet = (ground < water_y + .15) & (near < 3.5) & (np.hypot(X, Z) < F)
    # direction du courant : tangente du segment le plus proche
    flow = np.zeros(X.shape + (3,), np.float32)
    best = np.full(X.shape, 1e9)
    for pts, w in rivers:
        for (ax, az), (bx, bz) in zip(pts, pts[1:]):
            dx, dz = bx - ax, bz - az
            L2 = dx * dx + dz * dz or 1
            tt = np.clip(((X - ax) * dx + (Z - az) * dz) / L2, 0, 1)
            d = np.hypot(X - ax - dx * tt, Z - az - dz * tt)
            m = d < best
            best = np.where(m, d, best)
            L = math.sqrt(L2)
            flow[m] = (dx / L, 0, dz / L)
    depth = np.clip((water_y - ground) / .95, 0, 1)
    # cellules à garder : au moins un coin mouillé
    keep = wet[:-1, :-1] | wet[1:, :-1] | wet[:-1, 1:] | wet[1:, 1:]
    used = np.zeros(X.shape, bool)
    used[:-1, :-1] |= keep
    used[1:, :-1] |= keep
    used[:-1, 1:] |= keep
    used[1:, 1:] |= keep
    ids = np.full(X.shape, -1, np.int64)
    ids[used] = np.arange(int(used.sum()))
    verts = np.stack([X[used], np.full(int(used.sum()), water_y), Z[used]], -1)
    ii, jj = np.nonzero(keep)
    a, b, c, d = ids[ii, jj], ids[ii + 1, jj], ids[ii, jj + 1], ids[ii + 1, jj + 1]
    tris = np.stack([a, c, b, b, c, d], -1).ravel()
    return verts, tris, flow[used], depth[used]


def set_time(node, t):
    if node is not None:
        node.set_shader_input('wtime', float(t % 1000.0))

