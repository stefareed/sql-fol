"""
fol_to_sql.py
=============
Translates a FOL formula (in the subset produced by sql_to_fol) back into SQL.

Expected input form
-------------------
  λ<proj>. ∃[!]<vars>. (<table_preds> ∧ <conditions> ∧ ¬∃(<subquery>))

e.g.
  λname. ∃e. (employees(e) ∧ (e.salary > 50000))
  λe,d. ∃e,d. (employees(e) ∧ departments(d) ∧ (e.dept_id = d.id))
  λe. ∃e. (employees(e) ∧ ¬∃(SELECT 1 FROM ...))
"""

from __future__ import annotations
import re
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Top-level ∧ splitter (respects parenthesis depth)
# ---------------------------------------------------------------------------

def _split_conjuncts(s: str, sep: str = "∧") -> List[str]:
    parts, depth, cur = [], 0, ""
    i = 0
    while i < len(s):
        if s[i] in "([": depth += 1
        elif s[i] in ")]": depth -= 1
        if depth == 0 and s[i:i+len(sep)] == sep:
            parts.append(cur.strip()); cur = ""; i += len(sep); continue
        cur += s[i]; i += 1
    if cur.strip(): parts.append(cur.strip())
    return parts


# ---------------------------------------------------------------------------
# FOL expression → SQL expression
# ---------------------------------------------------------------------------

_FOL_TO_SQL_OPS = {
    "∧": "AND", "∨": "OR", "¬": "NOT",
    "≥": ">=",  "≤": "<=", "≠": "!=", "∈": "IN",
}

def _fol_expr_to_sql(expr: str) -> str:
    expr = expr.strip().lstrip("(").rstrip(")")
    for fol_op, sql_op in _FOL_TO_SQL_OPS.items():
        expr = expr.replace(fol_op, sql_op)
    return expr.strip()


# ---------------------------------------------------------------------------
# Main translator class
# ---------------------------------------------------------------------------

class FOLtoSQL:
    """
    Translates a FOL formula string (in the form produced by SQLtoFOL)
    back into a SQL SELECT statement.

    Example
    -------
    >>> t = FOLtoSQL()
    >>> t.translate("λname. ∃e. (employees(e) ∧ (e.salary > 50000))")
    'SELECT name\\nFROM employees AS e\\nWHERE e.salary > 50000;'
    """

    def translate(self, fol: str) -> str:
        fol = fol.strip()

        # 1. Extract λ projection prefix
        proj_match = re.match(r"^λ([\w,*]+)\.\s*(.*)", fol, re.DOTALL)
        if proj_match:
            proj_str = proj_match.group(1)
            body     = proj_match.group(2).strip()
        else:
            proj_str = "*"
            body     = fol

        # 2. Extract quantifier ∃[!]vars. (...)
        quant_match = re.match(
            r"^(∃!?)([\w,]+)\.\s*\((.+)\)\s*$", body, re.DOTALL
        )
        if not quant_match:
            # Try without outer parens (lenient)
            quant_match = re.match(r"^(∃!?)([\w,]+)\.\s*(.*)", body, re.DOTALL)
            if not quant_match:
                raise ValueError(
                    "Cannot parse FOL structure. Expected: λ<vars>. ∃<vars>. (<body>)"
                )
            distinct = "!" in quant_match.group(1)
            inner    = quant_match.group(3)
        else:
            distinct = "!" in quant_match.group(1)
            inner    = quant_match.group(3)

        # 3. Split body into conjuncts
        conjuncts = _split_conjuncts(inner)

        tables:     List[Tuple[str, str]] = []
        conditions: List[str]             = []
        not_exists: List[str]             = []

        for conj in conjuncts:
            conj = conj.strip()
            if not conj:
                continue

            # Table predicate: UpperWord(var)
            tbl_m = re.match(r"^([A-Z][A-Za-z_0-9]*)\((\w+)\)$", conj)
            if tbl_m:
                tables.append((tbl_m.group(1), tbl_m.group(2)))
                continue

            # ¬∃(subquery)
            neg_m = re.match(r"^¬∃\((.+)\)$", conj, re.DOTALL)
            if neg_m:
                not_exists.append(neg_m.group(1).strip())
                continue

            # Regular condition
            conditions.append(_fol_expr_to_sql(conj))

        # 4. Build SQL
        if not tables:
            raise ValueError("No table predicates found in FOL body.")

        from_parts = [
            f"{tbl} AS {alias}" if tbl != alias else tbl
            for tbl, alias in tables
        ]
        from_clause = ", ".join(from_parts)

        distinct_kw = "DISTINCT " if distinct else ""
        select_cols = "*" if proj_str == ",".join(v for _, v in tables) else proj_str

        sql = f"SELECT {distinct_kw}{select_cols}\nFROM {from_clause}"

        all_conditions = list(conditions)
        for ne in not_exists:
            all_conditions.append(
                f"NOT EXISTS (\n  {ne}\n)"
            )

        if all_conditions:
            sql += "\nWHERE " + "\n  AND ".join(all_conditions)

        return sql + ";"


def fol_to_sql(fol: str) -> str:
    """Convenience wrapper: FOL string → SQL string."""
    return FOLtoSQL().translate(fol)
