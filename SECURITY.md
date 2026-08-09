# Security policy

## Status and supported scope

Framework Bundle is a technical preview, not a hardened multi-tenant service. Security fixes are
maintained only on the current default branch. There is no guaranteed response-time SLA.

The project is licensed under the [Business Source License 1.1](LICENSE); what you may do with the
source is set out there and in the Licence section of the [README](README.md#licence). Repository
access grants no rights beyond it.

Read [10_SECURITY_AND_SANDBOXING.md](docs/10_SECURITY_AND_SANDBOXING.md) before running generated
candidates: this project executes code it constructs, so the execution profile you choose is a
security decision, not a performance one.

## Reporting a vulnerability

Report suspected vulnerabilities privately:

1. Prefer GitHub's **Security** tab and a private vulnerability report when that feature is enabled.
2. Otherwise contact the repository owner through an existing private project channel.

Do not put exploit details, credentials, personal data, or unredacted logs in an issue, discussion,
commit, pull request, or chat shared beyond the response team. Include the affected revision, a
minimal reproduction, impact, and a safe remediation suggestion. Use synthetic credentials and
throwaway data.

## Security boundaries users must understand

- The default `trusted-local` execution policy is unsandboxed and inherits the host environment and
  network. It is for trusted code only.
- Use `generated-default` for untrusted generated candidates. It requires a working rootless
  container backend and fails closed when isolation is unavailable.
- The live Reader-to-Executor gRPC transport is currently plaintext and unauthenticated. Keep it
  host-isolated and never expose its port to an untrusted network.
- The local deploy profile must remain bound to `127.0.0.1`. Do not publish its PostgreSQL,
  monitoring, or gateway ports to a LAN or the Internet.
- Companion SUTs are test fixtures with different assurance levels. Their presence does not make
  candidate code safe.

See [Security and sandboxing](docs/10_SECURITY_AND_SANDBOXING.md) for the detailed threat model and
operating rules.

## Credential handling

- Never commit `.env`, token maps, private keys, certificates, database passwords, or cloud/API
  credentials.
- Keep `generator_trunk/deploy/.env.template` placeholder-only. `bundle deploy up` creates the
  real local `.env` with mode `0600`, generated credentials, and non-secret checkout-scoped
  volume names. Preserve that file with its volumes; never auto-reset or delete mismatched data.
- Supply secrets through approved environment or configuration-secret channels and ensure logs and
  bug reports are redacted.
- Rotate a credential immediately if it may have entered source, an artifact, a log, or Git history.

The repository's ignore and Docker-context rules are defense in depth, not permission to store a
secret in the worktree.
