# 21–23. Ranking, valutazione cronologica e machine learning

[Indice](00-INDEX.md) · [Feature e label](08-DATA-PIPELINE.md) · [Funzioni ricerca](04-CODE-WALKTHROUGH/03-RESEARCH.md) · [Stato M2–M4](11-CURRENT-STATUS.md)

## 21. Baseline e popolazioni

Una classifica assegna un ordine. Una baseline è un regolo semplice con cui misurare il vantaggio di metodi più complessi. Se un modello consuma più tempo e rende impossibile capire una predizione, serve evidenza comparabile che porti un miglioramento. Le baseline implementate sono deterministiche, senza fit e senza parametri appresi.

| Nome nel report | Formula al cutoff e significato | Per l'esempio del dataset |
| --- | --- | --- |
| `latest_views` | `vn`, usa l'ultimo conteggio. | 48 |
| `observed_growth` | `vn−v1`, privilegia incremento osservato. | 36 |
| `growth_rate` | `60(vn−v1)/(tn−t1)`, divide per minuti realmente trascorsi. | 2 |
| `age_normalized_views` | `vn / max(1, (tn−t0)/60)`, conta dalla creazione con denominatore minimo un minuto. | 48/23 ≈ 2,087 |

La chiave di ordinamento è `(score is None, -score, clip_id)`, con valore di comodo zero nel termine numerico per il mancante. Una crescita negativa valida precede comunque il mancante. Precision e Recall riguardano la membership nella testa del pool. Un giorno è UTC fra due mezzanotti, quindi indipendente da fuso e DST del server. Il pool è raggruppato per `(game_id, day_utc)`.

### Validazione dei file e degli overlap

`read_inputs` accetta manifest 2a.1 e 2a.2 e controlla cutoff, allowlist di feature e finestra label. Ricalcola hash di ogni artefatto richiesto, incluso `dataset.csv`. Il replay ricostruisce da `candidates.csv` e `outcomes.csv`. Il join esportato serve a consumo a valle e il suo hash ne verifica i byte, senza riutilizzare le sue righe per lo scoring. Verifica bounds e maturità, categorie e quadratura delle chiavi. Stessa clip con diversa creazione/categoria o conflitto fra feature stabili è incompatibile. Una riga immatura può essere sostituita con il risultato più aggiornato. Una label valida prevale sugli esiti non validi, e due label valide divergenti fanno fallire il caricamento. Il token broadcaster segue il watermark più recente. [Lettore e validazioni](../../src/viralclip/evaluation.py) · [Test conflitti](../../tests/test_evaluation.py)

### Split, embargo e “giorno pieno”

- La partizione dipende da `created_at`. Train precede `validation_start`, validation parte da lì in modo inclusivo e finisce esclusivamente a `test_start`, test include la seconda data. Tutti i cutoff di una clip appartengono alla stessa partizione. La CLI normalizza in UTC e l'evaluatore chiede entrambe le mezzanotti in ordine.
- Una label di train deve maturare entro l'inizio validation. Una label validation deve maturare entro l'inizio test. Il test usa i watermark dei file sorgente. La maturità è l'intera finestra a 24h+5m, anche quando la vista è stata già misurata e il suo valore è noto al replay.
- Per gioco e giorno `_day_is_covered` unisce intervalli dichiarati nell'ordine di inizio senza buchi, avanzando un cursore con `min(window.end, min(window.watermark, deadline)−MATURITY)`. Una pool day parte da una data che ha almeno una clip candidata. Il gate richiede almeno 10 clip con feature e label ammissibili **a tutti e quattro i cutoff**, con almeno due esiti diversi. Due giochi nella stessa data non fanno due date indipendenti.
- Train, validation e test richiedono ciascuno almeno due giorni rankable distinti **dopo** l'embargo. Senza date dichiarate, almeno sei giorni rankable prima di applicare embargo fanno stampare `SPLIT BOUNDARIES REQUIRED`. Sotto sei o se uno split dichiarato non raggiunge il proprio minimo, stato `INSUFFICIENT DATA` e `metrics={}`. Altrimenti `EVALUATED` con metriche soltanto su validation e test.
- Le due popolazioni osservate sono `cutoff_eligible` e `matched`, entrambe sugli stessi pool gioco/giorno rankable. La prima permette al cutoff più largo di usare clip nuove. La seconda fissa gli ID e rende interpretabile l'effetto del solo cutoff. Ogni score mantiene gli stessi candidati all'interno della rispettiva popolazione.
- I report conservano riassunti su giorni non scored, stato label, esclusi, blackout e concentrazione. La copertura di giorno attesta l'intervallo di estrazione e maturità, con i limiti del processo di discovery.

