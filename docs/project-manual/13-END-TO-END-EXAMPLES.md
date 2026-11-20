# 29. Otto scenari da seguire nel codice

[Indice](00-INDEX.md) · [Architettura](02-ARCHITECTURE.md) · [Raccolta](05-TWITCH-AND-COLLECTION.md) · [Pipeline](08-DATA-PIPELINE.md)

Gli ID e i conteggi qui sono sintetici. I timestamp sono UTC. Ogni caso distingue dato letto, decisione e scrittura. Il [diagramma della clip delle 14:00](02-ARCHITECTURE.md#esempio-guida-clip-creata-alle-1400-utc) collega la sequenza generale.

## A. Nuova clip

| Tempo | Chiamata e input | Decisione e risultato |
| --- | --- | --- |
| 14:00 | Twitch crea `demo-a`. Per il nostro processo è ancora ignota. | Nessun job locale. |
| 14:05:00 | `cli.main → collect_cycle → discover → _whole_minute_window`. Legge game e checkpoint. | Costruisce finestra al minuto. Prima del primo run imposta bootstrap, `create_run` scrive running. |
| 14:05:02 | `TwitchClient.get_clips` per game. `_parse_clip` normalizza ID, data e view=12. | `record_clip` legge PK, inserisce nuova clip, snapshot discovery di età 302 s e cinque job, uno commit. |
| 14:05:03 | Cursor esaurito entro cap. | `finish_run` scrive completed e contatori; `update_watermark` salva fine finestra. |
| 14:10:03 | `due_jobs` individua il target 600, `start_jobs` registra running, GET ripetuti `id`. | Ricevuto 18, `add_scheduled_snapshot` salva età 603 e collega atomicamente. Job 600 completed. |

Una risposta non valida dopo la prima pagina mantiene lo snapshot confermato e lascia il checkpoint avanzato solo rispetto a un eventuale bootstrap. Un crash interno alla transazione di `record_clip` rende impossibile lasciare la clip appena inserita senza job della stessa transazione. Se la stessa clip ritorna dopo cinque minuti, cambia last seen, si appende una misura e il primo timestamp rimane. [Collector](../../src/viralclip/collector/service.py) · [Prova overlap](../../tests/test_collector.py#L103)

## B. Prima scoperta a +45 minuti

La clip è creata alle 14:00, ma `discover` la riceve per primo alle 14:45:00, per esempio in una finestra allargata da checkpoint vecchio. Si registra una misura reale di 100 view, età 2.700 s. `_create_jobs` confronta ogni `due_at` con `first_seen_at`.

| Scadenza nominale | Stato all'INSERT e motivo |
| --- | --- |
| 14:10 e 14:30 | `missed`, scadenze raggiunte prima della prima vista. completed_at dello stato a 14:45 e nessun link. |
| 15:00, 20:00, 14:00 del giorno dopo | `pending`, scadenze future. |

A watermark sufficiente, il builder restituisce late discovery a 30/35. A 60 può usare 14:45. Se il primo scheduled arriva a 15:00:04, 65 può usare entrambi e vedere crescita, mentre 60 ha crescita null se non c'è un altro discovery utile. Se la finestra non restituisce proprio quella clip, non ci sarà né riga né job da classificare missed. [Job](../../src/viralclip/storage/database.py#L292) · [Cutoff](../../src/viralclip/dataset.py#L168)

## C. Errore Twitch

Con `Retry-After=7` e un reset tra 10 s, un 429 può portare alla pausa di 10 s se domina il backoff. `_request` registra status e ritardo, `_wait_for_retry` produce gli eventi attesa/retry, `_get` ripete il tentativo. Se il GET seguente riesce, la misura è timestampata dopo la risposta. Per quattro GET transitori falliti con default, si solleva `TwitchAPIError`.

- In **discovery**, `_discover_window` scrive error, conserva i risultati già committed e propaga. `collect_cycle` scrive un errore operativo per la categoria e può cercare le altre, ripassando poi dai job. Il checkpoint della categoria fallita non viene avanzato a fine finestra.
- In **refresh**, i job selezionati erano running. `finish_jobs` li mette failed e imposta retry_at=istante+30s. Se il terzo tentativo fallisce, non sono più selezionati. Si può comunque lavorare su batch successivi. La mancanza di un singolo ID su 200 valido segue un ramo unavailable indipendente.
- In un **401**, un rinnovo può salvare la stessa operazione. Un secondo 401 viene rifiutato. Il JSONL evita i dati del token. Se manca telemetria, lo stato dei job è ancora leggibile.

[Retry API](../../src/viralclip/twitch/client.py#L231) · [Prove mock](../../tests/test_http_telemetry.py)

## D. Riavvio con job pendenti

`demo-a` era nota alle 14:05, 10m pending e 30m pending. Alle 14:10 il vecchio processo segna running il primo job, con attempts=1. Cade prima dell'append e riparte alle 14:36. `Collector.__init__` acquisisce lock, `recover_running_jobs` segna pending il primo job e lascia pending il secondo. I run running passano a error. Nel primo `collect_due_snapshots` entrambi sono dovuti.

| Voce | Nuovo stato d'esempio alle 14:36:02 |
| --- | --- |
| Risposta Helix | Una per ID demo-a, 50 view. |
| Snapshot scheduled | Un record, età effettiva 2.162 s, target_age_seconds NULL. |
| Job 600 | completed, attempts=2, link al nuovo snapshot, 1.562 s di ritardo. |
| Job 1800 | completed, attempts=1, stesso link, 362 s di ritardo. |

Nessun record viene creato alle 14:10 o 14:30. La misura recovery può entrare a 60/65, non a 30/35, indipendentemente dal successo del job. Se il primo job aveva già tre tentativi al crash, il recovery lo lascia failed ed esaurito. [Recovery e query](../../src/viralclip/storage/database.py#L457) · [Test flusso condiviso](../../tests/test_audit.py#L100) · [Evidenza blackout](../PROJECT_HISTORY.md#2026-11-17-read-only-real-power-outage-recovery-audit)

## E. Il job a 24 ore non aggiorna bene

Per una clip creata alle 14:00, il job 86400 è due alle 14:00 del giorno seguente. `candidate` ha già calcolato feature indipendenti. `read_source` guarda lo stato a watermark maturo e `outcome` sceglie quanto si può concludere.

| Evento | Dati SQLite | Stato outcome dopo maturità |
| --- | --- | --- |
| GET 200 senza ID | Job unavailable, completamento datato e nessuno snapshot collegato. | unavailable |
| Tre tentativi falliti o processo fermo | Job failed/running/pending o mancante, nessun dato valido. | missing |
| Misura arriva alle 14:08 nel recovery | Snapshot reale + job completed, età 86.880, link coerente. | outside_window |
| Job punta a scheduled di un'altra clip | FK può essere presente, ma il join ha clip ID differente. | invalid_link |
| Misura 14:04 con view=0 e link esatto | W almeno 14:05. | valid, `views_24h=0` |
| Qualsiasi caso a W=14:04:59 | Tutta la finestra non è trascorsa. | immature |

Solo l'ultimo caso maturo con conteggio noto entra nel join se ha feature. Gli altri sono visibili in `outcomes.csv`. [Esiti e label](08-DATA-PIPELINE.md#20-quando-esiste-una-label) · [Regressioni](../../tests/test_dataset.py#L117)

## F. Clip che entra nel dataset

Scelta sintetica `Selection` con gioco 42, intervallo [20 novembre 00:00, 21 novembre 00:00), watermark 21 novembre 15:00. La clip `demo-a` è creata alle 14:00, scoperta 14:05 con 12 view e vista alle 14:23 con 48 view. Il job 24h è completed il 21 novembre alle 14:00:04, con snapshot ID 801, `job_id=505` e 450 view.

1. Il reader prende clip, misure in early window e il job 24h su SQLite RO. Gli ID early potrebbero essere 101 e 108.
2. A 30m, `candidate` scrive eligible, list `101|108`, creation/prediction e feature. Staleness 420 s, delta 36 e tasso 2/m. A 35, se non arriva una misura nuova, count e delta coincidono e la staleness passa 720 s.
3. `outcome` verifica completamento, sorgente e clip, i 4 secondi oltre due, maturo al watermark. Scrive valid con 450 view e provenance `505/801`.
4. `extract` scrive candidati, outcome, righe join, coverage, token audit, hash e manifest. Righe che condividono ID restano nello stesso split.
5. `evaluate` può consumare file hash-valid. Questa singola clip resta prova della pipeline. Le metriche richiedono pool e date minime per split. In un eventuale future training il target è 450, le feature sono quelle già disponibili al cutoff e l'ID è chiave di join, non feature.

Se il path output esiste, `ignored_output` rifiuta prima di leggere il DB. Un artefatto hash-mismatch viene escluso in `read_inputs`. [Dataset](../../src/viralclip/dataset.py) · [Evaluation](../../src/viralclip/evaluation.py)

## G. Restore del gioco sbagliato

Il profilo autorizzato deve ripristinare GTA VI. Si sceglie una directory isolata nuova e si fornisce indipendentemente `1867279146`. A causa di una configurazione incrociata `restic restore latest` deposita lì un bundle GTA V perfetto byte per byte.

1. `restore_latest` invoca il restore e trova il manifest. I byte si trovano solo nell'output di prova. Nessuna funzione sostituisce automaticamente il live.
2. Per manifest v2, `verify_snapshot` rifiuta `game_id=32982` contro l'ID approvato. Se il manifest sostiene VI ma il DB contiene V, la verifica semantica del DB rifiuta. Per manifest v1 legacy, il DB costituisce la prova di identità.
3. Il comando termina con errore. L'output resta per diagnosi e il file `rehearsal.sqlite3` viene creato solo dopo la verifica positiva. Vanno verificati scope indipendenti prima di una futura esecuzione.
4. Nel caso valido, `backup_and_verify` crea il rehearsal a parte e rilegge conteggi e link. Questo stabilisce restore verificato della copia, con RPO misurabile a partire dalle ultime osservazioni recuperate.

[Verifica manifest e identit?](../../src/viralclip/deployment.py#L136) · [Test incrociati](../../tests/test_operations.py#L161)

## H. Un collector degradato, l'altro sano

In un preflight con V in coda ritardata e VI nei limiti, le due chiamate `read_health` restituiscono 1 e 0. `health_both` riceve i due esiti separatamente, preservando exit code attraverso le liste condizionali Bash.

```text
GTA V: DEGRADED (exit 1)
GTA VI: HEALTHY (exit 0)
esito complessivo del controllo: 1
```

Entrambe le letture avvengono sui propri DB, senza scrivere SQLite. Se un `sudo` o interprete fallisce, la riga corrispondente diventa FAILED con l'exit originale. Il timer monitor, se installato, applica ulteriori check systemd/disco/backup e heartbeat per profilo. In fase 0 si registrano invece prove per controllo, incluse quelle UNKNOWN, e il rollout si tiene fermo quando un prerequisito operativo non è soddisfatto. [Script](../../deploy/dual-collector-health.sh) · [Nove coppie mock](../../tests/test_dual_collector_runbook.py#L35) · [Monitor](07-INFRASTRUCTURE.md)
