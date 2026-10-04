# EvidencePack

**Recoverable tool evidence, bounded input, and quotations you can check.**

[中文](README.zh-CN.md) · [Design](docs/design.md) · [Integration](docs/integration.md) ·
[Measurements](docs/results.md) · [Related work](docs/related-work.md)

Operations agents often receive long logs, configuration dumps and command
output. A prefix can hide the only failure. A summary can alter a port or request
ID. A saved file helps recovery, but does not establish whether a quoted passage
belonged to the evidence pack returned for this answer.

EvidencePack is a small Python library for that boundary. Archive the exact tool
output once, select complete task-relevant excerpts within a serialized budget,
then validate the model's quotations against the returned pack's receipt.

## Who uses it, and what goes in and out?

This is a library for developers who already have an agent and tools. It runs
between tool execution and model input. EvidencePack's core needs no GPU and
does not call a model; your application supplies the model and diagnostic logic.

```text
Tool logs / configuration + task + budget
                  ↓ EvidencePack
Evidence JSON with source, line / record locator, citation ID and pack receipt
                  ↓ your existing model
Diagnosis with citations and exact quotes
                  ↓ EvidencePack verification
Quote accepted or rejected; your application decides what to do next
```

| Call | You provide | You receive |
| --- | --- | --- |
| `capture(source, text)` | A source label and the original text; JSON text may use `media_type="json"` | An artifact containing the stored output's ID |
| `pack(question, ids, budget=2000)` | A task, captured IDs and an allowance | A pack; `pack.to_json()` is the payload to send to your model |
| `verify(pack.receipt, citation, quote)` | The pack ID, quoted excerpt's ID and exact quote | A `Verdict` with `valid` and `reason` |

The receipt is simply the pack's ID for later quotation checks. The output of
`pack()` is evidence, while the diagnostic answer comes from your model. Passing
quotation checks does not establish that the model's reasoning is correct.

After the installation below, run `python -m examples.quickstart` to see both
outputs from generated logs, without any model configuration. Replace its
strings with your tool results. Put `pack.to_json()` into your model's input,
request citations and exact quotes, and check those quotes before accepting the
answer. [The host integration](examples/tool_middleware.py) wraps existing tools.

![Actual fault experiment and measured comparisons](docs/assets/demo.png)

## What it guarantees

- **Exact capture and recovery:** one opaque identity per invocation, SHA-256
  checks, complete line windows or JSON records with recoverable locators.
- **Whole-pack accounting:** the allowance includes JSON, citation IDs and
  metadata. UTF-8 bytes by default; optional real tokenizer counters.
- **Useful selection:** BM25 relevance, duplicate suppression and an initial
  coverage pass across captures, followed by relevance-density filling and
  presentation. Selection makes no model call.
- **Receipt-bound quotation checks:** an exact quotation must occur in a unit
  selected for this receipt. Text elsewhere in the archive cannot pass.
- **Explicit lifetimes:** live receipts pin captures; release permits collection;
  forced deletion leaves tombstones and invalidates dependent receipts.

The core is eight modules with no runtime dependencies. Frozen domain values,
repository/counter/ranker Protocols, a composing service, CLI and optional stdio
MCP adapter separate policy from storage and transport. See the
[design and completed delivery stages](docs/design.md).

## Try it

Python 3.11+:

```bash
git clone https://github.com/chrischen-coder/evidencepack.git
cd evidencepack
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m examples.quickstart
python -m examples.diagnose
```

The `diagnose` example starts two disposable loopback HTTP processes, captures an actual
502 failure, and applies an observation-derived rule patch. It prints the
measured 200 response and accepts a real quote while rejecting an invented one.
Both child processes are cleaned up. This demo uses no LLM.

