# 30. Glossario tecnico

[Indice](00-INDEX.md) · [Infrastruttura](07-INFRASTRUCTURE.md) · [Schema](06-DATABASE.md) · [Ricerca](08-DATA-PIPELINE.md)

| Termine | Significato ed esempio in ViralClip Radar |
| --- | --- |
| API | Interfaccia con operazioni e contratti per interagire fra programmi. Helix fornisce una lista pubblica di clip. |
| Endpoint | Un'operazione esposta a un indirizzo e metodo. `GET /helix/clips` legge metadati, `POST /oauth2/token` ottiene un token. |
| Helix | API Twitch da cui il collector legge clip e categorie. |
| OAuth | Meccanismo di autorizzazione. Il grant app usa credenziali dell'app per un token con scadenza, poi i GET includono Bearer e Client ID. |
| App access token | Credenziale temporanea d'app per risorse autorizzate. In ViralClip Radar è tenuta in memoria. |
| Rate limit | Budget di richieste o punti imposto dal servizio. A bucket esaurito, il collector usa reset o retry-after. |
| Backoff e jitter | Attesa crescente con componente variabile. Riduce nuovi picchi di retry, ad esempio un secondo più 0–0,25 alla prima ripetizione transitoria. |
| Paginazione e cursore | Il server fornisce parti della lista e un token per la parte seguente. Viene passato in `after` a Helix discovery. |
| Saturazione | Una finestra riceve un numero e condizioni che indicano possibile incompletezza. Il collector segnala 900 risultati e prova subdivision se ha budget. |
| Categoria / ID opaco | Identificatore Twitch trattato come stringa. V e VI hanno ID distinti anche con nomi simili. |
| Collector | Processo che scopre clip, misura e scrive dati. Ogni gioco può usare lo stesso codice e un DB distinto. |
| Discovery | Ricerca per categoria e tempo per conoscere nuovi ID e osservare quelli restituiti. |
| Refresh | Domanda delle view correnti per ID già noti. Può servire più job della stessa clip. |
| Scheduler | Logica che decide quale attività dovuta eseguire. Il loop Python prende job SQLite. Il timer systemd attiva monitor e backup separati. |
| Job | Record di lavoro identificato e riprendibile. Il target 600 di una clip può essere pending, running e completed. |
| Snapshot | Nel dominio, una misura delle visualizzazioni con ora reale. In SQLite, “snapshot di lettura” significa invece la versione consistente dei dati vista da un reader. |
| Target age ed età effettiva | Target scelto per uno snapshot pianificato e secondi realmente trascorsi dalla creazione. Target 600 può produrre età 604 e quattro secondi di ritardo. |
| Checkpoint discovery | Ultimo punto di copertura gestita per categoria, recuperato dopo riavvio. |
| Checkpoint WAL | Operazione SQLite per riversare pagine del log nel file principale. Distinta dalla riga di discovery. |
| Watermark | Limite temporale cui si attribuisce evidenza. In discovery è il bordo del checkpoint. In dataset esclude misure e maturità successive. |
| UTC | Riferimento temporale senza ora legale. Il cohort giorno raggruppa clip a partire da mezzanotte UTC. |
| Tempo monotono | Conta durata senza dipendere dalle correzioni dell'ora civile. Usato per cadenza e deadline, mentre le misure si datano in UTC. |
| Idempotenza | Ripetere una scrittura con la stessa identità evita un doppione. Ad esempio la chiave clip/timestamp/source contiene un solo snapshot. |
| Append-only | Misure già confermate non si riscrivono e non si cancellano attraverso le operazioni ordinarie. I trigger lo impongono in `clip_snapshots`. |
| SQLite | Motore DB incorporato. Il collector lavora su file locale e il reader apre una connessione propria. |
| WAL | Write-ahead log SQLite. Permette a un lettore di vedere commit precedenti mentre il writer procede. |
| SHM | Sidecar SQLite usato per coordinamento WAL locale. Non è un backup. |
| Transazione | Gruppo di operazioni confermabili insieme. Snapshot scheduled e completamento job sono nello stesso commit. |
| Commit / rollback | Rendere definitive le modifiche della transazione o scartarle. La funzione Python omonima di Git riguarda revisioni, concetto distinto. |
| Primary key | Identità univoca di riga, ad esempio `clip_id`. |
| Foreign key | Riferimento imposto fra tabelle, ad esempio snapshot di un clip ID esistente. |
| Indice | Struttura che rende più rapido trovare righe. Uno parte da `status,due_at` per i job. |
| Lock | Esclusione di accesso concorrente. Un handle `.collector.lock` limita i collector concorrenti sul path. |
| Migrazione additiva | Aggiornamento schema conservando dati esistenti. V2 aggiunge `jobs.snapshot_id`, fra gli altri. |
| Online backup | Produzione di una copia coerente da SQLite vivo, leggendo anche commit WAL pertinenti. |
| Manifest | Documento di identità e provenienza. Nel backup conserva byte/hash e metriche, nel dataset contiene regole e hash artefatti. |
| Hash SHA-256 | Impronta deterministica dei byte. Se il file cambia, il confronto col digest di riferimento fallisce. Fiducia nel riferimento resta necessaria. |
| Integrity check | Controllo SQLite della struttura interna. Foreign key check e verifiche semantiche integrano l'evidenza. |
| Restore e rehearsal | Recupero di un backup e prova separata in path isolato. Rehearsal ops verifica gioco e ricopia senza promuovere a live. |
| Restic | Tool di backup cifrato usato per upload e restore sul repository privato. |
| S3-compatible | Protocollo storage a oggetti. Un backend HTTPS privato può ospitare il repository Restic. |
| Retention e prune | Regole per conservare alcune generazioni e liberare spazio delle altre. I profili Restic devono essere indipendenti. |
| RPO e RTO | Massima perdita di dati accettabile e obiettivo di tempo per recuperare. Le copie giornaliere suggeriscono un ordine di grandezza di un giorno se funzionano. |
| Telemetria / JSONL | Eventi strutturati. Ogni riga è un oggetto JSON, ad esempio esito di un tentativo senza corpo o token. |
| P95 | Percentile 95. Il report sort dei ritardi usa la posizione `ceil(0,95n)`. |
| Heartbeat | Segnale periodico di salute verso un ricevitore. Il monitor ops invia severità, usando la route di failure per 1 o 2. |
| Coorte | Popolazione di clip selezionata con regola dichiarata, ad esempio un gioco e un giorno di creazione UTC. |
| Cutoff | Durata/istante massimo ammesso per le feature. Un'osservazione a 30m+3s non è disponibile a cutoff 30. |
| Point-in-time | Vista conforme a ciò che era misurato entro un tempo. Il builder include timestamp effettivi e ID di provenance. |
| Feature | Input numerico calcolato da quanto era disponibile, ad esempio crescita per minuto fra la prima e l'ultima misura ammesse. |
| Outcome / label | Risultato osservato destinato a valutazione o training. Qui conteggio da un job 24h valido e linkato. |
| Censura | Risultato non ancora o non pienamente osservabile. Una clip con finestra label immatura non ha valore finale in quel replay. |
| Leakage | Accesso diretto o indiretto al futuro. Usare la vista a 60m+5s come feature a 60m è un esempio. |
| Provenance | Traccia dei dati usati. `observation_ids` e coppia job/snapshot identificano le misure da cui deriva una riga. |
| Baseline | Regola di riferimento, ad esempio ordinare per `latest_views`. |
| Ranking | Ordine di candidate. Il replay confronta quattro regole su pool gioco/giorno. |
| Backtesting / replay | Applicazione di una regola alle misure storiche rispettando tempo e cutoff, confronto solo a maturità. |
| Split temporale | Partizione di train, validation e test in ordine cronologico di creazione. |
| Embargo | Intervallo per impedire che label non mature prima del prossimo split entrino nello sviluppo. Qui è richiesta tutta la finestra 24h+5m. |
| Pool matched | Intersezione degli ID eleggibili e labeled a tutti e quattro i cutoff. |
| Precision, Recall, NDCG | Precision misura la quota di suggerimenti rilevanti. Recall misura la quota dei rilevanti trovata. NDCG premia view alte nelle prime posizioni. |
| Training, tuning, test | Fit dei parametri, scelta del metodo/iperparametri nella validation, stima successiva su test separato. Fasi M3 future. |
| Inferenza | Applicazione di una funzione addestrata a nuove feature al cutoff. Ancora progettata. |
| Overfitting e generalizzazione | Imparare peculiarità del passato o ottenere qualità anche su popolazioni future. Un giorno del lancio può favorire il primo. |
| VPS / SSH | Macchina virtuale e protocollo per amministrarla. OVH Ubuntu ospitava i due servizi durante il campione registrato. |
| systemd | Supervisore e gestore servizi Linux, usa file .service e .timer. |
| Deployment | Installazione di una revisione su ambiente destinato all'uso, per esempio package ops in directory separata. |
| Preflight | Controllo di prerequisiti prima di avvio/cambio. Per GTA VI rifiuta path, ID e cadence inattesi. |
| Rollback | Ritorno di configurazione o applicazione a stato precedente. Il rollback ops-only del runbook lascia intatta la storia dati. |
| GO / NO-GO / UNKNOWN | Accettazione, vincolo negativo o prova assente. M0 ha GO storico, M1 unattended rimane aperto, stato live attuale UNKNOWN. |

Per approfondire un termine segui lo [scenario corrispondente](13-END-TO-END-EXAMPLES.md), poi il sorgente tramite le [schede](04-CODE-WALKTHROUGH/00-GUIDE.md).
