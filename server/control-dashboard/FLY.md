# ElioBot piloté par le connectome de mouche

## Ce qui tourne réellement

L’intégration utilise les données locales du projet **Pytorch_fly** : le cache intact `data/experiments/laboratory_v1/weight.npz` et ses annotations `data/cache/raw/neuron_meta.feather`.

Le réseau MaleCNS v1.0 contient **176 422 neurones et 25 862 574 connexions dirigées pondérées**. Il n’est pas remplacé par un réseau réduit ou synthétique lorsque les fichiers sont absents. Le chargement échoue alors avec un message dans le dashboard.

Le moteur reprend le calcul déjà utilisé par la mouche incarnée de Pytorch_fly :

```text
x_suivant = 0,7 × x + 0,3 × tanh(W × x + entrée)
```

Cette version s’appuie sur NumPy/SciPy et le cache creux existant, comme `flyconnectome.laboratory.advance`. PyTorch et le serveur web de Pytorch_fly ne sont pas nécessaires à l’exécution du dashboard. Le calcul est effectué dans un thread séparé ; il ne bloque pas les commandes HTTP ni l’arrêt du robot.

**Portée scientifique :** le câblage est anatomique, mais la dynamique, les stimuli et la correspondance avec les roues sont des modèles simplifiés. Ce n’est pas une reconstitution physiologique validée du comportement d’une mouche. Les poids restent fixes et aucune politique de navigation apprise n’est utilisée.

## Préparation des données

Depuis la racine d’ElioBot Framework, sur la machine qui possède Pytorch_fly :

```bash
python3 server/control-dashboard/prepare_fly.py /chemin/vers/Pytorch_fly
```

Le script copie uniquement les deux caches nécessaires vers `server/control-dashboard/fly-data/`, environ **85 Mio sur disque**, et écrit un manifeste avec leurs empreintes SHA-256. Il ne modifie pas Pytorch_fly et ne lit pas ses identifiants neuprint. Les copies sont exclues de Git, mais doivent être transférées au serveur avec le reste du dossier `control-dashboard/`.

Les empreintes vérifient l’intégrité des copies. La provenance reste celle des caches de référence fournis ; le loader contrôle également les dimensions, le nombre de connexions, les valeurs finies et la présence des groupes neuronaux.

