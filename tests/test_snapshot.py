from pathlib import Path
from tempfile import TemporaryDirectory
import tarfile
import unittest

from mnl_backup.snapshot import create_snapshot


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


if __name__ == "__main__":
    unittest.main()
