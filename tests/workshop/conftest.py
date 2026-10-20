import pandas as pd


class FakeConn:
    """Mimics st.connection('snowflake') .query(sql, ttl=...) for unit tests."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.queries = []

    def query(self, sql, ttl=None):
        self.queries.append(sql)
        for needle, df in self.responses.items():
            if needle in sql:
                return df
        return pd.DataFrame()

    def cursor(self):
        """Mimics conn.cursor() context manager used for DDL (see utils/judge_cache.ensure_table)."""
        conn = self

        class _Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql):
                conn.queries.append(sql)

        return _Cur()
