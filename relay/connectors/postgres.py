"""Optional Postgres connector, e.g. for tasks that need to inspect or seed a database
as part of the build. Requires `pip install relay-oss[postgres]`."""


def run_query(dsn: str, query: str, params=None):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:
        raise RuntimeError(
            "The 'psycopg2-binary' package is required for the Postgres connector. "
            "Install with: pip install relay-oss[postgres]"
        ) from e
    with psycopg2.connect(dsn) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            if cur.description:
                return [dict(row) for row in cur.fetchall()]
            conn.commit()
            return {"rowcount": cur.rowcount}
