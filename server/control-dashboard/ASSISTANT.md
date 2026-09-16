# Assistant ElioBot : chat, Gemini, Ollama et MCP

Le bouton **Assistant ElioBot** ouvre un chat sur les pages de pilotage et du laboratoire.
Le modèle comprend la demande ; un client MCP appelle les outils du serveur local ; ces outils utilisent le contrôle FastAPI existant et MQTT. Aucune commande shell, gestion d'installation ou clé API n'est accessible au modèle.

## Installation commune

Prérequis : Python 3.11+, système 64 bits, Docker Engine + Compose v2 sur Linux, ou Docker Desktop utilisant les conteneurs Linux sur Mac/Windows. Le script diagnostique Docker ; il n'installe pas automatiquement Docker ni ses pilotes.

Depuis `server/control-dashboard` :

```bash
# Linux, Raspberry Pi, macOS
./setup.sh
# Diagnostic sans modification
./setup.sh --check
# Option : démarrer également le conteneur Ollama (CPU)
./setup.sh --ollama
```

```powershell
# Windows (PowerShell)
.\setup.ps1
# Ou directement
py -3 setup.py
```

Le lanceur écrit le système de **l'hôte** dans `assistant-runtime/host.json`, puis reconstruit et démarre les services. Il ne déduit pas le système du navigateur ni du Linux visible dans un conteneur Docker Desktop. Avec un contexte Docker distant, exécuter le lanceur sur la véritable machine du serveur.

Le démarrage direct `docker compose up -d --build` reste possible ; sans passage par le lanceur, le système hôte peut être indiqué comme inconnu et le guide permet de choisir le système manuellement.