```python
from evidencepack import EvidenceService, Scope, SQLiteRepository

service = EvidenceService(
    SQLiteRepository(".evidencepack/vault.sqlite"), Scope("local", "incident-1")
)
capture = service.capture("healthcheck", "INFO ready\nERROR connection refused\n")
pack = service.pack("connection refused", [capture.id], budget=2048)
print(pack.to_json())
unit = pack.excerpts[0]
assert service.verify(pack.receipt, unit.citation, "connection refused").valid
assert not service.verify(pack.receipt, unit.citation, "database corruption").valid
assert service.raw(capture.id).text == capture.text
service.release(pack.receipt)
```

Install `'.[tokens]'` for `TiktokenCounter`, `'.[eval]'` for a local
`HuggingFaceCounter`, or `'.[mcp]'` for MCP. Tokenizers must match the model you
use. Reserve the system prompt, question, chat template and transport separately
from the evidence allowance. Oversized records are omitted, with an explicit
omission count; reread a narrower line range or deeper JSON pointer.

CLI and MCP bind the scope at process startup:

```bash
evidencepack --tenant local --session incident-1 capture app.log --source service-log
evidencepack --tenant local --session incident-1 pack ARTIFACT_ID --query 'connection refused' --budget 2000
evidencepack --tenant local --session incident-1 serve --max-budget 8192
```

Use [trusted-host middleware](examples/tool_middleware.py) for large outputs;
sending the full output through a model just to call MCP capture defeats the
purpose. The [integration guide](docs/integration.md) covers rereads, receipts,
deletion and a generic MCP configuration.

## Measured behavior

| Policy | Stress: all evidence | Live: full chain | Live: rule repair | Fresh model: grounded answer |
| --- | ---: | ---: | ---: | ---: |
| Prefix | 0/65 | 0/12 | 0/12 | 0/12 |
| Head / tail | 20/65 | 0/12 | 0/12 | 0/12 |
| BM25 | 60/65 | 8/12 | 12/12 | 11/12 |
| EvidencePack | 60/65 | 12/12 | 12/12 | 11/12 |

The live pack shrinks mean serialized input from **99,689 to 1,847 bytes (98.15%)**,
under a 2,000-byte allowance. EvidencePack takes 13.307 ms median on Linux.
On one RTX 5090 with Qwen3-4B and a separate 1,000-native-token evidence allowance,
final code produces **24/24 correct patches and 23/24 grounded answers** across
the paired and fresh instance runs. BM25 achieves the same model totals.
The fresh run rejects one unsupported submitted quote in each arm.
**62 tests pass on macOS and Linux**, including an actual MCP stdio client.

All policies receive the same complete units, metadata schema and allowance.
They are selection-policy baselines, not full OpenClaw, Hermes or OpenHands
agents. Generated stress, live rule-based repair and model answer grading are
separate experiments. Original prompts, answers, failures, source fingerprints,
the initial unsuccessful presentation order, and reproduction commands are in
[the measurements](docs/results.md).

## Contribution and limits

Existing agents already prune, summarize and recover context.
[The source comparison](docs/related-work.md) acknowledges those capabilities
and ClawVM's fidelity contracts. The contribution here is a compact, executable
contract joining complete evidence, serialized budgeting, invocation provenance,
receipt-bound quotation checks and reference-aware retention. No universal
research novelty or superiority over complete agent systems is claimed.

An accepted quote is not proof that a diagnosis is true. A receipt records the
pack returned to the host; the host must actually deliver that exact pack and
bind it to the checked answer. It does not attest model attention. Scope labels
are application checks, not authentication; hashes are not signatures against
database owners. Keep the vault outside writable agent workspaces. Tool text
remains untrusted, and the host owns repair authorization.

Lexical selection can miss synonyms, coverage is heuristic, and oversized units
may not fit. This alpha release handles textual local evidence; it has no
distributed vault, multimodal support or million-record index. Released receipts
remain checkable only while their captures exist. SQLite deletion is not secure
erasure. See [integration limits](docs/integration.md).

MIT licensed. [Contributing and verification](CONTRIBUTING.md).
