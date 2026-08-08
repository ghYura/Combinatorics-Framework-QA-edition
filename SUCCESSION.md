# SUCCESSION

This file exists because the author of this work lives in Kyiv, Ukraine, during
a war, and is the only person who holds the knowledge, the rights and the
access to this project. In backup terms the project's bus factor is **1**.

The purpose of this document is simple: **if the author cannot continue, this
work must not die with him.**

> ## Status: NOT YET IN PLACE
>
> As of 2026-08-08 the licence guarantee below **is** in force, but the human
> arrangements are **not**: no custodian has been named, no mirror has been
> handed over, no organisation has been created, and no succession document has
> been signed. Until the checklist at the end of this file is complete, the only
> protection this project has is the licence's Change Date.
>
> Do not read the sections below as a description of the current state. They
> describe what must be done.

---

## The guarantee already built into the licence

The strongest protection is not this document — it is [LICENSE](LICENSE).

Under the Business Source License 1.1:

- Everyone who has received a copy may **copy, modify and redistribute** the
  source. That right is already granted and cannot be withdrawn from copies
  already distributed.
- On the **Change Date, 2030-08-08** — or the fourth anniversary of the first
  public distribution of a given version, whichever comes first — that version
  automatically becomes available under the **GNU AGPL v3.0-only**.

No action by the author, his heirs, a court or any custodian is required for
that conversion to happen. It is a calendar event written into the licence.

This is the answer to the bus factor. A work under "All Rights Reserved" would
have been frozen for seventy years after the author's death; this one opens on
a fixed date regardless of what happens to anyone.

---

## Custodians

Distribution of this work is deliberately private and selective. To ensure the
work survives, complete verified mirrors are to be held by at least three
people, in different locations, in these roles:

| Role | Responsibility | Holder |
|---|---|---|
| Legal successor | Inherits copyright; may decide on licensing and publication | *to be named* |
| Technical steward | Able to build and run the full Bundle from a clean checkout | *to be named* |
| Archive keeper | Holds an offline encrypted copy in a separate geographic location | *to be named* |

Each mirror must be a full history clone, not an export:

```bash
git clone --mirror https://github.com/ghYura/Combinatorics-Framework-QA-edition.git
git clone --mirror https://github.com/ghYura/Combinatorics-Framework.git
git clone --mirror https://github.com/ghYura/SUT.git
```

A mirror that has never been restored and built is not a backup. Each
custodian should verify once that they can restore the repository and complete
the QUICKSTART on their own machine.

---

## Repository custody

The repositories are and remain **private**. Publication is a separate decision
from survival, and this document does not authorise it.

Two facts about GitHub matter here:

- GitHub's *successor* mechanism can only manage **public** repositories. It
  provides no protection whatsoever for private ones.
- Collaborators on a personal private repository automatically receive write
  access; genuine read-only access requires an organisation.

Therefore the repositories should be transferred to a private GitHub
**organisation** with **at least two owners**, so that control does not rest on
a single personal account. Repository transfer preserves commits, issues,
releases and settings.

---

## Two-of-three rule

Where custodians are named, publication of this work, or any change to its
licensing, following the author's death or incapacity, requires the agreement
of **two of the three** custodians.

This protects the work in both directions: against disappearing, and against
being released by a single person acting alone.

---

## What is still required

The items below are legal and organisational, and are recorded here so they are
not forgotten:

- [ ] Name the three custodians and give them mirror access.
- [ ] Confirm at least one custodian has successfully built the project.
- [ ] Create the private GitHub organisation with two owners; transfer repos.
- [ ] Store one encrypted offline copy outside Ukraine.
- [ ] Have a Ukrainian IP lawyer or notary record: who inherits the copyright,
      who may maintain the project, under what confirmed circumstances
      publication is permitted, and who decides commercial matters.
- [ ] Have the Additional Use Grant in `LICENSE` reviewed by that lawyer.

Technical access does not give a person the legal right to publish this code.
Both layers are needed. Until the legal layer exists, the licence's Change Date
is what carries the work forward.

---

Copyright (c) 2012–2026 Yurii Baranov, Kyiv, Ukraine.
