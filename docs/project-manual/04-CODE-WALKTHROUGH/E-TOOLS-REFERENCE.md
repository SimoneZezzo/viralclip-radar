# Riferimento a firme e chiamate

[Indice delle schede](00-GUIDE.md) · [Spiegazione dei moduli](05-TOOLS.md)

Indice statico ricavato con AST. I chiamanti e i test sono corrispondenze per simbolo, comprese quelle indirette nei callback definiti dentro un test. Le prove indirette e i percorsi effettivi sono nelle schede narrative. Per nomi condivisi come `main`, `_csv`, `preflight` e `close`, gli omonimi di altri moduli sono omessi dall'elenco per evitare attribuzioni ambigue. Importazioni dinamiche e callback passati senza invocarli possono sfuggire all'indice.

## scripts/package_release.py

[Apri il file](../../../scripts/package_release.py)

Import dichiarati. `import argparse`, `import gzip`, `import hashlib`, `import io`, `import re`, `import subprocess`, `import tarfile`, `from dataclasses import dataclass`, `from pathlib import Path, PurePosixPath`.

Costanti. `ROOT_FILES`, `PACKAGER`, `REQUIRED`, `SOURCES`.

### Classe SourceFile

[`SourceFile`](../../../scripts/package_release.py#L30) (righe 30–32).

Campi dichiarati. `mode: int`, `data: bytes`.

### git

`git(root: Path, *args: str) -> bytes`

[`Sorgente`](../../../scripts/package_release.py#L35) (righe 35–40).

Chiamate nel corpo. `subprocess.check_output`.

Chiamanti per nome. [`read_sources`](../../../scripts/package_release.py#L43), [`git_check`](../../../scripts/verify_offline.py#L161), [`source_paths`](../../../scripts/verify_offline.py#L191), [`packaging_check`](../../../scripts/verify_offline.py#L240).

Test che richiamano il simbolo. [`test_exact_commit_is_independent_of_git_and_checkout_configuration`](../../../tests/test_release_packaging.py#L62), [`test_rejects_symlink_blob_without_following_it`](../../../tests/test_release_packaging.py#L104).

### read_sources

`read_sources(root: Path, revision: str) -> dict[str, SourceFile]`

[`Sorgente`](../../../scripts/package_release.py#L43) (righe 43–78).

Chiamate nel corpo. `re.fullmatch`, `ValueError`, `git(root, 'rev-parse', '--verify', f'{revision}^{{commit}}').decode().strip`, `git(root, 'rev-parse', '--verify', f'{revision}^{{commit}}').decode`, `git`, `git(root, 'ls-tree', '-rz', '--full-tree', revision, '--', *ROOT_FILES, 'src', 'tests', 'deploy', PACKAGER).split`, `filter`, `entry.split`, `name.decode`, `metadata.decode('ascii').split`, `metadata.decode`, `SOURCES.fullmatch`, `path.startswith`, `data.endswith`, `SourceFile`, `set(REQUIRED).difference`, `', '.join`.

Chiamanti per nome. [`package_release`](../../../scripts/package_release.py#L130).

Test che richiamano il simbolo. [`test_rejects_archives_that_do_not_match_the_commit`](../../../tests/test_release_packaging.py#L132), [`test_rejects_corrupt_gzip_checksum`](../../../tests/test_release_packaging.py#L146).

### directories

`directories(sources: dict[str, SourceFile]) -> set[str]`

[`Sorgente`](../../../scripts/package_release.py#L81) (righe 81–87).

Chiamate nel corpo. `parent.as_posix`, `PurePosixPath`.

Chiamanti per nome. [`verify_archive`](../../../scripts/package_release.py#L90), [`build_archive`](../../../scripts/package_release.py#L111).

### verify_archive

`verify_archive(payload: bytes, revision: str, sources: dict[str, SourceFile]) -> None`

[`Sorgente`](../../../scripts/package_release.py#L90) (righe 90–108).

Chiamate nel corpo. `tarfile.open`, `io.BytesIO`, `gzip.decompress`, `archive.pax_headers.get`, `ValueError`, `archive.getmembers`, `sources.keys`, `directories`, `sources.get`, `member.isdir`, `archive.extractfile`, `stream.read`.

Chiamanti per nome. [`package_release`](../../../scripts/package_release.py#L130).

Test che richiamano il simbolo. [`test_rejects_archives_that_do_not_match_the_commit`](../../../tests/test_release_packaging.py#L132), [`test_rejects_corrupt_gzip_checksum`](../../../tests/test_release_packaging.py#L146).

### build_archive

`build_archive(revision: str, sources: dict[str, SourceFile]) -> bytes`

[`Sorgente`](../../../scripts/package_release.py#L111) (righe 111–127).

Chiamate nel corpo. `io.BytesIO`, `gzip.GzipFile`, `tarfile.open`, `directories`, `tarfile.TarInfo`, `tar.addfile`, `sources.items`, `buffer.getvalue`.

Chiamanti per nome. [`package_release`](../../../scripts/package_release.py#L130).

Test che richiamano il simbolo. [`test_rejects_archives_that_do_not_match_the_commit`](../../../tests/test_release_packaging.py#L132), [`test_rejects_corrupt_gzip_checksum`](../../../tests/test_release_packaging.py#L146).

### package_release

`package_release(root: Path, revision: str, output: Path) -> tuple[str, list[str]]`

[`Sorgente`](../../../scripts/package_release.py#L130) (righe 130–138).

Chiamate nel corpo. `output.name.endswith`, `ValueError`, `read_sources`, `build_archive`, `verify_archive`, `output.open`, `stream.write`, `hashlib.sha256(payload).hexdigest`, `hashlib.sha256`.

Chiamanti per nome. [`main`](../../../scripts/package_release.py#L141), [`packaging_check`](../../../scripts/verify_offline.py#L240).

Test che richiamano il simbolo. [`test_exact_commit_is_independent_of_git_and_checkout_configuration`](../../../tests/test_release_packaging.py#L62), [`test_rejects_unsafe_committed_inputs`](../../../tests/test_release_packaging.py#L94), [`test_rejects_symlink_blob_without_following_it`](../../../tests/test_release_packaging.py#L104), [`test_rejects_abbreviated_revision_and_preserves_existing_output`](../../../tests/test_release_packaging.py#L113).

### main

`main() -> int`

[`Sorgente`](../../../scripts/package_release.py#L141) (righe 141–153).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `package_release`, `Path.cwd`, `parser.exit`, `'\n'.join`.

## scripts/verify_offline.py

[Apri il file](../../../scripts/verify_offline.py)

Import dichiarati. `import argparse`, `import importlib.util`, `import json`, `import os`, `import shutil`, `import subprocess`, `import sys`, `import tempfile`, `import xml.etree.ElementTree as ET`, `from pathlib import Path`, `from package_release import git, package_release`.

Costanti. `ROOT`, `POWERSHELL_PARSER`.

### offline_env

`offline_env(scratch: Path) -> dict[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L49) (righe 49–75).

Chiamate nel corpo. `key.upper`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### run

`run(command: list[str], env: dict[str, str] | None=None) -> subprocess.CompletedProcess[str]`

[`Sorgente`](../../../scripts/verify_offline.py#L78) (righe 78–89).

Chiamate nel corpo. `subprocess.run`.

Chiamanti per nome. [`command_check`](../../../scripts/verify_offline.py#L96), [`pytest_check`](../../../scripts/verify_offline.py#L103), [`ignored_output`](../../../src/viralclip/dataset.py#L347), [`_restic`](../../../src/viralclip/operations.py#L169), [`_service_state`](../../../src/viralclip/operations.py#L272).

Test che richiamano il simbolo. [`test_cli_exports_separate_audit_files_and_blackout_coverage`](../../../tests/test_dataset.py#L181), [`test_health_preflight_reports_both_results_under_errexit`](../../../tests/test_dual_collector_runbook.py#L35), [`test_prepare_generates_local_xml_without_opening_database`](../../../tests/test_windows_supervision.py#L50), [`test_pause_interrupts_and_runs_synthetic_cleanup`](../../../tests/test_windows_supervision.py#L148), [`test_real_cross_process_database_lock_rejects_second_owner`](../../../tests/test_windows_supervision.py#L216).

### details

`details(result: subprocess.CompletedProcess[str]) -> str`

[`Sorgente`](../../../scripts/verify_offline.py#L92) (righe 92–93).

Chiamate nel corpo. `'\n'.join`, `(result.stdout + result.stderr).strip().splitlines`, `(result.stdout + result.stderr).strip`.

Chiamanti per nome. [`command_check`](../../../scripts/verify_offline.py#L96), [`pytest_check`](../../../scripts/verify_offline.py#L103).

### command_check

`command_check(command: list[str], env: dict[str, str] | None, success: str) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L96) (righe 96–100).

Chiamate nel corpo. `run`, `details`.

Chiamanti per nome. [`ruff_check`](../../../scripts/verify_offline.py#L140), [`git_check`](../../../scripts/verify_offline.py#L161), [`bash_check`](../../../scripts/verify_offline.py#L202), [`powershell_check`](../../../scripts/verify_offline.py#L223).

### pytest_check

`pytest_check(scratch: Path, env: dict[str, str]) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L103) (righe 103–137).

Chiamate nel corpo. `importlib.util.find_spec`, `run`, `xml.is_file`, `details`, `ET.parse(xml).iter`, `ET.parse`, `case.find`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### ruff_check

`ruff_check(arguments: list[str], env: dict[str, str]) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L140) (righe 140–158).

Chiamate nel corpo. `importlib.util.find_spec`, `command_check`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### git_check

`git_check() -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L161) (righe 161–188).

Chiamate nel corpo. `command_check`, `git`, `ignored.count`, `bytes`.

### source_paths

`source_paths(*patterns: str) -> list[str]`

[`Sorgente`](../../../scripts/verify_offline.py#L191) (righe 191–199).

Chiamate nel corpo. `git`, `os.fsdecode`, `paths.split`, `(ROOT / path).is_symlink`, `ValueError`.

Chiamanti per nome. [`bash_check`](../../../scripts/verify_offline.py#L202), [`powershell_check`](../../../scripts/verify_offline.py#L223).

### bash_check

`bash_check(env: dict[str, str]) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L202) (righe 202–220).

Chiamate nel corpo. `shutil.which`, `Path`, `bundled.is_file`, `source_paths`, `command_check`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### powershell_check

`powershell_check(scratch: Path, env: dict[str, str]) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L223) (righe 223–237).

Chiamate nel corpo. `shutil.which`, `manifest.write_text`, `json.dumps`, `source_paths`, `parser.write_text`, `command_check`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### packaging_check

`packaging_check(scratch: Path) -> tuple[str, str]`

[`Sorgente`](../../../scripts/verify_offline.py#L240) (righe 240–246).

Chiamate nel corpo. `git(ROOT, 'rev-parse', 'HEAD').decode().strip`, `git(ROOT, 'rev-parse', 'HEAD').decode`, `git`, `package_release`.

Chiamanti per nome. [`main`](../../../scripts/verify_offline.py#L249).

### main

`main() -> int`

[`Sorgente`](../../../scripts/verify_offline.py#L249) (righe 249–279).

Chiamate nel corpo. `argparse.ArgumentParser`, `parser.add_argument`, `parser.parse_args`, `tempfile.TemporaryDirectory`, `Path`, `offline_env`, `pytest_check`, `ruff_check`, `bash_check`, `powershell_check`, `packaging_check`, `checks.items`, `check`, `', '.join`, `results.count`.
