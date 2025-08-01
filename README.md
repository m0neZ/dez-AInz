# desAInz

This repository contains the desAInz project. Use `scripts/setup_codex.sh` to install dependencies and build the documentation in a Codex environment.

```bash
./scripts/setup_codex.sh
```

## Environment requirements

Make sure the following tools are available before setting up the project:

- **Python 3.12**
- **Node.js 20**
- **Docker** and **Docker Compose** supporting schema version 3.8

These versions match the containers used in `docker-compose.prod.yml` and the
development tooling. Newer versions may also work but are not tested.
Using Python 3.12 improves performance thanks to a faster interpreter and more
efficient memory management. CI now verifies compatibility on 3.12.

## Installing dependencies

Install Python and Node requirements before running tests or building the
documentation.

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
npm ci --legacy-peer-deps
```

Using a dedicated virtual environment path outside the repository keeps
dependencies cached between runs:

```bash
python -m venv ~/.cache/desainz_venv
source ~/.cache/desainz_venv/bin/activate
```

Build the HTML documentation locally with:

```bash
make -C docs html
```


## Development helpers

Run the common tasks using the `Makefile`:

```bash
make up           # start services with Docker Compose for development
make prod-up      # start services with the production compose file
make test         # run unit and integration tests
make lint         # run all linters, type checkers and docstring coverage
make docker-build # build local Docker images
make docker-push  # push images to REGISTRY with TAG
make helm-deploy  # deploy charts with Helm
```
### Compose files

`docker-compose.dev.yml` builds images from local sources for development. `docker-compose.prod.yml` uses published images and is meant for production.


## Storage setup

Create the buckets required by the blueprint and apply the lifecycle policy.
The script automatically detects whether the AWS CLI or `mc` is available and
will print a hint if neither is installed:

```bash
scripts/setup_storage.sh desainz-bucket --minio  # omit --minio for AWS S3
```

## Type Checking

Run Flow across the repository with:

```bash
npm run flow
```

## Dashboard Stats

The admin dashboard shows trending keywords and basic A/B test statistics.
These widgets use React Query and lightweight tRPC calls via hooks located in
`frontend/admin-dashboard/src/lib/trpc/`.
The QueryClient defined in `src/lib/trpc.tsx` sets sensible defaults so cached
data remains fresh without excessive requests. The recommended values are:

- **cacheTime**: 60 minutes
- **staleTime**: 10 minutes

## Debugging with VSCode

VSCode launch configurations are provided in `.vscode/launch.json`.
Start the desired configuration from the Run panel to attach the debugger to the FastAPI API or the Next.js admin dashboard.

Run `scripts/register_schemas.py` after the Kafka and schema registry containers
start to register the provided JSON schemas.

Base Kubernetes manifests are available under `infrastructure/k8s`.

PgBouncer connection pooling is available via the `pgbouncer` service in
`docker-compose.dev.yml`. Point `DATABASE_URL` at port `6432` to leverage pooling.
The default SQLAlchemy pool size can be tuned using the `DB_POOL_SIZE`
environment variable. Observe the `db_pool_size` and `db_pool_in_use` metrics in
Prometheus to determine whether the pool is frequently exhausted and adjust the
setting accordingly.
Execute `scripts/analyze_query_plans.py` periodically to inspect query plans and
identify missing indexes.

## Configuration and Secrets
Local development uses dotenv files. For a quick start copy `.env.quickstart.example` to `.env`. This file contains only the variables required for running the stack with default local services. If you need the full configuration copy the root `.env.example` to `.env` and the `.env.example` in **every** `backend` service directory to their respective `.env` files. The services automatically load these variables using Pydantic `BaseSettings`.
For convenience you can run:

```bash
for f in backend/*/.env.quickstart.example; do cp "$f" "$(dirname "$f")/.env"; done
```

In production, secrets are stored in HashiCorp Vault or AWS Secrets Manager and surfaced to the containers via Docker secrets or Kubernetes Secrets. The settings modules read from `/run/secrets` if present. Do not rely on `.env` files in production.

See [docs/security.md](docs/security.md) for the rotation procedure.
See [docs/backup.md](docs/backup.md) for disaster recovery instructions.
Error tracking is provided via Sentry. Populate the `SENTRY_DSN` variable in each service's `.env` file to enable detailed exception reports. See [docs/monitoring.md](docs/monitoring.md) for details.


## Release process

1. Ensure all commits follow the Conventional Commits specification.
2. Run `./scripts/release.sh <registry>` to generate the changelog, tag the release and publish versioned Docker images.

### Production deployment

Start the infrastructure stack in production mode using:

```bash
make prod-up
```

The `docker-compose.prod.yml` file uses prebuilt images and is intended for use on servers.

## UAT Checklist

Use the following checklist to verify a release candidate in the staging environment:

- [ ] Ingestion workflow completes successfully *(blocked by network restrictions on 2025-07-23)*
- [ ] Scoring jobs finish and persist results *(blocked by network restrictions)*
- [ ] Mock-up creation produces downloadable previews *(blocked by network restrictions)*
- [ ] Publishing pipeline uploads items and invalidates caches *(blocked by network restrictions)*
- [ ] Dashboard pages load and manual job triggers work *(blocked by network restrictions)*
- [ ] No errors appear in logs *(unable to verify in staging)*
- [ ] Documentation and tests pass *(lint checks reported issues)*
- [ ] Stakeholders sign off on the release *(pending)*

## Implementation Plan

See [docs/implementation_plan.md](docs/implementation_plan.md) for the milestone roadmap derived from the [Design Idea Engine Complete Blueprint](docs/blueprints/DesignIdeaEngineCompleteBlueprint.md).

## Running on Windows

Most helper scripts in `scripts/` are written for a POSIX shell. Python equivalents
are provided for common tasks so Windows users can run them without WSL:

```bash
python scripts/setup_codex.py           # install dependencies and build docs
python scripts/run_integration_tests.py # run integration tests
python scripts/run_dagster_webserver.py # start the Dagster web UI
python scripts/rotate_logs.py           # archive and prune logs
python scripts/wait_for_services.py     # block until local services respond
                                        # use --max-wait to override timeout
```

Other scripts depend on tools like Docker, kubectl or AWS CLI and therefore
still require a POSIX environment (WSL or Git Bash).
