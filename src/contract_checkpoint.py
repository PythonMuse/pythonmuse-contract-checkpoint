"""The contract checkpoint: cross-reference the AI use-case register against
the customer contract register and the AI tool data-terms register, and flag
any workflow that internal governance approved but the applicable customer
contract may not permit.

This is the control described in PythonMuse Article 38, "Your AI Workflow Was
Approved. Did Anyone Read the Customer Contract?" -- implemented as a small,
readable join, not a black box. See the README for what each exception means
and why the sample data is deliberately seeded to trigger them.

Run from the repository root:
    python src/contract_checkpoint.py
    python src/contract_checkpoint.py --data-dir path/to/your/export --json report.json
"""

import argparse
import csv
import hashlib
import sys
from datetime import date, datetime, timezone
from pathlib import Path

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Severity order, highest first. A use case's final status is the most severe
# outcome triggered by any single check -- it is not an average and it is not
# a vote.
SEVERITY_ORDER = ["BLOCK", "REVIEW", "RE-REVIEW", "PASS"]

# Columns each register must have. Checked at load time so a malformed or
# renamed-column export fails with one clear message instead of a KeyError
# raised mid-evaluation on whichever row happens to hit the missing field
# first.
REQUIRED_COLUMNS = {
    "ai_use_case_register.csv": [
        "use_case_id", "name", "owner", "tool", "customer_id",
        "data_categories", "human_review", "ai_supports_restricted_decision",
        "disclosure_given", "contract_restrictions_reviewed", "approval_date",
    ],
    "customer_contract_register.csv": [
        "customer_id", "customer_name", "contract_type", "ai_restrictions",
        "disclosure_required", "training_prohibited",
        "automated_decision_limits", "subcontractor_flow_down",
        "effective_date", "last_renewed_date",
    ],
    "ai_tool_data_terms.csv": [
        "tool", "retains_inputs", "trains_by_default",
        "can_disable_training", "enterprise_tier_enabled",
    ],
}

_YES = {"yes", "y", "true", "1"}
_NO = {"no", "n", "false", "0"}
_NA = {"na", "n/a", "-", ""}


def _flag(value):
    """Normalise a register cell to 'yes', 'no', 'na', or 'unknown'.

    Blank cells and anything that isn't a recognised yes/no/NA spelling map
    to 'unknown' rather than being silently treated as 'no'. Every check
    below decides explicitly what 'unknown' means for that check -- usually
    the unfavourable outcome, because a governance control that fails open
    on a blank cell is worse than one that over-flags.
    """
    v = (value or "").strip().lower()
    if v in _YES:
        return "yes"
    if v in _NO:
        return "no"
    if v in _NA:
        return "na"
    return "unknown"


def _severity_rank(status):
    return SEVERITY_ORDER.index(status)


def _date(value, *, file, row_id, field):
    """Parse an ISO (YYYY-MM-DD) date cell, raising a clear error naming the
    file, row, and column on anything else -- including a blank cell, which
    a raw string comparison would otherwise silently mishandle.
    """
    v = (value or "").strip()
    try:
        return date.fromisoformat(v)
    except ValueError:
        raise ValueError(
            f"{file}, row {row_id!r}: column {field!r} is {value!r}, "
            "expected an ISO date (YYYY-MM-DD)."
        ) from None


def load_rows(filename, key_field):
    """Load a CSV from the data directory into a dict keyed by `key_field`.

    Validates that every required column is present, and raises if the same
    key appears twice -- a silent last-row-wins overwrite is exactly the kind
    of data error a governance join must not hide.
    """
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        _check_columns(filename, reader.fieldnames)
        rows = {}
        for row in reader:
            key = row[key_field]
            if key in rows:
                raise ValueError(
                    f"{filename}: duplicate {key_field}={key!r}. Each row "
                    "must have a unique key; fix the source export."
                )
            rows[key] = row
        return rows


def load_use_cases(filename="ai_use_case_register.csv"):
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        _check_columns(filename, reader.fieldnames)
        return list(reader)


def _check_columns(filename, fieldnames):
    required = REQUIRED_COLUMNS.get(filename)
    if required is None:
        return
    present = set(fieldnames or [])
    missing = [c for c in required if c not in present]
    if missing:
        raise ValueError(
            f"{filename} is missing required column(s): {', '.join(missing)}. "
            f"Expected: {', '.join(required)}."
        )


