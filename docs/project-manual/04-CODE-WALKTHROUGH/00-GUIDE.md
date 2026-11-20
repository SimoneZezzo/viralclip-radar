# 6. Lettura del codice per modulo

[Indice generale](../00-INDEX.md) · [Inventario](../03-REPOSITORY-MAP.md) · [Mappa chiamate](../02-ARCHITECTURE.md#entry-point-e-mappa-delle-chiamate)

Ogni gruppo ha una scheda di lettura e un riferimento per righe, firme e chiamanti. Leggi prima l'esempio e poi segui i link al sorgente. Il riferimento automatico AST comprende i callback annidati e le classi. Per dipendenze, return, risorse, rami, effetti e test, consulta la scheda narrativa corrispondente. Per gli script Bash ci sono sequenze e funzioni nella scheda operativa.

| Gruppo | Scheda narrativa | Firme, classi e riferimenti sorgente |
| --- | --- | --- |
| CLI, config, discovery, refresh, OAuth, telemetria | [Raccolta](01-COLLECTION.md) | [A](A-COLLECTION-REFERENCE.md) |
| SQLite, backup e health | [Storage](02-STORAGE.md) | [B](B-STORAGE-REFERENCE.md) |
| Builder, feature, outcome, split, ranking | [Ricerca](03-RESEARCH.md) | [C](C-RESEARCH-REFERENCE.md) |
| Deployment, GTA VI, backup/monitor, Windows e Bash | [Operazioni](04-OPERATIONS.md) | [D](D-OPERATIONS-REFERENCE.md) |
| Packaging, verifica offline e CI | [Tooling](05-TOOLS.md) | [E](E-TOOLS-REFERENCE.md) |

Il [capitolo test](../10-TESTING-AND-RELIABILITY.md) spiega i confini coperti da ciascuna suite. L'[indice dei casi](F-TEST-REFERENCE.md) dà accesso diretto alle 112 funzioni test e alle fixture/helper. Le parametrizzazioni fanno sì che il numero di casi eseguiti superi quello delle funzioni.
