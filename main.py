"""Pokémon Dominion (3D) - point d'entrée.

Deux équipes de 5 Pokémon s'affrontent dans un stade pour le contrôle de
5 arènes ouvertes. Vous choisissez votre Pokémon dans le salon et jouez dans
l'équipe rouge, seul ou avec un ami (partie à deux en réseau), avec des alliés
contrôlés par l'ordinateur, contre 5 adversaires.

Lancer :  python main.py
"""
import atexit

from panda3d.core import AntialiasAttrib, loadPrcFileData
from ursina import Entity, Sky, Text, Ursina, camera, color, invoke, scene, window

from game import config as C
# Anticrénelage matériel (MSAA) : très coûteux sur certaines puces graphiques
# intégrées (Intel), donc désactivé par défaut. Mettre MSAA = 4 pour l'activer.
MSAA = C.QUALITY['msaa']
if MSAA:
    loadPrcFileData('', 'framebuffer-multisample 1')
    loadPrcFileData('', f'multisamples {MSAA}')

app = Ursina(title='Pokémon Dominion', size=C.WINDOW_SIZE, borderless=False,
             development_mode=False, vsync=True)

# les modules suivants créent des shaders/entités : ils doivent être importés après Ursina()
from game.interface.lobby import Lobby                                                         # noqa: E402
from game.interface.widgets import Banner                                                      # noqa: E402
from game.match import Match                                                                   # noqa: E402
from game.world.geometry import set_environment, setup_sun, unfreeze_shadows, update_camera_uniform  # noqa: E402

SKY = (.55, .72, .95, 1)


class Game(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgba(*SKY)
        window.fps_counter.enabled = C.SHOW_FPS
        window.exit_button.enabled = False
        camera.fov = 70
        camera.clip_plane_far = 800
        if MSAA:
            scene.setAntialias(AntialiasAttrib.MMultisample)
        self.sky = Sky(texture='sky_default')
        set_environment(fog_color=SKY, fog_range=(140, 420))
        self.sun = setup_sun(resolution=C.QUALITY['shadow_resolution'])
        self.banner = Banner()
        self.match = None
        self.lobby = Lobby(self)
        self.loading = None
        atexit.register(self._shutdown)

    def start_match(self, setup):
        """Quitte le salon et construit le stade (quelques secondes)."""
        self.lobby.close()
        self.lobby = None
        unfreeze_shadows(self.sun)          # le stade calculera ses ombres puis les figera
        self.loading = Text(parent=camera.ui, text='Chargement du stade...', origin=(0, 0), scale=2,
                            color=color.rgb(1, .9, .5))
        invoke(self._build_match, setup, delay=.05)       # laisse s'afficher le message d'abord

    def _build_match(self, setup):
        from ursina import destroy
        camera.fov = 70
        self.match = Match(self, setup)
        destroy(self.loading)
        self.loading = None

    def back_to_menu(self, message=None):
        if self.match is not None:
            self.match.dispose()
            self.match = None
        self.banner.enabled = False
        self.lobby = Lobby(self, message)

    def _shutdown(self):
        """Fermeture du jeu : prévient l'autre joueur et referme le port de la box."""
        try:
            if self.match is not None and self.match.net is not None:
                self.match.net.close()
                host = getattr(self.match.net, 'host', None)
                if host is not None:
                    host.close()
            if self.lobby is not None:
                self.lobby._close_net(notify=True)
        except Exception:
            pass

    def update(self):
        update_camera_uniform()


game = Game()

if __name__ == '__main__':
    app.run()
