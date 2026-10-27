# 07 — Roadmap v2 (after M1)

**Date:** 2026-10-27 · **Decision:** [D-014](06_DECISION_LOG.md) · **Supersedes:** Phases 2–3 of
[`04_EXECUTION_PLAN.md`](04_EXECUTION_PLAN.md) (kept for the record)

## 中文摘要

M1 已交付：证据核验、分层 eval、规则判资格都已上线，但 0% 幻觉与打分校准两个目标未达成，且
已经停更两周。v2 不再堆功能，而是按"面试作品集优先、每周约 5 小时"重新排期：先补发布卫生与
README（A），再让 eval 数字可信——多语言等价、样本外测试集、v5 支持性检查、置信区间（B），然后
把"适配度"和"优先级"拆开，补上规则与使用数据（C），最后做精简自动化（D）与可选的试点和 MCP（E）。
对标 17 个同类项目，没有一个公开抽取错误率，这正是投投乐的差异化。工作在 Claude 与 Codex 两个窗口
按文件所有权并行推进（见 `AGENTS.md` / `CLAUDE.md` 的 Parallel lanes）。

---

## 1. Where M1 left the project

**Keep and amplify.** These are rare among comparable projects and are the portfolio:

- Tiered eval with a plain-prompt baseline and pre-registered hypotheses (v1 → v4).
- Evidence quotes verified in code; deterministic eligibility rules R1–R6.
- A decision log that records reversals and misses (D-009, D-012).
- [`eval/scoring.md`](eval/scoring.md): the 3 / 20 scoring miss traced to a *specification*
  error (priority ≠ fit), not a tuning error.

**Gaps found on review (2026-10-27).**

| # | Gap | Evidence |
|---|---|---|
| 1 | Tags stop at v0.0.4; `pyproject.toml` says 0.0.2; M1 milestone left open | `git tag`, GitHub |
| 2 | Repo has no description, topics or homepage | GitHub |
| 3 | Important accuracy and recall understated: a correct Chinese answer against an English label counts as a miss | README Results |
| 4 | No held-out set; every number is in-sample | D-009, D-010 |
| 5 | Remaining hallucinations concentrate in `application_cap` and misfiled `graduation_window`; the verbatim check cannot see a real quote in the wrong field | iteration log, v4 |
| 6 | Three hard conditions (MBA-only, internship vs full-time) sit in the fit score, not the rules | scoring.md |
| 7 | North star (high-fit applications per week) and time per posting never measured | PRD §3 |
| 8 | Market not persisted; tracker Market column always blank | D-011 §4 |
| 9 | Live demo stops working when the API budget runs out | README |
| 10 | No prompt caching; extraction model not re-evaluated since 2026-10-02 | `score.py`, `config.py` |
| 11 | Weekly retro files never written | `04_EXECUTION_PLAN.md` |

## 2. Comparable work (surveyed 2026-10-27)

Star counts as fetched that day; commercial details partly from third-party sources.

