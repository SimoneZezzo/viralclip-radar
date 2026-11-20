# 15–17. Infrastruttura e operatività

[Indice](00-INDEX.md) · [Backup e database](06-DATABASE.md) · [Schede operative](04-CODE-WALKTHROUGH/04-OPERATIONS.md) · [Stato](11-CURRENT-STATUS.md)

## 15. PC, VPS e processi separati

Una VPS è un sistema Linux virtuale in esecuzione presso il provider. Ha CPU, RAM e storage assegnati e continua a funzionare quando il PC dell'operatore si spegne. SSH è il canale amministrativo per una shell remota. Autenticazione SSH e chiavi sono separate dalle credenziali Twitch e offsite. systemd, avviato dal sistema, è il supervisore dei processi e delle attivazioni temporizzate. Un servizio abilitato viene agganciato al target di boot previsto. Uno attivo può essere disabilitato al boot. Chiudere SSH lascia un servizio systemd attivo, perché non è figlio di quella shell. La disponibilità a reboot dipende anche dal marker, dal preflight e dalla rete, oltre che da enable. [Procedura Ubuntu e cutover](../OVHCLOUD_CUTOVER.md)

| Risorsa dichiarata | GTA V | GTA VI |
| --- | --- | --- |
| Account e gruppo | `viralclip` | `viralclip-gta-vi` |
| Unità collector | `viralclip-collector.service` | `viralclip-gta-vi.service` |
| Codice e interpreter | `/opt/viralclip-radar/.venv/bin/python` | `/opt/viralclip-gta-vi/.venv/bin/python` |
| Directory di stato e SQLite | `/var/lib/viralclip-radar/viralclip.sqlite3` | `/var/lib/viralclip-gta-vi/gta-vi.sqlite3` |
| Config e marker | `/etc/viralclip/collector.env`, `production-authorized` sotto `/etc/viralclip` | `/etc/viralclip/gta-vi.env`, `gta-vi-authorized` |
| Discovery nominale | 300 s, 30m, nome GTA V alla CLI | 300 s, 10m, ID pin via wrapper |
| Policy processo | Restart on failure dopo 15 s, burst 5 su 300 s | Restart on failure dopo 30 s, burst 3 su 300 s, CPU 35%, I/O weight 20, memory high 256M e max 512M, nice 10 |
| Backup e monitor | Prefisso `viralclip-`, backup 03:30 UTC | Prefisso `viralclip-gta-vi-`, backup 04:15 UTC |
| Ops e credenziali | Codice `/opt/viralclip-ops`, profilo `/etc/viralclip/ops` | Codice ops comune, profilo `/etc/viralclip/gta-vi-ops` |
| Output | JSONL nei dati, stdout/stderr collector nel journal | JSONL separato, stdout/stderr collector nel journal |

Le due unità collector chiedono `network-online.target`, che ordina lo startup ma non assicura connettività Twitch. Usano `Type=exec`, un utente non root, directory stato 0700 e umask 0077, `PYTHON_DOTENV_DISABLED=1`, protezioni dei mount e privilegi ridotti. Su stop usano SIGINT con attesa fino a 120 s. GTA V ha `ExecStartPre` con la verifica di schema e configurazione, GTA VI chiama il preflight nel wrapper. Gli ops sono oneshot indipendenti: backup con budget fino a 2h15, I/O idle, directory locale di backup writable in unità dedicata e sorgente montata RO. I due monitor hanno timeout 60 s, si attivano ogni cinque minuti con accuratezza 20 s. I timer giornalieri backup sono `Persistent=true`. Il repository documenta i file modello. La configurazione realmente caricata e i drop-in vanno verificati a parte. [Unità e timer](../../deploy)

