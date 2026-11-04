"""Container runtime + restricted caller's rights for PROD and DEV.

Covers the automated half of the cutover test matrix (A1-A7, plus B1 checked
statically against snowflake.yml). Nothing here talks to Snowflake: the
caller's-rights setup block and the viewer lookup are executed out of
streamlit_app.py against a fake `st`.
"""
import ast
import re
import sys
import types
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

APP_SRC = (ROOT / "streamlit_app.py").read_text()


class _State(dict):
    """st.session_state: dict with attribute access."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def __setattr__(self, name, value):
        self[name] = value


class _Cursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql):
        self.log.append(sql)


class FakeConn:
    def __init__(self, user="VIEWER"):
        self.user = user
        self.executed = []
        self.queries = []

    def cursor(self):
        return _Cursor(self.executed)

    def query(self, sql, ttl=None):
        import pandas as pd
        self.queries.append(sql)
        return pd.DataFrame({"U": [self.user]})


def _fake_st(callers_rights):
    """`callers_rights` is a FakeConn, or an Exception to raise."""
    st = types.SimpleNamespace(session_state=_State())
    owner = FakeConn(user="APP_OWNER")

    def connection(name):
        if name == "snowflake":
            return owner
        if name == "snowflake-callers-rights":
            if isinstance(callers_rights, Exception):
                raise callers_rights
            return callers_rights
        raise AssertionError(name)

    st.connection = connection
    return st, owner


def _setup_block():
    """Source of streamlit_app.py from the owner connection up to the first
    sidebar default, i.e. the connection setup only."""
    start = APP_SRC.index('if "conn" not in st.session_state:')
    end = APP_SRC.index('if "_ui_region" not in st.session_state:')
    return APP_SRC[start:end]


def _run_setup(callers_rights):
    st, owner = _fake_st(callers_rights)
    exec(_setup_block(), {"st": st})
    return st, owner


def _current_user_fn(st):
    tree = ast.parse(APP_SRC)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_current_snowflake_user")
    ns = {"st": st}
    exec(compile(ast.Module([fn], []), "streamlit_app.py", "exec"), ns)
    return ns["_current_snowflake_user"]


# A1 -----------------------------------------------------------------------
def test_a1_callers_rights_unavailable_falls_back():
    st, owner = _run_setup(RuntimeError("only supported on container runtime"))
    s = st.session_state
    assert s.conn is owner
    assert s._callers_rights_conn is None
    assert s.caller_conn is None
    assert "container runtime" in s.caller_conn_error
    # Pages pick the owner connection when caller's rights is missing.
    assert (s.get("_callers_rights_conn") or s.conn) is owner


# A2 -----------------------------------------------------------------------
def test_a2_single_callers_rights_conn_with_secondary_roles():
    cr = FakeConn()
    st, _ = _run_setup(cr)
    s = st.session_state
    assert s._callers_rights_conn is cr
    assert s.caller_conn is cr, "workshop must reuse the same connection"
    assert cr.executed == ["USE SECONDARY ROLES ALL"]
    assert "caller_conn_error" not in s


def test_a2_setup_is_not_env_gated():
    """Caller's rights must be created on every env, not only DEV, and at the
    top of the script (the token is only valid for two minutes)."""
    block = _setup_block()
    assert "get_env" not in block
    assert APP_SRC.index('st.connection("snowflake-callers-rights")') < APP_SRC.index("st.navigation(")


def test_a2_setup_runs_once_per_session():
    cr = FakeConn()
    st, _ = _run_setup(cr)
    exec(_setup_block(), {"st": st})
    assert cr.executed == ["USE SECONDARY ROLES ALL"]


# A3 -----------------------------------------------------------------------
def test_a3_viewer_comes_from_callers_rights_and_is_memoized():
    cr = FakeConn(user="sdogra")
    st, owner = _run_setup(cr)
    fn = _current_user_fn(st)
    assert fn(owner) == "SDOGRA"
    assert fn(owner) == "SDOGRA"
    assert len(cr.queries) == 1, "memoized in session_state"
    assert owner.queries == [], "owner connection would return the app OWNER"


def test_a3_viewer_falls_back_to_owner_connection():
    st, owner = _run_setup(RuntimeError("warehouse runtime"))
    owner.user = "localdev"
    assert _current_user_fn(st)(owner) == "LOCALDEV"


def test_a3_viewer_lookup_not_globally_cached():
    """st.cache_* is shared across viewers on container runtime."""
    tree = ast.parse(APP_SRC)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_current_snowflake_user")
    assert not fn.decorator_list


def test_a3_executive_email_uses_resolved_viewer():
    src = (ROOT / "app_pages" / "executive_email.py").read_text()
    assert 'st.session_state.get("_current_user_upper")' in src


# A4 -----------------------------------------------------------------------
_CALLER_NAMES = ("_callers_rights_conn", "caller_conn", "data_conn", "snowflake-callers-rights")


def _cached_functions():
    for path in list((ROOT / "app_pages").glob("*.py")) + list((ROOT / "utils").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                target = dec.func if isinstance(dec, ast.Call) else dec
                name = ast.unparse(target)
                if name.endswith(("cache_data", "cache_resource", "lru_cache", "cache")):
                    yield path, node, dec


def test_a4_no_globally_cached_function_touches_callers_rights():
    offenders = []
    for path, node, dec in _cached_functions():
        body = ast.unparse(node)
        if not any(n in body for n in _CALLER_NAMES):
            continue
        session_scoped = isinstance(dec, ast.Call) and any(
            kw.arg == "scope" and getattr(kw.value, "value", None) == "session"
            for kw in dec.keywords)
        if not session_scoped:
            offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {node.name}")
    assert not offenders, f"cache these with scope='session' or not at all: {offenders}"


def test_a4_acq_theatre_reads_are_uncached():
    src = (ROOT / "app_pages" / "acquisition_opportunities.py").read_text()
    assert "_callers_rights_conn" in src
    for call in re.findall(r"conn\.query\([^)]*\)", src, flags=re.S):
        if "params=" in call:
            assert "ttl=0" in call, call


# A5 -----------------------------------------------------------------------
# Allowed: the PROD dashboard link in the exec email prompt, and COCO_AGENT,
# which only exists in the PROD schema.
_PROD_LITERAL_ALLOW = ("streamlit-apps/TEMP.COCO_PARTNER_ADOPTION.", "TEMP.COCO_PARTNER_ADOPTION.COCO_AGENT")


def test_a5_no_hardcoded_prod_schema_in_sql():
    hits = []
    for path in [ROOT / "streamlit_app.py", *(ROOT / "app_pages").glob("*.py"), *(ROOT / "utils").rglob("*.py")]:
        if path.name == "config.py":
            continue
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "TEMP.COCO_PARTNER_ADOPTION." in line and not any(a in line for a in _PROD_LITERAL_ALLOW):
                hits.append(f"{path.relative_to(ROOT)}:{i}")
    assert not hits, f"use get_schema(): {hits}"


@pytest.mark.parametrize("env,schema", [("dev", "TEMP.COCO_PARTNER_ADOPTION_DEV"),
                                         ("prod", "TEMP.COCO_PARTNER_ADOPTION")])
def test_a5_get_schema_routes_by_env(monkeypatch, env, schema):
    from utils import config
    monkeypatch.setenv("APP_ENV", env)
    with mock.patch.dict(sys.modules, {"streamlit": mock.MagicMock(secrets={})}):
        assert config.get_schema() == schema


# A6 -----------------------------------------------------------------------
def test_a6_rest_parses_text_and_detects_expired_token():
    from utils.cortex_rest_helpers import _extract_and_check
    ok = {"content": [{"type": "text", "text": " hello "}, {"type": "tool_use"}]}
    assert _extract_and_check(ok) == "hello"
    with pytest.raises(RuntimeError, match="390112"):
        _extract_and_check({"code": "390112", "message": "expired"})
    with pytest.raises(RuntimeError, match="390112"):
        _extract_and_check('{"error": {"code": "390112"}}')


# A7 -----------------------------------------------------------------------
def _exec_email_users():
    tree = ast.parse(APP_SRC)
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and getattr(n.targets[0], "id", None) == "EXEC_EMAIL_USERS")
    return ast.literal_eval(node.value)


@pytest.mark.parametrize("viewer,allowed", [("SDOGRA", True), ("RMAKKENA", True),
                                            ("SOMEONE_ELSE", False), ("", False),
                                            ("APP_OWNER", False)])
def test_a7_exec_email_allowlist(viewer, allowed):
    assert (viewer in _exec_email_users()) is allowed


# B1 (static) --------------------------------------------------------------
def _entity(name):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((ROOT / "snowflake.yml").read_text())["entities"][name]


@pytest.mark.parametrize("name", ["coco_usecase_insights", "coco_usecase_insights_cr",
                                  "coco_usecase_insights_dev"])
def test_b1_entities_use_container_runtime(name):
    e = _entity(name)
    assert e["runtime_name"] == "SYSTEM$ST_CONTAINER_RUNTIME_PY3_11"
    assert e["compute_pool"] == "STREAMLIT_DEDICATED_POOL_L"
    assert "PYPI_ACCESS_INTEGRATION" in e["external_access_integrations"]
    assert "pyproject.toml" in e["artifacts"]
    assert "environment.yml" not in e["artifacts"], "conda env is warehouse-runtime only"


def test_b1_rehearsal_app_targets_prod_schema():
    e = _entity("coco_usecase_insights_cr")["identifier"]
    assert (e["database"], e["schema"]) == ("TEMP", "COCO_PARTNER_ADOPTION")
    assert e["name"] != "COCO_USECASE_INSIGHTS"


def test_streamlit_version_supports_callers_rights():
    """Restricted caller's rights require Streamlit >= 1.53.1."""
    deps = (ROOT / "pyproject.toml").read_text()
    m = re.search(r'streamlit\[snowflake\]>=(\d+)\.(\d+)', deps)
    assert m and (int(m[1]), int(m[2])) >= (1, 54)
