import os
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SEED_DIR = BACKEND_DIR / "seed"
DEFAULT_LOCALDATA_DIR = BACKEND_DIR / "localdata"

_DB_VARIABLES = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


def store_mode(env: Mapping[str, str] = os.environ) -> str:
    """データの保存先を返す。

    DB の接続情報 (DATABASE_URL または POSTGRES_*) が .env などで設定されていれば "postgres"、
    1つも設定されていなければ "file" (backend/localdata の JSON ファイル) とする。
    一部だけが設定されている場合は設定ミスとして "postgres" とし、不足を _database_url が報告する。
    """
    if env.get("DATABASE_URL") or any(env.get(name) for name in _DB_VARIABLES):
        return "postgres"
    return "file"


def localdata_dir(env: Mapping[str, str] = os.environ) -> Path:
    """ファイルストアの保存先。LOCALDATA_DIR で変更できる (テスト用)。"""
    return Path(env["LOCALDATA_DIR"]) if env.get("LOCALDATA_DIR") else DEFAULT_LOCALDATA_DIR


def _database_url() -> str | URL:
    """接続URLを返す。DATABASE_URL があればそれを優先し、なければ POSTGRES_* から組み立てる。

    パスワードに記号が含まれても壊れないよう、URL文字列ではなく URL オブジェクトで組み立てる。
    """
    if url := os.environ.get("DATABASE_URL"):
        return url
    try:
        return URL.create(
            "postgresql+psycopg",
            username=os.environ["POSTGRES_USER"],
            password=os.environ["POSTGRES_PASSWORD"],
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            database=os.environ["POSTGRES_DB"],
        )
    except KeyError as e:
        raise RuntimeError(
            f"環境変数 {e.args[0]} が未設定です。.env.example を .env にコピーして値を設定してください"
        ) from None


STORE_MODE = store_mode()
LOCALDATA_DIR = localdata_dir()
# ファイルストアでは PostgreSQL に接続しない
DATABASE_URL = _database_url() if STORE_MODE == "postgres" else None
