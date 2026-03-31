"""
sql_to_fol.py
=============
Translates SQL SELECT statements into First-Order Logic (FOL) formulae
with Fregean semantic annotations.

Fregean mapping
---------------
  Table name      → Begriff (concept predicate)   R(x)
  Row / tuple     → Gegenstand (object)            x
  WHERE clause    → Merkmal (feature predicate)    ∧ φ(x)
  JOIN condition  → shared variable               R(x) ∧ S(x)
  NOT EXISTS      → negated existential           ¬∃y. φ(y)
  DISTINCT        → unique existential            ∃!
  SELECT cols     → λ-abstraction                 λc₁,c₂.

Limitations
-----------
  - GROUP BY / HAVING / window functions not yet supported
  - For production use, swap the hand-rolled tokenizer for sqlglot:
      import sqlglot; ast = sqlglot.parse_one(sql)
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# AST nodes
# ---------------------------------------------------------------------------

@dataclass
class Atom:
    value: str

@dataclass
class BinOp:
    op: str
    left:  "Expr"
    right: "Expr"

@dataclass
class UnaryOp:
    op: str
    operand: "Expr"

Expr = Union[Atom, BinOp, UnaryOp]

@dataclass
class SelectStmt:
    columns:       List[str]
    tables:        List[Tuple[str, str]]   # (table_name, alias)
    where:         Optional[Expr]  = None
    distinct:      bool            = False
    not_exists:    Optional[str]   = None  # raw subquery text


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "EXISTS",
    "JOIN", "INNER", "LEFT", "RIGHT", "OUTER", "ON",
    "DISTINCT", "AS", "IN", "IS", "NULL", "LIKE",
}

def _tokenize(sql: str) -> List[dict]:
    pattern = r"(>=|<=|!=|<>|[=<>()\[\],;*]|'[^']*'|\"[^\"]*\"|[\w.]+)"
    tokens = []
    for m in re.finditer(pattern, sql):
        v = m.group(1)
        tokens.append({"val": v, "upper": v.upper(), "is_kw": v.upper() in _KEYWORDS})
    return tokens


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens):
        self.tok = tokens
        self.i   = 0

    def peek(self) -> Optional[dict]:
        return self.tok[self.i] if self.i < len(self.tok) else None

    def consume(self) -> dict:
        t = self.tok[self.i]; self.i += 1; return t

    def match(self, *keywords) -> bool:
        t = self.peek()
        if t and t["upper"] in {k.upper() for k in keywords}:
            self.consume(); return True
        return False

    def expect(self, keyword: str) -> dict:
        t = self.peek()
        if not t or t["upper"] != keyword.upper():
            raise ValueError(f"Expected '{keyword}', got '{t['val'] if t else 'EOF'}'")
        return self.consume()

    def parse(self) -> SelectStmt:
        self.expect("SELECT")
        distinct = self.match("DISTINCT")

        # Column list
        columns = []
        while self.peek() and self.peek()["upper"] != "FROM":
            if self.peek()["val"] == ",":
                self.consume(); continue
            columns.append(self.consume()["val"])

        self.expect("FROM")

        # Table list (handles comma-separated and explicit JOIN)
        tables = []
        stop = {"WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "OUTER"}
        while self.peek() and self.peek()["upper"] not in stop:
            if self.peek()["val"] in (",", ";"):
                self.consume(); continue
            tbl  = self.consume()["val"]
            alias = tbl.split(".")[-1]
            if self.peek() and not self.peek()["is_kw"] and self.peek()["val"] not in (",", ";"):
                if self.peek()["upper"] == "AS": self.consume()
                if self.peek() and not self.peek()["is_kw"]:
                    alias = self.consume()["val"]
            tables.append((tbl, alias))

        # JOIN clauses
        while self.peek() and self.peek()["upper"] in ("JOIN", "INNER", "LEFT", "RIGHT", "OUTER"):
            jtype = self.consume()["upper"]
            if self.peek() and self.peek()["upper"] == "JOIN": self.consume()
            tbl  = self.consume()["val"]
            alias = tbl.split(".")[-1]
            if self.peek() and self.peek()["upper"] == "AS": self.consume()
            if self.peek() and not self.peek()["is_kw"] and self.peek()["val"] not in ("ON", ","):
                alias = self.consume()["val"]
            tables.append((tbl, alias))
            if self.peek() and self.peek()["upper"] == "ON":
                self.consume()
                # consume join condition tokens until WHERE / JOIN / end
                while self.peek() and self.peek()["upper"] not in ("WHERE","JOIN","INNER","LEFT","RIGHT"):
                    self.consume()

        # WHERE
        where_expr = None
        not_exists_text = None

        if self.match("WHERE"):
            # Check for NOT EXISTS pattern
            if (self.peek() and self.peek()["upper"] == "NOT"
                    and self.i + 1 < len(self.tok)
                    and self.tok[self.i + 1]["upper"] == "EXISTS"):
                self.consume(); self.consume()           # NOT EXISTS
                if self.peek() and self.peek()["val"] == "(": self.consume()
                depth, sub_tokens = 1, []
                while self.peek() and depth > 0:
                    t = self.consume()
                    if t["val"] == "(": depth += 1
                    elif t["val"] == ")":
                        depth -= 1
                        if depth == 0: break
                    if depth > 0: sub_tokens.append(t["val"])
                not_exists_text = " ".join(sub_tokens)
            else:
                where_expr = self._parse_or()

        return SelectStmt(
            columns=columns or ["*"],
            tables=tables,
            where=where_expr,
            distinct=distinct,
            not_exists=not_exists_text,
        )

    # Expression grammar: OR < AND < NOT < atom
    def _parse_or(self):
        left = self._parse_and()
        while self.peek() and self.peek()["upper"] == "OR":
            self.consume()
            left = BinOp("OR", left, self._parse_and())
        return left

    def _parse_and(self):
        left = self._parse_unary()
        while self.peek() and self.peek()["upper"] == "AND":
            self.consume()
            left = BinOp("AND", left, self._parse_unary())
        return left

    def _parse_unary(self):
        if self.peek() and self.peek()["upper"] == "NOT":
            self.consume()
            return UnaryOp("NOT", self._parse_atom())
        return self._parse_atom()

    def _parse_atom(self):
        if self.peek() and self.peek()["val"] == "(":
            self.consume()
            e = self._parse_or()
            if self.peek() and self.peek()["val"] == ")": self.consume()
            return e
        left_tok = self.consume()
        left = Atom(left_tok["val"])
        _CMP = {">=", "<=", "!=", "<>", ">", "<", "=", "LIKE", "IS", "IN"}
        if self.peek() and (self.peek()["val"] in _CMP or self.peek()["upper"] in _CMP):
            op  = self.consume()["val"]
            right = Atom(self.consume()["val"] if self.peek() else "?")
            return BinOp(op, left, right)
        return left


# ---------------------------------------------------------------------------
# FOL emitter
# ---------------------------------------------------------------------------

_OP_MAP = {
    "AND": "∧", "OR": "∨", "=": "=", ">": ">", "<": "<",
    ">=": "≥", "<=": "≤", "!=": "≠", "<>": "≠",
    "LIKE": "like", "IS": "is", "IN": "∈",
}

def _emit_expr(expr: Expr) -> str:
    if isinstance(expr, BinOp):
        l = _emit_expr(expr.left)
        r = _emit_expr(expr.right)
        op = _OP_MAP.get(expr.op.upper(), expr.op)
        return f"({l} {op} {r})"
    if isinstance(expr, UnaryOp):
        return f"¬{_emit_expr(expr.operand)}"
    return expr.value


def _make_vars(tables: List[Tuple[str, str]]) -> dict:
    """Assign short distinct variable names per alias."""
    used, mapping = set(), {}
    for _, alias in tables:
        base = alias[0].lower()
        v = base
        n = 2
        while v in used:
            v = f"{base}{n}"; n += 1
        used.add(v); mapping[alias] = v
    return mapping


class SQLtoFOL:
    """
    Translates a parsed SelectStmt (or raw SQL string) into a FOL formula.

    Example
    -------
    >>> t = SQLtoFOL()
    >>> t.translate("SELECT name FROM employees WHERE salary > 50000")
    'λname. ∃e. (employees(e) ∧ (e.salary > 50000))'
    """

    def translate(self, sql_or_stmt: Union[str, SelectStmt]) -> str:
        if isinstance(sql_or_stmt, str):
            tokens = _tokenize(sql_or_stmt)
            stmt   = _Parser(tokens).parse()
        else:
            stmt = sql_or_stmt

        vars_ = _make_vars(stmt.tables)

        # Table membership predicates
        table_preds = " ∧ ".join(
            f"{tbl}({vars_[alias]})" for tbl, alias in stmt.tables
        )

        body = table_preds

        if stmt.where:
            body += f" ∧ {_emit_expr(stmt.where)}"

        if stmt.not_exists:
            body += f" ∧ ¬∃({stmt.not_exists})"

        # Quantifier
        bound    = ",".join(vars_.values())
        quantifier = f"∃!{bound}" if stmt.distinct else f"∃{bound}"

        # Projection (λ-abstraction)
        all_cols = (len(stmt.columns) == 1 and stmt.columns[0] == "*")
        proj_vars = bound if all_cols else ",".join(stmt.columns)

        return f"λ{proj_vars}. {quantifier}. ({body})"


def sql_to_fol(sql: str) -> str:
    """Convenience wrapper: SQL string → FOL string."""
    return SQLtoFOL().translate(sql)
