# CLI, setup, collector e client Twitch

[Indice delle schede](00-GUIDE.md) · [Firme e chiamate](A-COLLECTION-REFERENCE.md) · [Algoritmi di raccolta](../05-TWITCH-AND-COLLECTION.md)

## Pacchetto e CLI

`src/viralclip/__init__.py` esporta la versione del pacchetto. I tre `__init__.py` di collector, storage e twitch identificano i sottopacchetti. `__main__.py` chiama `main` con `SystemExit` quando si usa `python -m viralclip`. Non contengono inizializzazione di collector o DB. [Entry point](../../../src/viralclip/__main__.py) · [Package metadata](../../../pyproject.toml)

`cli.py` è uno smistatore. Importa `argparse` per la sintassi, `sqlite3` per gli errori, `sys` per stderr ed exit e `time` per cadenza monotona. `Path` serve per output. I componenti interni importati sono collector, config, dataset/evaluation, storage e client/log.

| Simbolo | Input, ritorno e rami | Collaborazione e prove |
| --- | --- | --- |
| `_parser` | Costruisce e restituisce `ArgumentParser`. `--db` globale, sottocomando richiesto. `collect` richiede esattamente una delle modalità once/loop. Dataset richiede estremi e directory, evaluate richiede directory input/output e accetta split e K. Parse o help possono terminare con `SystemExit`. | Solo struttura CLI con input impiegati nei test dataset, evaluate, health e collector. |
| `_print_status` | Riceve un `Database` già aperto. Chiede `status(utc_now())` e stampa path, conteggi, ultimo run e messaggio. Ritorna implicitamente None. | `Database.status`, `test_status_cli_without_credentials`. |
| `main` | Riceve argv o process args. Evaluate prima della config, dataset e health prima del writer. Config invalida/cred mancanti/categorie mancanti → 2. Dataset/evaluate errori catturati → 1, report concluso → 0 anche se `INSUFFICIENT DATA`. Health restituisce severità. Nel ramo writer apre DB, può completare init/status subito oppure aprire log, HTTP e Collector. Once un ciclo, loop snapshot fra discovery, cattura TwitchAPIError nel loop e riprova. Ctrl+C 0 con cleanup, TwitchAPIError o ValueError esterno 1, `Database.close` nel finally. Errori SQLite di apertura sono fuori da quella gestione. | Usata dallo script installato, da `__main__`, da GTA VI e supervisor Windows. I test patchano orologio, client, config e cassette HTTP. |

Esempio. Per argv `["--db", "demo.sqlite3", "health"]`, il path nuovo prevale sul default. Il lettore tenta una URI mode=ro, quindi il path mancante dà 2 e non crea il file. La stessa forma con `status` passa a `Database` e può creare o migrare. [CLI](../../../src/viralclip/cli.py) · [Health test](../../../tests/test_health.py) · [Audit test](../../../tests/test_audit.py)

## Configurazione

`Settings` è una dataclass congelata. Contiene ID/secret opzionali, path, intervallo/ampiezza, due tuple indipendenti di categorie e directory log opzionale. `has_twitch_credentials` torna il booleano di entrambi i campi, senza fare HTTP. `_positive_int` riceve il nome env e il default, legge con `os.getenv`, usa default per blank, rifiuta non intero e ≤0 con ValueError. `_csv_values` trasforma stringa separata da virgole in tupla di valori non vuoti e trimmati. `load_settings` chiama `load_dotenv`, poi costruisce l'oggetto con default 300 s, 30m e `data/viralclip.sqlite3`. Una configurazione `VIRALCLIP_GAME_IDS="42, ,43"` produce `("42","43")`. CLI e preflight riusano questo base loader ma applicano controlli diversi. [Config](../../../src/viralclip/config.py) · [Prova ambiente](../../../tests/test_collector.py#L68) · [Tabella variabili](../07-INFRASTRUCTURE.md)

## Collector

