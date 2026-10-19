"""Build mobile-only releases from explicit inputs, with pinned component downloads."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = "v0.4.0"
DIST = ROOT / "dist" / VERSION
STAMP = (2026, 10, 19, 0, 0, 0)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def build_zip(output, files, extras=None):
    """Stable archive metadata keeps published component pins reproducible."""
    temporary = output.with_suffix(".zip.part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name, path in sorted(files.items()):
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(info, "w") as target:
                shutil.copyfileobj(source, target, 1024 * 1024)
        for name, data in sorted((extras or {}).items()):
            info = zipfile.ZipInfo(name, STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
    temporary.replace(output)
    print(f"{output.name}: {output.stat().st_size / 1024**2:.2f} MiB", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--components-only", action="store_true")
    args = parser.parse_args()
    DIST.mkdir(parents=True, exist_ok=True)
    catalog_file = ROOT / "config/gms-packages.json"
    catalog = json.loads(catalog_file.read_text(encoding="utf-8"))
    assert len(catalog["packages"]) == 5, "Mobile catalog must contain GSF 35/36/37, ARM GMS and Store"
    assets = []
    offline = {}
    for entry in catalog["packages"]:
        path = (ROOT / "cache/gms" / entry["file"]).resolve()
        assert path.parent == (ROOT / "cache/gms").resolve()
        assert "x86" not in path.name
        assert path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"], path.name
        output = DIST / (entry["file"] + ".zip")
        if not (output.is_file() and entry.get("download_sha256") == sha(output)):
            build_zip(output, {entry["file"]: path})
        entry.update(download_asset=output.name, download_bytes=output.stat().st_size, download_sha256=sha(output))
        assets.append(output)
        offline["Google-Offline/cache/gms/" + entry["file"]] = path
    catalog_file.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.components_only:
        return

    offline["Google-Offline/gms-packages.json"] = catalog_file
    offline_manifest = {name: sha(path) for name, path in offline.items()}
    output = DIST / f"AndroidCoolNet-Google-Offline-{VERSION}.zip"
    build_zip(output, offline, {
        "Google-Offline/SHA256.json": json.dumps(offline_manifest, indent=2),
        "Google-Offline/README.txt": (
            "AndroidCoolNet Google offline components (Android 15/16/17, ARM).\n"
            "Run install.cmd from the separate Windows base package. Choose 2, then paste this ZIP path.\n"
            "No extraction needed. The installer selects missing components by API/ABI and SHA-256.\n"
            "Alternatively select the extracted folder. Existing installed packages are never replaced.\n"
            "Metadata/signatures verified; OEM compatibility and Google login are not guaranteed.\n"
            "Sources, versions, hashes and signing lineage: gms-packages.json.\n"
        ),
    })
    assets.append(output)

    names = ["install.cmd", "Prepare.ps1", "setup_tool.py", "gms_assets.py", "README.md", "TESTING.md"]
    paths = [ROOT / name for name in names]
    for directory in ("config", "runtime", "platform-tools"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    paths.append(ROOT / "cache/cmfa-2.11.35-meta-arm64-v8a-release.apk")
    assert all(p.is_file() for p in paths)
    base = {"AndroidCoolNet/" + p.relative_to(ROOT).as_posix(): p for p in paths}
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in paths}
    output = DIST / f"AndroidCoolNet-Windows-{VERSION}.zip"
    build_zip(output, base, {"AndroidCoolNet/SHA256.json": json.dumps(manifest, indent=2)})
    assets.append(output)
    (DIST / "SHA256SUMS.txt").write_text("".join(f"{sha(p)}  {p.name}\n" for p in assets), encoding="ascii")
    print(f"Release files: {DIST}", flush=True)


if __name__ == "__main__":
    main()
