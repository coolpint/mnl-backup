# mnl-backup

`moneynlaw.co.kr` 기사와 이미지를 로컬에 안정적으로 백업하고, 기사별 XML과 전체 manifest XML을 생성하는 파이썬 도구입니다.

## 목표

- 기존 발행 기사 전체를 전수 백업
- 신규 기사 증분 동기화
- 원본 HTML, 이미지 바이너리, 정규화 XML, SQLite DB를 함께 유지
- 나중에 마이그레이션, 포털 전송, 2차 AI 가공에 재사용 가능한 구조 확보

## 저장 구조

기본 저장 경로는 `data/`입니다.

```text
data/
  db/backup.sqlite3
  archive/
    2026/03/
      html/000143.html
      xml/000143.xml
      media/000143/01.jpg
    manifests/articles.xml
```

## 사용법

초기 전수 백업:

```bash
python3 -m mnl_backup sync --full
```

증분 동기화:

```bash
python3 -m mnl_backup sync
```

테스트용 제한 실행:

```bash
python3 -m mnl_backup sync --max-pages 1 --limit 3
```

현황 확인:

```bash
python3 -m mnl_backup stats
```

manifest 재생성:

```bash
python3 -m mnl_backup export
```

스냅샷 생성:

```bash
python3 -m mnl_backup --data-dir data snapshot --output-dir exports
```

OneDrive 업로드:

```bash
export MNL_ONEDRIVE_TENANT_ID="..."
export MNL_ONEDRIVE_CLIENT_ID="..."
export MNL_ONEDRIVE_CLIENT_SECRET="..."
export MNL_ONEDRIVE_DRIVE_ID="..."
python3 -m mnl_backup onedrive-upload --snapshot-path exports/mnl-backup-20260309T000000Z.tar.gz
```

## 설계 메모

- 기사 목록은 `articleList.html?page=N&view_type=sm`에서 수집합니다.
- 기사 상세는 `articleView.html?idxno=...`에서 메타데이터와 본문을 추출합니다.
- 증분 동기화 때는 최신 페이지를 다시 읽어 수정 기사도 반영합니다.
- XML에는 기사 본문 HTML, 본문 텍스트, 타임스탬프, 분류, 작성자, 이미지 로컬 경로와 해시를 함께 저장합니다.

## 원격 실행

- 로컬 Mac이 꺼져 있어도 실행되게 하려면 GitHub Actions 같은 원격 스케줄러에서 `sync --full`을 돌리는 것이 가장 단순합니다.
- 예시 워크플로는 [.github/workflows/mnl-backup.yml](/Users/air/codes/mnl-backup/.github/workflows/mnl-backup.yml)에 추가했습니다.
- 이 워크플로는 매일 `06:17 KST`에 실행되도록 `21:17 UTC` cron으로 설정되어 있습니다.
- 원격 런너는 매번 새 환경이므로 기본값은 `전체 백업 -> tar.gz 스냅샷 생성 -> 아티팩트 저장` 흐름입니다.

## OneDrive 메모

- 무인(background) 업로드는 Microsoft Graph의 app-only 인증을 전제로 구현했습니다.
- 현재 업로더는 OneDrive app folder 하위에 `snapshots/` 폴더를 만들고 tar.gz 스냅샷을 업로드합니다.
- 필요한 비밀값은 다음 네 가지입니다.
  - `MNL_ONEDRIVE_TENANT_ID`
  - `MNL_ONEDRIVE_CLIENT_ID`
  - `MNL_ONEDRIVE_CLIENT_SECRET`
  - `MNL_ONEDRIVE_DRIVE_ID`
- 이 방식은 Microsoft 365 / OneDrive for Business 쪽이 가장 안정적입니다. 개인용 OneDrive는 사용자 위임 토큰/리프레시 토큰 운영이 더 복잡하므로 기본 구현 범위에서 제외했습니다.
