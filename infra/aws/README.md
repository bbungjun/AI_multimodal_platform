# AWS Terraform 구현 메모

이 디렉터리는 CreativeOps Studio의 AWS 포트폴리오 배포용 Terraform
stack입니다. 2026-06-13 기준 Sydney `ap-southeast-2`에 첫 mock-mode
배포가 완료되어 있습니다.

## 현재 구현 범위

- VPC, public/private subnet, route table
- ALB와 API target group
- ECS Fargate cluster
- API, worker, dispatcher task definition/service
- ECR backend image repository
- RDS PostgreSQL
- ElastiCache Redis
- EFS asset storage
- S3 + CloudFront frontend hosting
- CloudWatch Logs
- Secrets Manager secret metadata

## 왜 기본 desired count가 0인가

첫 `terraform apply` 직후에는 `DATABASE_URL` secret 값이 아직 없습니다.
RDS는 `manage_master_user_password=true`로 비밀번호를 AWS가 생성하므로,
RDS 생성 후 managed secret에서 password를 확인한 다음 `DATABASE_URL`
secret을 별도로 채워야 합니다.

그래서 `api_desired_count`, `worker_desired_count`,
`dispatcher_desired_count` 기본값은 `0`입니다. secret 값을 채운 뒤
`terraform.tfvars`에서 각각 `1`로 올립니다.

## 기본 실행 순서

```powershell
cd infra/aws
terraform init -backend=false
terraform fmt -recursive -check
terraform validate
```

실제 remote state를 쓸 때는 S3 state bucket을 먼저 만든 뒤
`backend.hcl.example`을 복사해서 값을 채우고 실행합니다.

```powershell
Copy-Item backend.hcl.example backend.hcl
terraform init -backend-config=backend.hcl
```

## 배포 후 DATABASE_URL secret 채우기

RDS가 생성된 뒤 다음 정보를 확인합니다.

```powershell
terraform output rds_endpoint
terraform output rds_master_secret_arn
terraform output database_url_secret_arn
```

RDS managed secret에서 password를 꺼내 `DATABASE_URL` 형식으로 만든 뒤
Secrets Manager의 `database_url_secret_arn`에 넣습니다.

그 다음 `terraform.tfvars`에서 desired count를 올립니다.

```hcl
api_desired_count        = 1
worker_desired_count     = 1
dispatcher_desired_count = 1
```

## 주의

- `terraform apply`는 RDS, ElastiCache, EFS, ALB, CloudFront 등 비용이
  발생하는 리소스를 생성합니다.
- 첫 배포는 `ai_provider = "mock"`으로 진행합니다.
- Vertex credential JSON은 Terraform 변수로 넣지 않습니다. Vertex 전환 시
  `gcp_credentials_json_secret_arn`에 값을 넣고, `ai_provider = "vertex"`로
  apply하면 ECS task가 `GOOGLE_APPLICATION_CREDENTIALS_JSON` secret을
  주입받습니다.
- 현재 live endpoint는 `https://d3up7fakknt15b.cloudfront.net`입니다.
- live service를 계속 켜둘 때는 ECS API/worker/dispatcher desired count가
  각각 `1`이므로 비용을 확인하세요. 데모가 필요 없으면 local tfvars로
  desired count를 `0`으로 낮춘 뒤 apply합니다.
