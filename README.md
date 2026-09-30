# Pokémon Dominion

Jeu de bataille d'arènes en 3D : deux équipes de 5 Pokémon s'affrontent pour le contrôle
de 5 arènes. Jouable seul (avec des alliés contrôlés par l'ordinateur) ou à deux en coopération.

---

## 1. Installer Python (une seule fois)

1. Téléchargez **Python 3.13** sur <https://www.python.org/downloads/>.
2. Lancez l'installateur et **cochez la case « Add python.exe to PATH »** en bas de la
   première fenêtre, puis cliquez sur « Install Now ».
3. Vérifiez dans un terminal (PowerShell) :

   ```powershell
   python --version
   ```

   Cela doit afficher `Python 3.13.x`.

## 2. Récupérer le jeu

**Avec Git :**

```powershell
git clone https://github.com/Texone35/pokemon_game.git
cd pokemon_game
```

**Sans Git :** sur la page GitHub, cliquez sur **Code → Download ZIP**, décompressez le
dossier, puis ouvrez un terminal dedans (clic droit dans le dossier → « Ouvrir dans le terminal »).

## 3. Créer l'environnement virtuel et installer les dépendances (une seule fois)

Toutes les commandes se lancent **depuis le dossier du jeu** (celui qui contient `main.py`).

**Créer l'environnement virtuel :**

```powershell
python -m venv venv
```

**L'activer :**

```powershell
.\venv\Scripts\Activate.ps1
```

> Si PowerShell affiche une erreur du type « l'exécution de scripts est désactivée sur ce
> système », lancez cette commande **une seule fois**, puis réessayez d'activer :
>
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
>
> Dans l'invite de commandes classique (cmd) : `venv\Scripts\activate.bat`.
> Dans Git Bash : `source venv/Scripts/activate`.

Une fois activé, `(venv)` apparaît au début de la ligne du terminal.

**Installer les dépendances dans l'environnement :**

```powershell
pip install -r requirements.txt
```

## 4. Lancer le jeu

```powershell
python main.py
```

**Les fois suivantes**, il suffit d'ouvrir un terminal dans le dossier du jeu puis :

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

---

## Commandes

| Touche | Action |
|---|---|
| Clic (droit ou gauche) au sol | Se déplacer à cet endroit (le Pokémon contourne les murs ; maintenir pour suivre la souris) |
| Clic sur un adversaire | L'approcher puis l'auto-attaquer en continu |
| Flèches | Se déplacer au clavier (annule l'ordre au clic) |
| A (maintenir) | Auto-attaque ; à l'arrêt, le Pokémon attaque aussi tout seul l'adversaire à portée |
| Q Z S D | Attaques n°1 à 4 : **maintenir** pour viser à la souris, **relâcher** pour lancer (les attaques autour du Pokémon partent tout de suite) |
| E | Ultime (niveau 10) |
| Clic gauche / clic droit (pendant la visée) | Lancer tout de suite / annuler |
| F | Méga-Évolution ou Dynamax (selon le Pokémon) |
| Espace | Esquive vers la souris (longue recharge, comme le Flash) |
| B | Boutique (dans sa base, ou pendant qu'on est K.O.) |
| Molette | Zoom |
| Clic molette + glisser | Déplacer la vue (C : recentrer) |
| Tab | Voir toute la carte |

Dans le salon : **← →** ou clic pour choisir son Pokémon, bouton **Build** pour choisir sa façon de
le jouer (quand il en a plusieurs), **Entrée** pour valider, **Échap** pour revenir.

## Déroulé d'une partie

- **Stats** : chaque Pokémon a PV, Attaque, Défense, Attaque spéciale, Défense spéciale et Vitesse.
  Elles montent avec le niveau selon son rôle (tank, combattant, rapide, sniper, soutien) et sa
  courbe (« early » : fort tôt ; « late » : fort en fin de partie), et à chaque évolution.
- **Attaques** : la 1re dès le niveau 1, puis une nouvelle aux niveaux 3, 5 et 7, l'ultime au
  niveau 10. Les attaques visées à la souris frappent plus fort que celles à cible automatique.
- **Argent (₽) et XP** : en mettant K.O. des adversaires, des Pokémon sauvages, des camps, des
  sbires, des tours, et en capturant des arènes. La boutique propose 10 objets (3 emplacements).
- **Arènes** : une tour défensive se dresse peu après la capture ; la météo de l'arène (pluie,
  soleil, tempête de sable...) s'installe sur le quartier au profit de l'équipe qui la tient.
- **Voies** : chaque arène contrôlée envoie des vagues de sbires vers les arènes voisines.
- **Jungle** : Magmar, Lokhlass et Héliatronc donnent des buffs ; les buissons de Baies Sitrus
  soignent puis repoussent au bout de 2 minutes.

## Jouer à deux

Les deux joueurs sont dans la même équipe (rouge), contre 5 adversaires contrôlés par l'ordinateur.

> ⚠️ Les deux joueurs doivent avoir **exactement la même version du jeu** (mêmes fichiers).
> Sinon, la connexion est refusée.

1. **L'hôte** clique sur **« Créer une partie à deux »**, puis sur **« Copier le code »**, et
   envoie ce code à son ami.
2. **L'ami** clique sur **« Rejoindre une partie »**, colle le code, puis **« Rejoindre »**.
3. Chacun choisit son Pokémon et clique sur **« PRÊT ! »** : la partie démarre.

**Quel code utiliser ?**

- **Même box / même Wi-Fi :** utilisez le bouton **« Code local »** (le plus simple).
- **Par Internet :** utilisez le code principal. Le jeu essaie d'ouvrir tout seul le port
  **47650** (TCP et UDP) sur la box de l'hôte. Si le salon indique que c'est impossible,
  ouvrez ce port dans les réglages de la box, ou utilisez un VPN gratuit comme
  **Radmin VPN** ou **Tailscale** (puis le code local).
- Au premier lancement, si Windows demande l'autorisation du pare-feu, **autorisez Python**.

## En cas de problème

- **`python` n'est pas reconnu :** Python n'a pas été ajouté au PATH. Réinstallez-le en
  cochant « Add python.exe to PATH ».
- **`pip install` échoue :** vérifiez que l'environnement est bien activé (`(venv)` en début
  de ligne) et que vous êtes dans le dossier qui contient `requirements.txt`.
- **Le jeu est lent :** réduisez les réglages graphiques dans `game/config.py` (section
  `QUALITY`).

---

## Organisation du code

```
main.py             point d'entrée
requirements.txt    dépendances Python
game/
  config.py         carte, arènes, espèces (aspect), équipes, réseau
  balance/          TOUTES les valeurs d'équilibrage (stats, attaques, builds, objets, XP, argent,
                    jungle, arènes, météo, tours, vagues...) : c'est ici qu'on règle le jeu
  match.py          une partie : règles, score, caméra, interface de jeu
  world/            le stade : carte, jungle, arènes, effets visuels
  pokemon/          modèles 3D, unités, IA, attaques (moves.py), stats (kit.py), vagues (waves.py)
  network/          jeu à deux (connexion et synchronisation)
  interface/        écrans d'accueil, boutique et éléments d'interface
tools/              tests automatiques et équilibrage
archives/           anciennes versions du jeu (non utilisées)
```

## Tests et équilibrage

```powershell
python tools/smoke_test.py                  # une partie jouée par l'ordinateur, sans fenêtre (3 min)
python tools/smoke_test.py --minutes 10 --fast --seed 4 --log parties/p4.json
python tools/balance_report.py parties/*.json   # rythme des niveaux, argent, courbes early/late
python tools/balance_table.py               # stats de chaque lignée par niveau
python tools/net_test.py                    # partie à deux sur ce PC (hôte + invité)
```