`Collector` conserva database, client Twitch, lookback e funzione clock iniettata. `datetime` e `timedelta` esprimono orari/età, `Callable` descrive l'interfaccia clock, `TwitchAPIError` delimita i fallimenti gestiti. Le responsabilità dei metodi sono distribuite per separare acquisizione, pianificazione e persistenza e rendere possibile una prova con clock e trasporto mock.

| Metodo | Percorso tecnico, risorse ed effetti |
| --- | --- |
| `__init__` | Riceve oggetto DB e client, lookback e clock. Acquisisce lock esclusivo e recupera run/job prima delle prime richieste. Un altro collector o un errore storage impedisce la costruzione. |
| `resolve_game` | Nome → ID. Legge cache (30 giorni) in `games`. Se scaduta, chiama search e prende primo match casefold esatto. Un match aggiorna cache, assenza genera `TwitchAPIError`. |
| `_whole_minute_window` | ID e ora → coppia di datetime UTC al minuto. Legge il checkpoint, amplia indietro con il minimo fra lookback e watermark meno 5 minuti. |
| `discover` | ID → numero di nuove clip confermate. Salva bootstrap se mancante, invoca `_discover_window` con lista budget mutabile, riscrive watermark solo su complete. |
| `_discover_window` | ID, begin/end e riferimento a budget → `(nuove, completa)`. Apre run, preleva pagine e processa ogni clip, registra contatori/cursore, marca partial e suddivide se serve, ritorna AND dei due figli. Ogni eccezione tenta di chiudere run con errore e propaga. |
| `_parse_clip` | Dict API → dict normalizzata con ID, data UTC, view count e metadati. Valida tipo rigoroso del conteggio, ID non vuoto, data timezone-aware, durata convertibile. Errori Key/Type/Value → errore Twitch generico. |
| `collect_due_snapshots` | Una lettura job al clock presente. Raggruppa per ID, segna running e fa GET sino a 100 ID a batch. Esito di rete/payload fallito marca failed il batch. Per risultato valido, associa per ID e usa clock dopo la risposta. ID non presente → unavailable. Parse o età invalida per singola clip → failed. `add_scheduled_snapshot` lega i job riusciti. Ritorna numero job completati, eventualmente maggiore del numero snapshot. |
| `collect_cycle` | Tuple di nomi e ID → None. Passa prima dai job, poi per ogni nome prova resolve/discover, per ID registra seed se nuovo. Registra errori Twitch delle categorie, continua le altre, ripassa dai job e può rilanciare l'errore raccolto. |

Estratto breve, nell'ordine in cui agisce la funzione. [Righe discovery](../../../src/viralclip/collector/service.py#L77)

```python
self.collect_due_snapshots()
requests += 1
budget[0] -= 1
```

La prima riga concede lavoro prioritario ai refresh. La seconda conta una richiesta logica discovery. La terza consuma il budget condiviso anche se la richiesta che segue fallisce. Con budget 11 residuo e sinistra di 8 pagine, alla destra rimangono al massimo 3. I test riproducono page failure, saturazione, clock per pagina, recovery, job esauriti e isolamento del fallimento di una categoria. [Audit](../../../tests/test_audit.py) · [Collector](../../../tests/test_collector.py)

## Client HTTP

