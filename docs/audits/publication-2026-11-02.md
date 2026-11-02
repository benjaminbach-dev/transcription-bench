# Audit préalable à la publication — 2026-11-02

## Verdict provisoire : ne pas rendre le dépôt public

Audit en lecture seule, réalisé avant toute modification de visibilité. Aucun commit, push, nettoyage d'historique, installation d'outil ni workflow exécuté. Ce document ne constitue pas une garantie d'absence de secrets.

## Périmètre et constats exécutés

- Dépôt GitHub ciblé : `benjaminbach-dev/transcription-bench`, visibilité PRIVATE confirmée via `gh repo view`.
- Base : branche `main`, initialement propre et alignée sur `origin/main` ; 40 commits accessibles par les références locales.
- Historique local accessible : 313 versions de blobs, dont 59 versions de notes mémoire exclues du parcours Git pour respecter l'accès mémoire exclusivement via MCP.
- Sur les blobs hors mémoire : aucune correspondance aux formats de jetons GitHub/Hugging Face/AWS recherchés, aux en-têtes de clés privées, aux URL HTTP à identifiants intégrés ou aux chemins personnels absolus recherchés. Les valeurs potentielles n'ont pas été imprimées. Recherche heuristique limitée, sans détecteur spécialisé installé ; les secrets de format libre ne sont pas exclus.
- Aucun blob binaire ou supérieur à 1 Mo trouvé dans cet historique ; aucun chemin de poids, audio, dossier `data/`, sous-module ou LFS identifié dans les noms recherchés. Cela ne prouve pas l'absence de contenu sensible textuel.
- Deux identités d'auteur historiques, avec deux adresses électroniques personnelles/professionnelles, seraient publiées. Leurs valeurs ne sont pas recopiées ici.
- Mémoire courante : 15 notes lues via Basic Memory MCP, projet `transcription-bench`, pointant sur la mémoire de ce clone. Aucune correspondance aux formats de jetons/en-têtes de clés recherchés. Plusieurs notes décrivent la machine et le contexte d'utilisation.
- API GitHub consultée : aucun run Actions, aucune release, aucune issue ou pull request (requête paginée `state=all`). Une seule branche distante `main`, à la base `1424424d910abff72efd2eb3bc619b4557aaf7de`, aucun tag. Wiki, discussions et Pages désactivés, aucun fork déclaré par l'API. Les éventuelles références cachées ou objets supprimés ne sont pas couverts.
- Aucune licence de projet reconnue par GitHub (`licenseInfo: null`). La licence à choisir appartient au titulaire des droits ; aucune licence ajoutée arbitrairement.

## Blocages et décisions avant publication

1. **Contexte d'une tierce personne dans la mémoire — état courant anonymisé.** Sur demande explicite du propriétaire, la note de cadrage a été modifiée via MCP le 2026-11-02 : identité supprimée et contexte associé remplacé par une formulation métier générique. Relecture de la note et recherche textuelle dans la mémoire courante : aucune occurrence du prénom initial. Ni l'identité ni le contexte ne sont reproduits dans ce rapport. Cette correction ne purge pas les anciennes versions Git : le point 2 reste ouvert.
2. **L'historique conserve les anciennes versions.** Corriger les notes actuelles ne suffit pas. Les 59 versions historiques de notes ne sont pas auditables par le MCP mémoire courant avec les outils consultés ; elles n'ont pas été lues par un contournement Git/fichiers. Définir une procédure expressément autorisée pour les auditer et, si nécessaire, assainir l'historique ou publier un historique neuf. Aucune réécriture d'historique autorisée ou exécutée.
3. **Décider de l'exposition du contexte personnel.** Chemin initial du clone, caractéristiques matérielles, identité et adresses des auteurs, contexte de collaboration et notes de travail deviennent publics. Les identifiants techniques de mesure ne sont pas des secrets, mais leur publication doit être assumée.
4. **Licence du code — décision prise.** Sur accord du propriétaire, licence MIT ajoutée dans `LICENSE`, avec métadonnées du projet alignées. Les licences des modèles et dépendances restent distinctes ; voir `docs/licences-modeles.md` pour le relevé ciblé et ses limites. Aucun poids ni paquet tiers n'est redistribué.
5. **Audit final du candidat réellement publié.** Refaire les contrôles après les changements de specs et les éventuelles corrections ; vérifier toutes les références distantes et surfaces GitHub pertinentes. Ne pas assimiler cet audit local aux objets distants ou supprimés non accessibles localement.

## Hors périmètre de cette passe

- Valeurs de secrets et fichiers d'authentification : non consultés.
- Objets distants non accessibles par les références locales, objets orphelins, historique de notes via Git : non audités.
- CI et moteurs Windows : aucune exécution, installation ou inférence.
- Redistribution de dépendances et poids : aucune effectuée ; licences et conditions exactes des versions/révisions devront être établies avant leur intégration/redistribution ou essais CI autorisés. Ne pas présumer qu'un téléchargement de test équivaut à une redistribution.

