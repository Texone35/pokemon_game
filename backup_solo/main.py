"""Pokémon Dominion (3D) - point d'entrée.

Deux équipes de 5 Pokémon s'affrontent dans un stade pour le contrôle de
5 arènes ouvertes. Vous jouez Pikachu dans l'équipe rouge, avec 4 alliés
contrôlés par l'ordinateur, contre 5 adversaires.

Lancer :  python main.py
"""
from panda3d.core import AntialiasAttrib, loadPrcFileData
from ursina import Entity, Sky, Ursina, camera, color, scene, window

import config as C

# Anticrénelage matériel (MSAA) : très coûteux sur certaines puces graphiques
# intégrées (Intel), donc désactivé par défaut. Mettre MSAA = 4 pour l'activer.
MSAA = C.QUALITY['msaa']
if MSAA:
    loadPrcFileData('', 'framebuffer-multisample 1')
    loadPrcFileData('', f'multisamples {MSAA}')

app = Ursina(title='Pokémon Dominion', size=C.WINDOW_SIZE, borderless=False,
             development_mode=False, vsync=True)

# les modules suivants créent des shaders/entités : ils doivent être importés après Ursina()
from geometry import set_environment, setup_sun, update_camera_uniform  # noqa: E402
from match import Match                         # noqa: E402
from ui import Banner                           # noqa: E402

SKY = (.55, .72, .95, 1)


class Game(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgba(*SKY)
        window.fps_counter.enabled = C.SHOW_FPS
        camera.fov = 70
        camera.clip_plane_far = 800
        if MSAA:
            scene.setAntialias(AntialiasAttrib.MMultisample)
        self.sky = Sky(texture='sky_default')
        set_environment(fog_color=SKY, fog_range=(140, 420))
        self.sun = setup_sun(resolution=C.QUALITY['shadow_resolution'])
        self.banner = Banner()
        self.match = Match(self)

    def update(self):
        update_camera_uniform()


game = Game()

if __name__ == '__main__':
    app.run()
