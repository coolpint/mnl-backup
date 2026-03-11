from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest

from mnl_backup.onedrive import _clean_env_value
from mnl_backup.snapshot import create_snapshot, restore_snapshot


class SnapshotTests(unittest.TestCase):
    def test_create_snapshot_contains_data_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data_dir = base / "data"
            output_dir = base / "exports"
            (data_dir / "archive").mkdir(parents=True, exist_ok=True)
            (data_dir / "archive" / "sample.txt").write_text("hello", encoding="utf-8")

            snapshot_path = create_snapshot(data_dir=data_dir, output_dir=output_dir)

            self.assertTrue(snapshot_path.exists())
            with tarfile.open(snapshot_path, "r:gz") as archive:
                names = archive.getnames()
            self.assertIn("data/archive/sample.txt", names)

    def test_restore_snapshot_extracts_archived_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            data_dir = base / "data"
            output_dir = base / "exports"
            restore_root = base / "restored"
            (data_dir / "archive").mkdir(parents=True, exist_ok=True)
            (data_dir / "archive" / "sample.txt").write_text("hello", encoding="utf-8")

            snapshot_path = create_snapshot(data_dir=data_dir, output_dir=output_dir)
            restore_snapshot(snapshot_path=snapshot_path, destination_root=restore_root)

            restored = restore_root / "data" / "archive" / "sample.txt"
            self.assertTrue(restored.exists())
            self.assertEqual(restored.read_text(encoding="utf-8"), "hello")

    def test_clean_env_value_strips_wrapping_quotes_and_whitespace(self) -> None:
        self.assertEqual(_clean_env_value('  "b!abc123"  '), "b!abc123")
        self.assertEqual(_clean_env_value("  'tenant-id' "), "tenant-id")


if __name__ == "__main__":
    unittest.main()
