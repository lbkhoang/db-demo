import psycopg


async def database_status() -> dict:
    async with await psycopg.AsyncConnection.connect(connect_timeout=3) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("vector extension is missing")
            return {"database": "ok", "pgvector": row[0]}
