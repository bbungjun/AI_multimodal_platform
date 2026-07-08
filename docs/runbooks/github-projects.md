# GitHub Project Setup

Use this runbook to configure the CreativeOps Studio GitHub Project that receives
issues and pull requests from this repository.

## Required Repository Settings

Create or choose a GitHub Project, then set these repository values:

- Repository variable: `CREATIVEOPS_PROJECT_URL`
  - Example: `https://github.com/users/bbungjun/projects/1`
- Repository secret: `CREATIVEOPS_PROJECT_TOKEN`
  - Use a GitHub token with Project read/write access.
  - Do not commit or paste the token value.

The workflow `.github/workflows/project-automation.yml` skips project sync when
either value is missing.

## Project Fields

Recommended Project name:

```text
CreativeOps Studio
```

Recommended single-select fields:

- `Status`
  - `Backlog`
  - `Ready`
  - `In progress`
  - `In review`
  - `Blocked`
  - `Done`
- `Work type`
  - `Feature`
  - `Bug`
  - `Infra`
  - `Ops / QA`
  - `Docs`
- `Area`
  - `Generate Studio`
  - `Backend API`
  - `Worker / Dispatcher`
  - `Provider Boundary`
  - `Terraform / GKE`
  - `GitHub Automation`
  - `Docs`
- `Provider mode`
  - `mock`
  - `vertex`
  - `both`
  - `not applicable`

Recommended date fields:

- `Target date`
- `Verified at`

## Views

Recommended views:

- `Board`: group by `Status`, sort by updated date.
- `Infra`: filter `Work type:Infra` or label `terraform`.
- `Ops / QA`: filter `Work type:Ops / QA` or labels `ops`, `qa`.
- `PR Review`: filter open pull requests.
- `Done`: filter `Status:Done`, sort by closed date.

## Labels

The repository uses these collaboration labels for issue forms:

- `feature`
- `bug`
- `infra`
- `terraform`
- `ops`
- `qa`
- `documentation`

## Automation Behavior

When the repository variable and secret are configured:

- opened or reopened issues are added to the Project
- opened, reopened, or ready-for-review pull requests are added to the Project
- Project status transitions still happen in the Project UI or built-in Project
  workflows

Keep PR and issue ownership human-visible: every implementation PR should link
an issue with `Closes #N`.
