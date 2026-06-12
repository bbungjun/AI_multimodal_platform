# AWS Terraform 배포 계획

> 상태: 2026-06-13 기준 첫 mock-mode AWS 배포를 완료했습니다.
> 활성 리전은 Sydney `ap-southeast-2`이고, CloudFront 배포 주소는
> `https://d3up7fakknt15b.cloudfront.net`입니다.

> 구현 상태: `infra/aws/` Terraform skeleton이 추가되었고
> `terraform init -backend=false`, `terraform fmt -recursive`,
> `terraform validate`, no-apply `terraform plan -refresh=false`까지
> 통과했습니다. 이후 S3 remote backend로 전환했고, RDS/ElastiCache/EFS,
> ALB, ECS API/worker/dispatcher, S3/CloudFront frontend, ECR, CloudWatch
> Logs, Secrets Manager 기반 배포를 실제 생성했습니다.

## 목표

CreativeOps Studio를 AWS에 포트폴리오용으로 배포합니다. 목표는 실제
상용 서비스 운영이 아니라, 배포 가능한 구조와 운영 흐름을 보여주는
안정적인 데모 환경입니다.

이 프로젝트는 단순 웹앱이 아니라 다음 프로세스가 함께 움직입니다.

```text
프론트엔드
  -> 백엔드 API
    -> PostgreSQL에 job, asset metadata, outbox 저장
    -> /files 경로로 생성 파일 제공
outbox dispatcher
  -> PostgreSQL outbox 이벤트를 Redis/Celery 큐로 전달
Celery worker
  -> Redis 큐에서 job id를 받아 PostgreSQL job을 처리
  -> 생성 결과를 DATA_DIR에 저장
```

따라서 AWS에서도 API, worker, dispatcher, DB, Redis, asset storage를
역할별로 분리해서 배포해야 합니다.

## 권장 AWS 구조

```text
CloudFront
  -> S3 frontend origin: React/Vite 정적 파일 제공
  -> ALB origin: /api/*, /files/* 요청 전달

ALB
  -> ECS Fargate api service, port 8000

ECS Fargate worker service
  -> Celery worker 실행, 외부 inbound 없음

ECS Fargate dispatcher service
  -> outbox dispatcher 실행, 외부 inbound 없음

RDS PostgreSQL
  -> job 상태, asset metadata, prompt, pipeline, outbox 저장

ElastiCache Redis OSS 또는 Valkey
  -> Celery broker

EFS
  -> /data/assets에 마운트해서 API와 worker가 같은 생성 파일 저장소 사용

Secrets Manager
  -> DB 비밀번호, 추후 Vertex credential 보관

CloudWatch Logs
  -> api, worker, dispatcher 로그 확인

ECR
  -> backend Docker image 저장소
```

## 왜 이 구조를 쓰는가

### CloudFront + S3

프론트엔드는 Vite로 빌드하면 정적 파일입니다. 서버를 계속 켜둘 필요가
없기 때문에 S3에 `dist` 파일을 올리고 CloudFront로 배포하는 방식이
저렴하고 단순합니다.

또 CloudFront가 `/api/*`, `/files/*` 요청만 ALB로 보내게 만들면
프론트와 API를 같은 도메인 아래에서 사용할 수 있습니다. 이렇게 하면
CORS 문제가 줄어듭니다.

### ALB

ALB는 백엔드 API로 들어가는 공개 입구입니다. CloudFront가 받은
`/api/*`, `/files/*` 요청을 ECS API task로 전달합니다.

ALB target group의 health check는 `/api/health`를 사용합니다. 이 경로로
API가 정상적으로 뜨고 DB 연결이 가능한지 확인할 수 있습니다.

### ECS Fargate API

FastAPI backend를 컨테이너로 실행합니다. EC2 서버를 직접 관리하지 않고
컨테이너 단위로 배포할 수 있어서 포트폴리오 배포에 적합합니다.

API는 사용자 요청을 받고 job을 PostgreSQL에 저장합니다. 실제 이미지/영상
생성 작업은 worker가 처리하므로 API와 worker를 분리해야 합니다.

### ECS Fargate worker

Celery worker는 생성 job을 실제로 처리합니다. Imagen/Veo 작업은 오래
걸릴 수 있으므로 API 서버와 같은 프로세스에서 처리하면 API 응답성이
떨어집니다.

worker를 별도 ECS service로 두면 API는 가볍게 유지하고, 생성 작업은
worker에서 안정적으로 처리할 수 있습니다.

