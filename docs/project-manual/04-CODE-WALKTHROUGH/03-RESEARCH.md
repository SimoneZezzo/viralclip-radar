# Dataset, evaluate e ranking

[Indice delle schede](00-GUIDE.md) · [Firme](C-RESEARCH-REFERENCE.md) · [Pipeline](../08-DATA-PIPELINE.md) · [Formule e gating](../09-MACHINE-LEARNING.md)

## dataset.py

Costruisce una tabella candidata ripetibile e separa i futuri risultati. `csv/json` sono i formati, `sqlite3` legge sorgente, `subprocess` controlla gitignore, `Counter` fa audit, `sha256` lega i byte, `isclose` valida età, `log1p` costruisce le due trasformazioni. `VERSION`, `CUTOFFS`, `HORIZON` e `TOLERANCE` definiscono il contratto. `FEATURES` costituisce l'allowlist e le tuple colonne assicurano ordine e provenance.

| Struttura | Contenuto e vita |
| --- | --- |
| `Selection` | Inizio/fine, tuple giochi, eventuale watermark e blackout. Creata dalla CLI e passata all'intero builder. |
| `Clip` | Identità, game, creazione, prima vista e broadcaster per audit. Istanza dai risultati SQL. |
| `Observation` | ID snapshot, datetime effettivo e view; righe di misura ordinate in Source. |
| `Source` | Watermark, ultimo orario letto, max ID, schema, clip, mappa osservazioni e job, una fotografia estratta da una singola lettura. |

| Funzione | Input → output, algoritmi ed errori |
| --- | --- |
| `read_source` | Path e Selection → Source. Valida bounds, apre RO, richiede schema 2, massimo osservato e W ≤ massimo. Seleziona clip e legge early snapshot ordinati per ciascuna. Solo se matura cerca lo specifico job con LEFT JOIN. Date malformate o apertura non riuscita propagano. |
| `candidate` | Clip, lista Observation, cutoff, W, blackout → dict con colonne preinizializzate a None. Calcola prediction, status, deduplica per timestamp scegliendo ID minore, ordina, calcola 11 feature. Rifiuta conteggio non intero/negativo. Crescita e tasso richiedono due tempi. |
| `outcome` | Clip, riga job o None, W → dict label. Prima maturità, poi stato e tempo di completamento, poi coerenza FK semantica e misura. Type/Value/Overflow rendono invalid link anziché interrompere. |
| `_coverage` | Righe candidate a un cutoff, outcome e clip indicizzate → dict. Incrocia eligible e valid e conta freshness, due o più punti, assenza crescita, outcome status, blackout e concentrazione broadcaster. |
| `_outage_coverage` | Source, Selection e outcome → lista di risultati per blackout con outcome per gruppi prima/dentro/dopo, limitata a target nominali 10/30/60 strettamente interni. |
| `_csv` | Path, tuple colonne, lista dict → file UTF-8 scritto in modalità esclusiva con LF. CSV blank significa None. |
| `write_json` | Path e payload → JSON esclusivo deterministico per ordinamento chiavi e LF, NaN rifiutato. Riutilizzato dal replay. |
| `ignored_output` | Path → path risolto nuovo e accettato da `git check-ignore`. Path esistente, errore Git o output fuori esclusioni danno ValueError. Riutilizzato da evaluation e Windows prepare. |
| `extract` | Path DB, Selection e nuova dir → coverage. Produce tutte le righe, digest e manifest. Stampa e exit code spettano alla CLI. |

Nella selezione, `if prediction > watermark` gestisce prima l'esperimento che non ha raggiunto la propria età. `if clip.first_seen > prediction` evita di assumere che una clip nota oggi fosse nota al cutoff. Per un campione accettato, `previous is None or observation.snapshot_id < previous.snapshot_id` rende deterministico quale record rappresenta un istante. Con ID 31 e 32 alle 14:18, si conserva il 31. Con un solo campione non si divide per un tempo nullo. [Boundary test, duplicati e esiti](../../../tests/test_dataset.py)

## evaluation.py

