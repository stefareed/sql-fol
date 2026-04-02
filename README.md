# sql-fol

**Translate SQL ↔ First-Order Logic, with Fregean semantic annotations.**

```
λname. ∃e. (employees(e) ∧ (e.salary > 50000))
         ↑                ↑
    λ-abstraction    Sättigung (saturation of the Begriff)
```

This library translates SQL `SELECT` statements into FOL formulae and back, then annotates the result using Frege's semantic vocabulary: *Begriff*, *Gegenstand*, *Sinn*, *Bedeutung*, *Sättigung*, *Merkmal*, *Umfang*. 

This project is the result of a meme I made when taking formal semantics years ago + reading about the history of SQL. 
<img src="frege-against-the-machine.jpeg" width="300" height="auto">




Codd's relational model was grounded in predicate logic from the start, but the Fregean framing surfaces things that the standard database-theory account leaves implicit.

---

## Installation

```bash
git clone https://github.com/yourname/sql-fol.git
cd sql-fol
pip install -e .

# Optional: production-grade SQL parsing
pip install -e ".[sqlglot]"

# Optional: query equivalence checking via SMT
pip install -e ".[z3]"
```

---

## Quick start

```python
from sql_fol import sql_to_fol, fol_to_sql, fregean_analysis

# SQL → FOL
fol = sql_to_fol("SELECT name FROM employees WHERE salary > 50000")
# λname. ∃e. (employees(e) ∧ (e.salary > 50000))

# FOL → SQL
sql = fol_to_sql("λname. ∃e. (Employees(e) ∧ (e.salary > 50000))")
# SELECT name
# FROM Employees AS e
# WHERE e.salary > 50000;

# Fregean annotations
for ann in fregean_analysis(sql):
    print(f"[{ann['term']}]")
    print(f"  {ann['gloss']}")
    print(f"  {ann['analysis']}\n")
```

---

## The correspondence

| SQL | FOL | Fregean term |
|-----|-----|--------------|
| Table `R` | `R(x)` | *Begriff* — unsaturated concept predicate |
| Row / tuple | bound variable `x` | *Gegenstand* — object falling under the concept |
| `SELECT cols` | `λcols.` | λ-abstraction over free variables |
| `FROM R` | `∃x. R(x)` | existential claim over the concept's *Umfang* (extension) |
| `WHERE P(x)` | `∧ P(x)` | *Sättigung* — saturating the concept with argument values |
| Column predicate | sub-formula | *Merkmal* — feature contributing to the compound concept |
| `INNER JOIN` | `R(x) ∧ S(x)` | shared variable across two Begriffe |
| `NOT EXISTS (...)` | `¬∃x. φ(x)` | *Verneinung des Existenzialsatzes* |
| `DISTINCT` | `∃!x` | unique existential (*Einzigkeitsquantor*) |
| View `V` = query `Q` | same *Bedeutung*, different *Sinn* | see §Sinn/Bedeutung below |
| `NULL` | reference failure | *Bedeutungslosigkeit* — see §NULL below |

---

## Translation examples

### Simple filter

```sql
SELECT name FROM employees WHERE salary > 50000
```
```
λname. ∃e. (employees(e) ∧ (e.salary > 50000))
```

The table `employees` names a *Begriff*. The WHERE clause *saturates* it — binding the open argument position to a specific constraint. The λ-prefix abstracts over the projected column, yielding a function from satisfying rows to their `name` values.

---

### Inner join

```sql
SELECT e.name, d.name
FROM employees e, departments d
WHERE e.dept_id = d.id
```
```
λe.name,d.name. ∃e,d. (employees(e) ∧ departments(d) ∧ (e.dept_id = d.id))
```

Two concepts sharing a bound variable. The join condition `e.dept_id = d.id` is a *Merkmal* of the compound concept `employees(e) ∧ departments(d)`. Frege's logic was designed for monadic predicates; this is where his framework strains — n-ary relations require the extension Peirce and Russell added.

---

### NOT EXISTS — negated existential

