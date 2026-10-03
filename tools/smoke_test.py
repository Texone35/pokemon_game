"""Test de lancement automatique : une partie complète jouée par l'ordinateur, sans fenêtre.

Le Pokémon du joueur est piloté automatiquement (déplacements de l'IA, attaques au hasard,
achats). Le temps de jeu est simulé par pas fixes : plusieurs minutes de partie passent en
quelques dizaines de secondes. Le test échoue (code de sortie 1) à la moindre erreur.

Lancer :  python tools/smoke_test.py                 (3 minutes de jeu, IA facile)
          python tools/smoke_test.py --minutes 10 --ai expert --species salameche
          python tools/smoke_test.py --fps 15         (mesure aussi les FPS pendant 15 s réelles)
          python tools/smoke_test.py --window         (fenêtre visible, pour regarder)
"""
import argparse
import os
import random
import sys
import time as systime
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ap = argparse.ArgumentParser()
ap.add_argument('--minutes', type=float, default=3.0)
ap.add_argument('--ai', default='facile')
ap.add_argument('--species', default=None)
ap.add_argument('--fps', type=float, default=0.0, help='secondes réelles de mesure des FPS (0 = pas de mesure)')
ap.add_argument('--window', action='store_true')
ap.add_argument('--seed', type=int, default=1)
ap.add_argument('--report', action='store_true', help='affiche niveaux, argent et stats à chaque minute')
ap.add_argument('--no-waves', action='store_true', help='sans vagues de sbires (comparaison)')
ap.add_argument('--profile', type=float, default=0.0, help='profile N secondes réelles en fin de partie')
ap.add_argument('--census', action='store_true', help="détail des entités parcourues à chaque image")
ap.add_argument('--click-test', action='store_true', help="teste le déplacement et l'attaque au clic")
ap.add_argument('--map', default=None, help="impose les types des arènes : nord,ouest,est,sud_ouest,sud_est "
                                             "(ex. glace,poison,psy,spectre,dragon)")
ap.add_argument('--capture-test', action='store_true', help="teste la capture à la touche et le champ de force des bases")
ap.add_argument('--bot-player', action='store_true', help="le Pokémon du joueur joue exactement comme une IA")
ap.add_argument('--fast', action='store_true', help="n'affiche pas les images (simulation plus rapide)")
ap.add_argument('--log', default=None, help='enregistre le déroulé de la partie (JSON) pour tools/balance_report.py')
ap.add_argument('--build', default='standard', help='build du Pokémon du joueur')
ap.add_argument('--transform', action='store_true', help='pendant la capture : transformation active')
ap.add_argument('--level', type=int, default=1, help='niveau de départ du Pokémon du joueur')
ap.add_argument('--shot', default=None, help="enregistre une capture d'écran à la fin (chemin .png)")
ap.add_argument('--at', default=None, help='pendant la capture : place le joueur en x,z')
ap.add_argument('--shop', action='store_true', help='pendant la capture : boutique ouverte')
ap.add_argument('--aim', default=None, help="pendant la capture : touche d'attaque en cours de visée (ex. l)")
args = ap.parse_args()

from panda3d.core import ClockObject, loadPrcFileData  # noqa: E402

loadPrcFileData('', 'sync-video 0')
from ursina import Entity, Ursina, application, camera, color, scene, window  # noqa: E402

from game import config as C  # noqa: E402

if args.no_waves:
    C.WAVES['pool'] = 0
app = Ursina(title='smoke test', size=C.WINDOW_SIZE, development_mode=False, vsync=False,
             window_type='onscreen' if args.window else 'offscreen')

from game.interface.widgets import Banner  # noqa: E402

# mesures : Panda3D se met en pause quand il croit sa fenêtre réduite (fenêtre de test en arrière-plan)
_win_event = application.base.windowEvent


def _never_minimized(win):
    _win_event(win)
    application.base.mainWinMinimized = False


application.base.accept('window-event', _never_minimized)
from game.match import Match  # noqa: E402
from game.pokemon.units import PlayerBrain  # noqa: E402
from tools.pilot import Pilot  # noqa: E402
from game.world.geometry import set_environment, setup_sun, update_camera_uniform  # noqa: E402


