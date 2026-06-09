"""
json_to_csv.py — Export master pipeline JSON to CSV files.

Generates three CSVs from the master pipeline JSON:
  partners.csv      — one row per contact (partner fields repeated)
  accounts.csv      — one row per account  (brand array pipe-joined; sessions excluded)
  action_items.csv  — one row per action item (flat)

Usage:
    python json_to_csv.py <master.json> [output_dir]

If output_dir is omitted, CSVs are written alongside the master JSON.
Files are UTF-8 with BOM so Excel opens them correctly on Windows.
"""

import csv
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Flatteners
# ---------------------------------------------------------------------------

def flatten_partners(partners: list) -> list[dict]:
    """
    One row per contact.
    Partners that have no contacts still produce one row (contact fields empty).
    """
    rows = []
    for p in partners:
        base = {
            "partner_id":   p.get("id", ""),
            "fullName":     p.get("fullName", ""),
            "cadence":      p.get("cadence", ""),
        }
        contacts = p.get("contacts") or []
        if contacts:
            for c in contacts:
                row = dict(base)
                row["contact_name"]      = c.get("name", "")
                row["contact_email"]     = c.get("email", "")
                row["contact_mobile"]    = c.get("mobile", "")
                row["supportedRegions"]  = "|".join(c.get("supportedRegions") or [])
                rows.append(row)
        else:
            row = dict(base)
            row["contact_name"]      = ""
            row["contact_email"]     = ""
            row["contact_mobile"]    = ""
            row["supportedRegions"]  = ""
            rows.append(row)
    return rows


def flatten_accounts(accounts: list) -> list[dict]:
    """
    One row per account.
    - brand      : pipe-joined list  (e.g. "ENOVIA|DELMIA")
    - sessions   : excluded (latestUpdate + lastDiscussed carry the summary)
    - Null values: written as empty string
    """
    rows = []
    for a in accounts:
        row = {
            "id":                 a.get("id", ""),
            "partner":            a.get("partner", ""),
            "accountName":        a.get("accountName", ""),
            "accountURL":         a.get("accountURL") or "",
            "city":               a.get("city", ""),
            "region":             a.get("region", ""),
            "partnerSalesOwner":  a.get("partnerSalesOwner", ""),
            "techOwner":          a.get("techOwner", ""),
            "brand":              "|".join(a.get("brand") or []),
            "currentStatus":      a.get("currentStatus", ""),
            "targetMonth":        a.get("targetMonth") or "",
            "targetYear":         a.get("targetYear") or "",
            "oppValue":           a.get("oppValue") or "",
            "oppValueUOM":        a.get("oppValueUOM", ""),
            "deploymentModel":    a.get("deploymentModel", ""),
            "competition":        a.get("competition") or "",
            "latestUpdate":       a.get("latestUpdate", ""),
            "lastDiscussed":      a.get("lastDiscussed", ""),
            "sessionCount":       len(a.get("sessions") or []),
        }
        rows.append(row)
    return rows


def flatten_action_items(action_items: list) -> list[dict]:
    """Flat structure — direct field mapping."""
    rows = []
    for a in action_items:
        row = {
            "id":           a.get("id", ""),
            "partner":      a.get("partner", ""),
            "accountName":  a.get("accountName", ""),
            "accountId":    a.get("accountId") or "",
            "sessionDate":  a.get("sessionDate", ""),
            "action":       a.get("action", ""),
            "owner":        a.get("owner", ""),
            "deadline":     a.get("deadline") or "",
            "status":       a.get("status", ""),
        }
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], output_path: Path) -> None:
    if not rows:
        print(f"  [SKIP] No data for {output_path.name}")
        return
    with open(output_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [OK]   {output_path.name}  ({len(rows)} rows)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_csvs(master_json_path: str, output_dir: str | None = None) -> None:
    src = Path(master_json_path)
    out = Path(output_dir) if output_dir else src.parent
    out.mkdir(parents=True, exist_ok=True)

    with open(src, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    print(f"\nSource : {src}")
    print(f"Output : {out}\n")

    write_csv(flatten_partners(data.get("partners", [])),       out / "partners.csv")
    write_csv(flatten_accounts(data.get("accounts", [])),       out / "accounts.csv")
    write_csv(flatten_action_items(data.get("actionItems", [])), out / "action_items.csv")

    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python json_to_csv.py <master.json> [output_dir]")
        sys.exit(1)

    generate_csvs(
        master_json_path=sys.argv[1],
        output_dir=sys.argv[2] if len(sys.argv) > 2 else None,
    )
