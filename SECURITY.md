# Security

Security reports: [ipcontrol@knowdyn.co.uk](mailto:ipcontrol@knowdyn.co.uk)

CaeReflex is source-available software owned and licensed by **KNOWDYN LTD (UK)**. This document defines the supported versions, reporting process, deployment assumptions, execution-runtime boundary and known limitations.

## Supported versions

| Version | Security support | Status |
| --- | ---: | --- |
| `2.0.0a1` | Supported | Active 2.x alpha line |
| `1.0.0` | Critical fixes only | Maintenance during the alpha transition |
| Earlier versions | Not supported | Upgrade required |

The `2.0.0a1` package uses ReflexCase schema `1.0` and backend-neutral contract `2.0-alpha.3`. Reports should identify all three versions where relevant.

## Reporting security issues

Report suspected vulnerabilities privately to [ipcontrol@knowdyn.co.uk](mailto:ipcontrol@knowdyn.co.uk). Include, where possible:

1. the affected CaeReflex, contract and schema versions;
2. operating system and Python version;
3. installation method and optional dependencies;
4. command, REST endpoint or execution backend used;
5. steps to reproduce, expected behaviour and observed behaviour;
6. whether the issue affects CLI, REST, CrossRef, discovery, deep execution, artefacts, arrays or exports;
7. safe minimal fixtures, logs or tracebacks;
8. whether the issue is already public.

Do not send proprietary simulation files, credentials, API keys, private tokens, personal data or controlled technical data unless specifically agreed in writing.

## Security scope

Security issues include:

- path traversal or unrestricted filesystem access;
- exposure of absolute local paths, secrets or credentials;
- unintended shell, solver, mesher or source-code execution;
- unintended mutation of inspected engineering sources;
- unsafe REST exposure or missing API-key enforcement outside localhost;
- hidden network calls during ordinary inspection;
- raw simulation data being sent to external services;
- malformed or oversized files escaping configured limits;
- native-reader crashes terminating the parent service;
- content-addressed artefact integrity failures;
- array queries bypassing operation or output limits;
- misleading agent outputs claiming validation, convergence, certification or design safety.

Feature requests, commercial licensing, scientific disagreement and engineering review are not security issues unless they create a concrete security or safety vulnerability.

## Localhost-first deployment

CaeReflex is localhost-first:

```bash
caereflex serve --host 127.0.0.1 --port 8765
```

Non-localhost serving requires an API key and a restricted workspace:

```bash
caereflex serve --host 0.0.0.0 --port 8765 --api-key "$CAEREFLEX_API_KEY" --workspace /trusted/workspace
```

An internet-facing or institutional deployment must add HTTPS termination, access control, logging policy, request limits, dependency maintenance and operational review. CaeReflex does not provide OAuth, user accounts, RBAC, multi-tenant isolation, enterprise identity or a secure hosted SaaS boundary.

## Filesystem and source policy

CaeReflex performs read-only inspection. It must not:

- run solvers, meshers or ParaView;
- expose shell-command endpoints;
- repair CAD or meshes;
- mutate source simulation files;
- write into inspected source directories unless the user explicitly chooses an output path;
- follow traversal outside an allowed workspace;
- expose unrestricted filesystem browsing through REST.

Agent-facing outputs use safe relative paths, identifiers or summaries rather than absolute local paths.

## Gate 5A execution runtime

Deep inspection runs through a dedicated subprocess worker. The default runtime provides:

- explicit `InspectionPlan`, `InspectionBudget` and `ExecutionPolicy` inputs;
- allow-listed built-in or Python entry-point execution backends;
- a sanitised environment by default;
- Python-level network guards when networking is disabled;
- Python-level shell and child-process guards when subprocess access is disabled;
- POSIX address-space and CPU limits where supported;
- parent-enforced wall-time termination;
- bounded serialized result size;
- selected-path containment;
- before-and-after source snapshots;
- persistent job, result and parser-attempt records;
- separate state and artefact directories.

### Important limitation

