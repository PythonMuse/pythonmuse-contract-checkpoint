# PythonMuse Contract Checkpoint

A small, runnable companion to PythonMuse Article 38, [Your AI Workflow Was Approved. Did Anyone Read the Customer Contract?](https://github.com/PythonMuse/ai-ledger/blob/main/articles/38-ai-workflow-customer-contract/README.md)

An AI workflow can pass every internal control your organization has -- documented use case, limited access, tested results, human review, evidence retained, Governance Lead approved -- and still conflict with a customer contract your company already signed. The control gap is that the AI use-case register and the customer contract register usually never talk to each other.

This repository is that cross-reference, built as a small, readable Python join rather than a black box. It reads three registers and flags every use case that internal governance approved but the applicable customer contract may not permit.

## What it checks

For every row in the AI use-case register, the checkpoint cross-references the customer's contract and the AI tool's data-use terms and evaluates these checks, in order of severity:

0. **Does the row even join?** If `customer_id` or `tool` isn't in the other registers, there is nothing to cross-check it against -- **BLOCK**, and the remaining checks are skipped for that row. (This is a data-integrity finding, not a contract judgment; see [Register hygiene](#register-hygiene-blank-and-unknown-values).)
1. **Was the contract ever reviewed?** Unless `contract_restrictions_reviewed` is exactly `Yes`, that alone is a **BLOCK** -- nobody has established whether this workflow is even allowed. A blank cell is not a pass; it means nobody recorded an answer.
2. **Was required disclosure given?** If the contract requires notice before AI is used and none was recorded, **BLOCK**.
3. **Does the tool train on this customer's data despite a contractual prohibition?** If the contract prohibits training and the tool trains on inputs by default: if the tool can never disable training, **BLOCK** regardless of tier; otherwise, if the enterprise protection that disables training is not enabled, **BLOCK**.
4. **Does AI support a decision type the contract restricts?** With human review recorded, a human still makes the final call, but the AI determines what they see -- human review does not by itself satisfy the restriction, so this is a **REVIEW**. Without recorded human review, nothing catches what the AI gets wrong, so this is a **BLOCK**.
5. **Has the contract changed since the workflow was approved?** If the contract was renewed after the use case's approval date, or the current contract took effect after the approval date, the approval predates whatever changed. **RE-REVIEW**.
6. **Does the contract require subcontractor flow-down, and does the tool retain inputs?** That combination is a real exposure this join can flag but not resolve -- **REVIEW**, confirm the vendor's terms actually flow down.

A use case with none of the above is a **PASS** -- included deliberately, so the report is not all red.

### Register hygiene: blank and unknown values

Every yes/no field is normalized before a check reads it: `Yes/Y/True/1` -> yes, `No/N/False/0` -> no, `NA/N/A/-`/blank -> na, anything else -> unknown. A field that gates a check treats **unknown or blank as the unfavourable value** -- a blank `contract_restrictions_reviewed` blocks exactly like an explicit `No`, worded differently in the reason text so you can tell the two apart. This is a deliberate fail-closed choice: a governance control that quietly passes rows nobody filled in is worse than one that over-flags them.

Dates (`approval_date`, `effective_date`, `last_renewed_date`) must be ISO `YYYY-MM-DD`. Anything else -- a blank cell, a `M/D/YYYY` export from Excel -- raises a `ValueError` naming the file, row, and column, rather than silently comparing as strings.

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
| UC-07 | Meridian Health Network | **BLOCK** | The tool (DraftPilot Free) trains on inputs by default and cannot disable training at any tier -- no enterprise upgrade could ever fix this, so it's a stronger reason than UC-03's. |
| UC-08 | Atlas Logistics Co | **BLOCK** | Same contractual decision restriction as UC-04, but with no human review recorded at all -- nothing catches what the AI gets wrong. |
| UC-09 | Harbor Point Insurance | **REVIEW** | The contract requires subcontractor flow-down terms, and the tool (ClearCase Assistant) retains customer inputs -- a real exposure this join flags but can't resolve on its own. |
| UC-10 | *(C9 -- not in the contract register)* | **BLOCK** | The use case names a customer with no contract abstract on file. The row can't be checked against a contract that doesn't exist, so that absence is itself the finding. |

## Data files

- `data/ai_use_case_register.csv` -- the internal AI governance register: one row per approved use case, the tool it uses, the customer it touches, and whether contract restrictions were reviewed before deployment.
- `data/customer_contract_register.csv` -- one row per customer MSA: whether it contains AI restrictions, disclosure requirements, a training prohibition, limits on automated decisions, and when it was last renewed.
- `data/ai_tool_data_terms.csv` -- one row per AI tool: whether it retains inputs, trains on them by default, whether that can be disabled, and whether the enterprise tier that disables it is enabled.

None of these files start with a comment line. A comment line at the top of a CSV gets parsed as the header row by `csv.DictReader` -- if you add columns or notes to these files, put explanations here in the README, not in row 1 of the data.

## Running it

```bash
pip install -r requirements.txt
python src/contract_checkpoint.py   # prints the report, reads data/
pytest                              # runs the seeded-exception and engine tests
```

Expected `pytest` result: 30 passed.

### Command-line options

```bash
python src/contract_checkpoint.py --data-dir path/to/your/export
python src/contract_checkpoint.py --json report.json          # machine-readable evidence
python src/contract_checkpoint.py --fail-on review             # stricter CI gate
python src/contract_checkpoint.py --quiet --json report.json   # for scripts/CI
```

- `--data-dir PATH` -- point at your own three CSVs instead of the repo's `data/` (default).
- `--json PATH` -- write a report containing a UTC run timestamp, a SHA-256 of each input file (so you can prove which exact registers were evaluated), status counts, and the full per-use-case results. This is the artefact to retain as evidence that the checkpoint ran.
- `--fail-on {block,review,never}` -- controls the process exit code so this can gate a pipeline. `block` (default): exit 1 if any use case is BLOCK. `review`: exit 1 if any use case is BLOCK, REVIEW, or RE-REVIEW. `never`: always exit 0.
- `--quiet` -- suppress the human-readable stdout report (useful with `--json` in a script).

## Adapting this to your own registers

The three CSVs are meant to be replaced with your organisation's real exports. A few things worth knowing before you do:

- **The registers have different owners.** The AI use-case register is typically owned by whoever runs AI governance; the contract register is a Legal abstraction of the actual MSAs, not the contracts themselves; the tool data-terms register usually comes from Procurement or IT vendor management. The checkpoint is only as good as those three inputs agreeing on the same `customer_id` and `tool` spellings.
- **`contract_restrictions_reviewed` and `ai_supports_restricted_decision` are governance determinations, not self-reports.** If a use-case owner fills these in without anyone actually checking the contract, the checkpoint will faithfully report a wrong answer. The value of this tool is the cross-reference, not a substitute for someone reading the contract.
- **A blank cell is not a pass.** See [Register hygiene](#register-hygiene-blank-and-unknown-values) above -- unrecognised or missing values in a gating field resolve to the unfavourable outcome, not to PASS.
- **This is not legal advice.** The checkpoint tells you where your internal AI governance register and your contract register disagree. Whether a given disagreement is actually a problem, and what to do about it, is a legal and business judgment -- BLOCK/REVIEW/RE-REVIEW are prompts to have that conversation, not a verdict.

## Extending it

This is a teaching example, not a production tool. Real extensions worth trying:

- Support a use case that touches more than one customer (`customers_in_scope` as a list rather than a single `customer_id`).
- Load the registers from a real GRC platform's export instead of a static CSV.
- Turn `run_all()` into a scheduled check that re-runs whenever `customer_contract_register.csv` changes, so a contract renewal automatically re-flags every use case tied to that customer -- the re-review trigger, automated.
- Add a CI workflow that runs `pytest` and `python src/contract_checkpoint.py --json report.json` on every push, and uploads the JSON as a build artefact.

## License

MIT. See `LICENSE`.

## About this repository

Built as a companion to PythonMuse Article 38. Claude Sonnet and Claude Opus reviewed the article draft and co-built this repository's exception design; Claude Code (Claude Opus 5, handing off mid-session to Claude Sonnet 5) implemented, tested, and documented it.
