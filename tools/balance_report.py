"""Rapport d'équilibrage à partir de parties simulées (tools/smoke_test.py --log).

  python tools/smoke_test.py --minutes 10 --fast --seed 3 --log parties/p3.json   (une partie)
  python tools/balance_report.py parties/*.json                                  (le rapport)

Mesure : rythme de montée en niveau (quand les Pokémon atteignent les niveaux clés), argent,
pics de puissance selon la courbe (early / équilibré / late : part des dégâts et des K.O. en début
et en fin de partie), et résultats par lignée.
"""
import glob
import json
import statistics
import sys
from collections import defaultdict

KEY_LEVELS = (3, 5, 7, 10, 15)


def fmt_t(t):
    return f'{int(t // 60)}:{int(t % 60):02d}' if t is not None else '  -  '


def main(paths):
    games = []
    for p in paths:
        for f in glob.glob(p):
            with open(f, encoding='utf-8') as fh:
                games.append(json.load(fh))
    if not games:
        print('aucune partie')
        return
    print(f'{len(games)} parties')
    # ------------------------------------------------ rythme des niveaux
    reach = defaultdict(list)
    for g in games:
        for uid, lv in g['levels'].items():
            for k in KEY_LEVELS:
                reach[k].append(lv.get(str(k)))
    print('\nNIVEAUX (temps médian pour les atteindre, part des Pokémon qui les atteignent)')
    for k in KEY_LEVELS:
        ts = [t for t in reach[k] if t is not None]
        med = statistics.median(ts) if ts else None
        print(f'  Nv {k:2d} : médiane {fmt_t(med)}   premier {fmt_t(min(ts) if ts else None)}   '
              f'{100 * len(ts) / len(reach[k]):3.0f} % des Pokémon')
    # ------------------------------------------------ argent et objets
    print('\nARGENT (gagné au total, médiane) et OBJETS')
    for minute in (3, 5, 8, 10):
        vals, items = [], []
        for g in games:
            snap = min(g['minutes'], key=lambda s: abs(s['t'] - minute * 60))
            if abs(snap['t'] - minute * 60) < 40:
                vals += [u['gold'] for u in snap['units'].values()]
                items += [u['items'] for u in snap['units'].values()]
        if vals:
            print(f'  {minute:2d} min : {statistics.median(vals):5.0f} ₽   objets {statistics.mean(items):.1f} en moyenne')
    # ------------------------------------------------ courbes early / late
    print('\nCOURBES DE PUISSANCE (dégâts par minute et K.O. par minute, début / milieu / fin de partie)')
    phases = ((0, 180, 'début 0-3 min'), (180, 390, 'milieu 3-6:30'), (390, 600, 'fin 6:30-10'))
    by_curve = defaultdict(lambda: defaultdict(list))
    by_line = defaultdict(lambda: defaultdict(list))
    for g in games:
        snaps = [{'t': 0, 'units': {uid: {'dmg': 0, 'ko': 0} for uid in g['units']}}] + g['minutes']
        for a, b, name in phases:
            sa = min(snaps, key=lambda s: abs(s['t'] - a))
            sb = min(snaps, key=lambda s: abs(s['t'] - b))
            span = max(1.0, (sb['t'] - sa['t']) / 60)
            if sb['t'] - sa['t'] < 60:
                continue
            for uid, info in g['units'].items():
                d = (sb['units'][uid]['dmg'] - sa['units'].get(uid, {'dmg': 0})['dmg']) / span
                k = (sb['units'][uid]['ko'] - sa['units'].get(uid, {'ko': 0})['ko']) / span
                by_curve[info['curve']][name].append((d, k))
                by_line[info['line']][name].append((d, k))
    for curve in ('early', 'standard', 'late'):
        row = []
        for _, _, name in phases:
            v = by_curve[curve][name]
            if v:
                row.append(f"{name} : {statistics.mean(x[0] for x in v):5.0f} dmg/min {statistics.mean(x[1] for x in v):.2f} KO/min")
        print(f'  {curve:8s} ' + '   '.join(row))
    # ------------------------------------------------ par lignée
    print('\nPAR LIGNÉE (dégâts par minute début / milieu / fin, K/D, victoires)')
    kd = defaultdict(lambda: [0, 0])
    wins = defaultdict(lambda: [0, 0])
    for g in games:
        last = g['minutes'][-1]['units']
        win = max(g['score'], key=g['score'].get) if g['score']['rouge'] != g['score']['bleu'] else None
        for uid, info in g['units'].items():
            kd[info['line']][0] += last[uid]['ko']
            kd[info['line']][1] += last[uid]['d']
            wins[info['line']][0] += info['team'] == win
            wins[info['line']][1] += 1
    for line in sorted(by_line, key=lambda l: -sum(x[0] for x in by_line[l][phases[2][2]]) / max(1, len(by_line[l][phases[2][2]]))):
        cols = []
        for _, _, name in phases:
            v = by_line[line][name]
            cols.append(f'{statistics.mean(x[0] for x in v):5.0f}' if v else '   - ')
        k, d = kd[line]
        w, n = wins[line]
        print(f'  {line:11s} ' + ' / '.join(cols) + f'   K/D {k:3d}/{d:3d}   victoires {w}/{n}')
    # ------------------------------------------------ parties
    print('\nPARTIES')
    for g in games:
        s = g['score']
        print(f"  graine {g['seed']:3d}  IA {g['ai']:7s}  durée {fmt_t(g['time'])}  Rouge {s['rouge']:.0f} - {s['bleu']:.0f} Bleue")


if __name__ == '__main__':
    main(sys.argv[1:] or ['parties/*.json'])
