import os

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://idb:idbIDB108@localhost:5432/IDB")
