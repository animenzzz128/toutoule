# toutoule

## Known limits

Stated plainly, because volunteering a limit is more useful than being caught by it.
Numbers are from the shipped configuration (`extract_v3` plus the materials support
check), measured twice on the same 50 job descriptions: once derived from saved outputs
to isolate the code change, once on a fresh model run to test stability. Full numbers and
the reasoning behind each version are in [`docs/eval/iteration_log.md`](docs/eval/iteration_log.md).

**Four of the five extraction targets are not met.**

| Target | Result | Shipped numbers (derived / repeat) |
|---|---|---|
| Critical hallucination 0% | not met | 6 / 249 (2.4%) · 8 / 249 (3.2%) |
| Critical accuracy ≥95% | not met | 55 / 62 (88.7%) · 54 / 57 (94.7%) |
| Critical false-negative ≤10% | **met** | 5 / 67 (7.5%) · 6 / 67 (9.0%) |
| Important accuracy ≥90% | not met | 51 / 131 (38.9%) · 43 / 130 (33.1%) |
| Reference recall ≥80% | not met | 250 / 552 (45.3%) · 256 / 552 (46.4%) |

The remaining critical errors are concentrated in `application_cap` — the one critical
field no prompt version changed — and in values filed under the wrong field. Iteration
stopped under a stopping rule fixed before the first run
([D-009](docs/06_DECISION_LOG.md)), not because the targets were reached.

**No held-out set.** The prompts were tuned on the same 50 postings they are scored on,
so these results may overstate performance on postings the system has not seen.

**Labels are model-drafted and owner-reviewed, not hand-verified.** A model from a
different family drafted the ground truth from the source text, checked against five
cases the owner hand-labeled blind first. Every extractor/label disagreement on a
critical field was then checked against the raw posting before being counted
([D-008](docs/06_DECISION_LOG.md)).

**Important-tier and reference-tier numbers are depressed by a language mismatch.** The
labels are in English; for Chinese postings the model answers in Chinese, and the scorer
counts a correct Chinese answer as a miss. This affects the important and reference
tiers, not the critical-field hallucination rate that the project's main claim rests on.