# 34 — Release reproducibility: dependency locking, CI tiers, SBOM

What this repository claims about reproducibility, what it deliberately does
**not** claim, and how each dependency source is pinned. Generated instances
(release manifest, SBOM, capability matrix JSON, CI case list) are release
artifacts and are not committed; the generators, schemas and tests are.

```bash
python generator_trunk/bundle_run.py release --out /tmp/release-manifest.json \
                                             --sbom /tmp/sbom.cyclonedx.json \
                                             --pytest-output /tmp/pytest.txt
python generator_trunk/bundle_run.py capabilities --json /tmp/capability-matrix.json
python generator_trunk/bundle_run.py sut-manifests --json /tmp/sut-manifests.json
```

## 1. The reproducibility claim, stated narrowly

**Claimed:** the same source revision yields the same declared component
versions and the same set of release inputs, each freshly hashed and recorded in
the release manifest.

**Not claimed**, and the manifest says so in its own `reproducibility.not_claimed`
block so a consumer cannot read the numbers without the limits:

- **Byte-for-byte identical artifacts.** Maven jars embed zip entry timestamps,
  so a rebuild from identical source produces a different artifact `sha256`.
  `bundle inventory --baseline --policy block` will flag every rebuild; that is
  the tool behaving correctly, not a defect.
- **Platform-independent resolution.** `requirements-release.lock` records what
  resolved on one platform (Linux x86_64, CPython 3.12). Platform-specific
  wheels are not pinned per platform.
- **A fully transitive Maven dependency lock/SBOM.** Python components are bounded
  by `requirements-release.lock`; Maven covers reactor modules plus direct
  dependencies, plugins, extensions and declared build tools from checked-in POMs.
  It does not claim the resolved Maven transitive closure.
- **Hash-verified installs.** The Python lock pins versions, not artifact bytes.
  `--require-hashes` needs a hash-complete resolution and is a future step.
- **Source-archive reconstruction.** Tier 3 starts from a fresh checkout, but no
  separately produced source archive is yet unpacked and rebuilt byte-for-byte.

`generated_at` in the manifest is metadata about the document, never evidence
about the build.

## 2. Dependency and image locking

| Source | Declaration | Lock / pin | State |
|---|---|---|---|
| Python — Tier-3 release profiles (`test,science,deploy`) and build backend | `pyproject.toml` (human-maintained) | `requirements-release.lock` (machine-resolved, including exact `setuptools`) | ✅ locked |
| Python — other feature surfaces (`ui`, `gateway`, `ml`, `browser`, `test-full`, `face1_new/requirements.txt`) | `pyproject.toml` extras | outside the selected Tier-3 lock | ⚠ **release-scope decision open** |
| Node UI editors | `package.json` | `package-lock.json`, installed with `npm ci` | ✅ locked |
| Maven dependencies/build plugins | every reactor POM | exact versions or same-revision reactor source; Core's BOM-managed direct dependencies are also explicit | ✅ current audit pinned |
| Container images | deploy, workflow services and Dockerfiles | readable tag + immutable multi-platform manifest digest | ✅ digest-pinned |
| GitHub Actions | `.github/workflows/ci.yml` | full 40-hex commit SHA + reviewed major-tag comment | ✅ SHA-pinned |

`bundle_run.py release` audits this and reports each unpinned entry **with the
exact command to resolve it**. It does not resolve them itself: turning a tag
into a SHA or a digest requires network access, and a generator that quietly
reaches the network produces documents nobody can reproduce offline.

### Pin refresh evidence — 2026-08-01

The network-authorized pass was performed explicitly against the official GitHub API and Docker Hub
registry. The current uncommitted declarations contain these immutable identities; the offline release
audit reads them from source and reports them pinned.

| Mutable label retained for review | Immutable identity selected |
|---|---|
| `actions/checkout@v4` | `11d5960a326750d5838078e36cf38b85af677262` |
| `actions/setup-python@v5` | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| `actions/setup-java@v4` | `d7793b545071e98d581d3bf084a51c3213318a07` |
| `actions/upload-artifact@v4` | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| `postgres:16.9-alpine` | `sha256:7c688148e5e156d0e86df7ba8ae5a05a2386aaec1e2ad8e6d11bdf10504b1fb7` |
| `adminer:4.8.1` | `sha256:34d37131366c5aa84e1693dbed48593ed6f95fb450b576c1a7a59d3a9c9e8802` |
| `eclipse-temurin:25-jdk` | `sha256:201fbb8886b2d273218aa3a192f0afbf7b5ff65ee8cc6ef47f5dce2171f013ea` |

These are supply-chain selections, not timeless aliases. To refresh them, resolve the reviewed tags
again, inspect the upstream change, update the immutable values and rerun the release tests:

