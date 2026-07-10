from pathlib import Path

from caereflex.contracts import InspectionBudget
from caereflex.discovery import CatalogStore, scan_case


def test_openfoam_case_is_resolved_without_reading_arrays():
    manifest = scan_case("examples/openfoam_cavity_minimal")
    assert "openfoam" in manifest.case_hints
    assert "openfoam-case" in manifest.detected_formats
    assert any(entry.path == "system/controlDict" for entry in manifest.entries)
    assert manifest.truncated is False


def test_catalog_budget_is_explicit(tmp_path: Path):
    for index in range(5):
        (tmp_path / f"file_{index}.vtk").write_text("DATASET POLYDATA", encoding="utf-8")
    manifest = scan_case(tmp_path, budget=InspectionBudget(max_files=2, max_depth=2))
    assert manifest.truncated is True
    assert "max_files" in manifest.limits_reached
    assert any(item.code == "CRX-SCAN-LIMIT-001" for item in manifest.diagnostics)


def test_symlink_is_not_followed(tmp_path: Path):
    target = tmp_path / "outside"
    target.mkdir()
    (target / "large.vtk").write_text("DATASET POLYDATA", encoding="utf-8")
    root = tmp_path / "case"
    root.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        return
    manifest = scan_case(root)
    linked = next(entry for entry in manifest.entries if entry.path == "linked")
    assert linked.metadata["symlink"] is True
    assert not any(entry.path.startswith("linked/") for entry in manifest.entries)


def test_catalog_cache_reports_incremental_changes(tmp_path: Path):
    case = tmp_path / "case"
    case.mkdir()
    source = case / "model.geo"
    source.write_text("Point(1)={0,0,0,1};", encoding="utf-8")
    store = CatalogStore(tmp_path / "catalog.sqlite3")
    first = scan_case(case)
    assert store.diff(store.load(first.root_uri), first).added == ["model.geo"]
    store.save(first)
    source.write_text("Point(1)={1,0,0,1};", encoding="utf-8")
    second = scan_case(case)
    diff = store.diff(store.load(second.root_uri), second)
    assert diff.changed == ["model.geo"]
