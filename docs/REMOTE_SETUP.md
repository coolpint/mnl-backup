# Remote Setup Checklist

이 문서는 `mnl_backup`를 로컬 Mac 전원과 무관하게 GitHub Actions에서 실행하고, 결과를 Microsoft 365(SharePoint/OneDrive)로 누적 보관하기 위한 준비 항목을 정리한다.

## 현재 구조

- GitHub 원격 저장소: `git@github.com:coolpint/mnl-backup.git`
- 기본 브랜치: `main`
- 일간 증분 워크플로: `.github/workflows/mnl-backup-daily.yml`
- 월간 전체 워크플로: `.github/workflows/mnl-backup-monthly.yml`
- 일간 증분 실행 시간: 매일 `06:17 KST`
- 월간 전체 실행 시간: 매월 1일 `10:47 KST`

## 1. GitHub에서 확인할 것

- 저장소 `Actions`가 활성화되어 있어야 한다.
- 기본 브랜치가 `main`이어야 한다.
- 필요하면 두 워크플로를 각각 수동 실행해 1회 테스트한다.

## 2. Microsoft 365 쪽 권장 구조

권장 저장 위치:

- 개인 사용자 OneDrive 루트가 아니라
- 전용 SharePoint 사이트의 문서 라이브러리

예시:

- 사이트 이름: `MNL Backup`
- 라이브러리: `Documents`
- 실제 업로드 위치:
  - `Apps/mnl-backup-prod/backups/incremental/...`
  - `Apps/mnl-backup-prod/backups/full/...`
  - `Apps/mnl-backup-prod/state/current.tar.gz`
  - `Apps/mnl-backup-prod/social/inbox/...`
  - `Apps/mnl-backup-prod/social/notifications/...`
  - `Apps/mnl-backup-prod/social/status/...` (publisher가 기록)

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

### 일간 증분

1. OneDrive `state/current.tar.gz` 다운로드
2. 로컬 `data/` 복원
3. `python -m mnl_backup --data-dir data sync`
4. `python -m mnl_backup --data-dir data package-incremental --run-id ...`
5. GitHub artifact 업로드
6. OneDrive `backups/incremental/YYYY/MM/DD/...tar.gz` 업로드
7. 새 `state/current.tar.gz` 생성 및 덮어쓰기
 8. `python -m mnl_backup --data-dir data social-export --run-id ...`
 9. OneDrive `social/inbox/YYYY/MM/DD/run-xxxxxx/...` 업로드
 10. OneDrive `social/notifications/YYYY/MM/DD/run-xxxxxx.json` 및 `social/notifications/latest.json` 업로드

### 월간 전체

1. OneDrive `state/current.tar.gz` 다운로드
2. 로컬 `data/` 복원
3. `python -m mnl_backup --data-dir data sync`
4. `python -m mnl_backup --data-dir data package-full`
5. GitHub artifact 업로드
6. OneDrive `backups/full/YYYY/MM/...tar.gz` 업로드
7. 새 `state/current.tar.gz` 생성 및 덮어쓰기

## 7. 운영 중 바꾸기 쉬운 값

- 일간 실행 시간: `.github/workflows/mnl-backup-daily.yml`
- 월간 실행 시간: `.github/workflows/mnl-backup-monthly.yml`
- OneDrive 하위 경로:
  - 증분: `backups/incremental/...`
  - 전체: `backups/full/...`
  - 상태: `state/current.tar.gz`
  - social inbox: `social/inbox/...`
  - social notifications: `social/notifications/...`
  - social status: `social/status/...` (publisher 소유 경로)
- artifact 보관일: 각 워크플로의 `retention-days`

## 8. 첫 운영 점검 포인트

- 일간 증분 실행이 성공하는지
- 월간 전체 실행이 성공하는지
- SharePoint 문서 라이브러리에서 `Apps/<앱명>/backups/incremental` 경로가 생기는지
- SharePoint 문서 라이브러리에서 `Apps/<앱명>/backups/full` 경로가 생기는지
- `Apps/<앱명>/state/current.tar.gz`가 매 실행 후 갱신되는지
