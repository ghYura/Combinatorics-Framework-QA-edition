# Exclusive personal-use lane — Student / QA Engineer single Bundle copy — SUPERSEDED

> **SUPERSEDED by the root [LICENSE](../../LICENSE) on 2026-08-08.** The outcome this document
> asked for is now operative as the **Additional Use Grant** of the Business Source License 1.1:
> an individual QA engineer or student may make production use of one concurrently active
> installation, AS IS and free of charge, for their own learning, exploration, research and
> professional practice.
>
> Two differences from the draft below are deliberate and are what `LICENSE` actually says:
>
> 1. **Redistribution and non-production use are permitted to anyone holding a copy** — BUSL
>    restricts *production* use, not all use. This is intentional: it is what allows the work to
>    survive its author (see [SUCCESSION.md](../../SUCCESSION.md)).
> 2. **The AI-training restriction is a statement of intent, not an enforceable licence term.**
>    See [NOTICE.md](../../NOTICE.md).
>
> This document is retained as the record of owner direction. Where it differs from `LICENSE`,
> **`LICENSE` governs.** It is not legal advice, and the licence text has not yet had qualified
> legal review.

## 1. Owner direction

The owner wants every student, QA engineer, tester, or person learning those skills to have a
no-fee path to the complete Bundle for personal work, while organizations and commercial users pay
for broader rights.

Recommended public-facing promise:

> **A natural person may use one complete, non-crippled local installation of Bundle at a time,
> without a licence fee, solely for that person's lawful, non-commercial testing, learning, and
> research. Organizational, employment, client, production, hosted, redistributed, shared, or
> multi-installation use requires a separate written licence.**

The intended legal vehicle is a counsel-drafted **Bundle Personal Single-Instance Source-Available
Licence**, paired with a separate Commercial/Enterprise Licence. It is a source-available personal
grant, **not an Open Source licence**. Open Source licences cannot reserve use to one person, one
copy, non-commercial purposes, or a profession.

“Exclusive” in this document means that this is the sole default no-fee use lane. It must **not** be
drafted as an “exclusive copyright licence”: each qualifying user receives a non-exclusive,
non-transferable personal permission, and the owner remains free to license Bundle to others.

Eligibility should be determined by the user being a natural person and by the purpose of the use,
not by requiring proof of a job title. This covers students, employed or unemployed QA engineers,
self-taught testers, and people transitioning into QA, while excluding use for an employer,
customer, institution, or other organization.

## 2. What “one Bundle copy” should mean technically

Literal file-copy counting would make normal installation, compilation, backup, and Bundle runtime
behaviour impossible. The enforceable technical concept should therefore be:

> **One concurrently active local Bundle installation/deployment controlled and used only by one
> natural person.**

Within that one installation, all of the following are parts of the same permitted instance, not
extra copies:

- Core, optional Sieve, Reader, Executor, Analyzer, Control Plane, GUIs, gateway, local databases,
  build outputs, and the processes they normally start;
- parallel workers and candidate executions belonging to that installation;
- one non-running archival/backup copy and ephemeral compiler/build copies needed to operate it;
- migration to a replacement machine, provided the old active installation is disabled or removed.

The following are additional instances or broader uses and therefore need separate written terms:

- two concurrently usable installations, VMs, containers, hosts, or user-accessible deployments;
- sharing the installation or credentials with another person;
- exposing it as a service or UI to another person;
- installing it for a team, class laboratory, employer, client, or organization;
- using a nominally personal machine to produce paid, employment, customer, production, compliance,
  or internal-business deliverables.

This definition limits deployments, **not the combinatorial power of the one deployment**. It must
not cap candidate count, Core rows, processes, test scenarios, SUTs, or lawful personal research
performed inside the permitted installation.

## 3. Required permissions in the personal lane

Subject to the final counsel-drafted text, the qualifying natural person should be able to:

- download or otherwise obtain the complete source-available Bundle;
- install, compile, inspect, study, and run one active local installation;
- make private modifications needed for personal testing, learning, and research;
- create unlimited personal scenarios, adapters, constraints, oracles, test packs, candidates,
  reports, and datasets;
- test a lawfully accessible SUT for personal, non-commercial purposes;
- publish truthful research findings and benchmarks without redistributing Bundle code, disclosing
  confidential material, or implying official endorsement;
- keep necessary non-running backup and build copies as defined above.

