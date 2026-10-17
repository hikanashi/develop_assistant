# backend

FastAPI (REST) と FastMCP (MCP) を1つのプロセスで提供するバックエンドです。DBは PostgreSQL 18 を使います。

要件: [design/requiments/enviroment.md](../design/requiments/enviroment.md)

| 項目 | 内容 |
|---|---|
| REST API | `http://localhost:8000/` (Swagger UI: `/docs`、ヘルスチェック: `/health`) |
| MCP | `http://localhost:8000/mcp/` (Streamable HTTP。末尾の `/` が必要) |
| DB | PostgreSQL 18 (`db:5432`。ユーザー・パスワード・DB名は [.env](#環境変数-env) で設定) |
| DB確認GUI | Adminer (`http://localhost:8080`) |

## 1. 環境構築手順

### 前提

- VS Code と Dev Containers 拡張機能、GitHub Copilot
- Docker (WSL2 上の Docker Engine / Docker Desktop / Rancher Desktop / macOS の Docker Desktop など)。WSL のセットアップは [setup/initial_wsl.bat](../setup/initial_wsl.bat) を参照

### 手順

1. リポジトリをクローンして VS Code で開く (WSL の場合は WSL 側のファイルシステム上に置く)。
2. 認証情報の設定ファイルを作成する ([環境変数 (.env)](#環境変数-env))。

   ```bash
   cp .env.example .env     # 必要なら .env のパスワードを編集する
   ```

   Dev Container では、`.env` がなければ `.env.example` から自動で作成される。
3. コマンドパレットから **Dev Containers: Reopen in Container** を実行する。
4. 初回はイメージのビルドと、`.devcontainer/post-create.sh` による次の処理が自動で行われる。
   - `~/.bashrc` への psql 用接続情報の設定 (`.env` の値から。値はファイルに書き込まない)
   - `pip install -e "backend[dev]"` (依存パッケージのインストール)
   - `alembic upgrade head` (マイグレーション適用)
   - `python -m app.cli seed` (`backend/seed/*.json` の投入)
   - `npm install` (`web/` の依存パッケージ。Next.js は [web/README.md](../web/README.md) 参照)
5. コンテナ内のターミナルで起動する。

   ```bash
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0
   ```

6. `http://localhost:8000/health` が `{"status":"ok"}` を返せば完了。

### 環境変数 (.env)

DB の認証情報は、リポジトリ直下の `.env` に分離しています。

| ファイル | 内容 | Git |
|---|---|---|
| `.env.example` | 雛形。ユーザー名とDB名と、仮のパスワード (`change_me`) | コミットする |
| `.env` | 実際の値。`.env.example` をコピーして作成する | **コミットしない** (`.gitignore` 済み) |

| 変数 | 用途 |
|---|---|
| `POSTGRES_USER` | DB のユーザー名 |
| `POSTGRES_PASSWORD` | DB のパスワード |
| `POSTGRES_DB` | DB 名 (大文字小文字を区別する) |

- `db`、`backend-init`、`backend`、Dev Container の `app` が、compose の `env_file` で `.env` を読み込む。認証情報と DB 名は `.env` のみで管理し、compose ファイル・ソースコード・README には値を書かない。
- バックエンドは [app/config.py](app/config.py) で、これらの変数から接続URLを組み立てる (パスワードに記号が含まれても使える)。接続先ホストは `POSTGRES_HOST` (compose 内では `db`。未設定なら `localhost`)、ポートは `POSTGRES_PORT` (未設定なら `5432`)。`DATABASE_URL` を設定すると、それを優先する。
- **`POSTGRES_*` は DB ボリュームの作成時にだけ反映される。** 変更した場合は `docker compose down -v` でボリュームを削除して作り直す (データも消える)。
- `.env` がない状態で `docker compose` を実行すると `env file .../.env not found` で失敗する。`.env.example` をコピーする。
- ポート番号 (`DB_PORT`、`BACKEND_PORT`、`WEB_PORT`、`ADMINER_PORT`) は認証情報ではないため、必要なときに `.env` へ追記するか、コマンドラインで指定する。
- ローカル専用の値であり、本番 (Amazon RDS) の認証情報は使用しない。

### コンテナの構成

| サービス | 内容 |
|---|---|
| `app` | 開発コンテナ (Dev Container のみ)。Python 3.13 (`/opt/venv`)、Node.js 22、psql |
| `db` | PostgreSQL 18。データは named volume `pgdata` に保存される |
| `adminer` | DB確認用GUI |

設定は [.devcontainer/](../.devcontainer) にあります。`db` と `adminer` の定義はルートの compose と共通で、[compose/](../compose) を読み込んでいます。ポート 3000 / 8000 / 5432 / 8080 は VS Code が自動でフォワードします。

`app` コンテナはホストから隔離されています (全capability剥奪、sudoなし、`.git` は読み取り専用)。`git commit` / `git push` はホスト側で実行してください。

### Dev Container を使わずに全サービスを起動する

リポジトリのルートで `docker compose up` を実行すると、DB・バックエンド・フロントエンド・DB確認GUIがすべて起動し、初期データも投入されます。VS Code 以外から動作を確認したい場合や、Dify など他のサービスと組み合わせて使う場合に利用します。**事前に `cp .env.example .env` で `.env` を作成してください** ([環境変数 (.env)](#環境変数-env))。

```bash
docker compose up -d --build   # 起動 (-d でバックグラウンド。省略するとログを表示)
docker compose ps -a           # 状態確認
docker compose logs -f backend # ログ確認 (サービス名: db / backend-init / backend / web / adminer)
docker compose down            # 停止 (DBのデータは残る)
docker compose down -v         # 停止してDBのデータも削除
```

起動順序は `db` → `backend-init` (マイグレーション適用と `backend/seed/*.json` の投入。完了すると終了する) → `backend` → `web` です。`backend` と `web` はソースをマウントしており、編集するとホットリロードされます。

| サービス | URL (ホスト側) | 定義 |
|---|---|---|
| web (Next.js) | `http://localhost:3000` | [compose/web.yaml](../compose/web.yaml) |
| backend (REST / MCP) | `http://localhost:8000` (MCP: `/mcp/`) | [compose/backend.yaml](../compose/backend.yaml) |
| db (PostgreSQL 18) | `localhost:5432` | [compose/db.yaml](../compose/db.yaml) |
| adminer | `http://localhost:8080` | [compose/tools.yaml](../compose/tools.yaml) |

- ポートは `127.0.0.1` のみに公開される。変更する場合は環境変数 `WEB_PORT` / `BACKEND_PORT` / `DB_PORT` / `ADMINER_PORT` を指定する (例: `DB_PORT=15432 docker compose up -d`)。
- 初期データを変更したら、`docker compose run --rm backend-init` で再投入する (既存行は更新されない。[2. 初期投入データの編集手順](#2-初期投入データの編集手順))。
- スキーマ変更のコマンドは `docker compose exec backend alembic ...` のように実行する。
- Dev Container と同時に起動しない (同じプロジェクト・同じDBを共有するため、どちらか一方を使う)。

### compose ファイルを追加する (Dify など)

ルートの [compose.yaml](../compose.yaml) は、`compose/` 配下の種類別ファイルを `include` で読み込むだけの構成です。

1. `compose/dify.yaml` のように、サービスを定義したファイルを作成する。
   - ファイル内の相対パスは、そのファイルのあるディレクトリが基準になる。
   - 同じプロジェクトのネットワークに参加するため、他のサービスは `db`、`backend` などのサービス名で参照できる。
   - ポートの公開は `127.0.0.1:${XXX_PORT:-既定値}:内部ポート` の形式にそろえる。
   - 認証情報などの秘密の値は、ファイルに直接書かず、`.env` に変数を追加して `env_file: [../.env]` で読み込む。`.env.example` にも変数名と仮の値を追記する。
   - 名前付きボリュームやサービス名は、他のファイルと重複させない。
2. `compose.yaml` の `include` にその1行を追加する (`# - compose/dify.yaml` のコメントを外す)。
3. `docker compose config --quiet` で設定が正しいことを確認し、`docker compose up -d` を実行する。

Dify の MCP 接続先は `http://backend:8000/mcp/` (同じネットワーク内) です。

### よく使うコマンド

```bash
cd backend
pytest                       # テスト (DBに接続できない場合は一部スキップ)
ruff check .                 # Lint
```

### DBを初期状態へ戻す

ホスト側で次を実行し、Dev Container または `docker compose up` で再度起動する (`-v` でDBのデータも削除される)。`.env` の `POSTGRES_*` を変更したときも、この手順が必要です。

```bash
docker compose down -v                                        # ルートのcompose
docker compose -f .devcontainer/docker-compose.yml down -v    # Dev Container
```

## 2. 初期投入データの編集手順

ローカルDBの初期データは `backend/seed/*.json` で定義します。

### ファイル形式

1ファイルに複数テーブルを書けます。キーはテーブル名、値は行の配列です。

```json
{
  "customer": [
    {
      "customer_id": "6f9619ff-8b86-d011-b42d-00c04fc964ff",
      "name": "サンプル顧客",
      "created_at": "2026-01-01T09:00:00+09:00"
    }
  ],
  "json_schema": [
    {
      "schema_id": "0b8f7f5e-3d6a-4c58-9a35-2f5d2e0c1a11",
      "schema_key": "sys.artifact",
      "schema_version": 1,
      "record_type": "ARTIFACT",
      "feature_domain": null,
      "schema_json": { "type": "object" }
    }
  ]
}
```

- 主キー(UUID)は固定値で書く。他テーブルから参照する行の主キーを後から指定できるようにするため。
- 省略できる列(`created_at` など、DBにデフォルト値がある列)は書かなくてよい。
- トリガーで保護されているテーブル ([テーブル構成と制約](#テーブル構成と制約)) は、投入後に更新・削除できない。

- 列名は実際のDBの列名と一致させる。存在しない列やテーブルはエラーになる。
- UUID・日時・日付・数値(Decimal)は文字列で書く。JSON/JSONB 列はそのままJSONで書く。
- 複数ファイルは **ファイル名順** に読み込まれる (`00_master.json`、`10_sample.json` のように番号を付けると管理しやすい)。
- テーブルへの挿入順は外部キーの依存関係から自動で決まるため、ファイル内の記載順は問わない。
- 主キーが重複する行はスキップされる。**既存行の内容は更新されない** ため、既存行を変えたいときは次の「やり直し」を行う。

### 投入

```bash
cd backend
python -m app.cli seed             # backend/seed/*.json を投入
python -m app.cli seed --dir PATH  # 別ディレクトリを指定
```

スキーマ変更 (マイグレーション) を適用してから投入してください。

### やり直し (全データを入れ直す)

1. [DBを初期状態へ戻す](#dbを初期状態へ戻す) を実行して Dev Container を再度開く。
2. `post-create.sh` が自動でマイグレーションとシード投入を行う。

### 現在のDBの内容を初期データとして保存する

Adminer などでデータを作成・編集した後、その内容をシードにできます。

```bash
cd backend
python -m app.cli export                          # backend/seed/export.json に出力
python -m app.cli export -o seed/10_sample.json   # 出力先を指定
```

- 全テーブルが外部キー順に出力される (`alembic_version` は除く)。出力ファイルはそのまま `seed` で再投入できる。
- 出力先が `backend/seed/` 内だと次回の `seed` で読み込まれる。同じ内容を重複して置かないよう、不要なファイルは整理する。
- 出力ファイルはレビューしてからコミットする。

## 3. DBの内容確認手順

### Adminer (ブラウザ)

1. `http://localhost:8080` を開く (VS Code の「ポート」タブからも開ける)。
2. 次の値でログインする (サーバーは設定済み)。

   | 項目 | 値 |
   |---|---|
   | システム | PostgreSQL |
   | サーバー | `db` |
   | ユーザー名 | `.env` の `POSTGRES_USER` |
   | パスワード | `.env` の `POSTGRES_PASSWORD` |
   | データベース | `.env` の `POSTGRES_DB` |

3. 左のメニューからテーブルを選び、「データ選択」で行を確認・編集する。「SQLコマンド」で任意のSQLも実行できる。

### psql (ターミナル)

コンテナ内では接続情報が環境変数に設定済みです (`.env` の値。Dev Container では `post-create.sh` が `~/.bashrc` に `PGUSER` などを設定するため、新しく開いたターミナルで有効になります)。

```bash
psql                                   # 対話モード
psql -c '\dt'                          # テーブル一覧
psql -c 'select * from customer limit 5'
```

`docker compose up` で起動した場合は、ホストから次のコマンドでも接続できます (db コンテナには `.env` の値が環境変数として入っています)。

```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

### ホストのクライアントから接続する

VS Code がフォワードする `localhost:5432` に、`.env` の `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` で接続できます。

### テーブル構成と制約

テーブルは [design/database/er-design.md](../design/database/er-design.md) の ER 図に対応し、定義は [app/models.py](app/models.py)、初期マイグレーションは [alembic/versions/0001_create_initial_tables.py](alembic/versions/0001_create_initial_tables.py) です。

| 区分 | テーブル |
|---|---|
| 顧客・製品 | `customer`、`product`、`product_version` |
| プラットフォーム | `platform`、`platform_version`、`platform_schema_binding` |
| コンテンツ | `content_record`、`content_revision`、`revision_parent`、`json_schema` |
| バージョンの採用内容 | `platform_version_content`、`product_version_content` |

DB側で保証している主なルールは次のとおりです (整合性ルールの番号は er-design.md のもの)。

| ルール | 実装 |
|---|---|
| 1. 作成元はプラットフォームか製品の一方のみ。FEATURE のときだけ `feature_domain` を持つ | CHECK制約 |
| 2. `(record_id, revision_no)` は一意 | UNIQUE制約 |
| 3. 採用リビジョンは `record_id` のレコードに属する。1バージョンにつき同一レコードは1リビジョン | 複合外部キー `(revision_id, record_id)`、主キー `(version_id, record_id)` |
| 7. 論理キーは共有スコープ(プラットフォーム/製品/共通)内で一意 | 部分一意インデックス |
| 8. `content_revision`、`json_schema` は更新・削除不可 | トリガー |
| 8. `released_at` を設定した `platform_version`、`product_version` と、その内容テーブルの行は更新・削除不可 | トリガー |
| 製品の `base_platform_version_id` は作成後に変更不可 | トリガー |

- `released_at` が NULL のバージョンは編集中として扱う。公開済みバージョンへの内容の**追加**はDBでは止めないため、MCPサーバー側で検証する。
- JSON Schema による `content_json` の検証、参照先・アクセス権の検証、製品構成の重複・必須フィーチャーの検証は、DBではなくバックエンド(MCPサーバー)で行う。
- 主キーのUUIDは `gen_random_uuid()`、`created_at` は `now()` がデフォルト。

## 4. REST API / MCPツールの構築手順

REST API と MCP ツールは同じプロセス ([app/main.py](app/main.py)) で動き、DBアクセスの処理を共通化して両方から呼び出す構成にします。

```
app/
  models.py        # SQLModel のテーブル定義 (DBの形)
  schemas.py       # Pydantic の入出力モデル (JSONの形)
  services.py      # DB ⇔ JSON の変換と更新処理 (REST/MCP共通)
  routers/         # FastAPI のルーター
  mcp_server.py    # MCPツール
  main.py          # アプリ本体 (ルーターの登録、/mcp のマウント)
```

`models.py` と `db.py` は作成済みです ([テーブル構成と制約](#テーブル構成と制約))。`schemas.py` `services.py` `routers/` は必要になった時点で作成します。以降の手順は、例として `customer` テーブルの取得・設定APIを作る流れです。

### 手順1: テーブルを用意する

`app/models.py` に ER 設計のテーブルが定義済みのため、まず対象のモデルを確認します。テーブルの追加・列の変更が必要な場合は [5. スキーマ変更手順](#5-スキーマ変更手順) に従ってください。

### 手順2: JSON の入出力モデルを定義する

`app/schemas.py` に Pydantic v2 のモデルを定義します。DBの行とJSONの形が違う場合は、ここで差を吸収します。

```python
import uuid
from datetime import datetime

from pydantic import BaseModel


class CustomerOut(BaseModel):
    customer_id: uuid.UUID
    name: str
    created_at: datetime


class CustomerIn(BaseModel):
    customer_id: uuid.UUID | None = None  # 省略時は新規作成
    name: str
```

### 手順3: DB ⇔ JSON 変換の処理を書く

`app/services.py` に、取得 (DB → JSON) と設定 (JSON → DB) の処理を書きます。REST と MCP の両方から呼ぶため、`Session` は引数で受け取ります。

```python
from sqlmodel import Session, select

from app.models import Customer
from app.schemas import CustomerIn, CustomerOut


def list_customers(session: Session) -> list[CustomerOut]:
    rows = session.exec(select(Customer).order_by(Customer.created_at)).all()
    return [CustomerOut.model_validate(r, from_attributes=True) for r in rows]


def upsert_customer(session: Session, data: CustomerIn) -> CustomerOut:
    row = session.get(Customer, data.customer_id) if data.customer_id else None
    if row is None:
        row = Customer(**data.model_dump(exclude_none=True))
    else:
        row.name = data.name
    session.add(row)
    session.commit()
    session.refresh(row)
    return CustomerOut.model_validate(row, from_attributes=True)
```

JSON Schema の検証など、DBの外部キーで表現できない整合性チェックもこの層で行います ([design/database/er-design.md](../design/database/er-design.md) の整合性ルール参照)。

### 手順4: REST API を作る

1. `app/routers/customers.py` を作成する。

   ```python
   from collections.abc import Iterator

   from fastapi import APIRouter, Depends
   from sqlmodel import Session

   from app import services
   from app.db import engine
   from app.schemas import CustomerIn, CustomerOut

   router = APIRouter(prefix="/customers", tags=["customers"])


   def get_session() -> Iterator[Session]:
       with Session(engine) as session:
           yield session


   @router.get("", response_model=list[CustomerOut])
   def get_customers(session: Session = Depends(get_session)):
       return services.list_customers(session)


   @router.put("", response_model=CustomerOut)
   def put_customer(data: CustomerIn, session: Session = Depends(get_session)):
       return services.upsert_customer(session, data)
   ```

   (`routers/__init__.py` も空ファイルで作成する)

2. [app/main.py](app/main.py) に登録する。

   ```python
   from app.routers import customers

   app.include_router(customers.router)
   ```

3. 動作確認。`http://localhost:8000/docs` (Swagger UI) から実行するか、次のように呼び出す。

   ```bash
   curl -X PUT localhost:8000/customers -H 'content-type: application/json' \
     -d '{"name": "サンプル顧客"}'
   curl localhost:8000/customers
   ```

4. `tests/` に pytest を追加する (`fastapi.testclient.TestClient` を使う。既存の [tests/test_health.py](tests/test_health.py) を参照)。

### 手順5: MCP ツールを作る

[app/mcp_server.py](app/mcp_server.py) の `mcp` に `@mcp.tool` で関数を追加します。関数名・docstring・型ヒントが、そのままMCPクライアント(LLM)に公開されるツール名・説明・引数スキーマになるため、docstring は用途が分かるように書きます。

```python
from sqlmodel import Session

from app import services
from app.db import engine
from app.schemas import CustomerIn


@mcp.tool
def list_customers() -> list[dict]:
    """登録されている顧客の一覧をJSONで返す。"""
    with Session(engine) as session:
        return [c.model_dump(mode="json") for c in services.list_customers(session)]


@mcp.tool
def upsert_customer(customer: CustomerIn) -> dict:
    """顧客を登録または更新する。customer_idを省略すると新規作成する。"""
    with Session(engine) as session:
        return services.upsert_customer(session, customer).model_dump(mode="json")
```

- 追加後は uvicorn を再起動する (`--reload` なら自動)。
- ツールの確認は次の「GitHub Copilot での MCP 設定」で行うか、[MCP Inspector](https://github.com/modelcontextprotocol/inspector) (`npx @modelcontextprotocol/inspector`、Transport: Streamable HTTP、URL: `http://localhost:8000/mcp/`) を使う。
- 認可・参照先の存在確認など、MCPサーバーで検証すると設計されているルールは `services.py` で実装し、REST と MCP で同じ検証が働くようにする。

## 5. スキーマ変更手順

テーブルの追加、列の追加・変更・削除、制約・インデックスの変更は、**モデル ([app/models.py](app/models.py)) を編集し、Alembic でマイグレーションを作成**して行います。DBを直接 (Adminer や psql の DDL で) 変更しないでください。チームの全員と本番環境へ同じ変更を再現できなくなります。

### 流れ

1. `git pull` で最新を取り込み、未適用のマイグレーションがあれば適用する (`alembic upgrade head`)。
2. `app/models.py` を編集する。
3. マイグレーションを生成する。

   ```bash
   cd backend
   alembic revision --autogenerate -m "add customer note"
   ```

4. `alembic/versions/` に生成されたファイルを**必ずレビュー**して、必要なら修正する ([レビューの観点](#レビューの観点))。
5. 適用して確認する。

   ```bash
   alembic upgrade head       # 適用
   alembic check              # モデルとDBに差分がないことを確認 (差分があればエラー)
   pytest                     # テスト
   alembic downgrade -1       # 1つ戻せることを確認
   alembic upgrade head       # 再適用
   ```

6. 列やテーブルの追加・削除に合わせて、`backend/seed/*.json` を更新する ([2. 初期投入データの編集手順](#2-初期投入データの編集手順))。
7. モデルとマイグレーションファイルを一緒にコミットする。

### 例: 列を追加する

`Customer` に任意の備考列を追加する場合。

```python
class Customer(SQLModel, table=True):
    ...
    note: str | None = None
```

生成されたマイグレーションが `op.add_column('customer', sa.Column('note', ..., nullable=True))` になっていることを確認します。

### 既存データがあるテーブルへの NOT NULL 列の追加

そのまま追加すると、既存行があるとエラーになります。`server_default` を付けるか、3段階に分けます。

```python
def upgrade() -> None:
    op.add_column("customer", sa.Column("status", sa.String(), nullable=True))
    op.execute("UPDATE customer SET status = 'ACTIVE'")
    op.alter_column("customer", "status", nullable=False)
```

### レビューの観点

| 観点 | 内容 |
|---|---|
| 列名・テーブル名の変更 | autogenerate は「削除+追加」と判断し、**データが消える**。`op.alter_column(..., new_column_name=...)`、`op.rename_table(...)` に書き換える |
| 型の変更 | 変換できない型の変更は `postgresql_using=` を指定する。例: `op.alter_column(..., type_=sa.Integer(), postgresql_using="col::integer")` |
| 検出されないもの | CHECK制約の変更、`server_default` の変更、トリガー、関数、ビューは autogenerate では検出されない。`op.execute()` や `op.create_check_constraint()` で手書きする (トリガーの例: [0001_create_initial_tables.py](alembic/versions/0001_create_initial_tables.py)) |
| 制約名 | [app/models.py](app/models.py) の `naming_convention` により名前が自動で決まる。複数列のUNIQUE・CHECKは `name=` を明示する |
| `downgrade()` | 元に戻す処理が正しく書かれていること。トリガー関数など `op.execute` で作成したものは `downgrade()` で削除する |
| 生成SQL | `alembic upgrade head --sql` で、実行されるSQLを確認できる |

### 注意事項

- **適用済み(共有済み)のマイグレーションは編集しない。** 変更は新しいマイグレーションで行う。自分のブランチだけで未共有なら、`alembic downgrade` で戻してから作り直してよい。
- 不変性トリガーのあるテーブル ([テーブル構成と制約](#テーブル構成と制約)) の既存行を更新・削除するマイグレーションは、トリガーに拒否される。データを直す場合は、設計どおり新しいリビジョン・バージョンとして登録する。やむを得ず直接更新する場合は、`ALTER TABLE ... DISABLE TRIGGER` と `ENABLE TRIGGER` で囲み、レビューで理由を共有する。
- 複数人が同時に別のマイグレーションを作ると、`alembic upgrade head` が「Multiple head revisions」で失敗する。`alembic heads` で確認し、`alembic merge -m "merge heads" <rev1> <rev2>` で統合する。
- 他の人のマイグレーションを取り込んだら `alembic upgrade head` を実行する (Dev Container の再作成時は `post-create.sh` が自動で実行する)。
- 本番(Amazon RDS for PostgreSQL)へも同じマイグレーションを `alembic upgrade head` で適用する。事前に `alembic upgrade head --sql` でSQLを確認し、ロックが長くなる変更 (大きいテーブルへの列追加+書き換え、インデックス作成) はメンテナンス時間を検討する。

### 状態の確認コマンド

```bash
alembic current            # DBに適用済みのリビジョン
alembic heads              # 最新のリビジョン (1つであること)
alembic history            # 履歴
```

## 6. GitHub Copilot での MCP 設定手順

VS Code の GitHub Copilot (Agent モード) から、このバックエンドの MCP ツールを利用します。

### 手順

1. Dev Container 内でバックエンドを起動する (`uvicorn app.main:app --reload --host 0.0.0.0`)。
2. リポジトリに `.vscode/mcp.json` を作成する。

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

   - Dev Container 内の VS Code では、コンテナ内の `localhost:8000` に接続される。
   - URL 末尾の `/` を付けること (付けないとリダイレクトされ接続に失敗する場合がある)。
   - チームで共有する場合はこのファイルをコミットする。認証情報を書かないこと。

3. `.vscode/mcp.json` を開くと表示される **開始** をクリックするか、コマンドパレットの **MCP: List Servers** → `develop-assistant` → **Start Server** を実行する。
4. Copilot Chat を **Agent** モードにし、ツールアイコン (「ツールの構成」) の一覧に `develop-assistant` のツール (`db_version` など) が表示されていることを確認する。
5. チャットで利用する。例: 「`db_version` ツールで PostgreSQL のバージョンを教えて」。ツールの実行時には確認ダイアログが表示されるので許可する。

### うまく動かないとき

| 症状 | 確認すること |
|---|---|
| サーバーが起動できない | uvicorn が起動しているか。`curl localhost:8000/health` が `ok` を返すか |
| ツールが表示されない | **MCP: List Servers** → サーバー → **Show Output** でログを確認。ツールを追加した後は uvicorn の再起動とサーバーの再起動を行う |
| 接続エラー | URL が `http://localhost:8000/mcp/` (末尾 `/`) か。ポート 8000 がフォワードされているか |
| 企業・組織のポリシーで利用できない | GitHub の組織設定で Copilot の「MCP servers in Copilot」が有効か管理者に確認する |

### 補足: Dify / Claude Code から接続する場合

同じ URL (`http://localhost:8000/mcp/`、Streamable HTTP) を使います。Claude Code の場合の例:

```bash
claude mcp add --transport http develop-assistant http://localhost:8000/mcp/
```
