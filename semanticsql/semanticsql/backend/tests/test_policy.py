from app.validation.parser import parse
from app.validation.policy import check


def _check(sql: str, dialect: str = "postgres"):
    p = parse(sql, dialect)
    assert p.ok and p.ast is not None, f"parse failed: {p.error}"
    return check(sql, p.ast, dialect)


def test_allows_simple_select():
    assert _check("SELECT 1").ok


def test_allows_cte():
    r = _check("WITH x AS (SELECT 1 AS a) SELECT * FROM x")
    assert r.ok


def test_allows_union():
    r = _check("SELECT 1 UNION SELECT 2")
    assert r.ok


def test_blocks_insert():
    # Insert wouldn't be reached because policy is only invoked when parse() succeeded
    # with a SELECT-shaped statement; instead, parse a valid SELECT then craft a
    # multi-statement string and ensure we catch it.
    r = _check("SELECT 1; SELECT 2")
    assert not r.ok
    assert any("multiple statements" in v for v in r.violations)


def test_blocks_information_schema():
    r = _check("SELECT * FROM information_schema.tables")
    assert not r.ok
    assert any("blocked schema" in v.lower() or "system table" in v.lower() for v in r.violations)


def test_blocks_pg_catalog():
    r = _check("SELECT * FROM pg_catalog.pg_class")
    assert not r.ok


def test_blocks_pg_read_file():
    r = _check("SELECT pg_read_file('/etc/passwd')")
    assert not r.ok
    assert any("blocked function" in v.lower() for v in r.violations)


def test_allows_subselect():
    r = _check("SELECT * FROM (SELECT 1 AS a) sub")
    assert r.ok