```bash
gh api repos/actions/checkout/commits/v4     --jq .sha
gh api repos/actions/setup-python/commits/v5 --jq .sha
gh api repos/actions/setup-java/commits/v4   --jq .sha
gh api repos/actions/upload-artifact/commits/v4 --jq .sha

# With the buildx plugin; otherwise use the registry v2 HEAD response's
# Docker-Content-Digest for the multi-platform index.
docker buildx imagetools inspect postgres:16.9-alpine --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect adminer:4.8.1        --format '{{.Manifest.Digest}}'
docker buildx imagetools inspect eclipse-temurin:25-jdk --format '{{.Manifest.Digest}}'
```

The private sibling SUT checkout needs its own repository secret. The workflow's automatic
`GITHUB_TOKEN` can **never** serve here: GitHub scopes it to this repository alone, so it cannot read
a second private repository under any setting — and it reports the refusal as a misleading 404
"not found". Two credentials are accepted, `SUT_DEPLOY_KEY` (a read-only deploy key — preferred) and
`SUT_REPO_TOKEN` (a fine-grained PAT); see
[40_SIBLING_SUT_CREDENTIAL.md](40_SIBLING_SUT_CREDENTIAL.md) for setup, rotation and how to read the
pre-flight's failure messages. CI checks out the exact manifest revision; missing access is a failed
canonical gate, not an accepted skip.

### Pin refresh evidence — 2026-08-02 (Node 24 action generation)

The 2026-08-01 action pins were the heads of their reviewed major tags, but those
majors (`checkout@v4`, `setup-python@v5`, `setup-java@v4`, `upload-artifact@v4`)
are the Node.js 20 generation, which GitHub is deprecating and currently
force-runs on Node 24. The refresh therefore moves the reviewed major itself to
the Node-24-native generation. Upstream inspection: each new major's release
notes declare the Node 24 runtime bump (runner ≥ 2.327.1, satisfied by
GitHub-hosted runners) as the breaking change; no input or behaviour used by
this workflow changed. Resolved against the official GitHub API on 2026-08-02:

| Mutable label retained for review | Immutable identity selected |
|---|---|
| `actions/checkout@v5` | `fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09` |
| `actions/setup-python@v6` | `ece7cb06caefa5fff74198d8649806c4678c61a1` |
| `actions/setup-java@v5` | `b6effb05e454b25005698d916606bdc6ffcbf961` |
| `actions/upload-artifact@v6` | `b7c566a772e6b6bfb58ed0dc250532a479d7789f` |

Correction found by running the refreshed workflow: `upload-artifact@v5`'s
release notes claim Node 24 support, but its manifest still declares
`runs.using: node20` (the runner annotated it as a deprecated-Node action) —
upstream's own v6.0.0 notes confirm "v5 … was by default still running on
Node.js 20". The reviewed major for upload-artifact is therefore **v6**, whose
manifest declares `node24` and whose only change over v5 is that runtime bump.
v7 (ESM, direct-upload feature) was inspected and deliberately not selected:
a feature major days old is not a supply-chain necessity for this refresh.

Container image digests were not part of this pass and remain as selected on
2026-08-01.

### Open owner decision: which Python feature surfaces define a release?

`requirements-release.lock` is generated from `test,science,deploy` — the profiles Tier 3 actually
installs. It is **not** a lock over the whole published Python surface. Installing the `ui`,
`gateway`, `ml` or `browser` extras, or `generator_trunk/face1_new/requirements.txt`, resolves
dependencies this lock says nothing about.

`bundle_run.py release` reports each uncovered declaration by name rather than reporting the
aggregate as locked. Widening the lock is a **deliberate profile decision** — which surfaces a
release is expected to reproduce — not an installation defect. Do not install every heavy optional
surface merely to make the count green: either select additional release profiles and create
profile-specific locks, or explicitly keep them outside the release claim.

### Refresh process

1. Change **`pyproject.toml`** — never the lock — for a direct dependency.
2. Rebuild a clean environment and regenerate the lock:
   ```bash
   rm -rf .venv && python3 -m venv .venv && . .venv/bin/activate
   python -m pip install setuptools==83.0.0   # must match [build-system]
   python -m pip install -e '.[test,science,deploy]'
   python -m pip freeze --all --exclude-editable --exclude pip > requirements-release.lock
   ```
   (Restore the header comment block; it carries the scope limits.)
3. Run Tier 1 and Tier 2 locally before pushing.
4. Refresh image digests and action SHAs on the same cadence as a release, not
   opportunistically — an unreviewed pin bump is a supply-chain change.

Third-party `LICENSE`/`NOTICE` files that ship with vendored artifacts are
retained as-is; see `Executor_trunk/JANINO_ECJ_JAR_NOTICE.md`.

