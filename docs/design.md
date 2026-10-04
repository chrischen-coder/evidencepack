# EvidencePack: design and delivery plan

## Background

An operations agent may collect megabytes of logs, configuration and command
results before identifying a small causal chain. A prefix preview can omit the
only failure line. An LLM summary can change an identifier or omit a number.
Saving the full output helps recovery, but a saved path alone does not establish
which evidence the model actually received or whether its final quotation is
real.

The originating engineering audit revealed a useful direction: externalize tool
results and recover them through references. It also revealed second-resolution
filenames, a fixed prefix preview, and retention independent of live references.
This repository implements a new, generic design from that problem statement.
No originating source files, business tools, data, comments, credentials or Git
history are imported.

## The concrete problem

Given several noisy tool outputs and a bounded input allowance, return useful
complete excerpts, recover omitted material, and reject quotations that were
invented, taken from another session, or never exposed in the cited receipt.

This is an evidence transport and integrity library. It does not replace agent
planning, memory, sandboxes or a model, and does not prove that a supported
quotation entails the surrounding claim.

## Technical choices

1. **Immutable repository.** SQLite stores original UTF-8 text, SHA-256, scope
   and tool invocation identity in one transaction. Every capture receives an
   opaque random ID; repeated content cannot overwrite another invocation.
2. **Atomic evidence units.** Text uses complete line windows. JSON uses complete
   records at RFC 6901 pointers. The raw input remains byte-identical as UTF-8
   text; pretty-printing is only a model projection. Oversized units are omitted
   explicitly and can be reread; they are never silently sliced.
3. **Selection strategy.** A replaceable ranker uses lexical relevance and
   diagnostic signals. A coverage-first pass gives relevant independent sources
   a chance before filling the remaining budget. It is a heuristic, not an
   optimal knapsack solver or a learned causal model. Present selected units by
   relevance density, retaining source and locator metadata. Alphabetical source
   ordering obscured the primary comparison in the first model evaluation; the
   original run is retained with the final measurements.
4. **Budget contract.** A replaceable counter measures the final serialized
   pack, including identifiers and metadata. An insufficient budget raises a
   typed error. Default units are UTF-8 bytes; optional tokenizers measure their
   own token counts. Host prompts and transport wrappers require separate space.
5. **Exposure receipt.** The selected units and digests are committed before a
   pack is returned. A quotation is valid only if its citation belongs to that
   receipt and the quote occurs in that exact unit. Matching text elsewhere in
   the archive is insufficient.
6. **Lifetime contract.** Active receipts pin their captured artifacts. Explicit
   receipt release permits garbage collection. Forced deletion invalidates live
   references with a visible tombstone rather than silently resolving elsewhere.
7. **Ports and adapters.** Frozen domain types, a repository Protocol, a ranking
   strategy and a counter Protocol keep persistence, policy and transports
   separate. A small facade composes them. CLI and MCP use the same facade.

## Minimal layout

```text
src/evidencepack/
  domain.py       immutable values, errors and contracts
  repository.py   transactional SQLite evidence and receipts
  selection.py    unit construction, ranking and budget packing
  counters.py     byte and optional tokenizer adapters
  service.py      capture, pack, reread, verify, release, collect
  cli.py          command-line adapter
  mcp_server.py   host-bound stdio adapter
tests/            integrity, isolation, lifetime, budgets and transport
benchmarks/       generated tasks and captured local fault experiments
examples/         runnable diagnosis and agent integration
docs/             design, related work and measured results
```

Public methods get concise, newly written contract docstrings. Avoid copied
comments, compatibility layers, metaclasses, generic plugin loaders, business
configuration and an unnecessary web framework.

## Delivery sequence and acceptance criteria

| Stage | Deliverable | Acceptance |
| --- | --- | --- |
| 1 | Public-source comparison and this design | Existing mechanisms acknowledged; differences scoped to reviewed code |
| 2 | Core library and tests | Exact recovery, scoped reads, complete units, hard serialized budget, receipt verification |
| 3 | CLI and MCP | A real stdio client captures, packs, rereads and verifies through the protocol |
| 4 | Real fault corpus | Spawned HTTP services produce failures; measured repair makes health checks pass |
| 5 | Controlled evaluations | Equal-budget prefix, head/tail, lexical retrieval and EvidencePack; report quality, cost, latency and failures |
| 6 | Independent GPU evaluation | Native-tokenizer model run when server access is available; no inferred model results |
| 7 | Release | Installable wheel, CI, demo image, reproducibility, source/secret audit and GitHub release |

Only one project is shipped first. A later incident reasoning engine is a
possible second project, but is outside this release and has no claimed results.

## Evaluation discipline

Generated stress cases test evidence positions, identifiers, JSON records,
distractors and cross-source coverage. They are not production incidents. The
local fault corpus records actual process output and HTTP failures and verifies
repairs; it is still a controlled lab, not a production benchmark.

Baseline policies run under the same serialized allowance. A simple lexical
baseline is included because beating truncation alone is weak evidence. Report
record/evidence retention separately from LLM answer quality. Do not claim
superiority over complete OpenClaw, Hermes or OpenHands agents: they can reread,
search, use other policies and choose other models.

Model evaluations store prompts, answers, token usage, wall time and exact
grading outcomes. Model failures count in the denominator. Quote validity is
reported separately from correct diagnosis. Compare raw context separately when
it exceeds the common budget; do not silently give one arm more input.

## Limits and risks

SQLite and scope labels provide application-level separation, not OS sandboxing
or authentication. The trusted host supplies tenant/session and must keep the
vault outside writable agent workspaces. Tool text remains untrusted. An exact
quote can be misleading or malicious. Do not turn this verifier into permission
to execute a repair; the host owns action policy.

Lexical ranking can miss synonyms or unknown identifiers. Large JSON records
can exceed the allowance. Receipts pin storage until released; operators need
explicit lifecycle integration. This first release supports textual outputs,
not multimodal evidence, distributed storage or million-record indexing.
