from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .onedrive import OneDriveClient, OneDriveConfig
from .snapshot import create_snapshot
from .service import BackupService


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "sync":
        service = BackupService(Path(args.data_dir))
        try:
            summary = service.sync(
                full=args.full,
                max_pages=args.max_pages,
                refresh_pages=args.refresh_pages,
                delay_seconds=args.delay,
                limit=args.limit,
            )
            print("mode:", summary.mode)
            print("discovered:", summary.discovered_count)
            print("fetched:", summary.fetched_count)
            print("updated:", summary.updated_count)
            print("manifest:", summary.manifest_path)
            if summary.errors:
                print("errors:")
                for error in summary.errors:
                    print("  -", error)
                return 1
            return 0
        finally:
            service.close()

    if args.command == "export":
        service = BackupService(Path(args.data_dir))
        try:
            manifest_path = service.export_manifest()
            print(manifest_path)
            return 0
        finally:
            service.close()

    if args.command == "snapshot":
        snapshot_path = create_snapshot(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            prefix=args.prefix,
        )
        print(snapshot_path)
        return 0

    if args.command == "onedrive-upload":
        client = OneDriveClient(OneDriveConfig.from_env())
        remote_parts = [part for part in args.remote_dir.split("/") if part]
        remote_parts.append(Path(args.snapshot_path).name)
        result = client.upload_file(
            local_path=Path(args.snapshot_path),
            remote_parts=remote_parts,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    service = BackupService(Path(args.data_dir))
    try:
        stats = service.stats()
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0
    finally:
        service.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m mnl_backup",
        description="머니앤로 기사 백업 및 XML 아카이브 도구",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="백업 산출물(DB, XML, HTML, 이미지)을 저장할 디렉터리",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    sync_parser = subparsers.add_parser("sync", help="기사 목록을 수집하고 로컬 백업을 갱신합니다")
    sync_parser.add_argument("--full", action="store_true", help="전체 기사 목록을 처음부터 끝까지 다시 스캔합니다")
    sync_parser.add_argument("--max-pages", type=int, default=None, help="스캔할 기사 목록 페이지 수 상한")
    sync_parser.add_argument(
        "--refresh-pages",
        type=int,
        default=2,
        help="증분 동기화 때 항상 다시 가져올 최신 페이지 수",
    )
    sync_parser.add_argument("--delay", type=float, default=0.2, help="요청 사이 대기 시간(초)")
    sync_parser.add_argument("--limit", type=int, default=None, help="실제로 가져올 기사 수 상한")

    subparsers.add_parser("export", help="DB 기준으로 XML manifest를 다시 생성합니다")
    subparsers.add_parser("stats", help="현재 로컬 백업 상태를 요약합니다")

    snapshot_parser = subparsers.add_parser("snapshot", help="현재 data 디렉터리를 tar.gz 스냅샷으로 압축합니다")
    snapshot_parser.add_argument(
        "--output-dir",
        default="exports",
        help="생성된 스냅샷 파일을 저장할 디렉터리",
    )
    snapshot_parser.add_argument(
        "--prefix",
        default="mnl-backup",
        help="스냅샷 파일명 접두어",
    )

    onedrive_parser = subparsers.add_parser(
        "onedrive-upload",
        help="스냅샷 파일을 OneDrive app folder 하위로 업로드합니다",
    )
    onedrive_parser.add_argument("--snapshot-path", required=True, help="업로드할 tar.gz 스냅샷 경로")
    onedrive_parser.add_argument(
        "--remote-dir",
        default="snapshots",
        help="OneDrive app folder 하위 저장 폴더명",
    )
    return parser
