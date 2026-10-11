# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux de Wesnoth, Dominions 6, DDNet).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp ne référence que des fichiers présents, le port principal existe, le bloc
   Console.* / Limits.* est complet ;
3. chaque réglage exposé dans AMP passe dans la ligne de commande, une fois, sous la forme
   "cle={{Reglage}}" entre guillemets, et chaque cle est lue par le lanceur ; bornes et
   valeurs des listes identiques dans AMP et dans le lanceur ;
4. le lanceur ne donne à Scribble.rs que des variables qu'il connaît (internal/config/config.go,
   v0.9.14), et garde « mots personnalisés par tour » égal à « mots proposés » (sinon le
   formulaire de création refuse ses propres valeurs : internal/frontend/index.go) ;
5. les fichiers téléchargés à l'Update : binaire officiel (dernière release GitHub) au nom
   attendu par le lanceur, et nos fichiers à l'URL du dépôt du manifest, présents dans scripts/ ;
6. la liste de mots TeamKit : taille, aucun doublon, ni virgule ni apostrophe, minuscules,
   aucun mot de la liste noire ; et la vraie fonction lire_liste du lanceur (awk) la relit
   à l'identique, comme une liste perso en fins de ligne Windows avec commentaires et virgule ;
7. le lanceur : fins de ligne LF, aucun {{, `bash -n` s'il y a un bash sous la main ;
8. les regex de console reconnaissent les vraies lignes de Scribble.rs v0.9.14 (relevées le
   10 oct. 2026 dans un conteneur jetable cubecoders/ampbase:debian) et pas les autres.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'scribblers'
LANCEUR = 'scripts/lancer-scribblers.sh'
LISTE = 'scripts/mots-teamkit-famille.txt'
soucis = []


def lire(nom, binaire=False):
    chemin = os.path.join(ICI, nom)
    if binaire:
        with open(chemin, 'rb') as f:
            return f.read()
    with io.open(chemin, encoding='utf-8') as f:
        return f.read()


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...)
    return re.compile(motif.replace('(?<', '(?P<'))


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json', NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        print('ok   %-26s JSON valide' % nom)
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']

# ── 2. kvp ───────────────────────────────────────────────────────────────────
kvp = lire(NOM + '.kvp')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if not os.path.isfile(os.path.join(ICI, ref)):
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '?'))):
        soucis.append('%s pointe sur un fichier absent' % cle)
refs = {p['Ref'] for p in ports}
principal = cles.get('App.PrimaryApplicationPortRef')
if principal not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond à aucun port')
if '{GenericModule.App.Ports.$%s}' % principal not in cles.get('Meta.EndpointURIFormat', ''):
    soucis.append('Meta.EndpointURIFormat doit montrer le port web')
for p in ports:
    if 8080 <= p['Port'] <= 8125:
        soucis.append('port %d : dans la plage 8080-8125 des panneaux AMP du serveur TeamKit' % p['Port'])
print('ok   ports                      %s' % ', '.join('%s %s/%s' % (p['Ref'], p['Port'], p['Protocol']) for p in ports))
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex', 'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex', 'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex', 'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex', 'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart', 'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    print('ok   kvp complet                les %d clés Console/Limits sont là' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') == 'RegexMatch' and not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch sans AppReadyRegex : l’instance ne serait jamais déclarée prête')
if cles.get('App.ExitMethod') != 'SIGTERM':
    soucis.append('App.ExitMethod doit être SIGTERM : Scribble.rs s’arrête proprement dessus')
if cles.get('App.HasWriteableConsole') != 'False':
    soucis.append('Scribble.rs ne lit pas son entrée : HasWriteableConsole doit valoir False')
if cles.get('Meta.URL') != data['manifest.json']['url']:
    soucis.append('Meta.URL et manifest.json ne désignent pas le même dépôt')
for c, v in cles.items():
    if c.startswith('Meta.') and any(ord(x) > 127 for x in v):
        soucis.append('%s : caractère non ASCII (accent) dans le kvp' % c)

