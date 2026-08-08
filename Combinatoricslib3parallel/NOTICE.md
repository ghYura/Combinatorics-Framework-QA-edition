# Third-party attribution — combinatoricslib3parallel

This directory is a **modified derivative** of an upstream open-source library.
It is not original work of the Combinatorics Framework, and the root
[`LICENSE`](../LICENSE) of this repository does **not** apply to it.

## Upstream

| | |
|---|---|
| Project | **combinatoricslib3** |
| Author | Dmytro Paukov |
| Source | <https://github.com/dpaukov/combinatoricslib3> |
| Coordinates | `com.github.dpaukov:combinatoricslib3` |
| Licence | Apache License, Version 2.0 — <https://www.apache.org/licenses/LICENSE-2.0> |

Copyright of the original work remains with its author and contributors.

## Changes made in this fork

Apache-2.0 §4(b) requires a derivative work to carry prominent notice that the
files were changed. The modifications are:

- **Renamed package** — `com.github.dpaukov.combinatoricslib3` became
  `org.ghYura.combinatorics3parallel`, and the Maven coordinates became
  `com.github.ghYura:combinatoricslib3parallel`.
- **Parallel-stream generation** — generators were reworked to support
  index-addressable, parallel-friendly enumeration rather than sequential
  iteration only.
- **Index unranking** — combination and permutation generators resolve an
  element directly from its rank (combinatorial number system) so a generator
  can be split across workers without materialising the sequence.
- **Fast paths** — added short-circuit cases (for example `k=0`, `k=1`, `k=n`)
  that the Framework's Core relies on for performance.
- **Commentary** — explanatory comments were added, some in Ukrainian.

## Outstanding, and deliberately not decided here

The upstream project has been distributed under Apache-2.0, and this
directory's `pom.xml` declares Apache-2.0. Two points still need qualified
review before any public distribution, and this file does not settle them:

1. **Retained notices.** Apache-2.0 §4(c) requires retaining the copyright,
   patent, trademark and attribution notices present in the source form. The
   files in this directory currently carry no upstream copyright header; this
   NOTICE is directory-level attribution, which is not automatically equivalent.
2. **Licence interaction.** How an Apache-2.0 component sits inside a
   repository whose own root licence is the Business Source License 1.1 — and
   what must be reproduced for a recipient — is a legal question, not an
   engineering one.

The repository's provenance model already records this directory as
`third-party-fork` and states that its legal classification is not decided by
that model. See `generator_trunk/bundle/provenance.py`.