## Sauvegarde et candidat local assaini

Sur accord du propriétaire, une sauvegarde privée vérifiée (`git bundle verify`) et un candidat nu séparé ont été préparés sous `data/publication-privee/`, ignoré par Git et créé avec un masque de permissions restrictif. **Le dépôt de travail et le distant n'ont pas été réécrits.** Le bundle protège l'historique committé initial ; il ne remplace pas une sauvegarde des modifications non committées, qui restent dans le dépôt de travail.

L'index de chacun des 40 commits du candidat a été filtré pour retirer tout le dossier mémoire, sans lire ses anciens contenus par un contournement du MCP. La branche candidate `main` ne contient plus aucun chemin historique `.basic-memory/` ; aucun prénom tiers recherché dans ses messages de commit. Un bundle séparé de la seule branche assainie a été vérifié. Les notes courantes anonymisées pourront être réintroduites dans un futur commit après leur audit final, sans restaurer leurs anciennes versions.

**Le candidat nu conserve des références privées de récupération `refs/original/` : ne jamais le publier par `push --mirror`.** La sauvegarde complète doit rester privée. La base assainie ne contient pas encore les modifications de cette session (licence, specs, adaptateurs, CI, documentation).

Une réécriture et un push forcé ne garantissent pas la purge des anciennes vues et objets côté GitHub. La documentation officielle indique qu'ils peuvent rester accessibles par SHA ou références cachées. Le choix entre purge coordonnée du dépôt existant et publication dans un nouveau dépôt public sans les objets privés doit être explicite. Aucun push forcé, création de dépôt ni changement de visibilité n'a été effectué. Source : [suppression de données sensibles sur GitHub](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

## Revue indépendante de l'arbre courant

Le scout en lecture seule n'a trouvé aucun secret connu ni promesse clinique dans les fichiers courants examinés hors mémoire et historique. Il confirme l'absence de workflow et de licence du projet. Les instructions d'agents et les artefacts OpenSpec exposent le processus de développement : ce n'est pas un blocage de sécurité démontré ni une raison de les supprimer automatiquement. Les dépendances et poids ne sont pas redistribués dans le dépôt ; ne pas ajouter des obligations d'attribution non établies. Les licences exactes restent à contrôler avant une éventuelle redistribution.

Recommandations non bloquantes : clarifier que les tests sans réseau externe autorisent le loopback ; examiner la dépendance de test HTTP transitive ; documenter les prérequis Windows sans prendre l'image CI richement équipée pour un PC neuf. Ne pas bloquer globalement le réseau du runner pendant l'installation ni couper sa liaison avec GitHub : l'isolation éventuelle de l'inférence doit être ciblée et vérifiée.

## Suite

Présenter les décisions au propriétaire, puis seulement autoriser les corrections de confidentialité et la publication du candidat assaini. Les tâches CI ne sont pas considérées réalisées par cet audit.

## Conclusion après publication — 2026-11-02, soir

Le propriétaire a tranché le 2026-11-02 : publier le dépôt existant tel quel,
historique complet, en assumant l'exposition des éléments personnels
(identités d'auteur, machine, notes de travail). Le candidat assaini est
abandonné comme voie de publication (il reste une archive privée locale,
jamais à publier ni à `push --mirror`). Cette conclusion distingue trois
catégories :

**Contrôles exécutés** : scan heuristique de l'historique complet avant
publication (369 blobs, aucun format de secret, binaire, blob volumineux ni
chemin `data/` reconnus — recherche non exhaustive, sans détecteur
spécialisé) ; anonymisation de l'état courant des notes mémoire (vérifiée par
relecture) ; licence MIT ajoutée ; API GitHub consultée avant le changement
de visibilité (aucune fork, release, issue, PR, Pages) ; constat de
visibilité publique après bascule.

**Risques acceptés par décision explicite du propriétaire** : exposition des
identités d'auteur et adresses, du contexte machine, du journal de travail
versionné (`.basic-memory/`) ; présence du prénom d'une tierce personne dans
les anciennes versions Git des notes (l'état courant est anonymisé) ;
absence d'audit intégral des 59 versions historiques de notes.

**Contrôles non exécutés** : audit exhaustif des contenus historiques de la
mémoire, audit final du candidat (objet abandonné), purge coordonnée des
objets distants (sans objet, aucune réécriture effectuée).

Le verdict initial « ne pas rendre le dépôt public » est levé par cette
décision assumée ; il reste la référence des constats. Les tâches CI
(10.3–10.6) ont été exécutées après publication et consignées dans
`docs/ci-windows.md`.
