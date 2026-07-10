"""Read-only OpenFOAM ASCII parsing primitives.

The parser understands the native text representation used by OpenFOAM mesh and
field files. It never expands includes, substitutions, code streams, dynamic code,
or coded boundary conditions. Binary payloads are detected and reported as an
unsupported native representation rather than guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import gzip
from io import BytesIO
import re
from typing import Any, Iterable


_NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?"
_INT_RE = re.compile(r"[+-]?\d+")
_NUMBER_RE = re.compile(_NUMBER)
_FOAMFILE_RE = re.compile(r"\bFoamFile\s*\{(.*?)\}", re.DOTALL)
_SIMPLE_ENTRY_RE = re.compile(r"(?m)^\s*([A-Za-z_][A-Za-z0-9_.:-]*)\s+([^;{}]+);")
_TIME_RE = re.compile(r"^(?:0|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)$")


class OpenFOAMNativeError(ValueError):
    """Raised when native OpenFOAM text is malformed or internally inconsistent."""


class OpenFOAMUnsupportedError(OpenFOAMNativeError):
    """Raised for detected representations that this reader intentionally avoids."""


@dataclass(frozen=True)
class MeshData:
    points: list[tuple[float, float, float]]
    faces: list[list[int]]
    owner: list[int]
    neighbour: list[int]
    patches: list[dict[str, Any]]
    bounds_min: tuple[float, float, float] | None
    bounds_max: tuple[float, float, float] | None
    cell_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FieldData:
    name: str
    field_class: str | None
    association: str
    components: int | None
    component_names: list[str]
    dimensions_raw: str | None
    internal_mode: str
    internal_values: list[int | float | bool]
    internal_count: int | None
    boundary: list[dict[str, Any]]
    unsafe_constructs: list[dict[str, Any]]
    raw_internal: str | None = None


@dataclass(frozen=True)
class DecodedFoamText:
    text: str
    compressed: bool
    format: str
    header: dict[str, str]


def strip_comments(text: str) -> str:
    """Remove OpenFOAM C/C++ comments without evaluating any source content."""

    text = re.sub(r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def parse_header(text: str) -> dict[str, str]:
    match = _FOAMFILE_RE.search(strip_comments(text))
    if not match:
        return {}
    return {
        item.group(1): item.group(2).strip().strip('"')
        for item in re.finditer(r"\b([A-Za-z0-9_]+)\s+([^;{}]+);", match.group(1))
    }


def decode_foam_text(payload: bytes, path: str, *, max_decompressed_bytes: int) -> DecodedFoamText:
    """Decode a bounded ASCII OpenFOAM file and reject binary payloads explicitly."""

    compressed = path.lower().endswith(".gz")
    if compressed:
        try:
            with gzip.GzipFile(fileobj=BytesIO(payload), mode="rb") as handle:
                decoded = handle.read(max_decompressed_bytes + 1)
        except OSError as exc:
            raise OpenFOAMNativeError(f"Invalid gzip payload: {exc}") from exc
        if len(decoded) > max_decompressed_bytes:
            raise OpenFOAMNativeError(
                f"Decompressed OpenFOAM file exceeds {max_decompressed_bytes} bytes."
            )
        payload = decoded

    probe = payload[: min(len(payload), 64 * 1024)].decode("latin-1", errors="ignore")
    header = parse_header(probe)
    representation = header.get("format", "ascii").strip().lower()
    if representation != "ascii":
        raise OpenFOAMUnsupportedError(
            f"OpenFOAM format {representation!r} is detected; Gate 5B decodes native ASCII only."
        )
    if b"\x00" in payload:
        raise OpenFOAMUnsupportedError("NUL bytes were found in a file declared as ASCII.")
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        text = payload.decode("latin-1")
    return DecodedFoamText(text=text, compressed=compressed, format=representation, header=parse_header(text))


def unsafe_constructs(text: str) -> list[dict[str, Any]]:
    """Return constructs that are preserved but never expanded or executed."""

    clean = strip_comments(text)
    patterns: tuple[tuple[str, str, re.Pattern[str]], ...] = (
        ("include", "include directive", re.compile(r"(?m)^\s*#\s*include(?:Etc|IfPresent)?\b[^\n]*")),
        ("code_stream", "code or evaluation directive", re.compile(r"(?m)^\s*#\s*(?:codeStream|calc|eval)\b[^\n]*")),
        ("substitution", "dictionary substitution", re.compile(r"\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_./:-]*")),
        ("coded_boundary", "coded boundary condition", re.compile(r"\b(?:codedFixedValue|codedMixed|coded)\b")),
        ("dynamic_code", "dynamic code declaration", re.compile(r"\b(?:dynamicCode|codeInclude|codeOptions|codeLibs)\b")),
        ("dynamic_library", "dynamic library declaration", re.compile(r"(?m)^\s*libs\s*\(")),
    )
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str]] = set()
    for code, kind, pattern in patterns:
        for match in pattern.finditer(clean):
            token = match.group(0).strip()
            line = clean.count("\n", 0, match.start()) + 1
            key = (code, line, token)
            if key in seen:
                continue
            seen.add(key)
            found.append({"code": code, "kind": kind, "token": token, "line": line})
    found.sort(key=lambda item: (item["line"], item["code"], item["token"]))
    return found


def _extract_balanced(text: str, opening_index: int, opening: str, closing: str) -> tuple[str, int]:
    if opening_index < 0 or opening_index >= len(text) or text[opening_index] != opening:
        raise OpenFOAMNativeError(f"Expected {opening!r} at the requested block offset.")
    depth = 0
    for index in range(opening_index, len(text)):
        character = text[index]
        if character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return text[opening_index + 1 : index], index + 1
    raise OpenFOAMNativeError(f"Unterminated {opening}{closing} block.")


def extract_named_block(text: str, name: str, *, opening: str = "{", closing: str = "}") -> str | None:
    clean = strip_comments(text)
    match = re.search(rf"\b{re.escape(name)}\b\s*\{re.escape(opening)}", clean)
    if not match:
        return None
    opening_index = clean.find(opening, match.start())
    block, _ = _extract_balanced(clean, opening_index, opening, closing)
    return block


def _body_without_header(text: str) -> str:
    clean = strip_comments(text)
    match = _FOAMFILE_RE.search(clean)
    return clean[match.end() :] if match else clean


def parse_counted_list(text: str) -> tuple[int, str]:
    body = _body_without_header(text)
    match = re.search(r"(?m)^\s*(\d+)\s*(?:\r?\n\s*)?\(", body)
    if not match:
        raise OpenFOAMNativeError("Expected an OpenFOAM counted list.")
    count = int(match.group(1))
    opening_index = body.find("(", match.start())
    inner, _ = _extract_balanced(body, opening_index, "(", ")")
    return count, inner


def parse_points(text: str) -> list[tuple[float, float, float]]:
    declared, inner = parse_counted_list(text)
    tuple_re = re.compile(rf"\(\s*({_NUMBER})\s+({_NUMBER})\s+({_NUMBER})\s*\)")
    points = [tuple(float(match.group(index)) for index in (1, 2, 3)) for match in tuple_re.finditer(inner)]
    if len(points) != declared:
        raise OpenFOAMNativeError(f"points declares {declared} entries but {len(points)} were decoded.")
    return points


def parse_faces(text: str) -> list[list[int]]:
    declared, inner = parse_counted_list(text)
    faces: list[list[int]] = []
    for match in re.finditer(r"(\d+)\s*\(([^()]*)\)", inner, flags=re.DOTALL):
        expected = int(match.group(1))
        vertices = [int(token) for token in _INT_RE.findall(match.group(2))]
        if len(vertices) != expected:
            raise OpenFOAMNativeError(
                f"face declares {expected} vertices but {len(vertices)} labels were decoded."
            )
        faces.append(vertices)
    if len(faces) != declared:
        raise OpenFOAMNativeError(f"faces declares {declared} entries but {len(faces)} were decoded.")
    return faces


def parse_label_list(text: str, object_name: str) -> list[int]:
    declared, inner = parse_counted_list(text)
    labels = [int(token) for token in _INT_RE.findall(inner)]
    if len(labels) != declared:
        raise OpenFOAMNativeError(
            f"{object_name} declares {declared} labels but {len(labels)} were decoded."
        )
    return labels


def _top_level_named_brace_blocks(inner: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    index = 0
    token_re = re.compile(r"[A-Za-z_][A-Za-z0-9_.:+-]*")
    while index < len(inner):
        match = token_re.search(inner, index)
        if not match:
            break
        name = match.group(0)
        brace = inner.find("{", match.end())
        if brace < 0:
            break
        intervening = inner[match.end() : brace]
        if intervening.strip():
            index = match.end()
            continue
        body, end = _extract_balanced(inner, brace, "{", "}")
        blocks.append((name, body))
        index = end
    return blocks


def parse_simple_entries(body: str) -> dict[str, str]:
    return {match.group(1): match.group(2).strip() for match in _SIMPLE_ENTRY_RE.finditer(body)}


def parse_boundary(text: str) -> list[dict[str, Any]]:
    declared, inner = parse_counted_list(text)
    patches: list[dict[str, Any]] = []
    for name, body in _top_level_named_brace_blocks(inner):
        entries = parse_simple_entries(body)
        try:
            n_faces = int(entries.get("nFaces", ""))
            start_face = int(entries.get("startFace", ""))
        except ValueError as exc:
            raise OpenFOAMNativeError(f"Boundary patch {name!r} lacks integer nFaces/startFace values.") from exc
        patches.append(
            {
                "name": name,
                "type": entries.get("type"),
                "physical_type": entries.get("physicalType"),
                "n_faces": n_faces,
                "start_face": start_face,
                "metadata": {
                    key: value
                    for key, value in entries.items()
                    if key not in {"type", "physicalType", "nFaces", "startFace"}
                },
            }
        )
    if len(patches) != declared:
        raise OpenFOAMNativeError(
            f"boundary declares {declared} patches but {len(patches)} were decoded."
        )
    return patches


def build_mesh(
    points: list[tuple[float, float, float]],
    faces: list[list[int]],
    owner: list[int],
    neighbour: list[int],
    patches: list[dict[str, Any]],
) -> MeshData:
    warnings: list[str] = []
    if len(owner) != len(faces):
        raise OpenFOAMNativeError(
            f"owner length {len(owner)} does not match face count {len(faces)}."
        )
    if len(neighbour) > len(faces):
        raise OpenFOAMNativeError("neighbour contains more entries than faces.")
    for face_index, vertices in enumerate(faces):
        if len(vertices) < 3:
            warnings.append(f"face {face_index} has fewer than three vertices")
        for point_index in vertices:
            if point_index < 0 or point_index >= len(points):
                raise OpenFOAMNativeError(
                    f"face {face_index} references point {point_index}, outside 0..{max(len(points) - 1, 0)}."
                )
    labels = [*owner, *neighbour]
    if any(label < 0 for label in labels):
        raise OpenFOAMNativeError("owner/neighbour cell labels must be non-negative.")
    cell_count = max(labels) + 1 if labels else 0

    occupied: set[int] = set()
    for patch in patches:
        start = int(patch["start_face"])
        count = int(patch["n_faces"])
        if start < 0 or count < 0 or start + count > len(faces):
            raise OpenFOAMNativeError(
                f"Boundary patch {patch['name']!r} range [{start}, {start + count}) exceeds face count {len(faces)}."
            )
        overlap = occupied.intersection(range(start, start + count))
        if overlap:
            warnings.append(f"boundary patch {patch['name']} overlaps another patch")
        occupied.update(range(start, start + count))
    if patches and min(int(patch["start_face"]) for patch in patches) != len(neighbour):
        warnings.append(
            "first boundary startFace does not equal neighbour count; topology may use a nonstandard ordering"
        )
    expected_boundary = set(range(len(neighbour), len(faces)))
    if patches and occupied != expected_boundary:
        warnings.append("boundary patch ranges do not cover exactly the boundary-face interval")

    if points:
        bounds_min = tuple(min(point[axis] for point in points) for axis in range(3))
        bounds_max = tuple(max(point[axis] for point in points) for axis in range(3))
    else:
        bounds_min = None
        bounds_max = None
    return MeshData(
        points=points,
        faces=faces,
        owner=owner,
        neighbour=neighbour,
        patches=patches,
        bounds_min=bounds_min,
        bounds_max=bounds_max,
        cell_count=cell_count,
        warnings=warnings,
    )


def _field_components(field_class: str | None) -> tuple[int | None, list[str]]:
    lower = (field_class or "").lower()
    if "sphericaltensorfield" in lower:
        return 1, ["ii"]
    if "symmtensorfield" in lower:
        return 6, ["xx", "xy", "xz", "yy", "yz", "zz"]
    if "tensorfield" in lower:
        return 9, ["xx", "xy", "xz", "yx", "yy", "yz", "zx", "zy", "zz"]
    if "vectorfield" in lower:
        return 3, ["x", "y", "z"]
    if "scalarfield" in lower:
        return 1, []
    return None, []


def _field_association(field_class: str | None) -> str:
    lower = (field_class or "").lower()
    if lower.startswith("vol"):
        return "cell"
    if lower.startswith("surface"):
        return "face"
    if lower.startswith("point"):
        return "point"
    return "unknown"


def _parse_numeric_literal(raw: str) -> list[float | int]:
    token = raw.strip()
    if token.startswith("(") and token.endswith(")"):
        token = token[1:-1]
    values: list[float | int] = []
    for item in _NUMBER_RE.findall(token):
        value = float(item)
        values.append(int(value) if value.is_integer() and not any(char in item.lower() for char in (".", "e")) else value)
    return values


def _parse_nonuniform_values(inner: str, count: int, components: int | None) -> list[float | int]:
    if components is None:
        raise OpenFOAMNativeError("Field component count is unresolved for a nonuniform list.")
    if components == 1:
        values = _parse_numeric_literal(inner)
        if len(values) != count:
            raise OpenFOAMNativeError(
                f"nonuniform scalar list declares {count} values but {len(values)} were decoded."
            )
        return values
    tuple_re = re.compile(r"\(([^()]*)\)")
    flattened: list[float | int] = []
    tuples = list(tuple_re.finditer(inner))
    if len(tuples) != count:
        raise OpenFOAMNativeError(
            f"nonuniform field list declares {count} tuples but {len(tuples)} were decoded."
        )
    for tuple_match in tuples:
        values = _parse_numeric_literal(tuple_match.group(1))
        if len(values) != components:
            raise OpenFOAMNativeError(
                f"field tuple requires {components} components but {len(values)} were decoded."
            )
        flattened.extend(values)
    return flattened


def parse_field(text: str, *, fallback_name: str) -> FieldData:
    clean = strip_comments(text)
    header = parse_header(clean)
    field_class = header.get("class")
    name = header.get("object") or fallback_name
    components, component_names = _field_components(field_class)
    association = _field_association(field_class)
    dimensions_match = re.search(r"(?m)^\s*dimensions\s+(\[[^\]]+\])\s*;", clean)
    dimensions_raw = dimensions_match.group(1) if dimensions_match else None

    internal_mode = "missing"
    internal_values: list[int | float | bool] = []
    internal_count: int | None = None
    raw_internal: str | None = None

    uniform = re.search(r"\binternalField\s+uniform\s+([^;]+);", clean, flags=re.DOTALL)
    if uniform:
        raw_internal = uniform.group(1).strip()
        values = _parse_numeric_literal(raw_internal)
        if components is not None and len(values) != components:
            raise OpenFOAMNativeError(
                f"Uniform field {name!r} requires {components} components but {len(values)} were decoded."
            )
        internal_mode = "uniform"
        internal_values = values
        internal_count = 1
    else:
        nonuniform = re.search(
            r"\binternalField\s+nonuniform\s+(?:List\s*<\s*([^>]+)\s*>|([A-Za-z0-9_]+))\s+(\d+)\s*\(",
            clean,
            flags=re.DOTALL,
        )
        if nonuniform:
            internal_count = int(nonuniform.group(3))
            opening_index = clean.find("(", nonuniform.start(3))
            inner, _ = _extract_balanced(clean, opening_index, "(", ")")
            internal_values = _parse_nonuniform_values(inner, internal_count, components)
            internal_mode = "nonuniform"
            raw_internal = f"{nonuniform.group(1) or nonuniform.group(2)}[{internal_count}]"
        else:
            raw = re.search(r"\binternalField\s+([^;]+);", clean, flags=re.DOTALL)
            if raw:
                internal_mode = "unsupported"
                raw_internal = raw.group(1).strip()

    boundary_records: list[dict[str, Any]] = []
    boundary_body = extract_named_block(clean, "boundaryField")
    if boundary_body is not None:
        for patch_name, patch_body in _top_level_named_brace_blocks(boundary_body):
            entries = parse_simple_entries(patch_body)
            value = entries.get("value")
            boundary_records.append(
                {
                    "patch": patch_name,
                    "type": entries.get("type"),
                    "value": value,
                    "value_mode": (
                        "uniform" if value and value.lstrip().startswith("uniform")
                        else "nonuniform" if value and value.lstrip().startswith("nonuniform")
                        else "other" if value else "none"
                    ),
                    "metadata": {key: item for key, item in entries.items() if key not in {"type", "value"}},
                }
            )

    return FieldData(
        name=name,
        field_class=field_class,
        association=association,
        components=components,
        component_names=component_names,
        dimensions_raw=dimensions_raw,
        internal_mode=internal_mode,
        internal_values=internal_values,
        internal_count=internal_count,
        boundary=boundary_records,
        unsafe_constructs=unsafe_constructs(clean),
        raw_internal=raw_internal,
    )


def parse_dimensioned_properties(text: str) -> list[dict[str, str]]:
    clean = strip_comments(text)
    pattern = re.compile(
        r"(?m)^\s*(?:(dimensioned[A-Za-z0-9_]+)\s+)?([A-Za-z_][A-Za-z0-9_.:-]*)\s+"
        r"(\[[^\]]+\])\s+([^;{}]+);"
    )
    return [
        {
            "declared_type": match.group(1) or "",
            "name": match.group(2),
            "dimensions": match.group(3).strip(),
            "value": match.group(4).strip(),
            "line": str(clean.count("\n", 0, match.start()) + 1),
        }
        for match in pattern.finditer(clean)
    ]


def canonical_openfoam_path(path: str) -> str:
    return path[:-3] if path.lower().endswith(".gz") else path


def is_time_directory(name: str) -> bool:
    return bool(_TIME_RE.fullmatch(name))


def time_sort_key(name: str) -> tuple[int, Decimal | str]:
    try:
        return 0, Decimal(name)
    except (InvalidOperation, ValueError):
        return 1, name


def flatten_faces(faces: Iterable[Iterable[int]]) -> tuple[list[int], list[int]]:
    offsets = [0]
    values: list[int] = []
    for face in faces:
        values.extend(face)
        offsets.append(len(values))
    return offsets, values
