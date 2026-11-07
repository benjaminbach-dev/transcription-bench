/*
 * Harnais local de la préparation unique (tâche 4.2, design D4/D6).
 *
 * Exécute réellement `app.js` dans un contexte `node:vm` muni d'un DOM factice
 * minimal, sans navigateur, sans dépendance installée et sans réseau : la
 * soumission du formulaire GET et les minuteurs du suivi sont interceptés à la
 * main. Il imprime un rapport JSON que `tests/test_app_js_preparation.py`
 * vérifie ; aucune donnée réelle n'est lue ni écrite. Les valeurs (références,
 * noms d'audios, moteurs) sont entièrement fabriquées.
 */
"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(process.argv[2], "utf8");
const ORIGINE = "http://127.0.0.1:8765";
const ADRESSE = ORIGINE + "/executions";

function creerElement(attributs) {
  return {
    attributs: Object.assign({}, attributs),
    hidden: false,
    textContent: "",
    value: "",
    checked: false,
    auditeurs: new Map(),
    addEventListener(nom, auditeur) {
      this.auditeurs.set(nom, auditeur);
    },
    declencher(nom) {
      if (this.auditeurs.has(nom)) {
        this.auditeurs.get(nom)({ type: nom });
      }
    },
    getAttribute(nom) {
      return Object.prototype.hasOwnProperty.call(this.attributs, nom)
        ? this.attributs[nom]
        : null;
    },
    setAttribute(nom, valeur) {
      this.attributs[nom] = String(valeur);
    },
    removeAttribute(nom) {
      delete this.attributs[nom];
    },
    hasAttribute(nom) {
      return Object.prototype.hasOwnProperty.call(this.attributs, nom);
    }
  };
}

/* Option d'un sélecteur : valeur soumise et attributs de contrat éventuels. */
function creerOption(valeur, attributs) {
  const option = creerElement(attributs || {});
  option.value = valeur;
  return option;
}

function creerSelecteur(valeur, options) {
  const selecteur = creerElement({});
  selecteur.value = valeur;
  selecteur.options = options;
  return selecteur;
}

function creerCaseAudio(valeur, coche) {
  const element = creerElement({ "data-choix-audio": "" });
  element.value = valeur;
  element.checked = coche === true;
  return element;
}

/* Audio unitaire : contrôle simple (select) portant le même marqueur que les
 * cases du lot. Le script le traite comme les autres choix d'audio. */
function creerSelectAudio(valeur, valeurs) {
  return creerSelecteur(
    valeur,
    valeurs.map((nom) => creerOption(nom))
  );
}

/* Copie cachée d'un réglage dans le formulaire GET, désactivée sans script. */
function creerCopie(nom, valeur) {
  const element = creerElement({ "data-copie-reglage": "", disabled: "" });
  element.name = nom;
  element.value = valeur;
  element.disabled = true;
  return element;
}

/*
 * Préparation appliquée factice : contrôles des réglages avancés portant
 * `data-valeur-reglage` et jeton anti-CSRF sans ce marqueur, comme dans le
 * gabarit rendu. Seuls les contrôles marqués doivent être recopiés.
 */
function creerLancement(controles) {
  const formulaire = creerElement({ "data-preparation-lancement": "" });
  formulaire.controles = controles;
  formulaire.jeton = Object.assign(creerElement({}), { name: "jeton_csrf", value: "jeton-de-test" });
  formulaire.querySelectorAll = function (selecteur) {
    return selecteur === "[data-valeur-reglage]" ? this.controles.slice() : [];
  };
  return formulaire;
}

function controleReglage(nom, valeur, type, coche) {
  return { name: nom, value: valeur, type: type, checked: coche === true };
}

/*
 * Formulaire GET factice : mêmes contrôles que le gabarit rendu (modèle, cases
 * d'audios, moteur), sans aucun champ de jeton. `submit()` enregistre l'état
 * exact des contrôles au moment de la soumission, comme le navigateur le
 * ferait pour une requête GET.
 */