class GameStub(Entity):
    def __init__(self):
        super().__init__()
        window.color = color.rgba(.55, .72, .95, 1)
        set_environment(fog_color=(.55, .72, .95, 1), fog_range=(140, 420))
        self.sun = setup_sun(resolution=C.QUALITY['shadow_resolution'])
        self.banner = Banner()
        self.match = None

    def back_to_menu(self, message=None):
        pass

    def update(self):
        update_camera_uniform()


def check_themes():
    """Chaque type d'arène tirable doit avoir tout son thème (sinon une partie planterait au tirage)."""
    from game.world import biomes
    from game.world.arenas import ArenaDecor
    from game.world.landmarks import Landmarks
    from game.world.stadium import FLORA_T, GREENS_T
    from game import match as M
    tables = {'LAWN_T': biomes.LAWN_T, 'TRAIL_T': biomes.TRAIL_T, 'FOREST_T': biomes.FOREST_T,
              'ROCK_T': biomes.ROCK_T, 'BANK_T': biomes.BANK_T, 'RELIEF_T': biomes.RELIEF_T, 'GREENS_T': GREENS_T,
              'FLORA_T': FLORA_T, 'MAP_GROUND': M.MAP_GROUND, 'MAP_MASSIF': M.MAP_MASSIF,
              'WEATHER_OF': C.WEATHER_OF, 'ARENA_BONUS': C.ARENA_BONUS, 'TYPES': C.TYPES}
    for t in C.ARENA_TYPES:
        missing = [n for n, tb in tables.items() if t not in tb]
        from game.world.fx import ArenaWeather
        missing += [f for f, cls in (('build_' + t, ArenaDecor), ('plan_' + t, Landmarks),
                                     ('_' + C.WEATHER_OF.get(t, '?'), ArenaWeather)) if not hasattr(cls, f)]
        assert not missing, f'thème {t} incomplet : {missing}'
        assert C.WEATHER_OF[t] in C.WEATHERS, f'météo inconnue pour {t}'
    print(f'thèmes : {len(C.ARENA_TYPES)} types tirables complets', flush=True)


def main():
    check_themes()
    if args.map:                                          # carte imposée (test d'un thème)
        forced = dict(zip([a['key'] for a in C.ARENAS], args.map.split(',')))
        C.draw_map = lambda seed: dict(forced)
    random.seed(args.seed)
    game = GameStub()
    camera.fov = 70
    camera.clip_plane_far = 800
    species = args.species or random.choice(C.PLAYABLE)
    t0 = systime.time()
    match = Match(game, {'humans': [species], 'local': 0, 'role': 'solo', 'ai': args.ai, 'seed': args.seed,
                          'builds': [args.build]})
    game.match = match
    GAME['match'] = match
    real_update = match.update

    def timed_update():
        f0 = systime.perf_counter()
        real_update()
        GAME['py'].append((systime.perf_counter() - f0) * 1000)
    match.update = timed_update
    match.player.brain = Pilot(match.player, match)
    if args.bot_player:                                   # équilibrage : même jeu que les IA
        pb = match.player.brain
        del pb.bot.use_moves
        pb.t = 1e9
        pb.bot.goal = None
        match.player.role = C.ROSTERS['bleu'][0]['role']       # comme son vis-à-vis bleu (jungle)
    if args.level > 1:
        match.player.set_level(args.level, show=False)
    match._build_slots()
    print(f'Stade construit en {systime.time() - t0:.1f} s  (joueur : {species}, IA {args.ai})', flush=True)

    if args.click_test:
        click_test(match)
        return
    if args.capture_test:
        capture_test(match)
        return

    # FPS réels, en temps réel, au début de la partie (tous les Pokémon en jeu)
    if args.fps:
        application.base.mainWinMinimized = False
        for _ in range(10):
            app.step()
        n, t1 = 0, systime.time()
        while systime.time() - t1 < args.fps:
            application.base.mainWinMinimized = False
            app.step()
            n += 1
        print(f'FPS : {n / (systime.time() - t1):.1f}', flush=True)

    # temps simulé : 20 images par seconde de jeu, quel que soit le temps réel
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setFrameRate(20)
    frames = int(args.minutes * 60 * 20)
    t1 = systime.time()
    next_report = 60
    log = {'species': species, 'build': args.build, 'ai': args.ai, 'seed': args.seed, 'minutes': [], 'levels': {}}
    next_log = 30
    for _ in range(8):                               # la partie finit de se préparer (ombres, etc.)
        app.step()
    if args.fast:
        application.base.win.set_active(False)
    for i in range(frames):
        application.base.mainWinMinimized = False
        app.step()
        if args.log and match.time >= next_log:
            next_log += 30
            log['minutes'].append(snapshot(match))
        for u in match.units:
            if u.kind == 'pokemon':
                lv = log['levels'].setdefault(str(u.uid), {})
                if str(u.level) not in lv:
                    lv[str(u.level)] = round(match.time, 1)
        if match.state == 'end':
            break
        if args.report and match.time >= next_report:
            next_report += 60
            report(match)
    if args.log:
        import json
        log['minutes'].append(snapshot(match))
        log['score'] = dict(match.score)
        log['time'] = match.time
        log['units'] = {str(u.uid): {'line': u.species, 'build': u.build, 'team': u.team, 'human': u.is_player,
                                     'curve': C.LINES[u.species]['curve'], 'role': C.LINES[u.species]['role']}
                        for u in match.units if u.kind == 'pokemon'}
        with open(args.log, 'w', encoding='utf-8') as f:
            json.dump(log, f)
    if args.fast:
        application.base.win.set_active(True)
    if args.fps:
        measure_fps(args.fps, 'fin de partie')
    if args.profile and args.at:                       # profilage à un endroit précis (arène tenue)
        from ursina import Vec3
        x, z = (float(v) for v in args.at.split(','))
        a = min(match.arenas, key=lambda a: (a['pos'] - Vec3(x, 0, z)).length())
        a['owner'], a['control'] = match.player.team, 1.0
        match.player.reset(pos=Vec3(x, 0, z))
        match.player.brain = PlayerBrain(match.player, match)
    if args.profile:
        import cProfile
        import pstats
        pr = cProfile.Profile()
        pr.enable()
        measure_fps(args.profile, 'profilage')
        pr.disable()
        st = pstats.Stats(pr); st.sort_stats('tottime').print_stats(14); st.sort_stats('cumulative').print_stats('pokemon_game', 14)
    if args.shot:
        shot(match)
    print(f'{match.time / 60:.1f} min de jeu simulées en {systime.time() - t1:.0f} s réelles ; '
          f"score Rouge {int(match.score['rouge'])} - {int(match.score['bleu'])} Bleue", flush=True)
    report(match)


