"""
merge_delta.py — Merge a partner delta JSON into the master pipeline JSON.

Usage:
    python merge_delta.py <master.json> <delta.json> [output.json]

If output.json is omitted, the master file is updated in-place.

Merge rules
-----------
accounts:
  - New account  : append the full object; auto-assign next sequential ID for
                   the partner (e.g. last EDS-005 in master → delta EDS-001
                   becomes EDS-006).
  - Existing acct: matched by (partner + accountName, case-insensitive).
                     Always overwrite : lastDiscussed
                     Overwrite if changed: currentStatus, targetMonth,
                       targetYear, oppValue, oppValueUOM, deploymentModel,
                       competition, latestUpdate
                     Append (dedup by date): sessions

actionItems:
  - All delta items appended; deduplicated by action-item id.
  - accountId references inside action items are remapped from delta
    provisional IDs to the authoritative master IDs.
"""

import json
import re
import sys
from pathlib import Path


# Fields updated only when the delta value differs from the master value.
CONDITIONAL_UPDATE_FIELDS = {
    "currentStatus",
    "targetMonth",
    "targetYear",
    "oppValue",
    "oppValueUOM",
    "deploymentModel",
    "competition",
    "latestUpdate",
}


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_json(data: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    print(f"Saved -> {path}")


# ---------------------------------------------------------------------------
# ID helpers
# ---------------------------------------------------------------------------

def _parse_seq(account_id: str, partner_id: str) -> int | None:
    """Return the integer sequence number from an account id, or None."""
    m = re.fullmatch(rf"{re.escape(partner_id)}-(\d+)", account_id, re.IGNORECASE)
    return int(m.group(1)) if m else None


def get_next_seq(master_accounts: list, partner_id: str) -> int:
    """Return the next available sequence number for partner_id in master."""
    seqs = [
        _parse_seq(a["id"], partner_id)
        for a in master_accounts
        if _parse_seq(a["id"], partner_id) is not None
    ]
    return max(seqs, default=0) + 1


def make_id(partner_id: str, seq: int) -> str:
    return f"{partner_id}-{seq:03d}"


# ---------------------------------------------------------------------------
# Account helpers
# ---------------------------------------------------------------------------

def find_in_master(master_accounts: list, account_name: str, partner_id: str) -> dict | None:
    """Locate an existing master account by partner + accountName (case-insensitive)."""
    key = account_name.strip().lower()
    pid = partner_id.upper()
    for acc in master_accounts:
        if acc.get("partner", "").upper() == pid and acc.get("accountName", "").strip().lower() == key:
            return acc
    return None


def merge_sessions(existing_sessions: list, new_sessions: list) -> list:
    """Append new sessions; deduplicate by date; sort chronologically."""
    seen_dates = {s["date"] for s in existing_sessions}
    merged = list(existing_sessions)
    for s in new_sessions:
        if s["date"] not in seen_dates:
            merged.append(s)
            seen_dates.add(s["date"])
    merged.sort(key=lambda s: s["date"])
    return merged


# ---------------------------------------------------------------------------
# Core merge functions
# ---------------------------------------------------------------------------

def merge_accounts(master_accounts: list, delta_accounts: list, partner_id: str) -> tuple[list, dict]:
    """
    Merge delta accounts into master_accounts.

    Returns
    -------
    master_accounts : updated list (mutated in-place)
    id_mapping      : {delta_provisional_id -> authoritative_master_id}
    """
    id_mapping: dict[str, str] = {}
    next_seq = get_next_seq(master_accounts, partner_id)

    for delta_acc in delta_accounts:
        delta_id = delta_acc["id"]
        account_name = delta_acc.get("accountName", "")

        existing = find_in_master(master_accounts, account_name, partner_id)

        if existing is None:
            # ── New account ──────────────────────────────────────────────
            new_id = make_id(partner_id, next_seq)
            next_seq += 1
            id_mapping[delta_id] = new_id

            new_acc = dict(delta_acc)
            new_acc["id"] = new_id
            master_accounts.append(new_acc)
            print(f"  [NEW]      {delta_id} -> {new_id}  '{account_name}'")

        else:
            # ── Existing account ─────────────────────────────────────────
            master_id = existing["id"]
            id_mapping[delta_id] = master_id

            # Always overwrite lastDiscussed
            existing["lastDiscussed"] = delta_acc.get("lastDiscussed", existing["lastDiscussed"])

            # Overwrite conditional fields only when value differs
            for field in CONDITIONAL_UPDATE_FIELDS:
                if field in delta_acc and delta_acc[field] != existing.get(field):
                    existing[field] = delta_acc[field]

            # Append new sessions (dedup + sort)
            existing["sessions"] = merge_sessions(
                existing.get("sessions", []),
                delta_acc.get("sessions", []),
            )

            print(f"  [UPDATED]  {delta_id} -> {master_id}  '{account_name}'")

    return master_accounts, id_mapping


def merge_action_items(master_actions: list, delta_actions: list, id_mapping: dict) -> list:
    """
    Append delta action items to master.
    - Remaps accountId using id_mapping.
    - Deduplicates by action-item id.
    """
    existing_ids = {a["id"] for a in master_actions}

    added = 0
    for action in delta_actions:
        if action["id"] in existing_ids:
            continue  # already present (idempotent re-run guard)

        item = dict(action)

        # Remap provisional accountId → authoritative master id
        old_ref = item.get("accountId")
        if old_ref and old_ref in id_mapping:
            item["accountId"] = id_mapping[old_ref]

        master_actions.append(item)
        existing_ids.add(item["id"])
        added += 1

    print(f"  {added} action item(s) appended")
    return master_actions


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def merge(master_path: str, delta_path: str, output_path: str | None = None) -> None:
    master = load_json(master_path)
    delta  = load_json(delta_path)

    partner_id   = delta["meta"]["partner"]
    session_date = delta["meta"]["sessionDate"]

    print(f"\n{'='*60}")
    print(f"Partner  : {partner_id}  ({delta['meta'].get('partnerFullName', '')})")
    print(f"Session  : {session_date}")
    print(f"Accounts in delta      : {len(delta.get('accounts', []))}")
    print(f"Action items in delta  : {len(delta.get('actionItems', []))}")
    print(f"{'='*60}\n")

    print("-- Accounts --")
    master["accounts"], id_mapping = merge_accounts(
        master["accounts"],
        delta.get("accounts", []),
        partner_id,
    )

    print("\n-- Action Items --")
    master["actionItems"] = merge_action_items(
        master["actionItems"],
        delta.get("actionItems", []),
        id_mapping,
    )

    save_json(master, output_path or master_path)
    print("\nDone.")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python merge_delta.py <master.json> <delta.json> [output.json]")
        sys.exit(1)

    master_arg = sys.argv[1]
    delta_arg  = sys.argv[2]
    output_arg = sys.argv[3] if len(sys.argv) > 3 else None

    merge(master_arg, delta_arg, output_arg)
