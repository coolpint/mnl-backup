from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from .snapshot import create_snapshot, create_snapshot_from_paths


@dataclass
class PackageResult:
    package_type: str
    package_path: Path
    article_count: int
    file_count: int
    remote_dir: str


def create_full_package(
    data_dir: Path,
    output_root: Path,
    timestamp: Optional[datetime] = None,
    prefix: str = "mnl-backup-full",
    article_count: int = 0,
) -> PackageResult:
    timestamp = timestamp or datetime.now(timezone.utc)
    package_dir = output_root / "full" / timestamp.strftime("%Y") / timestamp.strftime("%m")
    package_path = package_dir / f"{prefix}-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    create_snapshot(data_dir=data_dir, output_path=package_path)
    return PackageResult(
        package_type="full",
        package_path=package_path,
        article_count=article_count,
        file_count=count_files(data_dir),
        remote_dir=package_path.parent.relative_to(output_root).as_posix(),
    )


def create_incremental_package(
    data_dir: Path,
    output_root: Path,
    run_id: int,
    rel_paths: Iterable[str],
    article_count: int,
    timestamp: Optional[datetime] = None,
    prefix: str = "mnl-backup-incremental",
) -> PackageResult:
    timestamp = timestamp or datetime.now(timezone.utc)
    package_dir = (
        output_root
        / "incremental"
        / timestamp.strftime("%Y")
        / timestamp.strftime("%m")
        / timestamp.strftime("%d")
    )
    package_dir.mkdir(parents=True, exist_ok=True)
    package_path = package_dir / (
        f"{prefix}-run{run_id:06d}-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.tar.gz"
    )

    rel_path_list = list(dict.fromkeys(str(Path(path)) for path in rel_paths))
    create_snapshot_from_paths(
        base_dir=Path(data_dir).parent,
        rel_paths=[str(Path(data_dir).name / Path(path)) for path in rel_path_list],
        output_path=package_path,
    )
    return PackageResult(
        package_type="incremental",
        package_path=package_path,
        article_count=article_count,
        file_count=len(rel_path_list),
        remote_dir=package_path.parent.relative_to(output_root).as_posix(),
    )


def create_state_snapshot(
    data_dir: Path,
    output_root: Path,
    filename: str = "current.tar.gz",
) -> Path:
    output_path = Path(output_root) / "state" / filename
    return create_snapshot(data_dir=data_dir, output_path=output_path)


def count_files(root: Path) -> int:
    return sum(1 for path in Path(root).rglob("*") if path.is_file())
