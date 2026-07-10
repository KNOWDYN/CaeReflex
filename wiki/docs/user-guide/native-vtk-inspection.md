# Native VTK inspection

CaeReflex `2.0.0a4` routes `deep` and `forensic` VTK inspection through the isolated `vtk.native` backend.

```bash
caereflex inspect path/to/results \
  --adapter vtk \
  --profile deep \
  --out vtk.caereflex.json
```

The standard profile remains a lightweight metadata and fingerprint path. Use a deep profile when native points, topology, fields or collection-time evidence is required.

## Reader order

For ordinary dataset files, CaeReflex records an ordered parser-attempt ledger:

1. PyVista/VTK when the optional `vtk` extra is installed;
2. meshio when the optional `mesh` extra is installed;
3. the dependency-free bounded core reader;
4. fingerprint-only evidence.

Install optional readers only when their native-library boundary is acceptable:

```bash
python -m pip install -e ".[vtk]"
python -m pip install -e ".[mesh]"
```

The core reader supports legacy ASCII VTK and single-piece XML VTK with inline ASCII or uncompressed inline base64 `DataArray` values. Binary legacy, compressed XML and appended XML require an optional reader or fall back explicitly.

## Dataset evidence

Supported evidence can include:

- dataset type and dimensionality;
- point and cell counts;
- point coordinates and bounds;
- cell offsets, connectivity and VTK type identifiers;
- structured extents, origin, spacing and direction metadata;
- rectilinear coordinate axes;
- point, cell and field arrays;
- component counts, data types and associations.

Heavy values remain outside ReflexCase JSON behind `ArrayRef` handles:

```bash
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays reduce ARRAY_ID --operation mean --json
```

Coordinate and field units remain unresolved unless the source or a reviewed annotation supplies them.

## Collections, parallel files and time values

The following metadata formats are inventoried without automatically opening referenced files:

- `.pvd` collections;
- `.vtm` and `.vtmb` multiblock metadata;
- `.pvtu`, `.pvtp`, `.pvti`, `.pvtr` and `.pvts` parallel metadata.

CaeReflex records:

- safe relative references;
- resolved paths inside the selected case root;
- whether each referenced file was selected by the manifest;
- PVD time values, group and part metadata;
- unsafe, absolute or traversal-bearing references.

A reference inventory is not proof that every referenced dataset was decoded. Collection metadata never causes hidden network access or traversal outside the selected source root.

## Stable diagnostics

- `CRX-VTK-READ-001`
- `CRX-VTK-PYVISTA-FALLBACK-001`
- `CRX-VTK-MESHIO-FALLBACK-001`
- `CRX-VTK-CORE-FALLBACK-001`
- `CRX-VTK-XML-ENCODING-001`
- `CRX-VTK-COLLECTION-REFERENCE-001`

Inspect the parser-attempt ledger before treating an array or topology item as available. Detected does not mean decoded, and decoded does not establish physical validity.

## Safety boundary

The backend does not:

- launch ParaView;
- execute programmable filters or pipelines;
- fetch external collection references;
- mutate the source dataset;
- infer coordinate or field units;
- assess mesh quality;
- prove convergence or validate simulation physics;
- certify engineering results or design safety.

PyVista and VTK execute native code inside the worker. The worker is defence in depth, not a complete operating-system sandbox. Use stronger external isolation for hostile, proprietary or safety-critical inputs.
