# ViralClip Radar, manuale tecnico e didattico

Audit del 20 novembre 2026 (Europe/Rome). La base tecnica è la working copy locale su `chore/context-efficiency`, con HEAD `c01480c6d401d84ae0cb4d169c333e409231395f`. All'apertura erano già modificati `PROJECT_STATUS.md`, `docs/MILESTONE_1_ROLLOUT.md` e `docs/PROJECT_HISTORY.md`. `docs/phase0-inspect.sh` era già presente come file non tracciato. Questo manuale descrive anche quelle modifiche, distinguendole dal commit. La produzione attuale è **UNKNOWN**. [Stato operativo e fonti](11-CURRENT-STATUS.md)

## Prima lettura

Dedica circa 15–20 minuti al [briefing](16-EXECUTIVE-BRIEFING.md). Poi segui l'ordine qui sotto. Ogni capitolo alterna il significato pratico al contratto ricostruito dal codice. Gli esempi, salvo indicazione con data e fonte, sono sintetici.

| Ordine | Documento | Cosa vi trovi |
| --- | --- | --- |
| 1 | [Visione e storia](01-VISION-AND-HISTORY.md) | Problema, perimetro, definizione di viralità, decisioni e prove storiche. Capitoli 1–2. |
| 2 | [Architettura](02-ARCHITECTURE.md) | Processi, diagrammi, errori, ciclo di vita della clip delle 14:00 e mappa delle chiamate. Capitoli 3–4 e 7. |
| 3 | [Inventario e percorso di studio](03-REPOSITORY-MAP.md) | Albero, ruolo di ogni file, esclusioni e ordine di lettura del codice. Capitoli 5 e 28. |
| 4 | [Schede del codice](04-CODE-WALKTHROUGH/00-GUIDE.md) | API interne, firme, rami, dipendenze, test e limiti per modulo. Capitolo 6. |
| 5 | [Twitch e raccolta](05-TWITCH-AND-COLLECTION.md) | OAuth, Helix, discovery, retry, job persistenti e isolamento GTA V/GTA VI. Capitoli 8–11. |
| 6 | [Database](06-DATABASE.md) | Schema, diagramma ER, scritture, WAL, concorrenza, recovery e garanzie. Capitoli 12–14. |
| 7 | [Infrastruttura](07-INFRASTRUCTURE.md) | Windows, Ubuntu, systemd, configurazione, monitor, rollout, backup e restore. Capitoli 15–17. |
| 8 | [Pipeline dati](08-DATA-PIPELINE.md) | Coorti, 11 feature, cutoff, label, censura, manifest, replay e leakage. Capitoli 18–20. |
| 9 | [Ranking e ML](09-MACHINE-LEARNING.md) | Quattro baseline, metriche, split temporali, vincoli di valutazione, ricerca e futura inferenza. Capitoli 21–23. |
| 10 | [Test e affidabilità](10-TESTING-AND-RELIABILITY.md) | Matrice requisiti, suite, esiti, difetti e rischi. Capitoli 24–25. |
| 11 | [Stato e incertezze](11-CURRENT-STATUS.md) | M0–M4, P0–P2, verifiche datate e punti aperti. Capitolo 26. |
| 12 | [Roadmap](12-ROADMAP.md) | Dipendenze, criteri, impatto, autorizzazioni e attività future. Capitolo 27. |
| 13 | [Esempi end-to-end](13-END-TO-END-EXAMPLES.md) | Otto scenari dal record di discovery all'errore di restore. Capitolo 29. |
| 14 | [Glossario](14-GLOSSARY.md) | Definizioni ed esempi nel contesto del progetto. Capitolo 30. |
| 15 | [Registro delle decisioni](15-DECISION-REGISTER.md) | Scelte prese, decisioni da approvare e alternative. Capitolo 31. |
| 16 | [Briefing](16-EXECUTIVE-BRIEFING.md) | Visione d'insieme per orientarsi prima delle schede. |

## Come leggere le prove

| Stato | Criterio |
| --- | --- |
| **IMPLEMENTATO** | Il comportamento è presente nel sorgente ispezionato. |
| **TESTATO** | Il comportamento è coperto da un test identificabile. Un risultato d'esecuzione indica anche piattaforma e sessione. |
| **VERIFICATO LIVE** | Un'osservazione datata documenta il comportamento entro ambiente, finestra e fonte indicati. |
| **PROGETTATO** | Obiettivo o contratto presente nella specifica, nel runbook o in una proposta identificata. |
| **PARZIALE** | Una parte del contratto è implementata o dimostrata e il resto ha prove mancanti. |
| **BLOCCATO** | Una condizione specifica impedisce il passo successivo, per esempio maturità del campione o autorizzazione. |
| **UNKNOWN** | Le prove disponibili non permettono di stabilire l'esito o lo stato. |

I file sorgente e i test spiegano il comportamento di questa copia. [Specifiche](../PROJECT_SPECIFICATION.md) e [runbook di M1](../MILESTONE_1_ROLLOUT.md) definiscono gli obiettivi e le procedure. [Project History](../PROJECT_HISTORY.md#evidence-log) fornisce i risultati datati. Le note di stato e la presenza di unità nel repository da sole non attestano l'installazione. I riferimenti con numero di riga puntano alla copia ispezionata. Per i link sorgente il frammento `#L…` è pensato per i browser Git che mostrano le righe.

Per orientarti in un singolo file, parti dall'[inventario](03-REPOSITORY-MAP.md), cerca la funzione nell'[indice delle schede](04-CODE-WALKTHROUGH/00-GUIDE.md) e risali al [percorso di esecuzione](02-ARCHITECTURE.md#entry-point-e-mappa-delle-chiamate).
