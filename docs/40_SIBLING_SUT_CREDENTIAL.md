# 40 — The sibling-SUT credential for CI

Tier 2 and Tier 3 check out the companion repository `ghYura/SUT` at a pinned revision, because the
canonical SUT gates test the two repositories *together*.

**This page applies while `ghYura/SUT` is private.** It is about giving CI read access across two
private repositories; it neither publishes anything nor grants write anywhere. If SUT is ever made
public, the credential stops being necessary — see [When SUT is public](#when-sut-is-public) at the
end. Nothing here forces either repository to stay private.

## Why a credential is needed at all

Every workflow run receives an automatic `github.token`. GitHub scopes it to **the repository the
workflow lives in**. It can never read a second private repository, and no workflow setting changes
that.

The failure is also actively misleading: GitHub reports a private repository the caller cannot see
as **404 "Repository not found"**, not 403. Before the pre-flight existed, Tier 2 died with

```
fatal: repository 'https://github.com/ghYura/SUT/' not found
```

which accuses the repository of not existing. The pre-flight now diagnoses the real cause before
`actions/checkout` is reached.

## Two supported credentials

| | `SUT_DEPLOY_KEY` (preferred) | `SUT_REPO_TOKEN` |
|---|---|---|
| What it is | private half of a read-only deploy key on `ghYura/SUT` | fine-grained PAT, `Contents: Read` on `ghYura/SUT` |
| Scope | exactly one repository | whatever the PAT grants |
| Write access | impossible — the key is registered read-only | none, if minted correctly |
| Identity | none; not tied to a person | acts as the user who minted it |
| Expiry | none | expires; CI breaks on that date |
| Revocation | delete the key from `ghYura/SUT` | revoke the token |

The deploy key is preferred because it cannot widen and cannot silently lapse. Configure **either**
one — the pre-flight takes the deploy key when both are present.

## Setting up the deploy key

```bash
# 1. Generate a keypair. No passphrase: CI cannot type one.
ssh-keygen -t ed25519 -N '' -C 'framework-ci-sut-readonly' -f /tmp/sut_deploy_key

# 2. Register the PUBLIC half on the SUT repository, read-only.
gh api repos/ghYura/SUT/keys -X POST \
  -f title='Framework CI — read-only sibling checkout' \
  -f key="$(cat /tmp/sut_deploy_key.pub)" \
  -F read_only=true

# 3. Store the PRIVATE half as a secret on THIS repository.
gh secret set SUT_DEPLOY_KEY --repo ghYura/Combinatorics-Framework-QA-edition < /tmp/sut_deploy_key

# 4. Destroy the local copy — the secret store is now the only place it lives.
shred -u /tmp/sut_deploy_key /tmp/sut_deploy_key.pub 2>/dev/null || rm -f /tmp/sut_deploy_key /tmp/sut_deploy_key.pub
```

Verify before relying on it:

```bash
gh api repos/ghYura/SUT/keys --jq '.[] | "\(.id) read_only=\(.read_only) \(.title)"'
gh secret list --repo ghYura/Combinatorics-Framework-QA-edition
```

`read_only=true` is the property that matters. A deploy key added with write access would let CI
push to the SUT repository, which nothing here needs.

## Setting up the PAT instead

Create a **fine-grained** token at <https://github.com/settings/personal-access-tokens/new>:
resource owner `ghYura`, *Only select repositories* → `ghYura/SUT`, Repository permissions →
**Contents: Read-only**, everything else *No access*. Then:

```bash
gh secret set SUT_REPO_TOKEN --repo ghYura/Combinatorics-Framework-QA-edition
```

Do not use a classic token with the `repo` scope: that grants read **and write** across every
repository you own, for a job that only clones.

## Reading the pre-flight's failures

All four states fail loudly. None skips — a canonical gate that self-skips reads as green while
never having run.

| Message | Meaning | Action |
|---|---|---|
| `no credential … is configured` | neither secret is set | follow one of the two setups above |
| `SUT_DEPLOY_KEY is set but cannot read …` | the secret is not the private half of a registered key, or the key was removed | re-run the deploy-key setup |
| `SUT_REPO_TOKEN is set but cannot read …` | the PAT lacks `Contents: Read` on `ghYura/SUT`, or has expired | re-mint and re-store it |
| `the pinned canonical revision … does not exist` | **not a credential problem** — the pinned SUT revision is gone | history moved under the gate; fix `SUT_SIBLING_PIN` |

The last one is the valuable case: the credential is fine and something genuinely moved.

## Rotation

Deploy key: generate a new pair, register it, overwrite the secret, then delete the old key from
`ghYura/SUT`. PAT: re-mint and overwrite the secret. In both cases the secret is replaced in place
and no workflow change is needed.

## When SUT is public

If `ghYura/SUT` becomes public, this whole mechanism becomes unnecessary: an anonymous clone can read
a public repository, and the automatic `github.token` is sufficient. At that point:

- **Delete the credential rather than leaving it.** Remove the deploy key from `ghYura/SUT`
  (`gh api -X DELETE repos/ghYura/SUT/keys/<id>`) and delete the secret from this repository
  (`gh secret delete SUT_DEPLOY_KEY`). A credential nobody needs is a credential nobody rotates.
- **The pre-flight still earns its place.** Its most valuable failure — *"the pinned canonical
  revision does not exist"* — is not about credentials at all, and a public SUT can still move its
  history out from under the gate.
- **One asymmetry to keep in mind.** Workflows triggered by a pull request *from a fork* do not
  receive secrets. While SUT is private, the SUT-dependent tiers therefore cannot pass on an outside
  contributor's PR, no matter how the credential is configured. Publishing SUT is what fixes that,
  not a different secret.

## What this does not do

It does not change any repository's visibility, does not grant write access anywhere, and does not
affect the SUT repository's own CI, which has no cross-repository dependency.