# ── 3. réglages <-> ligne de commande <-> lanceur ────────────────────────────
lanceur = lire(LANCEUR)
cmd = cles.get('App.CommandLineArgs', '')
args = re.findall(r'"([^"]*)"', cmd)
if not args or args[0] != '{{$FullBaseDir}}lancer-scribblers.sh':
    soucis.append('la ligne de commande doit commencer par "{{$FullBaseDir}}lancer-scribblers.sh"')
reste = re.sub(r'"[^"]*"', '', cmd).strip()
if reste:
    soucis.append('morceau de ligne de commande hors guillemets : %r' % reste)
paires = {}
for a in args[1:]:
    m = re.fullmatch(r'([a-z]+)=\{\{(\$?\w+)\}\}', a)
    if not m:
        soucis.append('argument inattendu : %r (attendu "cle={{Reglage}}")' % a)
        continue
    if m.group(1) in paires:
        soucis.append('clé %s passée deux fois' % m.group(1))
    paires[m.group(1)] = m.group(2)
params = {c['FieldName']: c for c in config}
# Capacité affichée par AMP et le site : celle d'un salon (le serveur n'a pas de limite de salons).
if cles.get('App.MaxUsers') != params['JoueursMax']['DefaultValue']:
    soucis.append('App.MaxUsers doit valoir le défaut de JoueursMax (%s)' % params['JoueursMax']['DefaultValue'])
for c in config:
    if c['FieldName'] != c['ParamFieldName']:
        soucis.append('%s : FieldName et ParamFieldName différents' % c['FieldName'])
    if c.get('IncludeInCommandLine') is not False:
        soucis.append('%s : IncludeInCommandLine doit valoir false (le lanceur reçoit tout par cle=valeur)' % c['FieldName'])
    if list(paires.values()).count(c['FieldName']) != 1:
        soucis.append('réglage %s absent de la ligne de commande (ou en double)' % c['FieldName'])
for cle, val in paires.items():
    if val.startswith('$'):
        if val[1:] not in refs:
            soucis.append('{{%s}} : aucun port ne porte ce Ref' % val)
    elif val not in params:
        soucis.append('{{%s}} : aucun réglage de ce nom' % val)
    if '${V[%s]' % cle not in lanceur:
        soucis.append('le lanceur ne lit jamais la clé %s' % cle)
lues = set(re.findall(r'\$\{V\[(\w+)\]', lanceur))
if lues - set(paires):
    soucis.append('le lanceur lit des clés que la ligne de commande ne passe pas : %s' % ', '.join(sorted(lues - set(paires))))
if paires.get('port') != '$' + principal:
    soucis.append('le port principal doit être passé en port=')
# bornes et listes : AMP et lanceur doivent dire la même chose
inverse = {v: k for k, v in paires.items()}
for c in config:
    cle = inverse.get(c['FieldName'])
    var = None
    m = re.search(r'^(\w+)="\$\{V\[%s\](?::-([^}]*))?\}"$' % cle, lanceur, re.M) if cle else None
    if not m:
        soucis.append('%s : lecture ${V[%s]} introuvable dans le lanceur' % (c['FieldName'], cle))
        continue
    var, defaut = m.group(1), m.group(2)
    if defaut is not None and defaut != str(c['DefaultValue']):
        soucis.append('%s : défaut %r dans AMP, %r dans le lanceur' % (c['FieldName'], c['DefaultValue'], defaut))
    if c['InputType'] == 'number':
        b = re.search(r'^borne "[^"]+" "\$%s" (\d+) (\d+)$' % var, lanceur, re.M)
        if not b or (b.group(1), b.group(2)) != (c.get('MinValue'), c.get('MaxValue')):
            soucis.append('%s : bornes %s-%s dans AMP, %s dans le lanceur' % (c['FieldName'], c.get('MinValue'), c.get('MaxValue'), b.groups() if b else 'aucune'))
        if not (int(c['MinValue']) <= int(c['DefaultValue']) <= int(c['MaxValue'])):
            soucis.append('%s : défaut hors bornes' % c['FieldName'])
    if c['InputType'] == 'enum':
        e = re.search(r'\[\[ "\$%s" =~ \^\(([^)]*)\)\$ \]\]' % var, lanceur)
        if not e or set(e.group(1).split('|')) != set(c['EnumValues']):
            soucis.append('%s : valeurs %s dans AMP, %s dans le lanceur' % (c['FieldName'], sorted(c['EnumValues']), e.group(1) if e else 'aucune'))
        if c['DefaultValue'] not in c['EnumValues']:
            soucis.append('%s : défaut absent des choix' % c['FieldName'])
