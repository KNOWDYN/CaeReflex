# CaeReflex

## The problem

Computer-aided engineering (CAE) projects often leave useful evidence scattered across solver folders, mesh files, result files, scripts, notes, and literature searches. A Gmsh geometry, an OpenFOAM case, a VTK/ParaView output, and a DOI search can all describe the same engineering question, but they usually live in formats that general-purpose LLM agents cannot safely inspect or cite without help.

That creates a practical gap: an engineer may have simulation artefacts on disk, while a Custom GPT, Claude agent, or other LLM assistant only sees a partial explanation typed into chat.

## What the problem impedes

Without a structured evidence layer, agents and reviewers can struggle to:

- identify which CAE tools and file formats are present;
- summarize case intent, detected inputs, and result artefacts consistently;
- distinguish detected evidence from assumptions;
- preserve provenance for where each piece of information came from;
- surface inspection warnings before a human relies on the case;
- connect a simulation case to related DOI/CrossRef metadata;
- export agent-ready context, human-readable reports, and BibTeX references; and
- avoid unsafe overclaims such as saying a simulation is validated, certified, converged, mesh-independent, or safe for final design.

## The solution

CaeReflex is a source-available Python package that turns Gmsh, OpenFOAM, and ParaView/VTK-compatible simulation artefacts into structured, agent-readable, provenance-aware, CrossRef-grounded engineering cases.

It can be used from the command line, as a local REST/OpenAPI service, or as a data-preparation layer for an LLM agent workflow. The package inspects CAE artefacts in read-only mode, creates a `ReflexCase` JSON record, exports agent context and reports, and can attach CrossRef literature metadata when explicitly requested.

> **Safety boundary:** CaeReflex is an inspection and documentation aid. It does **not** run solvers, validate simulations, certify engineering results, prove convergence, assess mesh adequacy, or replace qualified engineering judgement.

## What the solution achieves

CaeReflex helps you give an LLM agent a safer, more complete view of an engineering case:

- a normalized case identifier and summary;
- detected CAE formats and tools;
- extracted metadata from Gmsh, OpenFOAM, and VTK/ParaView-compatible artefacts;
- inspection status and warnings;
- provenance events describing what was inspected or exported;
- an agent-readable context object for Custom GPTs, Claude, and other agents;
- Markdown reports for human review;
- optional CrossRef literature context, DOI metadata, abstracts when available, and BibTeX export;
- REST/OpenAPI endpoints for tool-calling agents; and
- explicit guardrails against overclaiming validation or certification.

## Supported artefacts

- Gmsh `.geo` files in core mode; `.msh` files with optional mesh extras.
- OpenFOAM-like case folders through read-only text inspection.
- VTK/ParaView-compatible result files with safe fallback behaviour.
- CrossRef DOI metadata and available abstracts when explicitly requested.

## Install options

Install the package from a local checkout:

```bash
pip install -e .
```

Install optional extras as needed:

```bash
pip install -e ".[server]"   # REST/OpenAPI server for agent actions
pip install -e ".[mesh]"     # optional mesh support
pip install -e ".[vtk]"      # optional VTK/PyVista support
pip install -e ".[gmsh]"     # optional Gmsh Python support
pip install -e ".[all,dev]"  # everything plus test dependencies
```

## Full hands-on example: localhost CaeReflex + Custom GPT or Claude + CrossRef

This example starts with a fresh clone, serves CaeReflex on localhost, exposes it securely for a browser-based agent, connects either a Custom GPT or Claude-style agent, imports a bundled OpenFOAM example, and attaches CrossRef research metadata.

### Prerequisites

You need:

- Python 3.10 or newer;
- `git`;
- a browser;
- a ChatGPT account with Custom GPT Actions if testing a Custom GPT;
- a Claude environment that can call tools from an OpenAPI schema, or a developer-mediated Claude tool wrapper;
- an HTTPS tunnel for browser-hosted agents, because Custom GPT Actions and most hosted agent systems cannot call `http://localhost` directly.

