# Audit M2 delle coorti

L'audit riporta, per categoria, la disponibilità delle feature e degli outcome,
le giornate utilizzabili e la fattibilità degli split cronologici. Emette JSON
su stdout e un riepilogo su stderr. Legge uno snapshot SQLite per database,
con lo stesso cutoff temporale. Il report contiene solo aggregati.
Feature e label riusano le funzioni di [dataset.py](../src/viralclip/dataset.py).

## Lettura del report

- Il watermark comune è il minore dei due massimi timestamp di osservazione.
  Il report conserva entrambi i massimi e gli ID massimi degli snapshot.
  Se una sorgente manca, il watermark comune è `null` con stato `UNKNOWN`.
  L'altra può essere descritta con il proprio watermark, marcato `individual_only`.
- I totali del DB e al watermark sono distinti dagli aggregati delle coorti.
  `--start` e `--end` limitano coorti e registro a date UTC intere in un
  intervallo semiaperto. Il default va dal primo giorno osservabile al giorno
  del watermark incluso. Compaiono anche le giornate a zero clip. Una frazione
  senza denominatore è `null`. Gli snapshot giornalieri sono contati per
  coorte di creazione della clip e tempo di osservazione entro il watermark.
- `first_seen_this_utc_day` conta le prime discovery registrate in quel giorno
  UTC anche per clip create in altri giorni. `clips` usa il giorno di
  creazione. Le classi di latenza sono disgiunte, con estremo superiore
  incluso, e usano i target delle osservazioni e i cutoff documentati.
- `matched_at_cutoff` conta feature utilizzabili e outcome valido per quel
  cutoff. `matched_all_cutoffs` è l'intersezione dei quattro cutoff. Il report
  conserva stati, disponibilità di due istanti distinti e staleness rispetto
  agli ultimi cinque minuti.
- `scheduled_jobs_due_by_target_seconds` confronta i job attesi per età e quelli
  già dovuti nel DB. Distingue il link a una misura schedulata, arrivo oltre
  il target, indisponibilità, link invalido e righe mancanti. Un job senza una
  misura registrata al watermark può ancora completarsi. La validità
  puntuale di feature e outcome è determinata dai rispettivi cutoff.
- Le durate di discovery sono unioni di intervalli ritagliati al giorno UTC.
  Un retry sovrapposto conta gli stessi secondi una volta per categoria. Si
  considerano i run conclusi entro il watermark. I risultati delle lane
  `recent`, `history` e `retry` descrivono la scansione. `cursor_exhausted`
  rimane evidenza di scansione. La completezza della popolazione Twitch è
  `UNKNOWN` per entrambi i giochi.
- Il massimo intervallo tentato include le richieste senza una pagina utile.
  Il massimo intervallo utilizzabile richiede almeno una pagina e un esito
  diverso da `error`. Considerare entrambi entro l'intervallo dell'audit.
- Il criterio per il benchmark principale richiede 86.400 secondi di finestre
  legacy completate con almeno una richiesta e senza errore o troncamento.
  I successi possono risolvere un errore precedente sugli stessi secondi.
  `known_incomplete` rimane esplicito anche quando si sovrappone a un successo
  legacy. I giorni GTA VI sostenuti solo dal nuovo ledger restano esclusi
  dal benchmark principale finché manca un criterio approvato per ammetterli.
- Dichiarare gli incidenti verificati con `--outage GAME START END`. Per
  prudenza il giorno viene escluso se un incidente si sovrappone alla sua
  creazione o all'orizzonte massimo di osservazione e maturità.
- Un pool ammesso ha una giornata intera matura, almeno 10 matched e due
  esiti distinti. L'audit esamina i confini a mezzanotte UTC per gioco dopo
  l'embargo. Riporta quante coppie sono fattibili e un esempio per il minimo
  `2/2/2` e per il target `7/3/7` con 500 matched nel test. A zero coppie
  fattibili, l'eventuale esempio mostra il tentativo più vicino al target.

`GO` indica che il minimo software è raggiunto per il gioco. `PARTIAL`
indica evidenza insufficiente per lo scoring. `NO-GO` segnala un errore
tecnico di lettura, identità o integrità dei dati. Lo stato di misura
`UNKNOWN` distingue una verifica indisponibile da un conteggio zero
verificato. L'exit code `2` segnala un `NO-GO`. Leggere il JSON per il
giudizio per gioco.

## Esecuzione

In locale, usare database sintetici chiusi in modalità rollback su Windows.

```powershell
uv run --offline --no-sync python -I -B -m viralclip.m2_audit --gta-v 'v-fixture.sqlite3' --gta-vi 'vi-fixture.sqlite3'
```