print('ok   ligne de commande          %d réglages + port, tous lus par le lanceur' % len(config))

# ── 4. variables données à Scribble.rs ───────────────────────────────────────
CONNUES = {'NETWORK_ADDRESS', 'ROOT_PATH', 'ROOT_URL', 'CANONICAL_URL', 'ALLOW_INDEXING', 'SERVE_DIRECTORIES',
           'CPU_PROFILE_PATH', 'PORT'} | {'LOBBY_SETTING_DEFAULTS_' + x for x in (
               'PUBLIC', 'DRAWING_TIME', 'ROUNDS', 'MAX_PLAYERS', 'CUSTOM_WORDS', 'CUSTOM_WORDS_PER_TURN',
               'CLIENTS_PER_IP_LIMIT', 'LANGUAGE', 'SCORE_CALCULATION', 'WORDS_PER_TURN')}
exportees = set(re.findall(r'^export (\w+)', lanceur, re.M)) - {'LANG'}
if exportees - CONNUES:
    soucis.append('variables inconnues de Scribble.rs : %s' % ', '.join(sorted(exportees - CONNUES)))
if 'LOBBY_SETTING_DEFAULTS_PUBLIC' in exportees:
    soucis.append('LOBBY_SETTING_DEFAULTS_PUBLIC n’est lu par aucune page en v0.9.14 : ne pas faire croire qu’il marche')
if 'export LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS_PER_TURN="$PROPOSES"' not in lanceur \
        or 'export LOBBY_SETTING_DEFAULTS_WORDS_PER_TURN="$PROPOSES"' not in lanceur:
    soucis.append('mots personnalisés par tour doit suivre « mots proposés »')
for lang in ('custom', 'french'):
    if 'LANGUE=%s' % lang not in lanceur:
        soucis.append('le lanceur doit savoir choisir la langue %s' % lang)
print('ok   variables d’environnement  %d, toutes connues de config.go' % len(exportees))

# ── 5. fichiers téléchargés à l'Update ───────────────────────────────────────
depot = data['manifest.json']['url'].replace('https://github.com/', '')
fetch = [e for e in updates if e['UpdateSource'] == 'FetchURL']
binaire = [e for e in fetch if 'scribble-rs/scribble.rs' in e['UpdateSourceData']]
if len(binaire) != 1 or binaire[0]['UpdateSourceData'] != 'https://github.com/scribble-rs/scribble.rs/releases/latest/download/scribblers-linux-x64':
    soucis.append('le binaire doit venir de releases/latest/download/scribblers-linux-x64')
elif 'BIN="$ICI/%s"' % binaire[0]['UpdateSourceArgs'] not in lanceur:
    soucis.append('le lanceur n’attend pas le binaire sous le nom %s' % binaire[0]['UpdateSourceArgs'])
nos = [e for e in fetch if e not in binaire]
for e in nos:
    attendu = 'https://raw.githubusercontent.com/%s/main/scripts/%s' % (depot, e['UpdateSourceArgs'])
    if e['UpdateSourceData'] != attendu:
        soucis.append('URL inattendue pour %s : %s' % (e['UpdateSourceArgs'], e['UpdateSourceData']))
    elif not os.path.isfile(os.path.join(ICI, 'scripts', e['UpdateSourceArgs'])):
        soucis.append('scripts/%s absent du dépôt' % e['UpdateSourceArgs'])