def shot(match):
    """Capture d'écran de la partie (après quelques images en temps réel)."""
    from panda3d.core import Filename
    pl = match.player
    if args.aim:
        mv = next((mv for mv in pl.moves if mv['key'] == args.aim), None)
        if mv is not None:
            pl.brain.aiming = mv['slot']
            target = pl.position + pl.facing() * 8
            pl.brain.cursor = lambda: target
    if os.environ.get('MAPVIEW'):                      # vue de toute la carte (touche Tab)
        match.cam_mode = 'map'
        for _ in range(60):
            app.step()
    if args.shop:
        match.toggle_shop()
    if args.transform and pl.alive:
        if pl.transform_kind is None:
            pl.transform_cd = 0
            pl.start_transform()
    if args.at:
        from ursina import Vec3
        x, z = (float(v) for v in args.at.split(','))
        pl.reset(pos=Vec3(x, 0, z))
        pl.brain = PlayerBrain(pl, match)
        match.cam_target = Vec3(x, pl.position.y + 1.5, z)
        match.cam_dist = float(os.environ.get('CAM_DIST', match.cam_dist))
    for _ in range(3):
        application.base.mainWinMinimized = False
        app.step()
    application.base.win.save_screenshot(Filename.from_os_specific(os.path.abspath(args.shot)))
    print('capture :', args.shot, flush=True)


