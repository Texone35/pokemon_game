"""FPS en fenêtre, caméra posée à un endroit précis : python tools/fps_at.py x,z"""
import os, sys, time as systime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from panda3d.core import loadPrcFileData
loadPrcFileData('', 'sync-video 0')
from ursina import Entity, Ursina, application, camera, color, window, Vec3
from game import config as C
app = Ursina(title='t', size=C.WINDOW_SIZE, development_mode=False, vsync=False)
from game.interface.widgets import Banner
from game.match import Match
from game.world.geometry import set_environment, setup_sun, update_camera_uniform
class G(Entity):
    def __init__(s):
        super().__init__(); window.color = color.rgba(.55,.72,.95,1)
        set_environment(fog_color=(.55,.72,.95,1), fog_range=(140,420)); s.sun = setup_sun(resolution=C.QUALITY['shadow_resolution']); s.banner = Banner()
    def back_to_menu(s, m=None): pass
    def update(s): update_camera_uniform()
g = G(); camera.fov = 70; camera.clip_plane_far = 800
m = Match(g, {'humans': ['pikachu'], 'local': 0, 'role': 'solo', 'ai': 'facile', 'seed': 5})
for _ in range(20): app.step()
x, z = (float(a) for a in sys.argv[1].split(','))
m.player.reset(pos=Vec3(x, 0, z))
for _ in range(30): app.step()
fr = []; t1 = systime.time()
while systime.time() - t1 < 6:
    application.base.mainWinMinimized = False; f0 = systime.perf_counter(); app.step(); fr.append((systime.perf_counter()-f0)*1000)
fr.sort(); print('ACTUEL', sys.argv[1], 'FPS', round(len(fr)/6,1), 'médiane', round(fr[len(fr)//2],1), flush=True)
os._exit(0)
