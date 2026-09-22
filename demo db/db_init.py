import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()


def main():
    sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
    with psycopg.connect() as conn:
        conn.execute(sql)
    print("Database schema ready: pgvector, documents, versions, pages, chunks")


if __name__ == "__main__":
    main()
