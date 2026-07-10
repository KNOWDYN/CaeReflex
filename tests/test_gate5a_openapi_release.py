import json
from pathlib import Path

import yaml

from caereflex.version import __version__


def test_static_openapi_documents_match_package_version():
    root = Path("openapi")
    json_document = json.loads((root / "openapi.json").read_text(encoding="utf-8"))
    yaml_document = yaml.safe_load((root / "openapi.yaml").read_text(encoding="utf-8"))

    assert json_document["info"]["version"] == __version__
    assert yaml_document["info"]["version"] == __version__
    assert set(json_document["paths"]) == set(yaml_document["paths"])
