# Strumenti operativi e supervisione

[Indice delle schede](00-GUIDE.md) · [Firme](D-OPERATIONS-REFERENCE.md) · [Infrastruttura](../07-INFRASTRUCTURE.md) · [Casi restore e health](../13-END-TO-END-EXAMPLES.md)

## deployment.py

Separa condizioni dell'avvio e validazione del file trasferito dal collector. `sqlite3/closing` per read-only, `hashlib.file_digest` per SHA-256, `json` per manifest, `Path` per isolare file e sidecar, `load_settings` e `MIGRATIONS` per la preflight. `SCHEMA_VERSION=2` è un pin di operazione. `BackupIdentityError` è un ValueError specifico dell'identità. [Firme](D-OPERATIONS-REFERENCE.md#srcviralclipdeploymentpy)

| Simbolo | Contratto |
| --- | --- |
| `_open_read_only` | Path risolto → connessione URI mode=ro, timeout 2 s. |
| `_check_schema` | Connessione → None se migrazioni locali e righe corrispondono a 1 e 2. Rifiuta drift con ValueError. |
| `preflight` | Path → None su check statici dell'avvio V. Esiste, path env combacia, credenziali presenti, niente ID configurati extra, timing 300/30. Legge schema, modalità WAL/DELETE e colonna link job. |
| `_check_game_identity` | Reader e ID → verifica ID non vuoto e trimmato, una sola categoria uguale, nessuna riga fuori categoria in clip/run/checkpoint e prova di ingresso dalla raccolta. Separato da integrità tramite classe di errore. |
| `snapshot_manifest` | Path standalone e ID opzionale → dict. Rifiuta sidecar e journal diverso da DELETE; legge schema, identità se richiesta e job outstanding per stato/target, valida SQLite, calcola SHA-256 e byte. Versione 1 generica o 2 con ID. |
| `_unique_manifest_fields` | Coppie JSON → dict. Rifiuta chiavi duplicate anche dentro oggetti annidati. Chiamata da JSON loader. |
| `verify_snapshot` | DB, file manifest e ID opzionale → None. Accetta solo versione intera 1 o 2, confronta l'ID v2 con input indipendente, ricrea il manifest da sorgente e confronta contenuto canonico. Per v1 con ID controlla comunque il DB e toglie solo il campo aggiunto prima del confronto. |
| `main` | `preflight/manifest/verify` → 0 o exit 1. Stampa risultato, manifest o errore. La procedura decide gli ID approvati e la provenienza del manifest. |

Esempio. Un file copiato con un sidecar accanto viene rifiutato da `snapshot_manifest` prima ancora di calcolare il digest. Un altro con SHA congruo e righe gioco sbagliato fallisce sulla condizione indipendente. [Test trasferimento](../../../tests/test_deployment.py) · [Backup identity](../../../tests/test_operations.py)

## gta_vi.py

Adatta il collector generico al pilot senza cambiare lo scheduler. Nome esatto, ID pin, basename DB e policy 300/10 sono costanti. Usa `os.environ`, `Path`, `sqlite3`, configurazione, check schema, lettura RO, `TwitchClient` e alias collector di `cli.main`. [Firme](D-OPERATIONS-REFERENCE.md#srcviralclipgta_vipy)

| Simbolo | Input e rami |
| --- | --- |
| `_exact_match` | Lista record → ID se esattamente uno con nome esatto e ID valido, esclude espressamente `32982`. Valore inatteso → ValueError. |
| `resolve` | Client → ID coerente su due GET Games. Ripete regola exact per reverse lookup e confronta ID. Il pin locale richiede procedura di approvazione separata. |
| `_preflight` | Directory e ID → path DB. Verifica pin, credenziali, path e log, liste vuote e policy, file DB/sibling regolari e singolo link, schema v2, WAL e categorie già registrate. Rifiuta alias del percorso. Una tabella games vuota è compatibile con DB appena inizializzato. |
| `main` | Resolve con credenziali e zero retry transitori, stampa ID; preflight e run con state e pin ambientale. Run delega alla CLI collect con ID esplicito e loop. Chiude client nel ramo resolve e converte errori noti in exit 1. |

La prova offline usa MockTransport e settings sintetiche. Una verifica storica autenticata risale al 19 novembre. [Test](../../../tests/test_gta_vi.py) · [Pilot](../../GTA_VI_PILOT.md)

## operations.py

Orchestra i lavori separati. `json`, `NamedTemporaryFile` e `TemporaryDirectory` pubblicano bundle e marker. `shutil` misura capacità e `subprocess` invoca systemctl/Restic. `urllib` effettua heartbeat e filtra redirect. `deployment` verifica identità, `storage.backup` fa copia e `storage.health` riporta salute. Costanti `DB_NAME` e `MANIFEST` uniformano bundle, `COLLECTOR/BACKUP` sono unità predefinite V, `HOST/TAG` selettori storici comuni, `STAMP` regex del nome data e `GIB` riserva.

| Simbolo | Contratto e conseguenze |
| --- | --- |
| `_atomic_json` | Path e dict → file temp nello stesso parent e replace; rimuove il file temp su fallimento. I reader vedono un marker vecchio o nuovo. |
| `reserve_bytes` | Byte DB + WAL e capacità → max fra un quinto capacità e due copie + 1 GiB. |
| `_file_bytes`, `_source_bytes` | Path → dimensione, zero per sidecar mancante nel primo; il secondo richiede DB esistente e somma WAL. |
| `verify_mounts` | DB, root, flag writable backup → controlla statvfs del source/sidecar esistenti e accesso root. Prova lettura query-only WAL e max snapshot. Se writable, scrive/flush temp nella sola root. RuntimeError, OSError o errore SQLite se il probe fallisce. |
| `_http_rates` | DB e ora → riga diagnostica 1h, scorri quattro file, scarta linee/letture invalide, conta tentativi/errori/429; messaggio dedicato senza eventi. |
| `_retention` | Env e default → intero positivo; valore invalido rifiutato. |
| `_https_url` | Stringa → bool quando schema HTTPS, host presente e niente userinfo, query o fragment. Riusato per Restic e alert. |
| `_credentials_dir` | Senza parametri → path da CREDENTIALS_DIRECTORY, ValueError se mancante. |
| `_restic_environment` | Repository e tre file credenziali → dict ristretto per subprocess, rifiuta config/repo senza path o credenziale vuota. La password è passata via riferimento al file. |
| `_restic` | Argomenti e cwd opzionale → invoca binario assoluto con `--no-cache`, timeout 3.600 s. Cattura stdout/stderr, errore solo col nome del comando ed exit. |
| `_local_retention` | Root e numero da tenere → ordina cartelle con formato data. Elimina solo bundle vecchi con esattamente i due file regolari verificabili per forma e senza symlink. Non legge il loro hash qui. |
| `run_backup` | Source, root, istante, ID e Restic iniettabile → crea bundle. Registra marker locale dopo validazione e rename, esegue upload, scrive marker offsite dopo upload, poi forget/prune scoped e retention locale. Qualunque errore precedente interrompe il resto. L'ID errato viene rifiutato prima della pubblicazione. |
| `restore_latest` | Output nuovo, ID atteso, callable Restic → ripristina latest in dir isolata. Esige un solo manifest, verifica bundle e fa una seconda copia di rehearsal. Eccezioni lasciano l'output da esaminare. |
| `_service_state` | Nome unit → dizionario da `systemctl show`, timeout 10 s e exit code validato. |
| `monitor` | DB, backup root, ora, due unit e reader service → severità e righe. Combina health con 300 s fissi, HTTP, systemd, disk e freshness. Un errore nei servizi porta critical e prosegue gli altri gruppi. |
| `_NoRedirect.redirect_request` | Override del metodo urllib, ritorna None; la chiamata non segue il redirect. |
| `_heartbeat` | Severità 0–2 → POST HTTPS o no-op per file vuoto. Il corpo è un valore di `LEVELS`. Il fallimento usa eccezione al caller e viene convertito in CRITICAL. |
| `main` | Parser e dispatch backup/monitor/probe/init-remote/check-remote/restore-latest. Stampa report. Per operazioni fallite restituisce 1 con errori censurati, per monitor restituisce severità 0–2 o 2 per mancata delivery. |

Esempio. DB+WAL da 2 GiB e filesystem da 40 GiB richiedono max(8, 5) = 8 GiB liberi. Se il bundle viene verificato ma l'upload fallisce, resta `latest-local.json` aggiornato e il vecchio offsite invariato. Se upload riesce e prune fallisce, il marker offsite è già stato aggiornato e `Result` del servizio può comunque essere failure. [Test failure e retention](../../../tests/test_operations.py) · [Metriche](../07-INFRASTRUCTURE.md)

## windows_supervision.py

Fornisce preparazione offline e runtime Windows. `xml.etree` genera il task, `subprocess.list2cmdline` conserva argomenti con spazi, `threading` e `_thread` coordinano pausa, `logging` ruota lifecycle, `sqlite3` controlla il DB, `ignored_output` limita il path del template. `SCHEMA_VERSION`, namespace Task Scheduler e nome GTA V definiscono default.

| Simbolo | Contratto |
| --- | --- |
| `control_directory` | Path DB → sibling con suffisso `.viralclip-supervision`, senza aprire file. |
| `task_xml` | Python, CWD, path DB, SID, nome e timing → UTF-16 di XML. Valida forma SID, nome, positivi. Include launch di `run`. Scrittura e registrazione sono responsabilità distinte. |
| `preflight` | DB assoluto e timing approvato → controlla path/config, credenziali, niente ID extra, v2, esistenza e WAL in RO. |
| `is_paused` | Path marker → true se stat riesce, false su assenza, propaga altri OSError. |
| `supervise` | Marker, callable start/record e polling → un tentativo. Pausa già presente → 0. Avvia thread watcher, fa cleanup con due eventi di stato e `join`. Exception → 1, fine pulita inattesa → 1, pausa con fine pulita → 0, exit nonzero ereditata. Il task esterno possiede restart. |
| `supervise.monitor` | Callback thread. Attende finished o poll, verifica marker, salva pausa/errore e chiama `interrupt_main`. |
| `_run` | Path, gioco e timing → rifiuta non Win32, crea dir e rotazione, passa callback e marker a supervise. |
| `_run.record` | Evento e campi → record JSONL con timestamp UTC. |
| `_run.start` | Callback che esegue preflight. Fallisce con evento ed exit 2 o delega `collect --game … --loop` al main. |
| `main` | Risolve DB, rifiuta UNC, prepara XML in directory ignorata o esegue preflight/run/pause/resume/state. Scrive/elimina solo il marker per i controlli; restituisce 0 oppure 2 per errori comuni. |

I test usano lifecycle sintetico, monkeypatch di piattaforma e collector e un secondo processo su DB temporaneo per il lock. L'esecuzione reale del servizio Windows va verificata con gli account e i permessi effettivi. [Test Windows](../../../tests/test_windows_supervision.py) · [Runbook](../../WINDOWS_SUPERVISION.md)

## Helper Bash e Python inline

- [`deploy/dual-collector-health.sh`](../../../deploy/dual-collector-health.sh). `health_both` cattura i due esiti di `sudo -u … python -m viralclip … health` separatamente. `collector_health_result` riceve nome e exit e stampa healthy/degraded/failed. L'ultima condizione ritorna true solo per due zero. Simulazione Bash di 9 coppie di esiti in [`test_dual_collector_runbook.py`](../../../tests/test_dual_collector_runbook.py).
- [`docs/production-health-readonly.sh`](../../production-health-readonly.sh). Valida `sample|full`, legge risorse e timer, poi `audit` interroga systemd e passa gioco/account/DB/PID a `inspect_state`. `journal_summary` converte journal JSON in contatori. Python inline legge metadati, argv/env filtrati, apre WAL con timeout/progress handler, e in `inspect_db` usa `query` per leggere schema e aggregati indipendentemente. Include coverage e percentili di ritardo, legge rotazioni HTTP, cerca copie standalone in full e ne controlla header journal mode prima della query immutable. Una query SQLite fallita stampa indisponibilità e può lasciare proseguire le successive. Il processo può accedere a informazioni private internamente e stampa soltanto le proprietà selezionate.
- [`docs/phase0-inspect.sh`](../../phase0-inspect.sh). `main` accetta inventory/sample-a/sample-b con guardia su epoch start/end e ritardo minimo. `vcr_read` cattura output e rende missing un UNKNOWN. `vcr_inventory` esamina gli otto nomi attesi e gli elenchi timer/service/cron e path ops. `vcr_resources` raccoglie host load, RAM, CPU, disco e inode. `vcr_sample` invoca `vcr_game` per entrambi. `vcr_game` verifica proprietà systemd, chiama Python in account collector e ricontrolla PID e tempo di avvio.
- **Python inline di fase 0.** `emit` rende una riga in forma risultato/gioco/controllo. `utc` e `fmt` normalizzano data. `probe` verifica file e identità PID→DB tramite metadati, applica `deny_fs_writes`, apre SQLite con deadline di query, query_only e temp in RAM. `deny_fs_writes` imposta un confinamento Landlock per scritture di filesystem sui due target arch Linux; se non disponibile, il DB rimane chiuso. `inspect` verifica WAL/v2, categoria, integrità nel campione A, poi checkpoint, snapshot, run, stati job e `HEALTH_PHASE0`. B include quanti job non missed sono dovuti dall'anchor. I confronti fra campioni sono compito dell'operatore. I marker PASS/FAIL/UNKNOWN sono per check, non un unico exit code.
