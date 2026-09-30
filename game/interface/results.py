"""Page de fin de partie : résultat, durée, statistiques de chaque Pokémon des deux équipes,
boutons « Rejouer » et « Retour au menu »."""
from ursina import Entity, Text, camera, color, curve

from game import config as C
from game.interface.lobby import DIM, F_BOLD, F_SEMI, F_TITLE, GOLD, Btn, _quad, chip, panel

W = 1.5                   # largeur d'un tableau d'équipe
ROW = .044                # hauteur d'une ligne
BAND = .05                # bandeau de l'équipe (nom, score, titres des colonnes)
# (titre, clé des statistiques, position x du centre de la colonne)
COLUMNS = [('Nv', 'level', -.33), ('K.O.', 'ko', -.22), ('K.O. subis', 'deaths', -.1), ('Aides', 'assists', .02),
           ('Dégâts', 'dmg', .14), ('Soins', 'heal', .26), ('Captures', 'caps', .38), ('Points', 'points', .51)]


def rating(s):
    """Note d'ensemble d'un Pokémon (pour désigner le meilleur joueur de la partie)."""
    return (s['points'] + 4 * s['ko'] + 2 * s['assists'] + 3 * s['caps'] + s['dmg'] / 250 + s['heal'] / 200
            - s['deaths'])


class Results(Entity):
    def __init__(self, match):
        super().__init__(parent=camera.ui, z=-2)
        m = self.m = match
        me = m.player.team
        other = 'bleu' if me == 'rouge' else 'rouge'
        if m.score[me] > m.score[other]:
            title, col = 'VICTOIRE !', GOLD
        elif m.score[me] < m.score[other]:
            title, col = 'DÉFAITE', color.rgb(.6, .75, 1)
        else:
            title, col = 'MATCH NUL', color.white
        Entity(parent=self, model='quad', scale=(4, 2), color=color.rgba(.02, .03, .08, .66), z=.1)
        Text(parent=self, text=title, position=(0, .43, -.01), origin=(0, 0), scale=3, color=col, **F_TITLE)
        t = int(m.time)
        Text(parent=self, text=f'Durée de la partie : {t // 60:02d}:{t % 60:02d}      Objectif : {C.SCORE_TO_WIN} points',
             position=(0, .375, -.01), origin=(0, 0), scale=.85, color=DIM, **F_SEMI)

        units = [u for team in (me, other) for u in m.team_units[team]]
        stats = {u: dict(m.stats[u.uid], level=u.level) for u in units}
        best = {key: max(s[key] for s in stats.values()) for _, key, _ in COLUMNS}
        mvp = max(units, key=lambda u: rating(stats[u]))
        if rating(stats[mvp]) <= 0:
            mvp = None
        y = .335
        for team in (me, other):
            y = self._team(team, y, stats, best, mvp) - .025

        Btn(self, 'Retour au menu', (-.2, -.35), m.game.back_to_menu, w=.34, accent=color.rgb(.6, .75, 1))
        self.replay = Btn(self, 'Rejouer' if m.authority else 'Proposer de rejouer', (.2, -.35), self._replay,
                          w=.34, accent=GOLD)
        Text(parent=self, text='Échap : menu      R : rejouer', position=(0, -.415, -.01), origin=(0, 0), scale=.75,
             color=DIM, **F_SEMI)
        self.scale = .95
        self.animate_scale(1, duration=.25, curve=curve.out_back)

    def _team(self, team, top, stats, best, mvp):
        """Tableau d'une équipe ; renvoie le bas du tableau."""
        m = self.m
        rows = m.team_units[team]
        tc = C.TEAMS[team]
        h = BAND + ROW * len(rows) + .016
        panel(self, (0, top - h / 2), W, h)
        by = top - .008 - BAND / 2
        Entity(parent=self, model=_quad(W - .016, BAND, .014), scale=(W - .016, BAND), position=(0, by, -.005),
               color=color.rgba(tc['color'][0], tc['color'][1], tc['color'][2], .35))
        Text(parent=self, text=f"Équipe {tc['name']}   {int(m.score[team])} pts", position=(-.715, by, -.01),
             origin=(-.5, 0), scale=.95, color=tc['light'], **F_BOLD)
        for name, _, x in COLUMNS:
            Text(parent=self, text=name, position=(x, by, -.01), origin=(0, 0), scale=.72, color=DIM, **F_SEMI)
        y = top - .008 - BAND - ROW / 2
        for i, u in enumerate(rows):
            if u.local:
                Entity(parent=self, model=_quad(W - .016, ROW - .004, .01), scale=(W - .016, ROW - .004),
                       position=(0, y, -.005), color=color.rgba(1, .82, .28, .16))
            elif i % 2:
                Entity(parent=self, model='quad', scale=(W - .016, ROW), position=(0, y, -.005),
                       color=color.rgba(1, 1, 1, .035))
            m.portraits.icon(self, u.form, scale=.038, position=(-.7, y, -.01))
            Text(parent=self, text=u.name, position=(-.67, y, -.01), origin=(-.5, 0), scale=.9,
                 color=GOLD if u.local else color.white, **F_BOLD)
            tag = 'Vous' if u.local else f'Joueur {u.human + 1}' if u.is_player else 'IA'
            Text(parent=self, text=tag, position=(-.47, y, -.01), origin=(-.5, 0), scale=.72,
                 color=DIM if tag == 'IA' else tc['light'], **F_SEMI)
            s = stats[u]
            for _, key, x in COLUMNS:
                v = s[key]
                top_col = key != 'deaths' and key != 'level' and v > 0 and v >= best[key]
                Text(parent=self, text=str(int(round(v))), position=(x, y, -.01), origin=(0, 0), scale=.85,
                     color=GOLD if top_col else color.white, **(F_BOLD if top_col else F_SEMI))
            if u is mvp:
                chip(self, 'MVP', (.65, y), GOLD, txt_col=color.rgb(.2, .14, 0), size=.72)
            y -= ROW
        return top - h

    def _replay(self):
        m = self.m
        if m.authority:
            m.restart()
        elif m.net is not None:
            m.net.request_restart()
            self.replay.set('Demande envoyée...')
