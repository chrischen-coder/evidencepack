# Related work and bounded differentiation

Reviewed on 2026-10-04. These are source snapshots, not performance comparisons.
Absence from these reviewed paths is not proof of absence anywhere in a project.

| Project | Reviewed source | Existing capability |
| --- | --- | --- |
| OpenClaw | [`9c66d4c`, pruning](https://github.com/openclaw/openclaw/blob/9c66d4c9a39b16d70e7c55186fe7e8550468a663/docs/concepts/session-pruning.md), [truncation](https://github.com/openclaw/openclaw/blob/9c66d4c9a39b16d70e7c55186fe7e8550468a663/packages/agent-core/src/harness/utils/truncate.ts) | Preserved full history, projected tool-result trimming, head/tail and complete-line limits; provider-aware compaction |
| Hermes Agent | [`40b6238`, micro compaction](https://github.com/NousResearch/hermes-agent/blob/40b623849a7b0610a2221c00caf5e3bae6f75a45/agent/micro_compaction.py), [context engine](https://github.com/NousResearch/hermes-agent/blob/40b623849a7b0610a2221c00caf5e3bae6f75a45/agent/context_engine.py) | Extensible context engine, persistent compaction state, transactional generation checks and history transformations |
| OpenHands SDK | [`b347047`, truncation](https://github.com/OpenHands/software-agent-sdk/blob/b347047e2dcdd8f4b2be810aa8bc6632bc756d41/openhands-sdk/openhands/sdk/utils/truncate.py), [condenser](https://github.com/OpenHands/software-agent-sdk/blob/b347047e2dcdd8f4b2be810aa8bc6632bc756d41/openhands-sdk/openhands/sdk/context/condenser/README.md) | Hash-named saved outputs, head/tail clipping, append-only event history and summary-based views |

These systems already externalize, prune, summarize and recover context. Those
ideas are not claimed as innovations of EvidencePack. Their full agents also
have search/read tools; the truncation baselines here are policies, not complete
agent evaluations.

[ClawVM](https://github.com/mpi-dsg/clawvm), described in
[arXiv:2604.10352](https://arxiv.org/abs/2604.10352), explicitly treats agent state
as virtual memory with typed pages, minimum-fidelity invariants and validated
writeback. That is relevant prior art for recoverable context and fidelity
contracts. EvidencePack does not claim to invent virtual memory for agents.

The engineering contribution of this release is the small, framework-independent
contract joining **complete evidence selection, whole-pack budget accounting,
immutable invocation provenance, exposure-bound exact-quote verification and
reference-aware retention**. The reviewed paths do not expose that combination
through this receipt API. This is a design comparison; the repository's tests and
benchmarks establish its own behavior, not a universal research novelty claim.

The difficult part is keeping these contracts compatible: metadata consumes the
budget, every selected unit must be recoverable and scoped, and garbage
collection must not quietly invalidate evidence behind an accepted receipt.
The implementation makes those invariants executable and tests failure paths.