## 3. CI tiers

| Tier | Trigger | Purpose |
|---|---|---|
| **1** | every push / PR | source, artifact and secret hygiene; deterministic units and contracts; generated-artifact freshness; Maven reactor + Analyzer verifier; the exact 24-case no-database plan |
| **2** | every push / PR (after Tier 1) | isolated PostgreSQL; Python and Java full-chain smokes; canonical engine-demo/Java/automation SUT gates; telemetry reference checks; multi-optional contract; exact `generated-default` fail-closed reason; policy-required refusal; resume/cancel/cleanup |
| **3** | scheduled weekly / manual | fresh checkout, pinned sibling SUT revision and isolated PostgreSQL; clean venv/reactor build; full suite; release manifest; SBOM; capability matrix and CI case list, archived as artifacts |

Tier 1 includes two gates worth naming because they protect the others:

- **Capability matrix freshness** — `capabilities --check docs/33_CAPABILITY_MATRIX.md`
  fails if the generated table has drifted from the registry. One of them would
  otherwise be lying to a reader, and CI would not know which.
- **No unexpected test collection changes** — a module that fails to *collect*
  is a broken suite, not an absent backend. A missing optional dependency must
  present as a classified skip.

Tier 2 asserts two security properties directly rather than trusting them:
a run with no execution policy is refused, and `generated-default` refuses to
run when its container backend is unavailable instead of falling back to the
host.

## 4. Skip classification

Every skip lands in exactly one class. Two classes invalidate release evidence:

| Class | Meaning |
|---|---|
| `EXPECTED_OPTIONAL` | an optional extra is absent (Selenium, PyTorch, gRPC, a lazily built Analyzer), or the test is opt-in |
| `UNSUPPORTED_PLATFORM` | the behaviour is Linux-specific and this runner is not Linux |
| `MISSING_AUTHORIZED_BACKEND` | PostgreSQL, a container runtime, a JDK/jar, or the sibling SUT checkout is unavailable — classified, but **release-blocking**, because absence is not evidence |
| `BLOCKING_UNEXPECTED` | **anything else** — including an unclassified reason |

The default is `BLOCKING_UNEXPECTED` by construction. Both it and
`MISSING_AUTHORIZED_BACKEND` stop the release gate. Classification explains a
missing prerequisite; it does not turn the missing execution into success.

Writing a new skip? Prefix its reason with the class:

```python
pytest.importorskip(
    "selenium",
    reason="EXPECTED_OPTIONAL: browser E2E needs the test-full extra")
```

`test_bundle_release.py::test_every_skip_in_this_repository_is_classifiable`
scans the repository's own skip reasons and fails on any that cannot be
classified — so the taxonomy stays true as tests are added.

### Fixed during this work

Four test modules raised a **collection error** instead of skipping when an
optional dependency was absent (`selenium`, `torch`, and two needing the sibling
SUT checkout). A collection error reads as a broken suite and cannot be
classified at all. All four now use `pytest.importorskip` with a classified
reason, and Tier 1 fails if a new one appears.

## 5. Phase 03/04 verification record — 2026-07-31

The engineering verification of Phases 03 and 04 is **complete**. Recorded here as a summary and an
artifact hash; the runtime log itself is a release artifact and is deliberately not committed.

### Full suite, single process

```bash
BUNDLE_SUT_ROOT=<SUT_CHECKOUT> \
PYTHONPATH=$BUNDLE_SUT_ROOT/automation-scheme-studio/src \
python -m pytest -q -ra
```

```text
1218 passed, 15 skipped, 12 subtests passed in 970.72s (0:16:10)
BUNDLE_PYTEST_EXIT_CODE=0
```

**0 failed, 0 errors.** All 15 skips classify as `EXPECTED_OPTIONAL`; none is
`MISSING_AUTHORIZED_BACKEND` or `BLOCKING_UNEXPECTED`. Re-verified by feeding the log to the release
gate, which reported `passed=1218 failed=0 errors=0 skipped=15 complete=True`, `exit_code=0`, and
exited zero.

Captured summary artifact `sha256:5ddc1aea5a562561e2b4807223eaa89cf0f80136df88dadba601677189f3a1f6`
(exit line, final skip line, summary line, exit-code marker). The **complete** transcript was
overwritten in `/tmp` by a subsequent redundant invocation and is not retained; the summary above and
its hash are what is citable. Regenerate a full transcript with the command above if a complete log
is required.

### Gates

| Command | Expected | Result |
|---|---|---|
| `architecture`, `coverage`, `capabilities --check`, `sut-manifests`, `release` | exit 0 | ✅ |
| `provenance` | exit 0 | ✅ |
| `provenance --fail-on-blockers` | **non-zero** while blockers remain | ✅ exit 1 |
| `git diff --check`, `.rej`/`.orig` scan | clean / none | ✅ |