### ECS Fargate dispatcher

현재 코드 구조는 API가 job과 outbox event를 PostgreSQL에 저장하고,
dispatcher가 outbox event를 Redis/Celery 큐로 넘기는 방식입니다.

dispatcher를 별도 프로세스로 두면 API transaction과 queue publish를
분리할 수 있어 job 유실 가능성을 줄일 수 있습니다.

### RDS PostgreSQL

PostgreSQL은 이 시스템의 source of truth입니다.

다음 데이터는 Redis가 아니라 PostgreSQL에 남습니다.

- job 상태
- asset metadata
- prompt enhancement 기록
- pipeline parent/child 관계
- retry/dead-letter 정보
- outbox event 상태

그래서 AWS에서는 컨테이너 내부 DB가 아니라 RDS를 사용해야 합니다.

### ElastiCache Redis

Redis는 Celery broker입니다. dispatcher가 Redis에 `job_id`를 넣고,
worker가 Redis에서 해당 job을 가져갑니다.

Redis는 job의 최종 상태 저장소가 아닙니다. 최종 상태는 PostgreSQL에
남습니다.

### EFS

현재 코드는 생성 결과를 `DATA_DIR=/data/assets` 아래 로컬 파일로
저장합니다. API는 `/files/...` 경로로 이 파일을 스트리밍합니다.

ECS에서 API task와 worker task는 서로 다른 컨테이너로 실행되므로, 둘이
같은 파일을 보려면 공유 파일 시스템이 필요합니다. 첫 AWS 배포에서는
EFS를 `/data/assets`에 마운트하는 방식이 가장 코드 변경이 적습니다.

장기적으로는 S3 asset storage adapter를 만드는 것이 더 좋지만, 그것은
별도 코드 변경이 필요합니다.

### Secrets Manager

DB 비밀번호나 Vertex service-account JSON 같은 민감정보를 Terraform
변수로 넣으면 Terraform state에 남을 수 있습니다. 그래서 secret value는
Terraform으로 직접 관리하지 않고, Secrets Manager에 따로 넣습니다.

Terraform은 secret의 이름과 ARN만 다루고, 실제 값은 AWS CLI나 콘솔로
주입합니다.

### CloudWatch Logs

AWS 배포 후에는 로컬 터미널처럼 컨테이너 로그를 바로 볼 수 없습니다.
API, worker, dispatcher 로그를 CloudWatch Logs로 보내야 실패 원인을
확인할 수 있습니다.

### ECR

ECS가 backend 컨테이너 이미지를 pull하려면 AWS 안에 이미지 저장소가
필요합니다. 이 역할을 ECR이 합니다.

## 첫 배포 기준

포트폴리오용 첫 배포는 다음 기준으로 갑니다.

- Region: `ap-southeast-2` 시드니
- Provider mode: `AI_PROVIDER=mock`
- ECS API desired count: `1`
- ECS worker desired count: `1`
- ECS dispatcher desired count: `1`
- Worker concurrency: `2`
- Veo rate limit: 분당 `1`
- Imagen rate limit: 분당 `5`
- Gemini rate limit: 분당 `10`
- DB: RDS PostgreSQL 16 단일 인스턴스
- Redis: ElastiCache 단일 노드 또는 단일 replication group
- Asset storage: EFS
- Frontend: S3 + CloudFront

첫 배포는 비용과 리스크를 줄이기 위해 mock mode로 검증합니다. Vertex
실사용은 credential 전략을 안전하게 만든 뒤 켭니다.

## 중요한 환경변수와 이유

### `AI_PROVIDER=mock`

첫 AWS 배포에서는 실제 Vertex 비용이 발생하지 않아야 합니다. mock mode로
API, DB, Redis, worker, dispatcher, frontend routing이 정상인지 먼저
검증합니다.

### `DATABASE_URL`

API, worker, dispatcher가 모두 같은 RDS PostgreSQL을 바라봐야 합니다.
그래야 job 상태와 outbox 상태가 일관됩니다.

예시:

```text
postgresql+asyncpg://app:${DB_PASSWORD}@${RDS_ENDPOINT}:5432/multimodal
```

### `CELERY_BROKER_URL`

Celery가 사용할 Redis 주소입니다. dispatcher는 여기에 job id를 넣고,
worker는 여기서 job id를 가져갑니다.

예시:

```text
redis://${REDIS_ENDPOINT}:6379/0
```