The personal lane should be complete rather than feature-gated. “One instance” is the economic
boundary; an artificially weakened “community edition” is not proposed.

## 4. Uses outside the personal lane

A separate written Commercial/Enterprise, institutional, classroom, hosted-service, or other
licence should cover, as applicable:

- any use for or on behalf of an employer, business, customer, client, university, laboratory,
  public body, charity, or other organization;
- paid consulting, professional QA/security/compliance/AI-evaluation services, and deliverables;
- production, organizational CI/CD, shared test laboratories, or multi-user operation;
- more than one concurrently active installation;
- redistribution, publication, mirroring, sublicensing, resale, or transfer of Bundle itself or a
  modified Bundle;
- embedding Bundle in another product, offering it as SaaS, or granting third-party access.

Counsel should decide whether a no-fee classroom/research-lab licence is useful as a separate,
express programme. It must not be silently inferred from the one-person grant.

## 5. “AS IS” risk allocation

The complete no-fee personal installation is intended to be provided **“AS IS”** and **“AS
AVAILABLE”**, without warranties or conditions of any kind to the maximum extent permitted by
applicable law. In particular, the personal lane should promise no:

- merchantability, fitness for a particular purpose, non-infringement, correctness, availability,
  defect-free operation, security outcome, or suitability for a specific SUT;
- mandatory maintenance, updates, support response, training, data recovery, or SLA;
- liability for use of generated candidates, test decisions, missed defects, data loss, or other
  direct or indirect consequences beyond limits that applicable law does not allow the parties to
  exclude.

The user remains responsible for validating outputs, protecting data, selecting safe execution
policies, and deciding whether evidence is sufficient for a real decision. A separate written
Commercial/Enterprise agreement may expressly provide paid support, warranties, indemnities, or an
SLA; none should be implied by the no-fee grant.

## 6. AI assistance is allowed; AI training on Bundle capability is prohibited

### Permitted inference-only assistance

A licensed natural person may use an AI model, assistant, or agent as a tool to understand Bundle
or to help create that person's own test scenarios. Permitted examples include:

- explaining documentation, operators, plans, errors, or the Core → Reader → Executor chain;
- helping decompose a task and draft scenarios, constraints, renderers, adapters, oracles, or reports;
- operating the same licensed personal installation on that person's behalf; the agent is not a
  second user or a second Bundle instance;
- using ephemeral context or a private/local retrieval index, provided no model weights or policy
  are updated and protected material does not enter a provider's training corpus.

The AI remains an instrument of the licensed person. The person selects the SUT, validates generated
work, protects data, and remains responsible for every execution and conclusion.

### Prohibited machine training

The personal lane grants no right to use Bundle source, technical documentation, architecture,
examples, execution traces, or capability-embodying outputs to teach an AI machine the skills or
functionality of the Core → Reader → Executor chain or higher-order Bundle composition through:

- pretraining, continued training, fine-tuning, distillation, imitation, or model cloning;
- updating model weights, policies, adapters, reward models, or reinforcement-learning state;
- constructing or contributing to a training/evaluation corpus whose purpose is improving a machine
  at reproducing Bundle's distinctive capabilities;
- uploading protected material to a service that retains prompts, files, or outputs for provider
  training. The current owner direction provides no AI-capability-training exception.

Inference-only LLM testing is allowed: sending a prompt to an AI as the SUT and evaluating its
response does not train that AI when the interaction does not update its model or provider corpus.

User-owned ordinary outputs remain user-controlled, but output ownership is not a back door to train
an AI on protected Bundle technology substantially embodied in those outputs.

### Knowledge stewardship statement

> **Knowledge supplied to an AI does not become the AI's property. It remains attributable to its
> human authors and, in the owner's moral worldview, forms part of the inheritance entrusted by the
> Creator—the Author above—to humankind and nature. Technology and any separately authorized AI use
> should serve humankind, human authors, nature, and ecological well-being.**

This is an ethical and philosophical stewardship statement, not an attempt to claim legal title to
all knowledge or to make an AI system a legal owner. Applicable law, human authorship, provenance,
privacy, and third-party rights still govern. The enforceable boundary is the concrete list of
prohibited training, fine-tuning, distillation, policy-update, and provider-corpus actions above.

## 7. The “cow, milk, and calves” output principle

The owner's intended economic and ethical boundary is:

> **Bundle is the cow. The milk and calves it produces for a user belong to that user.**

In precise project-policy language:

> **The Bundle project makes no ownership claim over a user's inputs or ordinary generated
> outputs merely because Bundle processed or produced them. To the extent the Bundle owner holds
> any rights in designated Bundle-supplied output boilerplate, the operative licence should grant
> the user the rights needed to use, modify, distribute, and commercialize that output.**

“Ordinary generated outputs” should include user-authored specifications, composed candidates,
run artifacts, metrics, reports, Pareto fronts, datasets, and independently created scenarios,
adapters, constraints, and oracles. Ownership of the cow does not create ownership of the milk.
Conversely, ownership of the milk does not permit copying, redistributing, hosting, or relicensing
the cow.

No licence can transfer rights the owner does not have. Third-party input, SUT data, model/provider
terms, confidential information, personal data, and substantial embedded third-party or Bundle
source remain subject to their own rights. The final licence should therefore include a narrow,
express output-freedom grant or exception for any designated Bundle helper/template fragments that
may be copied into ordinary outputs, rather than making an impossible unconditional title promise.
See [`OUTPUT_POLICY_DRAFT.md`](OUTPUT_POLICY_DRAFT.md).

## 8. Mission and motto

### Owner's Declaration — Yurii Baranov, author of Combinatorics Framework

> **My purpose for Bundle is to preserve and develop work for living human QA engineers by
> upgrading their skills and productivity. AI may assist a person in understanding and using
> Bundle or in creating that person's own test scenarios, but Bundle materials must not be used to
> train a machine to reproduce the capabilities of the Core → Reader → Executor chain. Knowledge
> does not become the machine's property; it remains connected to humankind, its human authors and,
> in my worldview, the Creator—the Author above—and should be used for the benefit of humankind,
> nature, and ecosystems.**

This is the owner's declared purpose and moral position, not a prediction that a licence by itself
can guarantee employment. The operative licence should implement the concrete permissions and
restrictions stated in this document; community programmes, teaching, and product design should
advance the broader human-employment mission.

Bundle exists to help QA engineers remain professionally valuable as Systems Under Test outgrow
what manual test-case authoring can reasonably cover. The tester contributes imagination, domain
knowledge, decomposition, constraints, combination rules, and independent oracles. Bundle performs
the repetitive combinatorial mechanics and preserves evidence. It moves the human from manual
test-case writer toward test-space architect; it does not replace the human's judgement.

> **QA imagines and governs the test space; Bundle performs the combinatorial mechanics.**

> **Motto: “Do good; avoid evil.”**

The motto is a values statement and community norm. It should not be the operative legal test for
permitted use: “good” and “evil” are too subjective for predictable licence enforcement. The
objective conditions above—natural person, one active installation, personal non-commercial
purpose—carry the legal boundary.

## 9. Contribution consequence

This licensing direction is not compatible with accepting code under a plain DCO while assuming
the owner can continue licensing the collective code commercially. Before public code
contributions, choose one of these models:

1. accept no external code contributions initially; accept issues, discussion, and independently
   licensed examples only after review; or
2. use a counsel-drafted contributor agreement that expressly permits the personal and commercial
   outbound licences.

The existing DCO draft remains a documented alternative only if the owner later abandons unilateral
commercial relicensing of contributed code and changes the outbound model accordingly.

## 10. Activation checklist

Before this direction becomes an operative licence:

1. Resolve patent/disclosure, file-provenance, third-party, binary/media, and AI-assisted-code gates.
2. Have qualified counsel draft and name the personal licence; do not improvise standard terms by
   editing AGPL, PolyForm, or BSL text.
3. Define the licensed software scope and the exact one-active-installation test.
4. Add the explicit output-freedom grant/exception and test it against generated source templates.
5. Draft the exact inference-only AI permission and AI capability-training prohibition, including
   provider-retention and private-RAG cases.
6. Include counsel-reviewed “AS IS”, warranty, liability, and non-waivable-law language.
7. Draft Commercial/Enterprise and, if desired, classroom/research-lab terms.
8. Select the contribution agreement or initially refuse external code contributions.
9. Only in a separate approved change add the root licence, notices, identifiers, and publication.

Until those steps and the owner gates are complete, this document records intent only and grants
no permission to copy, modify, distribute, or use the repository.
