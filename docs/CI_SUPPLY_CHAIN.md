# CI supply-chain policy

CareerPilot CI is one GitHub Actions workflow (`.github/workflows/ci.yml`) plus Full-history Gitleaks (`.github/workflows/security.yml`). Neither workflow deploys the product.

## Runner image

`verify` uses `ubuntu-24.04`, not `ubuntu-latest`.

GitHub currently maps `ubuntu-latest` to 24.04, but that alias can move. Pinning the image keeps the browser, Node, and apt surface reproducible.

The Security workflow stays on `ubuntu-latest`. It does not install Playwright, does not use Node/Python setup actions beyond checkout, and already pins `actions/checkout` by SHA. Changing that runner would add risk without helping the Playwright/apt issue.

## Actions

CI uses Node 24-native official releases, pinned by commit SHA (tag comments are labels only):

| Action | Tag | SHA |
| --- | --- | --- |
| `actions/checkout` | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v7.0.0 | `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `actions/setup-node` | v7.0.0 | `820762786026740c76f36085b0efc47a31fe5020` |

SHAs were verified against the upstream tag objects. Do not revert to floating `@v4` / `@v5` majors. Do not set `ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION`.

The application still runs tests on **Node.js 22** and **Python 3.11**. The action upgrade is the Actions runtime, not a CareerPilot Node 24 product migration.

## Token

CI declares `permissions: contents: read`. It does not push, create releases, or comment.

Checkout uses `persist-credentials: false` so later steps do not inherit a stored `GITHUB_TOKEN` in git remotes. The committed-range whitespace check fetches public SHAs from `origin` on this public repository.

## Playwright

Install Playwright's bundled Chromium:

```bash
python -m playwright --version
python -m playwright install chromium
```

Do not use `playwright install --with-deps` on this workflow. That path mutates apt sources (including Google Chrome packages) on every run. ubuntu-24.04 already supplies the system libraries used by the MVP, Job Intelligence, and CORS/cookie browser gates.

Browser steps must remain required. Do not `|| true` install or skip those jobs.

## Dependabot

`.github/dependabot.yml` watches pip, frontend npm, extension npm, and **github-actions**. PRs are version updates for human review. Auto-merge stays off. Do not treat grouped Dependabot PRs (#88–#91) as part of this policy change.

## Python packages

`requirements.txt` is range-based. That is a known reproducibility gap. Do not `pip freeze` the developer machine into that file. A dedicated Python lock/constraints approach is tracked separately from this CI workflow change.

## Release tags

Future release tags should be signed when practical. Historical annotated `v1.0.0` (`b73a983ed3605d498aa90070c3b5f786a73bc525`) stays unsigned and must not be rewritten, moved, or retagged.