Per il VPS serve approvazione separata per SSH e lettura privilegiata.
Eseguire prima i campioni in sola lettura del
[runbook M1](MILESTONE_1_ROLLOUT.md#0-linux-vps--read-only-inventory-and-baseline).
Verificare PID, identità dei DB, sidecar esistenti e riserva disco. La vista
WAL può prolungare la ritenzione dei frame. Eseguire un audit alla volta.
Il limite predefinito è 30 secondi complessivi, con timeout esterno di 45
secondi. Il range è limitato a 366 giorni, il registro a 120.000 run e l'input
early a 4.096 snapshot per clip. Un limite superato produce `UNKNOWN`.
Se il range è troppo ampio, restringerlo a date UTC intere. I totali del DB
richiedono comunque una lettura globale.

Da PowerShell locale, il comando passa il sorgente via stdin e usa Python
del runtime GTA VI. Verifica gli SHA-256 normalizzati a LF dei due moduli
M2 caricati. L'operatore deve avere accesso approvato con `sudo -n` a entrambe
le directory di stato. Landlock ABI ≥3 è richiesto su Linux prima di aprire
i DB, con le restrizioni del runbook. Seguono URI `mode=ro`, `query_only`,
transazione e cache limitata. In assenza di JSON, l'audit è `UNKNOWN`.
Aggiungere al comando le altre interruzioni verificate nel preflight.
Usare la revisione verificata del runtime installato per gli hash dei
moduli di supporto. Durante l'audit del 23 novembre il runtime era
`4ab8d05f1ca1` e l'evaluator locale aveva già una revisione successiva.

```powershell
$target = Read-Host 'Alias SSH autorizzato'
if ($target -cnotmatch '^(?:[A-Za-z_][A-Za-z0-9_.-]*@)?[A-Za-z0-9][A-Za-z0-9.-]*$') {
    throw 'Alias SSH non valido'
}
$m2RuntimeRevision = Read-Host 'Revisione del runtime verificata nel preflight'
if ($m2RuntimeRevision -cnotmatch '^[0-9a-f]{12,40}$') { throw 'Revisione non valida' }
function Get-M2RuntimeModuleHash([string] $module) {
    $source = git --no-pager show "${m2RuntimeRevision}:src/viralclip/$module.py"
    if ($LASTEXITCODE -ne 0) { throw "Modulo di supporto non trovato: $module" }
    $normalized = [Text.Encoding]::UTF8.GetBytes(($source -join [char]10) + [char]10)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($sha.ComputeHash($normalized))).Replace('-', '').ToLowerInvariant()
    } finally {
        $sha.Dispose()
    }
}
$datasetHash = Get-M2RuntimeModuleHash 'dataset'
$evaluationHash = Get-M2RuntimeModuleHash 'evaluation'
$command = @(
    'sudo -n -- timeout 45s nice -n 10 /opt/viralclip-gta-vi/.venv/bin/python -I -B -'
    '--gta-v /var/lib/viralclip-radar/viralclip.sqlite3'
    '--gta-vi /var/lib/viralclip-gta-vi/gta-vi.sqlite3'
    "--verify-support $datasetHash $evaluationHash"
    '--outage gta-v 2026-11-17T18:26:14.379860Z 2026-11-17T18:49:26.389030Z'
) -join ' '
Get-Content -Raw -Encoding UTF8 .\src\viralclip\m2_audit.py |
    ssh.exe -T -o StrictHostKeyChecking=yes -o UpdateHostKeys=no $target $command
```

## Ammissione delle giornate GTA VI

Per il benchmark primario si applicano i criteri riportati sopra. Per
una futura analisi di sensibilità sulle sole clip osservate, preregistrare
la classificazione dei giorni usando l'unione degli intervalli con pagine
utilizzabili, il registro di risultati e le interruzioni verificate.
Richiedere 86.400 secondi di tentativi utilizzabili sull'intera giornata,
maturità e assenza di interruzioni durante creazione e osservazione. Usare
gli stessi minimi esistenti, 10 clip matched con due esiti distinti e
2/2/2 giorni dopo embargo. Riportare separatamente i giorni con budget,
paginazione anomala o omissioni note, i tassi di inclusione e la
concentrazione per broadcaster. Il confronto tra strategie usa gli stessi
giorni e le stesse clip del test GTA VI. L'ammissione di questo strato
resta una proposta da fissare prima di accedere ai risultati.

L'evaluator applica il minimo per gioco, le interruzioni dichiarate per
gioco e controlli di derivazione sulle feature dei baseline. Gli export
2a.3 includono le giornate di discovery ammesse nel `coverage.json`
verificato dall'hash nel manifest. L'evidenza è calcolata nella stessa
transazione e allo stesso watermark dei dati estratti. Una riga
proveniente solo da un altro export senza evidenza rimane diagnostica,
anche se appartiene allo stesso gioco e giorno. I pool richiedono comunque
outcome maturi, embargo e livelli minimi. Gli export 2a.1 e 2a.2 restano
leggibili per la diagnosi. Le automazioni leggono lo stato JSON di insufficienza.
Riportare incertezza tra giornate e dimensioni dei pool. Recall@10 vale 1
per qualsiasi ordine in un pool di dieci clip.

## Evidenza locale del 22 novembre 2026

Su Windows, la verifica strict ha eseguito 190 test con 0 errori e 0 skip.
Ruff lint, sintassi Bash/PowerShell e packaging della revisione selezionata
sono passati. Ruff format e Git hanno segnalato problemi preesistenti in
`cli.py` e `config.py`. I file Python dell'audit passano lint e formato.
Le fixture verificano che il lettore lasci invariati i file di stato.
Una prova sintetica di scala su Windows ha elaborato 125.002 clip e
500.002 osservazioni in 20,41 secondi. Il tempo sul VPS resta da misurare.
Il percorso WAL con Landlock richiede un host Linux compatibile per la
prova effettiva. Idoneità delle coorti reali e stato live restano `UNKNOWN`.
