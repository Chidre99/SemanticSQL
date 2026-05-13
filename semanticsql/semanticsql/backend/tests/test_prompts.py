from app.llm.prompts import extract_sql


def test_extracts_fenced_sql():
    raw = "Here you go:\n```sql\nSELECT 1;\n```\nThanks!"
    assert extract_sql(raw).strip() == "SELECT 1;"


def test_extracts_unfenced_sql():
    raw = "SELECT id FROM users WHERE id = 1"
    sql = extract_sql(raw)
    assert sql.upper().startswith("SELECT")
    assert sql.endswith(";")


def test_handles_no_language_hint():
    raw = "```\nSELECT 42;\n```"
    assert extract_sql(raw).strip() == "SELECT 42;"


def test_takes_first_fenced_block():
    raw = "```sql\nSELECT 1;\n```\n```sql\nSELECT 2;\n```"
    assert "1" in extract_sql(raw)
