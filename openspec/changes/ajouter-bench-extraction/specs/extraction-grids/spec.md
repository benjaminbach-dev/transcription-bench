## ADDED Requirements

### Requirement: Grilles en fichiers Markdown
Une grille d'extraction SHALL être un fichier Markdown UTF-8 d'au plus 64 Kio, placé directement dans le dossier `grilles/` du dépôt, nommé `<nom>.md` avec un nom de 1 à 64 caractères `[a-z0-9-]` commençant par une lettre ou un chiffre. Le programme MUST refuser tout autre emplacement, un lien symbolique sortant du dossier ou un nom non conforme.

#### Scenario: Grille d'exemple
- **WHEN** l'utilisateur exécute `grids list` sur un dépôt fraîchement extrait
- **THEN** la grille d'exemple de consultation de médecine générale est listée avec son titre, son nombre de cases, son empreinte et l'état valide

#### Scenario: Nom sortant du dossier
- **WHEN** une commande reçoit un nom de grille contenant un séparateur de chemin, `..` ou désignant un lien hors de `grilles/`
- **THEN** elle refuse avec le code 2 sans lire le fichier

### Requirement: Interprétation des cases
Le programme SHALL interpréter une grille ainsi : un titre `#` unique en premier contenu ; un texte facultatif de consignes générales avant la première case ; chaque titre `##` ouvre une case dont le texte suivant est la consigne ; la case est une liste si la première ligne non vide de sa consigne, blancs de tête retirés, commence par le mot « Liste » (casse ignorée) suivi d'espaces facultatifs puis de `.` ou `:` ; des titres `###` sous une case en font une case composée de sous-cases, chacune pouvant être une liste selon la même règle. Les titres placés dans un bloc de code clôturé par trois accents graves ou trois tildes ne sont pas interprétés ; un bloc non fermé rend la grille invalide.

#### Scenario: Case simple, liste et composée
- **WHEN** une grille contient `## Qui ?` sans consigne, `## Symptômes déclarés ?` suivi de « Liste. Un symptôme par entrée » et `## Prescription ?` suivi de « Liste. » puis `### Médicament`, `### Posologie`, `### Durée`
- **THEN** `grids show` présente une case texte `qui`, une liste de textes `symptomes_declares` et une liste composée `prescription` à trois sous-cases

#### Scenario: Mot Liste non reconnu
- **WHEN** une consigne commence par « Listes des antécédents » ou par « Liste » sans signe
- **THEN** la case reste une case texte

#### Scenario: Profondeur excessive ou structure invalide
- **WHEN** une grille contient un titre `####`, un `###` avant tout `##`, aucun `##`, plusieurs `#`, un bloc de code non fermé ou plus de 60 cases et sous-cases
- **THEN** la grille est déclarée invalide avec la ligne et la règle en cause, et elle n'est pas proposée à l'exécution

### Requirement: Clés stables et réservées
Chaque case et sous-case SHALL recevoir une clé dérivée de son libellé : décomposition Unicode NFKD sans marques diacritiques, `œ`→`oe`, `æ`→`ae`, `ß`→`ss`, minuscules, toute suite de caractères hors `[a-z0-9]` remplacée par un seul `_`, sans `_` en début ni en fin. Une clé vide, deux clés identiques au même niveau ou la clé réservée `autres_informations` MUST rendre la grille invalide.

#### Scenario: Libellés accentués
- **WHEN** une case est intitulée `Examens pratiqués ?`
- **THEN** sa clé est `examens_pratiques`, et `Œdème / douleur !!` donne `oedeme_douleur`

#### Scenario: Doublon
- **WHEN** deux cases ont pour libellés `Qui ?` et `Qui`
- **THEN** la grille est invalide et le refus nomme les deux lignes

### Requirement: Valeurs non mentionnées et section hors grille
Chaque case et sous-case SHALL accepter la valeur « non mentionné », représentée par `null`. Une liste non nulle contient au moins une entrée. Une chaîne vide est conforme mais affichée « (vide) », distincte de « non mentionné ». Une section `autres_informations` SHALL être ajoutée d'office après les cases de la grille : une liste, éventuellement vide, d'entrées composées d'un intitulé et d'une valeur textuels, destinée aux informations utiles absentes de la grille.

#### Scenario: Section ajoutée d'office
- **WHEN** `grids show` est exécuté sur une grille valide
- **THEN** le schéma présenté contient toutes les cases de la grille puis `autres_informations`, et la grille elle-même ne la déclare pas

### Requirement: Schéma JSON généré
Le programme SHALL convertir chaque grille valide en un schéma JSON n'utilisant que objets, tableaux, chaînes, `null`, `anyOf`, `minItems`, `required` et `additionalProperties: false`, où toutes les clés sont requises. La conversion MUST être déterministe : une même grille produit toujours le même schéma.

#### Scenario: Schéma déterministe
- **WHEN** `grids show --json` est exécuté deux fois sur la même grille
- **THEN** les deux schémas sont identiques octet pour octet

#### Scenario: Toutes les cases exigées
- **WHEN** une sortie omet une case ou ajoute une clé inconnue
- **THEN** la validation interne du programme la déclare non conforme

### Requirement: Empreinte et copie de la grille
L'empreinte d'une grille SHALL être le SHA-256 de son fichier. Chaque exécution d'extraction MUST consigner cette empreinte et conserver une copie exacte du fichier et du schéma généré, de sorte qu'une modification ultérieure de la grille n'altère pas les résultats existants.

#### Scenario: Grille modifiée après une exécution
- **WHEN** l'utilisateur modifie une grille déjà utilisée puis relit une ancienne extraction
- **THEN** l'ancienne extraction s'affiche avec sa copie de grille d'origine, et les nouvelles extractions forment un groupe distinct

### Requirement: Consultation des grilles sans écriture
`grids list` SHALL lister les grilles avec nom, titre, nombre de cases, empreinte et état (valide ou motif d'invalidité). `grids show NOM` SHALL présenter les cases interprétées, le schéma généré et le message système complet qui serait envoyé au modèle. Ces commandes MUST NOT écrire de fichier ni accéder au réseau.

#### Scenario: Vérifier l'interprétation avant de lancer
- **WHEN** l'utilisateur ou un agent modifie une grille puis exécute `grids show`
- **THEN** il voit comment chaque titre a été interprété (clé, type, consigne) avant toute exécution

#### Scenario: Grille invalide
- **WHEN** `grids show` vise une grille invalide
- **THEN** la commande se termine avec le code 2 et indique la ligne et la règle en cause