Ouvrir [le dashboard](http://localhost:8000), puis **Assistant ElioBot → Réglages**. Les commandes manuelles restent utilisables sans moteur IA.

## Gemini

Le fichier `.env` doit se trouver dans `server/control-dashboard/` :

```dotenv
GEMINI_API_KEY=votre_cle_google_ai_studio
```

Ce fichier est ignoré par Git. Compose injecte uniquement la variable nécessaire au dashboard ; en exécution native, le serveur lit également ce fichier. Il n'est pas copié dans l'image Docker.

Une clé peut aussi être saisie dans les réglages. Elle est enregistrée **sur le serveur** dans `assistant-data/settings.json` avec des permissions restrictives, jamais dans le stockage du navigateur ou dans les réponses HTTP. Une clé enregistrée dans les réglages a priorité sur la variable d'environnement. Pour la retirer, supprimer le champ `gemini_key` du fichier privé de configuration et redémarrer le dashboard ; la clé du `.env` redevient alors active.

Le modèle initial est `gemini-3.1-flash-lite`. **Enregistrer et tester** liste les modèles du compte sans générer de texte ; cette liste ne garantit pas leur disponibilité instantanée ni un quota gratuit. Le champ modèle permet d'en choisir un autre. Les erreurs de quota, d'accès, de modèle absent ou d'indisponibilité sont affichées dans le chat. Une erreur temporaire 502/503/504 autorise une seule nouvelle tentative de génération ; les actions robot déjà exécutées ne sont jamais rejouées.

Les messages, l'historique récent et les résultats des outils demandés sont transmis à Gemini lorsque ce moteur est choisi. La clé n'est pas placée dans l'URL. Il n'existe aucune bascule automatique entre moteurs.

En cas de quota ou de limite de requêtes Gemini (HTTP 429), le chat propose **Passer à Ollama** ou **Configurer Ollama**. Le premier bouton vérifie que l'instance configurée répond et que le modèle installé prend en charge les outils, puis sélectionne Ollama. Si cette vérification échoue, Gemini reste sélectionné. Aucun modèle n'est installé automatiquement. La conversation est conservée, mais la demande interrompue et les actions déjà transmises ne sont jamais relancées : envoyer une nouvelle demande pour continuer. Le message de quota reste accessible dans l'historique.

Sources : [clé API](https://ai.google.dev/gemini-api/docs/api-key), [tarification](https://ai.google.dev/gemini-api/docs/pricing), [quotas](https://ai.google.dev/gemini-api/docs/rate-limits).

## Ollama selon le système

| Hôte d'Ollama | Parcours conseillé | Accélération |
|---|---|---|
| Raspberry Pi, Linux ARM64 | Conteneur géré ElioBot, ou service natif existant | CPU ; tester un petit modèle |
| Linux x86-64 | Conteneur géré ElioBot | CPU ou NVIDIA avec pilotes et Container Toolkit |
| Mac Apple Silicon | Application Ollama native | GPU Apple via l'application native |
| Mac Intel | Application Ollama native | CPU |
| Windows | Application Ollama native | CPU ou GPU compatible ; dépend des pilotes |
| Autre machine du réseau | Instance distante existante | Dépend de cette machine |

Le conteneur géré utilise l'image officielle `ollama/ollama:latest`, conserve les modèles dans un volume portant un identifiant propre à cette installation et n'expose **aucun port sur l'hôte**. Le dashboard le joint sur `http://ollama:11434`. Les fonctions cloud d'Ollama y sont désactivées. Le téléchargement initial des modèles nécessite Internet ; leur exécution est ensuite locale.

Le choix GPU s'applique à la création du conteneur. Pour passer d'un conteneur CPU à NVIDIA, le désinstaller **en conservant les modèles**, puis le recréer avec NVIDIA. Un modèle ou un pilote incompatible peut échouer ; le diagnostic ne promet pas qu'un GPU sera utilisable.

### Application native ou machine distante

Choisir **Application sur la machine du serveur** ou **Instance sur une autre machine** :

- Dashboard dans Docker et Ollama sur le même Mac/PC : `http://host.docker.internal:11434`.
- Dashboard et Ollama tous deux natifs sur le même système : `http://127.0.0.1:11434`.
- Autre machine : `http://ADRESSE_LOCALE:11434`.

Ollama écoute normalement en boucle locale. Pour le joindre depuis un conteneur ou une autre machine, adapter `OLLAMA_HOST` et le pare-feu de la machine Ollama. Réserver l'accès au réseau local de confiance ; le dashboard contacte Ollama côté serveur, aucun réglage CORS du navigateur n'est nécessaire.

Exemples de configuration de l'écoute, **sur la machine Ollama** :

```bash
# macOS : quitter Ollama, définir la variable, puis relancer l'application
launchctl setenv OLLAMA_HOST "0.0.0.0:11434"
```

Sous Windows : définir la variable utilisateur `OLLAMA_HOST` à `0.0.0.0:11434`, quitter Ollama dans la zone de notification puis le relancer. Autoriser uniquement les connexions nécessaires sur le réseau privé dans le pare-feu.

Sous Linux natif : configurer `Environment="OLLAMA_HOST=0.0.0.0:11434"` dans un override du service Ollama, recharger systemd et redémarrer le service. Une adresse d'interface dédiée peut remplacer `0.0.0.0` selon le réseau.

Guides officiels : [macOS](https://docs.ollama.com/macos), [Windows](https://docs.ollama.com/windows), [Linux](https://docs.ollama.com/linux), [réseau et Docker](https://docs.ollama.com/faq).

### Modèles et mémoire

Choisir un modèle local compatible avec les appels d'outils. Point de départ : `qwen3:1.7b` sur une petite machine, `qwen3:4b` pour une machine plus confortable. Repères estimatifs pour le modèle et son contexte : environ 4 Go / 8 Go de RAM **disponible**, respectivement ; ajouter la mémoire du système, du dashboard et du connectome s'il est chargé. La mémoire exacte dépend de la quantification et du contexte. Ce n'est pas une garantie de qualité ou de vitesse.

L'interface indique la mémoire allouée au moteur Docker et la taille des modèles installés. Le connecteur utilise un contexte de 8 192 tokens, un seul modèle chargé et une génération à la fois dans l'instance gérée. Évaluer le temps de réponse avec une demande de lecture comme « Quel est ton état ? » avant de piloter.

## Gestion et désinstallation

Les actions de maintenance interrompent les commandes restantes du chat et arrêtent les mouvements qu'il possède. Elles ne sélectionnent jamais Gemini automatiquement.

- **Arrêter le service** : garde le conteneur et les modèles.
- **Déconnecter** : désactive l'utilisation de l'instance sans modifier le logiciel ni ses modèles. **Enregistrer** permet de la reconnecter.
- **Supprimer ce modèle** : confirmation explicite ; ne retire que le modèle choisi via l'API Ollama.
- **Désinstaller Ollama** : retire le conteneur créé par ElioBot. Les modèles sont conservés par défaut.
- **Supprimer aussi tous les modèles et les données** : option explicite dans la confirmation de désinstallation. Retire le volume géré, sans forcer la suppression s'il est encore utilisé.

Les tailles de volume ne sont affichées que si Docker peut les mesurer. L'image Docker téléchargée reste dans le cache Docker : elle peut être partagée avec d'autres installations. ElioBot ne fait aucun nettoyage global d'images ou de volumes.

Les identifiants de propriété sont enregistrés dans `assistant-runtime/`. Chaque ressource Docker est vérifiée avant sa modification. **Une installation native préexistante ou distante n'est jamais désinstallée automatiquement** : le guide de son système fournit la procédure. Une modification des modèles d'une instance externe exige une confirmation supplémentaire.

Le conteneur Ollama est créé dynamiquement par le gestionnaire et ne fait pas partie des services démarrés automatiquement par Compose. Arrêter ou désinstaller Ollama depuis l'interface **avant** `docker compose down` si l'on souhaite aussi l'arrêter : Compose seul ne supprime pas ce conteneur ni ses modèles.

Pour retirer entièrement cette fonctionnalité, désinstaller d'abord l'instance gérée depuis le dashboard, puis arrêter les services. Ne pas effacer `assistant-runtime/` avant la désinstallation : ce dossier contient l'identité des ressources gérées. Les réglages privés de l'assistant sont indépendants des modèles Ollama.

## Fonctionnement du chat et garanties d'exécution

- Conversation par onglet, conservée dans la mémoire du serveur (40 messages récents, 32 conversations maximum). Un redémarrage du serveur efface les conversations ; les réglages restent sur disque.
- Le changement de moteur conserve les messages et les résultats passés, mais aucun appel d'outil ancien n'est réexécuté.
- Une demande à la fois, au plus huit étapes de modèle et huit outils par étape, délai global de trois minutes.
- Les étapes et résultats arrivent immédiatement dans le chat ; le texte final est affiché à la fin de sa génération.
- Un déplacement dure de 0,1 à 3 secondes, à une vitesse de 1 à 70 %. Le serveur renouvelle les commandes toutes les 150 ms puis envoie l'arrêt. Le robot conserve son délai local de 800 ms.
- Une reprise manuelle, un Stop ou une annulation invalide les commandes en attente. Une réponse calculée avant un changement de mode n'est pas exécutée.
- Le chat ne contourne pas la confirmation de reprise manuelle depuis une autonomie. La reprise se fait depuis le dashboard.
- Une déconnexion pendant le flux du chat annule la demande en cours et arrête les actions qu'elle possède. Fermer seulement le panneau conserve la connexion et la demande.
- Le bouton **Arrêter le robot** et les messages exacts « stop », « arrête », « arrête-toi », « arrête le robot » ou « tout arrêter » n'attendent pas de modèle.
- Une commande transmise n'est pas une confirmation de déplacement physique. Les capteurs ne permettent pas de garantir une distance ou un angle précis.

### Demander une rotation en degrés

« **Tourne de 70 degrés à droite** » utilise l'outil `turn_robot`. Le serveur estime la durée avec le même calcul que l'exploration embarquée : diamètre des roues de 33,5 mm, entraxe de 77,5 mm, vitesse PWM, tension de batterie et `turn_factor`. Le modèle transmet l'angle demandé à cet outil sans calculer lui-même une durée. Le résultat est annoncé comme **approximatif**, puisque le robot ne mesure pas son angle réel.

Le programme `mqtt_dashboard` transmet maintenant `turn_factor` depuis `robot/config.json`. Redéployer ce programme pour appliquer sa calibration aux rotations du chat. Avec un ancien programme, le facteur utilisé est 1 ; en l'absence de mesure de batterie, la tension nominale utilisée est 3,7 V. Ces valeurs de remplacement sont indiquées dans le détail de l'action. Le réglage se calibre sur le sol utilisé : `nouveau facteur = ancien facteur × angle demandé / angle observé`, puis redéployer la configuration et redémarrer le programme. Il peut varier avec la vitesse et l'adhérence.

L'outil accepte 1–360° et 15–70 % (35 % par défaut), mais refuse toute combinaison dont la durée calculée sort de 0,1–3 secondes, sans tronquer l'angle ni contourner la limite. Les règles de connexion, de reprise manuelle et d'interruption sont celles des autres déplacements.

## MCP

Les outils sont `get_robot_state`, `move_robot`, `turn_robot`, `set_robot_speed`, `set_autonomy`, `stop_robot`.
Le chat utilise le SDK MCP officiel (branche 1.x bornée dans les dépendances) et un transport HTTP ASGI local. Il effectue réellement l'initialisation, la découverte des outils et leurs appels, sans ouvrir de port supplémentaire ni exposer le robot à Google.

L'accès MCP externe est désactivé par défaut. Pour un client compatible sur le réseau de confiance, définir un secret `ELIO_MCP_TOKEN` dans le `.env`, reconstruire/redémarrer le dashboard et utiliser :

- URL : `http://ADRESSE_DU_SERVEUR:8000/mcp/`
- Transport : Streamable HTTP
- En-tête : `Authorization: Bearer VOTRE_JETON`

Les outils de mouvement demandent la `generation` retournée par `get_robot_state`. Le client intégré l'injecte côté serveur ; le modèle ne peut pas choisir ni renouveler sa génération de contrôle. Un client externe doit gérer les interruptions et les consentements de son utilisateur.

Le dashboard existant reste destiné à un réseau de confiance et n'ajoute pas d'authentification globale. Ne pas le publier directement sur Internet. Le gestionnaire Ollama est un service privé, sans port publié, avec un jeton interne ; lui seul monte le socket Docker. Son API n'accepte que des opérations fixes sur les ressources qu'il possède.

## Vérification

```bash
cd server/control-dashboard/fastapi-dashboard
uv sync --group dev
uv run pytest ../../../tests
# Depuis la racine du dépôt :
node --test tests/*.test.cjs
```

Les tests de gestion Docker simulent le daemon pour vérifier la propriété des ressources, la conservation des modèles et la suppression explicite. Les tests d'assistant parlent au vrai serveur MCP mais simulent les sorties MQTT. Les essais physiques et les pilotes GPU nécessitent les machines correspondantes.
