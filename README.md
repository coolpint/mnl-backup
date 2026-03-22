# mnl-backup

`moneynlaw.co.kr` 기사와 이미지를 안정적으로 보관하기 위한 백업 도구다. 원본 HTML, 이미지, 정규화 XML, SQLite DB를 함께 유지하고, 원격 환경에서는 `일간 증분 패키지 + 월간 전체 패키지` 구조로 보관한다.

## 목표

- 기존 발행 기사 전체를 전수 백업
- 신규/수정 기사 증분 동기화
- 나중에 다른 CMS export, 네이버/다음 포털 전송, AI 2차 가공에서 재사용 가능한 정규화 데이터 유지
- 로컬 Mac 전원과 무관한 원격 실행

## 저장 구조

기본 정규화 저장소는 `data/`다.

```text
data/
  db/backup.sqlite3
  archive/
    2026/03/
      html/000143.html
      xml/000143.xml
      media/000143/01.jpg
    manifests/
      articles.xml
      runs/
        run-000001.xml
```

원격 패키지는 로컬 기준으로 아래처럼 분리된다.

```text
exports/
  incremental/2026/03/11/mnl-backup-incremental-run000123-....tar.gz
  full/2026/04/mnl-backup-full-....tar.gz

runtime/
  state/current.tar.gz
```

- `data/`: 항상 최신 상태를 유지하는 정규화 저장소
- `exports/incremental/`: 일별 변경분만 담은 패키지
- `exports/full/`: 월 1회 전체 상태를 담은 패키지
- `runtime/state/current.tar.gz`: GitHub Actions 런너 복원용 상태 스냅샷

## 사용법

초기 전수 백업:

```bash
python3 -m mnl_backup sync --full
```

증분 동기화:

```bash
python3 -m mnl_backup sync
```

실행별 증분 패키지 생성:

```bash
python3 -m mnl_backup --json package-incremental --run-id 123 --output-dir exports
```

특정 실행의 변경 기사로 social source package 생성:

```bash
python3 -m mnl_backup --json social-export --run-id 123 --output-dir exports/social
```

월간 전체 패키지 생성:

```bash
python3 -m mnl_backup --json package-full --output-dir exports
```

런너 상태 스냅샷 생성:

```bash
python3 -m mnl_backup --json state-snapshot --output-dir runtime
```

상태 복원:

```bash
python3 -m mnl_backup restore --snapshot-path runtime/state/current.tar.gz --destination-root .
```

OneDrive 업로드:

```bash
export MNL_ONEDRIVE_TENANT_ID="..."
export MNL_ONEDRIVE_CLIENT_ID="..."
export MNL_ONEDRIVE_CLIENT_SECRET="..."
export MNL_ONEDRIVE_DRIVE_ID="..."
python3 -m mnl_backup onedrive-upload \
  --snapshot-path exports/full/2026/04/example.tar.gz \
  --remote-path backups/full/2026/04/example.tar.gz
```

OneDrive 다운로드:

```bash
python3 -m mnl_backup onedrive-download \
  --remote-path state/current.tar.gz \
  --output-path state/current.tar.gz \
  --missing-ok
```

## 설계 원칙

- 수집과 보관을 분리한다.
  - `service.py`: 기사 수집과 정규화 저장
- `packages.py`: 일간 증분/월간 전체 패키징
- `snapshot.py`: tar.gz 생성과 복원
- `onedrive.py`: SharePoint/OneDrive 전송
- `social_export.py`: 기사별 social source package 생성
- 정규화 XML을 기준 저장 포맷으로 유지한다.
  - 기사별 XML
  - 전체 manifest XML
  - 실행별 run manifest XML
- 나중에 CMS export나 포털 전송은 이 정규화 저장소를 읽는 별도 어댑터 계층으로 붙인다.

## Social Exporter

social exporter는 canonical archive를 읽어, 별도 게시 시스템이 소비할 self-contained package를 만든다.

- 입력: `sync run`, 기사 XML, 원본 HTML, 이미지, SQLite 메타
- 출력: 기사별 `package.json`, `article.json`, `rights.json`, `body.txt`, 복사된 원본 파일
- 역할: 공통 소스 패키지 생성만 담당
- 비역할: 유튜브/인스타/페북/스레드별 최종 콘텐츠 생성, 업로드, 재시도

즉 이 리포는 source-of-truth와 exporter까지만 담당하고, 게시 앱은 별도 repo에서 package contract만 읽는 구조를 권장한다. 상세 규격은 [docs/SOCIAL_EXPORTER.md](/Users/air/codes/mnl-backup/docs/SOCIAL_EXPORTER.md)를 본다.
publisher 상태 기록 규격은 [docs/SOCIAL_STATUS.md](/Users/air/codes/mnl-backup/docs/SOCIAL_STATUS.md)를 본다.

## 원격 실행

- 일간 증분 워크플로: [.github/workflows/mnl-backup-daily.yml](/Users/air/codes/mnl-backup/.github/workflows/mnl-backup-daily.yml)
  - 매일 `06:17 KST`
  - `state 복원 -> sync -> 증분 패키지 -> OneDrive 업로드 -> state 갱신 -> social export -> social inbox/notification 업로드`
- 월간 전체 워크플로: [.github/workflows/mnl-backup-monthly.yml](/Users/air/codes/mnl-backup/.github/workflows/mnl-backup-monthly.yml)
  - 매월 1일 `10:47 KST`
  - `state 복원 -> sync -> 전체 패키지 -> OneDrive 업로드 -> state 갱신`

## XML 구조 메모

- 기사별 XML은 제목, 분류, 작성자, 발행/수정 시각, 본문 HTML, 본문 텍스트, 이미지 메타, 해시를 보관한다.
- `articles.xml`은 전체 기사 인덱스다.
- `run-xxxxxx.xml`은 특정 동기화 실행에서 새로 생기거나 수정된 기사 목록과 변경 유형을 담는다.

이 구조는 포털 전송용 최종 XML 스키마와 1:1로 같지는 않지만, 나중에 네이버/다음용 어댑터나 CMS별 exporter를 붙이기 쉬운 중간 포맷으로 설계했다.
