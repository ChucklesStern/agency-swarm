# OpenSwarm vendor manifest

This directory contains a vendored copy of OpenSwarm, originally
distributed under the MIT License.

- **Upstream:** https://github.com/VRSEN/OpenSwarm
- **Commit SHA:** `7a32832cd89d8956f7faf6ba2704531478aa796b`
- **Vendored:** 2026-05-15
- **License:** MIT (see `OPENSWARM_LICENSE` in this directory)

## Files copied (relative to upstream repo root)

```
swarm.py
onboard.py
helpers.py
config.py
shared_instructions.md
requirements.txt
LICENSE              -> OPENSWARM_LICENSE
orchestrator/**
virtual_assistant/**
deep_research/**
data_analyst_agent/**
slides_agent/**
docs_agent/**
image_generation_agent/**
video_generation_agent/**
shared_tools/**
patches/**
```

### Why `requirements.txt` is intentionally included

The `requirements.txt` is **intentionally part of the scaffold**, not an
oversight. It lands in the user's cwd alongside `agency.py` and the agent
packages, where it acts as the supported override hook for the
`agentswarm-cli` Node TUI's project-venv bootstrap.

Concretely, inspecting the cached Node TUI binary (`agentswarm-cli` v1.4.24,
strings dump at line 678590) shows `installProjectDependencies(directory,
python)` is a three-level fallback ladder:

1. If `{cwd}/requirements.txt` exists → `pip install --upgrade -r requirements.txt`
2. Else if `{cwd}/pyproject.toml` exists → `pip install --upgrade -e .`
3. Else → hardcoded `pip install agency-swarm[fastapi,litellm]>=1.9.1`

Branch 3 lacks `[jupyter]`, which means importing
`agency_swarm.tools.built_in.IPythonInterpreter` (which has a module-level
`from jupyter_client import …`) crashes the TUI's project server at startup.
The upstream OpenSwarm `requirements.txt` starts with
`agency-swarm[fastapi,jupyter,litellm]>=1.9.7` and includes every
OpenSwarm-runtime dep (composio, fal-client, pandas, …). Shipping it in the
scaffold forces the TUI down branch 1 instead.

**Future maintainers: do not move this back to the "skipped" list.** Doing so
re-introduces the IPythonInterpreter crash in fresh-directory `init
openswarm` runs.

## Files deliberately skipped

```
run_utils.py            (bundles TUI binary downloader + Playwright provisioning;
                         conflicts with agency-swarm's own TUI plumbing)
server.py               (FastAPI server entry; out of scope for the scaffold)
patches/dom-to-pptx+1.1.5.patch  (6 MB npm patch for a Node package; useless
                                  without node_modules/, which we also skip)
bin/, Dockerfile, docker-compose.yml
node_modules/, package.json, package-lock.json
.playwright-browsers/, assets/
.claude/, .cursor/, .github/
requirements-dev.txt, pyproject.toml
AGENTS.md, CLAUDE.md, README.md, RELEASE.md
```

## Audience

This NOTICE.md is **developer-facing**. It is package data inside
`agency_swarm._templates.openswarm/` and stays in the installed
agency-swarm distribution — it is NOT copied into a user's scaffolded
project when they run `agency-swarm init openswarm`. End users see
`OPENSWARM_LICENSE` and a short, user-facing `OPENSWARM_NOTICE.md`
that the scaffold writes into their cwd.

## Re-syncing from upstream

To bring the vendored tree up to a newer OpenSwarm commit:

```bash
rm -rf /tmp/openswarm-vendor-src
git clone --depth 1 https://github.com/VRSEN/OpenSwarm.git /tmp/openswarm-vendor-src
NEW_SHA=$(git -C /tmp/openswarm-vendor-src rev-parse HEAD)
# Diff against the current vendored copy to see upstream changes,
# then `cp -R` the files listed above and update this NOTICE.md with NEW_SHA
# and today's date. Run the launcher tests to catch any monkey-patch
# regressions (`pytest tests/test_cli_modules/ -v`).
```

Local edits to vendored files are deliberately not allowed — any change
here is drift from upstream. If a fix is required, apply it upstream
first, then re-sync.

## Locally-authored files in this directory

The following files in this directory are NOT from upstream OpenSwarm —
they are authored locally for agency-swarm's scaffold mechanism:

- `NOTICE.md` (this file, developer-facing vendor manifest)
- `OPENSWARM_NOTICE.md` (short user-facing attribution; copied into the
  user's scaffolded project at scaffold time)
