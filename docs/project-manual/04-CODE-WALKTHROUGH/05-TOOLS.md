# Tooling locale, verifica offline e pacchetti

[Indice delle schede](00-GUIDE.md) · [Firme](E-TOOLS-REFERENCE.md) · [Test e prove](../10-TESTING-AND-RELIABILITY.md)

## scripts/package_release.py

Costruisce un archivio dei byte Git selezionati, evitando dipendenze da CRLF locale, filtri, checkout sporco o file aggiunti manualmente. Git fornisce risoluzione e blob, `re` limita namespace e commit, `tarfile/gzip/io` determinano l'archivio e SHA-256 lo identifica. `PurePosixPath` serve per suddivisione su filesystem diversi. `ROOT_FILES/SOURCES/REQUIRED/PACKAGER` sono allowlist e contratti minimi per una revisione impacchettabile. `SourceFile` conserva mode e byte del blob.

| Funzione | Input e risultato |
| --- | --- |
| `git` | Repo e argv → stdout bytes. Disabilita replacement object e lock opzionali, timeout 30 s. Errore del comando propaga. |
| `read_sources` | Root e SHA-1 lowercase 40 → dict path, SourceFile. Esige oggetto commit esatto. Da `ls-tree -rz` legge blob regolari allowlisted e mode 0644/0755 con `cat-file`. Richiede LF finale e assenza CR per i file deploy. Rifiuta percorsi, mode e richiesti mancanti. |
| `directories` | File selezionati → set di parent POSIX, esclusa la root puntuale. |
| `build_archive` | Commit e file → bytes tar.gz. Directory e file in ordine, mtime gzip zero e senza filename, commento PAX commit, modalità fisse e path POSIX. |
| `verify_archive` | Payload, commit e file attesi → legge tar dopo decompressione gzip, confronta commento, inventario senza duplicati, tipo/mode e byte. Usa streaming del membro, senza estrazione in working tree. |
| `package_release` | Root, commit e output .tar.gz → `(digest, lista path)`. Costruisce e verifica prima della scrittura esclusiva. |
| `main` | CLI prende commit e nuovo output, stampa commit, file e hash. Errori noti portano exit 1. |

Esempio. Con la stessa revisione e stessi blob, una copia locale CRLF di `deploy/…` non entra nell'archivio. Se il blob della revisione contiene CR, il package si ferma invece di correggere i byte in silenzio. Percorsi non inclusi in allowlist comprendono la documentazione del manuale e gli strumenti che non servono all'installazione. [Test release](../../../tests/test_release_packaging.py) · [P1](../../PROJECT_HISTORY.md#2026-11-19-p1-offline-verification-and-reproducible-packaging)

## scripts/verify_offline.py

Orchestratore dei sette controlli. Usa `subprocess`, `tempfile`, `shutil.which`, `importlib.util` e report XML pytest con JSON per lista PowerShell. `ROOT` fissa CWD, `PASS/FAIL/SKIP/UNKNOWN` sono stati. La costante `POWERSHELL_PARSER` analizza file PowerShell e blocchi fenced tramite parser .NET, senza eseguirli. L'ambiente dei subprocess è ristretto e usa SQLite temporanei sintetici.

| Funzione | Contratto |
| --- | --- |
| `offline_env` | Scratch → allowlist delle variabili OS, temp, dotenv off, no plugin autoload, DB sintetico, Git senza prompt. |
| `run` | argv e env opzionale → CompletedProcess, root, UTF-8 con replace, cattura output, timeout 180 s. |
| `details` | Risultato → ultime 30 righe combinate di stdout/stderr. |
| `command_check` | Comando, env, messaggio → stato e testo. Exit nonzero è FAIL. |
| `pytest_check` | Temp e env → pytest isolato con cache disabilitata e XML. Conta pass/fail/skip effettivi. Manca modulo/report → UNKNOWN, skip → SKIP, nonzero/failure/zero casi → FAIL. |
| `ruff_check` | Argomenti check/format ed env → Ruff su src/tests/scripts con no-cache. Modulo assente → UNKNOWN. |
| `git_check` | Controlla whitespace su diff, index e HEAD senza ext-diff/textconv e cerca tracked ignorati. File Markdown untracked non sono coperti dal solo `git diff --check`. |
| `source_paths` | Pattern → nomi tracked e untracked non ignorati, ordinati e unici, rifiuta symlink. |
| `bash_check` | Cerca Bash, su Win32 preferisce quello di Git se disponibile. Smoke del binario e parsing -n su tutti .sh. Bash o input assenti → SKIP, impossibile avviarlo → UNKNOWN. |
| `powershell_check` | Cerca pwsh/powershell.exe, scrive manifest e parser nello scratch, avvia parser su .md/.ps1. Mancanza shell → SKIP. |
| `packaging_check` | Scratch → pacchetto HEAD creato localmente, digest e conteggio. Verifica i blob del commit, non usa testi locali untracked. |
| `main` | Parser flag strict, temp, loop sette verifiche, cattura errori ambiente come UNKNOWN, stampa esiti e ritorna 1 su FAIL, 2 su UNKNOWN o SKIP in strict, altrimenti 0. |

GitHub Actions definisce job su Windows 2025 e Ubuntu 24.04, checkout read-only di profondità 2, setup uv fissato, `uv sync --locked` e lo stesso comando strict. Risultato di GitHub Actions e Linux effettivo da provare. Controllo sintattico Bash su Windows non equivale a montare WAL in un servizio systemd. [Workflow](../../../.github/workflows/ci.yml) · [Esito locale](../10-TESTING-AND-RELIABILITY.md)
