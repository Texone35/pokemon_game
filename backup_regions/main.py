"""Pokémon - Les 5 Régions (3D) - point d'entrée.

L'île est divisée en 5 régions typiques (Feu, Eau, Plante, Roche, Glace).
Chaque région est gardée par un Pokémon boss que l'on combat sur place.

Lancer :  python main.py
"""
from ursina import Entity, Sky, Ursina, camera, color, window

import config as C

app = Ursina(title='Pokémon - Les 5 Régions', size=C.WINDOW_SIZE, borderless=False,
             development_mode=False, vsync=True)

# les modules suivants créent des shaders/entités : ils doivent être importés après Ursina()
from battle import Battle                       # noqa: E402
from geometry import set_environment, update_camera_uniform  # noqa: E402
from ui import Banner                           # noqa: E402
from world import Overworld                     # noqa: E402


class Game(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgb(.62, .8, .95)
        window.fps_counter.enabled = C.SHOW_FPS
        camera.fov = 75   # FOV horizontal dans Ursina
        camera.clip_plane_far = 700
        self.sky = Sky(color=color.rgb(.62, .8, .95))
        set_environment()
        self.battle = None
        self.banner = Banner()
        self.overworld = Overworld(self)
        self.banner.show("Bienvenue ! Explorez les 5 régions de l'île et battez leurs boss !", 4)

    def start_battle(self, type_key):
        reg = self.overworld.region(type_key)
        start = self.overworld.enter_battle(reg)
        self.battle = Battle(self, type_key, reg['lair'], reg['heading'], start)

    def end_battle(self, type_key, won):
        pos = None
        if self.battle:
            pos = self.battle.player_world_position()
            self.battle.cleanup()
            self.battle = None
        first = won and not self.overworld.region(type_key)['beaten']
        self.overworld.exit_battle(type_key, won, pos)
        if won:
            n = self.overworld.refresh_badges()
            if n == len(self.overworld.regions) and first:
                self.banner.show('Félicitations ! Les 5 boss sont vaincus : vous êtes Maître Pokémon !', 6,
                                 text_color=color.rgb(1, .85, .3), big=False)
            elif first:
                self.banner.show(f'Boss vaincu ! ({n} / 5)', 3, text_color=color.rgb(1, .85, .3))
        elif won is False:
            self.banner.show('Pikachu a été soigné. Revenez défier le boss quand vous voulez !', 3)

    def update(self):
        update_camera_uniform()


game = Game()

if __name__ == '__main__':
    app.run()
