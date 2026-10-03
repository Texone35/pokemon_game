"""Test de la partie à deux sur ce PC : un hôte et un invité (deux processus, sans fenêtre) passent
par le vrai salon (code local, choix du Pokémon et du build, « Prêt »), puis jouent en pilote
automatique. Le test échoue à la moindre erreur ou si la partie ne démarre pas.

Lancer :  python tools/net_test.py            (lance l'hôte et l'invité, 90 s de jeu)
"""
import os
import subprocess
import sys
import time as systime
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CODE_FILE = os.path.join(ROOT, 'tools', '.net_test_code')
PLAY = 90.0


def run(role):
    import ursina
    from panda3d.core import loadPrcFileData
    loadPrcFileData('', 'sync-video 0')
    real = ursina.Ursina

    def offscreen(*a, **k):
        k['window_type'] = 'offscreen'
        k['vsync'] = False
        return real(*a, **k)
    ursina.Ursina = offscreen
    from game import config as C
    C.NET['upnp'] = False                          # pas de box à ouvrir pour un test local
    import main                                    # crée l'application et l'écran d'accueil
    from ursina import application
    from tools.pilot import Pilot
    app, game = main.app, main.game
    lobby = game.lobby

    def step(n=1):
        for _ in range(n):
            application.base.mainWinMinimized = False
            app.step()

    def wait(cond, what, timeout=60):
        t0 = systime.time()
        while not cond():
            step()
            if systime.time() - t0 > timeout:
                raise RuntimeError(f'{role} : délai dépassé ({what})')

    step(5)
    if role == 'host':
        lobby.start_host()
        with open(CODE_FILE, 'w') as f:
            f.write(lobby.host.lan_code)
        wait(lambda: lobby.link is not None and getattr(lobby.link, 'joined', False), "arrivée de l'invité")
        lobby.choose('bulbizarre')
        lobby.cycle_build()                        # build suivant : Liane
        step(10)
        lobby.toggle_ready()
    else:
        wait(lambda: os.path.exists(CODE_FILE), 'code de la partie', 30)
        with open(CODE_FILE) as f:
            code = f.read().strip()
        lobby.show_join()
        lobby.code_field.text = code
        lobby.connect()
        wait(lambda: lobby.mode == 'guest', 'connexion au salon')
        lobby.choose('salameche')
        lobby.cycle_build()                        # build Dragon
        step(10)
        lobby.toggle_ready()
    wait(lambda: game.match is not None and game.match.enabled and game.match._warmup <= 0, 'début de la partie',
         120)
    m = game.match
    print(f"{role} : carte tirée {[(a['key'], a['type']) for a in m.arenas]}, "
          f"{len(m.stadium.obstacles)} obstacles", flush=True)       # identique chez l'hôte et l'invité
    m.player.brain = Pilot(m.player, m)
    m.player.role = 'jungle'                       # va se battre contre les camps de la jungle
    m._build_slots()
    dealt = {'n': 0, 'dmg': 0.0}
    if role == 'host':                             # compte les coups portés par l'invité (calculés chez l'hôte)
        real_deal = m.deal_damage

        def counting(src, tgt, base, *a, **k):
            hp0 = tgt.hp
            real_deal(src, tgt, base, *a, **k)
            if src is m.remote and src is not None:
                dealt['n'] += 1
                dealt['dmg'] += max(0.0, hp0 - tgt.hp)
        m.deal_damage = counting
    print(f'{role} : partie lancée, joueur {m.player.name} (build {m.player.build}), '
          f'humains {[(h.name, h.build) for h in m.humans]}', flush=True)
    t0 = systime.time()
    while systime.time() - t0 < PLAY:
        step()
        if m.state == 'lost':
            raise RuntimeError(f'{role} : connexion perdue')
    pl = m.player
    alive = sum(1 for u in m.units if u.alive)
    minions = sum(1 for u in m.units if u.kind == 'minion' and u.alive)
    print(f'{role} : temps de jeu {m.time:.0f} s, {pl.name} Nv {pl.level} PV {pl.hp:.0f}/{pl.max_hp} '
          f'{int(pl.gold)} ₽ objets {pl.items}, unités en vie {alive}, sbires {minions}, '
          f"score {int(m.score['rouge'])}-{int(m.score['bleu'])}", flush=True)
    if role == 'host' and m.remote is not None:
        r = m.remote
        print(f'host : invité vu chez l\'hôte : {r.name} Nv {r.level} ({r.build}) en '
              f'({r.position.x:.0f}, {r.position.z:.0f}), {dealt["n"]} coups portés, {dealt["dmg"]:.0f} dégâts',
              flush=True)
        if dealt['n'] == 0:
            raise RuntimeError("les attaques de l'invité n'arrivent pas chez l'hôte")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            run(sys.argv[1])
        except BaseException:
            traceback.print_exc()
            print('ÉCHEC', flush=True)
            os._exit(1)
        print('OK', flush=True)
        os._exit(0)
    if os.path.exists(CODE_FILE):
        os.remove(CODE_FILE)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    host = subprocess.Popen([sys.executable, __file__, 'host'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, text=True, encoding='utf-8')
    systime.sleep(3)
    guest = subprocess.Popen([sys.executable, __file__, 'guest'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=env, text=True, encoding='utf-8')
    outs = [p.communicate(timeout=600)[0] for p in (host, guest)]
    ok = True
    for name, out, p in zip(('HÔTE', 'INVITÉ'), outs, (host, guest)):
        lines = [ln for ln in out.splitlines() if not ln.startswith((':', 'info', 'Known pipe', '  ', '(', 'set window',
                                                                        'package_folder', 'asset_folder', 'AL lib'))]
        print(f'===== {name} (code {p.returncode})')
        print('\n'.join(lines[-25:]))
        ok &= p.returncode == 0
    if os.path.exists(CODE_FILE):
        os.remove(CODE_FILE)
    print('RÉSULTAT :', 'OK' if ok else 'ÉCHEC')
    sys.exit(0 if ok else 1)
