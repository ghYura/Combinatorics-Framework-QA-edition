# 41 — `FW_ReplaceRE` authoring policies (`core.replace.*`)

Five opt-in `fw.properties` keys that make the two silent failure modes of `FW_ReplaceRE`
observable — and, at your choice, fatal — **without restricting anything the feature can express**.

Every default is exactly the behaviour that shipped before these keys existed. An `fw.properties`
with none of them, or with the block deleted, behaves identically to before. Nothing is deprecated.

## Why this is a policy layer and not a redesign

`FW_ReplaceRE` inside `FW_Group` operates on the **inner short keys**, not on the values behind them.
The Core's combinatorics store is `Map<Short, List<Short>>`: every value is interned to a 16-bit
code, and a produced combination is a *list of those codes*. Per group the Core builds
`curStr = w.toString()` — e.g. `"[47, 48]"` — runs `curStr.replaceAll(pattern, replacement)` for each
declared rewrite, then parses the result straight back to `short[]` with `Integer.parseInt`
(`SheetWorker.java`, the `FW_Group` generator stream).

That is the whole point of it, and it is worth keeping. Because the transform sits *between*
generation and parse-back, it can perform surgery on the tuple itself — remap a symbol, splice in a
symbol resolved from another sheet, delete one — and hand the result onward to further composition.
A value-text replacement could not reach that layer at all, and a typed operator over sheets would
not compose as freely. **The capability is the point; the ergonomics were the problem.**

> **Per the author, Yurii Baranov:** the functionality that existed at this place beforehand allowed
> one to **combine even deeper**. That reach comes precisely from operating on the interned *keys*
> rather than on the text they stand for — the rewrite is applied to the combination while it is
> still a tuple of codes, so its output is itself combinable.
>
> These policies are therefore **observation only**. They remove no reach, change no semantics, and
> every one of them defaults to the pre-existing behaviour. Read a `warn` or `strict` setting as
> "tell me what this rewrite is really doing", never as "this rewrite is disallowed".

The three modes are all code-level:

| Mode | Form | Effect |
|---|---|---|
| remap | `FW_ReplaceRE("<code>","<code>")` | substitute one code for another |
| `+`-splice | `FW_ReplaceRE("<pat>","OTHER + …")` | resolve `OTHER`'s **first code** and splice it in |
| delete | `FW_ReplaceRE("<pat>","")` | strip matches from the code-string |

## The two silent failures

**A pattern that cannot match.** A rewrite written against rendered value text — the classic being a
placeholder such as `@S@` inside `sel.append("@S@")` — never matches, because that whole cell is
**one** value with **one** code and the transform only ever sees `"[47, 48]"`. The result is a no-op:
the run is green, every row is present, and the substitution simply never happened. This cost real
debugging time on 2026-06-12 during an LLM-transformer campaign; see the ⚠ section in
[`ZEN_OF_COMBINATORICS.md`](../ZEN_OF_COMBINATORICS.md).

**A replacement that breaks the parse.** If the rewritten code-string is no longer integer-parseable,
`Integer.parseInt` throws and **the row is dropped**, historically with one `WARN` that is easy to
miss in a large log.

## The keys

```properties
core.replace.patternPolicy     = permissive | warn | strict     # default permissive
core.replace.unmatchedPolicy   = ignore     | warn | fail       # default ignore
core.replace.unparseablePolicy = warn       | drop | fail       # default warn
core.replace.identityPolicy    = allow      | warn              # default allow
core.replace.diagnostics       = off        | summary           # default off
```

An unrecognised value **throws** rather than falling back to the default: a policy key exists to make
something loud, so `strict` mistyped as `stict` quietly meaning `permissive` would defeat it.

### `core.replace.patternPolicy` — authoring time

Checks whether a pattern *could* match a code-string, which contains only digits, commas, brackets
and spaces. Regex structure is stripped before the check, so `\d`, `^`, `$`, `|`, `[...]` and escapes
all remain acceptable — only literal text that cannot appear among codes is flagged.

