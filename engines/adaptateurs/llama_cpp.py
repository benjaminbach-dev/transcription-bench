"""Adaptateur d'exécution llama.cpp (GGUF), CPU uniquement — API de bas niveau.

Cet adaptateur est le seul code qui importe `llama_cpp`, et il le fait **à
l'intérieur** de `charger` : importer ce module ne charge aucun paquet moteur
(design D4). Il n'utilise que les liaisons C du paquet (`llama_cpp.llama_cpp`),
jamais la classe `Llama` — dont le constructeur 0.3.36 compile en Jinja2 les
gabarits embarqués — ni `response_format`, qui retombe silencieusement sur une
grammaire JSON générique. Le paquet importe lui-même jinja2 au niveau module
(fait mesuré à l'essai minimal du 2026-11-20) : seule la **compilation** de
gabarits est évitée, aucun gabarit n'est jamais exécuté.

Décisions appliquées, issues de l'essai minimal 0.1 (`data/feasibility/
llama-cpp/`, PC de test Linux, 2026-11-20) et du design D4 :

- chargement : `llama_model_load_from_file` avec `n_gpu_layers=0`, projection
  mémoire (`mmap`) laissée par défaut, threads de lecture et de génération
  posés sur `threads_demandes` (aucune lecture native du nombre appliqué
  n'existe dans la 0.3.36 : la valeur posée est consignée), contexte =
  réglage `contexte` puis relu par `llama_n_ctx` (valeur réelle utilisée par
  le refus de contexte insuffisant) ;
- journaux natifs **neutralisés** : le rappel installé par `llama_log_set`
  n'écrit plus rien (le journal `run.log` ne reçoit jamais de contenu natif,
  design D7 ; seuls les diagnostics du programme y entrent : messages d'échec
  de l'adaptateur, motifs du runner). Le rappel reste conservé au niveau
  module : la bibliothèque C peut l'appeler bien après le retour de `charger`,
  et ctypes ne maintient pas sa durée de vie ;
- grammaire : schéma → GBNF (`llama_cpp.llama_grammar.json_schema_to_gbnf`,
  une exception de conversion échoue le chargement) → `llama_sampler_init_grammar`
  → **sonde de contrainte obligatoire** : l'échantillonneur fraîchement créé
  est appliqué à tout le vocabulaire ; la liaison 0.3.36 **ne renvoie pas
  d'échantillonneur nul** sur grammaire mal formée (repli silencieux natif
  documenté), le refus est donc assuré par la sonde : aucun token masqué
  (repli silencieux) ou vocabulaire entièrement masqué mettent `charger` en
  échec, sans qu'aucune génération soit possible ;
- chaîne d'échantillonnage : grammaire puis glouton (`llama_sampler_init_
  greedy`, température nulle, déterministe : `graine` vaut `None` par
  convention « aucune : échantillonnage glouton déterministe ») ;
- `reinitialiser` vide la mémoire KV (`llama_memory_clear(mem, True)`) et
  réinitialise la chaîne (`llama_sampler_reset`) : sans cela, le préfixe
  commun des consignes serait réutilisé (relecture intégrale prouvée à
  l'essai par deux sources au préfixe identique) ;
- génération token par token (`llama_batch_init`/`llama_decode` par morceaux
  de 512 tokens, `llama_sampler_sample`), arrêt sur tout token de fin reconnu
  par `llama_vocab_is_eog` (exclu du compte) ou à `sortie_max` (`fin` =
  `"limite"`) ;
- compteurs natifs : les **comptes** de tokens sont lisibles en cumul mais ne
  s'engagent qu'à l'accès aux sorties d'un décodage (lecture différée mesurée
  à l'essai) ; `extraire` relève donc une différence entre deux lectures
  prises après échantillonnage, cohérente à ±1 token près (repli différé du
  dernier décodage). Les **temps natifs** sont restés à 0.0 dans la roue
  essayée : aucun temps natif n'est rendu, toutes les durées viennent du
  chronomètre du programme.

`charger` rend un dict opaque portant en plus la clé `meta_chargement`
(transportée par le runner dans l'événement `chargement`) :
`threads_appliques` (valeur posée, voir ci-dessus), `mode_chargement_poids`
(`"mmap"`), `architecture` (lue dans `general.architecture`), 
`sha256_gabarit_embarque` (SHA-256 du gabarit `tokenizer.chat_template` lu
**comme texte** par `llama_model_meta_val_str`, jamais compilé ; `None` si
absent), `version_format` (constante du module), `decodage` (`"glouton"`) et
`graine` (`None`, convention ci-dessus).

Formats de conversation locaux (design D3) : le gabarit Jinja embarqué n'est
jamais exécuté ; chaque architecture admise a un format local, assemblage de
chaînes et de tokens spéciaux, versionné par `VERSION_FORMAT`.

- `mistral3` : **vérifié** à l'essai minimal (gabarit embarqué du
  Ministral-3-3B-Instruct-2512 lu comme texte, SHA-256
  d28d7df94f0fd7e8d0075a22c473333d6e7dd2bc4c36c83e8b975300a0fb94bc ;
  comparaison structurelle 5/5) :
  `<s>[SYSTEM_PROMPT]{système}[/SYSTEM_PROMPT][INST]{utilisateur}[/INST]`,
  sans espacement ajouté ;
- `qwen35` : ChatML des `chat_template.jinja` publics de Qwen/Qwen3.5-4B
  et Qwen/Qwen3.5-9B, lus comme texte (2026-11-20, sans poids) ;
  contenu trimé par le gabarit, aucun BOS émis, préfixe de génération
  `<|im_start|>assistant\\n<think>\\n\\n</think>\\n\\n` sans raisonnement —
  **à vérifier à la qualification 6.3** ;
- `granite` : `chat_template.jinja` public de ibm-granite/granite-4.2-8b
  lu comme texte (2026-11-20, sans poids) ; contenu du message
  utilisateur non trimé par ce gabarit, aucun BOS émis, préfixe de génération
  `<|im_start|>assistant\\n<think></think>` sans raisonnement — **à vérifier à
  la qualification 6.3** ;
- `gemma4` : gabarit canonique « Google Gemma 4 Canonical Chat Template »
  (publication du 2026-07-09) lu comme texte dans les métadonnées du dépôt
  ggml-org/gemma-4-E4B-it-GGUF (API Hugging Face, consultation publique du
  2026-11-20, sans poids) : BOS émis, tours `<|turn>{rôle}\\n…<turn|>\\n`,
  contenu trimé, mode raisonnement désactivé par défaut dans ce gabarit et
  jamais activé ici — **à vérifier à la qualification 6.3**.

Une architecture sans format local est refusée au chargement. Le chargement
est local uniquement (`local_files_only=True` forcé par le runner) : aucun
téléchargement n'a lieu ici.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from engines.declarations import DEFAUT_CONTEXTE_LLAMA, DEFAUT_SORTIE_MAX_LLAMA
from engines.protocole import ErreurContexteInsuffisant

#: Référence FORTE au rappel de journal natif installé par `charger` : ctypes ne
#: garde pas lui-même les rappels vivants, et la bibliothèque C peut appeler le
#: pointeur bien après le retour de `charger` (pendant toute la vie du moteur).
#: Sans cette référence de niveau module, le pointeur serait libéré et le
#: processus tomberait. La liste ne garde que le rappel actif : chaque
#: `charger` remplace le précédent, comme `llama_log_set` lui-même.
_RAPPEL_JOURNAL_ACTIF: list[Any] = []

#: Version des formats de conversation locaux (design D3) : incrémentée à
#: toute modification d'un format.
VERSION_FORMAT = 2

#: Clé de métadonnée GGUF portant l'architecture.
CLE_ARCHITECTURE = "general.architecture"
#: Clé de métadonnée GGUF portant le gabarit de conversation embarqué.
CLE_GABARIT = "tokenizer.chat_template"
#: Racine des grammaires produites par le convertisseur du paquet.
RACINE_GRAMMAIRE = "root"
#: Morceaux de décodage du prompt (valeur validée à l'essai minimal).
N_BATCH = 512
#: Taille du tampon d'une pièce de token (valeur du paquet).
TAILLE_PIECE = 32


def _format_mistral3(systeme: str, utilisateur: str) -> str:
    """Rendu local mistral3, vérifié à l'essai (docstring du module)."""
    return (
        f"<s>[SYSTEM_PROMPT]{systeme}[/SYSTEM_PROMPT]"
        f"[INST]{utilisateur}[/INST]"
    )


