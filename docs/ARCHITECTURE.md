# Architecture

## 모듈 분리

- `mnl_backup/service.py`
  - 기사 목록/상세 수집
  - HTML, 이미지, 기사 XML, 전체 manifest 생성
  - 실행별 run manifest 생성
- `mnl_backup/storage.py`
  - SQLite 스키마와 실행 이력 관리
  - 증분 패키징에 필요한 변경 기사 조회
- `mnl_backup/packages.py`
  - `incremental/` 패키지 생성
  - `full/` 패키지 생성
  - 원격 런너 상태 스냅샷 생성
- `mnl_backup/social_export.py`
  - sync run 기준 social source package 생성
  - 기사별 self-contained package 작성
- `mnl_backup/snapshot.py`
  - tar.gz 생성
  - 안전한 복원
- `mnl_backup/onedrive.py`
  - app-only 인증
  - SharePoint/OneDrive 업로드와 다운로드

## 데이터 계층

### 1. Canonical Archive

항상 최신 상태를 유지하는 기준 저장소다.

- `data/db/backup.sqlite3`
- `data/archive/YYYY/MM/html/...`
- `data/archive/YYYY/MM/xml/...`
- `data/archive/YYYY/MM/media/...`
- `data/archive/manifests/articles.xml`
- `data/archive/manifests/runs/run-xxxxxx.xml`

### 2. Delivery Packages

외부 저장소로 보내는 전달 단위다.

- `exports/incremental/YYYY/MM/DD/*.tar.gz`
  - 특정 sync run에서 바뀐 기사만 포함
  - 기사 XML, 원본 HTML, 이미지, 전체 manifest, run manifest 포함
- `exports/full/YYYY/MM/*.tar.gz`
  - 현재 canonical archive 전체 포함

### 3. Runner State

GitHub Actions 런너가 다음 실행 때 이어받기 위한 운영 상태다.

- `runtime/state/current.tar.gz`

이 파일은 백업 보존본이 아니라 원격 런너 복원용이다.

## 향후 확장 방향

- `exporters/naver.py`
- `exporters/daum.py`
- `exporters/wordpress.py`
- `exporters/custom_cms.py`
- `exporters/social.py`

이 계층은 스크래퍼를 직접 읽지 않고, 반드시 canonical archive의 XML/DB를 읽도록 유지하는 것이 맞다. 그렇게 해야 수집 로직과 전송 로직이 분리되고, 포털 전송 스키마가 바뀌어도 exporter만 수정하면 된다.

social 쪽도 같은 원칙을 따른다.

- `mnl-backup`: social source package 생성
- 별도 publisher repo: YouTube/Instagram/Facebook/Threads별 builder + publisher
- 연결 방식: 코드 import가 아니라 package contract
