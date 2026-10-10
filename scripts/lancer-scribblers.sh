#!/bin/bash
# lancer-scribblers.sh - pose par le template AMP TeamKit (recree a chaque Update).
#
#   lancer-scribblers.sh verifier          controle apres telechargement (etape d'Update)
#   lancer-scribblers.sh cle=valeur ...    demarrage du serveur (ligne de commande d'AMP)
#
# AMP passe chaque reglage sous la forme cle=valeur, entre guillemets : un reglage
# vide reste un argument "cle=" et ne decale jamais les autres. Les valeurs sont
# controlees ici, puis donnees a Scribble.rs en variables d'environnement (c'est
# ainsi qu'il lit sa configuration : internal/config/config.go).
#
# Ce script :
#  1. rend le binaire executable (le telechargement d'AMP ne le fait pas) ;
#  2. choisit la liste de mots proposee par defaut a la creation d'un salon ;
#  3. ecrit une ligne « pret » quand le port ecoute vraiment ;
#  4. ecrit dans la console le nombre de joueurs connectes quand il change ;
#  5. laisse la place au binaire (exec) : le SIGTERM d'AMP lui arrive directement.
cd "$(dirname "$0")" || exit 1
ICI="$PWD"
BIN="$ICI/scribblers-linux-x64"
LISTE_TEAMKIT="$ICI/mots-teamkit-famille.txt"
LISTE_PERSO="$ICI/mots-perso.txt"
export LANG=C.UTF-8 LC_ALL=C.UTF-8

verifier_binaire() {
  if [ ! -s "$BIN" ]; then
    echo "ERREUR : $BIN absent ou vide. Lance Update (il vient des releases GitHub de Scribble.rs)."
    return 1
  fi
  if [ "$(head -c 4 "$BIN" | od -An -tx1 | tr -d ' \n')" != "7f454c46" ]; then
    echo "ERREUR : $BIN n'est pas un programme Linux (telechargement abime ?). Relance Update."
    return 1
  fi
  chmod +x "$BIN" || return 1
}

if [ "$1" = "verifier" ]; then
  verifier_binaire || exit 1
  version=$(grep -a -o -m1 'v[0-9]\+\.[0-9]\+\.[0-9]\+[-0-9a-z]*' "$BIN" | head -n 1)
  echo "Scribble.rs telecharge : $(( $(stat -c %s "$BIN") / 1024 / 1024 )) Mo, version ${version:-inconnue}."
  if [ -s "$LISTE_TEAMKIT" ]; then
    echo "Liste de mots TeamKit : $(grep -v '^[[:space:]]*#' "$LISTE_TEAMKIT" | grep -c '[^[:space:]]') mots."
  else
    echo "ATTENTION : liste de mots TeamKit absente ($LISTE_TEAMKIT)."
  fi
  exit 0
fi

declare -A V
for a in "$@"; do
  case "$a" in
    *=*) V["${a%%=*}"]="${a#*=}" ;;
    *) echo "ERREUR : argument inattendu : $a" ; exit 1 ;;
  esac
done

refuser() {
  echo "ERREUR : $1"
  echo "Corrige ce reglage dans l'onglet Configuration d'AMP, puis relance."
  exit 1
}
# Nombre entier entre deux bornes (celles de Scribble.rs : game.SettingBounds).
borne() {
  [[ "$2" =~ ^[0-9]+$ ]] && [ "$2" -ge "$3" ] && [ "$2" -le "$4" ] \
    || refuser "$1 : '$2' n'est pas un nombre entre $3 et $4."
}

PORT="${V[port]}"
ADRESSE="${V[adresse]}"
CHEMIN="${V[chemin]}"
MOTS="${V[mots]:-teamkit}"
TEMPS="${V[temps]:-120}"
MANCHES="${V[manches]:-4}"
JOUEURS="${V[joueurs]:-24}"
PROPOSES="${V[proposes]:-3}"
PARIP="${V[parip]:-6}"
POINTS="${V[points]:-chill}"
INDEX="${V[indexation]:-non}"

