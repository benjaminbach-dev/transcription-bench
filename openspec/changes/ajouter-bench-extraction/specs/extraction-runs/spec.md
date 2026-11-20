## ADDED Requirements

### Requirement: Sources d'extraction
Une source d'extraction SHALL être désignée par `identifiant:ordre` et correspondre à un audio terminé, avec un texte non vide, d'une exécution de transcription enregistrée. Une source inexistante, en erreur, non traitée, vide ou désignée par un identifiant sortant du dossier des résultats MUST être refusée. Une transcription factice MAY servir de source ; l'extraction est alors marquée « source factice ».

#### Scenario: Source valide
- **WHEN** l'utilisateur exécute `extract check` avec une source `identifiant:ordre` désignant une transcription terminée
- **THEN** la demande normalisée indique l'audio, son empreinte, le modèle et le moteur de transcription, la longueur du texte et l'empreinte du texte

#### Scenario: Source inutilisable
- **WHEN** la source désigne un audio en erreur, non traité ou un identifiant inconnu
- **THEN** la commande refuse avec le code 2 et le motif, sans rien lancer

### Requirement: Configuration d'une extraction
Une extraction SHALL associer un modèle d'extraction prêt, son moteur, une grille valide, une ou plusieurs sources ordonnées, les threads demandés et les seuls réglages de la famille. `extract options` présente les modèles d'extraction exécutables ou non avec motif, les grilles valides, les sources proposables, les threads par défaut et les réglages avec leurs défauts. `extract check` valide la demande sans rien lancer ni écrire ; `extract start` lance l'extraction après la même validation.

#### Scenario: Modèle de transcription proposé à l'extraction
- **WHEN** `extract check` reçoit un modèle d'un moteur de transcription
- **THEN** la commande refuse avec le code 2 en indiquant que le modèle n'est pas un modèle d'extraction

#### Scenario: Grille invalide
- **WHEN** `extract start` reçoit une grille invalide
- **THEN** la commande refuse avec le code 2 et le motif de la grille, sans lancer d'opération

#### Scenario: Arguments acceptés
- **WHEN** l'utilisateur exécute `extract start`
- **THEN** la commande accepte `--model`, `--grid`, `--source` répétable et ordonné, `--threads` et `--setting NOM=VALEUR` applicables à la famille du modèle

### Requirement: Consignes versionnées
Le programme SHALL construire, à partir d'un gabarit interne versionné, un message système contenant les règles d'extraction, les consignes générales de la grille et la description de chaque case, puis un message utilisateur contenant la transcription source. La version du gabarit MUST être consignée avec chaque exécution.

#### Scenario: Message système consultable
- **WHEN** une extraction est terminée
- **THEN** le message système exact et la version du gabarit sont conservés avec le résultat

#### Scenario: Règles fixes du message système
- **WHEN** le message système est construit
- **THEN** ses règles demandent de n'utiliser que ce qui est dit, de renvoyer « non mentionné » plutôt que d'inventer, de reprendre médicaments, doses et chiffres tels qu'entendus et d'utiliser `autres_informations` pour l'utile hors grille

### Requirement: Sortie contrainte et validée
Le moteur SHALL contraindre la génération par une grammaire convertie explicitement depuis le schéma de la grille puis chargée nativement avant la première source. Un échec de conversion ou de chargement, ou tout repli vers une contrainte plus large, MUST mettre l'exécution en échec avec ce motif, sans générer. Le programme MUST valider lui-même chaque sortie contre le schéma, en refusant les clés JSON dupliquées. La conformité ne mesure que la forme, jamais l'exactitude.

#### Scenario: Grammaire impossible à compiler
- **WHEN** la compilation de la grammaire échoue pour le schéma d'une grille
- **THEN** l'exécution passe en échec avec ce motif avant toute génération et la commande se termine avec le code 1

#### Scenario: Sortie conforme
- **WHEN** le modèle produit un JSON conforme au schéma
- **THEN** la valeur décodée et la sortie brute sont enregistrées et l'état de la source est terminé et conforme

#### Scenario: Limite de sortie atteinte
- **WHEN** la génération s'arrête parce que le réglage `sortie_max` est atteint
- **THEN** la source est enregistrée non conforme avec la fin « limite », la sortie brute est conservée et l'exécution continue avec la source suivante

#### Scenario: Arrêt de la génération et sortie brute
- **WHEN** la génération s'arrête sur un token de fin du modèle ou à la limite `sortie_max`
- **THEN** la sortie brute est conservée dès qu'au moins un token a été généré ; une sortie non conforme ou interrompue par la limite est enregistrée avec l'état « non conforme » et son motif, sans être corrigée ni complétée

### Requirement: Génération reproductible et CPU
Une extraction SHALL s'exécuter sur CPU uniquement, hors ligne à partir des fichiers locaux, avec un décodage glouton et une graine fixe consignés. Le prompt SHALL être assemblé par un format de conversation maintenu localement pour l'architecture du modèle et versionné ; le gabarit embarqué dans le fichier du modèle MUST NOT être compilé ni interprété, même au chargement. Les réglages `contexte` et `sortie_max` SHALL être exposés avec leurs défauts.

#### Scenario: Lot de deux sources
- **WHEN** une extraction porte sur deux sources partageant le même message système
- **THEN** le modèle est chargé une fois, le cache est réinitialisé avant la seconde source et les tokens lus de la seconde source incluent tout son prompt

#### Scenario: Aucun effet d'une source sur la suivante
- **WHEN** plusieurs sources sont extraites dans une même exécution
- **THEN** l'état du modèle est réinitialisé avant chaque source, sans réutilisation de préfixe ni cache de prompt, pour que la lecture d'une source ne bénéficie pas de celle de la précédente

