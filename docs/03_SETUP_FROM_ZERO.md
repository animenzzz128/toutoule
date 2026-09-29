# 03 — Setup From Zero

For a machine with no development environment installed. Budget **90 minutes**. Do this
once, in order, before any other work.

A note on how to read this: you do not need to understand what every command does. You do
need to verify each step produced the expected output before moving on — a broken setup
discovered three tasks later costs far more than checking now.

---

## Step 1 — Open a terminal (5 min)

**macOS:** press `Cmd + Space`, type `Terminal`, press Enter.
**Windows:** press the Windows key, type `PowerShell`, press Enter.

Everything below is typed here. Type commands rather than pasting blindly when you can —
you will remember them.

✅ **Check:** a window with a blinking cursor.

---

## Step 2 — Install a code editor (10 min)

Download **Visual Studio Code** from `https://code.visualstudio.com` and install it.

Then install two extensions (open the Extensions panel with `Cmd/Ctrl + Shift + X`):
- **Python** (Microsoft)
- **Ruff** (Astral)

✅ **Check:** VS Code opens and both extensions appear as installed.

---

## Step 3 — Install Git and create a GitHub account (15 min)

**macOS:** run `git --version`. If Git is missing, macOS offers to install the developer
tools — accept.
**Windows:** download Git from `https://git-scm.com/download/win` and install with the
defaults.

Then configure your identity — this is what appears on every commit, and this repository is
part of your portfolio, so use your real name and an email you are comfortable showing:

```bash
git config --global user.name "Jiaqi Yao"
git config --global user.email "your.email@example.com"
git config --global init.defaultBranch main
```

Create an account at `https://github.com` if you do not have one. Use a professional
username — it becomes part of every URL you share with an interviewer.

✅ **Check:** `git --version` prints a version number, and `git config --global user.name`
prints your name.

---

## Step 4 — Install uv (10 min)

`uv` handles both Python itself and your project's packages. One tool instead of three.

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal afterwards, then:
```bash
uv --version
uv python install 3.12
```

✅ **Check:** `uv --version` prints a version number.

> If `uv` is not found after reopening the terminal, the installer's directory is not on
> your PATH. The installer prints the fix at the end of its output — scroll back and follow
> it.

---

## Step 5 — Install Claude Code (15 min)

Claude Code requires **macOS 10.15+, Ubuntu 20.04+/Debian 10+, or Windows 10+** (on Windows,
via WSL or Git for Windows), at least **4GB RAM**, and a paid Claude subscription (Pro, Max,
or Team) or an API key. The free tier does not include it.

**Use the native installer.** It has zero dependencies and does not require Node.js. The npm
installation path does require Node.js — and as of v2.1.198 the npm package requires Node
22 or later — which is an extra moving part you do not need.

Follow the current official instructions at
`https://docs.claude.com/en/docs/claude-code/overview` — installation commands change, so
use the docs rather than a command copied from anywhere else, including this file.

After installing:
```bash
claude doctor
```
This reports your installation type and whether everything is wired up correctly.

✅ **Check:** `claude doctor` runs and reports no errors.

---

## Step 6 — Get an Anthropic API key (10 min)

The project's code calls the Claude API directly. This is billed separately from your
Claude Code subscription.

1. Go to `https://console.anthropic.com`
2. Create an API key
3. **Set a spending limit immediately.** For this project, $20/month is generous. Do this
   before writing any code — a runaway loop in a scheduled job is the classic way to
   discover you had no limit set.
4. Copy the key somewhere safe. You will paste it into `.env` in Step 8, and you will not be
   able to view it again.

✅ **Check:** the key exists in your console and a spending limit is visible on the account.

> ⚠️ **Do not `export` this key in your shell.** If `ANTHROPIC_API_KEY` is set as a shell
> environment variable, Claude Code will use it instead of your Pro/Max/Team subscription —
> silently switching your coding-assistant usage from "included in subscription" to
> "billed per token." Keep the key inside `.env` only, loaded by the application at
> runtime (Step 8). Run `claude /status` any time to confirm which auth method is active —
> it should say subscription, not API key, while you are doing Claude Code work.

