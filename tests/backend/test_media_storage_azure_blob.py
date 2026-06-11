"""Testes do backend azure_blob de core/media_storage.py (v1.3.122).

O SDK azure-storage-blob NAO precisa estar instalado: injetamos um modulo
fake em sys.modules (o import no codigo e lazy). Cobre store/load/stream/
delete e a validacao de envs obrigatorias.

Exigem DATABASE_URL de teste para a tabela media_files (guard do conftest
bloqueia producao).
"""
import os
import sys
import types
import unittest
from unittest import mock

from core import media_storage


class _FakeDownloader:
    def __init__(self, data: bytes):
        self._data = data
        self.size = len(data)

    def readall(self) -> bytes:
        return self._data

    def chunks(self):
        yield self._data[: len(self._data) // 2]
        yield self._data[len(self._data) // 2:]


class _FakeBlobClient:
    def __init__(self, store: dict, key: str):
        self._store = store
        self._key = key

    def exists(self) -> bool:
        return self._key in self._store

    def download_blob(self) -> _FakeDownloader:
        return _FakeDownloader(self._store[self._key])

    def delete_blob(self) -> None:
        del self._store[self._key]


class _FakeContainerClient:
    def __init__(self, store: dict):
        self._store = store
        self.uploads: list[dict] = []

    def upload_blob(self, name, data, overwrite=False, content_settings=None):
        self._store[name] = bytes(data)
        self.uploads.append(
            {"name": name, "overwrite": overwrite, "content_settings": content_settings}
        )

    def get_blob_client(self, key: str) -> _FakeBlobClient:
        return _FakeBlobClient(self._store, key)


def _install_fake_azure_sdk(store: dict) -> _FakeContainerClient:
    """Monta azure.storage.blob fake em sys.modules e devolve o container."""
    container = _FakeContainerClient(store)

    class _FakeBlobServiceClient:
        @classmethod
        def from_connection_string(cls, _conn_str):
            return cls()

        def get_container_client(self, _name):
            return container

    class _FakeContentSettings:
        def __init__(self, content_type=None):
            self.content_type = content_type

    blob_module = types.ModuleType("azure.storage.blob")
    blob_module.BlobServiceClient = _FakeBlobServiceClient
    blob_module.ContentSettings = _FakeContentSettings
    azure_module = types.ModuleType("azure")
    storage_module = types.ModuleType("azure.storage")
    azure_module.storage = storage_module
    storage_module.blob = blob_module

    sys.modules["azure"] = azure_module
    sys.modules["azure.storage"] = storage_module
    sys.modules["azure.storage.blob"] = blob_module
    return container


def _pg_available() -> bool:
    try:
        from db.database import get_connection

        with get_connection() as conn:
            conn.cursor().execute("SELECT 1 FROM media_files LIMIT 1")
        return True
    except Exception:
        return False


_PG_OK = _pg_available()


@unittest.skipUnless(_PG_OK, "exige banco de teste migrado (media_files)")
class TestMediaStorageAzureBlob(unittest.TestCase):
    HASH = "classified:teste_azure_blob_hash"

    def setUp(self):
        self._store: dict = {}
        self.container = _install_fake_azure_sdk(self._store)
        self._env = mock.patch.dict(
            os.environ,
            {
                "MEDIA_STORAGE_BACKEND": "azure_blob",
                "AZURE_STORAGE_CONNECTION_STRING": "UseDevelopmentStorage=true",
                "AZURE_STORAGE_CONTAINER": "auditoria-midia-teste",
            },
        )
        self._env.start()
        self._cleanup_record()

    def tearDown(self):
        self._env.stop()
        self._cleanup_record()
        for name in ("azure.storage.blob", "azure.storage", "azure"):
            sys.modules.pop(name, None)

    def _cleanup_record(self):
        from db.database import get_connection

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM media_files WHERE file_hash = %s", (self.HASH,))
            conn.commit()

    def test_store_e_load_roundtrip(self):
        media_storage.store_media(
            self.HASH, b"RIFFazure", "audio.wav", "audio/wav", "classified/azure_hash.wav"
        )
        self.assertEqual(self._store["classified/azure_hash.wav"], b"RIFFazure")
        self.assertTrue(self.container.uploads[0]["overwrite"])
        self.assertEqual(
            self.container.uploads[0]["content_settings"].content_type, "audio/wav"
        )

        loaded = media_storage.load_media_bytes(self.HASH)
        self.assertEqual(loaded, b"RIFFazure")

    def test_open_media_stream(self):
        media_storage.store_media(
            self.HASH, b"0123456789", "audio.wav", "audio/wav", "classified/azure_hash.wav"
        )
        result = media_storage.open_media_stream(self.HASH)
        self.assertIsNotNone(result)
        iterator, size = result
        self.assertEqual(b"".join(iterator), b"0123456789")
        self.assertEqual(size, 10)

    def test_delete_media_remove_blob_e_registro(self):
        media_storage.store_media(
            self.HASH, b"RIFFdelete", "audio.wav", "audio/wav", "classified/azure_hash.wav"
        )
        deleted = media_storage.delete_media(self.HASH)
        self.assertTrue(deleted)
        self.assertNotIn("classified/azure_hash.wav", self._store)
        self.assertIsNone(media_storage.load_media_bytes(self.HASH))

    def test_connection_string_ausente_falha_com_erro_claro(self):
        with mock.patch.dict(os.environ, {"AZURE_STORAGE_CONNECTION_STRING": ""}):
            with self.assertRaises(media_storage.MediaStorageError) as ctx:
                media_storage.store_media(
                    self.HASH, b"x", "a.wav", "audio/wav", "classified/azure_hash.wav"
                )
            self.assertIn("AZURE_STORAGE_CONNECTION_STRING", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
