import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from storage.audit_storage import (  # noqa: E402
    AudioUploadVerificationError,
    resolve_stored_audit_audio_path,
    store_audit_audio_file,
)


class TestAuditStorageFiles(unittest.TestCase):
    def setUp(self):
        self.storage_dir = tempfile.mkdtemp(prefix="audit_storage_files_")
        self.original_storage_dir = os.environ.get("AUDIT_AUDIO_STORAGE_DIR")
        self.original_bucket = os.environ.get("GCS_BUCKET_NAME")
        os.environ["AUDIT_AUDIO_STORAGE_DIR"] = self.storage_dir
        os.environ.pop("GCS_BUCKET_NAME", None)

    def tearDown(self):
        if self.original_storage_dir is None:
            os.environ.pop("AUDIT_AUDIO_STORAGE_DIR", None)
        else:
            os.environ["AUDIT_AUDIO_STORAGE_DIR"] = self.original_storage_dir
        if self.original_bucket is None:
            os.environ.pop("GCS_BUCKET_NAME", None)
        else:
            os.environ["GCS_BUCKET_NAME"] = self.original_bucket
        shutil.rmtree(self.storage_dir, ignore_errors=True)

    def test_store_audit_audio_file_writes_physical_file(self):
        stored = store_audit_audio_file(
            audit_id=42,
            audio_bytes=b"RIFFdemo-audio",
            mime_type="audio/wav",
            original_filename="ligacao.wav",
            input_hash="hash-audio",
        )

        stored_path = resolve_stored_audit_audio_path(stored["audio_storage_path"])

        self.assertIsNotNone(stored_path)
        self.assertTrue(stored_path.exists())
        self.assertEqual(stored_path.read_bytes(), b"RIFFdemo-audio")
        self.assertEqual(stored["audio_original_filename"], "ligacao.wav")
        self.assertEqual(stored["audio_mime_type"], "audio/wav")
        self.assertEqual(stored["audio_size_bytes"], len(b"RIFFdemo-audio"))

    def test_store_audit_audio_file_raises_when_final_replace_never_succeeds(self):
        with patch("storage.audit_storage.os.replace", side_effect=PermissionError("locked")):
            with patch("time.sleep"):
                with self.assertRaises(PermissionError):
                    store_audit_audio_file(
                        audit_id=43,
                        audio_bytes=b"RIFFlocked",
                        mime_type="audio/wav",
                        original_filename="ligacao.wav",
                        input_hash="hash-audio",
                        existing_relative_path="2026/04/audit_43_hash.wav",
                    )

        expected_path = Path(self.storage_dir) / "2026" / "04" / "audit_43_hash.wav"
        self.assertFalse(expected_path.exists())
        self.assertFalse(expected_path.with_suffix(".wav.tmp").exists())

    def test_store_audit_audio_file_local_readback_size_mismatch_cleans_up(self):
        original_stat = Path.stat

        def fake_stat(self_path, *args, **kwargs):
            real = original_stat(self_path, *args, **kwargs)
            if self_path.suffix == ".wav" and "audit_44" in self_path.name:

                class _StatProxy:
                    def __init__(self, src):
                        self._src = src

                    def __getattr__(self, name):
                        return getattr(self._src, name)

                    @property
                    def st_size(self):
                        return self._src.st_size + 5

                return _StatProxy(real)
            return real

        with patch.object(Path, "stat", fake_stat):
            with self.assertRaises(AudioUploadVerificationError):
                store_audit_audio_file(
                    audit_id=44,
                    audio_bytes=b"RIFFmismatch",
                    mime_type="audio/wav",
                    original_filename="x.wav",
                    input_hash="hash-mismatch",
                    existing_relative_path="2026/04/audit_44_hash.wav",
                )

        expected_path = Path(self.storage_dir) / "2026" / "04" / "audit_44_hash.wav"
        self.assertFalse(expected_path.exists())


if __name__ == "__main__":
    unittest.main()