`TwitchAPIError` è un `RuntimeError` di dominio destinato a messaggi operativi sanificati. `TwitchClient` possiede ID/secret, client HTTP o client iniettato, callable per sleep, jitter, wall clock ed eventi, contatore max retry, token e scadenze. Usa `httpx` per rete, `random` e `time` per backoff, parser date header e `math.isfinite` per telemetria. Le URL fisse sono Helix e token endpoint. [Firme complete](A-COLLECTION-REFERENCE.md#srcviralcliptwitchclientpy)

| Simbolo | Input → uscita, comportamento e failure |
| --- | --- |
| `__init__`, `close` | Imposta dipendenze, stato token e rate limit iniziale. Default HTTP ha timeout e User-Agent. Solo il client creato internamente viene chiuso. Un client iniettato resta proprietà del chiamante. |
| `_event` | Tipo, endpoint simbolico e campi → sink opzionale. Un'eccezione sink viene assorbita e non cambia risultato HTTP. |
| `_network_reason` | Eccezione httpx → `timeout` oppure `network_error`. Usata in eventi richiesta e retry. |
| `_request` | Endpoint/attempt, callable HTTP, URL e kwargs → Response o eccezione rete propagata. Senza eventi chiama direttamente send. Con eventi misura durata perf_counter, registra status e header numerici limitati o label di header invalido. |
| `_wait_for_retry` | Calcola delay con `_retry_delay`, emette evento retry, emette rate_limit_wait su 429 e chiama sleep. Ritorna None. |
| `_get_token` | Con force false, token ancora a più di 60 s dalla scadenza → quello cached. Altrimenti registra tentativo iniziale, expiry o unauthorized e propaga successo/fallimento di `_request_token`. |
| `_request_token` | POST form client credentials, retry 429/5xx/rete delimitato, altri status non 200 falliscono immediatamente. Valida JSON con token stringa e scadenza intera positiva, aggiorna token, expiry e validation reset, restituisce il token. |
| `_validate_token` | Token → None. Se validato da meno di 3600 s salta. GET validate con retry transitori, status non 200 invalida cache, JSON client ID errato rifiutato. Con successo salva timestamp. |
| `_retry_delay` | Response o None e indice → secondi. Esponenziale limitato più jitter. Su 429 prende il massimo fra base, retry-after e reset parseabili. |
| `_get` | Path, parametri ed endpoint logico → dict. Ottiene/valida token, rispetta reset, tenta GET. Un primo 401 forza rinnovo e validazione; 429/5xx/rete consumano retry; altri 4xx o JSON non oggetto danno errore di dominio. |
| `get_games` | Nome oppure ID esclusivi → lista `data`, altrimenti ValueError. Usato da `gta_vi.resolve`, utile per verificare la categoria senza ricercare clip. |
| `search_categories` | Nome → lista di pagine accumulate. Pagine con ID e nome di tipo corretto, fino a exact casefold, fine cursor o errore dopo 10 pagine. |
| `parse_data`, `parse_cursor` | Payload → lista di dict o cursore/None. Forma sbagliata → `TwitchAPIError`. Un pagination mancante/{} o cursore vuoto indica fine. |
| `get_clips` | Modalità categoria con datetime aware opzionali e cursor o batch non vuoto ≤100 ID. Costruisce parametri e chiama `_get` col nome logico appropriato. Selettori invalidi → ValueError prima della rete. |

Esempio. Una serie GET `500 → 401 → 200` produce un retry transitorio con backoff, un refresh/validate senza consumare il budget transitorio e un risultato finale. Il conteggio tentativi del log include anche le nuove chiamate OAuth. L'orologio di backoff è iniettato nei test. [Test autenticazione e retry](../../../tests/test_collector.py) · [Test telemetria](../../../tests/test_http_telemetry.py)

## Telemetria JSONL

`HttpEventLog` è il sink callable della CLI. Usa `logging`, handler rotante, Path, time UTC e JSON. `__init__` salva path e directory senza aprire file. `__call__` ritorna subito con `off`, altrimenti apre lazily il file `db.name.http.jsonl` in parent DB o directory configurata. Scrive un record per evento con `timestamp` UTC e campi controllati dal client, JSON compatto e non NaN. Usa massimo 5 MiB e tre copie rotate. `close` chiude l'handler se creato e assorbe errori di chiusura. `_QuietRotatingHandler.handleError(record)` evita dump standard del record o traceback in caso di errore di scrittura. La formula di aggregazione dell'ultima ora appartiene a `operations._http_rates`. Il sink fallibile è isolato dall'HTTP, quindi una serie di HTTP riuscite può non comparire in un'ora di log. [Writer JSONL](../../../src/viralclip/twitch/telemetry.py) · [Rotation ed esclusione segreti](../../../tests/test_http_telemetry.py)