### Requirement: Contexte insuffisant refusé sans troncature
Avant de générer, le programme SHALL tokeniser le prompt effectivement soumis, tokens spéciaux compris, avec le tokenizer du modèle ; ce sont ces tokens qui sont comptés et soumis. Si ce nombre augmenté de `sortie_max` dépasse `contexte`, la source MUST être enregistrée en erreur « contexte insuffisant » avec les deux nombres, sans tronquer la transcription.

#### Scenario: Transcription trop longue
- **WHEN** une transcription produit un prompt de 15 000 tokens avec `contexte` 16384 et `sortie_max` 4096
- **THEN** la source est en erreur « contexte insuffisant », aucun texte n'est généré pour elle et les sources suivantes sont traitées

### Requirement: Traitement séquentiel et arrêt
Les sources d'une extraction SHALL être traitées une par une avec un seul chargement du modèle, et le résultat de chaque source MUST être enregistré dès qu'il est produit. L'arrêt par signal, la clôture d'une extraction abandonnée et l'opération longue unique suivent les mêmes règles que les exécutions de transcription.

#### Scenario: Arrêt pendant un lot
- **WHEN** l'utilisateur interrompt `extract start` après la première source d'un lot de trois
- **THEN** le résultat de la première source est conservé, les autres sont marquées non traitées, l'extraction est interrompue et le code de sortie est 3

#### Scenario: Arrêt brutal
- **WHEN** le programme redémarre après une terminaison brutale pendant une extraction
- **THEN** le moteur survivant vérifié est terminé et l'extraction est clôturée en état abandonné, ses résultats déjà écrits restant consultables

### Requirement: Mesures d'extraction
Le programme SHALL mesurer, pour chaque source, token par token : tokens du prompt soumis et générés, délai avant le premier token généré (lecture du prompt comprise), durée de génération, durée de l'extraction, temps CPU, pic de mémoire cumulatif du processus moteur et cause de fin. Par exécution : temps de chargement, durée du processus moteur, durée totale, contexte système. Une mesure indisponible MUST être absente, jamais remplacée par zéro ; aucun score de qualité n'est calculé.

#### Scenario: Source extraite
- **WHEN** une source est extraite
- **THEN** ses mesures sont enregistrées en valeurs brutes avec leurs unités ; les compteurs natifs du moteur ne sont consignés, à part et sous leur nom, que s'ils ont été vérifiés lisibles et cohérents, sans remplacer les mesures du programme

#### Scenario: Un seul token produit
- **WHEN** la génération ne produit qu'un token
- **THEN** la vitesse de génération est absente et non nulle

#### Scenario: Vitesses dérivées
- **WHEN** les mesures d'une source sont calculées
- **THEN** la vitesse de génération vaut (tokens générés − 1) / durée de génération et la vitesse de lecture estimée vaut tokens du prompt / délai avant le premier token, étiquetée comme estimation

### Requirement: Métadonnées et conservation
Chaque extraction SHALL être enregistrée dans un emplacement unique sous `data/extractions/` avec grille, consignes, modèle, moteur, réglages effectifs, threads, machine, programme, date, et par source texte copié, provenance, sortie brute, valeur décodée et mesures. Les écritures sont atomiques ; le résultat d'une source est écrit en dernier et marque sa publication ; une extraction finalisée n'est jamais modifiée. Le journal d'exécution MUST NOT contenir le texte source ni la sortie du modèle.

#### Scenario: Même source extraite de nouveau
- **WHEN** une source est extraite une seconde fois avec la même configuration
- **THEN** un nouveau résultat est créé et le précédent reste inchangé

#### Scenario: Résultat de transcription source supprimé ou illisible
- **WHEN** l'exécution de transcription d'origine n'est plus lisible
- **THEN** l'extraction reste consultable grâce à sa copie du texte source et à sa provenance consignée

#### Scenario: Détail des métadonnées et fichiers de travail
- **WHEN** une extraction est enregistrée
- **THEN** le modèle porte identifiant, révision, fichier, famille et architecture ; les threads demandés et appliqués et le mode de chargement des poids sont consignés si vérifiables ; la provenance d'une source porte exécution, ordre, audio et empreinte, modèle et moteur de transcription et marque factice ; les fichiers de travail contenant texte source ou sortie du modèle sont supprimés à la fin de l'opération ou lors de la récupération

### Requirement: Extraction factice
Le moteur factice SHALL proposer une famille d'extraction qui, sans réseau ni modèle, produit pour une grille une sortie conforme déterministe et des mesures simulées clairement identifiées comme factices.

#### Scenario: Extraction factice
- **WHEN** `extract start` utilise le modèle synthétique du moteur factice
- **THEN** le résultat est conforme au schéma, marqué factice et ses mesures sont signalées simulées dans toutes les vues

### Requirement: États et code de sortie d'une extraction
Chaque source SHALL avoir l'un des états conforme, non conforme, erreur ou non traitée ; une source sans fichier de résultat publié est non traitée. L'exécution suit les états des exécutions de transcription. `extract start` SHALL se terminer avec le code 0 si toutes les sources sont conformes, 1 si au moins une source est non conforme ou en erreur ou si l'exécution est en échec, 2 en cas de refus et 3 après un signal, avec un résumé par source.

#### Scenario: Lot partiellement non conforme
- **WHEN** une extraction de trois sources produit deux sources conformes et une non conforme
- **THEN** les trois résultats sont enregistrés, le résumé identifie la source non conforme et le code de sortie est 1

#### Scenario: Interruption entre deux écritures
- **WHEN** le programme est tué après l'écriture de la sortie brute d'une source mais avant son fichier de résultat
- **THEN** à la récupération, la source est considérée non traitée et l'extraction est abandonnée, sans fichier JSON tronqué
