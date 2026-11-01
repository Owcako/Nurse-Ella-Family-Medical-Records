"""Fictional demo sources and saved processing fixtures; chat answers remain live."""

import json
import hashlib
from pathlib import Path


KIT = Path(__file__).with_name("demo-kit")


def manifest():
    return json.loads((KIT / "manifest.json").read_text(encoding="utf-8"))


def catalog():
    kit = manifest()
    return dict(title=kit["title"], file_count=len(kit["files"]), profile_count=len(kit["profiles"]), questions=kit["questions"],
                prepared_count=len(kit["files"]) - len(kit["live_files"]), live_count=len(kit["live_files"]))


def sources():
    kit = manifest()
    prepared = json.loads((KIT / "prepared.json").read_text(encoding="utf-8"))
    if set(prepared) != set(kit["files"]) - set(kit["live_files"]) or not 1 <= len(kit["live_files"]) <= 3:
        raise ValueError("The demo kit must contain prepared results and one to three live PDFs.")
    # Load and validate the entire bundled kit before any destructive transaction.
    files = []
    for name in kit["files"]:
        path = KIT / name
        if path.parent != KIT or path.suffix != ".pdf":
            raise ValueError("Invalid bundled demo filename.")
        content = path.read_bytes()
        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid bundled demo PDF.")
        item = dict(operation=f"demo:{kit['version']}:{name}", source=content,
                    title=name, media="application/pdf", origin="imported")
        if name in prepared:
            preset = prepared[name]
            if hashlib.sha256(content).hexdigest() != preset["source_sha256"]:
                raise ValueError("Prepared demo result does not match its original PDF.")
            item["prepared"] = preset
        files.append(item)
    return kit["profiles"], files
