"""Pokémon Arènes 3D - point d'entrée.

Lancer :  python main.py
"""
from ursina import Entity, Sky, Text, Ursina, Vec3, camera, color, window

import config as C

app = Ursina(title='Pokémon - Les 5 Arènes', size=C.WINDOW_SIZE, borderless=False,
             development_mode=False, vsync=True)

# les modules suivants créent des shaders/entités : ils doivent être importés après Ursina()
from battle import Battle                       # noqa: E402
from geometry import ENV, set_environment, update_camera_uniform  # noqa: E402
from ui import Banner                           # noqa: E402
from world import Overworld                     # noqa: E402

DEFAULT_ENV = dict(ENV)


class Game(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgb(.62, .8, .95)
        window.fps_counter.enabled = C.SHOW_FPS
        camera.fov = 75   # FOV horizontal dans Ursina
        camera.clip_plane_far = 600
        self.sky = Sky(color=color.rgb(.62, .8, .95))
        set_environment()
        self.overworld = Overworld(self)
        self.battle = None
        self.banner = Banner()
        self.banner.show('Bienvenue ! Battez les 5 arènes de l\'île pour devenir Maître Pokémon !', 4)

    def start_battle(self, type_key):
        self.overworld.hide()
        self.battle = Battle(self, type_key)

    def end_battle(self, type_key, won):
        if self.battle:
            self.battle.cleanup()
            self.battle = None
        set_environment(**{k: v for k, v in DEFAULT_ENV.items()})
        self.sky.color = color.rgb(.62, .8, .95)
        self.overworld.place_player_at_door(type_key)
        self.overworld.show()
        if won:
            a = next(a for a in self.overworld.arenas if a['type'] == type_key)
            first = not a['beaten']
            a['beaten'] = True
            n = self.overworld.refresh_badges()
            if n == len(self.overworld.arenas) and first:
                self.banner.show('Félicitations ! Vous avez les 5 badges : vous êtes Maître Pokémon !', 6,
                                 text_color=color.rgb(1, .85, .3), big=False)
            elif first:
                self.banner.show(f'Badge obtenu ! ({n} / 5)', 3, text_color=color.rgb(1, .85, .3))
        elif won is False:
            self.banner.show('Pikachu a été soigné. Réessayez quand vous voulez !', 3)

    def update(self):
        update_camera_uniform()


game = Game()

if __name__ == '__main__':
    app.run()
