from app.db.introspect import SchemaCache
from app.validation.identifiers import check
from app.validation.parser import parse


def _cache():
    return SchemaCache(
        schemas={
            "pagila": {
                "film":     {"film_id", "title", "rating", "length", "rental_rate"},
                "customer": {"customer_id", "first_name", "last_name"},
                "payment":  {"payment_id", "customer_id", "amount", "payment_date"},
            }
        }
    )


def _parse(sql: str):
    p = parse(sql, "postgres")
    assert p.ok, p.error
    return p.ast


def test_known_identifiers_pass():
    ast = _parse("SELECT title FROM film WHERE rating = 'PG-13'")
    r = check(ast, "pagila", _cache())
    assert r.ok, r.issues


def test_unknown_table_detected():
    ast = _parse("SELECT * FROM flim")
    r = check(ast, "pagila", _cache())
    assert not r.ok
    issue = r.issues[0]
    assert issue.kind == "unknown_table"
    assert "film" in issue.did_you_mean


def test_unknown_column_with_suggestion():
    ast = _parse("SELECT titel FROM film")
    r = check(ast, "pagila", _cache())
    assert not r.ok
    issue = r.issues[0]
    assert issue.kind == "unknown_column"
    assert "title" in issue.did_you_mean


def test_qualified_columns_resolved_via_alias():
    ast = _parse(
        """
        SELECT c.first_name, SUM(p.amount)
        FROM   customer c
        JOIN   payment  p ON p.customer_id = c.customer_id
        GROUP  BY c.first_name
        """
    )
    r = check(ast, "pagila", _cache())
    assert r.ok, r.issues


def test_unknown_column_on_qualified():
    ast = _parse("SELECT c.middle_name FROM customer c")
    r = check(ast, "pagila", _cache())
    assert not r.ok
    assert r.issues[0].kind == "unknown_column"
    assert r.issues[0].table == "customer"