def evaluate_use_case(use_case, contracts_by_id, tools_by_name):
    """Evaluate one AI use case against its customer's contract and its
    tool's data-use terms. Returns a dict with the use case id, the final
    status, and the list of reasons that produced it.

    Each check below corresponds to a control in the article's "Practical
    Ways to Reduce the Risk" section. A use case can trigger more than one
    reason; the final status is the most severe one triggered.
    """
    use_case_id = use_case["use_case_id"]
    contract = contracts_by_id.get(use_case["customer_id"])
    tool = tools_by_name.get(use_case["tool"])
    reasons = []

    # 0. Referential integrity: this workflow names a customer or tool that
    # isn't in the other registers at all. There is nothing to cross-check
    # it against, which is itself the finding -- not a crash.
    if contract is None:
        reasons.append((
            "BLOCK",
            f"No contract abstract exists for customer "
            f"{use_case['customer_id']!r}. This workflow cannot be checked "
            "against a contract that isn't in the register.",
        ))
    if tool is None:
        reasons.append((
            "BLOCK",
            f"No data-use terms are on file for tool {use_case['tool']!r}. "
            "This workflow cannot be checked against terms that aren't in "
            "the register.",
        ))
    if contract is None or tool is None:
        status = min((r[0] for r in reasons), key=_severity_rank)
        return {
            "use_case_id": use_case_id,
            "name": use_case["name"],
            "customer_name": contract["customer_name"] if contract else use_case["customer_id"],
            "status": status,
            "reasons": [r[1] for r in reasons],
        }

    reviewed = _flag(use_case["contract_restrictions_reviewed"])
    disclosure_required = _flag(contract["disclosure_required"])
    disclosure_given = _flag(use_case["disclosure_given"])
    training_prohibited = _flag(contract["training_prohibited"])
    trains_by_default = _flag(tool["trains_by_default"])
    can_disable_training = _flag(tool["can_disable_training"])
    enterprise_tier_enabled = _flag(tool["enterprise_tier_enabled"])
    decision_limits = _flag(contract["automated_decision_limits"])
    restricted_decision = _flag(use_case["ai_supports_restricted_decision"])
    human_review = _flag(use_case["human_review"])
    flow_down = _flag(contract["subcontractor_flow_down"])
    retains_inputs = _flag(tool["retains_inputs"])

    # 1. The contract checkpoint itself: was this workflow ever checked
    # against the customer's contract at all? A blank or unrecognised value
    # is treated the same as "No" -- an un-reviewed workflow is un-reviewed
    # whether that was recorded explicitly or just never filled in.
    if reviewed != "yes":
        if reviewed == "no":
            detail = "were never reviewed"
        else:
            detail = "have no recorded review status"
        reasons.append((
            "BLOCK",
            f"Contract restrictions {detail} for this workflow before it "
            "was deployed.",
        ))

    # 2. Disclosure: the contract requires notice before AI is used, and none
    # was recorded.
    if disclosure_required == "yes" and disclosure_given != "yes":
        reasons.append((
            "BLOCK",
            f"{contract['customer_name']}'s contract requires disclosure "
            "before AI is used in connection with the Services, and no "
            "disclosure was recorded for this workflow.",
        ))

    # 3. Processing vs. training: the contract prohibits training on this
    # customer's data, and the tool trains on inputs by default. If the tool
    # can never disable training, no tier can fix that -- a stronger finding
    # than the enterprise-tier gap below, and mutually exclusive with it.
    if training_prohibited == "yes" and trains_by_default == "yes":
        if can_disable_training == "no":
            reasons.append((
                "BLOCK",
                f"{use_case['tool']} trains on inputs by default and cannot "
                "disable training at any tier, but "
                f"{contract['customer_name']}'s contract prohibits training "
                "on their data.",
            ))
        elif enterprise_tier_enabled != "yes":
            reasons.append((
                "BLOCK",
                f"{use_case['tool']} trains on inputs by default, "
                f"{contract['customer_name']}'s contract prohibits training "
                "on their data, and the enterprise protection that disables "
                "training is not enabled.",
            ))

    # 4. Human review is not a universal solvent: the contract limits AI
    # support for certain decisions. With human review, a human still makes
    # the final call, but the AI narrows what they see -- REVIEW, not a
    # clean pass. Without human review, nothing stands between the
    # restricted AI output and the customer -- BLOCK, not REVIEW.
    if decision_limits == "yes" and restricted_decision == "yes":
        if human_review == "yes":
            reasons.append((
                "REVIEW",
                f"{contract['customer_name']}'s contract limits AI support "
                "for this type of decision. A human makes the final call, "
                "but the AI still determines what the human sees -- human "
                "review does not by itself satisfy this restriction.",
            ))
        else:
            reasons.append((
                "BLOCK",
                f"{contract['customer_name']}'s contract limits AI support "
                "for this type of decision, and this workflow has no "
                "recorded human review to catch what the AI gets wrong.",
            ))

    # 5. Approval is not permanent, in either direction. If the contract was
    # renewed after this workflow was approved, the approval predates
    # whatever the renewal changed. If the workflow was somehow approved
    # before the contract now in force even took effect, that is a data
    # ordering problem needing the same re-review.
    last_renewed = _date(
        contract["last_renewed_date"], file="customer_contract_register.csv",
        row_id=contract["customer_id"], field="last_renewed_date",
    )
    effective = _date(
        contract["effective_date"], file="customer_contract_register.csv",
        row_id=contract["customer_id"], field="effective_date",
    )
    approved = _date(
        use_case["approval_date"], file="ai_use_case_register.csv",
        row_id=use_case_id, field="approval_date",
    )
    if last_renewed > approved:
        reasons.append((
            "RE-REVIEW",
            f"{contract['customer_name']}'s contract was renewed on "
            f"{contract['last_renewed_date']}, after this workflow was "
            f"approved on {use_case['approval_date']}. The approval predates "
            "the renewal and should be re-reviewed against the current "
            "contract.",
        ))
    elif effective > approved:
        reasons.append((
            "RE-REVIEW",
            f"{contract['customer_name']}'s current contract took effect on "
            f"{contract['effective_date']}, after this workflow was "
            f"approved on {use_case['approval_date']}. The approval predates "
            "the contract it is supposed to comply with.",
        ))

    # 6. Subcontractor flow-down: the contract requires AI vendors to be
    # bound by the same terms, and the tool retains customer inputs. That
    # combination needs a human check that the vendor is actually covered --
    # it isn't something this join alone can confirm or deny.
    if flow_down == "yes" and retains_inputs == "yes":
        reasons.append((
            "REVIEW",
            f"{use_case['tool']} retains inputs, and "
            f"{contract['customer_name']}'s contract requires subcontractor "
            "flow-down terms for any vendor that processes their data. "
            "Confirm the AI vendor's terms actually flow down before relying "
            "on this workflow.",
        ))

    if reasons:
        status = min((r[0] for r in reasons), key=_severity_rank)
    else:
        status = "PASS"

    return {
        "use_case_id": use_case_id,
        "name": use_case["name"],
        "customer_name": contract["customer_name"],
        "status": status,
        "reasons": [r[1] for r in reasons],
    }


