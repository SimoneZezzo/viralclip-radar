# 27. Roadmap per dipendenze e gate

[Indice](00-INDEX.md) · [Stato e incertezze](11-CURRENT-STATUS.md) · [Decisioni](15-DECISION-REGISTER.md)

## CURRENT SCOPE — M0–M4

La priorità è chiudere M1 e M2. Per M1 servono collector affidabili 24/7 e prove di continuità e ripartenza. Per M2 occorre risolvere i problemi di discovery, copertura e qualità, ottenere coorti mature verificabili e valutare le baseline su split cronologici. M3 potrà iniziare quando queste evidenze saranno sufficienti. M4 conserva la demo offline con dati sintetici. Lo [stato operativo](../../PROJECT_STATUS.md#current-priority) riporta i gate aperti e le prossime verifiche.

### Piano di lavoro storico

La tabella seguente conserva le dipendenze del piano originario. Per M1 si applicano le decisioni successive, inclusa la rinuncia al backup fuori VPS e la cancellazione di M1-02. [Decisione del 21 novembre](../PROJECT_HISTORY.md#2026-11-21-research-first-strategy-and-read-only-audit)

| Ordine, stato | Attività, motivazione e file | Prova di successo e rischio | Confine e risultato |
| --- | --- | --- | --- |
| 1, immediato in locale | Consolidare la lettura di handoff, script e prerequisiti. Se si prepara un release candidato, identificare il commit da esaminare con `scripts/verify_offline.py` e `scripts/package_release.py`. | Esiti strict, inventario, hash e file selezionati. Rischio: confondere working copy e blob Git. | Locale. Commit, push o upload richiedono la rispettiva decisione. Prepara M1. |
| 2, bloccato da autorizzazione | Fase 0 VPS. `docs/phase0-inspect.sh` e runbook M1. Due sample UTC, A/B, 6m, capacità e orari. Verificare account, PID, inode, wrong rows, checkpoint, job e alternative cron/timer. | Baseline confrontabile, nessun cambiamento di PID, dati in progresso e riscontri/comandi mancanti registrati. Fermarsi se drift, alias, errori, pressione o automazioni inspiegate. | Ispezione live e staging file remoto autorizzati. Produce l'evidenza iniziale per M1. |
| 3, dopo baseline e autorizzazione | Fasi 1–2 M1. Creare ancore separate online/standalone, copia su destinazione privata fuori VPS, verificare due manifest pinnati e hash. Review del package da commit. | Verifica in due ambienti, watermark e schema, nessun riuso di un output, riserva disco sufficiente. Rischio I/O e archivi/dati trattati come privati. | Scritture di backup e transfer autorizzati. Capacità di rollback/recovery indipendente. |
| 4, dopo ancore | Fasi 3–5 M1. Preparare servizi ops, secret per account, due profili Restic indipendenti con repo ID/prefissi/scope, validazione degli input. | Diverso repo/scope e mount namespace corretti. Bloccare prune finché l'indipendenza non è dimostrata. Possono esserci costi di storage e permessi da accordare. | Produzione, credenziali, state remoto e provider sotto autorizzazione. Prepara installazione M1. |
| 5, dopo isolamento | Fase 6 M1, installare le sole otto unità ops candidate, verify unit/probe, backup iniziali per entrambi. | Stesso PID e inode in raccolta, nuove copie/marker e upload per gioco, integrità verificata. Fallimento preserva il collector e le copie buone. | Autorizzazione operations e storage/prune, traffico e file lato VPS. |
| 6, dopo upload | Fase 7 M1. Restore offsite in dir separate, check manifest e watermark, verifica monitor failure/recovery. | Un solo bundle per restore e ID corretto, controlli SQLite, risposta del ricevitore esterno e ritorno a healthy. Valutare spazio impiegato. | Ripristini isolati e test alert richiedono autorizzazione. M1 recuperabilità. |
| 7, dopo drill | Fase 8 M1. Attivare e osservare timer, decidere boot GTA VI e prova reboot autorizzata. | Quattro timer con esecuzioni da calendario, due collector indipendenti e job post-boot. Applicare rollback ops-only se richiesto. Un reboot può perdere misure non recuperabili. | Modifica supervisione e boot, decisione esplicita. Chiude M1 solo con gate documentati. |
| 8, in attesa di dati | Estendere letture 2A sui periodi UTC integri e maturi, con versionamento da `dataset.py` e `POINT_IN_TIME_DATASET.md`. Dichiarare watermark, blackout, gioco e retention privata. | Coverage, label, istanti e hash verificati. Controllare contemporaneamente disponibilità originaria, outcome non osservabili e concentrazione. Evitare I/O su VPS durante backup. | Lettura di dati reali e trasferimento autorizzati secondo sede, applicativi locali se su copia approvata. Sblocca M2B. |
| 9, dopo dati | Dichiarare split e K, eseguire replay `evaluation.py` su artefatti 2A. Controllare almeno due giorni per periodo dopo embargo, ≥10 matched e variazione in ogni pool. | `EVALUATED` con metriche validation/test, copertura e stima di stabilità. Decisione separata su sufficienza statistica. | Locale/privato. Completa prova reale M2 e fornisce baseline M3. |
| 10, opportunità separata | Studiare GTA VI con flags non equivoci, distribuzioni della discovery lag e strict coverage a 10/30/60. Se il problema è misurato, confrontare strategia attuale e finestre più piccole. | Effetto su quota incompleta, coverage, volume API, latency refresh e costo. Non attribuire all'algoritmo che si vede localmente un fenomeno senza revisione provata. | Misura read-only autorizzata e, solo con altra approvazione, pilot live. Migliora M1/M2 senza confondere i gate. |
| 11, futuro | Decidere target e cutoff primari, addestrare un candidato semplice e un candidato ad alberi sul train, validare e congelare prima del test. Crea file nuovi solo in un incarico M3. | Parità pool, riproducibilità, controllo leakage, metriche e limiti, eventuale calibrazione/holdout e model card. Senza benefici resta la baseline. | Decisione ricerca e uso dati. Storage privato. Completa M3 solo con risultati. |
| 12, futuro | Demo offline M4. Generatore sintetico e interfaccia Streamlit locale come specificato, guida e licenza, benchmark e demo senza asset privati. | Offline, dataset dichiarato sintetico, link/feature intermedi e stato fallback coerenti. Verifica CI quando esiste repository remoto autorizzato. | Codice locale prima, pubblicazione distinta. M4. |
| 13, facoltativo | Dopo misure, valutare dichiarazione profili multi-game, riduzione N+1, hardening di backoff, monitor lag e metriche di commit-time o partition. | Baseline costi, regressioni mirate e invarianti preservati. Migrazioni solo con nuovo incarico e operatività autorizzata. | Miglioramenti per scala prodotto, non prerequisiti inventati per lo studio attuale. |

[Runbook M1 e soglie](../MILESTONE_1_ROLLOUT.md#acceptance-and-risk) · [Gate di valutazione](../CHRONOLOGICAL_EVALUATION.md#when-scoring-is-permitted) · [Specifica delle milestone](../PROJECT_SPECIFICATION.md)

## FUTURE SCOPE — dopo M4

L'espansione si valuterà dopo le milestone attuali e dopo la validazione e distribuzione autorizzata del primo modello Twitch. La numerazione è indicativa. Prima di avviare ciascuna fase si definiranno prerequisiti, criteri di accettazione misurabili, metodo di validazione ed evidenze necessarie per decidere GO/NO-GO.

| Fase proposta | Domanda da valutare |
| --- | --- |
| M5 — Multimodal Content Understanding | Quali segnali di video, audio e dialogo si possono estrarre in modo affidabile da clip autorizzate? |
| M6 — Automated Video Editing | Il creator può ottenere, esaminare e approvare una variante verticale con sottotitoli? |
| M7 — Social Publishing and Analytics | Per una piattaforma e un account autorizzato, si può pubblicare il montaggio approvato e misurarne gli esiti tramite API ufficiali? |
| M8 — Cross-platform Dataset | Quali post e misure si possono attribuire con sufficiente certezza a una clip e a una variante utilizzabili per la ricerca? |
| M9 — Cross-platform ML and Ranking | A parità di condizioni, la selezione specifica per piattaforma migliora i risultati rispetto alle baseline? |
| M10 — MCP Server and tool Agent Integration | Un agente può usare il backend rispettando permessi, approvazione e tracciabilità? |
| M11 — Continuous Experimental Optimization | Gli aggiornamenti derivati dai risultati pubblicati mantengono un vantaggio su coorti successive? |

Obiettivo di prodotto, disegno degli esperimenti e responsabilità del backend sono descritti nella [visione di lungo termine](../LONG_TERM_PRODUCT_VISION.md).
