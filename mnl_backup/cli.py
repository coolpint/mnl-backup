from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Optional

from .onedrive import OneDriveClient, OneDriveConfig
from .snapshot import create_snapshot, restore_snapshot
from .service import BackupService


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "restore":
        restore_snapshot(
            snapshot_path=Path(args.snapshot_path),
            destination_root=Path(args.destination_root),
        )
        return emit_output(args, {"restored_to": str(Path(args.destination_root).resolve())})

    if args.command == "onedrive-upload":
        client = OneDriveClient(OneDriveConfig.from_env())
        remote_path = args.remote_path
        if not remote_path:
            remote_parts = [part for part in args.remote_dir.split("/") if part]
            remote_parts.append(Path(args.snapshot_path).name)
            result = client.upload_file(
                local_path=Path(args.snapshot_path),
                remote_parts=remote_parts,
            )
        else:
            result = client.upload_to_path(
                local_path=Path(args.snapshot_path),
                remote_path=remote_path,
            )
        return emit_output(args, result)

    if args.command == "onedrive-upload-tree":
        client = OneDriveClient(OneDriveConfig.from_env())
        result = client.upload_directory_to_path(
            local_dir=Path(args.local_dir),
            remote_path=args.remote_path,
        )
        return emit_output(args, result)

    if args.command == "onedrive-download":
        client = OneDriveClient(OneDriveConfig.from_env())
        downloaded = client.download_from_path(
            remote_path=args.remote_path,
            local_path=Path(args.output_path),
            missing_ok=args.missing_ok,
        )
        return emit_output(
            args,
            {
                "found": downloaded is not None,
                "output_path": None if downloaded is None else str(downloaded),
            },
        )

    if args.command == "snapshot":
        snapshot_path = create_snapshot(
            data_dir=Path(args.data_dir),
            output_dir=Path(args.output_dir),
            prefix=args.prefix,
        )
        return emit_output(args, {"snapshot_path": str(snapshot_path)})

    service = BackupService(Path(args.data_dir))
    try:
        if args.command == "sync":
            summary = service.sync(
                full=args.full,
                max_pages=args.max_pages,
                refresh_pages=args.refresh_pages,
                delay_seconds=args.delay,
                limit=args.limit,
            )
            emit_output(args, summary)
            return 1 if summary.errors else 0

        if args.command == "export":
            manifest_path = service.export_manifest()
            return emit_output(args, {"manifest_path": manifest_path})

        if args.command == "package-incremental":
            result = service.create_incremental_package(
                run_id=args.run_id,
                output_root=Path(args.output_dir),
            )
            return emit_output(args, result)

        if args.command == "package-full":
            result = service.create_full_package(output_root=Path(args.output_dir))
            return emit_output(args, result)

        if args.command == "state-snapshot":
            snapshot_path = service.create_state_snapshot(output_root=Path(args.output_dir))
            return emit_output(args, {"snapshot_path": str(snapshot_path)})

        if args.command == "social-export":
            result = service.export_social_packages(
                run_id=args.run_id,
                output_root=Path(args.output_dir),
            )
            return emit_output(args, result)

        stats = service.stats()
        return emit_output(args, stats)
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
    parser.add_argument(
        "--json",
        action="store_true",
        help="기계가 읽기 쉬운 JSON으로 결과를 출력합니다",
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

    incremental_parser = subparsers.add_parser(
        "package-incremental",
        help="특정 sync run의 변경 기사만 담은 증분 패키지를 생성합니다",
    )
    incremental_parser.add_argument("--run-id", type=int, required=True, help="패키징할 sync run ID")
    incremental_parser.add_argument(
        "--output-dir",
        default="exports",
        help="생성된 증분 패키지를 저장할 디렉터리 루트",
    )

    full_parser = subparsers.add_parser(
        "package-full",
        help="현재 data 디렉터리 전체를 월간 전체 패키지로 압축합니다",
    )
    full_parser.add_argument(
        "--output-dir",
        default="exports",
        help="생성된 전체 패키지를 저장할 디렉터리 루트",
    )

    state_parser = subparsers.add_parser(
        "state-snapshot",
        help="원격 런너 복원을 위한 현재 data 상태 스냅샷을 생성합니다",
    )
    state_parser.add_argument(
        "--output-dir",
        default="exports",
        help="상태 스냅샷을 저장할 디렉터리 루트",
    )

    social_export_parser = subparsers.add_parser(
        "social-export",
        help="특정 sync run의 변경 기사들로 social source package를 생성합니다",
    )
    social_export_parser.add_argument("--run-id", type=int, required=True, help="social package를 만들 sync run ID")
    social_export_parser.add_argument(
        "--output-dir",
        default="exports/social",
        help="social package 배치를 저장할 디렉터리 루트",
    )

    restore_parser = subparsers.add_parser(
        "restore",
        help="tar.gz 스냅샷을 지정한 루트 디렉터리에 복원합니다",
    )
    restore_parser.add_argument("--snapshot-path", required=True, help="복원할 tar.gz 파일 경로")
    restore_parser.add_argument(
        "--destination-root",
        default=".",
        help="압축을 풀 대상 루트 디렉터리",
    )

    onedrive_upload_parser = subparsers.add_parser(
        "onedrive-upload",
        help="스냅샷 파일을 OneDrive app folder 하위로 업로드합니다",
    )
    onedrive_upload_parser.add_argument("--snapshot-path", required=True, help="업로드할 tar.gz 스냅샷 경로")
    onedrive_upload_parser.add_argument(
        "--remote-dir",
        default="snapshots",
        help="OneDrive app folder 하위 저장 폴더명",
    )
    onedrive_upload_parser.add_argument(
        "--remote-path",
        default="",
        help="OneDrive app folder 기준 전체 저장 경로(파일명 포함)",
    )

    onedrive_download_parser = subparsers.add_parser(
        "onedrive-download",
        help="OneDrive app folder 하위 파일을 다운로드합니다",
    )
    onedrive_download_parser.add_argument(
        "--remote-path",
        required=True,
        help="OneDrive app folder 기준 다운로드할 파일 경로",
    )
    onedrive_download_parser.add_argument(
        "--output-path",
        required=True,
        help="로컬 저장 파일 경로",
    )
    onedrive_download_parser.add_argument(
        "--missing-ok",
        action="store_true",
        help="원격 파일이 없으면 실패하지 않고 found=false를 반환합니다",
    )

    onedrive_upload_tree_parser = subparsers.add_parser(
        "onedrive-upload-tree",
        help="로컬 디렉터리 트리를 OneDrive app folder 하위로 업로드합니다",
    )
    onedrive_upload_tree_parser.add_argument(
        "--local-dir",
        required=True,
        help="업로드할 로컬 디렉터리 경로",
    )
    onedrive_upload_tree_parser.add_argument(
        "--remote-path",
        required=True,
        help="OneDrive app folder 기준 업로드할 폴더 경로",
    )
    return parser


def emit_output(args, payload: Any) -> int:
    data = normalize_payload(payload)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, list):
                print(f"{key}:")
                for item in value:
                    print(f"  - {item}")
                continue
            print(f"{key}: {value}")
        return 0

    print(data)
    return 0


def normalize_payload(payload: Any) -> Any:
    if is_dataclass(payload):
        return normalize_payload(asdict(payload))
    if isinstance(payload, Path):
        return str(payload)
    if isinstance(payload, dict):
        return {key: normalize_payload(value) for key, value in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [normalize_payload(item) for item in payload]
    return payload