Source anatomique : [MaleCNS v1.0, Janelia](https://male-cns.janelia.org/), données distribuées sous CC BY 4.0 d’après la documentation du projet source. L’intégrateur et la lecture motrice sont adaptés des modules `laboratory.py`, `embodied.py` et `realtime/embodied.py` de Pytorch_fly. Les paramètres ajoutés pour ElioBot sont décrits ci-dessous.

## Exécution sur ordinateur ou Raspberry Pi

Le même service peut fonctionner sur les deux. Le fichier Docker Compose monte `./fly-data` en lecture seule dans `/data/fly`. Prévoir un système 64 bits pour les dépendances scientifiques et assez de RAM : **198 Mio pour la matrice seule**, auxquels s’ajoutent Python, les annotations et les autres bibliothèques. Le pic de chargement est supérieur.

```bash
cd server/control-dashboard
docker compose up -d --build dashboard
```

Puis déployer le nouveau `mqtt_dashboard` sur ElioBot et recharger le navigateur. Les versions robot et serveur doivent être mises à jour ensemble. Le serveur refuse le mode mouche si le robot n’annonce pas `protocol: 2` dans sa télémétrie.

Sans Docker, depuis `server/control-dashboard/fastapi-dashboard` :

```bash
uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

Configurer `MQTT_BROKER` / `MQTT_PORT` pour le broker utilisé. Le dossier de données est automatiquement `../fly-data` ; la variable `FLY_DATA_DIR` permet de choisir un autre chemin. Le robot doit viser l’IP du serveur dans ses propres paramètres MQTT.

Dans le dashboard : **Charger le cerveau**, puis **Lancer la mouche** lorsque le modèle est prêt et le robot connecté. Un obstacle présenté aux capteurs amorce l’activité ; sans stimulation initiale le réseau est nul, donc le robot reste immobile. La récurrence peut maintenir une activité après disparition de l’obstacle.

## Laboratoire dédié et visualisation

![Laboratoire : stimulation simulée sans mouvement](image-fly.png)

La page `/fly` sépare l’expérience neuronale du pilotage classique. Sur `/`, le bouton Lancer/Pause/Reprendre de l’exploration est directement superposé à sa carte.

Après chargement, le laboratoire affiche les **185 neurones LPLC2** (94 gauches, 91 droits), avec leur identifiant et leur activité signée. Les points sont regroupés par population : leur disposition n’est pas une carte anatomique. Vert et violet représentent les signes positif et négatif ; gris indique le repos. Les quatre neurones DNa02/DNg13 sont détaillés individuellement. Un classement montre les 12 activités absolues les plus élevées du réseau complet, et un compteur indique le nombre de neurones avec une valeur absolue ≥ 0,05. Ces seuils servent à l’affichage ; ils ne modifient pas le calcul neuronal.

Les boutons **Stimuler à gauche / devant / à droite** exécutent 32 pas du réseau complet depuis le repos, dans un état séparé. L’interface rejoue leur progression et affiche les réponses et commandes calculées. Ces tests fonctionnent sans robot et **ne publient aucune commande MQTT** ; ils ne modifient pas l’état neuronal utilisé pour piloter ElioBot. Le libellé « Test simulé » distingue cette lecture des capteurs réels. « Revenir au robot » rétablit la vue du réseau de pilotage. Une stimulation de test est refusée pendant le mode mouche actif.

Le chargement seul ne crée pas d’activité : le réseau initial reste à zéro tant qu’aucune stimulation ne lui est présentée.

## Éviter les versions mélangées

Le serveur et l’interface annoncent le protocole dashboard **3** (distinct du protocole robot 2). Une page connectée à un ancien serveur affiche un diagnostic de compatibilité et bloque les nouvelles commandes ; l’arrêt général reste accessible via la commande de veille historique. Les réponses HTTP ne sont pas mises en cache.

Docker embarque maintenant l’interface et le code Python dans la même image ; seuls les caches neuronaux sont montés depuis le disque. Après toute modification, reconstruire et recréer le service :

```bash
cd server/control-dashboard
docker compose up -d --build --no-deps dashboard
```

Cela évite une nouvelle interface affichée avec un ancien processus Python, cause des erreurs `state.control.revision` et `Not Found`.

## Correspondance capteurs → neurones

| Détection ElioBot | Entrée du réseau |
|---|---|
| Avant gauche, index 0 | Intensité 4 dans les 94 LPLC2 gauches |
| Avant droit, index 2 | Intensité 4 dans les 91 LPLC2 droits |
| Avant central, index 1 | Intensité 4 dans les deux populations |
| Arrière, index 3 | Affiché, sans population supplémentaire inventée |
| Aucun obstacle | Intensité 0 |

Les quatre seuils logiciels sont réglables dans `robot/config.json` via `obstacle_thresholds` (gauche, avant, droite, arrière). Ils sont partagés avec l’exploration et leur valeur par défaut reste 10000. Les valeurs brutes et les seuils apparaissent dans **Valeurs des 4 capteurs** après mise à jour du programme robot.

Les entrées sont binaires. Elles ne représentent ni des distances mesurées, ni une image rétinienne, ni un modèle de grossissement visuel. Les populations olfactives ne sont pas stimulées : le robot n’a pas de capteur d’odeur.

## Correspondance neurones → roues

La lecture reprend les deux neurones DNa02/DNg13 de chaque côté :

```text
vitesse = 3 × (moyenne(abs(gauche)) + moyenne(abs(droite))) / 2
rotation = borner(3 × (moyenne(gauche) − moyenne(droite)), −2, 2)
avance_PWM = vitesse × 15
rotation_PWM = rotation × 20
roue_gauche = avance_PWM − rotation_PWM
roue_droite = avance_PWM + rotation_PWM
```

Chaque roue est bornée à **±45 %**. Les demandes dont la valeur absolue est inférieure à 15 % sont ramenées à zéro pour éviter de les amplifier avec le seuil minimum des moteurs. Une valeur négative demande de reculer cette roue.

Un obstacle frontal supprime la composante d’avance, en conservant la rotation issue du réseau. Ce garde-fou est appliqué côté serveur et revérifié directement côté robot. Il ne crée pas une décision de virage à la place du connectome. Les gains ne sont pas une calibration musculaire et devront être vérifiés physiquement. Les activités gauche/droite peuvent provoquer des réponses asymétriques et ne garantissent pas un évitement efficace.

Le dashboard montre les sorties neuronales et **la dernière commande calculée**, pas une mesure des vitesses réelles des roues. Le mouvement neuronal ne modifie pas la carte d’exploration : la position y devient incertaine dès qu’ElioBot se déplace hors de cette exploration.

## Protocole et expiration

- Mode robot supplémentaire : `fly` sur `elio/command/mode`.
- Le robot publie une observation identifiée sur `elio/telemetry/fly_sensors` : `{session, frame, left, front, right, back}`.
- Une nouvelle observation est produite au plus toutes les 200 ms, après réponse à la précédente. Sans réponse, elle est remplacée après 600 ms.
- Le serveur calcule un pas puis répond sur `elio/command/fly_drive` : `{session, frame, left, right}`. Ici `left` et `right` sont des consignes de roues entières, pas des capteurs.
- Le robot accepte uniquement une réponse correspondant à son observation en attente, âgée de 600 ms au maximum. Un doublon ou un ancien identifiant ne prolonge pas le mouvement.
- Une commande de roues expire après **500 ms**, vérifiées dans la boucle embarquée. Le temps des opérations réseau synchrones peut ajouter de la latence : ce n’est pas un arrêt matériel temps réel.
- Le serveur suspend le calcul moteur pour une observation de plus de 600 ms et écarte une réponse terminée après 550 ms. Après les 2 secondes de démarrage, un flux interrompu pendant plus de 1,5 seconde met la mouche en pause. Le message distingue désormais l’absence totale d’observations d’une interruption en cours de fonctionnement et indique la dernière trame reçue. Les journaux `[Mouche]` détaillent le nombre d’observations, de réponses transmises et de calculs périmés pour diagnostiquer le délai sans désactiver ces protections.
- Un changement de mode, une reconnexion ou un reset annule les consignes en cours. Une commande calculée pendant une ancienne révision du pilotage est rejetée avant publication.
- Le statut robot conserve `last_error` après une erreur de réception MQTT, de télémétrie ou d’envoi des observations. Il contient l’étape, le message, la session et le temps écoulé depuis le démarrage. Le serveur journalise chaque nouvelle erreur sous `[Robot] Erreur embarquée`, y compris après reconnexion : l’USB n’est plus nécessaire pour récupérer cette cause. Un redémarrage complet efface ce diagnostic en mémoire.
- Le serveur suspend le pilotage si la présence du robot ou son mode ne sont plus confirmés. Le robot reste capable d’arrêter ses roues même si le serveur ne répond plus.

Un pas neuronal ne correspond pas à une durée biologique validée. Le rythme cible est de cinq observations par seconde maximum ; les délais réseau et de calcul peuvent le réduire.

## Pilotage sans sélecteur

- Une direction manuelle depuis la veille active le pilotage manuel.
- **Lancer l’exploration** ou **Lancer la mouche** coupe le manuel et démarre le comportement choisi.
- Une demande manuelle pendant une autonomie reçoit un HTTP 409 avec la révision du pilotage. Le navigateur ouvre une confirmation.
- Annuler ne change rien. Confirmer met l’autonomie en pause et active le manuel, **sans déplacer immédiatement le robot**. Il faut ensuite maintenir une direction.
- Le bouton **Reprendre** relance l’autonomie. L’état neuronal est conservé en pause ; **Réinitialiser l’activité** le remet à zéro lorsque la mouche est arrêtée.
- Une confirmation périmée est refusée si un autre navigateur a changé le pilotage entre-temps.
- **Tout arrêter** / Échap revient en veille immédiatement côté serveur. Les mouvements manuels portent aussi une révision pour qu’une ancienne requête ne réactive pas le robot après cet arrêt.
- Une pause d’exploration préserve son historique. Si un mouvement était en cours ou si le robot est déplacé manuellement, la précision du repère n’est plus garantie : l’interface le signale.

## Vérifications réalisées

Sur l’ordinateur de développement :

- 37 tests Python (framework, robot simulé, moteur neuronal et arbitrage).
- 10 tests JavaScript (confirmation, annulation, reprise, perte de focus, deltas et arrêt immédiat).
- Comparaison au moteur original de Pytorch_fly sur **256 pas avec le réseau complet** : quatre scénarios de 64 pas, états neuronaux strictement identiques et sorties motrices identiques à la tolérance numérique testée.
- Temps observé : environ **28 ms par pas** sur cet ordinateur, hors aller-retour MQTT. Ce résultat ne mesure pas les performances d’un Raspberry Pi.
- Interface vérifiée dans le navigateur sur ordinateur et à 390 px de largeur.
- Configuration Docker Compose validée, image construite et chargement du réseau complet vérifié dans un conteneur isolé du réseau.

Les essais physiques sur ElioBot restent à effectuer : sens de rotation, comportement au contact, arrêts réels, performances du serveur cible et stabilité du WiFi.

Pour répéter les tests usuels depuis la racine :

```bash
uv run --no-project --with fastapi --with paho-mqtt --with numpy --with scipy --with pandas --with pyarrow python -m unittest discover -s tests -v
node --test tests/dashboard.test.cjs
```

Pour la comparaison au moteur original, utiliser l’environnement installé de Pytorch_fly :

```bash
cd /chemin/vers/Pytorch_fly
uv run --no-sync python /chemin/vers/Eliobot-Framework/tests/verify_fly_reference.py /chemin/vers/Pytorch_fly
```
