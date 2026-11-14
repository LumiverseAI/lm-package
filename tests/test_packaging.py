"""What lm-package writes into a .lmext, and which plugInfo.json it accepts."""

import json
import zipfile
from pathlib import Path

from lm_package.packager import create_package
from lm_package.validator import validate_manifest

MANIFEST = {
    "formatVersion": 1,
    "id": "com.example.thing",
    "name": "Thing",
    "version": "1.0.0",
    "description": "An extension made for the tests.",
    "author": {"name": "Tests"},
    "license": "MIT",
    "engine": {"minVersion": "26.0.0"},
    "platforms": ["windows-x64"],
    "pluginType": "editor",
}


def extension(name: str, base: str, **extra) -> dict:
    """A plugInfo.json registering one LmExtension type."""
    return {"Plugins": [{"Name": name, "Type": "python", "Root": "..", "ResourcePath": "resources",
                         "Info": {"Types": {f"{name}.Extension": {"bases": [base], "pluginName": name, **extra}}}}]}


def write(path: Path, content) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")


def built_project(tmp_path: Path, root_registration: dict | None) -> tuple[Path, Path]:
    """A built extension: its project (manifest, registration, build file) and its bundle, which has a
    sub-plugin in editor/ and, when given, a registration of its own at its root."""
    project, bundle = tmp_path / "project", tmp_path / "bundle"
    write(project / "manifest.json", MANIFEST)
    write(project / "CMakeLists.txt", "")
    write(project / "plugInfo.json", extension("com.example.thing", "LmExtension"))
    write(bundle / "editor/resources/plugInfo.json", extension("thing_editor", "LmExtension"))
    write(bundle / "editor/thing_editor/__init__.py", "")
    if root_registration is not None:
        write(bundle / "resources/plugInfo.json", root_registration)
    return project, bundle


def packaged(project: Path, bundle: Path, output: Path) -> dict[str, list[bytes]]:
    """The archive's entries, by name: each name with the contents of every entry it has."""
    archive, *_ = create_package(project, output, build_dir=bundle)
    entries: dict[str, list[bytes]] = {}
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            entries.setdefault(info.filename, []).append(package.read(info))
    return entries


def test_a_package_without_a_root_registration_gets_one_that_finds_its_sub_plugins(tmp_path):
    project, bundle = built_project(tmp_path, None)
    entries = packaged(project, bundle, tmp_path / "out")
    (generated,) = entries["resources/plugInfo.json"]
    assert json.loads(generated) == {"Includes": ["../*/resources/"]}


def test_a_package_keeps_its_own_root_registration_whole_and_once(tmp_path):
    own = {"Includes": ["../editor/resources/"], **extension("com.example.thing", "lm.lumydra.lumydra.LmExtension")}
    project, bundle = built_project(tmp_path, own)
    entries = packaged(project, bundle, tmp_path / "out")
    # One entry, the package's own: no generated twin that extraction would resolve by order.
    assert [json.loads(content) for content in entries["resources/plugInfo.json"]] == [own]
    assert len(entries["editor/resources/plugInfo.json"]) == 1


def test_a_python_extension_is_an_lm_extension_whatever_its_plugin_name(tmp_path):
    # A Python package with a second extension, its editor part, whose pluginName is not the id.
    project = tmp_path / "project"
    registration = extension("com.example.thing", "lm.lumydra.lumydra.LmExtension")
    registration["Plugins"] += extension("com.example.thing.editor", "lm.lumydra.lumydra.LmExtension")["Plugins"]
    write(project / "resources/plugInfo.json", registration)
    assert validate_manifest(MANIFEST, project) == []
    # A type that is not an extension still has to be named after the package.
    write(project / "resources/plugInfo.json", extension("com.example.other", "UsdSchemaBase"))
    assert validate_manifest(MANIFEST, project) == [
        "plugInfo.json pluginName 'com.example.other' does not match manifest id 'com.example.thing'. "
        "They must be identical."]
