cd C:\Users\acer\Desktop\WQ\worldquant-miner-master\generation_two

@'
import sqlite3
import re

db = "generation_two_backtests.db"
bad_ts_terms = [
    "ts_add",
    "ts_subtract",
    "ts_multiply",
    "ts_divide",
    "ts_log",
    "ts_sqrt",
]

con = sqlite3.connect(db)
cur = con.cursor()

tables = {r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

if "compiler_knowledge" in tables:
    cols = [r[1] for r in cur.execute("PRAGMA table_info(compiler_knowledge)").fetchall()]
    text_cols = [
        c for c in [
            "replacement_operator",
            "compiler_rule",
            "error_message",
            "learned_from_error",
            "learned_from_template",
            "metadata",
        ]
        if c in cols
    ]
    if text_cols:
        where_parts = []
        params = []
        for c in text_cols:
            for term in bad_ts_terms:
                where_parts.append(f"LOWER(COALESCE({c}, '')) LIKE ?")
                params.append(f"%{term}%")
        sql = "DELETE FROM compiler_knowledge WHERE " + " OR ".join(where_parts)
        cur.execute(sql, params)
        print("deleted bad compiler_knowledge:", cur.rowcount)
    else:
        print("compiler_knowledge exists, but no expected text columns found")
else:
    print("compiler_knowledge table not found")

if "generated_templates" in tables:
    cur.execute("DELETE FROM generated_templates")
    print("cleared generated_templates:", cur.rowcount)

con.commit()
con.close()
'@ | python
