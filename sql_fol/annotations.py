"""
annotations.py
==============
Produces Fregean semantic annotations for a SQL query, identifying:

  - Begriff (concept)         table names / predicates
  - Gegenstand (object)       bound row variables
  - Sättigung (saturation)    WHERE clause argument binding
  - Sinn (sense)              the query's mode of presentation
  - Bedeutung (reference)     the result relation it denotes
  - Umfang (extension)        the full set of satisfying tuples
  - Merkmal (feature)         individual column predicates
"""

from __future__ import annotations
import re
from typing import List, Dict


def fregean_analysis(sql: str) -> List[Dict[str, str]]:
    """
    Return a list of annotation dicts for a SQL query.

    Each dict has:
        term    : German Fregean term
        gloss   : English translation
        analysis: Explanation specific to this query
    """
    sql_upper = sql.upper()
    annotations = []

    # --- Begriff (concept) ---
    tables = re.findall(r"FROM\s+(\w+)", sql, re.IGNORECASE)
    joins  = re.findall(r"JOIN\s+(\w+)", sql, re.IGNORECASE)
    all_tables = tables + joins
    if all_tables:
        annotations.append({
            "term":     "Begriff (concept)",
            "gloss":    "An unsaturated predicate; a function from objects to truth values",
            "analysis": (
                f"The table{'s' if len(all_tables)>1 else ''} "
                f"{', '.join(all_tables)} name Fregean Begriffe. "
                f"Each is an unsaturated predicate R(x) whose Umfang (extension) "
                f"is the set of all rows satisfying it."
            ),
        })

    # --- Sättigung (saturation) ---
    where_m = re.search(r"WHERE\s+(.+?)(?:;|$)", sql, re.IGNORECASE | re.DOTALL)
    if where_m:
        clause = where_m.group(1).strip()[:120]
        annotations.append({
            "term":     "Sättigung (saturation)",
            "gloss":    "Filling the argument places of an unsaturated expression",
            "analysis": (
                f"The WHERE clause '{clause}' saturates the concept by binding "
                f"argument positions to specific values, just as function application "
                f"fills argument slots. An unsaturated concept becomes a truth value once saturated."
            ),
        })

    # --- Merkmal (feature) ---
    conditions = re.findall(r"(\w+\.\w+|\w+)\s*[><=!]+\s*['\w.]+", sql)
    if conditions:
        annotations.append({
            "term":     "Merkmal (feature / mark)",
            "gloss":    "A sub-predicate contributing to a compound concept",
            "analysis": (
                f"The conditions {conditions} are Merkmale — "
                f"component predicates that jointly define the compound concept. "
                f"Frege distinguished a Merkmal (a predicate that contributes to a concept's "
                f"definition) from a property (a predicate true of the concept itself)."
            ),
        })

    # --- JOIN: shared variable ---
    if joins:
        annotations.append({
            "term":     "Relationale Verbindung (relational connection)",
            "gloss":    "Two concepts sharing a bound variable",
            "analysis": (
                f"The JOIN connects {' and '.join(joins)} via a shared variable: "
                f"R(x) ∧ S(x). This is a compound concept whose extension is the "
                f"Cartesian product filtered by the join predicate. Frege had no "
                f"explicit account of relations (n > 1 arity), a gap Russell addressed."
            ),
        })

    # --- NOT EXISTS: negated existential ---
    if "NOT EXISTS" in sql_upper:
        annotations.append({
            "term":     "Verneinung des Existenzialsatzes (negated existential)",
            "gloss":    "¬∃x.φ(x) — the concept's extension is empty",
            "analysis": (
                "NOT EXISTS maps to ¬∃x.φ(x). This is also how SQL encodes universal "
                "quantification: ∀x.φ(x) ≡ ¬∃x.¬φ(x). Frege would note that this "
                "is a second-level predicate — it says something about a concept "
                "(that nothing falls under it), not about an object."
            ),
        })

    # --- DISTINCT: unique existential ---
    if "DISTINCT" in sql_upper:
        annotations.append({
            "term":     "Einzigkeitsquantor (unique existential)",
            "gloss":    "∃!x — exactly one object falls under the concept",
            "analysis": (
                "DISTINCT collapses multiple witnesses to a concept into a unique "
                "representative, corresponding to ∃!. Frege used unique existence in "
                "his definition of number: the number 1 belongs to a concept F iff "
                "∃!x.F(x). DISTINCT is the query-level analog."
            ),
        })

    # --- NULL warning ---
    if "NULL" in sql_upper:
        annotations.append({
            "term":     "Bedeutungslosigkeit (reference failure)",
            "gloss":    "An expression with sense but no reference",
            "analysis": (
                "NULL is Frege's nightmare: a term with Sinn (it appears in well-formed "
                "expressions) but no Bedeutung (it denotes no value). This forces SQL "
                "into three-valued logic (TRUE / FALSE / UNKNOWN), breaking the law of "
                "excluded middle. Frege considered such reference failure a flaw in "
                "natural language that formal notation should eliminate — SQL inherits it."
            ),
        })

    # --- Sinn / Bedeutung (always) ---
    annotations.append({
        "term":     "Sinn / Bedeutung (sense / reference)",
        "gloss":    "The mode of presentation vs. the object presented",
        "analysis": (
            "This query has a Sinn — its syntactic form and execution plan — and a "
            "Bedeutung — the result relation it denotes. A SQL view over this query "
            "shares the same Bedeutung but differs in Sinn. Query optimization is "
            "the practice of finding a query with a cheaper Sinn but identical Bedeutung."
        ),
    })

    return annotations
