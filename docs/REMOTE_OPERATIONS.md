# Remote Operations

이 문서는 `mnl-backup`를 로컬이 아니라 원격 SharePoint/OneDrive 중심으로 운영할 때 확인해야 할 항목만 모아둔 간단 운영 가이드다.

## 운영 원칙

- 장기 보관 기준 저장소는 로컬이 아니라 SharePoint/OneDrive다.
- GitHub Actions 런너의 `data/`, `exports/`, `runtime/`은 실행 중 임시 작업 공간이다.
- 매일 이어지는 증분 백업의 핵심은 `state/current.tar.gz`다.

즉 운영에서 꼭 봐야 하는 원격 경로는 세 축이다.

- `Apps/mnl-backup-prod/backups/incremental/`
- `Apps/mnl-backup-prod/backups/full/`
- `Apps/mnl-backup-prod/state/current.tar.gz`

social exporter까지 쓰는 경우는 아래도 함께 본다.

- `Apps/mnl-backup-prod/social/inbox/`
- `Apps/mnl-backup-prod/social/notifications/`
- `Apps/mnl-backup-prod/social/status/`

## 매일 확인할 것

GitHub Actions:

1. `mnl-backup-daily`가 오늘 실행됐는지 확인
2. 결론이 `Success`인지 확인
3. 실행 Summary에서 `Remote Archive Summary`가 보이는지 확인

SharePoint:

1. `Apps/mnl-backup-prod/state/current.tar.gz`의 수정 시각이 오늘로 바뀌었는지 확인
2. `Apps/mnl-backup-prod/backups/incremental/YYYY/MM/DD/` 아래에 오늘자 `tar.gz`가 생겼는지 확인
3. social exporter를 쓰는 경우 `social/inbox/...`와 `social/notifications/...`도 함께 생겼는지 확인

## 매월 확인할 것

1. `mnl-backup-monthly`가 월초에 1회 성공했는지 확인
2. `Apps/mnl-backup-prod/backups/full/YYYY/MM/` 아래에 새 전체 스냅샷이 생겼는지 확인
3. 월간 실행 뒤에도 `state/current.tar.gz`가 갱신됐는지 확인

## 이상 징후

이 셋 중 하나면 점검이 필요하다.

- `state/current.tar.gz`만 갱신되고 `incremental` 파일이 안 늘어남
- `incremental`은 생기는데 `state/current.tar.gz` 날짜가 멈춤
- GitHub Actions는 성공인데 SharePoint에 새 파일이 안 보임

## 빠른 판단 기준

- `incremental`만 늘고 있다: 보존은 되고 있지만 다음 실행의 연속성이 깨질 위험이 있다
- `state`만 갱신된다: 백업 보존본 누적이 안 되고 있을 가능성이 크다
- `full`이 매달 안 생긴다: 장기 복구 기준점이 부족해진다

## 권장 확인 순서

문제가 생겼을 때는 아래 순서가 가장 빠르다.

1. GitHub Actions 실행 결과 확인
2. 실행 Summary의 `Remote Archive Summary` 확인
3. SharePoint에서 해당 원격 경로 실제 존재 여부 확인
4. 실패 시점의 step 로그에서 OneDrive upload/download 단계 확인