- `permissive` — accept anything (historical).
- `warn` — log a WARNING naming the pattern and explaining what it actually sees.
- `strict` — refuse the run at directive-parse time.

### `core.replace.unmatchedPolicy` — run time

Catches the pattern that is *capable* of matching but never does — the failure that reads as success.
Reported per grouped sheet, after the stream, with the number of rows examined.

- `ignore` (historical) · `warn` · `fail`

### `core.replace.unparseablePolicy` — run time

- `warn` (historical) — one WARNING, row dropped.
- `drop` — drop silently; for rewrites that discard rows deliberately.
- `fail` — refuse the run, quoting the code-string **before and after** the rewrite, e.g.
  `no longer a list of short codes: "[[xx]]" (was "[[17]]")`.

### `core.replace.identityPolicy` — authoring time

Flags a rewrite whose pattern and replacement are identical, such as `("47","47")`. It does nothing
at run time, yet it still changes the emitted directive and therefore the **FW_Seq graph
fingerprint** used for provenance — so it is not free.

- `allow` (historical) · `warn`

### `core.replace.diagnostics` — run time

`summary` logs one INFO line per grouped sheet and changes no outcome:

```
FW_ReplaceRE summary — sheet GROUPED_STAGE (key=2): rows seen=2 rewritten=0 dropped=0;
rows changed per pattern: "47"=0
```

A pattern showing `=0` changed nothing. This is the cheapest way to see, without altering behaviour,
whether a rewrite you believe is running actually is.

## Suggested settings

| Situation | Setting |
|---|---|
| Existing specs, no change wanted | leave everything at the defaults |
| Authoring a new `group_replace` | `patternPolicy=warn`, `diagnostics=summary` |
| CI / release gates | `patternPolicy=strict`, `unmatchedPolicy=fail` |
| A rewrite that deletes rows on purpose | `unparseablePolicy=drop` |
| Auditing what a spec really does | `diagnostics=summary`, `identityPolicy=warn` |

## Where to set them

The file Core reads at run time is rendered from `generator_trunk/config/core.fw.properties`;
`Core_trunk/fw.properties` is the in-repository development copy and carries the same block. To use
a variant for one run without editing either:

```bash
cp generator_trunk/config/core.fw.properties /tmp/strict.properties
echo 'core.replace.patternPolicy=strict' >> /tmp/strict.properties
python generator_trunk/bundle_run.py <spec> --core-props /tmp/strict.properties ...
```

The Reader needs no equivalent keys: it never applies `FW_ReplaceRE` (verified — zero references in
`Reader_trunk`). The rewrite is entirely a Core, `fw2_`-stage concern.

## Known limitations

Two things these policies do **not** fix, recorded so their absence is a decision rather than an
oversight.

**`processAll` swallows per-sheet exceptions.** Each sheet runs in its own virtual thread under
`catch (Exception e) { log.error(...) }`, with no failure record and no effect on the exit code — so
a sheet can fail outright while the run still reports success. That is why the `fail` policies do not
simply throw: they record the violation and re-raise it on the calling thread after the join, which
confines the fix to `core.replace.*`. The general swallow is untouched and remains a live issue.

**`group_replace` is applied on only one of the two `FW_Group` execution paths.** The rewrite loop
lives in the generator-stream path; a second, sub-combo path writes `fw2_` rows without consulting
`replacerHM`. A spec that takes the second path has its rewrites silently ignored. This predates the
policies and is unchanged by them — `diagnostics=summary` will simply print nothing for such a sheet,
which is itself the tell.

## Related

- [`ZEN_OF_COMBINATORICS.md`](../ZEN_OF_COMBINATORICS.md) — the 2026-06-12 correction that first
  documented the code-string semantics
- [`05_SPEC_V1_AUTHORING_GUIDE.md`](05_SPEC_V1_AUTHORING_GUIDE.md) — `group_replace` as a spec field
- [`12_OPERATIONS_AND_TROUBLESHOOTING.md`](12_OPERATIONS_AND_TROUBLESHOOTING.md) — symptom table
- `Core_trunk/AI_QUICK_CORE_UNDERSTANDING.md` — the Core-side summary
