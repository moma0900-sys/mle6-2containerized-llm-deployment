# Containerized LLM Deployment

This repository teaches how to package an asynchronous LLM API in Docker and
deploy it to Render with explicit health checks,
resource, scaling, caching, and cost decisions. The API, Dockerfile, and
deployment configuration are supplied. You first run the service locally in
dry-run mode, then deploy the same container as a Free Render web service
without an API key. A short live Groq check is optional.

## Learning Objectives

By the end of this repository, you should be able to:

- Run an LLM API in Docker and explain how its ports, environment variables,
  and health checks form a container contract.
- Deploy a containerized LLM API to Render with explicit resource, health, and
  secret configuration.
- Explain when horizontal scaling and autoscaling help an LLM API, and which
  limits they cannot remove.
- Diagnose cold starts, outages, and provider failures from health checks,
  load-test results, and logs.
- Measure exact-match cache behavior and estimate fixed plus token-based cost.

## Learning Path

| File / Folder | Description |
|---|---|
| [**01 - Container Contract**](01-container-contract.md) | Build the image, run the container, and verify health and readiness from the host. |
| [**02 - Render Deployment**](02-render-deployment.md) | Read the service configuration, deploy the service to a Free Render web service, and measure a cold start. |
| [**03 - Scaling and Failures**](03-scaling-and-failures.md) | Read an autoscaling example, load-test the local container, and diagnose an outage and a failing provider. |
| [**04 - Caching and Cost**](04-caching-and-cost.md) | Inspect a cache hit and connect token usage, instance hours, and cost to what you would measure before scaling. |

### Additional Folders and Files

| File / Folder | Description |
|---|---|
| [**Autoscaling Example**](deployment/) | Optional paid Render autoscaling configuration. |
| [**scripts/load_test.py**](scripts/load_test.py) | Load probe that reports throughput, p95 latency, and error rate. |
| [**Dockerfile**](Dockerfile) | Container image for the API. |
| [**docker-compose.yaml**](docker-compose.yaml) | Local service definition with runtime settings and a health check. |
| [**render.yaml**](render.yaml) | Blueprint reference with Groq as the default; lesson 02 creates the service manually in dry-run mode. |
| [**.env.example**](.env.example) | Provider configuration template and service limits. |
| [**pyproject.toml**](pyproject.toml) | Project configuration and dependencies. |
| [**uv.lock**](uv.lock) | Dependency lock file. |

## Prerequisites

- **Docker Desktop**: required to build the API image and run the container with `docker compose`. Follow the [installation instructions](https://docs.docker.com/get-docker/) if you do not have it yet. Make sure it is **installed and running** before you start lesson 01.

- **Render account**: required to deploy the service in lesson 02. [Sign up](https://dashboard.render.com/register) for free with your GitHub account.

> [!NOTE]
> **Windows Users:** The commands in this walkthrough use bash syntax. Use **Git Bash** (installed with [Git for Windows](https://git-scm.com/downloads/win)) instead of PowerShell to run them.

## Setup

Use [uv](https://docs.astral.sh/uv/getting-started/installation/) 0.13.5 or newer
and Python 3.13.17 or a newer 3.13 patch release, as defined in
[`.python-version`](.python-version).

> [!NOTE]
> Throughout these steps, text in angle brackets like `<repo-name>` is a **placeholder**. Replace it, including the `< >` brackets, with your own value. For example, `cd <repo-name>` becomes `cd mle-containerized-llm-deployment`.

### 1. Create the Repository from the Template

Click **Use this template** on GitHub.

When creating the repository:

- Set yourself as the **Owner**
- Choose a repository name
- Keep the repository **Private**
- Enable **Include all branches** only if the lesson is on a non-default branch
- Click **Create repository**

> [!IMPORTANT]
> If you are working in pairs or groups, only **one person** should complete this step.

---

### 2. Add Collaborators (Pairs/Groups Only)

If working with teammates:

1. Open the repository on GitHub
2. Go to **Settings → Collaborators**
3. Add your teammates as collaborators
4. Share the repository link with your team

Teammates should accept the invitation before continuing.

---

### 3. Clone the Repository

Copy the SSH URL from the **Code** button on GitHub, then run:

```bash
git clone <copied-ssh-url>
```

The copied SSH URL will look like `git@github.com:<your-username>/<repo-name>.git`.
If a lesson branch was shared, clone with
`git clone --branch <lesson-branch> <copied-ssh-url>` and select the same branch
when deploying on Render.

---

### 4. Move into the Project Folder and Install Dependencies

This installs all dependencies and creates a virtual environment in `.venv/`.

```bash
cd <repo-name>
uv sync
```

---

### 5. Set Up Environment Variables

Copy the provider settings and service limits:

```bash
cp .env.example .env
```

The guides explicitly set `MODEL_PROVIDER=dry` for the local walkthrough, so no keys are needed. For live calls, keep `MODEL_PROVIDER=groq`, create a key at [console.groq.com/keys](https://console.groq.com/keys), and set `GROQ_API_KEY`. Alternatively, set `MODEL_PROVIDER` to `mistral`, `openrouter`, `google`, or `openai` and fill in the matching key and model from [`.env.example`](.env.example).

> [!CAUTION]
> Never commit `.env`. It is git-ignored because environment files often hold secrets. Only `.env.example`, with placeholder or default values, belongs in the repository.

---

### 6. Open the Repository in VS Code

> [!NOTE]
> Make sure you open VS Code from the project root so it automatically detects the environment created by `uv sync`.

Launch VS Code in the project root folder:

```bash
code .
```

Select the Python interpreter in `.venv/` created by `uv sync`. Run all commands in the lessons from the repository root.

## References & Further Reading

- [Render Docs](https://render.com/docs)
- [FastAPI Deployment Concepts](https://fastapi.tiangolo.com/deployment/concepts/)
