# Contributing

## Private-preview participation

This repository is currently a private technical preview. Contributions are accepted only from
collaborators explicitly authorized by the repository owner.

The project is licensed under the [Business Source License 1.1](LICENSE) — see the Licence section
of the root [README](README.md#licence). Repository access alone still grants no special standing:
your rights are exactly those the `LICENSE` gives any holder of a copy.

**Contribution terms have not been settled.** No CLA or DCO is in force yet, so do not solicit or
merge outside code until the owner has chosen one. This matters more than usual here: BUSL names a
single Licensor, and accepting third-party copyright without an agreement would remove the owner's
ability to set the Change Date or issue commercial licences for the whole work.

## Before changing code

1. Start from the current default branch and use a focused topic branch.
2. Read [QUICKSTART.md](QUICKSTART.md), the relevant design document, and
   [docs/17_DEVELOPER_GUIDE.md](docs/17_DEVELOPER_GUIDE.md).
3. Confirm whether the change affects the Bundle repository, the companion SUT repository, or both.
4. Keep behavior, schemas, documentation, and tests in the same change when they form one contract.

## Change discipline

- Do not commit build products, IDE state, caches, runtime databases, run output, evidence generated
  on a local machine, or operator-owned configuration.
- Never commit credentials. Use synthetic fixtures that are unmistakably not real secrets.
- Keep SUT locations portable through `BUNDLE_SUT_ROOT`; do not add developer-machine paths.
- Preserve the five-part result identity
  `(run_id, candidate_id, attempt, repeat_idx, env_id)` across readers, executors, analyzers, and
  reports.
- State whether generated candidate code is trusted. Do not silently weaken an execution policy.
- Treat public claims, benchmark figures, and historical evidence conservatively; include the
  revision, environment, command, and retained artifact when making a new claim.
- Update quick-start or operating documentation whenever a user-visible command or prerequisite
  changes.

## Commit authorship

- **Never add a `Co-Authored-By` trailer naming an AI assistant.** The trailer asserts authorship.
  An AI assistant that helps prepare a change set is a tool, and this project's engine — Core,
  Reader and Executor — was conceived in Q4 2012 and had solid versions by 2022–2023, long before
  such tools existed as a service. If your editor or agent adds the trailer by default, remove it
  before committing.
- Do record AI involvement, because publication review requires it. Record it in the commit body as
  assistance under owner direction, and in the provenance material — never in an authorship field.
- Do not add other people or organisations as authors or co-authors without the owner's explicit
  instruction.

The owner remains the final authority for authorship and contribution records. AI assistance is a
tool under owner direction and must not be represented through a false co-author trailer.

## Minimum local verification

From a clean Framework checkout:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test,science]'

python -m pytest -q \
  generator_trunk/test_bundle_doctor.py \
  generator_trunk/test_bundle_counts.py \
  generator_trunk/test_fwgen_aliases.py

python generator_trunk/bundle_run.py plan \
  generator_trunk/usecases/event_order \
  --out /tmp/framework-plan

mvn -q clean package
bash Analyzer_trunk/run-tests.sh
```

Run additional focused tests for every component changed. Database, Docker, browser, ML, gateway,
and external-SUT tests must be clearly identified because they require extra services or isolation.

### Running the full suite

The complete suite requires **two clean PostgreSQL instances up and running** — main on
`127.0.0.1:5433` and results on `127.0.0.1:5432` — as described in the root
[README](README.md#the-two-postgresql-instances). Without them roughly thirty tests skip rather than
run, so a green summary line from such a run proves much less than it appears to.

With both databases up and no leftover deploy containers, the suite reports **1375 passed,
2 skipped** — and those two skips are opt-in (ML extra absent, `FACE1_E2E_LIVE` unset).

```bash
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5432
python -m pytest -q
```

When reporting verification results, state whether the databases were running. "All tests passed"
without that detail is ambiguous.

## Pull request handoff

A reviewable pull request explains:

- the user-visible problem and intended result;
- the principal files and contracts changed;
- exact verification commands and outcomes, including skipped tests;
- security, compatibility, migration, and data implications;
- any follow-up work that remains deliberately out of scope.

Do not include secrets or sensitive operational details in the pull-request description or logs.
