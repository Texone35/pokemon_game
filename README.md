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
| Z Q S D | Se déplacer |
| J (maintenir) | Attaque de base |
| K L U I | Attaques spéciales |
| Espace | Esquive |
| Clic droit + glisser | Tourner la caméra |
| Molette | Zoom |
| Clic molette + glisser | Déplacer la vue |
| Tab | Voir toute la carte |

Dans le salon : **← →** ou clic pour choisir son Pokémon, **Entrée** pour valider, **Échap** pour revenir.

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
  config.py         données du jeu (carte, espèces, attaques, équilibrage)
  match.py          une partie : règles, score, caméra, interface de jeu
  world/            le stade : carte, jungle, arènes, effets visuels
  pokemon/          modèles 3D des Pokémon, IA, attaques
  network/          jeu à deux (connexion et synchronisation)
  interface/        écrans d'accueil et éléments d'interface
archives/           anciennes versions du jeu (non utilisées)
```
