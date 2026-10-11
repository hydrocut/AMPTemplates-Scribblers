# AMPTemplates-Scribblers — Scribble.rs (online Pictionary) for AMP

**AMP Generic Module** template for **[Scribble.rs](https://github.com/scribble-rs/scribble.rs)**,
a free, open-source (BSD-3) and privacy-friendly Pictionary game played in the web browser: one
player draws, the others guess in the chat. No account, no ads, nothing to install for players.
Written for TeamKit, a free French game host, on 10 Oct 2026. CubeCoders ships no Scribble.rs
template, and no community template was found.

> Résumé en français à la fin du fichier.

## What it does

| | |
|---|---|
| Server | official `scribblers-linux-x64` binary, **latest GitHub release** downloaded at each Update (v0.9.14 on 10 Oct 2026, 14 MB) |
| Dependencies | none: static Go binary (`CGO_ENABLED=0` in upstream CI). Runs in `cubecoders/ampbase:debian` (Debian 13) or without a container |
| Port | **one TCP port** for the web page **and** the WebSocket. Default **8380** (the game's own default, 8080, is taken by AMP on our host) |
| Interface language | follows the player's browser (`Accept-Language`); French is built in since v0.9.13. Can be forced to French by nginx (below) |
| Words | French family word list (~730 words) shipped here and offered by default; the game's official French list or your own file can be chosen instead |
| Players in AMP | not listed: Scribble.rs logs no join/leave line. The start script prints the number of connected players and open lobbies when it changes |
| State | everything lives in memory: a restart closes every lobby (the game sends its players a `shutdown` event). Nothing to back up |

## Files

| File | Role |
|---|---|
| `scribblers.kvp`, `scribblers*.json`, `manifest.json` | the AMP template |
| `scripts/lancer-scribblers.sh` | start script (below), fetched from this repository at each Update |
| `scripts/mots-teamkit-famille.txt` | the TeamKit word list, fetched at each Update |
| `verifier.py` | pre-push checks, must print `Tout est bon.` |

Both `scripts/` files come from `raw.githubusercontent.com` (branch `main`), so **the repository
must be public**.

## How the server is started

AMP runs `/bin/bash lancer-scribblers.sh "port=…" "mots=…" …` (every setting as one quoted
`key=value` argument: an empty value never shifts the others). The script:

1. checks every value (the same bounds as Scribble.rs, `game.SettingBounds`) and stops with a
   French message naming the setting to fix;
2. makes the binary executable (AMP's download does not);
3. turns the chosen word list into the comma-separated "custom words" value;
4. exports the settings as environment variables — this is how Scribble.rs reads its
   configuration (`internal/config/config.go`) — and `exec`s the binary, so AMP's SIGTERM reaches
   it directly: it logs `Received terminated, gracefully shutting down.`, warns the players and
   exits 0 (measured: 50 ms with 12 open lobbies);
5. prints `TeamKit : Scribble.rs pret, il ecoute sur le port <port>.` once the port is really in
   LISTEN state (`/proc/net/tcp*`). Scribble.rs prints `Started, listening on` **before** it binds;
6. every 30 s reads `/v1/stats` and prints `TeamKit : N joueur(s) connecte(s), M salon(s) ouvert(s).`
   when it changes (bash `/dev/tcp`, no curl needed).

`verifier` as first argument only checks the download (ELF header, size, version string, word
count): it is the last Update stage.

## Settings exposed in AMP (French UI)

Lobby settings are the **defaults of the "create a lobby" form**: whoever creates a lobby can
still change them. Bounds are the game's own.

| AMP setting | Scribble.rs variable | Default |
|---|---|---|
| Port web du jeu (Network tab) | `PORT` | 8380/TCP |
| Liste de mots | `LOBBY_SETTING_DEFAULTS_LANGUAGE` + `…_CUSTOM_WORDS` | `teamkit` |
| Mots proposés au dessinateur (1–6) | `…_WORDS_PER_TURN` and `…_CUSTOM_WORDS_PER_TURN` | 3 |
| Temps pour dessiner (60–300 s) | `…_DRAWING_TIME` | 120 |
| Nombre de manches (1–20) | `…_ROUNDS` | 4 |
| Joueurs par salon (2–24) | `…_MAX_PLAYERS` | 24 |
| Joueurs par adresse IP (1–24) | `…_CLIENTS_PER_IP_LIMIT` | **6** (game: 2, too low for a family behind one router) |
| Calcul des points | `…_SCORE_CALCULATION` (`chill` / `competitive`) | chill |
| Adresse publique | `ROOT_URL` (link previews, canonical link) | empty |
| Chemin dans l'adresse | `ROOT_PATH` (serve under `/dessin/`) | empty |
| Visible dans Google | `ALLOW_INDEXING` | no |

`…_CUSTOM_WORDS_PER_TURN` always follows "words per turn": the form refuses to create a lobby when
it is higher (`internal/frontend/index.go`). `LOBBY_SETTING_DEFAULTS_PUBLIC` is **not** exposed:
no page reads it in v0.9.14 — the home page has two buttons, *public lobby* and *private lobby*.

### Word lists

| Choice | What happens |
|---|---|
| `teamkit` (default) | `scripts/mots-teamkit-famille.txt`: ~730 French words written by hand for families — animals, food, home, school, jobs, tales, sports, nature… Only drawable things, no comma, no apostrophe. The lobby form opens with language *Custom words only* and the words in the *custom words* box; the game then cycles through them in random order |
| `officielle` | the game's built-in French list (`internal/game/words/fr`, ~1 800 words). Translated from the English list: many abstract words (*moyenne*, *annuler*, *candidat*) and some that families may not want (*avortement*, *suicide*, *terroriste*, *drogue*…) |
| `perso` | `mots-perso.txt` in the instance folder, one word per line, `#` for comments; created empty on first start and never overwritten. Empty file = TeamKit list |

Guesses ignore case, accents, spaces, hyphens and underscores (`internal/sanitize`): `pere noel`
finds `père noël`. Apostrophes are **not** ignored, hence none in the list. A line containing a
comma is dropped with a console notice (a comma separates words in Scribble.rs).

### Extra settings

Scribble.rs also reads a `.env` file in its working folder (the instance folder). The script creates
a commented one and never overwrites it; AMP's settings, passed as environment variables, win over
it (tested). Example: `LOBBY_SETTING_BOUNDS_MAX_ROUNDS=30`, `LOBBY_CLEANUP_INTERVAL=90s`,
`CORS_ALLOWED_ORIGINS=…` — full list in `internal/config/config.go` upstream.

## Behind nginx in HTTPS (recommended)

Players then open `https://dessin.teamkit.fr` instead of `http://IP:8380`. The page itself opens
`wss://` when it is served over `https://` (`lobby.js`), so nginx must pass **WebSocket upgrades**.
In AMP, set **Adresse publique** to `https://dessin.teamkit.fr` and leave **Chemin** empty.

```nginx
# /etc/nginx/sites-available/dessin.teamkit.fr
# Own map name: $connection_upgrade already exists on the TeamKit host (palword-api vhost),
# defining it twice would stop nginx.
map $http_upgrade $tk_scribble_connection {
    default upgrade;
    ''      close;
}

server {
    server_name dessin.teamkit.fr;
    access_log /var/log/nginx/dessin.teamkit.fr.access.log;

    location / {
        proxy_pass http://127.0.0.1:8380;          # the instance's port
        proxy_http_version 1.1;                    # WebSocket
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $tk_scribble_connection;
        proxy_set_header Host $host;
        # $remote_addr, NOT $proxy_add_x_forwarded_for: Scribble.rs trusts the FIRST address of
        # X-Forwarded-For for its per-IP limit, so a client could otherwise send a fake one.
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Optional: French interface for everyone, whatever the browser language.
        proxy_set_header Accept-Language "fr-FR,fr;q=0.9";
        # A lobby may stay idle while someone draws: keep sockets open.
        proxy_read_timeout 1h;
        proxy_send_timeout 1h;
    }

    # include snippets/teamkit-noindex.conf;   # if the game must stay out of search engines
    listen 80;
}
```

Then `sudo nginx -t`, `sudo systemctl reload nginx`, `sudo certbot --nginx -d dessin.teamkit.fr`
(certbot adds the `listen 443 ssl` and the redirect). DNS: an `A` record `dessin` → the host IP.

Tested on 10 Oct 2026 with this exact block (nginx 1.26, self-signed certificate on port 8443):
HTTPS page, `101 Switching Protocols` for the WebSocket, a full lobby with two players, French
interface for an English browser, and the per-IP limit holding against forged `X-Forwarded-For`
values (directly on the port, the same forged values pass).

Once nginx is in front, the game port no longer needs to be reachable from outside: closing it
also removes the forged `X-Forwarded-For` loophole. The upstream wiki has a shorter example:
<https://github.com/scribble-rs/scribble.rs/wiki/reverse-proxy-(nginx)>.

To serve under a path instead (`https://teamkit.fr/dessin/`): set **Chemin** to `dessin` and use
`location /dessin/ { proxy_pass http://127.0.0.1:8380; … }` (no trailing path on `proxy_pass`, the
game expects `/dessin/` itself). Tested directly on the port, not through nginx: `/` → 404,
`/dessin/` → 200, lobby created and played under `/dessin/lobby/…`.

## Console lines (real, v0.9.14)

```
TeamKit : liste de mots « teamkit » proposee par defaut (735 mots).
TeamKit : Scribble.rs sur le port 8380, page d'accueil http://127.0.0.1:8380/
2026/10/10 17:45:01 Setting 'PORT' to '8380' (isDefault: false)
2026/10/10 17:45:01 Starting Scribble.rs version 'v0.9.14'
2026/10/10 17:45:01 Started, listening on: http://:8380
TeamKit : Scribble.rs pret, il ecoute sur le port 8380.            <- AppReadyRegex
TeamKit : 2 joueur(s) connecte(s), 2 salon(s) ouvert(s).
2026/10/10 17:48:23 Received terminated, gracefully shutting down.
```

`Console.ThrowawayMessageRegex` drops the 16 `Registering route:` lines and the
`Setting 'LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS'` line (one line holding the whole word list).

## Resources (measured)

| | |
|---|---|
| RAM | 25–33 MB idle, 38 MB with 12 lobbies / 24 players |
| Start | under 1 s to the ready line |
| Disk | 15 MB |
| CPU | negligible: the server relays drawing strokes, browsers draw |

## Before pushing

```
python verifier.py
```

Must print `Tout est bon.`: JSON, includes, ports, complete `Console.*` / `Limits.*` block, every
AMP setting passed once as `"key={{Setting}}"` and read by the script with the same default, bounds
and choices, only variables Scribble.rs knows, download URLs, the word list (size, duplicates,
commas, apostrophes, blacklist), the script's own `awk` reading of that list and of a Windows-style
custom list, LF endings, `bash -n`, console regexes on real lines.

## Install in AMP

ADS → Configuration → Instance Deployment → **Configuration Repositories**: add
`hydrocut/AMPTemplates-Scribblers:main`, save, **Fetch latest**. Create Instance →
**Scribble.rs - Pictionary en ligne (TeamKit)** → **Update** (must end with
`Scribble.rs telecharge : 14 Mo, version v0.9.x.`) → **Start** → open `http://IP:port`.

## Credits

Scribble.rs is © its authors (BSD-3-Clause; logo and background are all rights reserved). This
repository only holds the template and the TeamKit word list (free to reuse); the server binary
is downloaded from the official GitHub releases.

---

## Résumé en français

Template AMP pour **Scribble.rs**, un Pictionary multijoueur gratuit et libre qui se joue **dans le
navigateur** (sans compte, sans pub, rien à installer). Un seul port **TCP**, **8380** par défaut
(8080, le défaut du jeu, est pris par AMP chez TeamKit), qui porte la page web et le WebSocket.

- **Binaire officiel** `scribblers-linux-x64`, dernière version publiée sur GitHub, téléchargée à
  chaque Update (v0.9.14 au 10/10/2026) ; aucune dépendance, marche en conteneur Debian 13.
- **Interface en français** quand le navigateur est en français (traduction intégrée depuis v0.9.13) ;
  derrière nginx, une ligne peut l'imposer à tout le monde.
- **Liste de mots familiale TeamKit** (~730 mots dessinables, sans mot gênant) proposée par défaut
  à la création d'un salon. Au choix : la liste française officielle du jeu (~1 800 mots traduits
  de l'anglais, dont des mots abstraits et quelques mots à éviter devant des enfants) ou son propre
  fichier `mots-perso.txt`.
- **Réglages en français dans AMP** : liste de mots, mots proposés, temps de dessin, manches,
  joueurs par salon, joueurs par IP (6 au lieu de 2, pour les familles), calcul des points, adresse
  publique, chemin, indexation Google. Ce sont les valeurs par défaut du formulaire de création.
- **Derrière nginx en HTTPS** (`dessin.teamkit.fr`) : configuration complète plus haut, testée,
  avec le WebSocket et `X-Forwarded-For $remote_addr` (sinon la limite par IP se contourne).
- Pas de liste de joueurs dans AMP (le jeu n'écrit pas qui arrive) : le script écrit le nombre de
  joueurs et de salons quand il change. `App.MaxUsers=24` (un salon plein, défaut de « Joueurs par
  salon ») n'est que la capacité affichée par AMP et le site. Tout est en mémoire : un redémarrage ferme les salons.
- **Testé en vrai** le 10 oct. 2026 dans un conteneur jetable : 25 à 38 Mo de RAM, prêt en moins d'une seconde.
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
