from app.validation.parser import parse


def test_parses_valid_postgres():
    r = parse("SELECT 1", "postgres")
    assert r.ok and r.ast is not None


def test_parses_valid_mysql():
    r = parse("SELECT 1 FROM dual", "mysql")
    assert r.ok and r.ast is not None


def test_rejects_garbage():
    r = parse("not a sql statement at all", "postgres")
    assert not r.ok and r.error is not None


def test_rejects_empty():
    r = parse("", "postgres")
    assert not r.ok


def test_handles_complex_query():
    sql = """
    SELECT c.customer_id, c.first_name, SUM(p.amount) AS total
    FROM   customer c
    JOIN   payment  p ON p.customer_id = c.customer_id
    WHERE  EXTRACT(YEAR FROM p.payment_date) = 2022
    GROUP  BY c.customer_id, c.first_name
    ORDER  BY total DESC
    LIMIT  5
    """
    r = parse(sql, "postgres")
    assert r.ok
