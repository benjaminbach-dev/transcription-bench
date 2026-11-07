/*
 * Amélioration progressive de l'interface locale (design D6).
 *
 * Fichier unique servi par la route fixe /app.js, chargé avec `defer` par le
 * squelette commun : aucune dépendance, aucun CDN, aucune étape de compilation,
 * aucun code téléchargé à l'exécution et aucun code issu des modèles. Sans lui,
 * l'interface HTML reste complète : le lien Actualiser recharge la page et
 * toutes les actions restent des formulaires protégés.
 *
 * Seulement deux comportements, tous deux facultatifs : la mise à jour des
 * sélections compatibles de la préparation (design D4, tâche 4.2) et le suivi
 * borné de l'opération longue dans Exécutions (design D5, tâche 3.3). Aucun ne
 * déclenche de mutation : la préparation recharge la même requête GET, sans
 * jeton ni réglage, et le suivi ne fait que lire `GET /executions/etat`.
 */
"use strict";

(function () {
  "use strict";

  var DELAI_SUIVI_MS = 3000;
  var CHEMIN_ETAT = "/executions/etat";
  var MESSAGE_ECHEC =
    "Suivi automatique interrompu : le lien Actualiser recharge l'état.";
  var LIBELLES = {
    etat: "État : ",
    type: "Type : ",
    cible: "Cible : ",
    erreur: "Erreur : "
  };

  /*
   * Chemin local exact d'un résultat, ou `null` si la valeur reçue ne décrit
   * pas `/resultats/<identifiant>`. `new URL` normalise le chemin avant
   * contrôle : `/resultats/../../evil` devient `/evil` et n'est donc jamais
   * accepté au motif qu'il commence par `/resultats/`. Sont refusés : autre
   * origine, protocole relatif (`//hôte`), paramètre, fragment et chemin plus
   * profond qu'un identifiant unique.
   */
  function cheminResultatLocal(valeur) {
    if (typeof valeur !== "string" || valeur === "" || valeur.startsWith("//")) {
      return null;
    }
    var adresse;
    try {
      adresse = new URL(valeur, window.location.href);
    } catch (erreur) {
      return null;
    }
    if (adresse.origin !== window.location.origin) {
      return null;
    }
    if (adresse.search !== "" || adresse.hash !== "") {
      return null;
    }
    var segments = adresse.pathname.split("/");
    if (segments.length !== 3) {
      return null;
    }
    if (segments[0] !== "" || segments[1] !== "resultats" || segments[2] === "") {
      return null;
    }
    if (!/^[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$/.test(segments[2])) {
      return null;
    }
    return adresse.pathname;
  }

  /*
   * Préparation unique (design D4, tâche 4.2) : changer Modèle, Audio ou Moteur
   * recharge la préparation sans attendre le bouton « Appliquer les choix » et
   * sans rien lancer, installer ni télécharger. Le formulaire GET rendu par
   * Jinja est soumis tel quel — méthode `get`, même action, aucun jeton —
   * exactement comme le repli sans JavaScript : le serveur reste seul juge des
   * valeurs retenues et revalide tout. Avant la soumission, les réglages
   * avancés affichés (`threads`, `reglage_*`) sont recopiés dans les copies
   * prévues du formulaire GET : seules ces valeurs non sensibles sont
   * conservées, jamais le jeton, et le serveur décide s'il peut les garder.
   * Le moteur affiché est ensuite aligné sur la référence choisie (`data-moteur`), et le choix d'un
   * moteur prend la première référence réellement compatible
   * (`data-reference`) : aucune combinaison n'est inventée et aucun format de
   * poids n'est converti. Si ces attributs manquent, rien n'est modifié et le
   * bouton HTML reste disponible.
   */
  var ANCRE_PREPARATION = "#preparation";

  /* Option d'un sélecteur par sa valeur, ou `null` si elle n'y figure pas. */
  function optionDeValeur(selecteur, valeur) {
    var options = selecteur.options;
    if (!options) {
      return null;
    }
    for (var position = 0; position < options.length; position += 1) {
      if (options[position].value === valeur) {
        return options[position];
      }
    }
    return null;
  }

  function demarrerPreparation() {
    var formulaire = document.querySelector("[data-preparation-choix]");
    if (formulaire === null) {
      return;
    }
    var modele = formulaire.querySelector("[data-choix-modele]");
    var moteur = formulaire.querySelector("[data-choix-moteur]");
    if (modele === null) {
      return;
    }
    var choix = optionDeValeur(modele, modele.value);
    if (choix === null || choix.getAttribute("data-moteur") === null) {
      return;
    }

    /*
     * Recopie les réglages avancés encore affichés dans les copies cachées du
     * formulaire GET (design D4) : la valeur de la préparation appliquée est
     * reprise pour `threads` et pour chaque `reglage_*` déclaré, jamais le jeton
     * anti-CSRF ni un autre champ. Une copie sans valeur disponible reste
     * désactivée : elle n'est pas transmise et le serveur remplace alors la
     * valeur par son défaut en l'annonçant.
     */
    function copierReglages() {
      var lancement = document.querySelector("[data-preparation-lancement]");
      var valeurs = {};
      if (lancement !== null) {
        var controles = lancement.querySelectorAll("[data-valeur-reglage]");
        for (var position = 0; position < controles.length; position += 1) {
          var controle = controles[position];
          if (controle.type === "radio" && !controle.checked) {
            continue;
          }
          valeurs[controle.name] = controle.value;
        }
      }
      var copies = formulaire.querySelectorAll("[data-copie-reglage]");
      for (var copie = 0; copie < copies.length; copie += 1) {
        var cible = copies[copie];
        if (!Object.prototype.hasOwnProperty.call(valeurs, cible.name)) {
          cible.disabled = true;
          continue;
        }
        cible.value = valeurs[cible.name];
        cible.disabled = false;
      }
    }

    /* Recharge la même requête GET en gardant la vue sur la préparation. */
    function appliquer() {
      copierReglages();
      var action = formulaire.getAttribute("action");
      if (
        typeof action === "string" &&
        action !== "" &&
        action.indexOf("#") === -1
      ) {
        formulaire.setAttribute("action", action + ANCRE_PREPARATION);
      }
      formulaire.submit();
    }

    function surModele() {
      if (moteur === null) {
        appliquer();
        return;
      }
      var option = optionDeValeur(modele, modele.value);
      var identifiant = option === null ? null : option.getAttribute("data-moteur");
      if (identifiant === null || optionDeValeur(moteur, identifiant) === null) {
        return;
      }
      moteur.value = identifiant;
      appliquer();
    }

    function surMoteur() {
      var option = optionDeValeur(moteur, moteur.value);
      var reference = option === null ? null : option.getAttribute("data-reference");
      var courant = optionDeValeur(modele, modele.value);
      if (reference === null || optionDeValeur(modele, reference) === null) {
        return;
      }
      /* Le modèle affiché est déjà servi par ce moteur : ne pas en changer. */
      if (courant !== null && courant.getAttribute("data-moteur") === moteur.value) {
        return;
      }
      modele.value = reference;
      appliquer();
    }

    modele.addEventListener("change", surModele);
    if (moteur !== null) {
      moteur.addEventListener("change", surMoteur);
    }
    var audios = formulaire.querySelectorAll("[data-choix-audio]");
    for (var position = 0; position < audios.length; position += 1) {
      audios[position].addEventListener("change", appliquer);
    }
    var bouton = document.querySelector("[data-action-appliquer]");
    if (bouton !== null) {
      /* Sans intérêt une fois la sélection automatique : repli sans script. */
      bouton.hidden = true;
    }
  }

  /* Lancée avant le suivi, qui peut sortir tôt quand aucune opération n'est
     affichée : la préparation reste améliorée sur une page sans opération. */
  demarrerPreparation();

  var racine = document.querySelector("[data-suivi-operation]");
  if (racine === null) {
    return;
  }
  if (racine.getAttribute("data-etat-url") !== CHEMIN_ETAT) {
    return;
  }
  if (racine.getAttribute("data-actif") !== "oui") {
    return;
  }

  function champ(nom) {
    return racine.querySelector('[data-champ="' + nom + '"]');
  }

  var generationInitiale = Number(racine.getAttribute("data-generation"));
  var champLien = champ("lien-resultat");
  var champEchec = champ("echec");
  var minuterie = null;
  var requeteEnCours = false;
  var termine = false;
  var arretApplicable = true;
  var formulaireArret = document.querySelector("[data-arret-operation]");
  var boutonArret = formulaireArret === null ? null :
    formulaireArret.querySelector('[data-champ="bouton-arret"]');

  if (formulaireArret !== null) {
    formulaireArret.addEventListener("submit", function (evenement) {
      if (!arretApplicable) {
        evenement.preventDefault();
      }
    });
  }

  function inactiverArret() {
    arretApplicable = false;
    if (boutonArret !== null) {
      // Ne pas masquer/désactiver nativement le bouton : garder son focus.
      boutonArret.setAttribute("aria-disabled", "true");
      boutonArret.setAttribute("class", "secondary");
      boutonArret.textContent = "Opération terminée : arrêt sans objet";
    }
  }

  /* Met à jour une ligne du résumé sans jamais interpréter son texte. */
  function afficherLigne(nom, valeur) {
    var ligne = champ(nom);
    if (ligne === null) {
      return;
    }
    var presente = typeof valeur === "string" && valeur !== "";
    ligne.hidden = !presente;
    var texte = presente ? LIBELLES[nom] + valeur : "";
    if (ligne.textContent !== texte) {
      ligne.textContent = texte;
    }
  }

  /* Pose le lien de résultat seulement après validation locale de sa cible. */
  function afficherResultat(valeur) {
    var ligne = champ("resultat");
    if (ligne === null || champLien === null) {
      return;
    }
    var chemin = cheminResultatLocal(valeur);
    if (chemin === null) {
      champLien.removeAttribute("href");
      ligne.hidden = true;
      return;
    }
    champLien.setAttribute("href", chemin);
    ligne.hidden = false;
  }

  function afficherEtat(donnees) {
    afficherLigne("etat", donnees.libelle_etat);
    afficherLigne("type", donnees.libelle_type);
    afficherLigne("cible", donnees.cible);
    afficherLigne("erreur", donnees.erreur);
    afficherResultat(donnees.url_resultat);
  }

  /* Échec de la requête : plus aucune relance automatique, repli manuel. */
  function signalerEchec() {
    termine = true;
    requeteEnCours = false;
    if (minuterie !== null) {
      clearTimeout(minuterie);
      minuterie = null;
    }
    if (champEchec !== null) {
      champEchec.textContent = MESSAGE_ECHEC;
      champEchec.hidden = false;
    }
  }

  function armer() {
    if (termine || minuterie !== null) {
      return;
    }
    minuterie = setTimeout(function () {
      minuterie = null;
      interroger();
    }, DELAI_SUIVI_MS);
  }

  function interroger() {
    if (termine || requeteEnCours) {
      return;
    }
    /* Onglet masqué : aucune requête ; la reprise passe par visibilitychange. */
    if (document.hidden) {
      return;
    }
    requeteEnCours = true;
    fetch(CHEMIN_ETAT, {
      cache: "no-store",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    })
      .then(function (reponse) {
        if (!reponse.ok) {
          throw new Error("etat indisponible");
        }
        return reponse.json();
      })
      .then(function (donnees) {
        requeteEnCours = false;
        if (donnees === null || typeof donnees !== "object") {
          signalerEchec();
          return;
        }
        if (donnees.generation !== generationInitiale) {
          inactiverArret();
          signalerEchec();
          if (champEchec !== null) {
            champEchec.textContent = "Opération changée : utilisez Actualiser pour la suivre.";
          }
          return;
        }
        afficherEtat(donnees);
        if (donnees.actif === true) {
          armer();
        } else {
          termine = true;
          inactiverArret();
        }
      })
      .catch(function () {
        signalerEchec();
      });
  }

  document.addEventListener("visibilitychange", function () {
    if (!document.hidden && !termine && !requeteEnCours) {
      interroger();
    }
  });

  armer();
})();