For a quick tunnel, use one of:

- Cloudflare Tunnel;
- ngrok;
- GitHub Codespaces port forwarding;
- another HTTPS reverse proxy that forwards to `localhost:8765`.

### 1. Clone and install CaeReflex

```bash
git clone https://github.com/YOUR_ORG_OR_USER/CaeReflex.git
cd CaeReflex
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[all,dev]"
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### 2. Confirm the CLI works

```bash
caereflex version
caereflex examples list
```

You should see the installed package version and the bundled example names.

### 3. Generate a local example case from the CLI

```bash
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal \
  --out caereflex.json \
  --agent-context agent_context.json \
  --report case_report.md
```

This creates:

- `caereflex.json` — the full structured ReflexCase;
- `agent_context.json` — compact agent-readable context;
- `case_report.md` — a human-readable Markdown report.

### 4. Attach CrossRef literature metadata from the CLI

Use a focused query that matches the simulation domain. For the bundled cavity-style example, you can start with:

```bash
caereflex crossref attach caereflex.json \
  --query "lid driven cavity CFD OpenFOAM" \
  --limit 5 \
  --mailto your.email@example.com \
  --out caereflex.with_literature.json
```

Then export BibTeX references:

```bash
caereflex export bibtex caereflex.with_literature.json --out references.bib
```

If you want a deterministic offline CrossRef-style test, use the bundled mock data:

```bash
caereflex crossref attach examples/crossref_context/sample_case.json \
  --mock-response examples/crossref_context/mock_crossref_response.json \
  --out caereflex.with_literature.json
```

### 5. Start the localhost REST/OpenAPI server

```bash
caereflex serve --host 127.0.0.1 --port 8765 --workspace .
```

Open these URLs in your browser:

- `http://127.0.0.1:8765/health`
- `http://127.0.0.1:8765/version`
- `http://127.0.0.1:8765/openapi.yaml`

The OpenAPI document is what browser-based agents use to discover CaeReflex actions.

### 6. Expose localhost through HTTPS for hosted agents

A Custom GPT normally cannot call `http://127.0.0.1:8765` on your machine. You need an HTTPS URL that forwards to the local server.

Example with ngrok:

```bash
ngrok http 8765
```

Example with Cloudflare Tunnel:

```bash
cloudflared tunnel --url http://127.0.0.1:8765
```

Copy the generated HTTPS URL, for example:

```text
https://your-tunnel.example.trycloudflare.com
```

Your agent schema URL will be:

```text
https://your-tunnel.example.trycloudflare.com/openapi.yaml
```

> **Security note:** For public or team use, run CaeReflex with an API key on a non-localhost host, restrict the workspace, and do not expose private simulation folders or proprietary data through a public tunnel.

### 7A. Connect a Custom GPT to CaeReflex

In ChatGPT:

1. Open **Explore GPTs**.
2. Select **Create**.
3. Open **Configure**.
4. Name the GPT, for example `CaeReflex Engineering Case Reviewer`.
5. Add an action.
6. Import the OpenAPI schema from your tunnel URL:

   ```text
   https://your-tunnel.example.trycloudflare.com/openapi.yaml
   ```

7. If you run CaeReflex with an external API key, configure action authentication with this header:

   ```text
   x-api-key
   ```

8. Add these Custom GPT instructions:

```text
You are a CaeReflex engineering-case reviewer.

Use CaeReflex actions to inspect and summarize CAE artefacts, retrieve agent context, review inspection flags, and summarize optional CrossRef literature metadata.

Always call the health endpoint first when beginning a live API workflow. When the user provides a case path, import the case, retrieve the agent context, retrieve inspection flags, and then summarize the result.

Never claim that CaeReflex validates a simulation, certifies engineering safety, proves convergence, assesses mesh adequacy, confirms physical correctness, or replaces qualified engineering judgement.

Separate detected evidence from assumptions. Clearly identify warnings, missing evidence, provenance, and recommended human follow-up checks.

Only use CrossRef search or attach when the user explicitly asks for literature context. Treat CrossRef records as metadata and available abstracts only; do not claim to have read full papers unless full text is provided.
```

