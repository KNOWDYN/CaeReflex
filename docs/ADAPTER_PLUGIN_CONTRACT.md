# Adapter plugin contract

CaeReflex adapters may be distributed independently from the core package. The core discovers external adapters through Python package entry points in the `caereflex.adapters` group.

## Required interface

A plugin exposes:

```python
class AdapterPlugin(Protocol):
    plugin_id: str
    plugin_version: str

    def capabilities(self) -> AdapterCapabilities: ...
    def probe(self, manifest: CaseManifest) -> ProbeResult: ...
    def plan(
        self,
        manifest: CaseManifest,
        profile: InspectionProfile,
        budget: InspectionBudget,
    ) -> InspectionPlan: ...
```

The protocol separates discovery from deep parsing:

1. CaeReflex builds a bounded `CaseManifest`.
2. Plugins probe the manifest without loading large arrays.
3. The selected plugin builds an explicit inspection plan.
4. A later execution layer performs the plan inside the declared resource budget.

## Capability honesty

A plugin must distinguish detection from interpretation. Recommended capability language includes:

- `none`;
- `fingerprint-only`;
- `header-summary`;
- `declaration-summary`;
- `native-topology`;
- `native-fields`;
- `full`.

STEP detection, for example, must not be advertised as B-rep interpretation unless a geometry backend actually decoded vertices, edges, faces, shells, and solids.

## Licence isolation

Capabilities include a licence field and optional dependency list. GPL or commercially restricted native backends must remain optional and separately installable unless the CaeReflex distribution licence is explicitly made compatible with them.

## Safety requirements

Plugins must be read-only by default. Capabilities must disclose whether a plugin requires network access or source execution. A parser must not execute solver dictionaries, embedded code, macros, or user scripts merely to inspect them.

## Large data

Plugins return semantic summaries and `ArrayRef` objects for heavy data. They must not place complete industrial meshes or fields into ReflexCase JSON.
