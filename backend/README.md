# backend

FastAPI (REST) と FastMCP (MCP) を1つのプロセスで提供するバックエンドです。データの保存先には PostgreSQL 18 を使います。リポジトリルートに `.env` を作成し、DB 接続情報を設定してください。

要件: [design/requiments/enviroment.md](../design/requiments/enviroment.md)

| 項目 | 内容 |
|---|---|
| REST API | `http://localhost:8000/v1/` (ヘルスチェック: `/health`)。仕様: [openapi/openapi.yaml](../openapi/openapi.yaml) (`/openapi.yaml` で配信し、Swagger UI の `/docs` で表示。[8. OpenAPI 仕様の編集手順](#8-openapi-仕様の編集手順)) |
| MCP | `http://localhost:8000/mcp/` (Streamable HTTP。末尾の `/` が必要) |
| DB | PostgreSQL 18 (`db:5432`。ユーザー・パスワード・DB名は [.env](#環境変数-env) で設定) |
| DB確認 | VS Code の PostgreSQL 拡張機能 ([4. DBの内容確認手順](#4-dbの内容確認手順)) |

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
- `.env` がない場合は起動できないため、必ず `.env.example` をコピーして `.env` を作成する。`.env` に追加の設定は不要。
- ポート番号 (`DB_PORT`、`BACKEND_PORT`、`WEB_PORT`) は認証情報ではないため、必要なときに `.env` へ追記するか、コマンドラインで指定する。
- ローカル専用の値であり、本番 (Amazon RDS) の認証情報は使用しない。

### コンテナの構成

| サービス | 内容 |
|---|---|
| `app` | 開発コンテナ (Dev Container のみ)。Python 3.13 (`/opt/venv`)、Node.js 22、psql |
| `db` | PostgreSQL 18。データは named volume `pgdata` に保存される |

設定は [.devcontainer/](../.devcontainer) にあります。`db` の定義はルートの compose と共通で、[compose/](../compose) を読み込んでいます。ポート 3000 / 8000 / 5432 は VS Code が自動でフォワードします。

`app` コンテナはホストから隔離されています (全capability剥奪、sudoなし、`.git` は読み取り専用)。`git commit` / `git push` はホスト側で実行してください。

### Dev Container を使わずに全サービスを起動する

リポジトリのルートで `docker compose up` を実行すると、DB・バックエンド・フロントエンドがすべて起動し、初期データも投入されます。VS Code 以外から動作を確認したい場合や、Dify など他のサービスと組み合わせて使う場合に利用します。実行前に、**`cp .env.example .env` で `.env` を作成してください** ([環境変数 (.env)](#環境変数-env))。`.env` がない場合は Compose がエラーになります。

```bash
docker compose up -d --build   # 起動 (-d でバックグラウンド。省略するとログを表示)
docker compose ps -a           # 状態確認
docker compose logs -f backend # ログ確認 (サービス名: db / backend-init / backend / web)
docker compose down            # 停止 (DBのデータは残る)
docker compose down -v         # 停止してDBのデータも削除
```

起動順序は (`.env` がある場合) `db` → `backend-init` (マイグレーション適用と `backend/seed/*.json` の投入。完了すると終了する) → `backend` → `web` です。`backend` と `web` はソースをマウントしており、編集するとホットリロードされます。

| サービス | URL (ホスト側) | 定義 |
|---|---|---|
| web (Next.js) | `http://localhost:3000` | [compose/web.yaml](../compose/web.yaml) |
| backend (REST / MCP) | `http://localhost:8000` (MCP: `/mcp/`) | [compose/backend.yaml](../compose/backend.yaml) |
| db (PostgreSQL 18) | `localhost:5432` | [compose/db.yaml](../compose/db.yaml) |

- ポートは `127.0.0.1` のみに公開される。変更する場合は環境変数 `WEB_PORT` / `BACKEND_PORT` / `DB_PORT` を指定する (例: `DB_PORT=15432 docker compose up -d`)。
- 初期データを変更したら、`docker compose run --rm backend-init` で再投入する (既存行は更新されない。[3. 初期投入データの編集手順](#3-初期投入データの編集手順))。
- スキーマ変更のコマンドは `docker compose exec backend alembic ...` のように実行する。
- Dev Container と同時に起動しない (同じプロジェクト・同じDBを共有するため、どちらか一方を使う)。

### docker compose up 後に Swagger UI で REST API を確認する

`docker compose up` (または `docker compose up -d backend`) の後、ブラウザで REST API の仕様と動作を確認できます。

1. `docker compose ps` で、`backend` が `healthy`、`backend-init` が `Exited (0)` であることを確認する (`curl localhost:8000/health` が `{"status":"ok"}` を返せばよい)。
2. ブラウザで `http://localhost:8000/docs` を開く (ポートを変えた場合は `BACKEND_PORT` の値)。
3. 画面上部に `develop_assistant backend API 1.0.0 OAS 3.1` と表示され、`json-schema`・`record` の operation (`listSchemas`、`createRecord` など) が並んでいることを確認する。
   - 表示されているのは、FastAPI が実装から自動生成した仕様ではなく、[openapi/openapi.yaml](../openapi/openapi.yaml) (`http://localhost:8000/openapi.yaml`) です。
4. 画面下部の **Schemas** で `ArtifactContent` を開き、`SYS.1〜SYS.3 成果物` などのスキーマが展開されていることを確認する。仕様の外部参照 (`$ref: /v1/schemas/by-key/sys.artifact/schema-json`) が、バックエンドのスキーマテーブルから解決されている状態です。画面上部に `Errors` / `Resolver error` が出ていないことも確認する。
5. operation を試す。例: `listSchemas` を開き、**Try it out** → **Execute** を押すと、登録済みのスキーマの一覧 (`sys.artifact` など) が返る。`getSchemaByKey` に `schemaKey` = `sys.artifact` を指定すると、スキーマ本体 (`schemaJson`) まで取得できる。

- 認証は未実装のため、**Authorize** で値を入力する必要はない (仕様には Bearer 認証を記載している)。
- Swagger UI の画面 (JavaScript / CSS) は、CDN (`cdn.jsdelivr.net`) から読み込まれる。インターネットに接続できない環境では、`/docs` が空白になる。その場合は `http://localhost:8000/openapi.yaml` を VS Code などで開いて確認する。
- `openapi/openapi.yaml` を編集した場合は、ブラウザを再読み込みすれば反映される (バックエンドの再起動は不要。[8. OpenAPI 仕様の編集手順](#8-openapi-仕様の編集手順))。
- 画面が表示されない、または 404 になるときは、`docker compose logs backend` を確認し、`openapi/` が `backend` コンテナの `/openapi` にマウントされているか (`docker compose exec backend ls /openapi`) を確認する。

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

## 2. GitHub Copilot での MCP 設定手順

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
4. Copilot Chat を **Agent** モードにし、ツールアイコン (「ツールの構成」) の一覧に `develop-assistant` のツール (`db_version`、`listSchemas` など) が表示されていることを確認する。
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

## 3. 初期投入データの編集手順

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

### 設計ファイルから初期データを生成する

JSON スキーマと成果物の例は、設計ファイル (`design/database/schemas/`) を正本とし、ツールで `backend/seed/` へ変換します (要件: [enviroment.md](../design/requiments/enviroment.md) の 4.4)。

| 生成ファイル | 入力 | 内容 |
|---|---|---|
| `seed/10_json_schema.json` | `sys.artifact.schema.json` | `json_schema` の行。`schema_key`・`schema_version` は `$id` から取る |
| `seed/20_artifact_examples.json` | `examples/*.json` の `valid` | 例1件ごとに `content_record` 1行と `content_revision` 1行 (`revision_no` = 1)。`logical_key` は `<種別キー>.<連番>` (例: `sys1.actor.001`) |

```bash
cd backend
python -m app.cli build-seed          # 設計ファイルから seed を生成する
python -m app.cli build-seed --check  # 書き込まず、生成ファイルが設計と一致するか確認する
```

- **`backend/` に移動して実行してください。** `app` パッケージは `backend/` 直下にあるため、リポジトリ直下で `python -m app.cli ...` を実行すると `No module named 'app'` で失敗します。リポジトリ直下から実行する場合は `PYTHONPATH=backend python -m app.cli build-seed` としてください。依存パッケージ (`jsonschema` など) は `pip install -e backend` で入ります (Dev Container では導入済み)。
- DBへの接続は不要で、`.env` も読み込みません。`backend` コンテナは `design/` を参照できないため、ホストまたは Dev Container の `app` コンテナで実行してください。`docker compose up` では実行されません。生成ファイルはコミットします。
- 生成ファイルは手で編集しません。設計ファイルを編集して再実行します。
- ID は `$id` や `logical_key` から決定的に生成するため (UUIDv5)、同じ入力なら同じ内容になります。
- スキーマ・例が不正 (メタスキーマ違反、正常例がスキーマに不適合) の場合は、何も書き込まずエラーで終了します。
- スキーマの版を上げる (`$id` の版を変える) と、生成済みの旧版の行は残したまま新しい版の行が追加されます。同じ版のまま内容を変えるとエラーになります (登録済みスキーマは変更できないため)。
- 例の中の参照 (`record_id`) は書き換えません。参照先の存在確認は、書き込み時のバックエンドの検証で行うため、初期データには参照先がない例が含まれます。

`seed/00_sample_master.json` は、ER 設計 ([er-design.md](../design/database/er-design.md)) の全テーブルを 1 行以上含む手書きのサンプルです (`json_schema` は `10_json_schema.json` が提供します)。

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

VS Code の PostgreSQL 拡張機能などでデータを作成・編集した後、その内容をシードにできます。

```bash
cd backend
python -m app.cli export                          # backend/seed/export.json に出力
python -m app.cli export -o seed/10_sample.json   # 出力先を指定
```

- 全テーブルが外部キー順に出力される (`alembic_version` は除く)。出力ファイルはそのまま `seed` で再投入できる。
- 出力先が `backend/seed/` 内だと次回の `seed` で読み込まれる。同じ内容を重複して置かないよう、不要なファイルは整理する。
- 出力ファイルはレビューしてからコミットする。

## 4. DBの内容確認手順

### VS Code の PostgreSQL 拡張機能

VS Code の PostgreSQL 拡張機能 (`ms-ossdata.vscode-pgsql`) で、テーブルの内容確認とSQLの実行ができます。Dev Container では自動でインストールされます。ホスト側の VS Code で使う場合は、拡張機能ビューで「PostgreSQL」(Microsoft) をインストールしてください。

1. アクティビティバーの PostgreSQL アイコンを開き、接続の追加 (**Add Connection**) を選ぶ。
2. 次の値を入力して接続する (表示名は拡張機能のバージョンにより異なる)。

   | 項目 | 値 |
   |---|---|
   | サーバー (ホスト) | Dev Container 内の VS Code: `db` / ホスト側の VS Code: `localhost` |
   | ポート | `5432` (`DB_PORT` を変更した場合はその値) |
   | 認証 | パスワード |
   | ユーザー名 | `.env` の `POSTGRES_USER` |
   | パスワード | `.env` の `POSTGRES_PASSWORD` |
   | データベース | `.env` の `POSTGRES_DB` |

3. 接続したサーバーを展開し、データベース → スキーマ → テーブルの順にたどる。テーブルを右クリックして行を確認する。
4. データベースを右クリックしてクエリエディターを開くと、任意の SQL を実行できる。結果は表で確認できる。

- 接続情報には `.env` の値を使う。接続設定をリポジトリ内のファイル (`.vscode/settings.json` など) にコミットしない。パスワードの保存は拡張機能の保管機能に任せる。
- `docker compose up` で起動した場合 (Dev Container を使わない場合) も、ホスト側の VS Code から `localhost` に接続できる。ポートは `127.0.0.1` のみに公開されている。
- 接続できないときは、`db` が healthy か (`docker compose ps`)、ホストとポートが上の表のとおりかを確認する。

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

## 5. REST API / MCPツールの構築手順

REST API は [api-guideline.md](../design/requiments/api-guideline.md) に従い、**OpenAPI 仕様 ([openapi/openapi.yaml](../openapi/openapi.yaml)) を先に作成してから実装します** ([8. OpenAPI 仕様の編集手順](#8-openapi-仕様の編集手順))。MCP ツールは REST API の operation を MCP として公開したもので、REST と MCP の処理は `services.py` に共通化します (要件: [enviroment.md](../design/requiments/enviroment.md) の ENV-046)。

```
openapi/openapi.yaml   # REST API の仕様 (実装の基準)
backend/app/
  models.py        # SQLModel のテーブル定義 (DBの形)
  schemas.py       # Pydantic の入出力モデル (JSONの形。camelCase)
  services.py      # DB ⇔ JSON の変換と更新処理、エラーの生成 (REST/MCP共通)
  routers/         # FastAPI のルーター (薄いアダプター)
  mcp_server.py    # MCPツール (薄いアダプター)
  main.py          # アプリ本体 (ルーターの登録、エラー形式、/mcp のマウント)
```

### 共通化のルール

| 項目 | ルール |
|---|---|
| 対応関係 | REST の operation 1 つにつき MCP ツールを 1 つ作る。ツール名は `operationId` (`verbResource`)、引数名は REST と同じ camelCase |
| 処理 | 業務処理・DB 更新・JSON スキーマの検証・エラーの生成は `services.py` にだけ書く。ルーターと MCP ツールは、入力の受け取りと `services.py` の呼び出し、結果・エラーの変換だけを行う |
| 入出力 | REST と MCP は同じ Pydantic モデル (`schemas.py`) を使う。JSON のフィールド名は camelCase (`alias_generator=to_camel`) |
| エラー | `services.ServiceError` が `{"code", "message", "details"}` を作る。REST は HTTP ステータス (400 / 404 / 409 / 422 / 500)、MCP は ToolError のメッセージ (同じ JSON) で返す |
| MCP 専用のツール | REST API にない処理に限り認める (`MCP_ONLY_TOOLS`。例: `db_version`) |
| 認証 | 仕様 (`openapi.yaml`) には Bearer 認証を必須と記載しているが、ローカル開発では未実装 ([ADR-0014](../design/requiments/adr/0014-openapi-schema-import.md)) |

仕様と実装の一致は `tests/test_api_conformance.py` が確認します (全 operation に同名の MCP ツールがあること、REST と MCP が同じ結果・同じエラーを返すこと、スキーマの外部参照がホストと版を含まないこと)。このテストは `openapi/openapi.yaml` を読むため、`openapi/` がない環境ではスキップされます (`backend` コンテナには `/openapi` としてマウントされるので実行されます)。

`models.py` と `db.py` は作成済みです ([テーブル構成と制約](#テーブル構成と制約))。`schemas.py` `services.py` `routers/` は JSON Schema の検証とレコード登録 ([7. JSON スキーマの編集手順](#7-json-スキーマの編集手順)) 用に作成済みです。以降の手順は、例として `customer` テーブルの取得 API を追加する流れです。

### 手順1: OpenAPI 仕様を更新する

[8. OpenAPI 仕様の編集手順](#8-openapi-仕様の編集手順) に従い、`openapi/openapi.yaml` に operation (`listCustomers` など) とスキーマを追加する。パスは kebab-case (`/v1/customers`)、JSON のフィールドは camelCase、ステータスとエラー形式はガイドラインに従う。

### 手順2: テーブルを用意する

`app/models.py` に ER 設計のテーブルが定義済みのため、まず対象のモデルを確認します。テーブルの追加・列の変更が必要な場合は [6. スキーマ変更手順](#6-スキーマ変更手順) に従ってください。

### 手順3: JSON の入出力モデルを定義する

`app/schemas.py` に、`ApiModel` を継承した Pydantic v2 のモデルを定義します (属性名は snake_case、JSON のフィールド名は自動で camelCase になる)。モデルは `openapi.yaml` のスキーマと一致させます。

```python
import uuid
from datetime import datetime


class CustomerOut(ApiModel):
    customer_id: uuid.UUID
    name: str
    created_at: datetime
```

### 手順4: DB ⇔ JSON 変換の処理を書く

`app/services.py` に、取得 (DB → JSON) と設定 (JSON → DB) の処理を書きます。REST と MCP の両方から呼ぶため、`Session` は引数で受け取ります。業務エラーは `ServiceError(status_code, code, message, details)` で表します。

```python
from sqlmodel import Session, select

from app.models import Customer
from app.schemas import CustomerOut


def list_customers(session: Session) -> list[CustomerOut]:
    rows = session.exec(select(Customer).order_by(Customer.created_at)).all()
    return [CustomerOut.model_validate(r) for r in rows]
```

JSON Schema の検証など、DBの外部キーで表現できない整合性チェックもこの層で行います ([design/database/er-design.md](../design/database/er-design.md) の整合性ルール参照)。

### 手順5: REST API を作る

1. `app/routers/customers.py` を作成する。`operation_id` は仕様の `operationId` と同じにする。

   ```python
   from typing import Annotated

   from fastapi import APIRouter, Depends
   from sqlmodel import Session

   from app import services
   from app.db import get_session
   from app.schemas import CustomerOut

   router = APIRouter(prefix="/v1/customers", tags=["customer"])

   SessionDep = Annotated[Session, Depends(get_session)]


   @router.get("", response_model=list[CustomerOut], operation_id="listCustomers")
   def list_customers(session: SessionDep):
       return services.list_customers(session)
   ```

2. [app/main.py](app/main.py) に登録する (`app.include_router(customers.router)`)。
3. 動作確認。`http://localhost:8000/docs` (Swagger UI) から実行するか、`curl localhost:8000/v1/customers` で呼び出す。
4. `tests/` に pytest を追加する (`fastapi.testclient.TestClient` を使う。[tests/test_content_api.py](tests/test_content_api.py) を参照)。

### 手順6: MCP ツールを作る

[app/mcp_server.py](app/mcp_server.py) の `mcp` に、同じ operation のツールを追加します。ツール名は `operationId`、引数名は REST と同じ camelCase にします。docstring と型ヒントが、MCPクライアント(LLM)に公開されるツールの説明・引数スキーマになります。

```python
@mcp.tool(name="listCustomers")
def list_customers():
    """登録されている顧客の一覧をJSONで返す。"""
    return _run(lambda s: services.list_customers(s))
```

- `_run` が、サービス層の呼び出しとエラーの変換 (REST と同じ `code` / `message` / `details`) を行う。
- 追加後は uvicorn を再起動する (`--reload` なら自動)。
- ツールの確認は [2. GitHub Copilot での MCP 設定手順](#2-github-copilot-での-mcp-設定手順) で行うか、[MCP Inspector](https://github.com/modelcontextprotocol/inspector) (`npx @modelcontextprotocol/inspector`、Transport: Streamable HTTP、URL: `http://localhost:8000/mcp/`) を使う。
- 認可・参照先の存在確認など、MCPサーバーで検証すると設計されているルールは `services.py` で実装し、REST と MCP で同じ検証が働くようにする。
- 最後に `tests/test_api_conformance.py` を実行し、仕様・REST・MCP の一致を確認する。

## 6. スキーマ変更手順

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

6. 列やテーブルの追加・削除に合わせて、`backend/seed/*.json` を更新する ([3. 初期投入データの編集手順](#3-初期投入データの編集手順))。
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

## 7. JSON スキーマの編集手順

`json_schema` 以外のテーブルの jsonb 列 (`content_revision.content_json`) の構造は、`json_schema.schema_json` の JSON Schema (draft 2020-12) で定義します。スキーマの変更にモデルの編集やマイグレーションは不要です (要件: [design/requiments/enviroment.md](../design/requiments/enviroment.md) の 4.3)。

### 仕組み

- レコードの追加・更新時、バックエンドが jsonb 列の値を対応するスキーマで検証します。通過した場合のみDBを更新します。
- 検証に失敗すると、DBは更新されず、エラーの詳細が返ります (REST は HTTP 422、MCP はツールのエラー)。応答の `details.errors[].path` (JSON Pointer) と `message` で違反箇所を特定し、スキーマを再取得して入力を修正し、再送してください。AI も人間も同じ手順で修正できます。
- 検証はバックエンドの `app/services.py` で行い、REST と MCP で共通です。スキーマは、リクエストで `schemaId`、または `schemaKey` (`schemaVersion` 省略時は最新版) として指定します。検証エラーの `details` には、使ったスキーマの `schemaId`・`schemaKey`・`schemaVersion`・`latestSchemaVersion` と、再取得の方法 (`refetch`) が含まれます。
- `json_schema` の行は更新・削除できません (トリガーで保護。[テーブル構成と制約](#テーブル構成と制約))。**スキーマの編集は、`schema_version` を増やした新しい行の追加**で行います。既存のリビジョンは、作成時点の `schema_id` のスキーマを参照し続けます。

### 使うAPI

| 操作 | REST | MCPツール (operationId) |
|---|---|---|
| スキーマの一覧 | `GET /v1/schemas?schemaKey=` | `listSchemas` |
| スキーマの取得 | `GET /v1/schemas/{schemaId}` | `getSchema` |
| スキーマの取得 (キー指定) | `GET /v1/schemas/by-key/{schemaKey}?version=` (省略時は最新版) | `getSchemaByKey` |
| スキーマ本体 (`schemaJson`) の取得 | `GET /v1/schemas/{schemaId}/schema-json`、`GET /v1/schemas/by-key/{schemaKey}/schema-json?version=` | `getSchemaJson`、`getSchemaJsonByKey` |
| スキーマの登録 | `POST /v1/schemas` | `createSchema` |
| レコード+最初のリビジョンの作成 | `POST /v1/records` | `createRecord` |
| リビジョンの追加 | `POST /v1/records/{recordId}/revisions` | `createRevision` |
| レコードの取得 | `GET /v1/records/{recordId}` | `getRecord` |

エラーは、REST では HTTP ステータスと JSON `{"code", "message", "details"}`、MCP では同じ JSON をメッセージとする ToolError です。検証エラーは HTTP 422 の `code: JSON_SCHEMA_VALIDATION_FAILED` で、`details` に `target`・`schema`・`errors`・`refetch`・`hint` が入ります。入力項目の指定エラー (必須項目の未指定など) は HTTP 400 (`INVALID_REQUEST`) です。Swagger UI (`/docs`) で試せます。

### 手順

1. 現行のスキーマを確認する。`schema_key` ごとの最新の `schema_version` を調べる (`GET /v1/schemas?schemaKey=...`、または次のSQL)。

   ```sql
   SELECT schema_id, schema_key, schema_version, record_type, feature_domain
   FROM json_schema ORDER BY schema_key, schema_version;
   ```

2. 現行の `schema_json` をファイルに書き出して編集する。成果物スキーマ (`sys.artifact`) は [design/database/schemas/sys.artifact.schema.json](../design/database/schemas/sys.artifact.schema.json) が正本。構成と編集の方針は [json-schema-design.md](../design/database/json-schema-design.md) を参照する。
3. `$id` の末尾の版を `schema_version` と同じ新しい値にする (`urn:das:schema:<schema_key>:<schema_version>`)。
4. スキーマ自体の妥当性と、正常例・異常例 (`examples/`) を検証する。種別を追加・変更したときは対応する examples も更新する。

   ```bash
   python design/database/schemas/validate.py
   ```

   バックエンドでも、登録前にメタスキーマ (draft 2020-12) で `schema_json` を検証し、不正なスキーマは登録されません。

5. 新しい行として登録する。`schema_id` は新しい UUID、`schema_key` は既存と同じ値、`schema_version` は最新+1、`record_type`・`feature_domain` は既存の行と揃える。登録は次のどちらかで行う。
   - 成果物スキーマ (`sys.artifact`) を設計ファイルから登録する: `$id` の版を上げたうえで `python -m app.cli build-seed` を実行すると、`backend/seed/10_json_schema.json` に新しい版の行が追加される (旧版の行は残る。[設計ファイルから初期データを生成する](#設計ファイルから初期データを生成する))。続けて `python -m app.cli seed` を実行する。
   - シードに追加する: `backend/seed/*.json` の `json_schema` に新しい行を書き、`python -m app.cli seed` を実行する ([3. 初期投入データの編集手順](#3-初期投入データの編集手順))。既存行は更新されないため、既存の行を書き換えず、新しい行を追加する。
   - スキーマ登録のAPI / MCPツールを使う (`POST /v1/schemas`、`createSchema`)。`schema_json` はメタスキーマで検証され、`$id` を書く場合は `urn:das:schema:<schema_key>:<schema_version>` と一致している必要がある。シード投入はバックエンドの検証を通らないため、`validate.py` で事前に確認する。
6. 新しいスキーマを使うプラットフォームに割り当てる。`platform_schema_binding` に `(platform_id, 新しい schema_id)` の行を追加する。複数プラットフォームで同じ行を共有できる。なお、`content_json` の検証に使うスキーマはリクエストで指定したもの (`schema_key` のみなら最新版) で、現時点では `platform_schema_binding` による絞り込みは行わない。
7. 新しいスキーマで検証されることを確認する。違反する `contentJson` を送って、HTTP 422 と `details.errors` が返ること、DBが更新されていないことを確認する。

   ```bash
   pytest
   ```

8. `seed` ファイルの変更をコミットする。VS Code の PostgreSQL 拡張機能などで登録した場合は、[現在のDBの内容を初期データとして保存する](#現在のdbの内容を初期データとして保存する) でシードへ反映する。

### 注意事項

- 登録済みのスキーマ (行) を直接 UPDATE / DELETE しない。誤って登録した場合も、新しい `schema_version` の行で置き換える。
- 新しい版で必須項目を追加するなど、互換性のない変更をするときは、既存リビジョンの `content_json` が新しいスキーマに合わないことがある。既存リビジョンは変更されないが、それを元に新しいリビジョンを作成するときは新しいスキーマで検証されるため、必要に応じて内容を修正する。
- スキーマを再取得してから修正する。呼び出し元が古いスキーマで修正を続けないよう、エラー応答の `details.schema.schemaVersion` と `latestSchemaVersion` を比べる。

## 8. OpenAPI 仕様の編集手順

REST API の仕様 (OpenAPI 3.1) は [openapi/openapi.yaml](../openapi/openapi.yaml) です。API の作成・変更は、仕様を先に更新してから実装します ([5. REST API / MCPツールの構築手順](#5-rest-api--mcpツールの構築手順))。要件: [enviroment.md](../design/requiments/enviroment.md) の ENV-041〜ENV-048、決定の経緯: [ADR-0014](../design/requiments/adr/0014-openapi-schema-import.md)。

### 編集と確認

1. `openapi/openapi.yaml` を VS Code などで直接編集する (専用の編集ツールはない)。パスは kebab-case、JSON のフィールドは camelCase、ステータスとエラー形式は [api-guideline.md](../design/requiments/api-guideline.md) に従う。
2. バックエンドを起動する (`docker compose up -d backend`、または Dev Container で `uvicorn app.main:app --reload --host 0.0.0.0`)。
3. `http://localhost:8000/docs` (Swagger UI) を開き、仕様が読み込まれ、エラー表示がないこと、外部参照のスキーマ (`ArtifactContent` など) が展開されることを確認する。`/docs` は、FastAPI が実装から自動生成する仕様ではなく、`openapi.yaml` (`http://localhost:8000/openapi.yaml`) を表示する。
4. 仕様を反映して実装し、`tests/test_api_conformance.py` で仕様・REST・MCP の一致を確認する ([5. REST API / MCPツールの構築手順](#5-rest-api--mcpツールの構築手順))。

- `openapi/` は、`backend` コンテナに `/openapi` として読み取り専用でマウントされる ([compose/backend.yaml](../compose/backend.yaml))。編集内容は、バックエンドの再起動なしで `/openapi.yaml` に反映される (ファイルを都度読み込む)。
- `/openapi.yaml` と `/docs` は、`/health` と同様に、認証を要求しない運用用のエンドポイントで、OpenAPI の対象外。

### スキーマ取得 API

JSON スキーマテーブルのスキーマは、REST API で取得できます ([7. JSON スキーマの編集手順](#7-json-スキーマの編集手順)の「使うAPI」)。仕様の外部参照には、`schemaJson` 本体だけを返す API (`getSchemaJson`、`getSchemaJsonByKey`) を使います。外部参照として解決できるよう、スキーマ本体から `$id` (`urn:`) を除いて返します (本体内の `#/$defs/...` が `urn:` を基準に解決されるのを避けるため)。スキーマテーブルの内容と、検証に使うスキーマは変わりません。

### JSON スキーマテーブルのスキーマを参照する

`components/schemas` などに、スキーマを取得する URL を `$ref` で書きます。**ホストと版は書きません。**

```yaml
ArtifactContent:
  $ref: /v1/schemas/by-key/sys.artifact/schema-json
```

- ホストを書かないため、参照は、仕様を配信しているホスト (バックエンドの `/openapi.yaml`) を基準に解決される。ローカルと本番で `openapi.yaml` を書き換えない (ENV-047)。
  - ローカル: `http://localhost:8000/openapi.yaml` を配信するローカルのバックエンド。
  - 本番: 本番のバックエンドの `/openapi.yaml`。または `/openapi.yaml` と `/v1/` を同じホストから本番のバックエンドへ中継する配信元。
  - リバースプロキシや CORS の設定は要らない。
- 版を書かないため、常に最新版を参照する。スキーマテーブルに新しい版を登録すると、`openapi.yaml` を変更せずに、参照先が最新版に切り替わる。新しい版は、既存の REST API の呼び出し元に影響しないことを確認してから登録する。環境ごとに登録されている版が異なれば、仕様の内容も環境ごとに異なる。
- 特定の版に固定したいときは、`/v1/schemas/by-key/{schemaKey}/schema-json?version={版}` または `/v1/schemas/{schemaId}/schema-json` を書く。
- 実装 (検証) が使うスキーマは、リクエストで指定する `schemaId` / `schemaKey` であり、仕様の外部参照とは独立している。
