import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from light_video_enhancer_forked import model_manager


def _two_file_pack(payload_a, payload_b):
    files = ["repair-test/a.bin", "repair-test/b.bin"]
    return model_manager._remote_pack(
        "repair-test", "repair-test", "Test pack", "Test pack", files,
        downloads={files[0]: "a.bin", files[1]: "b.bin"},
        official_base="https://example.invalid/models",
        mirror_base="https://example.invalid/models",
        download_size=len(payload_a) + len(payload_b),
        hashes={
            files[0]: hashlib.sha256(payload_a).hexdigest(),
            files[1]: hashlib.sha256(payload_b).hexdigest(),
        })


class _Response:
    def __init__(self, status, headers, data):
        self.status = status
        self.headers = headers
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if not self._data:
            return b""
        value, self._data = self._data[:size], self._data[size:]
        return value


class ModelRepairTests(unittest.TestCase):
    def _install(self, temporary, relative, payload):
        path = Path(temporary).joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        return path

    def test_repair_refetches_only_the_corrupt_file(self):
        payload_a = b"healthy model bytes"
        payload_b = b"second file payload"
        pack = _two_file_pack(payload_a, payload_b)
        response = _Response(
            200, {"Content-Length": str(len(payload_b))}, payload_b)

        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(model_manager, "MODEL_PACKS", (pack,)), \
                mock.patch.object(
                    model_manager, "_BY_ID", {pack["id"]: pack}), \
                mock.patch.object(
                    model_manager, "get_model_root", return_value=temporary), \
                mock.patch.object(model_manager.urllib.request, "urlopen",
                                  return_value=response) as open_url:
            good = self._install(temporary, "repair-test/a.bin", payload_a)
            corrupt = self._install(
                temporary, "repair-test/b.bin", b"damaged beyond repair")
            stages = []
            model_manager.repair_model_pack(
                pack["id"], "github", None,
                lambda stage, current, total: stages.append(
                    (stage, current, total)))

            self.assertEqual(good.read_bytes(), payload_a)
            self.assertEqual(corrupt.read_bytes(), payload_b)
            # Only the corrupt file was fetched over the network.
            open_url.assert_called_once()
            self.assertIn("verify", [stage for stage, _, _ in stages])
            self.assertIn("download", [stage for stage, _, _ in stages])

    def test_repair_of_a_healthy_pack_touches_nothing(self):
        payload_a = b"healthy model bytes"
        payload_b = b"second file payload"
        pack = _two_file_pack(payload_a, payload_b)

        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(model_manager, "MODEL_PACKS", (pack,)), \
                mock.patch.object(
                    model_manager, "_BY_ID", {pack["id"]: pack}), \
                mock.patch.object(
                    model_manager, "get_model_root", return_value=temporary), \
                mock.patch.object(model_manager.urllib.request, "urlopen") as open_url:
            self._install(temporary, "repair-test/a.bin", payload_a)
            self._install(temporary, "repair-test/b.bin", payload_b)

            model_manager.repair_model_pack(pack["id"], "github", None, None)

            open_url.assert_not_called()
            self.assertEqual(
                Path(temporary, "repair-test", "a.bin").read_bytes(), payload_a)
            self.assertEqual(
                Path(temporary, "repair-test", "b.bin").read_bytes(), payload_b)

    def test_repair_downloads_a_missing_file(self):
        payload_a = b"healthy model bytes"
        payload_b = b"second file payload"
        pack = _two_file_pack(payload_a, payload_b)
        response = _Response(
            200, {"Content-Length": str(len(payload_b))}, payload_b)

        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(model_manager, "MODEL_PACKS", (pack,)), \
                mock.patch.object(
                    model_manager, "_BY_ID", {pack["id"]: pack}), \
                mock.patch.object(
                    model_manager, "get_model_root", return_value=temporary), \
                mock.patch.object(model_manager.urllib.request, "urlopen",
                                  return_value=response) as open_url:
            self._install(temporary, "repair-test/a.bin", payload_a)

            model_manager.repair_model_pack(pack["id"], "github", None, None)

            open_url.assert_called_once()
            self.assertEqual(
                Path(temporary, "repair-test", "b.bin").read_bytes(), payload_b)

    def test_repair_of_an_archive_pack_reinstalls_the_verified_archive(self):
        pack = model_manager._pack(
            "zip-repair", "zip-repair.zip", "Test zip pack", "Test zip pack",
            ["zip-repair/model.bin"])
        with mock.patch.object(model_manager, "MODEL_PACKS", (pack,)), \
                mock.patch.object(
                    model_manager, "_BY_ID", {pack["id"]: pack}), \
                mock.patch.object(model_manager, "download_model_pack") as download:
            model_manager.repair_model_pack(
                pack["id"], "mirror", "https://example.invalid/base", None)
            download.assert_called_once_with(
                pack["id"], "mirror", "https://example.invalid/base", None)


if __name__ == "__main__":
    unittest.main()
