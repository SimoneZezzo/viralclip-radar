# Storage SQLite, backup e salute

[Indice delle schede](00-GUIDE.md) · [Firme e riferimenti](B-STORAGE-REFERENCE.md) · [Schema ER e transazioni](../06-DATABASE.md) · [Monitor](../07-INFRASTRUCTURE.md)

## database.py

È il lato writer del progetto. Importa `sqlite3` per la connessione, `Path` per file e lock, `contextmanager`/`Iterator` per delimitare transazioni, `datetime` per UTC/età. I target sono 600, 1.800, 3.600, 21.600, 86.400 s. `MIGRATIONS` contiene due script SQL. `Database` conserva `path`, `connection` con righe nominate e un handle lock opzionale. Il suo costruttore apre, imposta PRAGMA e migra. Chi lo possiede lo chiude. [Classi e firme](B-STORAGE-REFERENCE.md#srcviralclipstoragedatabasepy)

| Funzione o metodo | Parametri, ritorno e lavoro svolto |
| --- | --- |
| `utc_now` | Restituisce datetime UTC aware di sistema. Usato da CLI, health, migrazione e clock di default del collector. |
| `to_utc_iso` | Datetime aware → stringa UTC a microsecondi con Z. ValueError per data naive. Output usato in SQL/artefatti. |
| `parse_utc` | Stringa ISO con offset → datetime UTC. Aggiustamenti e confronti eseguiti dopo normalizzazione. |
| `Database.__init__` | Riceve string/Path, supporta `:memory:` senza directory. Crea il parent per file, apre a 30 s, attiva row_factory, FK, WAL e busy timeout, quindi migrate. Le eccezioni SQLite possono propagare prima che il caller possieda il DB. |
| `acquire_collector_lock` | Nessun dato extra. Riutilizza lock acquisito e salta in memory. Apre file sidecar del path risolto, inizializza byte su Windows, prende `LK_NBLCK` o flock non bloccante. Se il locking fallisce chiude e alza ValueError. L'apertura del file fuori dal blocco può invece propagare OSError. |
| `close` | Chiude connessione e poi handle collector, rilasciando OS lock. |
| `transaction` | Context manager, produce la stessa connessione. Commit/rollback sono delegati al context manager SQLite. Non crea un savepoint per ogni chiamata nidificata. |
| `migrate` | Crea registro se manca, legge versione massima. Per ciascuna versione mancante, DDL e timestamp in una transazione esplicita. Rollback SQLite in caso d'errore. |
| `upsert_game` | ID, nome e ora → INSERT o update su PK; memorizza str(ID) e timestamp. |
| `cached_game` | Nome case-insensitive, max age e ora → prima riga se età minore del limite; None se assente o scaduta. Usato dalla risoluzione. |
| `record_clip` | Clip normalizzata, gioco, tempo e run → boolean nuova clip. Rifiuta osservazione prima della creazione. Legge esistenza, upsert metadati, append discovery e crea job se nuova nella stessa transazione. Preserva creazione e prima vista stabili in caso di conflitto. |
| `_create_jobs` | Static method con conn, clip, creazione e prima vista. Inserisce i cinque target, ignorando conflitti. Se `due <= first_seen` marca missed e scrive motivo e orario; altrimenti pending. |
| `create_run` | Gioco, finestra e istante inizio → INSERT running e ID riga. |
| `finish_run` | Run, fine, contatori, flag, errore e unique → UPDATE; sceglie error se c'è errore, partial se troncato, altrimenti completed. |
| `update_watermark` | Gioco e data → upsert del checkpoint. La condizione per chiamarlo appartiene a `discover`. |
| `record_error` | UTC e messaggio → append in `operational_errors`. |
| `due_jobs` | Ora e limite, default 1.000 → lista righe job e ora di creazione della clip, solo pending/failed dovuti, con retry consentito e <3 attempts. |
| `start_jobs` | Lista ID, vuota → no-op. Per gli ID scrive running e incrementa attempts, prima del tentativo di rete. |
| `finish_jobs` | Lista, stato, orario ed errore → update su stato e campi. Failed salva next retry a +30s. Lo schema rifiuta uno stato non ammesso. |
| `add_scheduled_snapshot` | Clip ID, osservazione, conteggio, target singolo o nullo e ID job opzionali → append idempotente e link. Cerca creazione, rifiuta ID sconosciuto o età negativa. Recupera lo snapshot esistente per chiave e aggiorna tutti i job richiesti nella stessa transazione. Il collector garantisce la relazione degli ID in ingresso. |
| `recover_running_jobs` | Aggiorna run e job running. Run error interrotto, job pending con attempts <3 altrimenti failed. Il contatore non viene azzerato. |
| `status` e `status.table_count` | Ora → dict di conteggi, latest success, ultimi errori da tre origini in UNION e job dovuti. Il helper locale conta solo nomi di tabella definiti nel codice. Questa query due ignora backoff `retry_at`, che è rispettato da `due_jobs`. |

Esempio tecnico. Dopo `start_jobs([501, 502])` la transazione è già confermata. Se il processo muore dopo il GET ma prima dell'append, il DB contiene due running e nessuna misura. Il nuovo collector li riprende secondo attempts. Se muore dopo la transazione di append, i due link sono già completed e la coda li esclude. Il trigger append-only impedisce di correggere retroattivamente il conteggio. [Regressioni atomicità e riavvio](../../../tests/test_audit.py) · [Matrice](../10-TESTING-AND-RELIABILITY.md)

## backup.py

Il backup usa l'API `sqlite3.Connection.backup` e una connessione separata. `closing` chiude anche se fallisce la verifica. Timestamp e timer della copia usano clock monotono dove conta la durata. `TemporaryDirectory` isola il drill. `argparse` e JSON espongono l'helper operativo. [Firme](B-STORAGE-REFERENCE.md#srcviralclipstoragebackuppy)

| Simbolo | Flusso e failure |
| --- | --- |
| `_reader` | Path → connessione URI RO con timeout 2 s, generata dal path risolto. Il caller imposta query_only. |
| `online_copy` | Source e destinazione nuova → None. Apre reader, crea parent e riserva target con `touch(exist_ok=False)`. Backup a 128 pagine con pausa 50 ms tra tentativi SQLite, passa callback deadline e richiede modalità DELETE sul target. SQLite/OSError/ValueError nel blocco rimuovono il target appena riservato. |
| `online_copy.check_deadline` | Status/progress callback → no return oppure TimeoutError se oltre 60 s prima di SQLITE_DONE. Riceve anche pagine rimanenti e totali senza usarle. |
| `validate` | Path → dizionario di metriche. Read transaction, integrità, FK, conteggi, coerenza job completed, snapshot orfani e cinque scadenze. ValueError su invarianti violate e sqlite3.Error su schema/lettura. Include ultima discovery riuscita via `collection_runs`, ultima osservazione e conteggi 24h. |
| `backup_and_verify` | Copia e valida destination, seconda copia in temp e stesse metriche. Ritorna metriche base, alza errore se mismatch. |
| `main` | CLI con destinazione e `--source` opzionale, altrimenti settings. Stampa JSON e verdetto. Fallimento comune usa exit 1. Il path è esclusivo; la dicitura “ignored” nell'help non è una verifica Git. |

Tre prove costruiscono un WAL con writer sintetico e transazione non committed, impediscono la sovrascrittura anche con alias source, e rifiutano un job completed incoerente. I test deployment e operations riusano il vero verificatore sul clone temporaneo. [Test backup](../../../tests/test_backup.py) · [Test operations](../../../tests/test_operations.py)

## health.py

Organizza un report dalla stessa lettura SQLite. Importa UTC/helper storage, `median` e `ceil` per lateness, `defaultdict` per gruppi e `closing` per cleanup. Le costanti rappresentano severità 0–2, l'ora recente e i tre primi target. Mantiene `lines` e `alerts` come liste mutabili condivise fra gli helper di una lettura.

| Funzione | Input → output e rami |
| --- | --- |
| `_age` | Ora e timestamp → età in secondi, ValueError su futuro. |
| `_discovery` | Connessione, ora, inizio ora, periodo e liste → append di dettagli globali e per categoria. Join giochi, run e checkpoint. Alert assenza/staleness/errori/incomplete irrisolte. |
| `_jobs` | Connessione, ora, cutoff e liste → raggruppa stati, massimo overdue, failed/esauriti e date non parseabili. Alert a 5m e 15m o sui failure. |
| `_observations` | Connessione, tempo, bounds e liste → verifica link recenti, calcola lateness mediana/P95 per target, poi coverage a 10/30/60. Date/link incoerenti propagano a read_health, P95 elevato degrada. |
| `read_health` | Path e interval, now override → `(severity, lines)`. Apre RO senza inizializzare. Fissa snapshot, clock, count, chiama tre helper e conta errori di tipo sanificato. Read o strumenti dati invalidi restituiscono critical senza dump SQL. |

Esempio. Tre job di uno stesso target con ritardo 2, 6 e 310 secondi danno mediana 6 e P95 alla posizione 3, cioè 310. Il report degrada anche se la coda corrente è vuota. `test_late_observation_p95_can_degrade_without_backlog` verifica il principio. [Soglie e monitor esteso](../07-INFRASTRUCTURE.md#16-monitorare-significa-misurare-progressi-e-ritardi) · [Test](../../../tests/test_health.py)