Consuma file esportati con controllo d'integrità. Usa `csv/io/json/sha256` per ingest, `isfinite` per score, `log1p/log2` per DCG, `Counter/defaultdict/mean` per pool e aggregati e datetime UTC per calendario. Versione 2b.1, maturità 24h+5m, due date per periodo, dieci label matched per gioco/giorno e quattro baseline. [Protocollo dettagliato](../09-MACHINE-LEARNING.md)

| Struttura | Campi, costruttore e uso |
| --- | --- |
| `Candidate` | ID, game, creazione, cutoff, status, provenance snapshot e tupla score opzionali nell'ordine di `BASELINES`. `day` restituisce la mezzanotte corrispondente. |
| `Outcome` | Stato, eventuale conteggio, timestamp e coppia di ID job/snapshot. Oggetto confrontabile per conflitti. |
| `SourceWindow` | Inizio, fine, W e tuple game; da ogni manifest. |
| `Inputs` | Mappe candidate/outcome/token, finestre, outage, fingerprint e conteggi input, aggiornate durante merge. |

| Funzione | Input → output, algoritmi ed errori |
| --- | --- |
| `_csv` | Byte UTF-8 → lista di dict con celle stringa. |
| `_candidate` | Riga CSV e finestra → Candidate normalizzato; ricontrolla coorte, cutoff e status con W, date first/latest ≤ prediction, età ricalcolata, conteggi e tassi finiti. Calcola le 4 baseline. |
| `_outcome` | Riga, Candidate della stessa clip, W → Outcome. Confronta status e maturità, vieta label negli esclusi. Per valid ricontrolla finestra, età misurata, count e ID. |
| `read_inputs` | Directory → Inputs. Verifica hash, versioni e colonne, fa merge con regole di conflitto, vincola i keyset delle clip/outcome e di eventuali broadcaster. Errori di lettura, hash o metadata possono interrompere. |
| `ranking_metrics` | Ordine di clip, label per ID e K → dict. Immagina l'ordine ideale, deriva soglia top decile con pareggi e conta hit sui primi K. Restituisce Precision/Recall e rapporto DCG ideale, null per guadagno ideale zero. Assume pool non vuoto. |
| `_dcg` | Lista di conteggi nell'ordine da valutare → somma di guadagni logaritmici scontati. Lista vuota produce 0. |
| `_day_is_covered` | Giorno, gioco, finestre, deadline opzionale → bool. Unione crescente di finestre senza gap, tagliando ogni fine a W/deadline meno maturità. |
| `_period` | Candidate di una partizione, Inputs e deadline → report, mappe eligible per cutoff, set matched e set pool rankable. Calcola coverage, stati, embargo, date mature, cardinalità e variazione outcome. |
| `_outage_exposed` | Candidate e Inputs → boolean sovrapposizione della finestra di predizione con almeno un blackout. |
| `_population` | Iterable di Candidate e Inputs → diagnostica per conteggio, gap, missing score e concentrazione token. Materializza la lista per aggregarla più volte. |
| `_scores` | Tupla period, Inputs, K → metriche per cutoff e popolazione. Raggruppa per pool rankable, ordina per score e ID, computa le i tre indicatori per ciascuno dei quattro metodi, costruisce media macro su ogni metrica. |
| `evaluate` | Inputs, confini o None, K → dict status, motivi, periodi, metriche e dedup. Valida positive K e date. Richiede giorni e split, fa score soltanto validation/test quando entrambi e train passano. |
| `run_evaluation` | Directory, output, split, K → report. Controlla directory, legge, calcola, scrive report e manifest con hash, versioni, settings e regole. Errori non vengono assorbiti qui. |

Esempio di merge. Due input con lo stesso ID, cutoff 60 e stesso conteggio utile possono differire perché il più vecchio è `cutoff_immature`. Il più recente può rimpiazzarlo secondo watermark. Se entrambi si dichiarano maturi con feature differenti, il lettore rifiuta il confronto. Anche due label valide con stessi view ma con provenance ID diversi non sono lo stesso Outcome. [Test hash, overlap, embargo e ranking](../../../tests/test_evaluation.py)