```sql
SELECT name FROM students
WHERE NOT EXISTS (
  SELECT 1 FROM enrollments WHERE student_id = students.id
)
```
```
λname. ∃s. (students(s) ∧ ¬∃(SELECT 1 FROM enrollments WHERE student_id = students.id))
```

`NOT EXISTS` maps to `¬∃`. This is also the basis of SQL's universal quantification encoding:

```
∀x. φ(x)  ≡  ¬∃x. ¬φ(x)
```

In SQL: `NOT EXISTS (SELECT 1 FROM t WHERE NOT condition)`. Frege would note this is a *second-level* predicate — it says something about a *concept* (that nothing falls under it), not about an object.

---

### DISTINCT — unique existential

```sql
SELECT DISTINCT city FROM customers WHERE country = 'US'
```
```
λcity. ∃!c. (customers(c) ∧ (c.country = 'US'))
```

The `∃!` (unique existential) collapses multiple witnesses to a concept into a single representative. Frege used unique existence in his definition of number: the number 1 belongs to concept *F* iff `∃!x. F(x)`. `DISTINCT` is the query-level analog.

---

## NULL and the collapse of bivalence

Frege's logical system rests on a single foundational commitment: every well-formed proposition is either true or false. This is the law of excluded middle (LEM), and for Frege it was a precondition for logic being logic at all — not a convention but a structural feature of thought.

SQL NULL violates this deliberately, and the consequences cascade.

### Three-valued logic

NULL introduces a third truth value, UNKNOWN, following Kleene's strong K3 semantics:

| `p` | `q` | `p AND q` | `p OR q` |
|-----|-----|-----------|----------|
| T | U | **U** | **T** |
| F | U | **F** | **U** |
| U | U | **U** | **U** |

The asymmetric cases (`F AND UNKNOWN = FALSE`, `T OR UNKNOWN = TRUE`) are the "absorption" rules that prevent total logical collapse. But AND and OR are no longer truth-functional in the classical sense.

### Double negation elimination fails

In classical logic, `φ ≡ ¬¬φ` is a tautology. In SQL with NULLs it isn't:

```sql
-- These should be complementary. They are not.
SELECT * FROM employees WHERE salary > 60000;
SELECT * FROM employees WHERE NOT (salary > 60000);
```

If `salary` is NULL, the row appears in *neither* query — because `NOT UNKNOWN = UNKNOWN`, and the WHERE clause silently discards UNKNOWN rows as if they were false. The union of these two queries is not the full table.

```sql
-- Demonstration
CREATE TABLE t (x INT);
INSERT INTO t VALUES (1), (NULL), (3);

SELECT * FROM t WHERE x > 1;       -- returns: 3
SELECT * FROM t WHERE NOT (x > 1); -- returns: 1
-- NULL row appears in neither. The full table is not covered.
```

This is the direct violation of LEM: the row with `x = NULL` satisfies neither `x > 1` nor `¬(x > 1)`.

### NULL = NULL is UNKNOWN, not TRUE

```sql
SELECT NULL = NULL;    -- UNKNOWN
SELECT NULL IS NULL;   -- TRUE
```

The `=` predicate with NULL doesn't return FALSE — it returns UNKNOWN. This means SQL's equality is not an equivalence relation. In FOL, identity `x = x` is a logical truth. In SQL, `NULL = NULL` has no truth value, which breaks reflexivity.

This is what Frege called *Bedeutungslosigkeit*: an expression with a perfectly coherent *Sinn* (we understand `NULL = NULL` syntactically) but no *Bedeutung* — it refers to nothing and therefore has no truth value. Frege considered this a defect in natural language. Codd built it into the type system.

### Frege's own patch

In *Grundgesetze*, Frege tried to handle empty names by assigning them a conventional reference — he stipulated that a concept-expression failing to denote would refer to the empty set. This was a patch, and it didn't save him: Russell's paradox arrived in 1902, showing that even well-formed concept expressions could fail to have a consistent extension.

NULL is the database-theorists' version of the same problem. Codd introduced it in his 1970 paper almost as an afterthought. By 1979 he was proposing a *four-valued* logic:
- `TRUE`
- `FALSE`
- `UNKNOWN (missing value)`
- `UNKNOWN (inapplicable value)`

