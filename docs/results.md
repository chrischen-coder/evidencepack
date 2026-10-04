# Measurements and reproduction

Campaign: 2026-10-04. All policies and grading are visible in `benchmarks/`.
Reports use this fixed campaign date. These are controlled development-lab
results, not production incidents or a comparison of complete agent systems.

## What is being evaluated

The question is whether a small evidence allowance retains the observations
needed for a known configuration/runtime comparison, while preserving exact
provenance and recoverability. It does not measure autonomous discovery of an
unknown failure class, browsing a repository, planning a repair or production
reliability.

Four policies share the same captures, complete three-line/JSON units, citation
schema, counters and allowance: prefix, alternating head/tail, BM25 relevance
density, and EvidencePack's initial coverage pass plus density filling. BM25
uses the same ranker, diagnostic bonus and duplicate suppression. Even baselines
receive receipts, so quotation checks cannot unfairly favor one arm.

The core contribution is the combined evidence contract. These experiments
compare selection policies inside that contract; they do not benchmark it
against every feature of OpenClaw, Hermes or OpenHands.

## Complete evidence under a 2,000-byte allowance

| Policy | Stress complete | Live chain complete | Actual rule repairs | Mean packed bytes | Selection + receipt median |
| --- | ---: | ---: | ---: | ---: | ---: |
| Prefix | 0/65 | 0/12 | 0/12 | 1,912 | 3.156 ms |
| Head / tail | 20/65 | 0/12 | 0/12 | 1,912 | 7.436 ms |
| BM25 | 60/65 | 8/12 | 12/12 | 1,846 | 10.325 ms |
| EvidencePack | 60/65 | 12/12 | 12/12 | 1,847 | 13.307 ms |

Stress comprises 20 middle-log, 20 JSON, 20 cross-source tasks and five deliberately
oversized records. The five large records do not fit and are counted as failures,
not silently truncated or removed from the denominator. BM25 and EvidencePack
both retain every required observation in the other 60 cases.

The real lab starts two Python HTTP subprocesses on loopback. Wrong upstream
port, wrong health path and wrong demo token each produce an actual 502 response;
there are four instances per family. Requests and telemetry add deliberate benign
noise around the actual observations. Configuration diagnostics also include
generated metadata rows. The outputs are real process/HTTP observations in a
controlled, noisy fixture; the noise layout is not a natural production sample.

Complete-chain grading requires the configuration, backend listener and specific
failed request. A transparent rule repairer uses selected CONFIG/LISTENER values,
applies the minimal change and performs a real HTTP health check. It needs only
two observations, which explains why BM25 can repair all cases without retaining
the entire three-observation chain. Configurations are restored between policies.

Mean raw serialized source text is 99,689 bytes; EvidencePack uses 1,847 bytes,
a **98.15% reduction**. This is a byte reduction, not an inferred token or billing
saving. The Linux selection/receipt median is 13.307 ms, p95 14.001 ms; BM25 takes
10.325 ms median. Capture/segmentation costs are recorded separately in rows.
The macOS repeat has identical retention and repair counts, with EvidencePack
8.747 ms median. There are zero budget violations for all four policies.

The EvidencePack stress and live runs perform 480 exact-positive checks and
480 fabricated-negative checks, with no failed checks. All arms share this
verifier; the checks confirm its contract, not a model hallucination rate.

## Actual model inference on an RTX 5090

| Policy | Paired correct patch | Paired grounded | Fresh correct patch | Fresh grounded | Fresh valid/submitted quotes | Fresh mean prompt tokens | Fresh median generation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Prefix | 0/12 | 0/12 | 0/12 | 0/12 | 0/0 | 1152.8 | 0.2219 s |
| Head / tail | 0/12 | 0/12 | 0/12 | 0/12 | 12/13 | 1184.7 | 1.3077 s |
| BM25 | 12/12 | 12/12 | 12/12 | 11/12 | 34/35 | 1206.8 | 4.0079 s |
| EvidencePack | 12/12 | 12/12 | 12/12 | 11/12 | 34/35 | 1207.5 | 3.9668 s |

