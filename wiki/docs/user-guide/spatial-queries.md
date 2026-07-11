# Spatial queries

Deep or forensic native inspection stores a canonical spatial graph in the configured CaeReflex state directory. Gate 6C provides bounded read-only queries over that graph.

## Find graphs

```bash
caereflex spatial graphs --state-root .caereflex
caereflex spatial show GRAPH_ID --state-root .caereflex --json
```

## Filter entities and relations

```bash
caereflex spatial entities GRAPH_ID \
  --kinds mesh_cell,patch \
  --limit 100 \
  --state-root .caereflex

caereflex spatial relations GRAPH_ID \
  --entity-id ENTITY_ID \
  --direction both \
  --state-root .caereflex
```

Entity results are ordered by stable entity ID. Relation results are ordered by stable relation ID. `--name-contains` and `--source-path` apply bounded post-filters and are constrained by `--max-scan-rows`.

## Traverse recorded relations

```bash
caereflex spatial neighbours GRAPH_ID ENTITY_ID \
  --kinds contains,belongs_to \
  --direction outgoing \
  --depth 2 \
  --state-root .caereflex
```

Traversal follows only stored relations. It does not derive adjacency from mesh connectivity or geometry.

## Query bounds

```bash
caereflex spatial bounds GRAPH_ID \
  --frame-id FRAME_ID \
  --minimum 0,0,0 \
  --maximum 1,1,1 \
  --mode intersects \
  --state-root .caereflex
```

Bounds are compared only within the exact named frame. CaeReflex does not compose transforms or convert unresolved units during this operation.

## Inspect lazy arrays

```bash
caereflex spatial arrays GRAPH_ID \
  --owner-entity-id ENTITY_ID \
  --roles coordinates,field \
  --state-root .caereflex
```

This returns ArrayRef links, not numerical payloads. Use the existing `caereflex arrays` commands for separately bounded array sampling or reduction.

## Validate the frozen contract

```bash
caereflex spatial validate GRAPH_ID --state-root .caereflex --json
```

An accepted report confirms Gate 6 contract compatibility, deterministic ordering, content-addressed array links, SQLite integrity and bounded query behaviour. It is not an engineering-validity or design-safety certificate.
