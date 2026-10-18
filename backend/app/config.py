import os
from pathlib import Path

from sqlalchemy.engine import URL

BACKEND_DIR = Path(__file__).resolve().parents[1]
# コンテナでは backend/ だけが /app にマウントされるため、openapi/ は /openapi にマウントする
OPENAPI_FILE = Path(os.environ.get("OPENAPI_FILE", BACKEND_DIR.parent / "openapi" / "openapi.yaml"))
DEFAULT_SEED_DIR = BACKEND_DIR / "seed"


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


DATABASE_URL = _database_url()
