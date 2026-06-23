# gmsh_minimal

[`t1.geo`](t1.geo) is a tiny hand-written Gmsh-style geometry fixture. It defines four points, four lines, one curve loop, one plane surface, and two physical groups named `walls` and `fluid`. CaeReflex inspects the text structure; it does not require Gmsh, generate a mesh, or validate mesh quality.

## Inspect the example

```bash
mkdir -p build
caereflex inspect-gmsh examples/gmsh_minimal/t1.geo --out build/gmsh_case.json
```

Expected output snippet:

```text
Status: success
Case ID: case_...
Gmsh-oriented case inspected with 1 source file(s).
Outputs:
- caereflex_json: build/gmsh_case.json
```

Expected JSON highlights:

```json
{
  "case_type": "gmsh",
  "detected_formats": [".geo"],
  "detected_tools": ["Gmsh"],
  "physics_tags": ["mesh", "geometry"]
}
```

The exported case should include one source file record for `examples/gmsh_minimal/t1.geo`, one geometry/mesh-oriented asset, and boundary-condition-like records derived from the `Physical Curve("walls")` and `Physical Surface("fluid")` declarations.

## Optional exports

Create compact agent context:

```bash
caereflex export agent-context build/gmsh_case.json --out build/gmsh_agent_context.json
```

Create a Markdown report:

```bash
caereflex export markdown build/gmsh_case.json --out build/gmsh_case_report.md
```

These exports are derived from the JSON inspection result and still do not run Gmsh.

## Safety limitations

- `case_type: gmsh` means the adapter recognized a Gmsh-oriented input, not that a mesh was generated or accepted.
- The `.geo` path is recorded as a source file with hash/provenance metadata when possible.
- Assets describe inspected geometry/mesh artefacts, not solver-ready proof.
- CaeReflex does not claim CAD validity, watertightness, mesh adequacy, convergence, design safety, or certification from this fixture.

## Related documentation

- [CLI reference](../../docs/CLI.md)
- [REST API](../../docs/REST_API.md)
- [Agent integration](../../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../../docs/ADAPTERS.md)
- [CrossRef literature metadata](../../docs/CROSSREF.md)