function creerFormulaire(configuration) {
  const options = configuration || {};
  const formulaire = creerElement({
    method: "get",
    action: options.action === undefined ? "/executions" : options.action,
    "data-preparation-choix": ""
  });
  formulaire.modele = options.modele === undefined ? null : options.modele;
  formulaire.moteur = options.moteur === undefined ? null : options.moteur;
  formulaire.cases = options.cases === undefined ? [] : options.cases;
  formulaire.unitaire =
    options.unitaire === undefined ? null : options.unitaire;
  formulaire.copies = options.copies === undefined ? [] : options.copies;
  formulaire.soumissions = [];
  formulaire.querySelector = function (selecteur) {
    if (selecteur === "[data-choix-modele]") {
      return this.modele;
    }
    if (selecteur === "[data-choix-moteur]") {
      return this.moteur;
    }
    return null;
  };
  formulaire.querySelectorAll = function (selecteur) {
    if (selecteur === "[data-choix-audio]") {
      const controles = this.cases.slice();
      if (this.unitaire !== null) {
        controles.push(this.unitaire);
      }
      return controles;
    }
    if (selecteur === "[data-copie-reglage]") {
      return this.copies.slice();
    }
    return [];
  };
  formulaire.submit = function () {
    const reglages = {};
    const noms = [];
    for (const copie of this.copies) {
      if (copie.disabled) {
        continue;
      }
      reglages[copie.name] = copie.value;
      noms.push(copie.name);
    }
    this.soumissions.push({
      method: this.getAttribute("method"),
      action: this.getAttribute("action"),
      modele: this.modele === null ? null : this.modele.value,
      moteur: this.moteur === null ? null : this.moteur.value,
      audios: this.cases
        .filter((element) => element.checked)
        .map((element) => element.value),
      audioUnique: this.unitaire === null ? null : this.unitaire.value,
      reglages: reglages,
      noms: noms,
      jeton: noms.indexOf("jeton_csrf") !== -1
    });
  };
  return formulaire;
}

/* Résumé de suivi factice, pour vérifier que le polling de 3.3 survit. */
function creerSuivi() {
  const racine = creerElement({
    "data-suivi-operation": "",
    "data-generation": "1",
    "data-etat-url": "/executions/etat",
    "data-actif": "oui"
  });
  const champs = new Map();
  for (const nom of ["etat", "type", "cible", "erreur", "echec", "resultat", "lien-resultat"]) {
    champs.set(nom, creerElement({ "data-champ": nom }));
  }
  racine.querySelector = function (selecteur) {
    const trouve = /^\[data-champ="([a-z-]+)"\]$/.exec(selecteur);
    return trouve === null ? null : champs.get(trouve[1]) || null;
  };
  racine.champs = champs;
  return racine;
}

function creerPage(configuration) {
  const options = configuration || {};
  const formulaire =
    options.formulaire === undefined ? creerFormulaire(options) : options.formulaire;
  const lancement =
    options.lancement === undefined ? null : options.lancement;
  const bouton = creerElement({ "data-action-appliquer": "" });
  const suivi = options.suivi === true ? creerSuivi() : null;
  const documentFactice = {
    hidden: false,
    querySelector(selecteur) {
      if (selecteur === "[data-preparation-choix]") {
        return options.sansFormulaire === true ? null : formulaire;
      }
      if (selecteur === "[data-preparation-lancement]") {
        return lancement;
      }
      if (selecteur === "[data-action-appliquer]") {
        return options.sansBouton === true ? null : bouton;
      }
      if (selecteur === "[data-suivi-operation]") {
        return suivi;
      }
      return null;
    },
    addEventListener() {},
    declencher() {}
  };
  return { formulaire, lancement, bouton, suivi, document: documentFactice };
}

function charger(configuration) {
  const page = creerPage(configuration);
  const appels = [];
  const minuteurs = [];
  const bac = {
    document: page.document,
    window: { location: { origin: ORIGINE, href: ADRESSE } },
    URL,
    setTimeout(fonction) {
      minuteurs.push(fonction);
      return minuteurs.length;
    },
    clearTimeout() {},
    fetch(adresse) {
      appels.push(adresse);
      return Promise.resolve({
        ok: true,
        json() {
          return Promise.resolve({ generation: 1, etat: "terminee", actif: false });
        }
      });
    },
    console
  };
  vm.runInNewContext(source, bac, { filename: "app.js" });
  return { page, appels, minuteurs };
}

/* Modèles et moteurs de test : chaque option porte son contrat, sans réseau. */
function selecteurModele(courant, entrees) {
  return creerSelecteur(
    courant,
    entrees.map((entree) => creerOption(entree.reference, { "data-moteur": entree.moteur }))
  );
}

function selecteurMoteur(courant, entrees) {
  return creerSelecteur(
    courant,
    entrees.map((entree) => creerOption(entree.moteur, { "data-reference": entree.reference }))
  );
}

