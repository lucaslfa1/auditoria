import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts import probe_huawei_obs  # noqa: E402


class _FakeResponse:
    def __init__(self, chunks):
        self._chunks = chunks

    def iter_content(self, chunk_size):
        self.chunk_size = chunk_size
        yield from self._chunks


class TestProbeHuaweiObsHardening(unittest.TestCase):
    def test_safe_get_sets_timeout_and_stream_flag(self):
        session = MagicMock()

        probe_huawei_obs._safe_get(session, "https://example.test/object", {"Auth": "x"}, stream=True)

        session.get.assert_called_once_with(
            "https://example.test/object",
            headers={"Auth": "x"},
            timeout=probe_huawei_obs.DEFAULT_HTTP_TIMEOUT,
            stream=True,
        )

    def test_safe_post_sets_timeout(self):
        session = MagicMock()

        probe_huawei_obs._safe_post(session, "https://example.test/object", {"Auth": "x"}, data=b"payload")

        session.post.assert_called_once_with(
            "https://example.test/object",
            headers={"Auth": "x"},
            data=b"payload",
            json=None,
            timeout=probe_huawei_obs.DEFAULT_HTTP_TIMEOUT,
        )

    def test_download_stream_to_file_writes_chunks_and_returns_head(self):
        response = _FakeResponse([b"abc", b"", b"def" * 20])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "sample.V3")
            total_bytes, head = probe_huawei_obs.download_stream_to_file(response, output_path)

            with open(output_path, "rb") as file:
                payload = file.read()

        self.assertEqual(payload, b"abc" + b"def" * 20)
        self.assertEqual(total_bytes, len(payload))
        self.assertEqual(head, payload[:32])

    def test_ffmpeg_commands_are_argument_lists(self):
        commands = probe_huawei_obs.ffmpeg_commands("storage/probe/sample.V3", "storage/probe")

        self.assertTrue(commands)
        for _name, command in commands:
            self.assertIsInstance(command, list)
            self.assertNotIn("&&", command)
            self.assertEqual(command[0], "ffmpeg")


if __name__ == "__main__":
    unittest.main()