**On using multiple Claude accounts (e.g. a personal Pro plan and a school-issued Pro
plan):** Claude Code can log into either with `claude /login`, and each account's 5-hour
usage window is separate, so switching accounts when one is rate-limited is a legitimate
way to extend a long session. Before routing a personal portfolio project through a
school-issued account, check your institution's usage terms — Anthropic's own policy
requires subscription seats to be for the account holder's individual use, but a school
may layer additional restrictions on top. When in doubt, default to the personal account
for this project.

---

## Step 7 — Create the repository (10 min)

On GitHub, create a new repository named `toutoule`:
- **Private** for now — make it public at milestone M1, when it is presentable
- Initialize with a README
- Add a `.gitignore` using the **Python** template
- Choose the **MIT License**

Then clone it to your machine:
```bash
cd ~/Documents
git clone https://github.com/<your-username>/toutoule.git
cd toutoule
code .
```

✅ **Check:** VS Code opens showing `README.md`, `.gitignore`, and `LICENSE`.

---

## Step 8 — Wire up secrets (10 min)

Create a file named `.env` in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...
DATABASE_URL=sqlite:///data/toutoule.db
MATCH_THRESHOLD=65
DIGEST_EMAIL_TO=your.email@example.com
```

Then confirm `.env` is ignored by Git. Open `.gitignore` and make sure it contains:
```
.env
data/toutoule.db
data/profile/real_*
```

Verify:
```bash
git status
```

✅ **Check:** `.env` does **not** appear in the output. If it does, stop and fix
`.gitignore` before committing anything. A key committed to Git history is compromised even
after deletion, and must be revoked and reissued.

---

## Step 9 — Set up the GitHub project board (15 min)

This is the project-management layer. It costs 15 minutes and it is the part an interviewer
can actually see.

1. On your repository, enable **Issues** (Settings → Features).
2. Create four **Milestones** (Issues → Milestones → New):
   - `M0 — Environment Ready`, due 2026-09-29
   - `M1 — Core Engine`, due 2026-10-08
   - `M2 — Automation`, due 2026-10-20
   - `M3 — Learning & Pilot`, due 2026-11-30
3. Create a **Project** (Projects → New → Board) named `投投乐 Delivery`, with columns
   `Backlog / In Progress / In Review / Done`.
4. Create **Labels**: `phase-1`, `phase-2`, `phase-3`, `P0`, `P1`, `P2`, `eval`,
   `infra`, `docs`, `bug`.

✅ **Check:** four milestones exist and the board is visible.

---

## Step 10 — First commit (5 min)

Copy the `docs/` folder from this handoff pack into the repository, and copy `CLAUDE.md` to
the repository root. Then:

```bash
git checkout -b docs/initial-handoff
git add .
git commit -m "docs: add PRD, tech spec, execution plan, and eval spec"
git push -u origin docs/initial-handoff
```

Open a pull request on GitHub, then merge it. Yes, this is a pull request to yourself. Do it
anyway — from this point on, `main` is only ever modified through reviewed PRs, and your
commit history becomes something you can show someone.

✅ **Check:** `main` contains `docs/` and `CLAUDE.md`, and the PR appears as merged.

---

## 🏁 Milestone M0 — Environment Ready

Tag it:
```bash
git checkout main
git pull
git tag -a v0.0.1 -m "M0: environment ready"
git push origin v0.0.1
```

**M0 is complete when every box below is checked:**

- [ ] `git --version` works and identity is configured
- [ ] `uv --version` works, Python 3.12 installed
- [ ] `claude doctor` reports no errors
- [ ] Anthropic API key created **with a spending limit set**
- [ ] `toutoule` repository cloned locally
- [ ] `.env` exists and is confirmed gitignored
- [ ] Four milestones and the project board exist on GitHub
- [ ] First PR merged, `v0.0.1` tagged

---

## When something breaks

In order:

1. **Read the error message.** Not the first line — the last few lines. That is where the
   actual cause usually is.
2. **Paste the whole error into Claude Code** and ask what it means. Include the command you
   ran. Do not paraphrase the error.
3. **Check the obvious things:** wrong directory (`pwd`), terminal not reopened after an
   installation, typo in a file name.
4. **Do not reinstall blindly.** Note the exact step that failed. Reinstalling from scratch
   usually reproduces the same failure and costs an hour.
