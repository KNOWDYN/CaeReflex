from caereflex.discovery import scan_case
from caereflex.plugins import adapter_capabilities, get_adapter_plugin, probe_manifest


def test_builtin_capabilities_are_declared():
    ids = {item.plugin_id for item in adapter_capabilities(include_external=False)}
    assert ids == {"gmsh", "openfoam", "vtk"}
    assert all(item.read_only for item in adapter_capabilities(include_external=False))


def test_manifest_probe_selects_expected_adapter():
    manifest = scan_case("examples/vtk_minimal")
    probes = probe_manifest(manifest, include_external=False)
    assert probes[0].plugin_id == "vtk"
    assert probes[0].supported is True


def test_plugin_can_build_bounded_plan():
    manifest = scan_case("examples/gmsh_minimal")
    plugin = get_adapter_plugin("gmsh", include_external=False)
    assert plugin is not None
    plan = plugin.plan(manifest, manifest.profile, __import__("caereflex.contracts", fromlist=["InspectionBudget"]).InspectionBudget())
    assert plan.plugin_id == "gmsh"
    assert "t1.geo" in plan.selected_paths