### `DATA_DIR=/data/assets`

생성 파일 저장 위치입니다. ECS에서는 이 경로에 EFS를 마운트합니다.
API와 worker가 같은 파일 시스템을 봐야 `/files/...` 응답이 정상적으로
동작합니다.

### `JOB_DISPATCH_MODE=celery`

현재 안정화한 구조가 outbox + Redis/Celery 기반이므로 AWS에서도 같은
dispatch 방식을 사용합니다.

### `CELERY_WORKER_CONCURRENCY=2`

포트폴리오용 배포에서는 동시에 너무 많은 생성 작업을 처리할 필요가
없습니다. 특히 Veo는 오래 걸리고 비용이 발생할 수 있으므로 worker
동시성을 낮게 유지합니다.

### `CELERY_TASK_ACKS_LATE=true`

worker가 job 처리를 끝낸 뒤에 Celery ack를 보냅니다. worker가 중간에
죽으면 job이 완료 처리되지 않아 재처리 가능성이 남습니다.

### `CELERY_TASK_REJECT_ON_WORKER_LOST=true`

worker 프로세스가 죽었을 때 작업을 유실하지 않고 다시 큐로 돌릴 수 있게
합니다. 긴 영상 생성 작업에서 중요합니다.

### `CELERY_WORKER_PREFETCH_MULTIPLIER=1`

worker가 미리 너무 많은 job을 가져가지 않게 합니다. 오래 걸리는 Veo
작업이 있을 때 특정 worker가 job을 쥐고만 있는 상황을 줄입니다.

### Rate limit 설정

```text
RATE_LIMIT_GEMINI_PER_MIN=10
RATE_LIMIT_IMAGEN_PER_MIN=5
RATE_LIMIT_VEO_PER_MIN=1
```

배포는 하지만 실제 서비스 운영 목적은 아니므로 보수적으로 제한합니다.
이 값은 비용 폭주와 provider quota 문제를 줄이기 위한 포트폴리오용
가드레일입니다.

### `CORS_ORIGINS`

CloudFront 도메인에서 오는 브라우저 요청만 허용하기 위해 설정합니다.

예시:

```text
CORS_ORIGINS=["https://CLOUDFRONT_DOMAIN"]
```

### `VITE_API_BASE=""`

프론트가 API를 별도 도메인으로 직접 호출하지 않고, 같은 CloudFront
도메인의 `/api`로 요청하게 합니다. 이렇게 하면 CloudFront가 `/api/*`를
ALB로 라우팅할 수 있고, CORS 설정도 단순해집니다.

## 사전 작업

### 1. 프론트엔드 운영 배포 방식 정리

현재 `frontend/Dockerfile`은 Vite dev server를 실행합니다. AWS 운영
배포에서는 이 방식을 쓰지 않습니다.

AWS에서는 다음 방식으로 갑니다.

```powershell
cd frontend
$env:VITE_API_BASE = ""
npm ci
npm run build
aws s3 sync dist s3://FRONTEND_BUCKET --delete
```

### 2. Vertex credential 전략

첫 배포는 `AI_PROVIDER=mock`으로 합니다.

Vertex 실사용을 켜려면 service-account JSON을 안전하게 다루는 전략이
필요합니다. Terraform variable에 JSON을 넣으면 state에 남을 수 있으므로
금지합니다.

권장 다음 작업:

- `GOOGLE_APPLICATION_CREDENTIALS_JSON`을 Secrets Manager에서 주입
- 컨테이너 entrypoint가 런타임에 임시 파일로 기록
- `GOOGLE_APPLICATION_CREDENTIALS`를 그 파일 경로로 설정

더 좋은 장기 방향은 AWS와 GCP 간 Workload Identity Federation입니다.

### 3. DB migration 전략

현재 backend는 startup 시점에 schema init을 수행합니다. 첫 배포에서는
API task를 1개만 두면 큰 문제는 없습니다.

하지만 API task를 여러 개로 늘리기 전에는 Alembic 또는 one-shot ECS
migration task를 추가해야 합니다.

### 4. Redis TLS

ElastiCache in-transit encryption을 켜려면 Celery가 `rediss://...`로
정상 연결되는지 검증해야 합니다.

첫 배포에서는 Redis를 private subnet과 security group으로 보호하고,
TLS는 별도 검증 후 켭니다.

## Terraform 디렉터리 구조

Terraform은 `infra/aws/` 아래에 둡니다.