Esempio embargo. Clip train del 9 alle 23:58, validation al 10 alle 00:00. La sua label matura l'11 alle 00:03. Viene esclusa da train anche se il file letto oggi contiene una misura alle 23:59 del 10. Un'intera giornata di confine può essere non rankable anche quando una parte delle label ha già maturato. Sei date osservate sono quindi un requisito necessario per richiedere split, non la prova che i tre split siano fattibili. [Guida cronologica](../CHRONOLOGICAL_EVALUATION.md#when-scoring-is-permitted) · [Gate nel codice](../../src/viralclip/evaluation.py)

### Metriche con esempio numerico

Ordinando le label reali di un pool di `N` clip, la soglia di rilevanza è il valore a posizione `ceil(N/10)` one-based. Tutti i pareggi sulla soglia sono inclusi. Nel pool di dieci con view `100,100,65,50,40,30,20,10,2,1` i due 100 sono rilevanti. A `K=3` il metodo restituisce label reali nell'ordine `100,65,50` e centra un rilevante.

- `Precision@3 = 1 / 3 ≈ 0,333`, quota dei suggerimenti scelti che sono rilevanti.
- `Recall@3 = 1 / 2 = 0,5`, quota dei rilevanti che sono stati trovati.
- `DCG@3 = ln(101)/log2(2) + ln(66)/log2(3) + ln(51)/log2(4) ≈ 9,225`. I guadagni logaritmici riducono il peso di code molto pesanti. Il divisore penalizza ciò che appare più in basso.
- `IDCG@3` usa `100,100,65` e vale circa 9,622. `NDCG ≈ 0,959`. È alta perché l'ordine prende comunque clip con label elevate, anche se Precision/Recall penalizzano il secondo 100 mancante. Se il guadagno ideale è zero l'helper restituisce null. Pool ammessi con label intere non negative e variazione hanno almeno un guadagno positivo.
- K effettivo è `min(K, N)` e il default è 10. La macro media dà lo stesso peso a ciascun gioco/giorno scored, indipendentemente dalla numerosità.

Il report datato 18 novembre aveva 3.344 clip matched su una parte del 17 UTC e zero giorni pieni rankable. L'esito `INSUFFICIENT DATA` attesta che il gating ha escluso una valutazione fuorviante. Il conteggio di righe e la verifica degli hash non sono una performance. Report con dataset più recenti e ripetuti non sono stati ispezionati in questa sessione. [Evidenza M2B](../PROJECT_HISTORY.md#2026-11-18-milestone-2b-chronological-evaluation-and-ranking-baselines)

## 22. Come leggere la progettazione M3

**PROGETTATO.** La specifica propone regressione logistica scikit-learn e LightGBM se ci sono dati sufficienti. Il checkout usa httpx e dotenv come dipendenze applicative e importa solo strumenti stdlib per l'analisi. Non contiene trainer, modello salvato, tattica di tuning o modello selezionato sperimentalmente. Le descrizioni matematiche seguenti spiegano le opzioni di specifica. [Specifica M3](../PROJECT_SPECIFICATION.md#6-milestone-3--machine-learning) · [Dipendenze](../../pyproject.toml)

- **Classificazione logistica.** Se si definisce un binario di rilevanza in un protocollo esplicito, `p(y=1|x)=1/(1+exp(−(b+w·x)))`. In forma standard minimizza la somma di perdite `−y ln p − (1−y) ln(1−p)` più un'eventuale penalità sui pesi. È interpretabile via direzione e ordine di grandezza dei coefficienti dopo scaling e gestione dei null. Intercetta, regolarizzazione, preprocessing, pesi di classe e regola usata per creare il target restano da scegliere.
- **Gradient boosting ad alberi, candidato LightGBM.** Un insieme di alberi produce `F_M(x)=F_0(x)+η Σ_m f_m(x)`. A ogni stadio l'albero impara ad approssimare correzioni determinate dal gradiente della loss, suddividendo lo spazio di feature tramite soglie. Apprende interazioni fra età e crescita e può overfittare canali, periodi e trend temporanei. Obiettivo classificazione, regressione o ranking a gruppi è da concordare. Learning rate, capacità e numero alberi sono iperparametri, scelti sul solo sviluppo.
- **Regressione.** Il target può essere `views_24h` o una sua trasformazione dichiarata. MAE media `|y−ŷ|` in unità di vista. Una error rate su log dà più peso a scostamenti relativi. Obiettivi simili per ranking possono produrre errori di conteggio diversi. Nessuna metrica di regressione è calcolata dall'attuale replay.
- **Ranking.** Ottimizzare direttamente un ordine può usare una loss fra coppie dello stesso pool o un surrogato di NDCG. È un'opzione di disegno. Le quattro baseline già presenti sono score di singola clip seguiti da sort. Una soglia di rilevanza di ground truth calcolata usando esiti del giorno serve al replay per giudicare, senza comparire tra le feature.
- **Generalizzazione.** Fit solo su train, scelta modello/iperparametri su validation, una misura finale su test più recente. Overfitting significa imparare peculiarità del campione, per esempio pochi canali dominanti o un giorno di lancio. Una prova separata su creator assenti dal training, feature importance e calibrazione sono nella specifica. Senza calibrazione e verifica non si interpreta uno score come probabilità.
- **Riproducibilità futura.** Conservare versione modello, feature e cutoff, digest dei dati, timestamp di training e previsione, partizioni, parametri, software, report e condizioni di riproduzione. I file `predictions`, `model_runs` e `evaluation_results` appaiono come possibilità di schema. Il codice oggi produce solo artefatti 2A e 2B.

La sufficienza statistica va oltre il minimo tecnico dei due giorni per split. Si deve controllare stabilità fra giorni, copertura degli esiti, concentrazione per e dentro gioco, incertezza, informatività a pari popolazione, deriva al cambiare di stagione o strategia API. Importanza di feature e confronto di performance sono criteri futuri, insieme ai diritti d'uso per dati e pesi. [Roadmap](12-ROADMAP.md) · [Decisioni aperte](15-DECISION-REGISTER.md)

## 23. Dalla misura all'eventuale inferenza

| Passaggio utente/sistema | Stato e contratto |
| --- | --- |
| Viene creata una clip e l'ID appare in Helix. | **IMPLEMENTATO** discovery del campione pubblico. Copertura assoluta **UNKNOWN**. |
| Prime osservazioni arrivano con tempo e conteggi reali. | **IMPLEMENTATO**, con omissioni, failure, ritardo e job persistenti. |
| Al cutoff si calcolano feature. | **IMPLEMENTATO** nel builder e replay offline, riusabile come base per il futuro calcolo online. Lo scheduler di inferenza per singola clip è **PROGETTATO** come flusso, da definire. |
| Si carica un modello e si produce score immutabile. | **PROGETTATO**. Restano modello o fallback, artifact store, tabella/evento di score, schema, latenza e integrazione. |
| Si ordina un gruppo comparabile. | **IMPLEMENTATO** come replay privato, **PROGETTATO** come classifica per utenti e demo. |
| L'utente apre un dashboard e segue il link Twitch. | M4 **PROGETTATO** come Streamlit locale e offline con sintetico. Una API separata resta opzionale, senza contratto. |
| Si misura nel tempo outcome osservato e qualità. | **IMPLEMENTATO** esito 24h in raccolta/estrazione. Monitor di predizioni, score e performance in produzione ancora futuro. |

Nei periodi con model assente la specifica propone un ranking euristico e stato `not_trained_yet`. Questo stato di prodotto e il flusso di servizio devono ancora essere implementati. In inferenza la label non è disponibile alla stessa clip. La raccolta a 24h può poi collegarsi alla previsione storica per validazione, senza modificarla. [Specifiche](../PROJECT_SPECIFICATION.md) · [Architettura](02-ARCHITECTURE.md)