const ENTREES = [
  { reference: "moteur-a/" + "a".repeat(64), moteur: "moteur-a" },
  { reference: "moteur-b/" + "b".repeat(64), moteur: "moteur-b" }
];

const scenarios = {};

scenarios.changement_modele = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true), creerCaseAudio("b.wav", false)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.modele.value = ENTREES[1].reference;
  essai.page.formulaire.modele.declencher("change");
  return {
    soumissions: essai.page.formulaire.soumissions,
    boutonMasque: essai.page.bouton.hidden,
    appelsReseau: essai.appels.length,
    minuteurs: essai.minuteurs.length
  };
};

scenarios.changement_audio_unitaire = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    unitaire: creerSelectAudio("a.wav", ["a.wav", "b.wav"])
  });
  const essai = charger({ formulaire });
  const page = essai.page.formulaire;
  page.unitaire.value = "b.wav";
  page.unitaire.declencher("change");
  return {
    soumissions: page.soumissions,
    boutonMasque: essai.page.bouton.hidden,
    appelsReseau: essai.appels.length,
    minuteurs: essai.minuteurs.length
  };
};

scenarios.changement_audio = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true), creerCaseAudio("b.wav", false)]
  });
  const essai = charger({ formulaire });
  const page = essai.page.formulaire;
  page.cases[1].checked = true;
  page.cases[1].declencher("change");
  // Un second événement sur la même case ne doit pas dupliquer l'audio.
  page.cases[1].declencher("change");
  return {
    soumissions: page.soumissions,
    boutonMasque: essai.page.bouton.hidden,
    appelsReseau: essai.appels.length
  };
};

scenarios.changement_moteur = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  const page = essai.page.formulaire;
  page.moteur.value = ENTREES[1].moteur;
  page.moteur.declencher("change");
  return { soumissions: page.soumissions, appelsReseau: essai.appels.length };
};

scenarios.moteur_deja_coherent = function () {
  const memeMoteur = [
    { reference: "moteur-a/" + "a".repeat(64), moteur: "moteur-a" },
    { reference: "moteur-a/" + "d".repeat(64), moteur: "moteur-a" }
  ];
  const formulaire = creerFormulaire({
    modele: selecteurModele(memeMoteur[1].reference, memeMoteur),
    moteur: selecteurMoteur("moteur-a", memeMoteur),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.moteur.declencher("change");
  return {
    soumissions: essai.page.formulaire.soumissions,
    modele: essai.page.formulaire.modele.value
  };
};

scenarios.contrat_absent_modele = function () {
  const sansContrat = ENTREES.map((entree) => creerOption(entree.reference));
  const formulaire = creerFormulaire({
    modele: creerSelecteur(ENTREES[0].reference, sansContrat),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.modele.value = ENTREES[1].reference;
  essai.page.formulaire.modele.declencher("change");
  return {
    soumissions: essai.page.formulaire.soumissions,
    boutonMasque: essai.page.bouton.hidden
  };
};

scenarios.contrat_absent_moteur = function () {
  const sansContrat = ENTREES.map((entree) => creerOption(entree.moteur));
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: creerSelecteur("moteur-a", sansContrat),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.moteur.value = ENTREES[1].moteur;
  essai.page.formulaire.moteur.declencher("change");
  return { soumissions: essai.page.formulaire.soumissions };
};

scenarios.reference_hors_liste = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  const page = essai.page.formulaire;
  page.modele.value = "moteur-z/" + "z".repeat(64);
  page.modele.declencher("change");
  page.moteur.value = "moteur-z";
  page.moteur.declencher("change");
  return { soumissions: page.soumissions, moteur: page.moteur.value };
};

scenarios.sans_formulaire = function () {
  const essai = charger({ sansFormulaire: true });
  return {
    soumissions: essai.page.formulaire.soumissions,
    boutonMasque: essai.page.bouton.hidden,
    appelsReseau: essai.appels.length
  };
};

scenarios.sans_hook_de_bouton = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire, sansBouton: true });
  essai.page.formulaire.cases[0].checked = false;
  essai.page.formulaire.cases[0].declencher("change");
  return { soumissions: formulaire.soumissions, appelsReseau: essai.appels.length };
};

scenarios.noms_d_audios_speciaux = function () {
  const formulas = ["séance #2 & fin.wav", "a+b=c.wav"];
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: formulas.map((nom) => creerCaseAudio(nom, true))
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.cases[0].declencher("change");
  return { soumissions: formulaire.soumissions };
};

