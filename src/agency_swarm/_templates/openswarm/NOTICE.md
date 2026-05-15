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
requirements*.txt, pyproject.toml
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