Un virtualenv isola l'interprete e le librerie. uv installa il lock, che è una lista ripetibile di versioni e artefatti per i Python e le piattaforme compatibili. La CLI installata e `python -m viralclip` chiamano lo stesso `main`. Il PC Windows supporta uso manuale. Il supervisore Windows genera XML UTF-16 con task disabilitato, trigger boot +30 s, least privilege, credenziale account in Task Scheduler, `IgnoreNew`, esecuzione senza timeout di durata e tre retry a un minuto. `run` è Win32-only. Una directory accanto al DB contiene marker `pause` e `lifecycle.jsonl`, ruotato a 512 KiB più due backup. Un watcher rileva il marker e interrompe il main perché si chiuda ordinatamente. `resume` rimuove il marker e il prossimo avvio resta al supervisore o all'operatore. La prova di registrazione, logon non interattivo e boot non è nell'evidenza disponibile. [Windows supervision](../WINDOWS_SUPERVISION.md) · [Implementazione](../../src/viralclip/windows_supervision.py)

### Variabili e confini

| Nome | Ruolo e precedenza |
| --- | --- |
| `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` | Campi per token app. La presenza viene controllata prima delle chiamate, l'autenticità da Twitch. |
| `VIRALCLIP_DB_PATH` | Path SQLite, default `data/viralclip.sqlite3`. CLI `--db` lo sostituisce con path espanso. |
| `VIRALCLIP_GAMES`, `VIRALCLIP_GAME_IDS` | Liste separate da virgola con trim. Ogni lista è sostituita dalla corrispondente opzione se presente. Passare `--game` non azzera automaticamente una lista di ID ambientale. La GTA V nel template locale è un esempio, mentre nel codice le liste vuote rimangono vuote. |
| `DISCOVERY_INTERVAL_SECONDS`, `DISCOVERY_LOOKBACK_MINUTES` | Interi positivi, default 300/30, configurazione pilot VI 300/10. |
| `VIRALCLIP_HTTP_LOG_DIR` | In assenza usa parent DB. `off` disattiva. Monitor ops legge la retention accanto al DB. |
| `PYTHON_DOTENV_DISABLED` | Nelle unità vale 1 per caricare solo l'ambiente configurato. Localmente `load_dotenv` offre default da `.env` senza override di variabili presenti. |
| `VIRALCLIP_GTA_VI_GAME_ID` | Pin approvato per il wrapper VI, obbligatorio per run/preflight. |
| `RESTIC_REPOSITORY`, `AWS_DEFAULT_REGION` | Repository privato `s3:https://…` con path e senza userinfo/query/fragment, regione con default `us-east-1`. |
| `VIRALCLIP_LOCAL_KEEP`, `VIRALCLIP_REMOTE_DAILY`, `VIRALCLIP_REMOTE_WEEKLY` | Retention positive, default 2 copie, 7 daily e 4 weekly, con periodi potenzialmente sovrapposti. |
| `CREDENTIALS_DIRECTORY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `RESTIC_PASSWORD_FILE` | systemd consegna file distinti di access key, secret key e password. Il wrapper costruisce un ambiente ristretto al subprocess Restic con queste variabili. `alert-url` è un quarto file distinto per il monitor. |

[Template locale](../../.env.example) · [Config](../../src/viralclip/config.py) · [Configurazioni operative](../../deploy) · [Wrapper credenziali](../../src/viralclip/operations.py)

## 16. Monitorare significa misurare progressi e ritardi

`health` apre un read SQLite consistente. La severità è il massimo fra i segnali. Exit `0/1/2` mappano `HEALTHY/DEGRADED/CRITICAL`. Le soglie operative sono hardcoded eccetto la cadenza passata alla funzione. Le percentuali di early coverage e HTTP sono diagnostiche. [Funzioni](../../src/viralclip/storage/health.py) · [Test](../../tests/test_health.py)

| Riga o segnale | Fonte e calcolo | Soglia o lettura |
| --- | --- | --- |
| `Checked at`, `Total clips/observations` | Clock dopo la prima SELECT, contatori delle due tabelle. | Un incremento fra campioni dimostra avanzamento delle misure. Da solo il volume non misura copertura. |
| `Last successful discovery` e per categoria | Ultimo `finished_at` di run completed, non troncato e senza errore, checkpoint, conteggi 1h complete, partial, troncati, error e incomplete oltre checkpoint, più running. | Missing o assenza giochi → degraded. Più vecchio fra ultimo successo e checkpoint oltre max(600,2×intervallo) → degraded, oltre max(1800,6×intervallo) → critical. Errori recenti o incomplete oltre watermark → degraded. |
| `Jobs`, `Overdue jobs` | Totali per stato. Overdue = pending/running/failed con scadenza raggiunta, età = ora−min(due_at). | Oltre 300 s o failure → degraded. Oltre 900 s o almeno un failed esaurito → critical. |
| `Missed at discovery`, `unavailable in refresh` | Stati terminali e failed, con tentativi esauriti separati. | Misura i tipi di attrito. Un missing a 10m non contiene una view. |
| `Scheduled observation lateness` | Ultima ora, completed con link coerente, `observed_at−due_at`. Mediana e P95 nearest rank, posizione `ceil(0,95n)`. | P95 >300 s → degraded per ogni target. Nessun campione mostra `no samples`. Un link malformato genera critical. |
| `Early coverage` | Su tutti i job 10/30/60 già dovuti, quota con almeno una misura nell'intervallo creato–due incluso. | Informativo. Può mostrare copertura con discovery anche quando il job esatto è mancato. |
| `Operational errors` | Righe ultime 1h, fino a cinque riepiloghi con orario e categoria da pattern SQL. | Una o più → degraded. Il report restituisce solo le categorie. |
| `Operations health` | Parte da `read_health(path, 300)` e aggrega controlli runtime. | Collector non active/running/PID>0, errori di status o lettura disk → critical. Tentativo backup fallito → degraded. |
| `Storage` | Spazio libero e capacità, dimensioni SQLite + WAL. | <10% → critical. Sotto `max(capacità/5, 2×(DB+WAL)+1 GiB)` → degraded. Monitor misura filesystem del DB, backup usa filesystem di destinazione. |
| `HTTP retained last hour` | File attivo e .1/.2/.3 in parent DB, eventi `http_request` nell'ora, errori se status nullo o ≥400, conta 429. | Solo diagnostica. Include tentativi e non richieste logiche. File assenti o non leggibili possono ridurre il denominatore. |
| `Last local/offsite backup` | Marker ISO e nome bundle conforme, controllo presenza DB+manifest per locale. | Missing/invalid/futuro o età >48h → critical. >30h → degraded. La prova restore è separata. |
| Heartbeat | Credential file privato, POST HTTPS con solo severità, uso base se sana o `/fail` altrimenti. Redirect rifiutati. | Stringa vuota disattiva. Errore di consegna rende il comando critical. Una conferma esterna di failure/recovery richiede verifica. |

### Esempi storici, aggregati e attribuzione

Il 18 novembre su Windows, in M1B, il registro riporta alle 21:35:36 Europe/Rome **HEALTHY**, 7 overdue con massimo 4,7 s e zero failed. Il primo valore conferma nessun superamento delle soglie. Il secondo mostra un piccolo arretrato e il massimo descrive il ritardo del job più vecchio. Alle 21:45:13 riporta zero overdue, 22.842 clip, 204.216 osservazioni e ultima discovery riuscita alle 21:45:06.672865. Il totale delle osservazioni include discovery e scheduled. Nello stesso intervallo la telemetria registrò 134 tentativi HTTP 200 e due eventi lifecycle OAuth, senza 429 o rinnovo live osservato. [Rollout 1B](../PROJECT_HISTORY.md#2026-11-18-milestone-1b-controlled-rollout-verified-go)

Nei due report operatori su OVH del 19 novembre, circa 18:09 e 18:13 UTC, GTA V passa da 320.860 a 321.180 osservazioni e GTA VI da 64.026 a 66.117. Entrambi fanno avanzare checkpoint e completano un nuovo run. PIDs distinti e invariati nell'intervallo indicano continuità di quei servizi. Dati di integrità e categoria danno una prova indipendente dai contatori. I campioni raccontano una finestra di quattro minuti e le unità operations attese risultavano assenti. I valori sono trascrizioni aggregate dal registro. [Fonte dei campioni](../PROJECT_HISTORY.md#2026-11-19-operator-production-evidence-and-milestone-1-release-review)

## 17. Runbook e prove attese

Il cutover originario usa staging, verifica di capacità, stop ordinato del writer Windows, snapshot finale via SQLite, trasferimento con manifest, avvio su Linux, check di bilanciamento e rollback. Le unità attuali permettono un aggiornamento operations-only indipendente dal cambio collector. Il percorso [M1 attivo](../MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline) è distinto sia dal [cutover](../OVHCLOUD_CUTOVER.md) sia dal [rollout storico della telemetria](../HTTP_TELEMETRY_ROLLOUT.md).

| Fase M1 | Procedura e prova richiesta |
| --- | --- |
| 0 | Inventaria servizi, timer, candidati cron e capacità. Verifica hash/sintassi dello script standalone. Due campioni UTC almeno 6 min dalla fine di A. PIDs, timestamp di avvio, relazione PID–DB e device/inode distinti e stabili. Attese categorie, zero violazioni e progressione di discovery e refresh. Un lavoro non dovuto lascia il refresh UNKNOWN. Stabilire la revisione con ricevuta verificabile. |
| 1–2 | Copie online separate con namespace e destinazioni nuove. Manifest pin per gioco, copia privata off-VPS e verifica di entrambe. Pacchetto da commit Git approvato e digest prima dell'upload. |
| 3–5 | Configurare due profili privati con valori fuori Git, installare codice ops separato, verifica di systemd/sandbox dove previsto. Confermare prefissi, repository ID, scope provider e profili Restic distinti prima del primo prune. `HOST` e `TAG` sono uguali per compatibilità legacy. L'attuale CLI non impone lei stessa l'indipendenza fra repository. |
| 6 | Installare otto file operations e verificare probe nei mount reali e backup iniziali. Le unità sono indipendenti dai collector. Main DB, WAL e SHM devono essere RO nell'ops e solo la directory backup writable per il backup. |
| 7 | Restore offsite in cartelle nuove, verifica SHA e identità, integrità e watermark. Verifica monitor e consegna di failure/recovery per entrambi. |
| 8 | Attivazione timer dopo i gate, con esecuzione da timer oltre alle prove manuali. Decisione GTA VI al boot e prova di recovery separatamente autorizzate. |
| 9 | Rollback prima installazione di sole unità operations, con conservazione di file e copie per diagnosi. Stessi PID e inode, progressione controllata. Un incidente DB ha un runbook distinto con writer escluso, preservazione di live main/WAL/SHM e decisione sulle perdite. |

[Acceptance e rischio](../MILESTONE_1_ROLLOUT.md#acceptance-and-risk) · [Backup e monitor](../BACKUP_AND_MONITORING.md)

`dual-collector-health.sh` cattura ogni exit code mediante `|| rc=$?` sotto `set -eu`. Stampa sempre le due righe, purché le invocazioni possano terminare, e torna 0 solo con entrambe sane. Il problema confermato in precedenza era che un 1 fermava il primo controllo prima di ottenere il risultato del secondo. Per restore, un backup valido per l'altro gioco poteva essere internamente coerente. La verifica attuale aggiunge ID separato e righe coerenti nel DB. I test coprono le regressioni. [Helper](../../deploy/dual-collector-health.sh) · [Test Bash](../../tests/test_dual_collector_runbook.py) · [Test restore](../../tests/test_operations.py)

`production-health-readonly.sh` è l'helper di audit storico, con due profili e dettaglio su systemd, file, processi, journal, HTTP e SQLite. Può leggere `/proc/PID/environ` per confronti booleani e applica una allowlist a argv. Il nuovo `phase0-inspect.sh` nella working copy usa aggregati e metadati di PID, rifiuta alias, richiede sidecar esistenti e confinamento Landlock prima di aprire SQLite, separa inventario da A/B e rende espliciti gli UNKNOWN. Usa una definizione propria `HEALTH_PHASE0` centrata su 600/300 secondi, errore e coda, senza calcolare P95, SQL health completo o HTTP. La revisione, lo stato attuale e qualsiasi schedulazione esterna restano aperti. [Script storico](../production-health-readonly.sh) · [Fase 0 locale](../phase0-inspect.sh) · [Riscontro](11-CURRENT-STATUS.md)