def run_all(
    use_cases_file="ai_use_case_register.csv",
    contracts_file="customer_contract_register.csv",
    tools_file="ai_tool_data_terms.csv",
):
    use_cases = load_use_cases(use_cases_file)
    contracts_by_id = load_rows(contracts_file, "customer_id")
    tools_by_name = load_rows(tools_file, "tool")
    return [
        evaluate_use_case(uc, contracts_by_id, tools_by_name) for uc in use_cases
    ]


def _print_report(results):
    for r in results:
        print(f"{r['use_case_id']}  {r['status']:<10} {r['name']} ({r['customer_name']})")
        for reason in r["reasons"]:
            print(f"    - {reason}")


def _file_hashes(data_dir, filenames):
    hashes = {}
    for filename in filenames:
        path = data_dir / filename
        hashes[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _write_json(path, results, data_dir):
    import json

    filenames = [
        "ai_use_case_register.csv",
        "customer_contract_register.csv",
        "ai_tool_data_terms.csv",
    ]
    counts = {status: 0 for status in SEVERITY_ORDER}
    for r in results:
        counts[r["status"]] += 1
    payload = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_dir),
        "file_sha256": _file_hashes(data_dir, filenames),
        "counts": counts,
        "results": results,
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _exit_code(results, fail_on):
    statuses = {r["status"] for r in results}
    if fail_on == "never":
        return 0
    if fail_on == "review":
        return 1 if statuses & {"BLOCK", "REVIEW", "RE-REVIEW"} else 0
    # fail_on == "block" (default)
    return 1 if "BLOCK" in statuses else 0


def main(argv=None):
    global DATA_DIR

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--data-dir", type=Path, default=DEFAULT_DATA_DIR,
        help="directory containing the three register CSVs "
             "(default: the repo's data/ directory)",
    )
    parser.add_argument(
        "--json", type=Path, default=None,
        help="write a machine-readable report (run timestamp, file hashes, "
             "counts, full results) to this path",
    )
    parser.add_argument(
        "--fail-on", choices=["block", "review", "never"], default="block",
        help="exit code 1 is returned when: 'block' (default) any use case "
             "is BLOCK; 'review' any use case is BLOCK, REVIEW, or "
             "RE-REVIEW; 'never' always exit 0",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="suppress the human-readable report on stdout",
    )
    args = parser.parse_args(argv)

    DATA_DIR = args.data_dir
    results = run_all()

    if not args.quiet:
        _print_report(results)
    if args.json:
        _write_json(args.json, results, DATA_DIR)

    return _exit_code(results, args.fail_on)


DATA_DIR = DEFAULT_DATA_DIR

if __name__ == "__main__":
    sys.exit(main())