Model: [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
revision `cdbee75f17c01a7cc42f958dc650907174af0554`.
BF16, Transformers 4.57.6, PyTorch 2.8.0+cu128, CUDA 12.8, SDPA, one RTX 5090,
greedy decoding, no thinking, maximum 700 generated tokens. The 1,000-token
allowance covers the evidence JSON with this model's native tokenizer. The
system prompt, question and chat template are added equally and counted in the
recorded prompt usage; 1,000 is not the total context-window limit.

Every case receives the same explicit comparison rule and JSON answer schema.
The model is asked for a diagnosis and patch but does not execute a repair. A
correct patch requires the exact fault family and minimal field/value change.
Grounded success also requires every submitted quote to pass its receipt check,
and quotes supporting the relevant field from both configuration and
backend-runtime sources. A matching quote alone is insufficient. Malformed
answers and inference errors count as failures; invalid JSON is not repaired.

The initial alphabetical-source presentation scored 9/12 correct patches and
8/12 grounded successes, while BM25 scored 12/12 and 11/12. Complete evidence did
not ensure correct use. The selected excerpts were subsequently presented by
relevance density; the same 12 captured cases were rerun and both policies scored
12/12. The initial [model report](results/2026-10-04/pre-salience/qwen4b/report.json)
and [all answers](results/2026-10-04/pre-salience/qwen4b/rows.jsonl) are retained.
The source change is [a small presentation patch](results/2026-10-04/presentation-change.patch).

This was an exploratory iteration on these cases, not a held-out discovery test
or an isolated proof of causality. Invocation/receipt IDs were regenerated and
can change prompt tokenization and model outputs. Freshly captured instances
were then evaluated without further implementation or prompt changes. They use
the same three known fault families and fixture structure, so they do not test
unseen failure classes. All three model runs are published. One model and small
samples cannot establish general superiority; BM25 remains a strong baseline.

On the fresh instances both policies produce 12/12 correct patches, with 11/12
grounded successes. In `real-path_mismatch-3`, the third submitted quotation
does not match its cited unit; the full answer fails the acceptance rule even
though the configuration/runtime quotes and patch are correct. That is a
concrete failure detected by the receipt check. The final two runs together have
24/24 correct patches and 23/24 grounded successes per policy.

Generation latency includes actual CUDA completion but excludes model load and
evidence capture/packing. Policy order rotates across cases. The first generation
is cold, and short refusals/unknown answers naturally take less time. Latency is
reported descriptively; no throughput advantage is claimed.

## Artifacts and fingerprints

Current implementation/benchmark SHA-256:
`eb215762aa0a10bd276e27f0851b0c1b58a9d71daf5f3c796db4b5ee4c4a0ebe`.

Initial implementation/benchmark SHA-256:
`088df377a3b7481dd9b677ebea5bb4789ecaba1aaa907b72d0fc5bf3c453ea4a`.

`benchmarks.provenance.source_digest()` hashes paths and file bytes in `src/` and
`benchmarks/`, independently of Git state. Reverse the presentation patch to
recover the initial fingerprint. Tests/docs are outside this code fingerprint.

| Artifact | Contents |
| --- | --- |
| [Linux final report](results/2026-10-04/linux/report.json) | 65 stress + 12 live fault cases, per-policy costs and checks |
| [Linux captures](results/2026-10-04/linux/cases.jsonl) / [rows](results/2026-10-04/linux/rows.jsonl) | All raw generated/loopback observations and selected packs; input for fresh model validation |
| [macOS final report](results/2026-10-04/macos/report.json) / [rows](results/2026-10-04/macos/rows.jsonl) | Independent live fault rerun and identical retention counts |
| [Paired model report](results/2026-10-04/qwen4b/report.json) / [rows](results/2026-10-04/qwen4b/rows.jsonl) | Final code on the initial 12 captures; all prompts, answers, tokens and outcomes |
| [Fresh model report](results/2026-10-04/qwen4b-validation/report.json) / [rows](results/2026-10-04/qwen4b-validation/rows.jsonl) | Unchanged final code on 12 newly captured fault instances |
| [Initial captures](results/2026-10-04/pre-salience/linux/cases.jsonl) | Input shared by the initial and paired final model runs |
| [Model manifest](results/2026-10-04/qwen4b/model-manifest.json) | Official revision and verified inference-file hashes |
| [Environment](results/2026-10-04/environment-linux.json) | Exact installed package versions, without host paths or credentials |
| [Installed dependency pins](results/2026-10-04/requirements-linux.txt) | Reproduction aid; CUDA PyTorch needs the official wheel index |

All three weight shards and tokenizer files matched the official revision's
SHA-256 or Git blob hashes before inference. The host used an existing local
model cache after Hugging Face downloads failed. No weights are redistributed.
The published corpus contains only generated and disposable loopback-lab data.
No private engineering data, server credentials or corporate repository history
are included.

## Reproduce

From a clone, with Python 3.11+:

```bash
python -m pip install -e '.[dev,tokens,mcp]'
ruff check src tests benchmarks examples
ruff format --check src tests benchmarks examples
mypy
python -m pytest
python -m benchmarks.run --output benchmark-runs/repeat --stress-count 20 --real-per-family 4
python -m build
```

The 62 tests cover concurrent capture, exact raw recovery, scope separation,
complete records, invalid JSON pointers, serialized Unicode/token budgets,
exposure checks, tampering, lifecycle races, actual MCP stdio, actual HTTP
repair, model grading and evidence presentation.

GPU reproduction requires a local snapshot of the pinned model and CUDA PyTorch:

```bash
python -m pip install -e '.[eval]'
python -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install transformers==4.57.6
export EVIDENCEPACK_MODEL=/absolute/path/to/Qwen3-4B-Instruct-2507
python -m benchmarks.model_eval \
  --cases docs/results/2026-10-04/linux/cases.jsonl \
  --tokenizer "$EVIDENCEPACK_MODEL" --model "$EVIDENCEPACK_MODEL" \
  --model-id Qwen/Qwen3-4B-Instruct-2507 \
  --revision cdbee75f17c01a7cc42f958dc650907174af0554 \
  --budget 1000 --output benchmark-runs/model-repeat
```

Use `pre-salience/linux/cases.jsonl` to reproduce the paired-case input instead.
Ports, request IDs, invocation/citation IDs and wall times can differ in a fresh
live run; greedy inference can also vary with hardware/library details and ID
strings. Source fingerprints and stored inputs make those differences visible.

To redraw the measured demo image:

```bash
python -m pip install -e '.[demo]'
python -m examples.render_demo
```
