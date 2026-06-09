"""
csv_to_json.py — Reconstruct the master pipeline JSON from the three exported CSVs.

Reads:
    partners.csv        (one row per contact)
    accounts.csv        (one row per account)
    action_items.csv    (one row per action item)

Writes:
    master_data_reconstructed.json  (or a path you specify)

Notes:
  - partners.csv rows are re-grouped by partner_id to rebuild the contacts array.
  - accounts.csv brand column (pipe-joined) is split back to a list.
  - accounts.csv sessions column (compact JSON string) is parsed back to an array.
  - Empty strings are converted back to null for nullable fields.

Usage:
    python csv_to_json.py <csv_dir> [output.json]

If output.json is omitted, master_data_reconstructed.json is written in <csv_dir>.
"""

import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Fields that should be null (not empty string) when blank
# ---------------------------------------------------------------------------
NULLABLE_ACCOUNT_FIELDS    = {"accountURL", "targetMonth", "targetYear", "oppValue", "competition"}
NULLABLE_ACTION_FIELDS     = {"accountId", "deadline"}


# ---------------------------------------------------------------------------
# CSV readers
# ---------------------------------------------------------------------------

def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Rebuilders
# ---------------------------------------------------------------------------

def rebuild_partners(rows: list[dict]) -> list[dict]:
    """
    Group rows back by partner_id and nest contacts.
    Row order is preserved for partners; contacts appear in file order.
    """
    # Use an ordered dict keyed by partner_id to preserve insertion order
    partner_map: dict[str, dict] = {}

    for row in rows:
        pid = row["partner_id"]
        if pid not in partner_map:
            partner_map[pid] = {
                "id":       pid,
                "fullName": row["fullName"],
                "cadence":  row["cadence"],
                "contacts": [],
            }
        # Only add contact if a name is present
        if row.get("contact_name", "").strip():
            regions_raw = row.get("supportedRegions", "").strip()
            contact = {
                "name":             row["contact_name"].strip(),
                "email":            row["contact_email"].strip(),
                "mobile":           row["contact_mobile"].strip(),
                "supportedRegions": [r.strip() for r in regions_raw.split("|") if r.strip()]
                                    if regions_raw else [],
            }
            partner_map[pid]["contacts"].append(contact)

    return list(partner_map.values())


def _to_null(value: str):
    """Return None for blank strings, otherwise return the stripped value."""
    v = value.strip() if isinstance(value, str) else value
    return None if v == "" else v


def _to_int_or_null(value: str):
    """Convert a numeric string to int; blank → None."""
    v = value.strip() if isinstance(value, str) else value
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return v  # keep as-is if not a clean integer


def _parse_sessions(value: str) -> list:
    """Parse sessions JSON string back to a list; return [] if blank or invalid."""
    v = value.strip() if isinstance(value, str) else ""
    if not v:
        return []
    try:
        parsed = json.loads(v)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def rebuild_accounts(rows: list[dict]) -> list[dict]:
    """
    Rebuild account objects.
    - brand    : split on '|' back to list; empty string → empty list
    - sessions : parsed from compact JSON string back to array
    - targetYear : int or null
    - nullable fields : empty string → null
    """
    accounts = []
    for row in rows:
        brand_raw = row.get("brand", "").strip()
        brand = [b.strip() for b in brand_raw.split("|") if b.strip()] if brand_raw else []

        acc = {
            "id":                row.get("id", "").strip(),
            "partner":           row.get("partner", "").strip(),
            "accountName":       row.get("accountName", "").strip(),
            "accountURL":        _to_null(row.get("accountURL", "")),
            "city":              row.get("city", "").strip(),
            "region":            row.get("region", "").strip(),
            "partnerSalesOwner": row.get("partnerSalesOwner", "").strip(),
            "techOwner":         row.get("techOwner", "").strip(),
            "brand":             brand,
            "currentStatus":     row.get("currentStatus", "").strip(),
            "targetMonth":       _to_null(row.get("targetMonth", "")),
            "targetYear":        _to_int_or_null(row.get("targetYear", "")),
            "oppValue":          _to_null(row.get("oppValue", "")),
            "oppValueUOM":       row.get("oppValueUOM", "").strip(),
            "deploymentModel":   row.get("deploymentModel", "").strip(),
            "competition":       _to_null(row.get("competition", "")),
            "latestUpdate":      row.get("latestUpdate", "").strip(),
            "lastDiscussed":     row.get("lastDiscussed", "").strip(),
            "sessions":          _parse_sessions(row.get("sessions", "")),
        }
        accounts.append(acc)
    return accounts


def rebuild_action_items(rows: list[dict]) -> list[dict]:
    """Direct mapping; blank accountId and deadline → null."""
    items = []
    for row in rows:
        item = {
            "id":          row.get("id", "").strip(),
            "partner":     row.get("partner", "").strip(),
            "accountName": row.get("accountName", "").strip(),
            "accountId":   _to_null(row.get("accountId", "")),
            "sessionDate": row.get("sessionDate", "").strip(),
            "action":      row.get("action", "").strip(),
            "owner":       row.get("owner", "").strip(),
            "deadline":    _to_null(row.get("deadline", "")),
            "status":      row.get("status", "").strip(),
        }
        items.append(item)
    return items


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def convert(csv_dir: str, output_path: str | None = None) -> None:
    src = Path(csv_dir)

    partners_file    = src / "partners.csv"
    accounts_file    = src / "accounts.csv"
    action_items_file = src / "action_items.csv"

    # Validate inputs
    missing = [f for f in [partners_file, accounts_file, action_items_file] if not f.exists()]
    if missing:
        print("ERROR: Missing CSV files:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)

    print(f"\nSource dir : {src}")

    partners_rows    = read_csv(partners_file)
    accounts_rows    = read_csv(accounts_file)
    action_items_rows = read_csv(action_items_file)

    print(f"  partners.csv      : {len(partners_rows)} rows")
    print(f"  accounts.csv      : {len(accounts_rows)} rows")
    print(f"  action_items.csv  : {len(action_items_rows)} rows")

    master = {
        "meta": {
            "version":      "1.0",
            "lastUpdated":  str(date.today()),
            "inrUnit":      "Lakhs",
            "eurUnit":      "Thousands",
            "_note":        "Reconstructed from CSV export.",
        },
        "partners":    rebuild_partners(partners_rows),
        "accounts":    rebuild_accounts(accounts_rows),
        "actionItems": rebuild_action_items(action_items_rows),
    }

    out = Path(output_path) if output_path else src / "master_data_reconstructed.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(master, fh, indent=2, ensure_ascii=False)

    print(f"\nOutput     : {out}")
    print(f"  Partners    : {len(master['partners'])}")
    print(f"  Accounts    : {len(master['accounts'])}")
    print(f"  ActionItems : {len(master['actionItems'])}")
    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python csv_to_json.py <csv_dir> [output.json]")
        sys.exit(1)

    convert(
        csv_dir=sys.argv[1],
        output_path=sys.argv[2] if len(sys.argv) > 2 else None,
    )
