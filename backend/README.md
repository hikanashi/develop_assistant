# Backend development

The backend is built from the ER model at `design/database/er-design.md` and JSON Schema
designs below `design/database/json/`. Do not edit the generated seed JSON files directly.

## 1. Build and run the environment

### Dev Container (recommended)

1. Install Docker Desktop or another Docker-compatible engine and the VS Code Dev Containers
   extension. Use Docker Compose v2.24 or newer for Compose `include` and optional env files.
2. Open this repository in VS Code and run **Dev Containers: Reopen in Container**.
3. If `.env` does not exist, the Dev Container setup copies `.env.example` to `.env`. Replace
   its template password with a local-only development value; never reuse production credentials.
4. The first container creation installs Python dependencies, generates seed files, applies
   Alembic migrations, and inserts the initial data.
5. Start the API in the Dev Container terminal:

   ```sh
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

The development container uses Python 3.13 or newer and includes `psql`. Its `.git` mount is
read-only; make commits from the host.

### Docker Compose from the repository root

To use PostgreSQL, create `.env` from `.env.example`, replace the template password with a
local-only value, then run:

```sh
docker compose up -d --build --wait
docker compose ps
```

The `db` service runs PostgreSQL 18, `backend-init` applies migrations and loads seeds, and
`backend` serves REST and MCP. The API is available at `http://localhost:8000/`; MCP clients
connect to `http://localhost:8000/mcp/`. Host ports bind only to loopback. Use `DB_PORT` and
`BACKEND_PORT` from `.env` to change the host ports.

Without `.env`, Compose still starts successfully: PostgreSQL idles without opening a database,
and the backend uses the JSON file store at `LOCALDATA_DIR`, which is visible on the host. The
backend container runs with UID/GID 1000 by default so generated files are accessible from the
host. On Linux/WSL, if your account uses different IDs, pass them when starting Compose:

```sh
LOCAL_UID="$(id -u)" LOCAL_GID="$(id -g)" docker compose up -d --build --wait
```

The JSON files are ignored by Git. Set all three `POSTGRES_*` values in `.env` to switch to
PostgreSQL. If any connection setting is present but incomplete, startup reports the missing
environment variable names.

Do not run the root Compose stack and Dev Container at the same time; they share the PostgreSQL
volume and host `LOCALDATA_DIR`. To stop the stack, use `docker compose down`. Do not remove named
volumes unless you intend to delete local development data.

### Adding Compose services or integrating a frontend

The root `compose.yaml` includes service-specific definitions from `compose/`. Add a new service
in its own YAML file and add it to the root `include` list. Bind exposed ports to `127.0.0.1`.
This repository has no frontend, so no frontend source, runtime, or `web.yaml` service is created.
If a frontend is added later, define its service in `compose/web.yaml`, pass
`BACKEND_URL=http://backend:8000`, join the same Compose network, and wait for the backend health
check. A frontend must use the backend API rather than connecting directly to PostgreSQL.

## 2. Connect GitHub Copilot and other MCP clients

With the backend running, VS Code can connect through `.vscode/mcp.json`:

```json
{
  "servers": {
    "develop-assistant": {
      "type": "http",
      "url": "http://localhost:8000/mcp/"
    }
  }
}
```

Start the `develop-assistant` server from VS Code's MCP server controls. Other clients on the
host use the same loopback URL. A client running in the same Compose network should use
`http://backend:8000/mcp/`. MCP tools provide table reads, validated record creation, and JSON
Schema retrieval. For Claude Code, register the host endpoint with
`claude mcp add --transport http develop-assistant http://localhost:8000/mcp/`. A Dify instance
on the same Compose network can use `http://backend:8000/mcp/` in its MCP client configuration.

## 3. Edit and generate initial data

Edit relational schema samples in `backend/seed/00_sample_master.json` only by changing the
generator's sample definitions in `backend/app/seed_builder.py`. JSON Schema rows and artifact
examples are derived from the schema design Markdown, JSON Schema files, and each example's
`valid` array.

