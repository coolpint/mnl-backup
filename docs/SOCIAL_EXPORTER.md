# Social Exporter

`social exporter`는 canonical archive를 읽어 기사별 `social source package`를 만든다. 이 패키지는 별도 게시 시스템이 공통 입력으로 사용한다.

## 역할

- 특정 `sync run`에 포함된 모든 변경 기사를 social package로 변환
- 기사 XML, 원본 HTML, 로컬 이미지, 본문 텍스트, 권리 검토 scaffold를 한 폴더에 묶기
- YouTube/Instagram/Facebook/Threads용 downstream builder가 공통으로 읽을 수 있는 최소 계약 제공

하지 않는 일:

- 플랫폼별 최종 카피/영상 생성
- 플랫폼 API 업로드
- 재시도, 스케줄링, 승인 처리

이 구분을 유지해야 백업 시스템과 게시 시스템이 서로의 장애를 전파하지 않는다.

## 권장 시스템 경계

- 이 repo
  - 수집
  - 보관
  - `social-export`
- 별도 repo (`mnl-social-publishers`)
  - `youtube_shorts_builder`, `youtube_publisher`
  - `instagram_builder`, `instagram_publisher`
  - `facebook_builder`, `facebook_publisher`
  - `threads_builder`, `threads_publisher`

## CLI

```bash
python3 -m mnl_backup --json social-export \
  --run-id 123 \
  --output-dir exports/social
```

## 출력 구조

```text
exports/social/
  2026/03/14/
    run-000123/
      batch.json
      notification.json
      article-000143/
        package.json
        article.json
        rights.json
        article.xml
        source.html
        body.txt
        assets/
          source-media/
            01.jpg
```

## 파일 설명

- `batch.json`
  - 실행 단위 manifest
  - 어떤 기사 package가 생성되었는지 목록 제공
- `notification.json`
  - publisher가 새 배치를 감지하기 위한 이벤트 파일
  - `latest.json` 또는 날짜별 notification 경로로 복사 업로드하기 좋게 설계
- `package.json`
  - downstream 시스템이 제일 먼저 읽는 진입점
  - 플랫폼별 builder/publisher 이름, review 정책, 파일 경로 포함
- `article.json`
  - 기사 메타, 본문, 해시, asset 메타
- `rights.json`
  - 기사 텍스트, 이미지, 음악 관련 검수 필요 상태
- `article.xml`, `source.html`
  - canonical archive 원본 복사본
- `body.txt`
  - LLM/TTS/자막 생성기가 읽기 쉬운 본문 텍스트

## 설계 원칙

- package는 self-contained여야 한다.
  - downstream repo가 canonical archive 전체를 알 필요가 없게 한다.
- package는 source package일 뿐이다.
  - 플랫폼별 최종 포맷 차이는 builder가 책임진다.
- 모든 플랫폼은 기본적으로 `manual review required`를 전제로 한다.
- `rights.json`의 기본값은 보수적으로 둔다.
  - 이미지 `social_use_allowed=false`
  - 음악 `license_required=true`

## 권장 SharePoint 적재 경로

```text
social/
  inbox/YYYY/MM/DD/run-000123/...
  notifications/YYYY/MM/DD/run-000123.json
  notifications/latest.json
```

- `social/inbox`
  - publisher가 실제 package를 읽는 위치
- `social/notifications/latest.json`
  - 새 배치가 생겼는지 빠르게 확인하는 포인터
- `social/notifications/YYYY/MM/DD/run-xxxxxx.json`
  - 배치별 이벤트 로그

publisher가 처리 상태를 남기는 규격은 [docs/SOCIAL_STATUS.md](/Users/air/codes/mnl-backup/docs/SOCIAL_STATUS.md)를 따른다.

## Builder / Publisher 분리

추천 구조:

- builder
  - source package를 읽어 플랫폼용 draft 산출물 생성
  - 예: `preview.mp4`, `caption.txt`, `threads_post.txt`
- publisher
  - draft 또는 승인된 결과물을 실제 API로 업로드
  - 예: YouTube private 업로드, Threads post 생성

이렇게 나누면 다음 장점이 있다.

- 플랫폼 정책 변화가 builder/publisher 내부로 격리된다.
- 한 플랫폼 API 장애가 다른 플랫폼에 전파되지 않는다.
- review 승인을 builder와 publisher 사이에서 끼워 넣기 쉽다.

## 향후 확장

- `approval.json`
  - 사람 검수 결과
- `platform-overrides/*.json`
  - 플랫폼별 금칙어, 길이 제한, CTA 규칙
- `editorial-brief.json`
  - 요약 포인트, 발음 가이드, 숫자 표기 규칙
- SharePoint 업로드 단계
  - `social/inbox`, `social/review`, `social/status`
