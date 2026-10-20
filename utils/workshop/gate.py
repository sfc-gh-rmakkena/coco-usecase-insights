"""Internal account eligibility + policy-safe A360 signals. Never rendered."""
from .compliance import normalize_company, sql_quote

LISTED_SQL = "SELECT COMPANY_NAME FROM SNOWHOUSE.IT.RAW_GOOGLE_SHEETS.TOP_SNOWFLAKE_COMPANIES"
BIG_TIER_MIN_ACTIVE_USERS = 25


def load_listed_names(conn) -> frozenset:
    df = conn.query(LISTED_SQL, ttl=3600)
    names = df["COMPANY_NAME"].tolist() if "COMPANY_NAME" in df.columns else []
    return frozenset(n for n in (normalize_company(x) for x in names) if n)


def is_listed(account: str, listed: frozenset) -> bool:
    n = normalize_company(account)
    return bool(n) and n in listed


def usage_tier(active_users) -> str:
    if active_users is None or active_users != active_users:  # None / NaN
        return "No"
    n = int(active_users or 0)
    if n >= BIG_TIER_MIN_ACTIVE_USERS:
        return "Big"
    return "Low" if n > 0 else "No"


def _in_list(accounts) -> str:
    return ", ".join("'" + sql_quote(a.upper()) + "'" for a in sorted(set(accounts)) if a)


def fetch_a360_context(conn, accounts: list) -> dict:
    """{ACCOUNT_UPPER: {usage_tier, surfaces, enablement_needed, dominant_maturity}} — tiers/flags only."""
    in_list = _in_list(accounts)
    if not in_list:
        return {}
    usage = conn.query(f"""
        SELECT UPPER(SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_UPPER,
               SUM(ACTIVE_USERS) AS ACTIVE_USERS, SUM(ANY_UI_USERS) AS ANY_UI_USERS,
               SUM(ANY_CLI_DESKTOP_USERS) AS ANY_CLI_DESKTOP_USERS,
               BOOLOR_AGG(IS_COCO_BLOCKED) AS IS_COCO_BLOCKED
        FROM SALES.REPORTING.COCO_ACCOUNT_COCO_USAGE
        WHERE IS_YESTERDAY AND UPPER(SALESFORCE_ACCOUNT_NAME) IN ({in_list})
        GROUP BY 1""", ttl=3600)
    maturity = conn.query(f"""
        SELECT ACCOUNT_UPPER, USER_MATURITY FROM (
          SELECT UPPER(SALESFORCE_ACCOUNT_NAME) AS ACCOUNT_UPPER, USER_MATURITY,
                 ROW_NUMBER() OVER (PARTITION BY UPPER(SALESFORCE_ACCOUNT_NAME) ORDER BY COUNT(*) DESC) AS RN
          FROM SALES.REPORTING.COCO_USER_MATURITY_SNAPSHOT
          WHERE DS = (SELECT MAX(DS) FROM SALES.REPORTING.COCO_USER_MATURITY_SNAPSHOT)
            AND UPPER(SALESFORCE_ACCOUNT_NAME) IN ({in_list}) AND USER_MATURITY IS NOT NULL
          GROUP BY 1, 2) WHERE RN = 1""", ttl=3600)
    mat = dict(zip(maturity.get("ACCOUNT_UPPER", []), maturity.get("USER_MATURITY", [])))
    out = {}
    for _, r in usage.iterrows():
        surfaces = (["Snowsight"] if (r["ANY_UI_USERS"] or 0) > 0 else []) + \
                   (["CLI/Desktop"] if (r["ANY_CLI_DESKTOP_USERS"] or 0) > 0 else [])
        out[r["ACCOUNT_UPPER"]] = {"usage_tier": usage_tier(r["ACTIVE_USERS"]), "surfaces": surfaces,
                                   "enablement_needed": bool(r["IS_COCO_BLOCKED"]),
                                   "dominant_maturity": mat.get(r["ACCOUNT_UPPER"], "")}
    return out