if {e['UpdateSourceArgs'] for e in nos} != {'lancer-scribblers.sh', 'mots-teamkit-famille.txt'}:
    soucis.append('l’Update doit déposer lancer-scribblers.sh et mots-teamkit-famille.txt')
for e in fetch:
    if e.get('UpdateSourceTarget') != '{{$FullBaseDir}}' or not e.get('OverwriteExistingFiles'):
        soucis.append('%s : doit aller dans {{$FullBaseDir}} et écraser l’ancien' % e['UpdateSourceArgs'])
if updates[-1]['UpdateSource'] != 'Executable' or 'lancer-scribblers.sh\\" verifier' not in json.dumps(updates[-1]['UpdateSourceArgs']):
    soucis.append('la dernière étape de l’Update doit être « lancer-scribblers.sh verifier »')
print('ok   Update                     binaire officiel + %d fichier(s) du dépôt %s' % (len(nos), depot))

# ── 6. liste de mots ─────────────────────────────────────────────────────────
brut = lire(LISTE, binaire=True)
if b'\r' in brut:
    soucis.append('%s : fins de ligne Windows' % LISTE)
mots = [l for l in brut.decode('utf-8').split('\n') if l.strip() and not l.lstrip().startswith('#')]
vus = set()
for m in mots:
    if m != m.strip():
        soucis.append('mot avec espaces autour : %r' % m)
    if m != m.lower():
        soucis.append('mot pas en minuscules : %r' % m)
    if re.search(r"[,'’ʼ`\"]", m):
        soucis.append('mot avec virgule, apostrophe ou guillemet : %r' % m)
    if len(m) > 30:
        soucis.append('mot trop long pour une partie : %r' % m)
    if m in vus:
        soucis.append('doublon : %r' % m)
    vus.add(m)
if not 500 <= len(mots) <= 1000:
    soucis.append('liste de %d mots : viser 500 à 1 000' % len(mots))
NOIRE = {'avortement', 'suicide', 'meurtre', 'drogue', 'terroriste', 'alcool', 'cigarette', 'bière', 'vin', 'whisky',
         'sang', 'mort', 'tuer', 'fusil', 'pistolet', 'bombe', 'guerre', 'cancer', 'sexe', 'grenade', 'arme', 'héroïne'}
if vus & NOIRE:
    soucis.append('mots à éviter dans une liste familiale : %s' % ', '.join(sorted(vus & NOIRE)))
print('ok   liste de mots              %d mots, aucun doublon ni mot de la liste noire' % len(mots))

bash = shutil.which('bash')
m = re.search(r'^lire_liste\(\) \{\n.*?^\}\n', lanceur, re.M | re.S)
if not m:
    soucis.append('fonction lire_liste introuvable dans le lanceur')
elif bash:
    with tempfile.TemporaryDirectory() as tmp:
        essai = os.path.join(tmp, 'perso.txt')
        with open(essai, 'wb') as f:
            f.write('# commentaire\r\n  tarte flambée  \r\n\r\ncigogne, alsace\r\nœuf au plat\r\n   # autre\r\nbretzel'.encode('utf-8'))
        for fichier, attendu in ((os.path.join(ICI, LISTE), ','.join(mots)), (essai, 'tarte flambée,œuf au plat,bretzel')):
            r = subprocess.run([bash, '-c', m.group(0) + 'lire_liste "$1"', '_', fichier.replace('\\', '/')],
                               capture_output=True)
            sortie = r.stdout.decode('utf-8')
            if r.returncode or sortie != attendu:
                soucis.append('lire_liste(%s) : %r…' % (os.path.basename(fichier), sortie[:120]))
            if fichier == essai and 'virgule' not in r.stderr.decode('utf-8', 'replace'):
                soucis.append('lire_liste doit signaler la ligne à virgule écartée')
    print('ok   lire_liste (awk du lanceur) relit la liste TeamKit et une liste perso Windows')