### Closed locally — engineering pin gaps

The two network-resolved gaps are closed in the current uncommitted tree: all workflow Actions use
full commit SHAs, all declared container images use immutable manifest digests, and the Core direct
dependencies formerly shown as Maven `managed/unresolved` now carry the exact versions already
selected by their pinned BOMs. The required `setuptools` build backend is also exact and included in
`requirements-release.lock`. See §2 for identities and refresh evidence.

### Still open — owner release-scope decision

The lock intentionally covers Tier 3 (`test,science,deploy`), not every optional UI/gateway/ML/browser
surface. The audit names 13 uncovered declarations. This is not fixed by installing packages into a
developer venv: the owner must decide which surfaces define a reproducible release, then either add
profile-specific locks or explicitly keep them outside the release claim. It is not a code blocker
for a private-source commit, but it remains a blocker to claiming whole-surface reproducibility.

### Still open — publication

The provenance gate remains intentionally non-zero. **There is no host-independent blocker count:**
six blocker classes describe tracked-source facts, while Maven and Python licence findings depend on
the exact metadata visible to the running environment. Missing evidence is never converted into the
stronger claim that a dependency declares no licence.

| Blocker | Severity | Depends on |
|---|---|---|
| `FILE_PROVENANCE_UNRESOLVED` | high | the tree |
| `THIRD_PARTY_FORK_REVIEW` | high | the tree |
| `HISTORY_IS_A_SNAPSHOT` | high | the tree |
| `BINARY_REDISTRIBUTION_REVIEW` | medium | the tree |
| `GENERATED_CORPUS_DISPOSITION` | medium | the tree |
| `AI_ASSISTED_CONTRIBUTION` | medium | the tree |
| `MAVEN_LICENSE_FLAGGED` | high | **evidence** — exact coordinate POM was read and needs a licence-family/election decision |
| `MAVEN_LICENSE_UNDECLARED` | high | **evidence** — exact coordinate POM was read and declares no licence |
| `MAVEN_LICENSE_METADATA_UNAVAILABLE` | high | **evidence** — exact coordinate POM is absent or unreadable under the running user's `~/.m2` |
| `PYTHON_LICENSE_UNDECLARED` | medium | **evidence** — exact locked version was read and declares no licence |
| `PYTHON_LICENSE_METADATA_UNAVAILABLE` | medium | **evidence** — exact version is absent or a different version is installed |

> **Do not use a fixed blocker count as a release criterion** (corrected 2026-08-01). Maven evidence
> comes from exact POMs under the running user's `~/.m2/repository`; Python evidence comes from
> `importlib.metadata` of the running interpreter. On the verified host with complete Maven metadata,
> the release venv reports **8** blockers and `/usr/bin/python3` reports **9** because it cannot read
> 12 exact locked Python versions. A clean host without Maven POMs will emit
> `MAVEN_LICENSE_METADATA_UNAVAILABLE` instead of the flagged/undeclared findings. Each result is
> truthful only with its evidence root and interpreter. The invariant is that
> `--fail-on-blockers` **exits non-zero while any blocker remains**.
>
> Earlier revisions first asserted "nine on every host", then "eight persistent plus a conditional
> Python ninth". Both were wrong: Maven was also being read from host state. For both ecosystems,
> "I could not read it" and "it declares nothing" now have different blocker IDs.

The historical publication-specific owner-gate checklist is intentionally omitted from this
private QA edition. Engineering verification being complete does **not** authorize publication or
activate a licence.

## 6. SBOM and release manifest

The release manifest records: source revision **and dirty state**, toolchain
versions, release-defining source/config/lock inputs hashed individually, the
capability matrix identity, canonical SUT inventory, dependency pin audit,
third-party declaration summary, and the test/skip summary. A failed, errored or
truncated pytest log is refused after evidence is emitted; grouped skip counts
must match pytest's terminal summary.

The SBOM is CycloneDX 1.5 over **only** locked Python distributions, Maven
reactor/direct/build declarations, and images found in deploy/CI/Dockerfiles,
each with a `purl`. Unrelated host `site-packages` are excluded. Exact local
coordinate metadata may enrich licences, but missing metadata stays missing.

Neither is committed. Tier 3 uploads both as artifacts with a 90-day retention.

See also: [33_CAPABILITY_MATRIX.md](33_CAPABILITY_MATRIX.md) (generated),
[13_BENCHMARKS_AND_SCALE_CLAIMS.md](13_BENCHMARKS_AND_SCALE_CLAIMS.md),
[18_VERIFICATION_AND_RELEASE_REPORT.md](18_VERIFICATION_AND_RELEASE_REPORT.md).
