"""Fail closed unless a publication artifact matches the tested source and bytes."""

import hashlib
import re
import sys
from pathlib import Path


def verify_artifact(directory: Path, expected_source_sha: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_source_sha):
        raise ValueError("Expected source SHA must be a full Git commit SHA")

    archive = directory / "image.tar.gz"
    source_sha = (directory / "source-sha").read_text().strip()
    image_id = (directory / "image-id").read_text().strip()
    expected_digest = (directory / "archive.sha256").read_text().strip()
    if source_sha != expected_source_sha:
        raise ValueError("Tested image belongs to a different source SHA")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise ValueError("Tested image ID is invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise ValueError("Archive SHA-256 is invalid")

    digest = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_digest:
        raise ValueError("Tested image archive bytes changed")
    return image_id


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify_tested_image_artifact.py DIRECTORY SOURCE_SHA")
    print(verify_artifact(Path(sys.argv[1]), sys.argv[2]))