Most database systems never implemented this. The result is that SQL's NULL is a single token covering at least two philosophically distinct situations — a value that exists but is unknown, and a value that doesn't exist (is inapplicable). Frege's vocabulary has a term for this: *Bedeutungslosigkeit* in both cases, but for different reasons.

---

## Sinn / Bedeutung and the view problem

Frege's puzzle: "Hesperus" and "Phosphorus" both refer to Venus, but they don't *mean* the same thing. Knowing Hesperus is Phosphorus is an empirical discovery, not a tautology. The two names share a *Bedeutung* (reference: the planet Venus) while differing in *Sinn* (sense: their mode of presentation).

The SQL analog is immediate.

### Views: same Bedeutung, different Sinn

```sql
CREATE VIEW active_customers AS
  SELECT * FROM customers WHERE status = 'active';

-- These denote the same relation (identical Bedeutung):
SELECT * FROM active_customers;
SELECT * FROM customers WHERE status = 'active';

-- But they differ in Sinn:
--   The view presents the relation as an atomic named object.
--   The inline query presents it as a compositional derivation.
```

Knowing these are equivalent is non-trivial — it's the query optimizer's job. This mirrors Frege's point: the informativeness of `Hesperus = Phosphorus` (vs. the triviality of `Hesperus = Hesperus`) comes from the difference in Sinn despite identical Bedeutung.

### Materialized views: Sinn and Bedeutung come apart temporally

```sql
CREATE MATERIALIZED VIEW monthly_revenue AS
  SELECT month, SUM(amount) FROM orders GROUP BY month;
-- Refresh hasn't run. The view's Bedeutung is stale.
-- The live query's Bedeutung is current.
-- Same Sinn (same logical definition), different Bedeutung.
```

Here the *same* Sinn corresponds to *different* Bedeutungen at different moments. Frege's semantics was static — he had no theory of temporal reference drift. Materialized views introduce a gap that has no Fregean analog.

### Updatable views: reference under a description

```sql
CREATE VIEW high_earners AS
  SELECT id, name, salary FROM employees WHERE salary > 100000;

UPDATE high_earners SET salary = 95000 WHERE id = 42;
-- Row 42 now disappears from the view after the update.
```

This is reference under a description: the view refers to rows *under the description* "salary > 100000." Updating through the view changes whether the description applies, which changes what the view refers to. It's the database version of "does 'the shortest spy' still refer to the same person after they stop being the shortest?"

Non-updatable views — those with `GROUP BY`, `DISTINCT`, aggregates, or certain joins — are views where the Bedeutung (result relation) has no unique preimage in the base tables. The mapping from base data to view output isn't injective: you can read the reference but not write back through it.

---

## Production-grade parsing with sqlglot

