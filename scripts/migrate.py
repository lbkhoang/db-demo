from hashlib import sha256
from pathlib import Path

import psycopg


def main():
    with psycopg.connect(connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(728401)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                name text PRIMARY KEY,
                checksum text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        for path in sorted(Path("migrations").glob("*.sql")):
            sql = path.read_text(encoding="utf-8")
            digest = sha256(sql.encode()).hexdigest()
            row = conn.execute("SELECT checksum FROM schema_migrations WHERE name = %s", (path.name,)).fetchone()
            if row:
                if row[0] != digest:
                    raise RuntimeError(f"Applied migration changed: {path.name}")
                continue
            conn.execute(sql)
            conn.execute("INSERT INTO schema_migrations(name, checksum) VALUES (%s, %s)", (path.name, digest))
            print(f"Applied {path.name}")


if __name__ == "__main__":
    main()
