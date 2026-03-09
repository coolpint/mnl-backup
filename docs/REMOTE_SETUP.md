# Remote Setup Checklist

이 문서는 `mnl_backup`를 로컬 Mac 전원과 무관하게 GitHub Actions에서 실행하고,
스냅샷을 Microsoft 365(OneDrive/SharePoint)로 업로드하기 위한 준비 항목을 정리한다.

## 현재 상태

- GitHub 원격 저장소: `git@github.com:coolpint/mnl-backup.git`
- 기본 브랜치: `main`
- 원격 워크플로: `.github/workflows/mnl-backup.yml`
- 기본 실행 시간: 매일 `06:17 KST`

## 1. GitHub에서 확인할 것

- 저장소 `Actions`가 활성화되어 있어야 한다.
- 기본 브랜치가 `main`이어야 한다.
- 필요하면 워크플로를 수동 실행해 1회 테스트한다.

## 2. Microsoft 365 쪽 권장 구조

권장 저장 위치:

- 개인 사용자 OneDrive 루트가 아니라
- 전용 SharePoint 사이트의 문서 라이브러리

예시:

- 사이트 이름: `MNL Backup`
- 라이브러리: `Documents`
- 업로드 대상 폴더: 앱 전용 `AppRoot/snapshots`

## 3. Entra 앱 등록에서 준비할 값

앱 1개를 생성하고 아래 값을 확보한다.

- `Tenant ID`
- `Client ID`
- `Client Secret`
- 업로드 대상 라이브러리의 `Drive ID`

권한:

- Microsoft Graph
- `Application permission`
- `Files.ReadWrite.AppFolder`

그리고 `Admin consent`를 수행한다.

## 4. GitHub Secrets에 넣을 값

저장소 `Settings > Secrets and variables > Actions`에 아래 4개를 등록한다.

- `MNL_ONEDRIVE_TENANT_ID`
- `MNL_ONEDRIVE_CLIENT_ID`
- `MNL_ONEDRIVE_CLIENT_SECRET`
- `MNL_ONEDRIVE_DRIVE_ID`

## 5. 드라이브 ID 확인 메모

코드는 `drive id`만 있으면 동작한다.

SharePoint 문서 라이브러리를 쓸 경우:

- 대상 사이트를 정한 뒤
- 해당 문서 라이브러리의 `drive id`를 확인해서
- `MNL_ONEDRIVE_DRIVE_ID`로 넣는다.

## 6. 워크플로 동작 순서

매일 실행 시 아래 순서로 진행된다.

1. `python -m mnl_backup --data-dir data sync --full --delay 0.5`
2. `python -m mnl_backup --data-dir data snapshot --output-dir exports`
3. GitHub Actions artifact 업로드
4. OneDrive 업로드

## 7. 운영 중 바꾸기 쉬운 값

- 실행 시간: `.github/workflows/mnl-backup.yml`
- OneDrive 하위 폴더명: `onedrive-upload --remote-dir snapshots`
- artifact 보관일: `retention-days`

## 8. 첫 운영 점검 포인트

- Actions 첫 실행이 성공하는지
- artifact가 생성되는지
- OneDrive/SharePoint에 tar.gz가 올라가는지
- 업로드 파일명이 날짜별로 누적되는지
- 다음 날 동일한 스케줄로 다시 실행되는지
