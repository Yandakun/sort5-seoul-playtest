# SORT 5 Seoul 온라인 v2.2 — GitHub → Vercel 배포 안내

현재 GitHub 저장소: https://github.com/Yandakun/sort5-seoul-playtest

## 변경사항
- 로컬 v2.1의 최신 UI 전체 적용: 서울 5개 미션 선택, 미션 이미지, Team Status의 사용 칩 이력, 추리 기록 기본 잠금, AI 턴 수동 진행, 캐릭터를 통한 카드 전달.
- 기존 Redis 공유 게임방 저장 로직 유지: `KV_REST_API_URL`과 `KV_REST_API_TOKEN` 자동 인식 (또는 `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN`).
- 온라인 공개 테스트에서는 손패 검사(Debug) 기능 기본 비활성화. `SORT5_ALLOW_DEBUG=true`를 명시한 경우에만 서버에서 테스트 검사 기능 허용하므로 공개 사이트에는 설정하지 마세요.
- 브라우저 캐시 버전을 22로 갱신.

## GitHub 업로드
1. ZIP을 풀고 **폴더 내부 파일과 폴더 전체**를 기존 저장소 루트에 업로드합니다. ZIP 파일 자체를 업로드하지 마세요.
2. `server.py`, `requirements.txt`, `static/index.html`, `static/app.js`, `static/style.css`, `static/layout-v20.css`, `static/layout-v21.css`, `static/assets/*`의 구조를 그대로 유지하세요.
3. GitHub 웹에서 하위 폴더를 통째로 교체하기 어렵다면 GitHub Desktop으로 기존 저장소를 Clone한 뒤 이 파일들을 복사해 Commit/Push 하는 방법이 간단합니다.
4. main 브랜치에 반영하면 연동된 Vercel 프로젝트에서 새 배포가 시작됩니다.

## Vercel 설정
- 기존 `sort5-seoul-playtest` 프로젝트/도메인 그대로 사용.
- Upstash Redis 환경변수는 **이전 프로젝트에 이미 연결된 값을 재사용**합니다. 값을 GitHub에 업로드하지 마세요.
- 배포 후 `https://sort5-seoul-playtest.vercel.app/health`에서 `storage: "upstash"`인지 확인하세요.
- `storage: "unconfigured"`라면 Redis 연결 여부 및 환경변수 적용 후 Redeploy 필요.

## 2인 멀티플레이 점검
1. 브라우저 A에서 `2 humans + 2 AI`로 새 방을 만들고, 우측 상단의 `ROOM XXXXXX`를 클릭해 초대 링크를 복사.
2. 브라우저 B(다른 컴퓨터 또는 시크릿 창)에서 링크 접속 후 이름을 입력하고 Join Room.
3. 호스트가 Deal Cards & Start → 각 플레이어가 서로 다른 캐릭터 선택.
4. 시작카드는 ▲에게 지급되며 해당 플레이어가 첫 턴.
5. 다른 사람에게 카드를 주면 수신자 화면에서 수신 카드와 피드백 조작이 보이는지 확인. 양쪽 Team Status의 사용 칩과 Live Turn이 일치해야 합니다.
6. 3~4인도 같은 방법으로 테스트.

## 제한사항
- 게임방은 마지막 저장부터 24시간 후 Redis에서 만료될 수 있습니다.
- 1.5초 간격 폴링을 사용하므로 실시간 WebSocket 수준의 즉시 반영은 아닙니다.
- Redis 연결/네트워크 장애와 동시 접속량에 따라 오류가 발생할 수 있습니다.
- '시작 카드 수신 시 빨강 칩 1개 소모'는 기존 프로토타입의 임시 룰 해석을 그대로 유지합니다.
- 로컬 자동 테스트는 실제 Vercel 운영 환경의 안정성을 보장하지 않습니다.
