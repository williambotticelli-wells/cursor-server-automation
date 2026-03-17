# EC2 Friday Report & Reminder — Automation Troubleshooting

## Error: "Failed to start background composer: [unauthenticated] Error"

This appears when you **Run Test** (or when the Friday/Slack trigger runs) and means the automation cannot authenticate with the repository.

---

## GitLab setup (this repo)

**This automation is configured to run against a GitLab repository.** The "[unauthenticated]" error in that case is a **known Cursor bug**: Background Agents / Automations currently expect **GitHub** authentication. The backend tries to use GitHub App auth and fails when the project is GitLab-only, and the UI may still show "Reconnect GitHub" or "Verify the GitHub App is installed."

- **Reported to Cursor:** [GitLab Automation Authentication Issue (same error)](https://forum.cursor.com/t/gitlab-automation-authentication-issue-failed-to-start-background-composer-unauthenticated-error/154162) — Cursor staff confirmed it’s been filed as a bug.
- **Status:** No official GitLab support for automations yet; fix is on Cursor’s side.

### Options while waiting for Cursor to fix GitLab

1. **Upvote / comment on the forum thread**  
   Helps prioritize GitLab support:  
   https://forum.cursor.com/t/gitlab-automation-authentication-issue-failed-to-start-background-composer-unauthenticated-error/154162

2. **Temporary workaround: GitHub mirror**  
   If you can maintain a read-only (or sync) mirror of this repo on GitHub and connect that to Cursor:
   - In Cursor, point the automation’s “Repository and Branch” to the **GitHub** repo/branch.
   - The agent would run in the GitHub context; you’d need to align any paths (e.g. `global-tapping-mirex`) with how the automation is configured.
   - Not ideal if you want a single source of truth on GitLab.  
   - **Step-by-step:** see [How to GitHub mirror this repo](#how-to-github-mirror-this-repo) below.

3. **Run the report manually**  
   Until automations work with GitLab, run the same steps locally or in a scheduled job (e.g. cron + script that runs `dallinger ec2 list instances --all`, parses output, and posts to Slack).

---

## How to GitHub mirror this repo

**Source:** GitLab `git@gitlab.com:williambotticelli-wells/cursor-server-automation.git`  
**Goal:** A GitHub repo that Cursor automations can use (same code, GitHub auth).

### One-time setup

1. **Create an empty repo on GitHub**
   - Go to [GitHub New Repository](https://github.com/new).
   - Name it e.g. `cursor-server-automation`.
   - Owner: your user or org (e.g. `williambotticelli-wells`).
   - Do **not** add a README, .gitignore, or license (you already have a repo).
   - Create the repo and copy its URL, e.g. `git@github.com:williambotticelli-wells/cursor-server-automation.git`.

2. **Add GitHub as a remote and push**
   From your local clone (with `origin` pointing at GitLab):

   ```bash
   # Add GitHub as remote (name 'github' or 'mirror')
   git remote add github git@github.com:YOUR_GITHUB_USER_OR_ORG/cursor-server-automation.git

   # Push main and all other branches
   git push github --all

   # Push all tags (optional)
   git push github --tags
   ```

   Replace `YOUR_GITHUB_USER_OR_ORG` with your GitHub username or org (e.g. `williambotticelli-wells`).

3. **Install Cursor GitHub App on the new repo**
   - [GitHub → Settings → Applications](https://github.com/settings/installations) (or org settings).
   - Install or configure the **Cursor** app so it has access to the new GitHub repo.

4. **Point the automation at GitHub**
   - In Cursor → Automations → your EC2 Friday Report automation.
   - Set “Repository and Branch” to the **GitHub** repo and branch (e.g. `williambotticelli-wells/cursor-server-automation`, `main`).
   - Run Test again; it should use GitHub auth.

### If the push fails: "pack exceeds maximum allowed size (2.00 GiB)"

Your repo’s **history** is over 2 GB (e.g. old commits with large `static/`, `output/`, `deploy-results/`). GitHub rejects the push. Use a **single-commit mirror** (current code only, no history):

```bash
# 1. Create a branch with no history but same current files as main
git checkout --orphan github-mirror
git commit -m "Mirror of main (single commit for GitHub)"

# 2. Push only this branch to GitHub (small pack, no big history)
git push github github-mirror:main
```

On GitHub, the repo will have one commit on `main`. To **refresh the mirror** after you’ve pushed new work to GitLab:

```bash
git checkout main
git pull origin main
git branch -D github-mirror 2>/dev/null || true
git checkout --orphan github-mirror
git commit -m "Mirror of main ($(date +%Y-%m-%d))"
git push github github-mirror:main --force
git checkout main
git branch -D github-mirror
```

### Keeping the mirror in sync

**Option A — Push from your machine when you update GitLab**

After you push to GitLab, refresh the single-commit mirror (see “If the push fails” above) and run:

```bash
git push github github-mirror:main --force
```

**Option B — Mirror all branches on a schedule (e.g. cron)**

Only works if the full history is under 2 GB. Otherwise use the single-commit mirror and refresh it on a schedule.

**Option C — GitHub Action (runs on GitHub, pulls from GitLab)**

You’d add a workflow that uses a GitLab token to fetch and push. This requires storing GitLab credentials in GitHub Secrets and is more setup; only do it if you want the mirror to update without using your laptop.

---

## If you were using GitHub instead

*(Kept for reference if the repo is ever moved to GitHub or a GitHub mirror is used.)*

1. **Reconnect GitHub** — In **Cursor → Automations → Run history**, use **"Reconnect GitHub"** if shown.
2. **Cursor GitHub App** — [GitHub → Settings → Applications](https://github.com/settings/installations): ensure Cursor is installed and has access to the repo.
3. **Permissions** — Grant repository (and any requested) permissions for the Cursor app.
4. **Retry** — Run Test again; if it still fails, try signing out and back into Cursor and retry.

---

---

## EC2 Friday report — automation runner context

For the Friday 9am / Slack-triggered agent that runs the EC2 report:

- **AWS credentials:** The runner needs AWS access for `dallinger ec2 list instances`. In **Cursor → Automations → your automation → Cloud Agent Environment → Manage**, add these **secrets** (boto3 reads the uppercase env var names; if your UI uses lowercase keys, it may map them automatically):
  - `AWS_ACCESS_KEY_ID` — IAM access key
  - `AWS_SECRET_ACCESS_KEY` — IAM secret key
  - `AWS_DEFAULT_REGION` or `AWS_REGION` — e.g. `us-east-1` (optional but avoids prompts; dallinger lists all regions anyway)
  Use an IAM user/role with minimal permissions (e.g. `ec2:DescribeInstances`, `ec2:DescribeRegions`). Without the first two, the EC2 listing will fail with an auth error.

- **Where to run:** This repo (**cursor-server-automation**) is the correct workspace. There is **no** `global-tapping-mirex` subfolder; run the EC2 command from the **repository root**. See below for copy-paste automation instructions that use the correct path.

- **If full venv setup fails** (e.g. cloud runner can’t resolve all project deps): use a minimal path so the report still runs:
  1. Create/use `.venv`: `python3 -m venv .venv && source .venv/bin/activate`
  2. Install dallinger only: `pip install dallinger`
  3. Apply the `--all` fix: `./scripts/apply-dallinger-ec2-fix.sh` (or manually patch the installed `dallinger/command_line/ec2.py` to add the `--all` option)
  4. Run: `dallinger ec2 list instances --all`

  Then parse output into running / stopped / long-running and post to #server-channel (or use memory for last week’s snapshot and pem↔person routing).

### What often happens on the cloud runner

The Cursor automation runs on a **minimal Linux image**, so the agent has to fix the environment on the fly:

1. **No `python3-venv`** — Creating `.venv` fails until the agent (or image) installs the system package (e.g. `python3-venv` on Debian/Ubuntu).
2. **`psycopg2` build fails** — Full `pip install dallinger` (or project requirements) pulls in psycopg2, which needs PostgreSQL dev headers. The agent may install `libpq-dev` (and `pg_config`) so the build succeeds. Using only `pip install dallinger` (or minimal EC2-related deps) can avoid this if the runner can't install system packages.
3. **Dallinger installs but the EC2 command fails** — Two common causes:
   - **Missing `--all` flag:** Vanilla dallinger has no `--all`. The agent **must** run `./scripts/apply-dallinger-ec2-fix.sh` after `pip install dallinger` so that `dallinger ec2 list instances --all` works.
   - **AWS credentials not set:** The runner must have `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` (and optionally `AWS_DEFAULT_REGION`) in the Cloud Agent Environment secrets; otherwise boto3 will fail with an auth error.

So the flow that works is: agent bootstraps system deps (python3-venv, libpq-dev if needed) → creates venv → installs dallinger → **runs apply-dallinger-ec2-fix.sh** → runs `dallinger ec2 list instances --all` (with AWS secrets already configured). If the command still fails after that, check the **exact error** in the run output (auth vs. missing `--all` vs. something else).

### Copy-paste automation instructions (for Cursor)

Use this version in your automation; it runs from the **repository root** (no global-tapping-mirex folder).

```
You manage EC2 instance tracking and notifications.

**On Friday 9am trigger:**
1. From the repository root, ensure the command will work:
   - If .venv is missing: install system package `python3-venv` (or equivalent), then `python3 -m venv .venv`. If `pip install dallinger` fails on psycopg2, install system package `libpq-dev` (or equivalent) and retry.
   - If dallinger is missing or the `--all` flag is not available: `source .venv/bin/activate && pip install dallinger && ./scripts/apply-dallinger-ec2-fix.sh` (you must run the fix script after installing dallinger so `--all` exists).
   - Then run: `source .venv/bin/activate && dallinger ec2 list instances --all`. If it fails with "No such option: --all", run `./scripts/apply-dallinger-ec2-fix.sh` and try again. If it fails with an AWS auth error, AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set in the automation environment.
2. Parse output and categorize servers:
   - Running servers: extract "name" and "pem" fields
   - Stopped servers: extract "name" and "pem" fields
   - Long-running servers: identify any running >1 week consecutively (compare against last week's output stored in memory)
3. Send to Slack with formatted results:
   **Running Servers:**
   [list names and pem]

   **Stopped Servers:**
   [list names and pem]

   **Long-running (>1 week):**
   [list names and pem]

**On Slack message trigger (when user replies with a person's name):**
1. Extract the person's name from the message
2. Look up which servers (running/stopped) correspond to that person's pem in your learned knowledge base
3. If you know the mapping, send them a direct Slack message with the reminder (running/stopped server names or "None")
4. If you don't have a learned mapping, ask the user in the Slack channel for clarification before messaging
5. After each interaction, learn and remember pem↔person mappings for future automations
```

---

### Reference

- [Cursor Forum: GitLab Automation Authentication Issue](https://forum.cursor.com/t/gitlab-automation-authentication-issue-failed-to-start-background-composer-unauthenticated-error/154162)  
- Run history may still show: *"Repository access denied. Verify the GitHub App is installed for this repo..."* — that’s the incorrect GitHub message when the project is actually GitLab.