def capture_test(match):
    """Capture à la touche (immobile, la tour ne vise plus le capteur) et base adverse infranchissable."""
    from ursina import Vec3
    from game.world.stadium import BASE_SHIELD
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setFrameRate(20)
    for _ in range(10):
        app.step()
    pl = match.player
    br = pl.brain = PlayerBrain(pl, match)
    for u in match.units:                                # personne d'autre sur le terrain
        if u is not pl and u.kind == 'pokemon':
            match._despawn(u)
            u.respawn_t = 1e9
    a = next(a for a in match.arenas if a['key'] == 'sud_est')
    pl.reset(pos=Vec3(a['pos'].x + 2, 0, a['pos'].z))
    br.input(C.CAPTURE_KEY)
    assert pl.capturing is a, 'la touche de capture ne lance pas la capture'
    here = Vec3(pl.position)
    br.input('space')                                    # (esquive refusée pendant la capture)
    for _ in range(40):
        app.step()
    assert (pl.position - here).length() < .05, 'le Pokémon bouge pendant la capture'
    assert a['control'] > .1, f"la capture n'avance pas ({a['control']:.2f})"
    tw = next(t for t in match.units if t.kind == 'tower')
    tw.team, tw.alive, tw.position = 'bleu', True, a['pos']
    assert tw.brain.choose() is not pl, 'la tour vise le Pokémon qui capture'
    br.input(C.CAPTURE_KEY)
    assert pl.capturing is None, "la touche n'arrête pas la capture"
    assert tw.brain.choose() is pl, 'la tour devrait viser le Pokémon (capture arrêtée)'
    print(f"capture : OK (contrôle {a['control']:.2f} après 2 s)", flush=True)
    bx, bz = C.TEAMS['bleu']['base']
    pl.reset(pos=Vec3(bx - BASE_SHIELD - 3, 0, bz))
    for _ in range(60):
        pl.move(Vec3(1, 0, 0), 1 / 20)
    d = (pl.position - Vec3(bx, pl.position.y, bz)).length()
    assert d >= BASE_SHIELD, f'le Pokémon rouge entre dans la base bleue ({d:.1f} m du centre)'
    print(f'champ de force : OK ({d:.1f} m du centre de la base adverse)', flush=True)


def click_test(match):
    """Déplacement au clic à travers la jungle, puis attaque au clic d'un Pokémon sauvage."""
    from ursina import Vec3
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNonRealTime)
    clock.setFrameRate(20)
    for _ in range(10):
        app.step()
    pl = match.player
    br = pl.brain = PlayerBrain(pl, match)
    goal = Vec3(-40, 0, 13)                              # zone de soin Ouest : il faut contourner des massifs
    br.cursor = lambda: goal
    start = Vec3(pl.position)
    br.input('right mouse down')
    print('chemin :', [(round(p.x), round(p.z)) for p in br.order[1]], flush=True)
    for i in range(20 * 60):
        app.step()
        if br.order is None:
            break
    d = (Vec3(pl.position.x, 0, pl.position.z) - goal).length()
    print(f'déplacement : de ({start.x:.0f}, {start.z:.0f}) à ({pl.position.x:.1f}, {pl.position.z:.1f}) '
          f'en {i / 20:.1f} s, écart {d:.1f} m', flush=True)
    if d > 2:
        raise RuntimeError("le Pokémon n'est pas arrivé au point cliqué")
    wild = min((u for u in match.units if u.kind == 'neutral' and u.alive and u.camp and u.camp.get('wild')),
               key=lambda u: (u.position - pl.position).length())
    br.cursor = lambda: wild.position
    br.input('left mouse down')
    print('ordre :', br.order[0], wild.name, f'à {(wild.position - pl.position).length():.0f} m', flush=True)
    for i in range(20 * 40):
        app.step()
        if not wild.alive:
            break
    print('sauvage K.O. :', not wild.alive, f'après {i / 20:.1f} s, PV restants {wild.hp:.0f}', flush=True)
    if wild.alive:
        raise RuntimeError("l'attaque au clic n'a pas mis le sauvage K.O.")
    # boutique ouverte : un clic au sol ne doit pas déplacer le Pokémon
    match.toggle_shop()
    here = Vec3(pl.position)
    far = here + Vec3(8, 0, 0)
    br.cursor = lambda: far
    match.input('right mouse down')
    for _ in range(40):
        app.step()
    moved = (Vec3(pl.position) - here).length()
    match.toggle_shop()
    match.input('right mouse down')
    for _ in range(40):
        app.step()
    moved_after = (Vec3(pl.position) - here).length()
    print(f'boutique ouverte : déplacement {moved:.2f} m ; boutique fermée : {moved_after:.2f} m', flush=True)
    if moved > .3 or moved_after < 1:
        raise RuntimeError('la boutique ne bloque pas (ou ne débloque pas) le déplacement')


