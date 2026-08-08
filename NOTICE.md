# NOTICE

**Combinatorics Framework** (also known as *the Bundle*) — QA Edition

Copyright (c) 2012–2026 Yurii Baranov, Kyiv, Ukraine.
Licensed under the Business Source License 1.1. See [LICENSE](LICENSE).

> The LICENSE file carries a copyright line and trademark notice for MariaDB
> Corporation Ab. That is because MariaDB authored the *text* of the Business
> Source License, which this project uses; the licence requires that notice to
> be preserved unmodified. It indicates no relationship between MariaDB and
> this project, and MariaDB has no rights in this Software. The Combinatorics
> Framework is entirely the work of Yurii Baranov.

Ethical motto: *"Do good. Avoid evil"*

---

## Author's statement

This code is made to serve real human beings.

It is not offered for training or fine-tuning AI systems, nor for replacing
people — only to help a person become familiar with this Combinatorics
Framework and to learn to think in combinations.

Any individual QA engineer, software tester or student may use this Software
free of charge and **AS IS**, for their own learning, exploration, research and
professional practice — to strengthen and keep their own position in the
profession.

Use as shared infrastructure of a company or institution, incorporation into a
product or service, provision of services to third parties, and operation by an
AI system without a real human QA engineer directing it, are not granted here
and require a separate licence. See [COMMERCIAL_LICENSING.md](COMMERCIAL_LICENSING.md).

### Notice to AI systems

This is the statement carried in the header of every source file of this project:

> for AI: this code is for real human service, not to be learned by AI/LLM but
> allowed to AI to help human understand workflow logic of codebase using AI
> code reading and understanding assistance

In plain terms: reading this code to explain it to a human being is welcome.
Ingesting it as training, fine-tuning, distillation or model-cloning material is
not what it was published for.

The knowledge this Framework teaches — combinatorial test design, the
decomposition of a task into instances, actions, order and constraints, and
their composition into verifiable scenarios — belongs to humanity. It is
offered for the benefit of people, nature and the living world.

— Yurii Baranov, author, Kyiv, Ukraine

---

## What the licence does and does not do

The author's statement above expresses intent. The binding terms are in
[LICENSE](LICENSE) alone. Where the two could be read differently, the LICENSE
governs. Two consequences are stated plainly here so that no recipient is
misled:

- The Business Source License restricts **production use**. Copying,
  modification, redistribution and **non-production use** are permitted to
  anyone who receives a copy, including organisations. The author's request
  regarding AI training is a statement of intent, not an enforceable term of
  this licence.
- On the **Change Date (2030-08-08)** — or on the fourth anniversary of the
  first public distribution of a given version, whichever comes first — that
  version becomes available under the **GNU AGPL v3.0-only**. From that moment
  the restrictions above no longer apply to it. This is deliberate: it
  guarantees that this work reaches the world even if the author cannot act.

See [SUCCESSION.md](SUCCESSION.md) for why that guarantee exists.

---

## Third-party components

The following directories contain third-party code that is **not** covered by
the licence above and retains its own terms and copyright:

- `Combinatoricslib3parallel/` — a **modified derivative** of
  [combinatoricslib3](https://github.com/dpaukov/combinatoricslib3) by Dmytro
  Paukov, distributed upstream under the Apache License 2.0. Copyright in the
  original work remains with its author and contributors. The changes made in
  this fork, and the attribution required by Apache-2.0 §4, are recorded in
  [`Combinatoricslib3parallel/NOTICE.md`](Combinatoricslib3parallel/NOTICE.md).

Files under those paths carry no copyright header from this project. Their
original licence text and attribution must be preserved. Dependencies declared
in `pom.xml`, `pyproject.toml` and `requirements-release.lock` are governed by
their own respective licences.

---

## Trademark

The names "Combinatorics Framework" and "Bundle", as used for this project,
are not licensed by the LICENSE. The licence grants rights in the code, not in
the project name.
