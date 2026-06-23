# CaeReflex CLI

The CaeReflex command-line interface turns local CAE artefacts into agent-readable JSON, Markdown reports, BibTeX references, and optional REST/OpenAPI workflows.

## Installation assumptions

Run CLI examples from a checkout installed in editable mode:

```bash
pip install -e .
```

Install optional extras only when the workflow needs them:

```bash
pip install -e ".[server]"   # REST/OpenAPI server: caereflex serve
pip install -e ".[mesh]"     # optional mesh-file support
pip install -e ".[vtk]"      # optional VTK/PyVista readers
pip install -e ".[gmsh]"     # optional Gmsh Python support
pip install -e ".[all,dev]"  # all runtime extras plus test dependencies
```

Core inspection works without these extras where adapters have safe text/fallback paths. Commands that require missing optional packages exit with the dependency exit code when the missing dependency is detected.

## Global command shape

All CLI commands use this shape:

```bash
caereflex COMMAND [ARGUMENTS] [OPTIONS]
```

Use `caereflex --help`, `caereflex COMMAND --help`, or nested help such as `caereflex crossref search --help` to inspect the active installation.

## Common output behavior

### Human output vs. `--json`

Most commands print concise human-readable status by default. Commands that accept `--json` print the command result metadata as JSON to stdout instead.

For inspection-style commands, the JSON/human CLI status is separate from the case JSON file written with `--out`. In other words, `--json` controls stdout formatting; `--out` controls a file written to disk.

### Output files

Commands that take `--out PATH` write their primary artefact to that path. Existing files at the same path are overwritten. Parent directories should already exist unless the service called by the command creates them for that command.

Default output paths are command-specific:

| Command | Default output |
| --- | --- |
| `inspect` | `caereflex.json` |
| `inspect-gmsh` | `gmsh_case.json` |
| `inspect-openfoam` | `openfoam_case.json` |
| `inspect-vtk` | `vtk_case.json` |
| `crossref attach` | `caereflex.with_literature.json` |
| `export agent-context` | `agent_context.json` |
| `export markdown` | `case_report.md` |
| `export bibtex` | `references.bib` |
| `examples run` | output directory `build` |

### Inspection limits

The auto-detecting `inspect` command exposes scan safety limits:

```bash
caereflex inspect PATH \
  --max-file-size-mb 25 \
  --max-scan-depth 3 \
  --max-scan-files 500
```

- `--max-file-size-mb` limits how large an individual file may be before CaeReflex skips or downscopes inspection.
- `--max-scan-depth` limits recursive directory traversal depth.
- `--max-scan-files` limits how many files are scanned.

These limits are intended to keep local inspections predictable and agent-safe. Adapter-specific commands currently use their service defaults rather than exposing these three limit flags.

## Commands

### `caereflex version`

Print the installed CaeReflex version:

```bash
caereflex version
```

### `caereflex inspect`

Inspect a simulation path with adapter auto-detection:

```bash
caereflex inspect PATH \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

This command:

1. inspects `PATH` using automatic adapter detection;
2. writes the full ReflexCase JSON to `--out`;
3. optionally writes an agent context JSON file when `--agent-context` is provided;
4. optionally writes a Markdown report when `--report` is provided;
5. prints status, case ID, summary, outputs, and warnings unless `--json` is used.

Useful options:

```bash
caereflex inspect PATH --json
caereflex inspect PATH --attach-crossref --crossref-limit 10
caereflex inspect PATH --max-file-size-mb 25 --max-scan-depth 3 --max-scan-files 500
```

`--attach-crossref` performs an explicit CrossRef attachment during inspection and uses `--crossref-limit` to limit the number of returned literature records.

### `caereflex inspect-gmsh`

Force the Gmsh adapter and write a Gmsh-focused case JSON:

```bash
caereflex inspect-gmsh PATH --out gmsh_case.json
```

Use this when the input is known to be a Gmsh case or when auto-detection is not desired. Add `--json` to emit machine-readable command status to stdout.

### `caereflex inspect-openfoam`

Force the OpenFOAM adapter and write an OpenFOAM-focused case JSON:

```bash
caereflex inspect-openfoam PATH --out openfoam_case.json
```

OpenFOAM inspection is descriptive: it reads case files and dictionaries that CaeReflex can safely inspect. It does not run OpenFOAM solvers.

### `caereflex inspect-vtk`

Force the VTK adapter and write a VTK-focused case JSON:

```bash
caereflex inspect-vtk PATH --out vtk_case.json
```

Install `.[vtk]` when you need optional PyVista/VTK-backed behavior. Core fallback behavior may still fingerprint supported VTK-family files when optional readers are unavailable.

## CrossRef commands

CrossRef commands are explicit metadata lookups. They retrieve DOI metadata and available abstracts where provided by CrossRef; they do not read full papers, scrape publishers, inspect simulations for correctness, or certify engineering results.

### `caereflex crossref search`

Search CrossRef using an existing case JSON plus an optional query:

```bash
caereflex crossref search CASE_JSON \
  --query "lid driven cavity CFD" \
  --limit 10 \
  --out crossref.json
```

The command loads `CASE_JSON`, builds a CrossRef search context, and writes search results to `--out` when provided. Without `--out`, results are summarized on stdout; with `--json`, stdout uses JSON-formatted command metadata.

Additional options include:

```bash
caereflex crossref search CASE_JSON --mailto user@example.com
caereflex crossref search CASE_JSON --include-case-tags / --no-include-case-tags
```

### `caereflex crossref attach`

Attach CrossRef literature metadata to a case JSON and save an updated ReflexCase:

```bash
caereflex crossref attach CASE_JSON \
  --query "lid driven cavity CFD" \
  --out caereflex.with_literature.json