The default worker is **not a complete operating-system sandbox**. Native libraries can potentially bypass Python-level socket, process or filesystem guards. POSIX resource limits are unavailable or different on some platforms. Source snapshots detect mutation but cannot automatically restore a changed source.

Hostile, proprietary or safety-critical inputs may require stronger external isolation such as a container, virtual machine, restricted operating-system account or institutionally managed worker. Future native backends must declare their isolation requirements honestly.

## Artefact and lazy-array security

Generated heavy payloads are stored outside ReflexCase JSON under `.caereflex/artifacts/sha256/` and addressed by SHA-256. The local store verifies payload integrity before use and rejects paths outside its configured root.

`ArrayRef` objects expose metadata and declared operations rather than unrestricted file access. Core array queries enforce:

- provider and format compatibility;
- permitted-operation lists;
- slice and component bounds;
- maximum returned element counts;
- streaming reductions rather than full JSON materialisation.

Users should not manually edit `.caereflex` state. Preserve logs and recreate state from trusted sources after an integrity failure.

## Solver, shell and mutation policy

CaeReflex does not expose commands or endpoints for:

- OpenFOAM execution;
- Gmsh meshing execution;
- ParaView launch or automation;
- general shell execution;
- source-file mutation;
- CAD or mesh repair;
- design optimisation;
- autonomous engineering decisions.

Any behaviour that enables unintended execution or mutation should be reported as a security issue.

## CrossRef privacy and network use

CrossRef is contacted only when explicitly requested through a CrossRef command, action or `--attach-crossref` option. Ordinary discovery, inspection, deep execution, array queries and exports must not make hidden CrossRef calls.

Only generated/user-supplied query strings and API parameters are sent. Raw simulation files, full case folders, proprietary artefacts, secrets and tokens must not be transmitted. CrossRef outputs are metadata and available-abstract context, not validation evidence.

## Agent-facing output safety

Agent outputs must preserve distinctions among extracted, inferred, generated, user-supplied and external metadata. CaeReflex does not validate simulations, prove convergence, assess mesh adequacy, certify engineering results or establish design safety.

A generated output exposing secrets, unrestricted local paths, excessive raw arrays or misleading engineering claims should be treated as a security or safety issue.

## Secrets and credentials

Do not place credentials, private keys, tokens, passwords or commercial licence secrets inside inspected workspaces. CaeReflex is not a secrets scanner. API keys must not be committed to repositories, examples, reports or generated outputs.

## Dependency security and licensing

The core install remains intentionally smaller than native-reader installations. Gmsh, meshio, VTK and PyVista are optional and governed by their own security and licence terms. Native readers introduced after Gate 5A must remain separately testable and installable.

Users are responsible for maintaining a secure Python environment and updating third-party dependencies according to their own policies. See `THIRD_PARTY_NOTICES.md` where applicable.

## Example and test data

Bundled fixtures must be small, offline, reproducible and legally clean. Core tests must not require live CrossRef access, solver installation, Gmsh, ParaView, large downloads or proprietary data.

Fault-injection execution backends are disabled unless `CAEREFLEX_ENABLE_TEST_BACKENDS=1` is explicitly set in a test environment.

## Known limitations

CaeReflex is not:

- a complete sandbox or container runtime;
- a malware or secrets scanner;
- a secure multi-tenant platform;
- an engineering validator or certification system;
- guaranteed to parse every grammar feature or malformed native file;
- a replacement for qualified engineering judgement.

Generated evidence is only as reliable as the inspected source, backend, declared fallback and available metadata. Commercial, institutional, cloud or safety-critical deployments require their own security and engineering review.

## Responsible disclosure

Report vulnerabilities privately and allow reasonable time for remediation before public disclosure. Do not use testing to access, modify, delete, exfiltrate, overload or disrupt data or systems you do not own or have explicit permission to test.

## No warranty

CaeReflex is provided “as is” and “as available”, without warranty. Use is at the user’s sole risk and remains subject to the CaeReflex Research Source Licence.
