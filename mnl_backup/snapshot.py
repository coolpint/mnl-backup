from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path


def create_snapshot(data_dir: Path, output_dir: Path, prefix: str = "mnl-backup") -> Path:
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    snapshot_path = output_dir / f"{prefix}-{timestamp}.tar.gz"

    with tarfile.open(snapshot_path, "w:gz") as archive:
        archive.add(data_dir, arcname=data_dir.name)

    return snapshot_path

