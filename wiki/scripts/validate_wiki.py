#!/usr/bin/env python3
"""Validate that the wiki matches package facts and release controls."""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[2]
WIKI = ROOT / "wiki"
DOCS = WIKI / "docs"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def pyproject_version() -> str:
    return tomllib.loads(read(ROOT / "pyproject.toml"))["project"]["version"]


def package_version() -> str:
    ns: dict[str, str] = {}
    exec(read(ROOT / "caereflex" / "version.py"), ns)
    return ns["__version__"]


def reflexcase_schema_version() -> str:
    tree = ast.parse(read(ROOT / "caereflex" / "core" / "models.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ReflexCase":
            for stmt in node.body:
                target = None
                value = None
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    target = stmt.target.id
                    value = stmt.value
                elif isinstance(stmt, ast.Assign) and stmt.targets and isinstance(stmt.targets[0], ast.Name):
                    target = stmt.targets[0].id
                    value = stmt.value
                if target == "schema_version" and isinstance(value, ast.Constant):
                    return str(value.value)
    raise AssertionError("Could not find ReflexCase.schema_version")


def cli_commands() -> set[str]:
    text = read(ROOT / "caereflex" / "cli" / "main.py")
    commands = set(re.findall(r'@app\.command\("([^"]+)"\)', text))
    groups = {
        "crossref_app": "crossref",
        "export_app": "export",
        "examples_app": "examples",
        "adapters_app": "adapters",
        "schema_app": "schema",
        "diagnostics_app": "diagnostics",
        "cache_app": "cache",
    }
    for variable, prefix in groups.items():
        pattern = rf'@{re.escape(variable)}\.command\("([^"]+)"\)'
        commands.update(f"{prefix} {name}" for name in re.findall(pattern, text))

    mounted_groups = {
        ROOT / "caereflex" / "cli" / "units.py": ("units_app", "units"),
        ROOT / "caereflex" / "cli" / "execution.py": ("execution_app", "execution"),
        ROOT / "caereflex" / "cli" / "arrays.py": ("arrays_app", "arrays"),
        ROOT / "caereflex" / "cli" / "jobs.py": ("jobs_app", "jobs"),
    }
    for path, (variable, prefix) in mounted_groups.items():
        mounted_text = read(path)
        pattern = rf'@{re.escape(variable)}\.command\("([^"]+)"\)'
        commands.update(f"{prefix} {name}" for name in re.findall(pattern, mounted_text))
    return commands


def rest_routes() -> set[str]:
    text = read(ROOT / "caereflex" / "server" / "app.py")
    return {f"{method.upper()} {path}" for method, path in re.findall(r"@app\.(get|post)\('([^']+)'", text)}


def adapter_names() -> set[str]:
    return {path.stem for path in (ROOT / "caereflex" / "adapters").glob("*.py") if path.stem not in {"__init__", "base"}}


def assert_contains(haystack: str, needle: str, source: Path) -> None:
    if needle not in haystack:
        raise AssertionError(f"{source.relative_to(ROOT)} is missing {needle!r}")


def main() -> int:
    failures: list[str] = []

    try:
        project_version = pyproject_version()
        pkg_version = package_version()
        if project_version != pkg_version:
            failures.append(f"pyproject version {project_version} != package version {pkg_version}")

        schema_version = reflexcase_schema_version()
        release_page = DOCS / "releases" / f"{pkg_version}.md"
        if not release_page.exists():
            failures.append(f"missing release page {release_page.relative_to(ROOT)}")
        else:
            release_text = read(release_page)
            assert_contains(release_text, f"`{pkg_version}`", release_page)
            assert_contains(release_text, f"`{schema_version}`", release_page)
            assert_contains(release_text, "does not validate simulations", release_page)

        changelog = read(ROOT / "CHANGELOG.md")
        if pkg_version not in changelog:
            failures.append(f"CHANGELOG.md is missing {pkg_version}")

        mkdocs = read(WIKI / "mkdocs.yml")
        assert_contains(mkdocs, f"{pkg_version}: releases/{pkg_version}.md", WIKI / "mkdocs.yml")
        assert_contains(mkdocs, "strict: true", WIKI / "mkdocs.yml")

        cli_ref = read(DOCS / "reference" / "cli.md")
        for command in sorted(cli_commands()):
            assert_contains(cli_ref, f"`{command}`", DOCS / "reference" / "cli.md")

        openapi_ref = read(DOCS / "reference" / "openapi.md")
        rest_arch = read(DOCS / "architecture" / "rest-api.md")
        rest_text = openapi_ref + "\n" + rest_arch
        for route in sorted(rest_routes()):
            assert_contains(rest_text, f"`{route}`", DOCS / "reference" / "openapi.md")

        adapters = read(DOCS / "architecture" / "adapters.md")
        for adapter in sorted(adapter_names()):
            display = {"gmsh": "Gmsh", "openfoam": "OpenFOAM", "vtk": "VTK"}.get(adapter, adapter)
            assert_contains(adapters, display, DOCS / "architecture" / "adapters.md")

        safe_use = read(DOCS / "user-guide" / "safe-use-policy.md")
        for required in ["validates a simulation", "proves convergence", "assesses mesh adequacy", "certifies an engineering result", "establishes design safety"]:
            assert_contains(safe_use, required, DOCS / "user-guide" / "safe-use-policy.md")

        release_controls = read(DOCS / "developer-guide" / "release-controls.md")
        for required in ["validate_wiki.py", "tests/test_wiki.py", "mkdocs build --strict"]:
            assert_contains(release_controls, required, DOCS / "developer-guide" / "release-controls.md")

    except AssertionError as exc:
        failures.append(str(exc))

    if failures:
        print("Wiki validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("Wiki validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