borne "port" "$PORT" 1024 65535
borne "temps pour dessiner" "$TEMPS" 60 300
borne "nombre de manches" "$MANCHES" 1 20
borne "joueurs par salon" "$JOUEURS" 2 24
borne "mots proposes au dessinateur" "$PROPOSES" 1 6
borne "connexions par adresse IP" "$PARIP" 1 24
[[ "$MOTS" =~ ^(teamkit|officielle|perso)$ ]] || refuser "liste de mots '$MOTS' inconnue."
[[ "$POINTS" =~ ^(chill|competitive)$ ]] || refuser "calcul des points '$POINTS' inconnu."
[[ "$INDEX" =~ ^(oui|non)$ ]] || refuser "indexation '$INDEX' : oui ou non."
# Adresse publique : seulement le protocole et le nom, sans chemin (Scribble.rs y colle ROOT_PATH).
ADRESSE="${ADRESSE%/}"
[ -z "$ADRESSE" ] || [[ "$ADRESSE" =~ ^https?://[A-Za-z0-9.-]+(:[0-9]{1,5})?$ ]] \
  || refuser "adresse publique '$ADRESSE' : de la forme https://dessin.teamkit.fr (sans chemin ni / a la fin)."
# Chemin : vide (le jeu a la racine du nom) ou des segments simples, ex. dessin ou jeux/dessin.
CHEMIN="${CHEMIN#/}"
CHEMIN="${CHEMIN%/}"
[ -z "$CHEMIN" ] || [[ "$CHEMIN" =~ ^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$ ]] \
  || refuser "chemin '$CHEMIN' : lettres sans accent, chiffres, - et _, separes par / (ex. dessin)."

verifier_binaire || exit 1

# Liste de mots -> une seule ligne, mots separes par des virgules (format du champ
# « mots personnalises » de Scribble.rs). Lignes vides et commentaires (#) ignores ;
# une ligne qui contient une virgule est ecartee (elle couperait le mot en deux).
lire_liste() {
  awk '
    { sub(/\r$/, ""); gsub(/^[ \t]+|[ \t]+$/, "") }
    $0 == "" || substr($0, 1, 1) == "#" { next }
    index($0, ",") { ecartes++; next }
    { printf "%s%s", (n++ ? "," : ""), $0 }
    END { if (ecartes) printf "TeamKit : %d ligne(s) avec une virgule ecartee(s) de la liste.\n", ecartes > "/dev/stderr" }
  ' "$1"
}

if [ "$MOTS" = "perso" ] && [ ! -f "$LISTE_PERSO" ]; then
  printf '%s\n' \
    "# mots-perso.txt - ta liste de mots pour Scribble.rs (reglage « Liste de mots » = perso)." \
    "# Un mot ou une expression par ligne. Les lignes qui commencent par # sont ignorees." \
    "# Pas de virgule ni d'apostrophe. Le template ne reecrit jamais ce fichier." \
    "# Relance le serveur apres une modification." > "$LISTE_PERSO"
fi

LANGUE=french
LISTE=""
case "$MOTS" in
  teamkit)
    [ -s "$LISTE_TEAMKIT" ] || refuser "liste TeamKit absente ($LISTE_TEAMKIT) : lance Update."
    LANGUE=custom
    LISTE=$(lire_liste "$LISTE_TEAMKIT")
    ;;
  perso)
    LANGUE=custom
    LISTE=$(lire_liste "$LISTE_PERSO")
    if [ -z "$LISTE" ]; then
      echo "TeamKit : mots-perso.txt est vide, la liste TeamKit est utilisee a la place."
      LISTE=$(lire_liste "$LISTE_TEAMKIT")
    fi
    ;;
esac
if [ "$LANGUE" = "custom" ]; then
  if [ -z "$LISTE" ]; then
    echo "TeamKit : aucune liste de mots lisible, la liste francaise officielle du jeu est utilisee."
    LANGUE=french
  else
    echo "TeamKit : liste de mots « $MOTS » proposee par defaut ($(awk -F, '{ print NF }' <<< "$LISTE") mots)."
  fi
fi

oui_non() { [ "$1" = "oui" ] && echo true || echo false; }

