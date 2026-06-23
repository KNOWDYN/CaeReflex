# vtk_minimal

[`sample.vtk`](sample.vtk) is a tiny ASCII legacy VTK file. It contains a `POLYDATA` dataset with four points, one polygon, point-associated scalar `pressure`, and point-associated vector `velocity`.

## Inspect the example

```bash
mkdir -p build
caereflex inspect-vtk examples/vtk_minimal/sample.vtk --out build/vtk_case.json
```

Expected output snippet:

```text
Status: success
Case ID: case_...
VTK-compatible result data inspected with 1 file(s).
Outputs:
- caereflex_json: build/vtk_case.json
```

Expected JSON highlights:

```json
{
  "case_type": "vtk",
  "detected_formats": [".vtk"],
  "detected_tools": ["VTK/ParaView-compatible"],
  "result_fields": ["pressure", "velocity"]
}
```

## Result field extraction

For legacy `.vtk` files, the core adapter performs bounded text inspection and extracts declarations such as:

- `DATASET POLYDATA`
- `POINTS 4 float`
- `SCALARS pressure float 1`
- `VECTORS velocity float`

The result-field records are useful for agent summaries and review prompts, but they are not proof of physical correctness.

## Limitations

- The core adapter does not require ParaView, PyVista, or VTK Python packages for this fixture.
- Field association is conservative for legacy text parsing.
- No units, derived physics, interpolation quality, solver provenance, or correctness claims are inferred.
- XML VTK-family files may need optional VTK/PyVista-style dependencies for deeper inspection.

## Related documentation

- [CLI reference](../../docs/CLI.md)
- [REST API](../../docs/REST_API.md)
- [Agent integration](../../docs/AGENT_INTEGRATION.md)
- [Adapter guide](../../docs/ADAPTERS.md)
- [CrossRef literature metadata](../../docs/CROSSREF.md)
