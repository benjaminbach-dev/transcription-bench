## ADDED Requirements

### Requirement: Contexte système distinct de l'empreinte moteur
Le détail et la comparaison SHALL montrer, lorsqu'ils sont disponibles, le CPU moyen de l'ordinateur pendant l'audio et la RAM disponible après l'audio, sous des libellés distincts du CPU et du pic mémoire du moteur. Les observations système MUST NOT servir à classer les modèles, ni à promettre une marge CPU réellement disponible ou un ordinateur fluide.

#### Scenario: Lecture des ressources de l'ordinateur
- **WHEN** un résultat dispose des observations système et des indicateurs moteur
- **THEN** les indicateurs moteur restent identifiés comme tels et une ligne de contexte visible indique « Ordinateur : CPU total moyen 90 % pendant la transcription ; RAM disponible après : 5,2 Go sur 16 Go », avec les valeurs propres à cet essai

#### Scenario: Résultat sans observation système
- **WHEN** l'utilisateur consulte un ancien résultat sans ces relevés
- **THEN** les indicateurs moteur restent disponibles selon leurs données et le contexte système indique « non mesuré » sans simuler une observation depuis des ratios moteur

### Requirement: Interprétation bornée de la marge mémoire
La RAM disponible SHALL être présentée avec la capacité totale consignée au même instant et une aide distinguant après chargement et après audio. L'interface MUST NOT présenter cet instantané comme la RAM minimale restée disponible ni calculer la marge réelle par RAM totale moins pic mémoire du moteur.

#### Scenario: Relevés de mémoire distincts
- **WHEN** le pic du moteur vaut 2,4 Go sur une machine de 16 Go et que l'instantané après audio indique 5,2 Go disponibles
- **THEN** la part de RAM du moteur et les 5,2 Go disponibles sont présentés comme deux informations différentes ; l'interface n'annonce pas 13,6 Go comme marge restante et le relevé après chargement reste accessible en détail

### Requirement: Limites du contexte système accessibles
L'aide locale SHALL expliquer que le CPU global inclut les autres programmes, que la mémoire disponible est estimée par le système à un instant donné et que les pourcentages reposent sur les ressources visibles par le système. Les quotas, affinités et ressources virtualisées MUST NOT être présentés comme une capacité matérielle garantie.

#### Scenario: Ordinateur partagé ou virtualisé
- **WHEN** une observation est consultée sur un essai provenant d'un ordinateur partagé ou virtualisé
- **THEN** elle est décrite comme le contexte de cet essai, pas comme une propriété du modèle, une capacité disponible garantie ou une preuve de performance sur un autre ordinateur
