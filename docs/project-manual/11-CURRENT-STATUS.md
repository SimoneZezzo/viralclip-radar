# 26. Stato reale, prove e incertezze

[Indice](00-INDEX.md) · [Prove e limiti](10-TESTING-AND-RELIABILITY.md) · [Roadmap](12-ROADMAP.md) · [Decisioni](15-DECISION-REGISTER.md)

**Stato attuale produzione UNKNOWN al 20 novembre 2026.** La revisione locale è `c01480c6d401d84ae0cb4d169c333e409231395f`, branch `chore/context-efficiency`, sei ahead e zero behind rispetto a `master`, senza remote in questa copia all'ispezione. Le modifiche locali presenti prima dell'audit sono indicate nell'[indice](00-INDEX.md). Nessuna versione installata è stata dedotta da Git locale. Il repository distingue le milestone di prodotto `M0–M4`, le fasi di rollout `0–9` di M1 e i lavori sul workflow `P0–P2`. [Tracker](../../PROJECT_STATUS.md) · [Specifiche](../PROJECT_SPECIFICATION.md) · [Runbook operativo](../MILESTONE_1_ROLLOUT.md)

## Milestone di prodotto e rollout

| Milestone | Obiettivo e implementazione | Prova datata | Dipendenza e criterio per completare |
| --- | --- | --- | --- |
| **M0 Collector MVP. GO storico** | Auth app, Helix discovery/snapshot, coda, schema, lock e CLI. Requisito: raccolta prospettica di clip uniche e più misure con tempo effettivo. | 17 novembre prova supervisionata, 125 clip nella prima discovery una tantum, dopo restart i job continuano. 18 novembre, dopo il blackout documentato, 1.338 finestre mature e 1.323 label valide con almeno una misura in prima ora, 15 unavailable. Integrità e append-only osservati. I mock M0 oggi passano. [Fonte](../PROJECT_HISTORY.md#2026-11-18-final-milestone-0-acceptance-go) | Accettazione storica completata. Specifica richiede credenziali reali, comandi documentati, dati temporali, test. Non equivale al gate di servizio 24/7. |
| **M1A Health. Completo come componente** | Report salute read-only con cadenza, gap, queue e lateness. | Test health e report locali del 18 novembre. [Fonte](../PROJECT_HISTORY.md#2026-11-18-milestone-1a-collector-health-monitoring) | Per servizio unattended servono runtime Linux, monitor e alert. |
| **M1B Telemetria. GO storico Windows** | Client emette tentativi, retry, OAuth e rate limit in JSONL bounded. | Rollout 18 novembre, circa 10 min, 134 HTTP 200 e 26 job in gap ripresi. Failure/429/401 verificati via mock, quella finestra live non ne registrò. [Fonte](../PROJECT_HISTORY.md#2026-11-18-milestone-1b-controlled-rollout-verified-go) | Telemetria processo e revisione VPS attuali UNKNOWN. |
| **M1C Supervisione e migrazione Linux. PARZIALE** | Unit e preflight V, cutover con backup e rollback, supervisore Windows alternativo. | Prova sintetica di trasferimento e Windows. Resoconto operatore del 19 novembre su OVH Ubuntu 24.04 con V attivo. [Linux offline](../PROJECT_HISTORY.md#2026-11-18-milestone-1c-linux-vps-deployment-preparation) · [Resoconto](../PROJECT_HISTORY.md#2026-11-19-daily-backup-and-monitoring-automation) | Dimostrare baseline, unità effettive, revisioni, permessi e continuità. |
| **Duale e M1 unattended. PARZIALE / in attesa di fase 0** | VI separato, ops restore con ID pin, monitor e timer configurati, isolamento profili e rollback documentati. | 19 novembre, due campioni operatori circa 18:09→18:13 UTC: PID distinti e stabili, DB senza errori integrità/FK/categoria nei campioni, discovery e refresh avanzano. V boot enabled, VI disabled. Otto unità ops attese assenti. Correzioni cross-game e Bash provate offline. [Fonte](../PROJECT_HISTORY.md#2026-11-19-operator-production-evidence-and-milestone-1-release-review) | Fase 0 completa con due campioni rispettando durata e inventario, poi ancore off-VPS, scope/provider, mount probe, backup/restores per entrambi, timer, alert failure/recovery e policy boot VI con prova. [Acceptance](../MILESTONE_1_ROLLOUT.md#acceptance-and-risk) |
| **M2A Estrazione. IMPLEMENTATO e TESTATO, replay circoscritti** | Cutoff 30/35/60/65, features as of, outcome, coverage, manifest 2a.2. | 18 novembre replay reali su tre coorti GTA V, 909/1.278/1.323 label valide per coorte. Esportazione e hash controllati allora con 2a.1 e riletti per 2B in 2a.2. [Fonte](../PROJECT_HISTORY.md#2026-11-18-milestone-2a-point-in-time-dataset-builder) | Estrazione disponibile. Per decisioni ranking raccogliere giorni maturi, usare le regole di coorte e quantificare missing e coverage. |
| **M2B Replay. IMPLEMENTATO e TESTATO. Baseline reale BLOCCATA nell'ultimo replay documentato** | Verifica hash e split/embargo, 4 baseline, 3 metriche, report coverage/matched. | Replay 18 novembre, 3.596 clip uniche, 14.384 candidati, 3.344 matched su un solo giorno parziale, zero giorni rankable. `INSUFFICIENT DATA`, nessuno score di performance. [Fonte](../PROJECT_HISTORY.md#2026-11-18-milestone-2b-chronological-evaluation-and-ranking-baselines) | Servono 2 giorni UTC rankable in ciascuna partizione dopo embargo e pool ≥10 matched con esiti distinti. Verificare le date recenti in fonte autorizzata e stabilità reale prima del training. Disponibilità attuale UNKNOWN. |
| **M3 Modelli. PROGETTATO, BLOCCATO a monte** | Specifica per logistica/LightGBM, split temporali e creator holdout. Nessun training verificato o implementazione del trainer in questa copia. | Evidenza disponibile riguarda solo estrazione e baseline. [Specifica](../PROJECT_SPECIFICATION.md#6-milestone-3--machine-learning) | Baseline reale valida, protocollo dichiarato, sufficienti label, confronto validation/test e calibration se si dichiarano probabilità. |
| **M4 Demo. PROGETTATO, incompleto** | README, .env.example, Gitignore, test e workflow già presenti. Demo Streamlit sintetica, guida completa, licenza MIT e pubblicazione previste. | Verifica packaging locale riproducibile. Nessun remote configurato e nessuna esecuzione CI remota dimostrata. [Specifica](../PROJECT_SPECIFICATION.md#7-milestone-4--open-source-demo--github-presentation) | Demo offline verificata, dati generati etichettati, limiti, benchmark riproducibile, audit pubblicazione e autorizzazione. Termini per real data/weights sono tema distinto. |

### P0, P1, P2 del workflow

- **P0 GO locale**, 19 novembre. Ignores, regole LF e baseline prima della riproduzione. `0b26d10` e `dd4a43b`. [Evidenza P0](../PROJECT_HISTORY.md#2026-11-19-p0-git-baseline-hardening)
- **P1 GO locale**, 19 novembre. Test da checkout Windows pulito, 159 test e 7/7, packaging da blob Git. `1c8c16d`. CI remota e Ubuntu **UNKNOWN**. [Evidenza P1](../PROJECT_HISTORY.md#2026-11-19-p1-offline-verification-and-reproducible-packaging)
- **P2 GO locale**, 19 novembre. Handoff corto, specifica completa e storia separate. Benchmark contesto inconclusivo sui task riusciti e sulla scelta High/Medium. `1434c49`, `f998517` e `c01480c`. Nessuna gate produzione deriva da P2. [Evidenza P2](../PROJECT_HISTORY.md#2026-11-19-p2-context-and-token-efficiency)
- **20 novembre, audit locale.** Verifica strict Windows 159 test e 7/7 PASS. Manuale e nota di evidenza documentano ciò che è stato letto. Il nuovo script di fase 0 compare nei tre file Bash analizzati dal parser. [Verifica](10-TESTING-AND-RELIABILITY.md)

## Come risolvere apparenti contraddizioni

| Due affermazioni da distinguere | Riscontro |
| --- | --- |
| `status` è “local” e non usa credenziali, mentre un'ispezione rispettosa usa read-only | `cli.main` apre il writer e invoca migrazioni per `status`. Il termine locale descrive assenza di HTTP. `health` usa `mode=ro` e `query_only`. [CLI](../../src/viralclip/cli.py) |
| Spec originale “never hardcode or invent a GTA VI game ID” e pin `1867279146` | L'obiettivo era evitare invenzioni e fallback. Il wrapper vincola a un ID verificato con due lookup Helix il 19 novembre e rifiuta V, con evidenza specifica. [ID](../../src/viralclip/gta_vi.py) · [Fonte](../PROJECT_HISTORY.md#2026-11-19-gta-vi-launch-pilot-prepared-offline) |
| “10 pagine” e “troncamento a 900” | Il code path controlla prima 900 righe, poi fine cursore, poi soglia pagine con continuazione. Un decimo GET con pagine non piene può esserci. Aver visto dieci pagine non prova incompleto. [Code path](../../src/viralclip/collector/service.py#L64) |
| Riferimenti cronologici `2a.1` vs attuale `2a.2` | 2a.1 è il primo export. 2a.2 aggiunge il grouping audit broadcaster. 2B supporta entrambe. [Versioni](../POINT_IN_TIME_DATASET.md) · [Reader](../../src/viralclip/evaluation.py#L148) |
| Spec parla di tolleranza 55–65m e un cutoff 60m | Il codice non inserisce a 60m una misura successiva. Gli esperimenti 65m e 35m sono esplicitamente posteriori. [Feature](08-DATA-PIPELINE.md#perché-quattro-cutoff) |
| Audit storico NO-GO, runbook CONDITIONAL GO e priorità fase 0 | È condizionale per rollout ops e historical nell'evidenza precedente, mentre unattended resta aperto. Due campioni a quattro minuti non soddisfano il nuovo requisito di sei e inventario. [Audit storico](../PRODUCTION_HEALTH_AUDIT.md) · [Rollout](../MILESTONE_1_ROLLOUT.md) |
| Vecchio controllo usa helper full/sample, preparazione recente cita nuovo script | L'helper storico ha accessi e metriche più ampi. La working copy preesistente aggiorna la fase 0 al nuovo script standalone con Landlock e A/B. Il runbook conserva domini di prova distinti. [Runbook fase 0](../MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline) |
| M1 base del release review `8fefbf9` e archivio strict su `c01480c` | Il primo è il sorgente applicativo indicato per le correzioni dual, il secondo è il commit locale verificato per il package. L'installato è UNKNOWN senza ricevuta. [Baseline rollout](../MILESTONE_1_ROLLOUT.md#local-release-review) |

## Elenco di ciò che resta UNKNOWN

- PID, eseguibile/revisione caricata, configurazione effettiva, marker, current boot policy, mount, spazio disponibile e autonomia dei due processi **oggi**.
- Identità DB, integrità e progresso **oggi**, prove A/B della fase 0, ambienti e timer alternativi, eventuale writer/prune esterno, compatibilità Landlock e permessi attuali.
- Presenza e freschezza di recovery anchor verificati fuori VPS per entrambi, provider/S3 scope e repo ID, restore reale, retention e ultima esecuzione da timer, latency e perdita effettiva con un incidente.
- Consegna/recupero di alert, traffico TLS/Helix e budget attuali, interferenza fra collector durante carico e backup, reboot recovery per VI e task Windows unattended.
- Percentuali correnti di GTA VI incompleto/missed, distribuzione conseguente e popolazione mai restituita da Twitch.
- Numero di giorni maturi recenti su DB o artefatti privati, qualità delle baseline reali e disponibilità di dati sufficienti per ML.
- Risultati nativi Linux e GitHub Actions, e comportamento di un eventuale prodotto pubblicato.
- Motivazioni originali non registrate, configurazioni o operazioni non documentate nel repository e nelle prove datate. Le aree sopra richiedono evidenza esterna al read-only locale. [Piano dei gate](12-ROADMAP.md)

## Copertura del manuale

Si conta la base ispezionata prima di creare il manuale, separata dai suoi stessi documenti. Le 152 definizioni Python includono cinque callback annidati e i metodi espliciti, mentre i costruttori generati da dataclass sono descritti attraverso i campi. Il totale dei test nella suite include i casi parametrizzati.

| Perimetro | Inventariati | Analizzati/documentati | Da analizzare nella base |
| --- | ---: | ---: | ---: |
| Moduli `src/viralclip` | 19 | 19 | 0 |
| Tool Python `scripts` | 2 | 2 | 0 |
| Definizioni Python in src e scripts | 152 | 152 | 0 |
| File test | 13 | 13 | 0 |
| Funzioni di test a livello modulo | 112 | 112 indicizzate e coperte nelle schede per file | 0 |
| File `deploy` | 15 | 15 | 0 |
| File originali `docs` incluso helper fase 0 | 16 | 16 | 0 |
| File root, editor e CI | 11 | 11 | 0 |
| **Totale base file** | **76** | **76** | **0** |
| Tabelle SQLite definite dall'applicazione | 8 | 8 | 0 |

[Albero e inventario file](03-REPOSITORY-MAP.md) · [Schede e riferimenti](04-CODE-WALKTHROUGH/00-GUIDE.md) · [Schema ER](06-DATABASE.md)