def snapshot(match):
    """État de la partie à un instant : niveaux, K.O., dégâts, argent de chaque Pokémon."""
    out = {'t': round(match.time, 1), 'score': dict(match.score),
           'arenas': {a['key']: a['owner'] for a in match.arenas}, 'units': {}}
    for u in match.units:
        if u.kind == 'pokemon':
            s = match.stats[u.uid]
            spent = sum(C.ITEMS[k]['price'] for k in u.items)
            out['units'][str(u.uid)] = {'lv': u.level, 'ko': s['ko'], 'd': s['deaths'], 'dmg': round(s['dmg']),
                                        'gold': round(u.gold + spent), 'items': len(u.items)}
    return out


GAME = {'match': None, 'py': []}


def measure_fps(seconds, label):
    GAME['py'] = []
    clock = ClockObject.getGlobalClock()
    clock.setMode(ClockObject.MNormal)
    n, t1 = 0, systime.time()
    frames = []
    while systime.time() - t1 < seconds:
        application.base.mainWinMinimized = False
        f0 = systime.perf_counter()
        app.step()
        frames.append((systime.perf_counter() - f0) * 1000)
        n += 1
    frames.sort()
    m = GAME['match']
    if m is not None:
        ct = m.cam_target
        print(f'   caméra en ({ct.x:.0f}, {ct.z:.0f}), joueur {"en vie" if m.player.alive else "K.O."}, '
              f'particules {m.particles.alive() if hasattr(m.particles, "alive") else "?"}, '
              f'logique Python médiane {sorted(GAME["py"])[len(GAME["py"]) // 2] if GAME["py"] else 0:.1f} ms', flush=True)
    print(f'FPS ({label}) : {n / (systime.time() - t1):.1f}   image médiane {frames[len(frames) // 2]:.1f} ms, '
          f'95 % {frames[int(len(frames) * .95)]:.1f} ms, pire {frames[-1]:.1f} ms', flush=True)


def entity_census():
    from collections import Counter
    from ursina import scene
    live = [e for e in scene.entities if e.enabled and not e.ignore and not e.has_disabled_ancestor()]
    c = Counter(type(e).__name__ + ('/' + str(e.model.name if e.model else '-')[:14] if type(e).__name__ == 'Entity' else '')
                for e in live)
    print('entités parcourues à chaque image :', len(live), c.most_common(12), flush=True)
    if args.census:
        from collections import Counter as K
        def chain(e):
            out = []
            if e.is_empty():
                return 'détruite'
            for _ in range(4):
                out.append(type(e).__name__ + ':' + str(getattr(e, 'name', ''))[:14])
                e = getattr(e, 'parent', None)
                if e is None or type(e).__name__ in ('Scene', 'NodePath') or e.is_empty():
                    break
            return ' < '.join(out)
        print(K(chain(e) for e in live).most_common(10), flush=True)
        from collections import Counter as K2
        info = K2()
        for e in live:
            try:
                par = e.parent
                ok = not par.is_empty()
            except Exception:
                ok = False
            try:
                kids = len(e.children)
            except Exception:
                kids = -1
            info[(type(e).__name__, str(e.model)[:20] if e.model else '-', 'parent ok' if ok else 'parent DÉTRUIT',
                  kids, round(e.y, 1))] += 1
        print('   ', info.most_common(8), flush=True)


def report(match):
    entity_census()
    mins = [u for u in match.units if u.kind == 'minion' and u.alive]
    towers = [u.arena['key'] + ':' + u.team for u in match.units if u.kind == 'tower' and u.alive]
    print(f'--- {match.time / 60:.1f} min   sbires en jeu : {len(mins)}   tours : {towers}   '
          f"arènes : {[(a['key'], a['owner']) for a in match.arenas]}", flush=True)
    for team in ('rouge', 'bleu'):
        for u in match.team_units[team]:
            s = match.stats[u.uid]
            gold = getattr(u, 'gold', None)
            items = ','.join(getattr(u, 'items', ()) or ())
            print(f"  {team:5s} {u.name:14s} Nv{u.level:2d}  KO {s['ko']:.0f}/{s['deaths']:.0f}  dmg {s['dmg']:6.0f}"
                  + (f'  ₽{gold:5.0f} [{items}]' if gold is not None else ''), flush=True)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except BaseException:
        traceback.print_exc()
        print('ÉCHEC', flush=True)
        os._exit(1)
    print('OK', flush=True)
    os._exit(0)
