이 프로젝트는 KRAFTON take-home assignment이지만, 결과물은 과제 데모가 아니라 실제 운영 중인 premium AI creator service처럼 보이게 만들고 싶습니다.

프로젝트 설명:
Vertex AI 기반 AI multimodal content-generation platform입니다.
사용자는 텍스트 프롬프트로 이미지를 생성하고(T2I), 텍스트로 영상을 생성하고(T2V), 이미지를 기반으로 영상을 생성하고(I2V), T2I 결과 이미지를 자동으로 I2V 입력으로 연결하는 pipeline을 실행할 수 있어야 합니다.
Prompt Enhance 기능도 있으며, 사용자가 입력한 원본 프롬프트를 Gemini 기반 개선 프롬프트로 바꾸고, 검토/수정한 뒤 generation에 사용할 수 있어야 합니다.

현재 backend 상태:
- T2I/T2V/I2V generation API 구현 완료
- Prompt Enhance backend 구현 완료
- T2I -> I2V Pipeline backend 구현 완료
- Job 상태, asset 저장, history/detail 조회 흐름이 backend에 있음
- 실제 AI 호출은 테스트에서 mock 처리됨
- frontend는 backend API를 연결해 과제 필수 UX를 완성하는 단계

기술스택:
- Frontend: Vite + React + TypeScript
- Styling: Tailwind CSS
- Data fetching: @tanstack/react-query
- Backend: FastAPI + async SQLAlchemy + Postgres
- Local dev/build: docker-compose로 frontend/backend/db 실행 예정

구현해야 하는 frontend 핵심 요소:
1. Generate 화면
   - mode switch: T2I / T2V / I2V / Pipeline
   - model select
   - prompt input
   - aspect ratio, duration 등 mode별 기본 옵션
   - submit 후 job detail 또는 waiting state로 연결

2. Prompt Enhance UX
   - 원본 프롬프트 입력 후 Enhance 실행
   - enhanced prompt 표시
   - 사용자가 enhanced prompt 수정 가능
   - 원본/개선본 차이를 이해하기 쉬운 review UI
   - 최종 선택한 prompt로 generation 실행

3. Waiting UX
   - pending/running/polling/succeeded/failed 상태를 시각적으로 표시
   - 영상 생성은 오래 걸릴 수 있으므로 단순 spinner보다 timeline 또는 progress-like feedback 필요
   - 실패 시 원인 메시지와 재시도/돌아가기 액션 제공

4. Result Display
   - image 결과 preview
   - video 결과 player
   - asset metadata 표시
   - 생성된 image asset을 I2V source로 이어서 사용할 수 있는 액션

5. History / Job Detail
   - 이전 generation jobs 목록
   - mode, state, created time, prompt 일부, result 여부 표시
   - job detail에서 prompt, enhanced prompt, status timeline, asset preview 확인

6. T2I -> I2V Pipeline UI
   - image prompt와 video prompt를 한 화면에서 입력
   - submit 시 parent T2I job과 child I2V job 흐름을 보여줌
   - parent image 생성 완료 후 child video generation이 이어지는 구조를 사용자가 이해할 수 있어야 함

디자인 톤:
- 실제 운영 중인 premium AI creative operations platform처럼 보여야 합니다.
- 첫 화면은 landing/hero page가 아니라 바로 generation workspace여야 합니다.
- Cyberpunk-inspired dark interface를 원합니다.
- 단, 과한 게임 UI나 장식 위주 sci-fi UI는 피해주세요.
- neon cyan / electric blue / magenta accent를 절제해서 사용해주세요.
- “creative control room”, “premium AI studio”, “cinematic but usable” 느낌이면 좋습니다.
- dense but polished dashboard/tool UI를 지향합니다.
- 가독성, 상태 파악, 작업 흐름이 분위기보다 우선입니다.

빌드 안정성 제약:
- Docker/Vite build 안정성을 해치지 않는 방향으로 구현해주세요.
- 가능하면 기존 dependency와 Tailwind CSS만 사용해주세요.
- 새 dependency가 꼭 필요하면 이유를 먼저 설명하고, package.json과 lockfile을 함께 맞춰주세요.
- 외부 CDN 폰트/이미지/스크립트에 의존하지 마세요.
- 큰 binary asset, 영상, 고해상도 이미지 파일을 repo에 추가하지 마세요.
- cyberpunk 분위기는 CSS, layout, color token, subtle glow/shadow, iconography로 표현해주세요.
- Tailwind class는 build에서 누락되지 않도록 정적인 className 위주로 작성해주세요.
- npm build 또는 기존 frontend build 검증이 가능한 구조로 유지해주세요.

피해야 할 것:
- 기능 설명만 많은 marketing page
- 보라색 그라디언트만 가득한 흔한 AI landing page
- 지나치게 장식적인 sci-fi/game UI
- 카드 안에 카드가 계속 중첩되는 구조
- 작은 텍스트와 낮은 대비
- 실제 기능보다 분위기만 강한 디자인
- backend 기능 변경
- credentials/env/service-account 내용 출력 또는 요구
- 실제 Vertex/Veo/Gemini manual QA
- Docker/README 최종화

요청:
현재 frontend 구조를 먼저 확인한 뒤, 위 필수 flow를 만족하는 UI/UX 설계와 구현 계획을 제안해주세요.
가능하면 기존 파일 구조와 컴포넌트를 최대한 활용하고, 너무 큰 작업은 2~4개 구현 Unit으로 나눠주세요.
먼저 UI/UX 계획만 제안하고, 내가 승인하기 전에는 코드 수정하지 마세요.