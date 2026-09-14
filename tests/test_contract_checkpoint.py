"""Tests for the contract checkpoint engine.

Part 1 tests the seeded sample data. The expected status for each use case in
data/ai_use_case_register.csv was hand-calculated against
data/customer_contract_register.csv and data/ai_tool_data_terms.csv before
these assertions were written -- see the README for the worked-out reasoning
behind each one. These are not "whatever the code currently outputs" tests;
each seeded use case is a deliberate, documented exception and must keep
failing (or passing) for the stated reason.

Part 2 tests the engine itself against synthetic rows, independent of
data/. These exist so that fail-closed behaviour on messy real-world input
(blank cells, alternate spellings of yes/no, non-ISO dates, unknown
customers or tools, duplicate keys, a BOM, a missing column) is a locked-in
regression, not an implementation detail someone can quietly break while
making the sample data prettier.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import contract_checkpoint as cc  # noqa: E402
from contract_checkpoint import evaluate_use_case, load_rows, run_all  # noqa: E402

REPO_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def _reset_data_dir():
    # main() mutates the module-level DATA_DIR; make sure no test leaks that
    # into another test's run_all() call.
    cc.DATA_DIR = REPO_DATA_DIR
    yield
    cc.DATA_DIR = REPO_DATA_DIR


def results_by_id():
    return {r["use_case_id"]: r for r in run_all()}


# --- Part 1: seeded sample data ---------------------------------------------


def test_ten_use_cases_load():
    results = results_by_id()
    assert len(results) == 10


def test_uc01_blocked_no_contract_review():
    # Contract restrictions were never reviewed, and the contract also
    # requires disclosure that was never given -- two independent BLOCK
    # reasons on the same workflow.
    r = results_by_id()["UC-01"]
    assert r["status"] == "BLOCK"
    assert any("never reviewed" in reason for reason in r["reasons"])
    assert any("disclosure" in reason.lower() for reason in r["reasons"])


def test_uc02_blocked_missing_disclosure():
    # Reviewed, but the contract requires disclosure before AI use and none
    # was recorded.
    r = results_by_id()["UC-02"]
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "disclosure" in r["reasons"][0].lower()


def test_uc03_blocked_training_conflict():
    # The tool trains on inputs by default, the contract prohibits training
    # on this customer's data, and the enterprise protection is not enabled.
    r = results_by_id()["UC-03"]
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "trains on inputs by default" in r["reasons"][0]


def test_uc04_review_human_in_loop_not_sufficient():
    # A human makes the final decision, but the contract limits AI *support*
    # for this decision type -- human review does not resolve that on its
    # own, so this is REVIEW, not a clean pass and not a BLOCK.
    r = results_by_id()["UC-04"]
    assert r["status"] == "REVIEW"
    assert len(r["reasons"]) == 1
    assert "human review does not by itself satisfy" in r["reasons"][0]


def test_uc05_re_review_contract_renewed_after_approval():
    # The contract was renewed on 2026-08-01; this workflow was approved
    # earlier, on 2026-06-01. The approval predates the renewal.
    r = results_by_id()["UC-05"]
    assert r["status"] == "RE-REVIEW"
    assert len(r["reasons"]) == 1
    assert "renewed" in r["reasons"][0]


def test_uc06_passes_clean():
    # No contract restrictions, disclosure not required, no training
    # conflict, no restricted decision, and the contract has not changed
    # since approval. Included so the report is not all red.
    r = results_by_id()["UC-06"]
    assert r["status"] == "PASS"
    assert r["reasons"] == []


def test_uc07_blocked_tool_cannot_disable_training():
    # DraftPilot Free trains by default and can't disable training at any
    # tier, so no enterprise upgrade could ever fix this -- a stronger BLOCK
    # than the "enterprise tier not enabled" case in UC-03.
    r = results_by_id()["UC-07"]
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "cannot disable training at any tier" in r["reasons"][0]


def test_uc08_blocked_restricted_decision_without_human_review():
    # Same contractual restriction as UC-04, but with no human review at
    # all -- nothing catches what the AI gets wrong, so this is BLOCK,
    # not REVIEW.
    r = results_by_id()["UC-08"]
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "no recorded human review" in r["reasons"][0]


def test_uc09_review_subcontractor_flow_down():
    # The contract requires subcontractor flow-down terms and the tool
    # retains customer inputs -- a real exposure that this join can flag
    # but not resolve on its own.
    r = results_by_id()["UC-09"]
    assert r["status"] == "REVIEW"
    assert len(r["reasons"]) == 1
    assert "flow-down" in r["reasons"][0]


def test_uc10_blocked_unknown_customer():
    # C9 is not in the contract register at all. This must be a finding,
    # not a KeyError that aborts the whole run.
    r = results_by_id()["UC-10"]
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "No contract abstract exists" in r["reasons"][0]


def test_exception_mix_matches_hand_calculation():
    # 6 BLOCK, 2 REVIEW, 1 RE-REVIEW, 1 PASS -- the mix documented in the
    # README.
    statuses = [r["status"] for r in run_all()]
    assert statuses.count("BLOCK") == 6
    assert statuses.count("REVIEW") == 2
    assert statuses.count("RE-REVIEW") == 1
    assert statuses.count("PASS") == 1


# --- Part 2: engine behaviour on synthetic, off-nominal input ---------------

BASE_CONTRACT = {
    "customer_id": "T1",
    "customer_name": "Test Customer",
    "contract_type": "MSA",
    "ai_restrictions": "Yes",
    "disclosure_required": "No",
    "training_prohibited": "No",
    "automated_decision_limits": "No",
    "subcontractor_flow_down": "No",
    "effective_date": "2024-01-01",
    "last_renewed_date": "2024-01-01",
}

BASE_TOOL = {
    "tool": "TestTool",
    "retains_inputs": "No",
    "trains_by_default": "No",
    "can_disable_training": "NA",
    "enterprise_tier_enabled": "Yes",
}

BASE_USE_CASE = {
    "use_case_id": "T-01",
    "name": "Test Workflow",
    "owner": "Test Owner",
    "tool": "TestTool",
    "customer_id": "T1",
    "data_categories": "Test data",
    "human_review": "Yes",
    "ai_supports_restricted_decision": "No",
    "disclosure_given": "NA",
    "contract_restrictions_reviewed": "Yes",
    "approval_date": "2024-06-01",
}


def _evaluate(use_case_overrides=None, contract_overrides=None, tool_overrides=None):
    use_case = {**BASE_USE_CASE, **(use_case_overrides or {})}
    contract = {**BASE_CONTRACT, **(contract_overrides or {})}
    tool = {**BASE_TOOL, **(tool_overrides or {})}
    return evaluate_use_case(use_case, {contract["customer_id"]: contract}, {tool["tool"]: tool})


@pytest.mark.parametrize("value", ["", "NA", "Pending", "Unknown", "no", " No "])
def test_unreviewed_variants_all_block(value):
    # Any spelling other than an explicit "Yes" -- including blank -- is
    # treated as not reviewed. A blank cell must not read as a clean pass.
    r = _evaluate({"contract_restrictions_reviewed": value})
    assert r["status"] == "BLOCK"
    assert any("review" in reason.lower() for reason in r["reasons"])


def test_unknown_customer_is_a_finding_not_a_crash():
    r = evaluate_use_case(
        {**BASE_USE_CASE, "customer_id": "NOPE"},
        {"T1": BASE_CONTRACT},
        {"TestTool": BASE_TOOL},
    )
    assert r["status"] == "BLOCK"
    assert "No contract abstract exists" in r["reasons"][0]


def test_unknown_tool_is_a_finding_not_a_crash():
    r = evaluate_use_case(
        {**BASE_USE_CASE, "tool": "NOPE"},
        {"T1": BASE_CONTRACT},
        {"TestTool": BASE_TOOL},
    )
    assert r["status"] == "BLOCK"
    assert "No data-use terms are on file" in r["reasons"][0]


def test_can_disable_training_no_yields_single_stronger_reason():
    r = _evaluate(
        contract_overrides={"training_prohibited": "Yes"},
        tool_overrides={"trains_by_default": "Yes", "can_disable_training": "No"},
    )
    assert r["status"] == "BLOCK"
    assert len(r["reasons"]) == 1
    assert "cannot disable training at any tier" in r["reasons"][0]


def test_malformed_date_raises_clear_error():
    with pytest.raises(ValueError, match="approval_date"):
        _evaluate({"approval_date": "6/1/2024"})


def test_blank_renewal_date_raises_instead_of_silently_passing():
    with pytest.raises(ValueError, match="last_renewed_date"):
        _evaluate(contract_overrides={"last_renewed_date": ""})


def test_effective_date_after_approval_triggers_re_review():
    # last_renewed_date predates the approval (so check 5's renewal branch
    # doesn't fire), but effective_date postdates it -- isolating the
    # "approved before the contract took effect" branch.
    r = _evaluate(
        {"approval_date": "2023-12-01"},
        contract_overrides={"effective_date": "2024-01-01", "last_renewed_date": "2023-01-01"},
    )
    assert r["status"] == "RE-REVIEW"
    assert "took effect" in r["reasons"][0]


def test_duplicate_key_raises(tmp_path):
    path = tmp_path / "dupes.csv"
    path.write_text(
        "customer_id,customer_name\nD1,First\nD1,Second\n", encoding="utf-8"
    )
    cc.DATA_DIR = tmp_path
    with pytest.raises(ValueError, match="duplicate"):
        load_rows("dupes.csv", "customer_id")


def test_bom_header_loads_cleanly(tmp_path):
    path = tmp_path / "customer_contract_register.csv"
    header = ",".join(BASE_CONTRACT.keys())
    row = ",".join(BASE_CONTRACT.values())
    path.write_text(f"﻿{header}\n{row}\n", encoding="utf-8")
    cc.DATA_DIR = tmp_path
    rows = load_rows("customer_contract_register.csv", "customer_id")
    assert "customer_id" in rows["T1"]  # not '﻿customer_id'


def test_missing_required_column_raises(tmp_path):
    path = tmp_path / "customer_contract_register.csv"
    path.write_text("customer_id,customer_name\nT1,Test\n", encoding="utf-8")
    cc.DATA_DIR = tmp_path
    with pytest.raises(ValueError, match="missing required column"):
        load_rows("customer_contract_register.csv", "customer_id")


def test_main_exit_code_1_on_block(tmp_path, capsys):
    _write_minimal_register_set(tmp_path, disclosure_given="No", disclosure_required="Yes")
    code = cc.main(["--data-dir", str(tmp_path), "--quiet"])
    assert code == 1


def test_main_exit_code_0_when_all_pass(tmp_path, capsys):
    _write_minimal_register_set(tmp_path, disclosure_given="NA", disclosure_required="No")
    code = cc.main(["--data-dir", str(tmp_path), "--quiet"])
    assert code == 0


def test_main_json_report_has_evidence_fields(tmp_path):
    _write_minimal_register_set(tmp_path, disclosure_given="NA", disclosure_required="No")
    report_path = tmp_path / "report.json"
    cc.main(["--data-dir", str(tmp_path), "--quiet", "--json", str(report_path)])
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert "run_at" in payload
    assert set(payload["file_sha256"]) == {
        "ai_use_case_register.csv",
        "customer_contract_register.csv",
        "ai_tool_data_terms.csv",
    }
    assert payload["counts"]["PASS"] == 1
    assert len(payload["results"]) == 1


def _write_minimal_register_set(tmp_path, *, disclosure_given, disclosure_required):
    (tmp_path / "ai_use_case_register.csv").write_text(
        "use_case_id,name,owner,tool,customer_id,data_categories,human_review,"
        "ai_supports_restricted_decision,disclosure_given,"
        "contract_restrictions_reviewed,approval_date\n"
        f"T-01,Test,Owner,TestTool,T1,data,Yes,No,{disclosure_given},Yes,2024-06-01\n",
        encoding="utf-8",
    )
    (tmp_path / "customer_contract_register.csv").write_text(
        "customer_id,customer_name,contract_type,ai_restrictions,disclosure_required,"
        "training_prohibited,automated_decision_limits,subcontractor_flow_down,"
        "effective_date,last_renewed_date\n"
        f"T1,Test Customer,MSA,Yes,{disclosure_required},No,No,No,2024-01-01,2024-01-01\n",
        encoding="utf-8",
    )
    (tmp_path / "ai_tool_data_terms.csv").write_text(
        "tool,retains_inputs,trains_by_default,can_disable_training,enterprise_tier_enabled\n"
        "TestTool,No,No,NA,Yes\n",
        encoding="utf-8",
    )