def _format_qwen35(systeme: str, utilisateur: str) -> str:
    """Rendu local qwen35 (ChatML, contenu trimé, sans BOS ; qualification 6.3)."""
    return (
        f"<|im_start|>system\n{systeme.strip()}<|im_end|>\n"
        f"<|im_start|>user\n{utilisateur.strip()}<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )


def _format_granite(systeme: str, utilisateur: str) -> str:
    """Rendu local granite (ChatML, sans BOS, contenu non trimé ; qualification 6.3)."""
    return (
        f"<|im_start|>system\n{systeme}<|im_end|>\n"
        f"<|im_start|>user\n{utilisateur}<|im_end|>\n"
        "<|im_start|>assistant\n<think></think>"
    )


def _format_gemma4(systeme: str, utilisateur: str) -> str:
    """Rendu local gemma4 (BOS, tours <|turn>, contenu trimé ; qualification 6.3)."""
    return (
        f"<bos><|turn>system\n{systeme.strip()}<turn|>\n"
        f"<|turn>user\n{utilisateur.strip()}<turn|>\n"
        "<|turn>model\n"
    )


#: Formats de conversation locaux par architecture admise (design D3) : une
#: architecture absente de cette table est refusée au chargement.
FORMATS_CONVERSATION: dict[str, Any] = {
    "mistral3": _format_mistral3,
    "qwen35": _format_qwen35,
    "granite": _format_granite,
    "gemma4": _format_gemma4,
}


def charger(
    modele: dict[str, Any],
    threads_demandes: int,
    reglages: Mapping[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Charge le modèle GGUF et la grammaire du schéma, en API bas niveau.

    Une exception (fichier absent, architecture sans format local, schéma non
    convertible, échantillonneur nul, sonde de contrainte refusée) met le
    chargement en échec avec un motif ; les ressources déjà posées sont
    libérées et aucune génération n'est possible.
    """
    chemin = _chemin_modele(modele)
    contexte_demande = _entier_positif_reglage(
        reglages, "contexte", DEFAUT_CONTEXTE_LLAMA
    )

    import llama_cpp  # import différé : paquet moteur

    # Journal natif neutralisé (design D7, `run.log` sans texte) : le rappel
    # ne recopie RIEN, ni sur stderr ni ailleurs — un fragment de texte source
    # recopié par le moteur ne doit jamais atteindre le journal. Il est gardé
    # vivant par `_RAPPEL_JOURNAL_ACTIF` : le C l'appelle pendant toute la vie
    # du moteur, bien après le retour de `charger`.
    def _journal_natif(level, message, user_data):
        return None

    rappel = llama_cpp.llama_log_callback(_journal_natif)
    _RAPPEL_JOURNAL_ACTIF.clear()
    _RAPPEL_JOURNAL_ACTIF.append(rappel)
    llama_cpp.llama_log_set(rappel, None)
    llama_cpp.llama_backend_init()

    parametres_modele = llama_cpp.llama_model_default_params()
    parametres_modele.n_gpu_layers = 0
    handle = llama_cpp.llama_model_load_from_file(
        str(chemin).encode("utf-8"), parametres_modele
    )
    if handle is None:
        raise RuntimeError(f"llama_model_load_from_file a échoué : {chemin}")
    try:
        return _charger_contexte(
            llama_cpp,
            handle,
            chemin,
            threads_demandes,
            contexte_demande,
            schema,
        )
    except Exception:
        llama_cpp.llama_model_free(handle)
        raise


def _charger_contexte(
    liaisons: Any,
    handle: Any,
    chemin: Path,
    threads_demandes: int,
    contexte_demande: int,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Contexte, grammaire sondée et dict moteur, une fois le modèle chargé."""
    architecture = _lire_meta(liaisons, handle, CLE_ARCHITECTURE)
    format_local = FORMATS_CONVERSATION.get(architecture or "")
    if format_local is None:
        admises = ", ".join(sorted(FORMATS_CONVERSATION))
        raise RuntimeError(
            f"architecture {architecture!r} lue dans {chemin.name} sans format "
            f"local de conversation (admises : {admises})"
        )
    gabarit = _lire_meta(liaisons, handle, CLE_GABARIT)
    sha_gabarit = (
        hashlib.sha256(gabarit.encode("utf-8")).hexdigest() if gabarit else None
    )
    vocabulaire = liaisons.llama_model_get_vocab(handle)

    parametres = liaisons.llama_context_default_params()
    parametres.n_ctx = contexte_demande
    parametres.n_threads = threads_demandes
    parametres.n_threads_batch = threads_demandes
    contexte = liaisons.llama_init_from_model(handle, parametres)
    if contexte is None:
        raise RuntimeError("llama_init_from_model a renvoyé NULL")
    try:
        contexte_reel = int(liaisons.llama_n_ctx(contexte))
        memoire = liaisons.llama_get_memory(contexte)
        if memoire is None:
            raise RuntimeError("llama_get_memory a renvoyé NULL")
        chaine, gbnf = _charger_grammaire(liaisons, vocabulaire, schema)
    except Exception:
        liaisons.llama_free(contexte)
        raise

    return {
        "liaisons": liaisons,
        "model": handle,
        "ctx": contexte,
        "vocab": vocabulaire,
        "mem": memoire,
        "chaine": chaine,
        "format": format_local,
        "contexte": contexte_reel,
        "n_batch": N_BATCH,
        "gbnf_octets": len(gbnf),
        "meta_chargement": {
            "threads_appliques": threads_demandes,
            "mode_chargement_poids": "mmap",
            "architecture": architecture,
            "sha256_gabarit_embarque": sha_gabarit,
            "version_format": VERSION_FORMAT,
            "decodage": "glouton",
            "graine": None,
        },
    }


def _charger_grammaire(
    liaisons: Any, vocabulaire: Any, schema: dict[str, Any]
) -> tuple[Any, str]:
    """Convertit le schéma en GBNF, charge l'échantillonneur et le sonde.

    Rend la chaîne d'échantillonnage (grammaire puis glouton). La sonde
    applique l'échantillonneur fraîchement créé à tout le vocabulaire : la
    liaison 0.3.36 accepte une grammaire mal formée sans renvoyer d'échantil-
    lonneur nul (repli silencieux natif, mesuré à l'essai minimal) ; aucun
    token masqué, ou un vocabulaire entièrement masqué, refusent le
    chargement. L'échantillonneur est libéré par la chaîne après adoption.
    """
    from llama_cpp.llama_grammar import json_schema_to_gbnf

    try:
        gbnf = json_schema_to_gbnf(json.dumps(schema, ensure_ascii=False))
    except Exception as exception:
        raise RuntimeError(
            f"schéma non convertible en grammaire GBNF : {exception}"
        ) from exception
    echantillonneur = liaisons.llama_sampler_init_grammar(
        vocabulaire, gbnf.encode("utf-8"), RACINE_GRAMMAIRE.encode("utf-8")
    )
    if echantillonneur is None:
        raise RuntimeError("llama_sampler_init_grammar a renvoyé NULL")
    n_vocab, masques = _sonde_contrainte(liaisons, vocabulaire, echantillonneur)
    if masques == 0:
        liaisons.llama_sampler_free(echantillonneur)
        raise RuntimeError(
            "grammaire non contraignante : aucun token masqué sur "
            f"{n_vocab} (repli silencieux refusé, aucune génération possible)"
        )
    if masques >= n_vocab:
        liaisons.llama_sampler_free(echantillonneur)
        raise RuntimeError(
            f"grammaire bloque tout le vocabulaire ({n_vocab} tokens masqués), "
            "aucune génération possible"
        )
    chaine = liaisons.llama_sampler_chain_init(
        liaisons.llama_sampler_chain_default_params()
    )
    if chaine is None:
        # La chaîne n'existe pas : l'échantillonneur de grammaire n'a pas encore
        # été adopté, sa libération reste à notre charge.
        liaisons.llama_sampler_free(echantillonneur)
        raise RuntimeError("llama_sampler_chain_init a renvoyé NULL")
    liaisons.llama_sampler_chain_add(chaine, echantillonneur)
    # Adoption faite : la chaîne est désormais propriétaire de l'échantillonneur
    # de grammaire, elle seule le libérera.
    glouton = liaisons.llama_sampler_init_greedy()
    if glouton is None:
        liaisons.llama_sampler_free(chaine)
        raise RuntimeError("llama_sampler_init_greedy a renvoyé NULL")
    liaisons.llama_sampler_chain_add(chaine, glouton)
    return chaine, gbnf


def _sonde_contrainte(
    liaisons: Any, vocabulaire: Any, echantillonneur: Any
) -> tuple[int, int]:
    """Applique l'échantillonneur à tout le vocabulaire, sans génération.

    Rend `(n_vocab, nombre de tokens masqués en -inf)` : la lecture ne modifie
    ni l'état de la grammaire ni la mémoire du contexte.
    """
    n_vocab = int(liaisons.llama_vocab_n_tokens(vocabulaire))
    donnees = (liaisons.llama_token_data * n_vocab)()
    for indice in range(n_vocab):
        donnees[indice].id = indice
        donnees[indice].logit = 0.0
        donnees[indice].p = 0.0
    tableau = liaisons.llama_token_data_array(
        data=ctypes.cast(donnees, liaisons.llama_token_data_p),
        size=n_vocab,
        selected=0,
        sorted=False,
    )
    liaisons.llama_sampler_apply(echantillonneur, ctypes.byref(tableau))
    masques = sum(
        1
        for indice in range(n_vocab)
        if donnees[indice].logit == float("-inf")
    )
    return n_vocab, masques


def reinitialiser(moteur: dict[str, Any]) -> None:
    """Vide la mémoire KV et réinitialise la chaîne d'échantillonnage.

    Le runner appelle cette fonction avant **chaque** source : la lecture
    d'une source ne bénéficie jamais du cache de la précédente (design D4,
    relecture intégrale prouvée à l'essai minimal).
    """
    liaisons = moteur["liaisons"]
    liaisons.llama_memory_clear(moteur["mem"], True)
    liaisons.llama_sampler_reset(moteur["chaine"])


def extraire(
    moteur: dict[str, Any],
    messages: Sequence[Mapping[str, str]],
    reglages: Mapping[str, Any],
) -> dict[str, Any]:
    """Génère token par token la sortie contrainte d'une source.

    Rend les sept clés du contrat (`sortie_brute`, `tokens_entree`,
    `tokens_sortie`, `fin` ∈ {"arret", "limite"}, `delai_premier_token_s`,
    `duree_generation_s`, `temps_cpu_s`) plus `comptes_natifs`
    (`tokens_lecture`, `tokens_generation` : comptes natifs en cumul,
    différence entre deux lectures prises après échantillonnage, cohérente à
    ±1 token près) ; `comptes_natifs` n'est rendu que pour une source terminée
    (`fin` "arret" ou "limite"). Aucun temps natif n'est rendu (restés à 0.0
    dans la roue essayée).

    Si les tokens du prompt augmentés de `sortie_max` dépassent le contexte,
    lève `ErreurContexteInsuffisant` **avant** toute génération.

    Un échec en plein décodage (exception après le premier décodage) marque le
    moteur : les compteurs natifs à engagement différé de la source suivante
    seraient faussés au-delà du ±1 documenté, donc `comptes_natifs` est omis
    pour la première source entièrement décodée qui suit l'échec — une mesure
    absente, jamais une mesure fausse.
    """
    liaisons = moteur["liaisons"]
    systeme, utilisateur = _messages(messages)
    prompt = moteur["format"](systeme, utilisateur)
    tokens_prompt = _tokeniser(liaisons, moteur["vocab"], prompt)
    tokens_entree = len(tokens_prompt)
    sortie_max = _entier_positif_reglage(
        reglages, "sortie_max", DEFAUT_SORTIE_MAX_LLAMA
    )
    if tokens_entree + sortie_max > moteur["contexte"]:
        raise ErreurContexteInsuffisant(
            tokens_entree, sortie_max, moteur["contexte"]
        )

    perf_avant = liaisons.llama_perf_context(moteur["ctx"])
    debut = time.perf_counter()
    debut_cpu = time.process_time()
    fin = "limite"
    sortie: list[int] = []
    instant_premier = None
    instant_dernier = None
    try:
        _decoder_prompt(liaisons, moteur, tokens_prompt)
        while len(sortie) < sortie_max:
            jeton = liaisons.llama_sampler_sample(moteur["chaine"], moteur["ctx"], -1)
            if instant_premier is None:
                instant_premier = time.perf_counter()
            if liaisons.llama_vocab_is_eog(moteur["vocab"], jeton):
                fin = "arret"
                break
            sortie.append(jeton)
            instant_dernier = time.perf_counter()
            _decoder_jeton(liaisons, moteur, jeton, tokens_entree + len(sortie) - 1)
    except Exception:
        # Échec après le début des décodages : des compteurs différés restent
        # non engagés et fausseraient les comptes de la source suivante au-delà
        # du ±1 documenté. Le marqueur est levé après la première source
        # entièrement décodée qui suit (ses propres comptes sont omis, jamais
        # faussés ; les pendings de l'échec se replient pendant ses décodages).
        moteur["comptes_natifs_incoherents"] = True
        raise
    duree_cpu = time.process_time() - debut_cpu
    brut = _detokeniser(liaisons, moteur["vocab"], sortie)

    resultat: dict[str, Any] = {
        "sortie_brute": brut,
        "tokens_entree": tokens_entree,
        "tokens_sortie": len(sortie),
        "fin": fin,
        "delai_premier_token_s": (
            round(instant_premier - debut, 3) if instant_premier is not None else None
        ),
        "duree_generation_s": (
            round(instant_dernier - instant_premier, 3)
            if instant_premier is not None and instant_dernier is not None
            else None
        ),
        "temps_cpu_s": round(duree_cpu, 3),
    }
    # Le marqueur d'échec partiel, s'il existait, est levé APRÈS une source
    # entièrement décodée : ses comptes sont omis (faussés par les pendings de
    # l'échec), la suivante retrouve des comptes cohérents à ±1 près.
    incoherent = moteur.pop("comptes_natifs_incoherents", None)
    if fin in ("arret", "limite") and not incoherent:
        perf_apres = liaisons.llama_perf_context(moteur["ctx"])
        resultat["comptes_natifs"] = {
            "tokens_lecture": int(perf_apres.n_p_eval - perf_avant.n_p_eval),
            "tokens_generation": int(perf_apres.n_eval - perf_avant.n_eval),
        }
    return resultat


def _messages(
    messages: Sequence[Mapping[str, str]],
) -> tuple[str, str]:
    """Contenus système et utilisateur ; le runner envoie exactement ces rôles."""
    systeme = None
    utilisateur = None
    for message in messages:
        role = message.get("role")
        if role == "system" and systeme is None:
            systeme = message.get("content")
        elif role == "user" and utilisateur is None:
            utilisateur = message.get("content")
    if not isinstance(systeme, str) or not isinstance(utilisateur, str):
        raise ValueError("messages attendus : un rôle system et un rôle user")
    return systeme, utilisateur


def _decoder_prompt(liaisons: Any, moteur: dict[str, Any], tokens: list[int]) -> None:
    """Décode le prompt par morceaux, logits uniquement sur le dernier token."""
    for debut in range(0, len(tokens), moteur["n_batch"]):
        morceau = tokens[debut : debut + moteur["n_batch"]]
        lot = liaisons.llama_batch_init(len(morceau), 0, 1)
        try:
            lot.n_tokens = len(morceau)
            for indice, jeton in enumerate(morceau):
                lot.token[indice] = jeton
                lot.pos[indice] = debut + indice
                lot.seq_id[indice][0] = 0
                lot.n_seq_id[indice] = 1
                lot.logits[indice] = 0
            lot.logits[len(morceau) - 1] = 1
            code = liaisons.llama_decode(moteur["ctx"], lot)
        finally:
            liaisons.llama_batch_free(lot)
        if code != 0:
            raise RuntimeError(f"llama_decode du prompt a échoué (code {code})")


def _decoder_jeton(liaisons: Any, moteur: dict[str, Any], jeton: int, position: int) -> None:
    """Décode un token généré à sa position, logits sur ce seul token."""
    lot = liaisons.llama_batch_init(1, 0, 1)
    try:
        lot.n_tokens = 1
        lot.token[0] = jeton
        lot.pos[0] = position
        lot.seq_id[0][0] = 0
        lot.n_seq_id[0] = 1
        lot.logits[0] = 1
        code = liaisons.llama_decode(moteur["ctx"], lot)
    finally:
        liaisons.llama_batch_free(lot)
    if code != 0:
        raise RuntimeError(f"llama_decode de génération a échoué (code {code})")


def _tokeniser(liaisons: Any, vocabulaire: Any, texte: str) -> list[int]:
    """Tokenise sans ajout de tokens spéciaux, en les analysant (D4).

    Deux passes : la première demande la taille requise, la seconde remplit
    le tampon. `add_special=False` : les tokens spéciaux viennent du format
    local, jamais du tokenizer.
    """
    brut = texte.encode("utf-8")
    besoin = liaisons.llama_tokenize(
        vocabulaire,
        brut,
        len(brut),
        (liaisons.llama_token * 0)(),
        0,
        False,
        True,
    )
    if besoin < 0:
        besoin = -besoin
    elif besoin == 0:
        return []
    tampon = (liaisons.llama_token * besoin)()
    nombre = liaisons.llama_tokenize(
        vocabulaire, brut, len(brut), tampon, besoin, False, True
    )
    if nombre < 0:
        raise RuntimeError(f"tokenisation impossible (code {nombre})")
    return list(tampon[:nombre])


def _detokeniser(liaisons: Any, vocabulaire: Any, tokens: list[int]) -> str:
    """Pièces de tokens assemblées (liaison bas niveau, sans tokens spéciaux)."""
    morceaux: list[bytes] = []
    for jeton in tokens:
        tampon = ctypes.create_string_buffer(TAILLE_PIECE)
        taille = liaisons.llama_token_to_piece(
            vocabulaire,
            liaisons.llama_token(jeton),
            tampon,
            TAILLE_PIECE,
            0,
            False,
        )
        if taille < 0:
            raise RuntimeError(f"llama_token_to_piece a échoué (token {jeton})")
        morceaux.append(tampon.raw[:taille])
    return b"".join(morceaux).decode("utf-8", "replace")


def _lire_meta(liaisons: Any, handle: Any, cle: str) -> str | None:
    """Métadonnée texte du modèle en deux passes, `None` si absente."""
    brut = cle.encode("utf-8")
    taille = liaisons.llama_model_meta_val_str(handle, brut, b"", 0)
    if taille is None or taille <= 0:
        return None
    tampon = ctypes.create_string_buffer(taille + 1)
    if liaisons.llama_model_meta_val_str(handle, brut, tampon, taille + 1) < 0:
        return None
    return tampon.raw[:taille].decode("utf-8", "replace")


def _chemin_modele(modele: Mapping[str, Any]) -> Path:
    """Fichier GGUF local du job, refusé s'il est absent ou illisible."""
    if modele.get("local_files_only") is not True:
        raise RuntimeError(
            "chargement local obligatoire : local_files_only doit valoir True"
        )
    valeur = modele.get("chemin")
    if not isinstance(valeur, str) or not valeur.strip():
        raise RuntimeError("chemin de modèle absent du job")
    chemin = Path(valeur)
    if not chemin.is_file():
        raise RuntimeError(f"fichier de modèle absent : {chemin}")
    return chemin


def _entier_positif_reglage(
    reglages: Mapping[str, Any], nom: str, defaut: int
) -> int:
    """Réglage entier positif du job, ou sa valeur par défaut documentée."""
    valeur = reglages.get(nom, defaut)
    if isinstance(valeur, bool) or not isinstance(valeur, int) or valeur < 1:
        raise ValueError(f"réglage {nom!r} invalide : {valeur!r}")
    return valeur
