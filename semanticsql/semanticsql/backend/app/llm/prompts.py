"""Prompt construction.

The system prompt sets policy + output format. Few-shots demonstrate the
desired shape — including one refusal and one self-correction shot, so
the model sees what those look like. The user message is built from the
retrieved schema chunks plus the natural-language question.

We deliberately keep prompts short and concrete. Long, hedging instructions
hurt small models more than they help.
"""
from __future__ import annotations

from textwrap import dedent

from app.rag.types import Chunk

SYSTEM_PROMPT = dedent("""\
    You are SemanticSQL, an expert text-to-SQL assistant.

    Rules — non-negotiable:
    1. Output exactly ONE SQL statement, wrapped in a ```sql ... ``` fence. No prose before or after.
    2. SELECT statements only. Never emit INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE, COPY, or any DDL/DML.
    3. Use only tables and columns that appear in the SCHEMA CONTEXT block below. Do not invent identifiers.
    4. Match the requested SQL DIALECT exactly. Postgres ≠ MySQL — date functions, quoting, and string concat differ.
    5. If the question cannot be answered from the available schema, respond with exactly: ```sql\nSELECT 'cannot answer from available schema' AS error;\n```
    6. Prefer explicit JOINs over comma joins. Always qualify columns with their table alias when more than one table is involved.
    7. For "top N" / "most" / "largest" use ORDER BY ... DESC LIMIT N.
""")


# Few-shots: (database, question, sql). Chosen to cover join, aggregation,
# date filter, CASE, multi-table join, dialect-specific quirks, and refusal.
# IMPORTANT: none of these questions appear in the eval set.
FEW_SHOTS: list[tuple[str, str, str]] = [
    (
        "pagila",
        "How many films are rated PG-13?",
        "SELECT COUNT(*) AS film_count FROM film WHERE rating = 'PG-13';",
    ),
    (
        "pagila",
        "What is the average rental rate per category?",
        dedent("""\
            SELECT c.name AS category, AVG(f.rental_rate) AS avg_rental_rate
            FROM   category   c
            JOIN   film_category fc ON fc.category_id = c.category_id
            JOIN   film       f    ON f.film_id     = fc.film_id
            GROUP  BY c.name
            ORDER  BY avg_rental_rate DESC;"""),
    ),
    (
        "pagila",
        "List the 5 customers who spent the most in 2022.",
        dedent("""\
            SELECT c.customer_id, c.first_name, c.last_name, SUM(p.amount) AS total_spent
            FROM   customer c
            JOIN   payment  p ON p.customer_id = c.customer_id
            WHERE  EXTRACT(YEAR FROM p.payment_date) = 2022
            GROUP  BY c.customer_id, c.first_name, c.last_name
            ORDER  BY total_spent DESC
            LIMIT  5;"""),
    ),
    (
        "pagila",
        "For each film rating, what fraction of films are longer than 2 hours? Express as a percent.",
        dedent("""\
            SELECT rating,
                   ROUND(100.0 * SUM(CASE WHEN length > 120 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_over_2h
            FROM   film
            GROUP  BY rating
            ORDER  BY rating;"""),
    ),
    (
        "chinook",
        "Top 10 best-selling tracks by total revenue.",
        dedent("""\
            SELECT t.TrackId, t.Name, SUM(il.UnitPrice * il.Quantity) AS revenue
            FROM   Track        t
            JOIN   InvoiceLine  il ON il.TrackId = t.TrackId
            GROUP  BY t.TrackId, t.Name
            ORDER  BY revenue DESC
            LIMIT  10;"""),
    ),
    (
        "chinook",
        "Average track length in minutes by genre.",
        dedent("""\
            SELECT g.Name AS genre, AVG(t.Milliseconds) / 60000.0 AS avg_minutes
            FROM   Genre g
            JOIN   Track t ON t.GenreId = g.GenreId
            GROUP  BY g.Name
            ORDER  BY avg_minutes DESC;"""),
    ),
    (
        "chinook",
        "Total revenue per year.",
        dedent("""\
            SELECT YEAR(InvoiceDate) AS year, SUM(Total) AS revenue
            FROM   Invoice
            GROUP  BY YEAR(InvoiceDate)
            ORDER  BY year;"""),
    ),
    # Refusal: question cannot be answered from schema
    (
        "pagila",
        "What is the IMDb score of each film?",
        "SELECT 'cannot answer from available schema' AS error;",
    ),
]


def _format_chunks(chunks: list[Chunk]) -> str:
    """Compact schema context block."""
    if not chunks:
        return "(no schema context retrieved)"
    return "\n\n".join(c.text for c in chunks)


def _format_fewshots(database: str) -> str:
    """Pick a few-shot subset relevant to the active database, plus the refusal."""
    relevant = [(db, q, s) for db, q, s in FEW_SHOTS if db == database]
    # Always include the refusal example regardless of DB
    refusal = [(db, q, s) for db, q, s in FEW_SHOTS if "cannot answer" in s.lower()]
    chosen = relevant + [r for r in refusal if r not in relevant]
    parts = []
    for _, q, s in chosen:
        parts.append(f"Question: {q}\n```sql\n{s.strip()}\n```")
    return "\n\n".join(parts)


def build_prompt(
    question: str,
    schema_chunks: list[Chunk],
    database: str,
    dialect: str,
    error_feedback: str | None = None,
) -> list[dict[str, str]]:
    """Assemble the chat-completions message list.

    Args:
        question: user's natural-language question.
        schema_chunks: ordered retrieval results (highest similarity first).
        database: db identifier — used to filter few-shots.
        dialect: 'postgres' or 'mysql' — included in user message.
        error_feedback: when set, this is a retry; the previous error report
            is appended so the model can self-correct.

    Returns: messages array suitable for chat.completions.create.
    """
    schema_block = _format_chunks(schema_chunks)
    fewshots = _format_fewshots(database)

    user_msg = dedent(f"""\
        SQL DIALECT: {dialect}
        DATABASE: {database}

        SCHEMA CONTEXT (use only these tables and columns):
        --------
        {schema_block}
        --------

        EXAMPLES:
        {fewshots}

        Question: {question}
    """).strip()

    if error_feedback:
        user_msg += dedent(f"""

            Your previous attempt failed validation. Errors:
            {error_feedback}

            Produce a corrected SQL statement that addresses every error above.
            Output only the SQL fence — no commentary.""")

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]


def extract_sql(raw: str) -> str:
    """Pull the SQL out of a ```sql fence, falling back to the whole string.

    Small models occasionally drop the fence or repeat the query twice.
    We take the first fenced block; if none, the first SELECT statement.
    """
    import re

    fenced = re.findall(r"```(?:sql)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced[0].strip().rstrip(";") + ";"

    # No fence — grab from first SELECT to end / first semicolon
    m = re.search(r"\bSELECT\b.*?(?:;|$)", raw, flags=re.DOTALL | re.IGNORECASE)
    if m:
        sql = m.group(0).strip().rstrip(";") + ";"
        return sql

    return raw.strip()
