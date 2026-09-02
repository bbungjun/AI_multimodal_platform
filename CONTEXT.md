# CreativeOps Studio

CreativeOps Studio는 사용자가 AI로 프롬프트를 개선하고 이미지와 영상을 생성한 뒤
결과를 관리하는 멀티모달 콘텐츠 작업 공간이다.

## Language

**User**:
Google OAuth로 식별되며 CreativeOps Studio에서 콘텐츠를 생성하는 사람.
_Avoid_: Account, member, customer

**Master**:
모든 사용자의 운영 상태를 조회하고 플랜, 보너스 크레딧, 계정 상태를 관리할 수 있는
승격된 User. 별도의 관리자 유형이나 로그인 방식이 아니다.
_Avoid_: Admin, administrator, superuser

**Plan**:
30일 동안 사용할 수 있는 기본 크레딧과 모델 접근권, 요청 한도를 묶은 상품 등급.
_Avoid_: Role, permission

**Credit**:
서로 다른 AI 모델의 사용량을 하나의 잔액으로 제한하기 위한 내부 소비 단위. 실제
통화나 provider 청구 금액을 뜻하지 않는다.
_Avoid_: Token, money, provider cost

**Usage**:
Gemini token, Imagen image, Veo video second처럼 provider 또는 플랫폼이 측정한 원본
소비량.
_Avoid_: Credit, charge

**Reservation**:
AI 요청을 시작하기 전에 예상 최대 Credit을 사용할 수 없도록 확보한 상태.
_Avoid_: Charge, payment

**Settlement**:
요청 결과의 실제 Usage에 따라 Reservation을 소비하거나 반환하는 최종 처리.
_Avoid_: Billing, payment

**Billing Cycle**:
User의 가입 시각부터 연속되는 고정 30일 Credit 사용 기간.
_Avoid_: Calendar month, monthly billing

**Synthetic User**:
운영 대시보드와 테스트를 위해 생성되며 Google OAuth로 로그인할 수 없는 가상 User.
_Avoid_: Mock login user, test account
