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
"""

import csv
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Severity order, highest first. A use case's final status is the most severe
# outcome triggered by any single check -- it is not an average and it is not
# a vote.
SEVERITY_ORDER = ["BLOCK", "REVIEW", "RE-REVIEW", "PASS"]


def _severity_rank(status):
    return SEVERITY_ORDER.index(status)


def load_rows(filename, key_field):
    """Load a CSV from the data directory into a dict keyed by `key_field`."""
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8") as f:
        return {row[key_field]: row for row in csv.DictReader(f)}


def load_use_cases(filename="ai_use_case_register.csv"):
    path = DATA_DIR / filename
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate_use_case(use_case, contracts_by_id, tools_by_name):
    """Evaluate one AI use case against its customer's contract and its
    tool's data-use terms. Returns a dict with the use case id, the final
    status, and the list of reasons that produced it.

    Each check below corresponds to one of the six controls in the article's
    "Practical Ways to Reduce the Risk" section. A use case can trigger more
    than one reason; the final status is the most severe one triggered.
    """
    contract = contracts_by_id[use_case["customer_id"]]
    tool = tools_by_name[use_case["tool"]]
    reasons = []

    # 1. The contract checkpoint itself: was this workflow ever checked
    # against the customer's contract at all?
    if use_case["contract_restrictions_reviewed"] == "No":
        reasons.append((
            "BLOCK",
            "Contract restrictions were never reviewed for this workflow "
            "before it was deployed.",
        ))

    # 2. Disclosure: the contract requires notice before AI is used, and none
    # was recorded.
    if contract["disclosure_required"] == "Yes" and use_case["disclosure_given"] != "Yes":
        reasons.append((
            "BLOCK",
            f"{contract['customer_name']}'s contract requires disclosure "
            "before AI is used in connection with the Services, and no "
            "disclosure was recorded for this workflow.",
        ))

    # 3. Processing vs. training: the contract prohibits training on this
    # customer's data, and the tool trains on inputs by default with no
    # enterprise-tier protection enabled to turn that off.
    if (
        contract["training_prohibited"] == "Yes"
        and tool["trains_by_default"] == "Yes"
        and tool["enterprise_tier_enabled"] != "Yes"
    ):
        reasons.append((
            "BLOCK",
            f"{use_case['tool']} trains on inputs by default, "
            f"{contract['customer_name']}'s contract prohibits training on "
            "their data, and the enterprise protection that disables "
            "training is not enabled.",
        ))

    # 4. Human review is not a universal solvent: the contract limits AI
    # support for certain decisions, and this workflow's AI narrows down
    # what a human reviews -- even though a human still signs off.
    if (
        contract["automated_decision_limits"] == "Yes"
        and use_case["ai_supports_restricted_decision"] == "Yes"
    ):
        reasons.append((
            "REVIEW",
            f"{contract['customer_name']}'s contract limits AI support for "
            "this type of decision. A human makes the final call, but the "
            "AI still determines what the human sees -- human review does "
            "not by itself satisfy this restriction.",
        ))

    # 5. Approval is not permanent: the contract was renewed after this
    # workflow was approved, so the approval predates whatever the renewal
    # changed.
    if contract["last_renewed_date"] > use_case["approval_date"]:
        reasons.append((
            "RE-REVIEW",
            f"{contract['customer_name']}'s contract was renewed on "
            f"{contract['last_renewed_date']}, after this workflow was "
            f"approved on {use_case['approval_date']}. The approval predates "
            "the renewal and should be re-reviewed against the current "
            "contract.",
        ))

    if reasons:
        status = min((r[0] for r in reasons), key=_severity_rank)
    else:
        status = "PASS"

    return {
        "use_case_id": use_case["use_case_id"],
        "name": use_case["name"],
        "customer_name": contracts_by_id[use_case["customer_id"]]["customer_name"],
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


if __name__ == "__main__":
    _print_report(run_all())
