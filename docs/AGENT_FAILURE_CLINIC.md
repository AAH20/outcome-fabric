# Agent Failure Clinic: apparent completion versus human acceptance

This first clinic is a small, deterministic synthetic case for a common
outcome-claim failure: an agent reports `COMPLETED` and leaves an artifact, but
the human acceptance rule still fails because required evidence is missing.

## Reproduce locally

```bash
cd outcome-fabric
PYTHONPATH=src python3 -m outcome_fabric.failure_clinic_cli run \
  fixtures/failure-clinic/apparent-completion.json \
  --output /tmp/agent-failure-clinic.json
PYTHONPATH=src python3 -m outcome_fabric.failure_clinic_cli verify \
  fixtures/failure-clinic/apparent-completion.json \
  /tmp/agent-failure-clinic.json
```

The output intentionally shows two different answers:

| Check | Result |
| --- | --- |
| Completion-only verifier | `PASS` |
| Independent acceptance verifier | `FAIL` |
| Failure codes | `HUMAN_ACCEPTANCE_NOT_ESTABLISHED`, `REQUIRED_EVIDENCE_GAP` |
| Post-rework status | `ACCEPTED_AFTER_REWORK` |
| Synthetic total after rework | `$21.35` |

The hidden failure is not that the artifact is absent. The artifact exists and
the agent's completion flag is true. The failure is that the requested outcome
includes human acceptance and an evidence map, neither of which follows from an
artifact-exists signal. The verifier also makes the rework cost visible instead
of allowing the initial completion signal to erase it.

## Claim and expected result

The explicit claim is: “The agent completed the policy memo because it returned
`COMPLETED` and produced an artifact.” The case expects a naive completion check
to pass and an independent acceptance check to fail. After the declared repair,
the follow-up decision is synthetic `ACCEPT`, so the report labels the path
`ACCEPTED_AFTER_REWORK`.

## Limits

Everything in this case is invented: task state, evidence fields, reviewer
decision, time, and costs. A passing local verification proves only that the
fixture and report agree. It does not authenticate a reviewer, inspect a real
agent or customer system, demonstrate a production failure rate, establish
causality, provide certification, or prove commercial savings.
