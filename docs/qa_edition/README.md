# QA edition — scope and use direction

> **SUPERSEDED — historical record of intent.** As of 2026-08-08 the project has an operative root
> licence: the [Business Source License 1.1](../../LICENSE). The intent recorded here — one personal
> installation for an individual QA engineer or student, AS IS and free of charge — is now carried
> by that licence's **Additional Use Grant**.
>
> These documents are kept because they explain *why* the terms are shaped as they are. They grant
> no rights themselves, and where they differ from `LICENSE`, **`LICENSE` governs**. Neither is
> legal advice.

## Purpose

This edition keeps the complete Bundle engine and practical QA operating surface while removing
historical process material and generated side effects. Its human-centred purpose is to help living
QA engineers move from repetitive manual test-case writing to designing test spaces, interactions,
constraints, unexpected events, and independent oracles.

> **QA imagines and governs the test space; Bundle performs the combinatorial mechanics.**

> **Motto: “Do good; avoid evil.”**

## Included source surface

- Core, optional Sieve, Reader, Executor, Analyzer, and Control Plane;
- Face 1 Old/New, constraint tooling, engine demonstration, CLI/gateway, and launchers;
- QA, LLM-response-testing, safety/red-team, domain, and general reference scenarios;
- exact oracles, fixtures required by tests, schemas, build manifests, and focused tests;
- operational, architecture, authoring, security, Analyzer, migration, and evidence documentation.

The checked-in `generator_trunk/example150726.xlsx` is retained because Core configuration and
Face 1 New use it as a canonical source/test fixture. It is not a runtime-generated workbook.

## Deliberately excluded

- all prior Git history—the new repository begins with one independent root commit;
- historical AI/engineer handoffs, release go/no-go paperwork, and opinion material (the current
  operational code audit remains because retained engineering documents link to it);
- the broad legal-option/publication-preparation package and provenance screenshots;
- generated candidate corpora in `generated_tests*/`;
- local runs, logs, databases, caches, build output, browser profiles, credentials, and API data;
- the helper that assembled training data for teaching an AI Bundle workflow knowledge.

The generators for candidate corpora remain. Their products are ignored and must be regenerated
locally when deliberately needed.

## Draft personal-use direction

The intended no-fee lane is one complete, concurrently active local Bundle installation, controlled
and used by one natural person for lawful non-commercial testing, learning, and research, supplied
**“AS IS”**. Employer, client, organization, production, hosted, shared, redistributed, or
multi-installation use requires separate written terms.

Inference-only AI may assist that person in understanding Bundle or authoring their scenarios,
constraints, adapters, and oracles. Training, fine-tuning, distillation, imitation/model cloning,
model/policy/reward updates, or provider-corpus ingestion intended to teach a machine the
capabilities of Core → Reader → Executor is prohibited by the owner's stated direction.

Ordinary user inputs and outputs are intended to remain user-controlled, subject to actual
authorship, embedded material, third-party/provider terms, privacy, contracts, and applicable law.

Read:

1. [Exclusive Student / QA Engineer single-copy draft](EXCLUSIVE_STUDENT_QA_SINGLE_BUNDLE_COPY_USAGE_DRAFT.md)
2. [Output policy draft](OUTPUT_POLICY_DRAFT.md)

Until an approved operative licence is added, repository access alone grants no permission.