```text
infra/aws/
  README.md
  versions.tf
  variables.tf
  outputs.tf
  locals.tf
  networking.tf
  security-groups.tf
  ecr.tf
  logs.tf
  secrets.tf
  rds.tf
  redis.tf
  efs.tf
  alb.tf
  cloudfront.tf
  frontend-s3.tf
  ecs-cluster.tf
  ecs-iam.tf
  ecs-task-api.tf
  ecs-task-worker.tf
  ecs-task-dispatcher.tf
```

## Terraform 핵심 설정

### `versions.tf`

Terraform state는 S3 backend에 저장하고, S3 native lock을 사용합니다.
2026-06-13 기준 AWS provider 최신 버전은 `6.50.0`입니다. 첫 적용 전에는
provider 버전을 고정하고, 이후 업그레이드는 의도적으로 진행합니다.

```hcl
terraform {
  required_version = ">= 1.10.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.50"
    }
  }

  backend "s3" {
    bucket       = "creativeops-terraform-state-ACCOUNT_ID"
    key          = "creativeops/portfolio/terraform.tfstate"
    region       = "ap-southeast-2"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.tags
  }
}
```

state bucket은 이 Terraform stack 안에서 만들지 않습니다. state를 저장할
bucket을 같은 state로 관리하면 처음 생성 순서가 꼬이기 때문입니다.

### `variables.tf`

```hcl
variable "project_name" {
  type    = string
  default = "creativeops"
}

variable "environment" {
  type    = string
  default = "portfolio"
}

variable "aws_region" {
  type    = string
  default = "ap-southeast-2"
}

variable "container_image" {
  type        = string
  description = "ECR image URI including tag."
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "dispatcher_desired_count" {
  type    = number
  default = 1
}

variable "ai_provider" {
  type    = string
  default = "mock"
}

variable "gcp_project_id" {
  type    = string
  default = ""
}

variable "gcp_location" {
  type    = string
  default = "us-central1"
}
```

## Terraform 리소스별 역할

### `networking.tf`

- VPC
- public subnet 2개
- private subnet 2개
- internet gateway
- 선택 사항: NAT gateway

포트폴리오 첫 배포에서는 비용을 줄이기 위해 ECS task를 public subnet에
두고 `assign_public_ip=true`로 시작할 수 있습니다. 단, security group은
ALB에서 API port로만 접근 가능하게 제한합니다.

나중에 실제 서비스화할 때 private subnet + NAT gateway 또는 VPC endpoint
구조로 올립니다.

### `security-groups.tf`

- ALB SG: 인터넷에서 `80`, 추후 `443` 허용
- API task SG: ALB SG에서 오는 `8000`만 허용
- worker/dispatcher SG: inbound 없음
- RDS SG: ECS task SG에서 오는 `5432`만 허용
- Redis SG: ECS task SG에서 오는 `6379`만 허용
- EFS SG: ECS task SG에서 오는 `2049`만 허용

각 리소스가 필요한 대상하고만 통신하게 하려는 설정입니다.

### `ecr.tf`

- backend Docker image 저장소
- push 시 image scan
- 최신 이미지 10개만 유지하는 lifecycle policy

API, worker, dispatcher는 같은 backend image를 사용하고 command만 다르게
실행합니다.

### `logs.tf`

CloudWatch log group:

- `/creativeops/portfolio/api`
- `/creativeops/portfolio/worker`
- `/creativeops/portfolio/dispatcher`

포트폴리오 환경에서는 로그 보관 기간을 14일 정도로 둡니다.

### `secrets.tf`

Secrets Manager secret metadata만 Terraform으로 만듭니다.

실제 secret value는 Terraform에 넣지 않습니다.

대상:

- DB password
- 추후 GCP credential JSON

### `rds.tf`

- PostgreSQL 16
- private subnet 배치
- public access 비활성화
- 첫 배포에서는 작은 instance class 사용
- 실제 데이터가 생기면 deletion protection 활성화

### `redis.tf`

- ElastiCache Redis OSS 또는 Valkey
- private subnet 배치
- ECS task security group에서만 접근

### `efs.tf`

- EFS file system
- private subnet별 mount target
- access point root: `/assets`
- ECS task mount path: `/data/assets`

현재 코드의 local storage 방식을 유지하기 위한 리소스입니다.

### `alb.tf`

- public ALB
- API target group port `8000`
- health check path `/api/health`
- 첫 배포는 HTTP 가능
- 도메인 연결 후 ACM 인증서로 HTTPS 추가

