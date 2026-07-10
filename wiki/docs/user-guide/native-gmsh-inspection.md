# Native Gmsh inspection

CaeReflex `2.0.0a3` adds bounded native Gmsh inspection for deep and forensic profiles.

## Inspect a Gmsh mesh

```bash
caereflex inspect model.msh \
  --adapter gmsh \
  --profile deep \
  --manifest-out manifest.json \
  --out case.json
```

The isolated `gmsh.native` backend uses this order:

1. optional meshio reader, when installed;
2. built-in bounded ASCII reader for MSH 2.x and 4.x;
3. fingerprint-only evidence when neither reader can decode the file.

A decoded mesh summary can include:

- MSH format version and encoding;
- model dimension and coordinate bounds;
- node and element counts;
- cell types;
- entities and physical groups;
- node and element fields;
- lazy-array identifiers for coordinates, tags, connectivity and field values.

## Query mesh arrays

```bash
caereflex arrays list
caereflex arrays describe ARRAY_ID --json
caereflex arrays sample ARRAY_ID --count 100 --json
caereflex arrays reduce ARRAY_ID --operation max --json
```

Connectivity is stored as flattened Gmsh node tags plus an offsets array. Element physical membership is also ragged and therefore represented through physical-tag and physical-offset arrays.

Complete industrial arrays are not embedded in ReflexCase JSON or agent context.

## Inspect a `.geo` file safely

```bash
caereflex inspect model.geo --adapter gmsh --profile deep --out case.json
```

The `.geo` reader is declaration-only. It can extract literal or safely resolved:

- scalar numeric assignments;
- points;
- lines, circles, splines and related curve declarations;
- curve loops;
- surfaces and surface loops;
- volumes;
- physical groups.

It never executes the file. Includes, loops, conditionals, functions, system calls, extrusions and boolean operations remain unresolved and produce `CRX-GMSH-GEO-PARTIAL-001` when relevant.

The reported geometry is therefore only the set of declarations that were explicitly decoded, not the geometry that a full Gmsh interpreter might generate.

## STEP, IGES and BREP

These files are fingerprinted by default. This preserves file identity, size and provenance without loading a native CAD library.

The optional Gmsh API path requires explicit backend configuration and a trusted input. It:

- runs inside the isolated worker;
- never accepts `.geo` files;
- does not request mesh generation;
- can report model entities, bounds and existing mesh arrays when available.

The default CLI deep-inspection path does not enable this option automatically.

## Units and coordinate frames

Gmsh coordinates and result data do not generally carry enough evidence to establish physical units. CaeReflex records units as unresolved unless another explicit source supplies them.

`gmsh_model_frame` is a source-local coordinate-frame reference only. It must not be treated as metres, global Cartesian coordinates or a mapped OpenFOAM/VTK frame without later Gate 6 evidence or human review.

## Diagnostics

- `CRX-GMSH-READ-001`
- `CRX-GMSH-MESHIO-FALLBACK-001`
- `CRX-GMSH-MSH-FALLBACK-001`
- `CRX-GMSH-GEO-PARTIAL-001`
- `CRX-GMSH-CAD-FINGERPRINT-001`
- `CRX-GMSH-API-FALLBACK-001`

Native Gmsh inspection does not establish geometry validity, mesh adequacy, numerical accuracy, convergence, certification or design safety.
