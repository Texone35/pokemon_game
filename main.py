"""Pokémon Dominion (3D) - point d'entrée.

Deux équipes de 5 Pokémon s'affrontent dans un stade pour le contrôle de
5 arènes ouvertes. Vous choisissez votre Pokémon dans le salon et jouez dans
l'équipe rouge, seul ou avec un ami (partie à deux en réseau), avec des alliés
contrôlés par l'ordinateur, contre 5 adversaires.

Lancer :  python main.py
"""
import atexit

from panda3d.core import AntialiasAttrib, loadPrcFileData
from ursina import Entity, Sky, Ursina, camera, color, scene, window

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
from game.interface.loading import LoadingScreen                                               # noqa: E402
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
        """Quitte le salon et construit la partie par petites étapes derrière l'écran de chargement (la
        carte, elle, a en général fini de se construire pendant le choix des Pokémon)."""
        self.lobby.close()
        self.lobby = None
        unfreeze_shadows(self.sun)          # le stade calculera ses ombres puis les figera
        camera.fov = 70
        self.match = Match(self, setup, defer=True)
        types = setup['preload'].types if setup.get('preload') else C.draw_map(setup.get('seed') or 0)
        self.loading = LoadingScreen(types)

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
        if self.loading is not None and self.match is not None:
            from ursina import destroy, time as utime
            ready = self.match.step(.012)               # une petite étape par image : l'écran reste animé
            self.loading.set(1.0 if ready else self.match.load_progress,
                             'Prêt !' if ready else self.match.load_label)
            self.loading.tick(utime.dt)
            if ready and self.loading.shown > .985:     # la barre a fini de se remplir : la partie commence
                destroy(self.loading)
                self.loading = None
                self.match.enabled = True


game = Game()

if __name__ == '__main__':
    app.run()
