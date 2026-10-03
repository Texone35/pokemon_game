"""Construction de la carte en arrière-plan, pendant que les joueurs choisissent leur Pokémon.

Le tirage (types des arènes) vient de la graine du salon : l'hôte et l'invité construisent la même
carte chacun de leur côté. Le calcul se fait dans un fil séparé ; les créations de nœuds 3D passent
par le fil principal (geometry.on_main), qui les exécute un peu à chaque image avec pump() : le salon
reste fluide. La partie récupère ensuite la carte toute prête (Match, setup['preload']).
"""
import sys
import threading

from ursina import Entity, destroy

from game import config as C
from game.world import geometry
from game.world.stadium import Stadium

_ACTIVE = []                   # constructions en cours (le fil principal reprend la main plus souvent)
_SWITCH = sys.getswitchinterval()


class MapPreload:
    def __init__(self, seed):
        self.seed = seed
        self.types = C.draw_map(seed)
        C.apply_map(self.types)
        self.root = Entity(enabled=False)              # caché jusqu'au début de la partie
        self.stadium = Stadium(self.root, build=False)
        self.error = None
        self.thread = threading.Thread(target=self._run, name='map-preload', daemon=True)
        self.thread.cancelled = False
        _ACTIVE.append(self)
        sys.setswitchinterval(.001)                    # l'affichage n'attend jamais plus d'1 ms le calcul
        geometry.BREATHE[1] = geometry.BREATHE[0]      # salon : le calcul laisse respirer l'affichage
        self.thread.start()

    def _run(self):
        try:
            self.stadium.build()
        except geometry.Cancelled:
            pass
        except BaseException as e:                     # transmise au fil principal par take()
            self.error = e

    @property
    def done(self):
        return not self.thread.is_alive()

    @property
    def progress(self):
        return 1.0 if self.done and self.error is None else min(.99, self.stadium.progress)

    @property
    def label(self):
        return self.stadium.step_label

    def pump(self, budget=.006, wait=False):
        """À chaque image (fil principal) : exécute un peu des créations demandées par le calcul (wait :
        voir geometry.pump)."""
        geometry.pump(budget, wait and not self.done)
        if self.done:
            self._release()

    def take(self):
        """La carte terminée (à appeler quand done est vrai)."""
        self._release()
        if self.error is not None:
            raise self.error
        return self.stadium

    def cancel(self):
        """Abandonne la construction (retour au menu, nouvelle partie) et libère la mémoire."""
        self.thread.cancelled = True
        self._release()
        destroy(self.root)

    def _release(self):
        if self in _ACTIVE:
            _ACTIVE.remove(self)
            if not _ACTIVE:
                sys.setswitchinterval(_SWITCH)
