# Social Status Contract

publisher는 exporter가 만든 package를 읽고, 자신의 진행 상태를 `social/status/...` 아래에 기록한다. exporter는 이 경로에 쓰지 않는다.

## 목적

- publisher가 어떤 배치를 받았는지 기록
- 기사별 build/publish 진행 상태를 외부에서 추적 가능하게 유지
- 재시도, 중복 방지, 장애 조사 시 기준 로그로 사용

## 경로 규격

```text
social/status/
  youtube_shorts/YYYY/MM/DD/run-000123/
    batch.json
    article-000143.json
    article-000094.json
  instagram/YYYY/MM/DD/run-000123/
    batch.json
    article-000143.json
```

- 플랫폼별 namespace를 분리한다.
- 같은 batch라도 플랫폼마다 독립적으로 상태를 기록한다.
- exporter는 `social/inbox`, `social/notifications`만 쓰고, publisher는 `social/status`만 쓴다.

## batch status

`batch.json`은 publisher가 해당 batch를 어디까지 처리했는지 나타낸다.

예시:

```json
{
  "schema_version": 1,
  "status_kind": "mnl/social-batch-status",
  "platform": "youtube_shorts",
  "relative_dir": "2026/03/14/run-000123",
  "run_id": 123,
  "state": "building",
  "article_count": 2,
  "processed_count": 1,
  "failed_count": 0,
  "detail": "",
  "updated_at": "2026-03-14T01:25:00+00:00"
}
```

## article status

기사별 상태 파일은 실제 처리 단위를 추적한다.

예시:

```json
{
  "schema_version": 1,
  "status_kind": "mnl/social-article-status",
  "platform": "youtube_shorts",
  "relative_dir": "2026/03/14/run-000123",
  "run_id": 123,
  "article_idxno": 143,
  "state": "review_required",
  "package_dir": "article-000143",
  "package_path": "article-000143/package.json",
  "detail": "Preview rendered and queued for editor review.",
  "output_path": "review/article-000143/preview.mp4",
  "review_url": "",
  "updated_at": "2026-03-14T01:26:00+00:00"
}
```

## 상태값

권장 상태값:

- `received`
- `building`
- `built`
- `review_required`
- `approved`
- `publishing`
- `published`
- `blocked`
- `failed`
- `skipped`

종료 상태:

- `published`
- `blocked`
- `failed`
- `skipped`

## 운영 규칙

- publisher는 자기 플랫폼 namespace만 수정한다.
- 상태 파일은 overwrite 방식으로 최신 상태를 유지한다.
- 중복 처리 방지는 publisher가 `relative_dir + article_idxno + platform` 기준으로 한다.
- `failed`와 `blocked`는 `detail`에 이유를 남긴다.
- `review_required`는 사람이 확인해야 하는 상태다.

## 테스트 권장 방식

1. exporter가 만든 `notification.json`을 읽는다.
2. `batch.json`과 각 `package.json`을 연다.
3. publisher는 자신의 `batch.json`과 `article-xxxxxx.json`을 로컬이나 staging SharePoint 경로에 쓴다.
4. 같은 notification을 다시 읽어도 같은 article status를 중복 생성하지 않는지 확인한다.

관련 문서:

- [SOCIAL_EXPORTER.md](/Users/air/codes/mnl-backup/docs/SOCIAL_EXPORTER.md)
