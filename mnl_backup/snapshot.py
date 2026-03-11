from __future__ import annotations

import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


def create_snapshot(
    data_dir: Path,
    output_dir: Optional[Path] = None,
    prefix: str = "mnl-backup",
    output_path: Optional[Path] = None,
) -> Path:
    data_dir = Path(data_dir)
    if output_path is None:
        if output_dir is None:
            raise ValueError("output_dir or output_path must be provided")
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = output_dir / f"{prefix}-{timestamp}.tar.gz"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    return create_snapshot_from_paths(
        base_dir=data_dir.parent,
        rel_paths=[data_dir.name],
        output_path=output_path,
    )


def create_snapshot_from_paths(base_dir: Path, rel_paths: Iterable[str], output_path: Path) -> Path:
    base_dir = Path(base_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(output_path, "w:gz") as archive:
        seen = set()
        for raw_rel_path in rel_paths:
            rel_path = Path(raw_rel_path)
            if rel_path.as_posix() in seen:
                continue
            seen.add(rel_path.as_posix())
            abs_path = base_dir / rel_path
            if abs_path.exists():
                archive.add(abs_path, arcname=rel_path.as_posix())

    return output_path


def restore_snapshot(snapshot_path: Path, destination_root: Path) -> None:
    snapshot_path = Path(snapshot_path)
    destination_root = Path(destination_root)
    destination_root.mkdir(parents=True, exist_ok=True)

    with tarfile.open(snapshot_path, "r:gz") as archive:
        members = archive.getmembers()
        _assert_safe_members(destination_root, members)
        archive.extractall(destination_root)


def _assert_safe_members(destination_root: Path, members) -> None:
    root = destination_root.resolve()
    for member in members:
        target = (destination_root / member.name).resolve()
        if root not in {target, *target.parents}:
            raise ValueError(f"Unsafe archive member path: {member.name}")
