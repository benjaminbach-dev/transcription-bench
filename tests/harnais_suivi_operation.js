/*
 * Harnais local du suivi d'opération (tâche 3.3).
 *
 * Exécute réellement `app.js` dans un contexte `node:vm` muni d'un DOM factice
 * minimal, sans navigateur, sans dépendance et sans réseau : `fetch` est
 * remplacé, les minuteurs sont pilotés à la main et la visibilité de l'onglet
 * est simulée. Il imprime un rapport JSON que `tests/test_app_js_suivi.py`
 * vérifie ; aucune donnée réelle n'est lue ni écrite.
 */
"use strict";

const fs = require("node:fs");
const vm = require("node:vm");

const source = fs.readFileSync(process.argv[2], "utf8");
const ORIGINE = "http://127.0.0.1:8765";
const ADRESSE = ORIGINE + "/executions";

function creerElement(attributs) {
  const noeud = {
    attributs: Object.assign({}, attributs),
    textContent: "",
    innerHTML: "",
    hidden: false,
    parentNode: null,
    enfants: new Map(),
    auditeurs: new Map(),
    addEventListener(nom, auditeur) {
      this.auditeurs.set(nom, auditeur);
    },
    declencher(nom, evenement) {
      if (this.auditeurs.has(nom)) {
        this.auditeurs.get(nom)(evenement);
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
    },
    querySelector(selecteur) {
      const trouve = /^\[data-champ="([a-z-]+)"\]$/.exec(selecteur);
      if (trouve === null) {
        return null;
      }
      return this.enfants.get(trouve[1]) || null;
    }
  };
  return noeud;
}

function creerPage(options) {
  const racine = creerElement({
    "data-suivi-operation": "",
    "data-generation": "1",
    "data-etat-url":
      options.urlEtat === undefined ? "/executions/etat" : options.urlEtat,
    "data-actif": options.actif === false ? "non" : "oui"
  });
  const champs = {};
  for (const nom of [
    "etat",
    "type",
    "cible",
    "erreur",
    "echec",
    "resultat",
    "lien-resultat"
  ]) {
    const element = creerElement({ "data-champ": nom });
    element.parentNode = racine;
    champs[nom] = element;
    racine.enfants.set(nom, element);
  }
  const formulaireArret = creerElement({ "data-arret-operation": "" });
  const boutonArret = creerElement({ "data-champ": "bouton-arret" });
  formulaireArret.enfants.set("bouton-arret", boutonArret);
  const auditeurs = [];
  const documentFactice = {
    hidden: false,
    activeElement: { marque: "focus-initial" },
    querySelector(selecteur) {
      if (options.sansSuivi) {
        return null;
      }
      if (selecteur === "[data-arret-operation]") {
        return formulaireArret;
      }
      return selecteur === "[data-suivi-operation]" ? racine : null;
    },
    addEventListener(nom, auditeur) {
      auditeurs.push({ nom, auditeur });
    },
    declencher(nom) {
      for (const entree of auditeurs) {
        if (entree.nom === nom) {
          entree.auditeur();
        }
      }
    }
  };
  return {
    racine,
    champs,
    formulaireArret,
    boutonArret,
    document: documentFactice,
    focusInitial: documentFactice.activeElement
  };
}

function charger(options) {
  const page = creerPage(options);
  const appels = [];
  const minuteurs = [];
  const delais = [];
  let compteur = 0;
  const bac = {
    document: page.document,
    window: { location: { origin: ORIGINE, href: ADRESSE } },
    URL,
    setTimeout(fonction, delai) {
      compteur += 1;
      minuteurs.push({ identifiant: compteur, fonction, annule: false });
      delais.push(delai);
      return compteur;
    },
    clearTimeout(identifiant) {
      const trouve = minuteurs.find((entree) => entree.identifiant === identifiant);
      if (trouve !== undefined) {
        trouve.annule = true;
      }
    },
    fetch(adresse, init) {
      appels.push({ adresse, init });
      return options.repondre(appels.length);
    },
    console
  };
  vm.runInNewContext(source, bac, { filename: "app.js" });
  return {
    page,
    appels,
    delais,
    minuteursEnAttente() {
      return minuteurs.filter((entree) => !entree.annule).length;
    },
    async tourner() {
      const prochain = minuteurs.find((entree) => !entree.annule);
      if (prochain === undefined) {
        return false;
      }
      prochain.annule = true;
      prochain.fonction();
      await viderMicrotaches();
      return true;
    }
  };
}

async function viderMicrotaches() {
  for (let tour = 0; tour < 10; tour += 1) {
    await new Promise((resoudre) => setImmediate(resoudre));
  }
}

function reponseOk(donnees) {
  return Promise.resolve({
    ok: true,
    json() {
      return Promise.resolve(donnees);
    }
  });
}

function donneesEtat(surcharge) {
  return Object.assign(
    {
      generation: 1,
      etat: "en_cours",
      libelle_etat: "en cours",
      type: "execution",
      libelle_type: "exécution",
      cible: "modele.wav",
      erreur: null,
      actif: true,
      url_resultat: null
    },
    surcharge || {}
  );
}

const scenarios = {};

scenarios.actif_puis_second_tour = async function () {
  const essai = charger({ repondre: () => reponseOk(donneesEtat()) });
  const premier = await essai.tourner();
  const texteEtat = essai.page.champs.etat.textContent;
  const texteCible = essai.page.champs.cible.textContent;
  const second = await essai.tourner();
  return {
    premier,
    second,
    appels: essai.appels.length,
    delais: essai.delais,
    texteEtat,
    texteCible,
    cibleVisible: essai.page.champs.cible.hidden === false,
    adresseDemandee: essai.appels[0].adresse
  };
};

scenarios.terminal = async function () {
  const essai = charger({
    repondre: () =>
      reponseOk(donneesEtat({ etat: "terminee", libelle_etat: "terminée", actif: false }))
  });
  await essai.tourner();
  const appelsApres = essai.appels.length;
  const minuteursApres = essai.minuteursEnAttente();
  essai.page.document.declencher("visibilitychange");
  await viderMicrotaches();
  return {
    appelsApres,
    minuteursApres,
    appelsFinal: essai.appels.length,
    texteEtat: essai.page.champs.etat.textContent
  };
};

scenarios.une_requete_a_la_fois = async function () {
  let liberer;
  const attente = new Promise((resoudre) => {
    liberer = resoudre;
  });
  const essai = charger({ repondre: () => attente });
  await essai.tourner();
  // Requête encore en vol : un nouvel événement ne doit pas en lancer une autre.
  essai.page.document.declencher("visibilitychange");
  await viderMicrotaches();
  const pendant = essai.appels.length;
  liberer({
    ok: true,
    json() {
      return Promise.resolve(donneesEtat({ actif: false }));
    }
  });
  await viderMicrotaches();
  return {
    pendant,
    apres: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.onglet_masque = async function () {
  const essai = charger({ repondre: () => reponseOk(donneesEtat()) });
  essai.page.document.hidden = true;
  await essai.tourner();
  const masque = essai.appels.length;
  essai.page.document.declencher("visibilitychange");
  await viderMicrotaches();
  const masqueApres = essai.appels.length;
  essai.page.document.hidden = false;
  essai.page.document.declencher("visibilitychange");
  await viderMicrotaches();
  return {
    masque,
    masqueApres,
    visible: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.echec_requete = async function () {
  const essai = charger({
    repondre: () => Promise.reject(new Error("réseau local indisponible"))
  });
  await essai.tourner();
  return {
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente(),
    message: essai.page.champs.echec.textContent,
    echecVisible: essai.page.champs.echec.hidden === false
  };
};

scenarios.reponse_non_ok = async function () {
  const essai = charger({
    repondre: () => Promise.resolve({ ok: false, json: () => Promise.resolve(null) })
  });
  await essai.tourner();
  return {
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente(),
    message: essai.page.champs.echec.textContent
  };
};

scenarios.arret_terminal = async function () {
  const essai = charger({ repondre: () => reponseOk(donneesEtat({ actif: false })) });
  essai.page.document.activeElement = essai.page.boutonArret;
  let empeche = false;
  essai.page.formulaireArret.declencher("submit", {
    preventDefault() { throw new Error("arrêt actif empêché"); }
  });
  await essai.tourner();
  essai.page.formulaireArret.declencher("submit", {
    preventDefault() { empeche = true; }
  });
  return {
    desactive: essai.page.boutonArret.getAttribute("aria-disabled"),
    libelle: essai.page.boutonArret.textContent,
    classe: essai.page.boutonArret.getAttribute("class"),
    focusInchange: essai.page.document.activeElement === essai.page.boutonArret,
    submitEmpeche: empeche,
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.operation_changee = async function () {
  const essai = charger({ repondre: () => reponseOk(donneesEtat({ generation: 2 })) });
  essai.page.document.activeElement = essai.page.boutonArret;
  await essai.tourner();
  return {
    etat: essai.page.champs.etat.textContent,
    message: essai.page.champs.echec.textContent,
    desactive: essai.page.boutonArret.getAttribute("aria-disabled"),
    focusInchange: essai.page.document.activeElement === essai.page.boutonArret,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.urls = async function () {
  const candidates = [
    "/resultats/20240103-000000-0000dead",
    "/resultats/../../evil",
    "//evil.example/resultats/x",
    "https://evil.example/resultats/x",
    "http://127.0.0.1:8765/resultats/20240103-000000-0000dead",
    "//127.0.0.1:8765/resultats/20240103-000000-0000dead",
    "/resultats/x",
    "/resultats/20240103-000000-0000dead%2f..",
    "/resultats/20240103-000000-0000dead%5c..",
    "/resultats/",
    "/resultats/a/b",
    "/resultats/x?suite=1",
    "/resultats/x#ancre",
    "/modeles",
    "",
    null
  ];
  const resultats = [];
  for (const candidate of candidates) {
    const essai = charger({
      repondre: () =>
        reponseOk(
          donneesEtat({ actif: false, url_resultat: candidate })
        )
    });
    await essai.tourner();
    resultats.push({
      candidate,
      href: essai.page.champs["lien-resultat"].getAttribute("href"),
      ligneMasquee: essai.page.champs.resultat.hidden
    });
  }
  return resultats;
};

scenarios.texte_et_focus = async function () {
  const hostile = "<img src=x onerror=alert(1)>";
  const essai = charger({
    repondre: () =>
      reponseOk(
        donneesEtat({
          actif: false,
          cible: hostile,
          erreur: "ligne <script>alert(2)</script>"
        })
      )
  });
  await essai.tourner();
  return {
    cible: essai.page.champs.cible.textContent,
    erreur: essai.page.champs.erreur.textContent,
    innerHTML: essai.page.champs.cible.innerHTML,
    focusInitial: essai.page.focusInitial,
    focusCourant: essai.page.document.activeElement,
    focusInchange:
      essai.page.focusInitial === essai.page.document.activeElement,
    ligneCibleVisible: essai.page.champs.cible.hidden === false,
    ligneErreurVisible: essai.page.champs.erreur.hidden === false
  };
};

scenarios.inactif_au_chargement = async function () {
  const essai = charger({ actif: false, repondre: () => reponseOk(donneesEtat()) });
  await essai.tourner();
  return {
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.adresse_inattendue = async function () {
  const essai = charger({
    urlEtat: "//evil.example/executions/etat",
    repondre: () => reponseOk(donneesEtat())
  });
  await essai.tourner();
  return {
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
  };
};

scenarios.sans_conteneur = async function () {
  const essai = charger({ sansSuivi: true, repondre: () => reponseOk(donneesEtat()) });
  await essai.tourner();
  return {
    appels: essai.appels.length,
    minuteurs: essai.minuteursEnAttente()
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
