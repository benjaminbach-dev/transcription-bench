/*
 * Amélioration progressive de l'interface locale (design D6).
 *
 * Fichier unique servi par la route fixe /app.js, chargé avec `defer` par le
 * squelette commun : aucune dépendance, aucun CDN, aucune étape de compilation,
 * aucun code téléchargé à l'exécution et aucun code issu des modèles. Sans lui,
 * l'interface HTML reste complète : le lien Actualiser recharge la page et
 * toutes les actions restent des formulaires protégés.
 *
 * Seul comportement implémenté à ce stade : le suivi borné de l'opération
 * longue dans Exécutions (design D5). Il interroge `GET /executions/etat`
 * toutes les 3 s tant qu'une opération est active, une seule requête à la
 * fois, suspendu quand l'onglet est masqué et arrêté à l'état terminal. Il ne
 * remplace ni le formulaire ni les contrôles : seuls des textes et le lien de
 * résultat sont mis à jour, jamais du balisage, sans déplacer le focus.
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