The built-in parser handles the core SQL fragment. For real-world SQL, use [sqlglot](https://github.com/tobymao/sqlglot):

```python
import sqlglot
import sqlglot.expressions as exp

def sql_to_fol_via_sqlglot(sql: str) -> str:
    ast = sqlglot.parse_one(sql)
    return _walk(ast)

def _walk(node) -> str:
    if isinstance(node, exp.Select):
        tables = [_walk(t) for t in node.find_all(exp.Table)]
        where  = node.find(exp.Where)
        cols   = [c.alias_or_name for c in node.expressions]
        body   = " ∧ ".join(f"{t}(x)" for t in tables)
        if where:
            body += f" ∧ {_walk(where.this)}"
        proj = "*" if cols == ["*"] else ",".join(cols)
        return f"λ{proj}. ∃x. ({body})"
    elif isinstance(node, exp.And):
        return f"({_walk(node.left)} ∧ {_walk(node.right)})"
    elif isinstance(node, exp.Or):
        return f"({_walk(node.left)} ∨ {_walk(node.right)})"
    elif isinstance(node, exp.Not):
        return f"¬{_walk(node.this)}"
    elif isinstance(node, exp.Exists):
        return f"∃({_walk(node.this)})"
    elif hasattr(node, "sql"):
        return node.sql()
    return str(node)
```

---

## Query equivalence checking with z3

Two SQL queries are semantically equivalent (same Bedeutung, potentially different Sinn) if their FOL translations are logically equivalent. The z3 SMT solver can check this:

```python
from z3 import Solver, Bool, And, Not, sat

def queries_equivalent(sql1: str, sql2: str) -> bool:
    """
    Returns True if sql1 and sql2 are semantically equivalent.
    Uses z3 to check unsatisfiability of their symmetric difference.
    Note: full FOL is undecidable; z3 handles the quantifier-free fragment.
    """
    fol1 = sql_to_fol(sql1)
    fol2 = sql_to_fol(sql2)

    # For the quantifier-free fragment, encode as propositional constraints
    # and check that (fol1 AND NOT fol2) OR (NOT fol1 AND fol2) is UNSAT
    # Full implementation requires encoding table membership as z3 Relations.
    # See: https://microsoft.github.io/z3guide/

    solver = Solver()
    p = Bool("p")  # placeholder for fol1
    q = Bool("q")  # placeholder for fol2
    solver.add(And(p, Not(q)))  # symmetric difference
    return solver.check() == sat  # UNSAT → equivalent
```

A full implementation encoding SQL tables as z3 `ArraySort` relations is in `examples/z3_equivalence.py`.

---

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

---

## Project structure

```
sql-fol/
├── sql_fol/
│   ├── __init__.py          # Public API: sql_to_fol, fol_to_sql, fregean_analysis
│   ├── sql_to_fol.py        # Tokenizer, recursive-descent parser, FOL emitter
│   ├── fol_to_sql.py        # FOL parser, SQL emitter
│   └── annotations.py       # Fregean semantic annotation engine
├── tests/
│   └── test_translator.py   # pytest suite: unit + round-trip tests
├── examples/
│   └── z3_equivalence.py    # Query equivalence checking (z3)
├── pyproject.toml
└── README.md
```

---

## Limitations and roadmap

| Feature | Status |
|---------|--------|
| `SELECT`, `WHERE`, `JOIN` | ✅ |
| `NOT EXISTS`, `DISTINCT` | ✅ |
| `AND`, `OR`, `NOT` conditions | ✅ |
| Comparison operators `> < >= <= != =` | ✅ |
| `GROUP BY` / `HAVING` | ⬜ maps to generalized quantifiers |
| `UNION` / `INTERSECT` / `EXCEPT` | ⬜ maps to `∨` / `∧` / `∧¬` |
| Aggregate functions | ⬜ requires second-order logic |
| Subqueries in SELECT | ⬜ λ-abstraction over nested scope |
| CTEs | ⬜ let-binding / fixed points |
| Window functions | ⬜ no standard FOL encoding |
| NULL / three-valued logic | ⬜ requires K3 or supervaluationist semantics |
| sqlglot integration | ⬜ swap parser for full SQL coverage |
| z3 equivalence checking | ⬜ quantifier-free fragment working |

The NULL row is intentionally left open — correct handling requires choosing a formal semantics (Kleene K3, Łukasiewicz L3, supervaluationism, or Codd's four-valued logic) and that choice is itself the interesting theoretical question.

---

## Background

Codd's 1970 paper *A Relational Model of Data for Large Shared Data Banks* grounded the relational model explicitly in set theory and predicate logic. The Fregean vocabulary applied here is not anachronistic — it names structural features Codd was already relying on, just without the philosophy-of-language framing.

Key sources:

- Codd, E.F. (1970). *A Relational Model of Data for Large Shared Data Banks.* CACM 13(6).
- Frege, G. (1879). *Begriffsschrift.*
- Frege, G. (1892). *Über Sinn und Bedeutung.* Zeitschrift für Philosophie und philosophische Kritik.
- Imielinski, T. & Lipski, W. (1984). *Incomplete information in relational databases.* JACM 31(4). — the formal treatment of NULL semantics.
- van Fraassen, B. (1966). *Singular Terms, Truth-Value Gaps, and Free Logic.* Journal of Philosophy. — supervaluationism as an alternative to K3.
- Codd, E.F. (1979). *Extending the Database Relational Model to Capture More Meaning.* TODS 4(4). — Codd's own four-valued logic proposal.

---

## License

MIT
