"""The image published to GHCR must be the one verified on Kind."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from scripts.verify_tested_image_artifact import verify_artifact

SOURCE_SHA = "a" * 40
IMAGE_ID = "sha256:" + "b" * 64


class TestedImageArtifactTests(unittest.TestCase):
    def _artifact(self, directory: Path) -> None:
        payload = b"synthetic docker archive"
        (directory / "image.tar.gz").write_bytes(payload)
        (directory / "archive.sha256").write_text(hashlib.sha256(payload).hexdigest())
        (directory / "source-sha").write_text(SOURCE_SHA)
        (directory / "image-id").write_text(IMAGE_ID)

    def test_exact_source_and_archive_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._artifact(directory)
            self.assertEqual(verify_artifact(directory, SOURCE_SHA), IMAGE_ID)

    def test_missing_or_mismatched_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._artifact(directory)
            with self.assertRaises(ValueError):
                verify_artifact(directory, "c" * 40)
            (directory / "image.tar.gz").write_bytes(b"modified archive")
            with self.assertRaises(ValueError):
                verify_artifact(directory, SOURCE_SHA)
            (directory / "image.tar.gz").unlink()
            with self.assertRaises(FileNotFoundError):
                verify_artifact(directory, SOURCE_SHA)


if __name__ == "__main__":
    unittest.main()
