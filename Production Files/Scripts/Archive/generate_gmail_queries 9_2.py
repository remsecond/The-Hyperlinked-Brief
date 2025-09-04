
import re
import argparse
import pandas as pd
from datetime import datetime

def parse_emails(characters: str):
    if not isinstance(characters, str):
        return []
    return re.findall(r'[\w\.-]+@[\w\.-]+', characters)

def split_terms(s: str):
    if not isinstance(s, str):
        return []
    # allow ; or , as separators
    parts = [p.strip() for p in re.split(r'[;,]', s) if p.strip()]
    # de-duplicate while preserving order
    seen = set()
    out = []
    for p in parts:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out

def to_gmail_date(d: str):
    """Normalize to Gmail-friendly YYYY/MM/DD if possible; else pass through."""
    if not isinstance(d, str):
        return d
    try:
        dt = datetime.strptime(d.strip(), "%Y-%m-%d")
        return dt.strftime("%Y/%m/%d")
    except Exception:
        return d.strip()

def build_keyword_clause(terms):
    # Quote multi-word phrases
    quoted = [f'"{t}"' if ' ' in t else f'"{t}"' for t in terms]  # quote everything for exact-match bias
    return " OR ".join(quoted) if quoted else ""

def build_exclude_clause(terms):
    # Exclude tokens (no quotes to let Gmail match variants)
    return " ".join([f"-{t}" for t in terms]) if terms else ""

def build_email_clause(emails, limit=None):
    if not emails:
        return ""
    use = emails if limit is None else emails[:limit]
    parts = [f"from:{e} OR to:{e}" for e in use]
    return " OR ".join(parts)

def build_queries(row):
    seed_id = row.get("Seed_ID", "").strip()
    start = to_gmail_date(row.get("Date_Range_Start", ""))
    end   = to_gmail_date(row.get("Date_Range_End", ""))
    emails = parse_emails(row.get("Primary_Characters", ""))
    include_terms = split_terms(row.get("Keywords_Include", ""))
    exclude_terms = split_terms(row.get("Keywords_Exclude", ""))

    kw_clause = build_keyword_clause(include_terms)
    ex_clause = build_exclude_clause(exclude_terms)

    date_clause = ""
    if start:
        date_clause += f" after:{start}"
    if end:
        date_clause += f" before:{end}"

    # Precise: all known emails + keywords + dates + excludes
    email_clause_precise = build_email_clause(emails, limit=None)
    if email_clause_precise and kw_clause:
        precise = f"({email_clause_precise}) ({kw_clause}){date_clause} {ex_clause}".strip()
    elif email_clause_precise:
        precise = f"({email_clause_precise}){date_clause} {ex_clause}".strip()
    else:
        precise = f"({kw_clause}){date_clause} {ex_clause}".strip()

    # Intermediate: first 1-2 emails + keywords + dates + excludes
    limit = 2 if len(emails) >= 2 else (1 if len(emails) == 1 else None)
    email_clause_intermediate = build_email_clause(emails, limit=limit)
    if email_clause_intermediate and kw_clause:
        intermediate = f"({email_clause_intermediate}) ({kw_clause}){date_clause} {ex_clause}".strip()
    elif email_clause_intermediate:
        intermediate = f"({email_clause_intermediate}){date_clause} {ex_clause}".strip()
    else:
        intermediate = f"({kw_clause}){date_clause} {ex_clause}".strip()

    # Broad: keywords + dates + excludes (no email filters)
    broad = f"({kw_clause}){date_clause} {ex_clause}".strip()

    return seed_id, precise, intermediate, broad

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to Case_Seeds.csv")
    ap.add_argument("--output", required=True, help="Path to write Queries_Output.csv")
    ap.add_argument("--mode", choices=["table","raw"], default="table", help="Output style for stdout")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    rows = []
    for _, row in df.iterrows():
        seed_id, precise, intermediate, broad = build_queries(row)
        rows.append({"Seed_ID": seed_id, "Precise Query": precise, "Intermediate Query": intermediate, "Broad Query": broad})

    out_df = pd.DataFrame(rows, columns=["Seed_ID","Precise Query","Intermediate Query","Broad Query"])
    out_df.to_csv(args.output, index=False)

    if args.mode == "table":
        # print a simple markdown-like table
        from tabulate import tabulate
        try:
            print(tabulate(out_df, headers="keys", tablefmt="github", showindex=False))
        except Exception:
            # Fallback: CSV preview
            print(out_df.to_string(index=False))
    else:
        # raw numbered list (Precise, Intermediate, Broad per seed in that order)
        n = 1
        for _, r in out_df.iterrows():
            for col in ["Precise Query","Intermediate Query","Broad Query"]:
                print(f"{n}. {r[col]}")
                n += 1

if __name__ == "__main__":
    main()
