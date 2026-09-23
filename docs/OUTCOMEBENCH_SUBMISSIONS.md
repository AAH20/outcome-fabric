# OutcomeBench synthetic submission contract

OutcomeBench has two public demonstration modes: built-in deterministic adapters and framework-neutral prediction replay. Both use the same versioned support protocol, Evidence Bridge, Passport, and offline scorecard verifier. The public index accepts **synthetic cases only**. There is no customer-data submission or independent-review program in this release.

## Replay predictions from any framework

An agent framework can run the published synthetic scenario in its own environment and export a JSON file. The benchmark never executes the framework's code during replay. Each arm needs exactly one result per case:

```json
{
  "schema_version": "0.1.0",
  "scenario_sha256": "SHA-256 of the exact scenario file bytes",
  "arms": {
    "baseline": [{"case_id": "S001", "resolution_code": "invoice_copy"}],
    "candidate": [{"case_id": "S001", "resolution_code": "invoice_copy"}]
  }
}
```

The arrays above illustrate the shape; a real file must cover **every** scenario case in each arm. The runnable example is [`support-rules-40-predictions.json`](../fixtures/simulation/support-rules-40-predictions.json).

```bash
PYTHONPATH=src python3 -m outcome_fabric.predictions_cli \
  fixtures/simulation/support-rules-40.json \
  protocols/support-accepted-resolution-v1.json \
  fixtures/simulation/support-rules-40-predictions.json \
  generated/my-replay
PYTHONPATH=src python3 -m outcome_fabric.outcomebench_cli verify \
  generated/my-replay/manifest.json \
  protocols/support-accepted-resolution-v1.json \
  generated/my-replay/scorecard.json
```

Choose an output directory that does not exist; replay refuses to overwrite a prior run. The scenario digest prevents accidentally scoring predictions against a changed case set. It does **not** prove that an agent generated the predictions, that labels were hidden, or that the submitting party did not tune against the public answers.

## Public registry

`registry/submissions/` contains reviewed JSON entries with `id`, `label`, `track`, `scenario`, `protocol`, and optionally `predictions`. The only accepted track is `SYNTHETIC`. A submission without `predictions` runs the repository's built-in adapters; one with `predictions` replays the bound results. The builder requires repository-local JSON paths, re-executes the benchmark, and writes [RESULTS.md](../registry/RESULTS.md) and [results.json](../registry/results.json). CI regenerates both and fails if committed results differ.

The index has no universal rank. It shows protocol version, execution mode, eligible and accepted counts, cost per accepted resolution, and comparison status. All costs are invented assumptions. The fixture repeats prompt templates, so case independence is not established and statistical intervals are withheld. Neither a minimum-sample pass nor a lower modeled cost supports a production or causal claim.

Do not commit real customer tickets, personal data, private prompts, invoices, credentials, or privileged material. A future customer-result process requires permission, source reconciliation, independent review with disclosed scope, and separate publication approval.
