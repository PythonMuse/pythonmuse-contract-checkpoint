"""Tests for the contract checkpoint engine.

The expected status for each use case in data/ai_use_case_register.csv was
hand-calculated against data/customer_contract_register.csv and
data/ai_tool_data_terms.csv before these assertions were written -- see the
README for the worked-out reasoning behind each one. These are not "whatever
the code currently outputs" tests; each seeded use case is a deliberate,
documented exception and must keep failing (or passing) for the stated
reason.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from contract_checkpoint import run_all  # noqa: E402


def results_by_id():
    return {r["use_case_id"]: r for r in run_all()}


def test_six_use_cases_load():
    results = results_by_id()
    assert len(results) == 6


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


def test_exception_mix_matches_hand_calculation():
    # 3 BLOCK, 1 REVIEW, 1 RE-REVIEW, 1 PASS -- the mix documented in the
    # README and in Article 38's "Practical Ways to Reduce the Risk".
    statuses = [r["status"] for r in run_all()]
    assert statuses.count("BLOCK") == 3
    assert statuses.count("REVIEW") == 1
    assert statuses.count("RE-REVIEW") == 1
    assert statuses.count("PASS") == 1