9. Test with this prompt:

```text
Check whether the CaeReflex API is healthy. Then import examples/openfoam_cavity_minimal, summarize the agent context, list inspection flags, and tell me what a qualified engineer would still need to verify.
```

10. Test CrossRef through the agent with:

```text
Attach CrossRef literature context to the imported case using the query "lid driven cavity CFD OpenFOAM" with a limit of 5, then summarize the DOI metadata without claiming validation.
```

### 7B. Connect a Claude agent to CaeReflex

Claude connection depends on the environment you use. The safe pattern is the same: give Claude a tool wrapper or OpenAPI-derived tool definitions that call the CaeReflex REST endpoints.

#### Claude option 1: OpenAPI-capable agent environment

If your Claude environment can import an OpenAPI schema:

1. Start CaeReflex and the HTTPS tunnel as shown above.
2. Import:

   ```text
   https://your-tunnel.example.trycloudflare.com/openapi.yaml
   ```

3. Configure the optional `x-api-key` header if your server requires it.
4. Add this system/developer instruction:

```text
You are using CaeReflex as a read-only CAE evidence inspection service.

Use the health endpoint before live workflows. Use case import, agent-context, inspection-flags, literature, CrossRef attach/search, and export endpoints only as needed.

Do not claim validation, certification, convergence, mesh adequacy, physical correctness, or design safety. Explain findings as detected metadata, inspection results, provenance, warnings, and literature metadata.
```

5. Test with:

```text
Use the CaeReflex tool to import examples/openfoam_cavity_minimal from the configured workspace. Summarize the case, show inspection warnings, and recommend next engineering checks.
```

#### Claude option 2: developer-mediated tool wrapper

If Claude cannot import OpenAPI directly, create a small wrapper in your application that exposes these operations to Claude:

- `health()` → `GET /health`
- `import_engineering_case(path, adapter="auto", attach_crossref=false)` → `POST /cases/import`
- `get_agent_context(case_id)` → `GET /cases/{case_id}/agent-context`
- `get_inspection_flags(case_id)` → `GET /cases/{case_id}/inspection-flags`
- `crossref_attach(case_id, query, limit)` → `POST /cases/{case_id}/crossref/attach`
- `get_literature(case_id)` → `GET /cases/{case_id}/literature`

Minimal Python wrapper example:

```python
import httpx

BASE_URL = "https://your-tunnel.example.trycloudflare.com"
API_KEY = None  # or "your-api-key"


def headers():
    return {"x-api-key": API_KEY} if API_KEY else {}


def health():
    return httpx.get(f"{BASE_URL}/health", headers=headers()).json()


def import_engineering_case(path: str, adapter: str = "auto", attach_crossref: bool = False):
    payload = {
        "path": path,
        "adapter": adapter,
        "attach_crossref": attach_crossref,
        "return_agent_context": True,
    }
    return httpx.post(f"{BASE_URL}/cases/import", json=payload, headers=headers()).json()


def get_agent_context(case_id: str):
    return httpx.get(f"{BASE_URL}/cases/{case_id}/agent-context", headers=headers()).json()


def get_inspection_flags(case_id: str):
    return httpx.get(f"{BASE_URL}/cases/{case_id}/inspection-flags", headers=headers()).json()


def crossref_attach(case_id: str, query: str, limit: int = 5):
    payload = {"query": query, "limit": limit, "include_case_tags": True}
    return httpx.post(
        f"{BASE_URL}/cases/{case_id}/crossref/attach",
        json=payload,
        headers=headers(),
    ).json()


def get_literature(case_id: str):
    return httpx.get(f"{BASE_URL}/cases/{case_id}/literature", headers=headers()).json()
```

Tool-use instruction for Claude:

```text
Call import_engineering_case first when the user asks about a simulation folder. Then call get_agent_context and get_inspection_flags. Call crossref_attach only when the user asks for related research. Never claim validation or certification.
```

