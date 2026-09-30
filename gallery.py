"""Galerie du décor : chaque élément de la carte posé à la suite sur un terrain vide, numéroté.

Utilisé par showroom.py (touche G ou `python showroom.py --galerie`). On réutilise les vraies
fonctions de construction du stade (arbres, rochers, falaises, pont, volcan...) : ce qu'on voit ici
est exactement ce qui sera posé dans la carte.
"""
import math
import random

import numpy as np
from ursina import Text, color

from game import config as C
from game.world import biomes
from game.world import stadium as S
from game.world.geometry import MeshBuilder
from game.world.water import WaterBuilder, set_time

ROW_SMALL, ROW_WALLS, ROW_BIG = 0, 30, 75      # rangées : petits éléments, bords de massifs, grands décors
BIG_STEP = 34                                  # écart entre deux grands décors
BRIDGE_X = 17 * 7 + 14                         # le pont, au bout de la rangée des bords de massifs
BIG_PER_ROW = 9                                # grands décors par rangée
X0, X1, Z0, Z1 = -30, 34 * 8 + 70, -30, 180    # étendue du terrain


class Gallery(S.Stadium):
    """Faux stade : mêmes outils de construction, mais un terrain plat et des éléments alignés."""

    def __init__(self, root):
        self.root = root
        self.rng = random.Random(11)
        self.obstacles, self.grid, self.paths = [], {}, []
        self.stand_angles = {}
        self.wb = WaterBuilder()
        self.emitters = []
        self.terrain_marks = []
        self.time = 0.0
        self.items = []               # (n°, nom, x, z, distance de vue)
        self.river = None
        self._plan_paths()            # utilisé par les emplacements de l'antre de Torterra
        self._plan_big()
        self._build_heightmap()
        self._new_builders()
        self._build_ground()
        self._build_small()
        self._build_walls()
        self._build_bridge()
        self.landmarks.build()
        self._flush()
        self._labels()

    # ------------------------------------------------------------ outils
    def _item(self, name, x, z, dist):
        self.items.append((len(self.items) + 1, name, x, z, dist))

    def wall_dist(self, x, z):
        return 10.0                   # tout est « au cœur d'un massif » : les cascades font face au sud

    def block(self, *a, **k):
        pass

    # ------------------------------------------------------------ grands décors
    def _plan_big(self):
        """Laisse les grands décors choisir leur taille et leurs reliefs, mais sur des emplacements
        alignés au lieu des massifs de la carte."""
        from game.world.landmarks import Landmarks
        lm = self.landmarks = Landmarks(self)
        slot = iter(range(100))

        def deep(x, z, search=10.0):
            i = next(slot)
            return 20 + (i % BIG_PER_ROW) * BIG_STEP, ROW_BIG + (i // BIG_PER_ROW) * 55, 8.0
        lm._deep = deep
        lm.plan()
        items = []
        for kind, x, z, r, data in lm.items:
            if kind == 'torterra':    # l'antre se construit autour d'un camp : on le recale derrière l'arbre
                tx, tz, d = data['tree']
                data['back'] = 0
                x, z = tx, tz - 11
            items.append((kind, x, z, r, data))
        lm.items = items
        self._big = [(kind, *(data['tree'][:2] if kind == 'torterra' else (x, z)), r) for kind, x, z, r, data in items]

    def _build_heightmap(self):
        n = X1 + 20
        xs = np.arange(X0 - 10, n + S.HM_RES / 2, S.HM_RES)
        X, Z = np.meshgrid(xs, xs, indexing='ij')
        H = np.zeros_like(X)
        amp = C.QUALITY['relief']
        for x0, z0, r, fn, mode in sorted(self.terrain_marks, key=lambda m: m[4] == 'flat'):
            d = np.hypot(X - x0, Z - z0) / r
            if mode == 'add':
                H += amp * fn(d)
            else:
                target, m = fn(d)
                H = H * (1 - m) + target * m
        # lit de la rivière sous le pont
        self.bridge_x = BRIDGE_X
        self.river_d = self._river_dist(X, Z)
        H -= 1.3 * (1 - S._smoothstep(-2.4, .9, self.river_d))
        self.hm, self.hm_n, self.hm_min = H, len(xs), xs[0]
        self.hm_gx, self.hm_gz = np.gradient(H, S.HM_RES)

    def _river_dist(self, x, z):
        """Distance au bord d'une rivière droite (Est-Ouest) qui passe sous le pont."""
        bx = self.bridge_x
        along = np.clip(x, bx - 14, bx + 14)
        return np.hypot(x - along, z - ROW_WALLS) - 2.5

    def _build_ground(self):
        xs = np.arange(X0, X1 + .01, 1.0)
        zs = np.arange(Z0, Z1 + .01, 1.0)
        x, z = np.meshgrid(xs, zs, indexing='ij')
        y = self._sample_np(self.hm, x, z)
        gx, gz = self._sample_np(self.hm_gx, x, z), self._sample_np(self.hm_gz, x, z)
        norms = np.stack([-gx, np.ones_like(gx), -gz], -1)
        norms /= np.linalg.norm(norms, axis=-1, keepdims=True)
        noise = np.clip(.5 + .35 * np.sin(x * .12 + np.sin(z * .08) * 2) * np.cos(z * .1 + np.sin(x * .06))
                        + .15 * np.sin(x * .45 + z * .38), 0, 1)[..., None]
        a_, b2 = (np.array(c) for c in biomes.LAWN[biomes.JUNGLE])
        col = a_ * (1 - noise) + b2 * noise
        slope = np.hypot(gx, gz)[..., None]
        col = col * (1 - S._smoothstep(.45, 1.1, slope)) + np.array([.48, .5, .5]) * S._smoothstep(.45, 1.1, slope)
        river_d = self._river_dist(x, z)
        bank = (1 - S._smoothstep(.2, 2.0, river_d))[..., None]
        col = col * (1 - bank) + np.array(biomes.BANK[biomes.JUNGLE]) * bank
        depth = np.clip((S.WATER_Y - y) / 1.0, 0, 1)[..., None]
        col = col * (1 - depth) + np.array([.08, .3, .42]) * depth
        glow = np.zeros_like(col[..., :1])
        self.landmarks.paint(x, z, y, col, glow)
        col = np.concatenate([col, 1 + glow], -1)
        NX, NZ = x.shape
        idx = np.arange(NX * NZ).reshape(NX, NZ)
        a, b_, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
        tris = np.stack([a, b_, c, c, b_, d], -1).reshape(-1)
        verts = np.stack([x, y, z], -1).reshape(-1, 3)
        MeshBuilder().add_raw(verts, tris, norms.reshape(-1, 3), col.reshape(-1, 4)).static(
            self.root, detail=C.QUALITY.get('detail', 1.0))

    # ------------------------------------------------------------ petits éléments
    def _build_small(self):
        b, rng = self.b, self.rng
        J, R, P, E, W, Fe = biomes.JUNGLE, biomes.ROCHE, biomes.PLANTE, biomes.ELECTRIK, biomes.EAU, biomes.FEU
        trees = [('Feuillu (jungle)', 'broadleaf', J), ('Feuillu (plante)', 'broadleaf', P),
                 ('Feuillu (électrik)', 'broadleaf', E), ('Conifère (jungle)', 'conifer', J),
                 ('Pin (roche)', 'conifer', R), ('Palmier (eau)', 'tropical', W), ('Palmier (plante)', 'tropical', P),
                 ('Arbre en fleurs', 'blossom', W), ('Fougère géante', 'fern', P), ('Buisson fleuri', 'bush', J),
                 ('Herbe sèche', 'dry', R), ('Cheminée de fée', 'hoodoo', R), ('Rochers de grès', 'sandstone', R),
                 ('Arbre calciné', 'dead', Fe), ('Orgues de basalte', 'basalt', Fe), ('Obsidienne', 'obsidian', Fe),
                 ('Cheminée volcanique', 'vent', Fe), ('Cristaux', 'crystal', W)]
        x = 0
        for name, kind, bio in trees:
            self._tree(b, x, ROW_SMALL, 1.2, kind, bio)
            self._item(name, x, ROW_SMALL, 14)
            x += 9
        self._crystals(b, x, ROW_SMALL, 1.0, S.VOLT)
        self._item('Cristaux électrik', x, ROW_SMALL, 12)
        x += 9
        for s in (.5, 1.0, 1.6):
            self._rock(b, x + (s - 1) * 2.5, ROW_SMALL, s, moss=.5)
        self._item('Rochers (3 tailles)', x, ROW_SMALL, 12)
        x += 13
        self._outcrop(b, x, ROW_SMALL, block=False)
        self._item('Massif rocheux', x + 1.5, ROW_SMALL, 20)
        x += 14
        for i in range(-8, 9):        # hautes herbes (cachettes) : touffe ovale, même recette que la carte
            for j in range(-5, 6):
                ex, ez = i * .5 / 4.2, j * .5 / 2.4
                d = 1 - math.hypot(ex, ez)                    # 1 au centre, 0 au bord de l'ovale
                if d <= 0 or (i + j) % 2:
                    continue
                bx = x + 4 + i * .5 + rng.uniform(-.25, .25)
                bz = ROW_SMALL + j * .5 + rng.uniform(-.25, .25)
                sc = .62 + .38 * S._smoothstep(.05, .45, d)
                self._grass_clump(b, bx, bz, sc, rng.choice(S.BUSH_GREENS), mound=(i % 4 == 0 and j % 2 == 0))
        self._pokemon(x + 4, ROW_SMALL - 4.5)
        self._item('Hautes herbes + barres de vie', x + 4, ROW_SMALL - 2, 14)
        x += 14
        b.add('cyl6', (x, .2, ROW_SMALL), (.18, .4, .18), col=color.rgb(.95, .92, .85))
        b.add('dome', (x, .35, ROW_SMALL), (.6, .4, .6), col=color.rgb(.9, .2, .15))
        self._item('Champignon', x, ROW_SMALL, 6)

    def _pokemon(self, x, z):
        """Quelques Pokémon devant les hautes herbes, avec leur barre de vie (PV qui varient)."""
        from game.pokemon.creatures import Creature
        from game.pokemon.healthbar import HealthBar
        from game.pokemon.units import ALLY_BAR, LOCAL_BADGE, LOCAL_BAR
        self.demo = []
        red, blue = C.TEAMS['rouge']['color'], C.TEAMS['bleu']['color']
        cast = [('pikachu', 5, LOCAL_BAR, LOCAL_BADGE, None), ('carapuce', 3, ALLY_BAR, ALLY_BAR, 'J2'),
                ('salameche', 8, red, red, None), ('bulbizarre', 11, blue, blue, None)]
        for k, (sp, level, col, badge, label) in enumerate(cast):
            d = C.SPECIES[sp]
            c = Creature(sp, parent=self.root, position=(x - 4.5 + k * 3, 0, z), scale=d['scale'])
            c.rotation_y = 180
            w = 1.6
            hb = HealthBar(c, d['scale'] * 1.5 + .5, w, col, badge, label, ALLY_BAR)
            from game.pokemon import kit
            hp = kit.team_stats(sp, sp, level)['hp']
            hb.set_level(level)
            hb.set(hp * (1 - .2 * k), hp)
            self.demo.append([c, hb, hp, hp * (1 - .2 * k)])
        self.demo_t = 0.0

    # ------------------------------------------------------------ bords des massifs
    def _build_walls(self):
        b = self.b
        walls = [('Falaise (jungle)', lambda x, z, k: self._cliff(b, x, z, 0, 1)),
                 ("Rideau d'arbres (jungle)", lambda x, z, k: self._grove(b, x, z, 0, 1, k, biomes.JUNGLE)),
                 ("Rideau d'arbres (plante)", lambda x, z, k: self._grove(b, x, z, 0, 1, k, biomes.PLANTE)),
                 ("Rideau d'arbres (eau)", lambda x, z, k: self._grove(b, x, z, 0, 1, k, biomes.EAU)),
                 ("Rideau d'arbres (électrik)", lambda x, z, k: self._grove(b, x, z, 0, 1, k, biomes.ELECTRIK)),
                 ('Pied de plateau (roche)', lambda x, z, k: self._mesa_foot(b, x, z, 0, 1, k)),
                 ('Paroi de basalte (feu)', lambda x, z, k: self._basalt_wall(b, x, z, 0, 1, k))]
        x = 0
        for name, fn in walls:
            for k in range(6):
                fn(x + k * 1.9, ROW_WALLS, k)
            self._item(name, x + 5, ROW_WALLS, 20)
            x += 17

    def _build_bridge(self):
        """Pont de bois sur une rivière animée, avec la voie dallée de chaque côté."""
        x = self.bridge_x
        river = [((x - 14, ROW_WALLS), (x + 14, ROW_WALLS)), 5.0]
        lane = [(x, ROW_WALLS - 12), (x, ROW_WALLS + 12)]
        saved = S.RIVERS
        S.RIVERS = [([river[0][0], river[0][1]], river[1])]
        try:
            self._build_bridges([(lane, 4.6)])
        finally:
            S.RIVERS = saved
        for z0, z1 in ((ROW_WALLS - 12, ROW_WALLS - 3.3), (ROW_WALLS + 3.3, ROW_WALLS + 12)):
            self._ribbon(self.flat, [(x, z0), (x, z1)], 5.9, S.LANE_EDGE, .04, h=.08, disc=False)
            self._ribbon(self.flat, [(x, z0), (x, z1)], 4.6, S.LANE, .07, h=.08, disc=False)
        # surface de l'eau : grille sur le lit, profondeur lue dans le relief
        xs = np.arange(x - 16, x + 16.01, .6)
        zs = np.arange(ROW_WALLS - 5, ROW_WALLS + 5.01, .6)
        X, Z = np.meshgrid(xs, zs, indexing='ij')
        ground = self._sample_np(self.hm, X, Z)
        depth = np.clip((S.WATER_Y - ground) / .95, 0, 1)
        NX, NZ = X.shape
        idx = np.arange(NX * NZ).reshape(NX, NZ)
        a, b_, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
        tris = np.stack([a, b_, c, c, b_, d], -1).ravel()
        verts = np.stack([X.ravel(), np.full(X.size, S.WATER_Y), Z.ravel()], -1)
        self.wb.add_raw(verts, tris, (1, 0, 0), depth.ravel(), speed=.45)
        self._item('Pont de bois + rivière', x, ROW_WALLS, 22)

    # ------------------------------------------------------------ étiquettes
    def _labels(self):
        names = {'volcano': 'Volcan', 'falls': 'Cascade', 'lavafall': 'Chute de lave', 'giant_tree': 'Arbre millénaire',
                 'tesla': 'Tour Tesla', 'pylon': 'Pylône', 'ruins': 'Ruines', 'arch': 'Arche de grès',
                 'torterra': 'Antre de Torterra', 'crystal_grove': 'Cristaux géants', 'vents': 'Cheminées volcaniques'}
        for kind, x, z, r in self._big:
            self._item(names.get(kind, kind), x, z, max(26, r * 4.2))
        self.items.sort(key=lambda it: (it[3], it[2]))            # rangée de devant d'abord
        self.items = [(i + 1,) + it[1:] for i, it in enumerate(self.items)]
        for n, name, x, z, dist in self.items:
            top = self.ground_y(x, z) + {ROW_SMALL: 8, ROW_WALLS: 10}.get(z, 18)
            Text(parent=self.root, text=f'{n}. {name}', position=(x, top, z), origin=(0, 0), scale=34,
                 billboard=True, color=color.white, background=True)

    # ------------------------------------------------------------ vues et animation
    def views(self):
        out = [("Galerie - vue d'ensemble", 150, 60, 0, 55, 250)]
        for n, name, x, z, dist in self.items:
            out.append((f'{n}. {name}', x, z, 0, 24, dist * 1.15))
        return out

    def update(self, dt, focus=None):
        self.time += dt
        self.demo_t += dt
        for i, item in enumerate(self.demo):             # coups et soins réguliers : on voit la traînée
            c, hb, max_hp, hp = item
            if self.demo_t > 2.5:
                hp = max_hp if hp < max_hp * .25 else hp - max_hp * random.uniform(.1, .3)
                item[3] = hp
                hb.set(hp, max_hp)
            hb.tick(dt)
            c.animate(dt)
        if self.demo_t > 2.5:
            self.demo_t = 0.0
        set_time(self.water_node, self.time)
        self._update_emitters(dt, focus)
