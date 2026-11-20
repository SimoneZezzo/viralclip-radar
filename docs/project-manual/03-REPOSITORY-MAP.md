# 5 e 28. Inventario e percorso di lettura

[Indice](00-INDEX.md) · [Chiamate](02-ARCHITECTURE.md#entry-point-e-mappa-delle-chiamate) · [Schede](04-CODE-WALKTHROUGH/00-GUIDE.md)

Base dell'inventario: 75 file tracciati da Git e il preesistente `docs/phase0-inspect.sh` non tracciato. Esclusi metadati `.git/`, dipendenze in `.venv/`, bytecode, cache pytest/Ruff, build e altri output generati. `.env` reale, `data/`, backup, export e log privati restano fuori dall'inventario per il confine dati dell'audit. Qui sono descritti gli esempi sicuri e i nomi dei parametri. [Regole](../../WORKFLOW.md) · [Esclusioni](../../.gitignore)

## Albero della base ispezionata

```text
viralclip-radar/
├── .env.example
├── .gitattributes
├── .github/workflows/ci.yml
├── .gitignore
├── .python-version
├── .vscode/settings.json
├── WORKFLOW.md
├── PROJECT_STATUS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── deploy/
│   ├── backup.env.example
│   ├── collector.env.example
│   ├── dual-collector-health.sh
│   ├── gta-vi-backup.env.example
│   ├── gta-vi.env.example
│   ├── viralclip-backup.service
│   ├── viralclip-backup.timer
│   ├── viralclip-collector.service
│   ├── viralclip-gta-vi-backup.service
│   ├── viralclip-gta-vi-backup.timer
│   ├── viralclip-gta-vi-monitor.service
│   ├── viralclip-gta-vi-monitor.timer
│   ├── viralclip-gta-vi.service
│   ├── viralclip-monitor.service
│   └── viralclip-monitor.timer
├── docs/
│   ├── BACKUP_AND_MONITORING.md
│   ├── CHRONOLOGICAL_EVALUATION.md
│   ├── DUAL_COLLECTOR_OPERATIONS.md
│   ├── GTA_VI_PILOT.md
│   ├── HTTP_TELEMETRY_ROLLOUT.md
│   ├── LINUX_DEPLOYMENT.md
│   ├── MILESTONE_0_AUDIT.md
│   ├── MILESTONE_1_ROLLOUT.md
│   ├── OVHCLOUD_CUTOVER.md
│   ├── POINT_IN_TIME_DATASET.md
│   ├── PRODUCTION_HEALTH_AUDIT.md
│   ├── PROJECT_HISTORY.md
│   ├── PROJECT_SPECIFICATION.md
│   ├── WINDOWS_SUPERVISION.md
│   ├── phase0-inspect.sh
│   └── production-health-readonly.sh
├── scripts/
│   ├── package_release.py
│   └── verify_offline.py
├── src/viralclip/
│   ├── __init__.py
│   ├── __main__.py
│   ├── cli.py
│   ├── config.py
│   ├── collector/
│   │   ├── __init__.py
│   │   └── service.py
│   ├── dataset.py
│   ├── deployment.py
│   ├── evaluation.py
│   ├── gta_vi.py
│   ├── operations.py
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── backup.py
│   │   ├── database.py
│   │   └── health.py
│   ├── twitch/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── telemetry.py
│   └── windows_supervision.py
└── tests/
    ├── test_audit.py
    ├── test_backup.py
    ├── test_collector.py
    ├── test_dataset.py
    ├── test_deployment.py
    ├── test_dual_collector_runbook.py
    ├── test_evaluation.py
    ├── test_gta_vi.py
    ├── test_health.py
    ├── test_http_telemetry.py
    ├── test_operations.py
    ├── test_release_packaging.py
    └── test_windows_supervision.py
```

L'aggiunta di questo audit è la directory `docs/project-manual/`. Il suo albero logico è l'[indice](00-INDEX.md) con la sottodirectory [`04-CODE-WALKTHROUGH/`](04-CODE-WALKTHROUGH/00-GUIDE.md).

## Root, configurazione e strumenti

| File | Tipo, uso, dipendenze e destinatario |
| --- | --- |
| [`.env.example`](../../.env.example) | Template fondamentale locale. Nomi Twitch, DB, timing e game. Operatore lo usa per configurare ambiente che la CLI legge via `config.py`. |
| [`.gitattributes`](../../.gitattributes) | Config Git. Impone LF su .sh, unità e template deploy usati su Linux e dal packager. |
| [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | Config di automazione. Matrix Windows/Ubuntu, sync lock e verifica strict. Dipende da uv e dallo script di controllo. |
| [`.gitignore`](../../.gitignore) | Esclusioni fondamentali per credenziali e dati. Git, verifier e `ignored_output` le consultano. |
| [`.python-version`](../../.python-version) | Pin locale 3.12 per uv. Il requisito package resta 3.11+ nel pyproject. |
| [`.vscode/settings.json`](../../.vscode/settings.json) | Secondario, consente l'environment file nei terminali Python dell'IDE. |
| [`WORKFLOW.md`](../../WORKFLOW.md) | Regole fondamentali di lavoro e autorizzazione. Rimanda a tracker, specifica e storia. |
| [`PROJECT_STATUS.md`](../../PROJECT_STATUS.md) | Handoff breve, priorità e gate. Puntatore a runbook/storia. Modifica preesistente nella working copy. |
| [`README.md`](../../README.md) | Quickstart e comandi d'uso, semantica delle osservazioni, telemetria e verifiche avvio. Collega procedure e `pyproject.toml` lo usa per il package. |
| [`pyproject.toml`](../../pyproject.toml) | Definizione fondamentale del package, build Hatchling, dipendenze httpx/dotenv, entry `viralclip.cli:main`, gruppo pytest/Ruff. |
| [`uv.lock`](../../uv.lock) | Lock versioni/artefatti e hash, include dipendenze transitive di runtime/dev. uv lo usa con pyproject, CI e packager lo conservano. |
| [`scripts/package_release.py`](../../scripts/package_release.py) | Tool di rilascio fondamentale, prende Git e produce tar.gz da allowlist, digest e inventario. Usato da runbook, test e verifica offline. |
| [`scripts/verify_offline.py`](../../scripts/verify_offline.py) | CLI qualità, orchestra pytest, Ruff, Git, sintassi e packaging con scratch sintetico. Usato localmente e da CI. |

## Modelli deploy

| File | Tipo, contenuto e collegamento di runtime |
| --- | --- |
| [`deploy/backup.env.example`](../../deploy/backup.env.example) | Template ops V di destinazione non segreta e retention. Copia autorizzata usata dal backup V e letta da `operations`. |
| [`deploy/collector.env.example`](../../deploy/collector.env.example) | Template collector V con path, timing e campi credenziali vuoti. Usato da unit V e preflight. |
| [`deploy/dual-collector-health.sh`](../../deploy/dual-collector-health.sh) | Bash operativo, invoca le due CLI health nei due account e aggrega esiti, riprodotto nel runbook e provato in test. |
| [`deploy/gta-vi-backup.env.example`](../../deploy/gta-vi-backup.env.example) | Template ops VI, profilo indipendente per Restic e retention, consumato dall'unità backup VI. |
| [`deploy/gta-vi.env.example`](../../deploy/gta-vi.env.example) | Template pilot con pin ID VI, directory indipendenti, 300/10. Unit e `gta_vi._preflight`. |
| [`deploy/viralclip-backup.service`](../../deploy/viralclip-backup.service) | Unit oneshot di probe, copia e upload V. Legge EnvironmentFile e LoadCredential del profilo V, invoca `operations` con ID V. |
| [`deploy/viralclip-backup.timer`](../../deploy/viralclip-backup.timer) | Timer corrispondente backup V, quotidiano 03:30 UTC con persistenza. |
| [`deploy/viralclip-collector.service`](../../deploy/viralclip-collector.service) | Unit primaria V, marker, preflight `deployment`, `viralclip collect` e riavvio. |
| [`deploy/viralclip-gta-vi-backup.service`](../../deploy/viralclip-gta-vi-backup.service) | Unit oneshot backup VI, mirror logico con account, mount, credenziali, ID e DB dedicati. |
| [`deploy/viralclip-gta-vi-backup.timer`](../../deploy/viralclip-gta-vi-backup.timer) | Timer backup VI, 04:15 UTC persistente. |
| [`deploy/viralclip-gta-vi-monitor.service`](../../deploy/viralclip-gta-vi-monitor.service) | Unit oneshot monitor per unit/DB/marker VI. Usa `operations probe/monitor` e alert del profilo VI. |
| [`deploy/viralclip-gta-vi-monitor.timer`](../../deploy/viralclip-gta-vi-monitor.timer) | Timer monitor VI con calendario 5m e accuratezza 20s. |
| [`deploy/viralclip-gta-vi.service`](../../deploy/viralclip-gta-vi.service) | Unit primaria VI, marker diverso, binario/path distinto e quote CPU/I/O/RAM, chiama `gta_vi run`. |
| [`deploy/viralclip-monitor.service`](../../deploy/viralclip-monitor.service) | Unit oneshot V. Probe read-only, monitor, credenziale alert V. |
| [`deploy/viralclip-monitor.timer`](../../deploy/viralclip-monitor.timer) | Timer monitor V, 5m e accuratezza 20s. |

## Documentazione e helper con prova storica

| File | Tipo, ruolo e collegamenti |
| --- | --- |
| [`docs/BACKUP_AND_MONITORING.md`](../BACKUP_AND_MONITORING.md) | Runbook generale Restic, retention, monitor/restore, comandi unit/ops e profilo. |
| [`docs/CHRONOLOGICAL_EVALUATION.md`](../CHRONOLOGICAL_EVALUATION.md) | Contratto di `evaluation.py`, input 2A, embargo, metriche e scorciatoie da evitare. |
| [`docs/DUAL_COLLECTOR_OPERATIONS.md`](../DUAL_COLLECTOR_OPERATIONS.md) | Runbook dual per package e profili indipendenti, rollback e helper health. Per rollout corrente partire da M1. |
| [`docs/GTA_VI_PILOT.md`](../GTA_VI_PILOT.md) | Staging, pin, capacity e stop pilot, `gta_vi.py`, template e unit. |
| [`docs/HTTP_TELEMETRY_ROLLOUT.md`](../HTTP_TELEMETRY_ROLLOUT.md) | Runbook storico Windows 1B, backup, restart controllato, verifica JSONL e coerenza DB. |
| [`docs/LINUX_DEPLOYMENT.md`](../LINUX_DEPLOYMENT.md) | Runbook Linux generico, compatibilità, ipotesi Oracle/x86, cutover e rollback con backup/deployment. |
| [`docs/MILESTONE_0_AUDIT.md`](../MILESTONE_0_AUDIT.md) | Audit storico del collector, regressioni e trace post-fix. Il verdetto successivo di accettazione è nel registro. |
| [`docs/MILESTONE_1_ROLLOUT.md`](../MILESTONE_1_ROLLOUT.md) | Procedura attiva con fase 0 e gate 1–9, helper standalone, identità, backup, restore e decisioni autorizzate. |
| [`docs/OVHCLOUD_CUTOVER.md`](../OVHCLOUD_CUTOVER.md) | Runbook cutover specifico OVH, bootstrap e migrazione a writer Linux, verifica e rientro. |
| [`docs/POINT_IN_TIME_DATASET.md`](../POINT_IN_TIME_DATASET.md) | Contratto di `dataset.py` con coorti, versioni, output e replay datati. |
| [`docs/PRODUCTION_HEALTH_AUDIT.md`](../PRODUCTION_HEALTH_AUDIT.md) | Audit storico con vecchi NO-GO e script collegato. Da leggere accanto alle correzioni locali successive. |
| [`docs/PROJECT_HISTORY.md`](../PROJECT_HISTORY.md) | Registro fonti e decisioni datate, milestone e sessioni P0–P2. |
| [`docs/PROJECT_SPECIFICATION.md`](../PROJECT_SPECIFICATION.md) | Specifica prodotto, requisiti e milestone originali. Include layout proposto e attività future. |
| [`docs/WINDOWS_SUPERVISION.md`](../WINDOWS_SUPERVISION.md) | Design e runbook Windows Task Scheduler, preparazione offline e opzioni operatori. |
| [`docs/phase0-inspect.sh`](../phase0-inspect.sh) | Helper operativo locale untracked all'inizio. Bash con Python inline, systemd e SQLite aggregato confinato per evidenza M1. |
| [`docs/production-health-readonly.sh`](../production-health-readonly.sh) | Helper Bash dell'audit storico, due profili, systemd, log, backup e query SQLite aggregate. |

## Moduli applicativi

| File | Scopo e dipendenze principali |
| --- | --- |
| [`src/viralclip/__init__.py`](../../src/viralclip/__init__.py) | Metadato package, versione. Importato con il pacchetto. |
| [`src/viralclip/__main__.py`](../../src/viralclip/__main__.py) | Entry per `python -m viralclip`, chiama la CLI. |
| [`src/viralclip/cli.py`](../../src/viralclip/cli.py) | Fondamentale, parser/loop, collega storage, research, client, config e collector. |
| [`src/viralclip/config.py`](../../src/viralclip/config.py) | Ambiente/dataclass e default, utilizzati da CLI/preflight. Dipende da dotenv. |
| [`src/viralclip/collector/__init__.py`](../../src/viralclip/collector/__init__.py) | Inizializzatore descrittivo del namespace collector. |
| [`src/viralclip/collector/service.py`](../../src/viralclip/collector/service.py) | Fondamentale, orchestra finestre, pagine, job e snapshot, collega DB e client. |
| [`src/viralclip/dataset.py`](../../src/viralclip/dataset.py) | Ricerca 2A, usa SQLite RO e helper UTC, produce artefatti consumati da evaluation. |
| [`src/viralclip/deployment.py`](../../src/viralclip/deployment.py) | Ops, preflight e manifest, connette config e backup, usato da unità e operations. |
| [`src/viralclip/evaluation.py`](../../src/viralclip/evaluation.py) | Ricerca 2B, consuma artefatti dataset, helper UTC e statistiche stdlib. |
| [`src/viralclip/gta_vi.py`](../../src/viralclip/gta_vi.py) | Wrapper pilot, gate pin e path, dipende da CLI, config, deployment e client. |
| [`src/viralclip/operations.py`](../../src/viralclip/operations.py) | Backup e monitor Linux, usa deployment/storage e subprocess Restic/systemctl. |
| [`src/viralclip/storage/__init__.py`](../../src/viralclip/storage/__init__.py) | Inizializzatore descrittivo del namespace storage. |
| [`src/viralclip/storage/backup.py`](../../src/viralclip/storage/backup.py) | Copia online e validate, dipende da sqlite3 e config. Chiamato da deployment e ops. |
| [`src/viralclip/storage/database.py`](../../src/viralclip/storage/database.py) | Fondamentale, SQL/schema/lock/job e helper UTC riusati ovunque. |
| [`src/viralclip/storage/health.py`](../../src/viralclip/storage/health.py) | Metriche RO per CLI e ops, dipende dal contratto DB e UTC. |
| [`src/viralclip/twitch/__init__.py`](../../src/viralclip/twitch/__init__.py) | Inizializzatore descrittivo del namespace Twitch. |
| [`src/viralclip/twitch/client.py`](../../src/viralclip/twitch/client.py) | Fondamentale, connessione Helix/OAuth con httpx, retry, parser ed eventi. |
| [`src/viralclip/twitch/telemetry.py`](../../src/viralclip/twitch/telemetry.py) | Sink rotante JSONL per CLI e client. Usa logging stdlib. |
| [`src/viralclip/windows_supervision.py`](../../src/viralclip/windows_supervision.py) | Wrapper Win32, XML, marker, log, preflight e chiamata CLI. |

## File di test

Ciascun file è consumato da pytest tramite `testpaths` e dalla verifica strict. I rimandi puntano al test effettivo. Fixture, dipendenze e limiti sono collegati nel [capitolo 24](10-TESTING-AND-RELIABILITY.md) e nell'[indice dei casi](04-CODE-WALKTHROUGH/F-TEST-REFERENCE.md).

| File | Componenti, fixture e ruolo |
| --- | --- |
| [`tests/test_audit.py`](../../tests/test_audit.py) | Regressioni M0, mock HTTP, DB/clock sintetici, cap e retry, snapshot atomici, migrazione. |
| [`tests/test_backup.py`](../../tests/test_backup.py) | SQLite WAL vera temporanea, backup e link seguito o rifiutato. |
| [`tests/test_collector.py`](../../tests/test_collector.py) | Helper clip, httpx MockTransport e SQLite, discovery e refresh di base. |
| [`tests/test_dataset.py`](../../tests/test_dataset.py) | Fixture DB e orari di confine, output su Git temporaneo, feature e outcome 2A. |
| [`tests/test_deployment.py`](../../tests/test_deployment.py) | Static unit e trasferimento SQLite/manifest sintetico. |
| [`tests/test_dual_collector_runbook.py`](../../tests/test_dual_collector_runbook.py) | Bash vero con sudo finto e matrice exit code di entrambi i collector. |
| [`tests/test_evaluation.py`](../../tests/test_evaluation.py) | Input di replay sintetico, metriche, split, conflict e gating. |
| [`tests/test_gta_vi.py`](../../tests/test_gta_vi.py) | Mock Get Games, fixture pilot, check path, ID e unit. |
| [`tests/test_health.py`](../../tests/test_health.py) | DB temporaneo, clock iniettato, severità, coverage e letture non mutanti. |
| [`tests/test_http_telemetry.py`](../../tests/test_http_telemetry.py) | Mock HTTP e handler, privacy dei messaggi, retry, retention e CLI. |
| [`tests/test_operations.py`](../../tests/test_operations.py) | DB con WAL, mock Restic/systemd/heartbeat, unit, identità e restore. |
| [`tests/test_release_packaging.py`](../../tests/test_release_packaging.py) | Git temporaneo, blob e archivi sintetici, stabilità, allowlist e corruzione. |
| [`tests/test_windows_supervision.py`](../../tests/test_windows_supervision.py) | XML, pausa, crash, avvio patchato e lock Python cross-process. |

## Percorso di studio pratico

1. Apri `pyproject.toml` e `src/viralclip/__main__.py`. Segui il collegamento a `cli._parser`. Scrivi su carta quale ramo apre SQLite in sola lettura e quale costruisce il writer.
2. In `config.py` leggi `load_settings` e confronta `.env.example` con il [registro variabili](07-INFRASTRUCTURE.md). Distingui una variabile vuota da un default nel file.
3. Apri `storage/database.py` e segui `record_clip`, `_create_jobs` e `add_scheduled_snapshot`. Confronta ogni istruzione con il diagramma ER. Disegna un job 600 pending e il link una volta completed.
4. In `collector/service.py` segui `collect_cycle → discover → _discover_window → record_clip`. Poi `collect_due_snapshots` e `due_jobs`. Per il traffico rete, entra in `twitch/client.py` da `get_clips` verso `_get`.
5. Leggi i test `test_overlapping_discovery_preserves_first_seen_and_appends_snapshots` e `test_full_http_flow_restart_and_delayed_snapshot`. Capisci quali orologi sono iniettati e quali dati appartengono alle fixture.
6. Leggi `read_health`, `online_copy`, `snapshot_manifest` e `run_backup`. Confronta due unità collector e poi due unità monitor. Individua come ciascun servizio riceve identità, configurazione e credenziali.
7. Segui `dataset.extract → read_source → candidate/outcome`. Calcola a mano due feature e la soglia di maturità. Poi `evaluation.read_inputs → _period → ranking_metrics`, e verifica con `test_evaluation.py` perché due finestre parziali non danno due giorni.
8. Chiudi con [milestone](11-CURRENT-STATUS.md), [decisioni](15-DECISION-REGISTER.md) e [roadmap](12-ROADMAP.md). Apri i runbook operativi quando serve risalire da un gate alla prova richiesta.

La tabella aggregata e il riscontro di completezza sono nel [capitolo di stato](11-CURRENT-STATUS.md#copertura-del-manuale).
