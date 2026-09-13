# PythonMuse Contract Checkpoint

A small, runnable companion to PythonMuse Article 38, [Your AI Workflow Was Approved. Did Anyone Read the Customer Contract?](https://github.com/PythonMuse/ai-ledger/blob/main/articles/38-ai-workflow-customer-contract/README.md)

An AI workflow can pass every internal control your organization has -- documented use case, limited access, tested results, human review, evidence retained, Governance Lead approved -- and still conflict with a customer contract your company already signed. The control gap is that the AI use-case register and the customer contract register usually never talk to each other.

This repository is that cross-reference, built as a small, readable Python join rather than a black box. It reads three registers and flags every use case that internal governance approved but the applicable customer contract may not permit.

## What it checks

For every row in the AI use-case register, the checkpoint cross-references the customer's contract and the AI tool's data-use terms and evaluates five checks, in order of severity:

1. **Was the contract ever reviewed?** If `contract_restrictions_reviewed` is `No`, that alone is a **BLOCK** -- nobody has established whether this workflow is even allowed.
2. **Was required disclosure given?** If the contract requires notice before AI is used and none was recorded, **BLOCK**.
3. **Does the tool train on this customer's data despite a contractual prohibition?** If the contract prohibits training, the tool trains on inputs by default, and the enterprise protection that disables that is not enabled, **BLOCK**.
4. **Does AI support a decision type the contract restricts, even with a human signing off?** Human review is a real control, but it does not by itself satisfy a contractual limit on AI *supporting* a decision -- the AI still determines what the human sees. This is a **REVIEW**, not an automatic pass.
5. **Has the contract changed since the workflow was approved?** If the contract was renewed after the use case's approval date, the approval predates whatever the renewal changed. **RE-REVIEW**.

A use case with none of the above is a **PASS** -- included deliberately, so the report is not all red.

## The sample data is fictional, on purpose

Every customer name, contract, AI tool, and use case in `data/` is invented for this repository. No row here makes a claim about a real vendor's actual data-use policy -- those claims, current as of publication, are cited with sources in the article itself. Fictional data means this repository's fixtures never go stale the way a real vendor's terms eventually will.

## The seeded exceptions

Each use case in `data/ai_use_case_register.csv` was built to trigger one specific, documented outcome. These are not incidental -- do not "fix" them by editing the sample data to make everything pass; that would delete the entire point of the repository. `tests/test_contract_checkpoint.py` hand-calculates and asserts each one:

| Use case | Customer | Outcome | Why |
|---|---|---|---|
| UC-01 | Cascade Retail Group | **BLOCK** | Contract restrictions were never reviewed, and the contract's required disclosure was never given either -- two independent reasons. |
| UC-02 | Lighthouse Financial Partners | **BLOCK** | Reviewed, but the contract requires disclosure before AI use and none was recorded. |
| UC-03 | Meridian Health Network | **BLOCK** | The tool (ScribeFlow AI) trains on inputs by default, the contract prohibits training on this customer's data, and the enterprise tier that would disable training is not enabled. |
| UC-04 | Atlas Logistics Co | **REVIEW** | The contract limits AI support for this decision type. A human makes the final call, but the AI still determines what gets reviewed -- human-in-the-loop does not resolve this on its own. |
| UC-05 | Summit Builders Group | **RE-REVIEW** | The contract was renewed (2026-08-01) after this workflow was approved (2026-06-01). The approval is now stale relative to the contract. |
| UC-06 | Northwind Fleet Services | **PASS** | No AI-specific contract restrictions, no training conflict, no restricted decision, and the contract has not changed since approval. |

## Data files

- `data/ai_use_case_register.csv` -- the internal AI governance register: one row per approved use case, the tool it uses, the customer it touches, and whether contract restrictions were reviewed before deployment.
- `data/customer_contract_register.csv` -- one row per customer MSA: whether it contains AI restrictions, disclosure requirements, a training prohibition, limits on automated decisions, and when it was last renewed.
- `data/ai_tool_data_terms.csv` -- one row per AI tool: whether it retains inputs, trains on them by default, whether that can be disabled, and whether the enterprise tier that disables it is enabled.

None of these files start with a comment line. A comment line at the top of a CSV gets parsed as the header row by `csv.DictReader` -- if you add columns or notes to these files, put explanations here in the README, not in row 1 of the data.

## Running it

```bash
pip install -r requirements.txt
python src/contract_checkpoint.py   # prints the report
pytest                              # runs the seeded-exception assertions
```

Expected `pytest` result: 8 passed.

## Extending it

This is a teaching example, not a production tool. Real extensions worth trying:

- Support a use case that touches more than one customer (`customers_in_scope` as a list rather than a single `customer_id`).
- Add a severity for "AI supports a restricted decision *without* human review" (currently every restricted-decision case in the sample data has human review; the engine does not yet distinguish the case where it's missing).
- Load the registers from a real GRC platform's export instead of a static CSV.
- Turn `run_all()` into a scheduled check that re-runs whenever `customer_contract_register.csv` changes, so a contract renewal automatically re-flags every use case tied to that customer -- the re-review trigger, automated.

## License

MIT. See `LICENSE`.

## About this repository

Built as a companion to PythonMuse Article 38. Claude Sonnet and Claude Opus reviewed the article draft and co-built this repository's exception design; Claude Code (Claude Opus 5, handing off mid-session to Claude Sonnet 5) implemented, tested, and documented it.