After editing schema design files, run from `backend/` on the host or in the Dev Container:

```sh
python -m app.cli build-seed
python -m app.cli build-seed --check
```

The generated files are `seed/00_sample_master.json`, `seed/10_json_schema.json`, and
`seed/20_artifact_examples.json`. Commit these files with their source design changes. The seed
command is safe to repeat: rows with existing primary keys are skipped.

Load the seeds into the selected store with:

```sh
python -m app.cli seed
```

Export the current database/file-store contents as seed-compatible JSON with:

```sh
python -m app.cli export -o /tmp/backend-export.json
```

The seed and export paths are relative to `backend/`, including inside `/app` in the backend
container.

## 4. Inspect database contents

The Dev Container installs the VS Code PostgreSQL extension (`ms-ossdata.vscode-pgsql`). Create
a connection using values from `.env`:

- From inside the Dev Container: host `db`, port `5432`.
- From VS Code running on the host: host `localhost`, port `DB_PORT`.

Use the user, password, and database name from `.env`; do not save those values in workspace
settings or repository files. Alternatively, use `psql` in the Dev Container:

```sh
PGPASSWORD="$POSTGRES_PASSWORD" psql \
  -h db -p 5432 -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

### Post-build verification

```sh
docker compose up -d --build --wait
docker compose ps
docker compose exec backend python -m app.cli seed
docker compose exec backend python -m app.cli export
```

Confirm `db` and `backend` are healthy and `backend-init` exited successfully. In `psql`, compare
the tables and row counts with the seed files. `GET /health` should return `status: ok`, and
`GET /api/CONTENT_RECORD` should contain sample records. The JSON Schemas are available at
`GET /api/schemas`; content revisions are validated against their referenced schema before
insertion. Do not include credentials or the database name in bug reports.

For the no-`.env` file-store path, stop the PostgreSQL stack, remove only `LOCALDATA_DIR` if a clean
initial state is needed, then start Compose without `.env`. Check that JSON arrays are created for
every ER table under `LOCALDATA_DIR` on the host and in the Dev Container. Create a record through
REST/MCP, restart the backend, and verify it remains present. Invalid JSON Schema payloads must
return validation details and must not be persisted.

## 5. REST and MCP API

- `GET /health`: readiness check.
- `GET /api/tables`: table names.
- `GET /api/{TABLE_NAME}`: records from a table.
- `POST /api/{TABLE_NAME}`: insert a record; JSON Schema definitions and content revisions are
  validated before the transaction commits.
- `GET /api/schemas`: registered JSON Schemas and identifiers.
- `/mcp/`: Streamable HTTP MCP endpoint with `list_records`, `create_record`, and
  `get_json_schemas` tools.

The JSON Schema validation error response includes schema identifiers and the JSON Pointer,
constraint, and message for each violation. Fetch the current schema from `/api/schemas` or the
MCP `get_json_schemas` tool before correcting and resubmitting a record.

## 6. Change the relational schema

Update `design/database/er-design.md` first, then modify the SQLModel definitions in
`backend/app/models.py`. Generate and review an Alembic revision from `backend/`:

```sh
alembic revision --autogenerate -m "describe schema change"
alembic upgrade head
```

Do not alter an already-applied migration. Add or update tests and ensure sample rows satisfy the
foreign keys, checks, uniqueness rules, and JSON Schema constraints.

## 7. Edit JSON Schemas

The source of truth is every Markdown file below `design/database/json/`. Edit the schema path
and corresponding examples declared by that design. Keep `$id`, `schema_key`, and
`schema_version` aligned. Registered schema versions are immutable: increment the version for
changes to a published schema. Put positive and negative cases in `valid` and `invalid`
respectively, then run `python3 design/database/json/schemas/validate.py`, the seed builder, and
tests. The builder validates the draft 2020-12
metaschema and every `valid` payload before generating seed rows.

## Tests and lint

From `backend/`:

```sh
pytest
ruff check app tests
```
