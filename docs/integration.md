# Integration and lifecycle

## Trusted host middleware

Create `EvidenceService` once for an authenticated tenant/session resolved by your
host. Capture tool output directly through `service.capture()` before passing it
to a model. At a context boundary, `service.pack(task, artifact_ids, budget=...)`
selects across the available sources. Put `pack.to_json()` in a tool-result
message; preserve the provider's existing tool-call/result pairing.

A receipt records the exact pack constructed and returned to the host. It does
not attest network delivery, model attention or later edits to the message.
The trusted host must send that exact projection and bind the receipt to the
answer being checked. Digests detect content changes under a trusted vault;
they are not signatures against an attacker who controls the database.

See [the middleware example](../examples/tool_middleware.py). Its callable runs
your existing tool: EvidencePack introduces no command executor or action policy.

The counter measures the entire pack JSON. It does not include the system prompt,
question, chat template or tool protocol envelope. Reserve those separately.
`ByteCounter` counts bytes. `TiktokenCounter` counts a chosen encoding.
`HuggingFaceCounter` uses a local tokenizer snapshot. Do not use an unrelated
encoding and call its result the model's native token count.

## Receiving a model answer

Have the model return citations and exact quotes. Validate each pair with
`service.verify(receipt, citation, quote)`. Its positive result establishes only
that the quoted bytes occur in an unaltered excerpt exposed in that receipt.
Check claim interpretation and action authorization separately. The model
benchmark additionally checks the repair values and relevant quoted fields.

If more detail is needed, `service.read(artifact, 'L100-L110', budget=...)` or
`service.read(artifact, 'J:/records/3', budget=...)` creates a new bounded receipt.
An oversized reread raises `BudgetTooSmall`; request a smaller complete range or
a deeper JSON pointer. `service.raw()` is an unbudgeted host export, not a model
projection.

Release each receipt when your host finishes using it. Active receipts pin
selected artifacts, including their original payload. Released receipts remain
verifiable until those artifacts are deleted. `collect(before=...)` deletes only
old, unpinned artifacts. Forced deletion clears payloads and invalidates all
dependent receipts with `artifact_deleted`.

Deletion is a logical payload deletion. SQLite pages, WAL, backups and previously
exported packs can retain bytes; this API is not a secure-erase primitive. Choose
host storage and backup policies appropriate to your data.

## Optional MCP adapter

Install `pip install '.[mcp]'` and run:

```bash
evidencepack --vault .evidencepack/vault.sqlite --tenant local --session incident-1 serve
```

Generic stdio host configuration:

```json
{
  "mcpServers": {
    "evidencepack": {
      "command": "evidencepack",
      "args": ["--vault", "/private/host/vault.sqlite", "--tenant", "local",
               "--session", "incident-1", "serve", "--max-budget", "8192"]
    }
  }
}
```

The adapter exposes capture, pack, read, verify and release. No tool accepts
tenant, session, vault path or a forced-deletion argument. The host binds these
when starting the process. MCP capture is useful for pasted textual evidence;
large tool outputs should be archived by host middleware to avoid sending their
full contents through the model just to capture them.

Scope labels are application checks. They do not authenticate callers or prevent
a process with direct vault access from editing SQLite. Keep the vault outside
the agent's writable workspace. One stdio server per bound session is the
supported first-release deployment. There is no multi-user HTTP service here.
