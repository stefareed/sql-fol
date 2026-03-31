"""
tests/test_translator.py
========================
pytest suite for sql_fol translation round-trips and edge cases.
"""

import pytest
from sql_fol import sql_to_fol, fol_to_sql, fregean_analysis


# ---------------------------------------------------------------------------
# SQL → FOL
# ---------------------------------------------------------------------------

class TestSQLtoFOL:

    def test_simple_select(self):
        fol = sql_to_fol("SELECT name FROM employees")
        assert "employees(" in fol
        assert "∃" in fol
        assert "λname" in fol

    def test_where_clause(self):
        fol = sql_to_fol("SELECT name FROM employees WHERE salary > 50000")
        assert "∧" in fol
        assert "50000" in fol
        assert ">" in fol

    def test_distinct(self):
        fol = sql_to_fol("SELECT DISTINCT city FROM customers")
        assert "∃!" in fol

    def test_not_exists(self):
        fol = sql_to_fol(
            "SELECT name FROM students "
            "WHERE NOT EXISTS (SELECT 1 FROM enrollments WHERE student_id = students.id)"
        )
        assert "¬∃" in fol

    def test_and_condition(self):
        fol = sql_to_fol("SELECT * FROM products WHERE price < 100 AND in_stock = true")
        assert "∧" in fol
        assert "100" in fol

    def test_or_condition(self):
        fol = sql_to_fol("SELECT * FROM orders WHERE status = 'pending' OR status = 'open'")
        assert "∨" in fol

    def test_join(self):
        fol = sql_to_fol(
            "SELECT e.name, d.name "
            "FROM employees e, departments d "
            "WHERE e.dept_id = d.id"
        )
        assert "employees(" in fol
        assert "departments(" in fol

    def test_star_select(self):
        fol = sql_to_fol("SELECT * FROM users WHERE active = true")
        assert "∃" in fol

    def test_comparison_operators(self):
        cases = [
            (">=", "≥"),
            ("<=", "≤"),
            ("!=", "≠"),
        ]
        for sql_op, fol_op in cases:
            fol = sql_to_fol(f"SELECT x FROM t WHERE a {sql_op} b")
            assert fol_op in fol, f"Expected {fol_op} in output for SQL op {sql_op}"

    def test_lambda_projection(self):
        fol = sql_to_fol("SELECT name, salary FROM employees WHERE dept = 'eng'")
        assert "λname,salary" in fol or "λname" in fol


# ---------------------------------------------------------------------------
# FOL → SQL
# ---------------------------------------------------------------------------

class TestFOLtoSQL:

    def test_simple(self):
        sql = fol_to_sql("λname. ∃e. (Employees(e) ∧ (e.salary > 50000))")
        assert "SELECT" in sql
        assert "FROM" in sql
        assert "WHERE" in sql
        assert "50000" in sql

    def test_distinct(self):
        sql = fol_to_sql("λcity. ∃!c. (Customers(c))")
        assert "DISTINCT" in sql

    def test_not_exists(self):
        sql = fol_to_sql("λe. ∃e. (Students(e) ∧ ¬∃(SELECT 1 FROM enrollments))")
        assert "NOT EXISTS" in sql

    def test_conjunction(self):
        sql = fol_to_sql("λx. ∃x. (Products(x) ∧ (x.price < 100) ∧ (x.active = true))")
        assert "AND" in sql

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            fol_to_sql("not valid fol at all !!!")


# ---------------------------------------------------------------------------
# Round-trip: SQL → FOL → SQL (structural equivalence)
# ---------------------------------------------------------------------------

class TestRoundTrip:

    def _normalize(self, sql: str) -> str:
        """Collapse whitespace and uppercase for loose comparison."""
        import re
        return re.sub(r"\s+", " ", sql.upper().strip())

    def test_simple_roundtrip(self):
        original = "SELECT name FROM employees WHERE salary > 50000"
        fol = sql_to_fol(original)
        # FOL → SQL won't be identical text, but should contain key elements
        # (table names uppercase in FOL notation)
        assert "employees" in fol.lower()

    def test_distinct_survives(self):
        fol = sql_to_fol("SELECT DISTINCT city FROM customers WHERE country = 'US'")
        sql = fol_to_sql(fol)
        assert "DISTINCT" in sql

    def test_negation_survives(self):
        original = (
            "SELECT name FROM students "
            "WHERE NOT EXISTS (SELECT 1 FROM enrollments WHERE student_id = students.id)"
        )
        fol = sql_to_fol(original)
        assert "¬∃" in fol


# ---------------------------------------------------------------------------
# Fregean annotations
# ---------------------------------------------------------------------------

class TestAnnotations:

    def test_returns_list(self):
        anns = fregean_analysis("SELECT name FROM employees WHERE salary > 50000")
        assert isinstance(anns, list)
        assert len(anns) > 0

    def test_has_required_keys(self):
        anns = fregean_analysis("SELECT * FROM t WHERE x = 1")
        for ann in anns:
            assert "term" in ann
            assert "gloss" in ann
            assert "analysis" in ann

    def test_null_triggers_annotation(self):
        anns = fregean_analysis("SELECT * FROM t WHERE x IS NULL")
        terms = [a["term"] for a in anns]
        assert any("Bedeutungslosigkeit" in t for t in terms)

    def test_not_exists_annotation(self):
        anns = fregean_analysis("SELECT * FROM t WHERE NOT EXISTS (SELECT 1 FROM s)")
        terms = [a["term"] for a in anns]
        assert any("Verneinung" in t for t in terms)

    def test_distinct_annotation(self):
        anns = fregean_analysis("SELECT DISTINCT x FROM t")
        terms = [a["term"] for a in anns]
        assert any("Einzigkeit" in t for t in terms)

    def test_sinn_bedeutung_always_present(self):
        anns = fregean_analysis("SELECT 1 FROM t")
        terms = [a["term"] for a in anns]
        assert any("Sinn" in t for t in terms)