### 8. REST calls you can test manually

Import a case:

```bash
curl -X POST "http://127.0.0.1:8765/cases/import" \
  -H "Content-Type: application/json" \
  -d '{"path":"examples/openfoam_cavity_minimal","adapter":"auto","attach_crossref":false,"return_agent_context":true}'
```

List cases:

```bash
curl "http://127.0.0.1:8765/cases"
```

Retrieve agent context, replacing `CASE_ID` with the ID returned by import:

```bash
curl "http://127.0.0.1:8765/cases/CASE_ID/agent-context"
```

Retrieve inspection flags:

```bash
curl "http://127.0.0.1:8765/cases/CASE_ID/inspection-flags"
```

Attach CrossRef metadata:

```bash
curl -X POST "http://127.0.0.1:8765/cases/CASE_ID/crossref/attach" \
  -H "Content-Type: application/json" \
  -d '{"query":"lid driven cavity CFD OpenFOAM","include_case_tags":true,"limit":5}'
```

Retrieve literature context:

```bash
curl "http://127.0.0.1:8765/cases/CASE_ID/literature"
```

## What CaeReflex can give users through an agent

Through a Custom GPT, Claude agent, or another LLM tool-calling workflow, CaeReflex can provide:

- **Case overview:** stable case ID, summary, detected formats, detected tools, and inspection status.
- **Agent-readable context:** compact JSON designed for LLM workflows.
- **Inspection warnings:** flags for missing, unsupported, partial, or potentially risky evidence.
- **Provenance:** records of inspection and export events.
- **Artefact inventory:** detected files and metadata from supported CAE folders and files.
- **OpenFOAM awareness:** read-only inspection of OpenFOAM-like case folders.
- **Gmsh awareness:** inspection of `.geo` files and optional `.msh` mesh files.
- **VTK/ParaView awareness:** inspection of VTK-compatible result files with safe fallback behaviour.
- **Markdown reports:** human-readable engineering case summaries.
- **JSON exports:** full ReflexCase records for downstream tools.
- **BibTeX export:** references generated from attached literature records.
- **REST/OpenAPI actions:** endpoints that browser-hosted agents can call as tools.
- **Safety framing:** reminders that inspection is not validation, certification, or engineering sign-off.

## What CrossRef integration can give users

When explicitly requested, CrossRef integration can add research context such as:

- DOI records related to a case or query;
- article titles, authors, journals, publishers, and publication dates when available;
- abstracts when available from CrossRef metadata;
- generated literature-context summaries;
- case-tag-informed searches;
- BibTeX-ready reference exports;
- traceability between simulation context and related research metadata; and
- safer agent answers that distinguish literature metadata from engineering proof.

CrossRef results should be treated as metadata and available abstracts, not as a guarantee that the full paper was read or that the simulation is correct.

## Quickstart

```bash
caereflex examples list
caereflex examples run openfoam_cavity_minimal
caereflex inspect examples/openfoam_cavity_minimal --out caereflex.json
caereflex export agent-context caereflex.json --out agent_context.json
caereflex export markdown caereflex.json --out case_report.md
```

## Supported files

- `QUICKSTART.md` — short offline and mock-CrossRef commands.
- `docs/CLI.md` — CLI command overview and exit codes.
- `docs/REST_API.md` — REST endpoint overview.
- `docs/AGENT_INTEGRATION.md` — agent integration modes and safety rules.
- `docs/REFLEXCASE_SCHEMA.md` — ReflexCase schema reference.
- `docs/EXAMPLES.md` — bundled example notes.
- `docs/LICENSING.md` — license overview.

## Licence summary

CaeReflex is source-available. Academic research, teaching, and non-commercial evaluation are free. Commercial use requires a paid commercial licence. CaeReflex is not released under an OSI-approved open-source licence.

See `LICENSE.md`, `ACADEMIC_USE.md`, and `COMMERCIAL_LICENSE.md`.