| Project | What to borrow | Where TouTouLe is stronger |
|---|---|---|
| [career-ops](https://github.com/santifer/career-ops) (~78k★), closest open-source analog | Scanner over Ashby / Greenhouse / Lever with a liveness check; "don't apply below 4.0" threshold; rejection-pattern analysis; never submits | README reports no metrics; eligibility is a prompt judgment, not verified quotes + rules; no 网申 caps or 届 windows |
| [Resume-Matcher](https://github.com/srbhr/Resume-Matcher) (~29k★) | Score computed in plain code with published weights; MCP server | No triage or eligibility; "no fabrication" not measured |
| [ApplyPilot](https://github.com/Pickle-Pixel/ApplyPilot) (~1.8k★) | Score threshold gates expensive steps (same idea as PD-3) | Auto-submits and solves CAPTCHAs — outside our boundary |
| AIHawk (the original repo URL now redirects elsewhere) | Cautionary: the best-known auto-apply project pivoted | Human approval avoids the ToS and quality problems |
| [JobSpy](https://github.com/speedyapply/JobSpy) (~4.6k★) | Reports blocked boards separately from empty results | Scrapes LinkedIn / Indeed — **not adopted** (ADR-005) |
| [Reactive Resume](https://github.com/amruthpillai/reactive-resume) (~45k★) | AI edits shown as a diff with a reason, accepted one by one → C4b | No triage |
| [Jobright.ai](https://jobright.ai), closest commercial analog | H-1B filter combining JD text with public sponsorship history → E4 | US only; no evidence quotes |
| Simplify, Teal, Huntr, Jobscan, Careerflow, LinkedIn Job Match | Clipper, auto-logging to a tracker, inline keyword gaps | No eligibility reasoning, no evidence |
| BOSS直聘 求职报告, 智联 职悟空 | A "risk avoidance" section in the report | Platform-locked; no 网申 caps or 届 windows |
| 网申 browser extensions (校招鸭, 求职方舟) | Demand for 网申 help is real | Broad permissions, résumés sent to third parties; TouTouLe is local-first |
| [LangExtract](https://github.com/google/langextract) (~39k★) | Every extraction mapped to a character span and highlighted → C6 | README shows no accuracy numbers |
| [Anthropic Citations](https://platform.claude.com/docs/en/build-with-claude/citations) | Native citations | Documented as not combinable with structured outputs — which supports ADR-003's schema + code-verified quotes |
| instructor, promptfoo, Inspect AI | Validator-driven retry; eval in CI | ADR-001: no framework; our harness covers it (B6 adds CI) |

**Read.** None of the 17 publishes an extraction error rate. The moat is a decision record you
can verify plus a public, tiered, honest error rate. Stay out of auto-apply and résumé
optimisation; take two cheap, high-signal ideas from the trend: source highlighting and an MCP
server.

## 3. Phases

Budget ~5 h/week. Every task is one issue, one branch, one PR. Lane = which agent window owns it
(§4).

### Phase A — Packaging · week of 2026-10-28 · ~5 h → v0.1.2

| Task | Lane | Issue |
|---|---|---|
| Setup: this roadmap, D-014, parallel lanes | Claude | [#39](https://github.com/animenzzz128/toutoule/issues/39) |
| A1 Tag v0.1.0 / v0.1.1, align package version | Claude | [#40](https://github.com/animenzzz128/toutoule/issues/40) |
| A2 Repo About, topics, homepage | Claude | [#41](https://github.com/animenzzz128/toutoule/issues/41) |
| A3 README first screen for a 5-minute reader | Claude | [#44](https://github.com/animenzzz128/toutoule/issues/44) |
| A4a Demo cases that need no API call (engine) | Codex | [#42](https://github.com/animenzzz128/toutoule/issues/42) |
| A4b Demo fallback in the app (UI) | Claude | [#43](https://github.com/animenzzz128/toutoule/issues/43) |
| A5 M1 retrospective | Claude | [#45](https://github.com/animenzzz128/toutoule/issues/45) |

### Phase B — Eval 2.0 · 2026-11-04 → 11-17 · ~10 h → v0.2.0

Make the numbers credible before adding surface. Pre-registration loop: Claude writes the
hypothesis → Codex implements and runs → Claude writes the read.

| Task | Lane | Issue |
|---|---|---|
| B1 Multilingual equivalence, re-score saved runs (0 API calls) | Codex | [#46](https://github.com/animenzzz128/toutoule/issues/46) |
| B2b Eval CLI runs a named case set | Codex | [#48](https://github.com/animenzzz128/toutoule/issues/48) |
| B2 Held-out set of 20 postings published after 2026-10-02 | Claude | [#49](https://github.com/animenzzz128/toutoule/issues/49) |
| B3a Pre-register the v5 hypothesis | Claude | [#50](https://github.com/animenzzz128/toutoule/issues/50) |
| B3b v5 support checks: `application_cap`, `graduation_window` | Codex | [#51](https://github.com/animenzzz128/toutoule/issues/51) |
| B4 Wilson intervals on every ratio | Codex | [#52](https://github.com/animenzzz128/toutoule/issues/52) |
| B5 Model-swap decision memo (D-015) | Claude | [#53](https://github.com/animenzzz128/toutoule/issues/53) |
| B6 Golden metrics snapshot in CI | Codex | [#47](https://github.com/animenzzz128/toutoule/issues/47) |
| B7 Write-up and v0.2.0 | Claude | [#54](https://github.com/animenzzz128/toutoule/issues/54) |

### Phase C — Fit vs Priority · 2026-11-18 → 12-01 · ~12 h → v0.3.0

The product response to scoring.md: hard conditions go to rules, preferences go to a transparent
priority, fit stays fit. If the week runs over, C6 moves to Phase D.

| Task | Lane | Issue |
|---|---|---|
| C1 Rules R7 (degree-restricted) and R8 (employment type) | Codex | [#55](https://github.com/animenzzz128/toutoule/issues/55) |
| C2a Priority spec, ADR-008, fit/priority hand-score protocol | Claude | [#56](https://github.com/animenzzz128/toutoule/issues/56) |
| C2b Priority engine | Codex | [#57](https://github.com/animenzzz128/toutoule/issues/57) |
| C2c "Why it ranks here" in the app | Claude | [#58](https://github.com/animenzzz128/toutoule/issues/58) |
| C3 Persist market; fill the tracker's Market column | Codex | [#59](https://github.com/animenzzz128/toutoule/issues/59) |
| C4 Rewrite suggestions after approval (engine) | Codex | [#11](https://github.com/animenzzz128/toutoule/issues/11) |
| C4b Rewrite suggestions as an accept/reject diff (UI) | Claude | [#63](https://github.com/animenzzz128/toutoule/issues/63) |
| C5a Usage events and time per posting | Codex | [#60](https://github.com/animenzzz128/toutoule/issues/60) |
| C5b Weekly metrics page and 2-week dogfooding report | Claude | [#61](https://github.com/animenzzz128/toutoule/issues/61) |
| C6a Character spans of verified quotes | Codex | [#62](https://github.com/animenzzz128/toutoule/issues/62) |
| C6b Source tab with highlighted quotes (UI) | Claude | [#33](https://github.com/animenzzz128/toutoule/issues/33) |
| C7 Write-up and v0.3.0 | Claude | [#64](https://github.com/animenzzz128/toutoule/issues/64) |

### Phase D — Lean Discovery · 2026-12-02 → 12-15 · ~8 h → v0.4.0

Public ATS APIs only. Cut from the original Phase 2: Tier 2 page watching and HMAC one-click
email links.

| Task | Lane | Issue |
|---|---|---|
| D0 ADR-002 (Postgres) and ADR-005 (sources and compliance) | Claude | [#65](https://github.com/animenzzz128/toutoule/issues/65) |
| D1 Hosted Postgres | Codex | [#66](https://github.com/animenzzz128/toutoule/issues/66) |
| D2 Greenhouse / Lever / Ashby adapters with liveness check | Codex | [#67](https://github.com/animenzzz128/toutoule/issues/67) |
| D3 Daily run and shortlist email | Codex | [#68](https://github.com/animenzzz128/toutoule/issues/68) |
| D3b Inbox page in the app | Claude | [#69](https://github.com/animenzzz128/toutoule/issues/69) |
| D4 Prompt caching for résumé context; cost per job | Codex | [#70](https://github.com/animenzzz128/toutoule/issues/70) |

### Phase E — Distribution & Pilot · optional

| Task | Lane | Issue |
|---|---|---|
| E0 ADR-009: TouTouLe as an MCP server | Claude | [#71](https://github.com/animenzzz128/toutoule/issues/71) |
| E1 MCP server: `triage_posting`, `get_shortlist` | Codex | [#72](https://github.com/animenzzz128/toutoule/issues/72) |
| E2 5-person pilot | Claude | [#73](https://github.com/animenzzz128/toutoule/issues/73) |
| E3 Case study (EN + 中文) and 3-minute video | Claude | [#74](https://github.com/animenzzz128/toutoule/issues/74) |
| E4 Sponsorship-history prior (reference only, never a flag) | Codex | [#75](https://github.com/animenzzz128/toutoule/issues/75) |

### Scope-cut order

Decided now, so it isn't decided under pressure: Phase E → D3/D3b → D2 → C4/C4b → C5.
**Never cut:** B1 and B2. Without them the published numbers stay understated and in-sample.

## 4. Two windows in parallel

Two agent windows (Claude Code and Codex) work at once. They never edit the same file, because
ownership is by path, not by task. The rules are in `AGENTS.md` and `CLAUDE.md` under
"Parallel lanes"; the summary:

- **Claude lane:** docs, README, CHANGELOG, `app/`, the two UI test files, eval data and labels,
  GitHub issues / milestones / releases, and the release version bump.
- **Codex lane:** `src/toutoule/`, all other tests and fixtures, prompts, scripts, CI,
  dependencies.
- Each window has its own git worktree. Cross-lane interfaces are fixed in the issue before
  coding. Coordination happens in issue comments, not a shared file.

## 5. Interview story map

| Question | Answer lives in |
|---|---|
| "How did you design the eval?" | Tiered by cost of error, with a baseline — eval spec, iteration log |
| "Tell me about a metric you missed." | Scoring 3 / 20 → specification error → C2 |
| "How do you know it works on new data?" | B2 held-out set |
| "How would you decide to change models?" | B5, D-015 |
| "What did you cut, and why?" | D-014, cut order above |
| "Why not career-ops or Jobright?" | §2: the only public tiered error rate; Citations vs structured outputs → ADR-003 |
| "Why not auto-apply?" | PRD non-goals, constraint 8 in `AGENTS.md`, AIHawk's pivot, ToS risk |
