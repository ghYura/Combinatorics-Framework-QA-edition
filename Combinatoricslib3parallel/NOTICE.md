# Third-party attribution — combinatoricslib3parallel

**This library is Dmytro Paukov's work, not the Combinatorics Framework's.**

It is the one component of this repository that its author does not claim. The
Framework uses this library heavily and adapts it for its own needs, but makes
no ownership claim over it, and the root [`LICENSE`](../LICENSE) of this
repository does **not** apply to this directory.

Everywhere else in this repository the Java engine — Core, Reader, Executor and
Analyzer — is the Framework author's own work. This directory is the exception,
and is called out as such so that no reader infers shared authorship in either
direction: the upstream author did not write the Framework, and the Framework's
author does not claim this library.

## Upstream

| | |
|---|---|
| Project | **combinatoricslib3** |
| Author | Dmytro Paukov |
| Source | <https://github.com/dpaukov/combinatoricslib3> |
| Coordinates | `com.github.dpaukov:combinatoricslib3` |
| Licence | Apache License, Version 2.0 — <https://www.apache.org/licenses/LICENSE-2.0> |

Copyright of the original work remains with its author and contributors.

## Why this adaptation exists — and where the `parallel` in its name comes from

The base library generates each combinatorial family as **one sequential
stream**. The Framework's Core needs the opposite: the space divided *before
anything is generated*, so N workers can each produce their own portion.

That capability was proposed upstream, by this project's author, as
**[combinatoricslib3 issue #22, "Return Stream[] or List&lt;Stream&gt; chunks for
combinations" (2023-04-16)](https://github.com/dpaukov/combinatoricslib3/issues/22)**:

> Return -array[] or -List() of chunked Streams of precalculated (but not yet
> generated as output) combinations according to input parallel thread number as
> a divisor for total precalculated number of output combinations…
>
> It is important, that array `Stream[]` or `List<Stream>` should not be
> prefilled by output generated data, just **chunks of stream** to be used for
> further parallel processing.

The proposal remains open upstream and was not implemented there. The design and
its implementation in this directory are therefore the Framework author's own
contribution; the library it builds on is Dmytro Paukov's. That is the whole
reason a fork exists at all, and the reason its name ends in `parallel`.

## Adaptations made for this project

Apache-2.0 §4(b) requires a derivative work to carry prominent notice that the
files were changed. Recording them is a licence obligation and a courtesy to the
upstream author — not an authorship claim over the library itself. They are:

- **Chunked parallel generation** — the capability of issue #22: a family is
  split into per-thread stream chunks that are *not* pre-filled, so each worker
  generates only its own share and nothing is materialised in advance.
- **Index unranking** — combination and permutation generators resolve an
  element directly from its rank (the combinatorial number system). This is what
  makes the split above possible: the closed-form cardinality of each family
  gives the chunk boundaries before a single element exists.
- **Fast paths** — short-circuit cases (`k=0`, `k=1`, `k=n`) that the Core relies
  on for performance.
- **Renamed package** — `com.github.dpaukov.combinatoricslib3` became
  `org.ghYura.combinatorics3parallel`, and the Maven coordinates became
  `com.github.ghYura:combinatoricslib3parallel`.
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