scenarios.ancre_non_dupliquee = function () {
  const formulaire = creerFormulaire({
    action: "/executions#preparation",
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.cases[0].declencher("change");
  essai.page.formulaire.cases[0].declencher("change");
  return { soumissions: formulaire.soumissions };
};

scenarios.audio_seul_conserve_reglages = function () {
  const copies = [
    creerCopie("threads", "4"),
    creerCopie("reglage_compute_type", "float32"),
    creerCopie("reglage_beam_size", "5"),
    creerCopie("reglage_vad_filter", "non")
  ];
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true), creerCaseAudio("b.wav", false)],
    copies: copies
  });
  const lancement = creerLancement([
    controleReglage("threads", "6", "number"),
    controleReglage("reglage_compute_type", "int8", "select-one"),
    controleReglage("reglage_beam_size", "8", "number"),
    controleReglage("reglage_vad_filter", "oui", "radio", false),
    controleReglage("reglage_vad_filter", "non", "radio", true),
    controleReglage("reglage_prompt", "amorce locale", "text")
  ]);
  const essai = charger({ formulaire, lancement });
  essai.page.formulaire.cases[1].checked = true;
  essai.page.formulaire.cases[1].declencher("change");
  return {
    soumissions: formulaire.soumissions,
    copiesActives: formulaire.copies.filter((copie) => !copie.disabled).length,
    appelsReseau: essai.appels.length
  };
};

scenarios.variante_conserve_reglages = function () {
  const copies = [
    creerCopie("threads", "4"),
    creerCopie("reglage_compute_type", "float32")
  ];
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)],
    copies: copies
  });
  const lancement = creerLancement([
    controleReglage("threads", "2", "number"),
    controleReglage("reglage_compute_type", "int8", "select-one")
  ]);
  const essai = charger({ formulaire, lancement });
  essai.page.formulaire.modele.value = ENTREES[1].reference;
  essai.page.formulaire.modele.declencher("change");
  return { soumissions: formulaire.soumissions };
};

scenarios.radio_sans_selection = function () {
  const copies = [
    creerCopie("threads", "4"),
    creerCopie("reglage_vad_filter", "non")
  ];
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)],
    copies: copies
  });
  const lancement = creerLancement([
    controleReglage("threads", "3", "number"),
    controleReglage("reglage_vad_filter", "oui", "radio", false),
    controleReglage("reglage_vad_filter", "non", "radio", false)
  ]);
  const essai = charger({ formulaire, lancement });
  essai.page.formulaire.cases[0].declencher("change");
  return {
    soumissions: formulaire.soumissions,
    copieDesactivee: formulaire.copies[1].disabled
  };
};

scenarios.jeton_jamais_transmis = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)],
    copies: [creerCopie("threads", "4"), creerCopie("reglage_beam_size", "5")]
  });
  const lancement = creerLancement([
    controleReglage("threads", "7", "number"),
    controleReglage("reglage_beam_size", "9", "number")
  ]);
  const essai = charger({ formulaire, lancement });
  essai.page.formulaire.cases[0].checked = false;
  essai.page.formulaire.cases[0].declencher("change");
  return {
    soumissions: formulaire.soumissions,
    jetonDansLeFormulaireLancement: lancement.jeton.value
  };
};

scenarios.sans_preparation_appliquee = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire });
  essai.page.formulaire.cases[0].declencher("change");
  return { soumissions: formulaire.soumissions };
};

scenarios.avec_suivi = function () {
  const formulaire = creerFormulaire({
    modele: selecteurModele(ENTREES[0].reference, ENTREES),
    moteur: selecteurMoteur("moteur-a", ENTREES),
    cases: [creerCaseAudio("a.wav", true)]
  });
  const essai = charger({ formulaire, suivi: true });
  const minuteursAvant = essai.minuteurs.length;
  essai.page.formulaire.modele.value = ENTREES[1].reference;
  essai.page.formulaire.modele.declencher("change");
  return {
    minuteursAvant,
    soumissions: formulaire.soumissions,
    appelsAvant: essai.appels.length,
    suiviPresent: essai.page.suivi !== null
  };
};

(async function principal() {
  const rapport = {};
  for (const [nom, scenario] of Object.entries(scenarios)) {
    rapport[nom] = await scenario();
  }
  process.stdout.write(JSON.stringify({ scenarios: rapport }));
})().catch((erreur) => {
  process.stderr.write(String(erreur && erreur.stack ? erreur.stack : erreur));
  process.exitCode = 1;
});