```

Use `--limit 10` to control the number of records considered and `--mailto user@example.com` when you want to identify your CrossRef requests.

### Deterministic `--mock-response`

Both CrossRef commands support `--mock-response PATH`:

```bash
caereflex crossref search CASE_JSON \
  --query "mesh independence" \
  --mock-response tests/fixtures/crossref_response.json \
  --out crossref.json

caereflex crossref attach CASE_JSON \
  --query "mesh independence" \
  --mock-response tests/fixtures/crossref_response.json \
  --out caereflex.with_literature.json
```

Use this option for deterministic examples, documentation, and tests. The command reads the supplied mock response instead of relying on a live CrossRef network response.

## Export commands

Export commands transform an existing ReflexCase JSON into another representation.

### Agent context JSON

```bash
caereflex export agent-context CASE_JSON --out agent_context.json
```

This writes compact agent-oriented context for tool-calling or file-context workflows.

### Markdown report

```bash
caereflex export markdown CASE_JSON --out case_report.md
```

This writes a human-readable case report suitable for review or inclusion in project notes.

### BibTeX references

```bash
caereflex export bibtex CASE_JSON --out references.bib
```

This writes BibTeX entries for literature metadata already attached to the case.

All export commands accept `--json` to print JSON-formatted command status to stdout.

## Server command

Start the REST/OpenAPI server:

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace .
```

Install the server extra first:

```bash
pip install -e ".[server]"
```

The server prints the workspace and OpenAPI URL, then runs Uvicorn. The workspace bounds file-oriented operations exposed through the API.

### API-key requirement outside localhost

Binding to `127.0.0.1` or `localhost` is treated as local mode and does not require an API key. Binding to any other host requires `--api-key`:

```bash
caereflex serve --host 0.0.0.0 --port 8765 --workspace . --api-key "$CAEREFLEX_API_KEY"
```

If you bind outside localhost without an API key, the command exits with the security exit code (`5`). This protects externally reachable servers from unauthenticated use.

## Example commands

List bundled examples:

```bash
caereflex examples list
```

Run a bundled example into an output directory:

```bash
caereflex examples run gmsh_minimal --out-dir build
```

`examples list` accepts `--json`. `examples run` accepts `--json` and writes example artefacts under `--out-dir`.

## Exit codes

`caereflex/cli/main.py` defines these process exit codes:

| Code | Name | Meaning |
| ---: | --- | --- |
| `0` | `success` | Command completed successfully. |
| `1` | `failed` | Command failed or returned a non-success status not otherwise mapped by `_exit_for`. |
| `2` | `partial_success` | Inspection completed with partial success and warnings. |
| `3` | `unsupported` | Unsupported input or format. Defined for CLI use, but not currently emitted by `_exit_for`. |
| `4` | `dependency` | Required optional dependency is missing. Currently used by `serve` when server imports fail. |
| `5` | `security` | Security/path/API-key requirement failure. Currently used by `serve` when binding outside localhost without `--api-key`. |

Commands that currently call `_exit_for` are:

- `caereflex inspect`
- `caereflex inspect-gmsh`
- `caereflex inspect-openfoam`
- `caereflex inspect-vtk`

For those commands, `_exit_for` maps `success` to `0`, `partial_success` to `2`, and any other status to `1`. Although `unsupported`, `dependency`, and `security` are defined in `EXIT`, adapter inspection failures that surface through `_exit_for` currently exit as `1` unless the command handles them separately.

Other commands generally complete with Typer's default success behavior unless they raise a specific `typer.Exit`, such as the server dependency and API-key checks described above.

## Troubleshooting

### Unsupported paths or formats

Symptoms:

- inspection status is `failed`;
- CLI exits with code `1`;
- warnings mention unsupported input, no matching adapter, or insufficient recognizable files.

What to try:

1. Confirm the path exists and is inside the intended workspace.
2. Use an adapter-specific command when you know the format, for example `inspect-gmsh`, `inspect-openfoam`, or `inspect-vtk`.
3. Increase scan limits for large or deeply nested cases:

   ```bash
   caereflex inspect PATH --max-scan-depth 6 --max-scan-files 2000 --max-file-size-mb 100
   ```

4. Read the inspection flags in the CLI output or in the generated case JSON before drawing conclusions. CaeReflex reports detected evidence; it does not certify the simulation or inspect it for correctness.

### Missing optional dependencies

Symptoms:

- `caereflex serve` prints a message asking for `[server]` extras and exits with code `4`;
- VTK, mesh, or Gmsh features are unavailable or reduced to fallback behavior.

Install the relevant extra:

```bash
pip install -e ".[server]"
pip install -e ".[mesh]"
pip install -e ".[vtk]"
pip install -e ".[gmsh]"
```

For a development environment with all optional features:

```bash
pip install -e ".[all,dev]"
```

### Partial-success warnings

Symptoms:

- command exits with code `2`;
- status is `partial_success`;
- warnings are printed in yellow or listed in JSON output.

Partial success means CaeReflex produced useful output but skipped, downscoped, or could not interpret part of the input. Review the warnings and generated outputs. Common causes include scan limits, large files, missing optional readers, mixed-format workspaces, or files that are intentionally unsupported.

### Server API-key failures

Symptoms:

- `caereflex serve --host 0.0.0.0 ...` exits with code `5`;
- message says an API key is mandatory outside localhost.

Either bind locally:

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace .
```

or provide an API key for externally reachable bindings:

```bash
caereflex serve --host 0.0.0.0 --port 8765 --workspace . --api-key "$CAEREFLEX_API_KEY"
```