else:
    print('--   lire_liste                 pas de bash ici, non essayée')

# ── 7. lanceur ───────────────────────────────────────────────────────────────
if b'\r' in lire(LANCEUR, binaire=True):
    soucis.append('%s : fins de ligne Windows (CRLF)' % LANCEUR)
if '{{' in lanceur:
    soucis.append('le lanceur contient {{ : AMP pourrait le remplacer')
for besoin, pourquoi in [
    ('exec "$BIN" 2>&1', 'le SIGTERM d’AMP doit arriver au binaire lui-même'),
    ('chmod +x "$BIN"', 'FetchURL ne rend pas le binaire exécutable'),
    ('echo "TeamKit : Scribble.rs pret, il ecoute sur le port $PORT."', 'ligne prêt'),
    ('/proc/net/tcp', 'la ligne prêt attend l’ouverture réelle du port'),
]:
    if besoin not in lanceur:
        soucis.append('lanceur : %s (%s)' % (besoin, pourquoi))
if bash:
    r = subprocess.run([bash, '-n', os.path.join(ICI, LANCEUR).replace('\\', '/')], capture_output=True, text=True)
    if r.returncode:
        soucis.append('bash -n %s : %s' % (LANCEUR, r.stderr.strip()))
    else:
        print('ok   bash -n                    %s' % LANCEUR)
else:
    print('--   bash -n                    pas de bash ici, syntaxe non vérifiée')

# ── 8. regex de console sur de vraies lignes (Scribble.rs v0.9.14, 10/10/2026) ─
pret = py(cles['Console.AppReadyRegex'])
jeter = py(cles['Console.ThrowawayMessageRegex'])
VRAIES = [
    ('pret', 'TeamKit : Scribble.rs pret, il ecoute sur le port 8380.'),
    ('jeter', '2026/10/10 17:45:01 Registering route: GET /v1/lobby/{lobby_id}/ws'),
    ('jeter', "2026/10/10 17:45:01 Setting 'LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS' to 'chat,chien,lapin,cheval' (isDefault: false)"),
    ('garder', "2026/10/10 17:45:01 Setting 'LOBBY_SETTING_DEFAULTS_CUSTOM_WORDS_PER_TURN' to '3' (isDefault: false)"),
    ('garder', "2026/10/10 17:45:01 Setting 'PORT' to '8380' (isDefault: false)"),
    ('garder', "2026/10/10 17:45:01 Starting Scribble.rs version 'v0.9.14'"),
    ('garder', '2026/10/10 17:45:01 Started, listening on: http://:8380'),
    ('garder', '2026/10/10 17:48:23 Received terminated, gracefully shutting down.'),
    ('garder', 'TeamKit : 2 joueur(s) connecte(s), 2 salon(s) ouvert(s).'),
    ('garder', 'TeamKit : ATTENTION, le port 8380 n\'ecoute toujours pas apres 30 secondes.'),
]
if not re.search(r'"TeamKit : Scribble.rs pret, il ecoute sur le port \$PORT\."', lanceur):
    soucis.append('la ligne prêt du lanceur a changé : revoir Console.AppReadyRegex')
for attendu, ligne in VRAIES:
    est_pret, est_jete = bool(pret.search(ligne)), bool(jeter.search(ligne))
    if (attendu == 'pret') != est_pret:
        soucis.append('AppReadyRegex %s : %r' % ('ne reconnaît pas' if attendu == 'pret' else 'attrape', ligne))
    if (attendu == 'jeter') != est_jete:
        soucis.append('ThrowawayMessageRegex %s : %r' % ('laisse passer' if attendu == 'jeter' else 'jette', ligne))
print('ok   console                    %d lignes réelles' % len(VRAIES))

print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