# Fichier .env : Scribble.rs le lit dans le dossier courant, pour des reglages en plus
# (voir le README). Les reglages d'AMP, passes en variables d'environnement, passent devant.
if [ ! -f .env ]; then
  printf '%s\n' \
    "# .env - reglages Scribble.rs en plus, un par ligne : NOM=valeur (liste dans le README)." \
    "# Lu a chaque demarrage. Les reglages de l'onglet Configuration d'AMP passent devant." \
    "# Le template ne reecrit jamais ce fichier." > .env
fi

export PORT
export NETWORK_ADDRESS=""
export ROOT_URL="$ADRESSE"
export ROOT_PATH="$CHEMIN"
export ALLOW_INDEXING="$(oui_non "$INDEX")"
export LOBBY_SETTING_DEFAULTS_DRAWING_TIME="$TEMPS"
export LOBBY_SETTING_DEFAULTS_ROUNDS="$MANCHES"
export LOBBY_SETTING_DEFAULTS_MAX_PLAYERS="$JOUEURS"
export LOBBY_SETTING_DEFAULTS_WORDS_PER_TURN="$PROPOSES"
# Doit rester <= mots proposes, sinon le formulaire de creation refuse ses propres valeurs.
export LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS_PER_TURN="$PROPOSES"
export LOBBY_SETTING_DEFAULTS_CLIENTS_PER_IP_LIMIT="$PARIP"
export LOBBY_SETTING_DEFAULTS_LANGUAGE="$LANGUE"
export LOBBY_SETTING_DEFAULTS_SCORE_CALCULATION="$POINTS"
export LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS="$LISTE"

URL_LOCALE="http://127.0.0.1:$PORT${CHEMIN:+/$CHEMIN}/"
echo "TeamKit : Scribble.rs sur le port $PORT, page d'accueil ${ADRESSE:-$URL_LOCALE}${ADRESSE:+${CHEMIN:+/$CHEMIN}/}"

# Ligne « pret » pour AMP, des que le port est en ecoute (LISTEN = 0A dans /proc/net).
# Scribble.rs ecrit « Started, listening on » AVANT d'ouvrir le port : on ne s'y fie pas.
SCRIPT_PID=$$
(
  motif=$(printf ':%04X$' "$PORT")
  for _ in $(seq 1 150); do
    kill -0 "$SCRIPT_PID" 2>/dev/null || exit 0
    for t in /proc/net/tcp /proc/net/tcp6; do
      if [ -r "$t" ] && awk -v p="$motif" '$2 ~ p && $4 == "0A" { t = 1 } END { exit !t }' "$t"; then
        echo "TeamKit : Scribble.rs pret, il ecoute sur le port $PORT."
        exit 0
      fi
    done
    sleep 0.2
  done
  echo "TeamKit : ATTENTION, le port $PORT n'ecoute toujours pas apres 30 secondes."
) &

# Joueurs connectes : lus toutes les 30 s dans /v1/stats (sans curl : /dev/tcp de bash),
# ecrits seulement quand le nombre change. Scribble.rs n'ecrit aucune ligne d'arrivee
# ou de depart de joueur, donc la liste des joueurs d'AMP reste vide.
(
  dernier="0 0"
  n=0
  # Reveil toutes les 2 s pour s'arreter vite avec le serveur, lecture toutes les 30 s.
  while sleep 2; do
    kill -0 "$SCRIPT_PID" 2>/dev/null || exit 0
    n=$((n + 1))
    [ $((n % 15)) -eq 0 ] || continue
    reponse=$(
      exec 3<>"/dev/tcp/127.0.0.1/$PORT" 2>/dev/null || exit 0
      printf 'GET /%sv1/stats HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n' "${CHEMIN:+$CHEMIN/}" >&3
      timeout 5 cat <&3
    )
    salons=$(sed -n 's/.*"activeLobbyCount":\([0-9]*\).*/\1/p' <<< "$reponse")
    joueurs=$(sed -n 's/.*"connectedPlayersCount":\([0-9]*\).*/\1/p' <<< "$reponse")
    [ -n "$salons" ] && [ -n "$joueurs" ] || continue
    if [ "$joueurs $salons" != "$dernier" ]; then
      echo "TeamKit : $joueurs joueur(s) connecte(s), $salons salon(s) ouvert(s)."
      dernier="$joueurs $salons"
    fi
  done
) &

exec "$BIN" 2>&1