### `frontend-s3.tf`, `cloudfront.tf`

- private S3 bucket
- CloudFront Origin Access Control
- S3 origin: 프론트 정적 파일
- ALB origin: `/api/*`, `/files/*`
- SPA fallback: `/index.html`

### `ecs-*.tf`

- ECS cluster
- task execution role
- task role
- API task definition
- worker task definition
- dispatcher task definition
- ECS service 3개

실행 command:

```text
API:
uvicorn app.main:app --host 0.0.0.0 --port 8000

worker:
celery -A app.celery_app worker --loglevel=info --queues=generation --concurrency=2

dispatcher:
python -m app.services.jobs.outbox_dispatcher
```

## 배포 순서

### 1. Terraform state bucket 생성

```powershell
aws s3 mb s3://creativeops-terraform-state-ACCOUNT_ID --region ap-southeast-2
aws s3api put-bucket-versioning --bucket creativeops-terraform-state-ACCOUNT_ID --versioning-configuration Status=Enabled
```

### 2. Terraform 파일 생성

`infra/aws/` 아래에 위 구조대로 Terraform 파일을 만듭니다.

### 3. backend image build/push

```powershell
aws ecr get-login-password --region ap-southeast-2 | docker login --username AWS --password-stdin ACCOUNT_ID.dkr.ecr.ap-southeast-2.amazonaws.com
docker build -t creativeops-backend:portfolio ./backend
docker tag creativeops-backend:portfolio ACCOUNT_ID.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-backend:portfolio
docker push ACCOUNT_ID.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-backend:portfolio
```

### 4. Terraform plan/apply

```powershell
cd infra/aws
terraform init
terraform fmt -check
terraform validate
terraform plan -var "container_image=ACCOUNT_ID.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-backend:portfolio"
terraform apply -var "container_image=ACCOUNT_ID.dkr.ecr.ap-southeast-2.amazonaws.com/creativeops-backend:portfolio"
```

### 5. frontend build/upload

```powershell
cd ../../frontend
$env:VITE_API_BASE = ""
npm ci
npm run build
aws s3 sync dist s3://FRONTEND_BUCKET --delete
aws cloudfront create-invalidation --distribution-id DISTRIBUTION_ID --paths "/*"
```

### 6. smoke test

```powershell
Invoke-RestMethod -Uri "https://CLOUDFRONT_DOMAIN/api/health"
Invoke-RestMethod -Uri "https://CLOUDFRONT_DOMAIN/api/ops/health"
```

확인할 것:

- `/api/health`가 `ok: true`
- `/api/ops/health`가 DB up, dispatch mode, job/outbox count 반환
- 브라우저에서 `/ops` 화면 렌더링
- CloudWatch Logs에서 API/worker/dispatcher 에러 없음

## 커밋 전 검증

Terraform 파일을 실제로 추가한 뒤에는 다음을 실행합니다.

```powershell
terraform fmt -recursive -check infra/aws
terraform validate
git diff --check
python scripts/verify_local.py
```

## 다음 작업

1. AWS 비용을 모니터링합니다. 데모가 필요 없을 때는 ECS desired count를
   `0`으로 내리거나 Terraform으로 stack을 의도적으로 제거합니다.
2. Vertex credential 전략을 구현합니다. 서비스 계정 JSON을 Terraform
   state에 넣지 않는 방식이 필요합니다.
3. quota/cost control을 확인한 뒤 `AI_PROVIDER=vertex` 전환을 별도 단계로
   진행합니다.
4. 포트폴리오 공개 전에 custom domain, ACM certificate, CloudFront alias를
   추가할지 결정합니다.
5. 반복 배포용 스크립트로 backend build/ECR push, frontend S3 sync,
   CloudFront invalidation, ECS service update를 자동화합니다.

## 참고 문서

- Terraform S3 backend:
  <https://developer.hashicorp.com/terraform/language/backend/s3>
- Terraform AWS provider:
  <https://registry.terraform.io/providers/hashicorp/aws/latest>
- ECS Fargate task definition:
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_definition_parameters.html>
- ECS Secrets Manager injection:
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/secrets-envvar-secrets-manager.html>
- ECS EFS volume:
  <https://docs.aws.amazon.com/AmazonECS/latest/developerguide/efs-volumes.html>
- ALB target group health check:
  <https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-target-groups.html>
- ElastiCache in-transit encryption:
  <https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/in-transit-encryption.html>
