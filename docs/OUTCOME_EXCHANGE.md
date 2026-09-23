# Outcome Exchange reference kernel

Outcome Exchange is a deliberately narrow, local reference slice for a future
job and agent-work marketplace. It combines four inspectable boundaries:

1. **Typed decision:** a Laya/Jev-compatible `choice` record selects a worker
   route and preserves probabilities. The fixture does not load a model.
2. **Swarm replay:** declared planner, reviewer, and verifier task records are
   replayed and checked against the job's acceptance contract.
3. **Evaluation and evolution:** first-pass acceptance, evidence completeness,
   rework rate, cost per accepted outcome, and a candidate promotion gate are
   emitted. A candidate is blocked when the acceptance evidence is missing.
4. **Unit economics:** worker payout, model, compute, review, payment,
   support, and rework-reserve costs are reconciled against customer price.

Run the synthetic case:

```bash
cd outcome-fabric
PYTHONPATH=src python3 -m outcome_fabric.outcome_exchange_cli run \
  fixtures/laya-outcome-exchange/synthetic-job.json \
  --output /tmp/laya-outcome-exchange.json
PYTHONPATH=src python3 -m outcome_fabric.outcome_exchange_cli verify \
  fixtures/laya-outcome-exchange/synthetic-job.json \
  /tmp/laya-outcome-exchange.json
```

The fixture intentionally returns `UNRESOLVED` and `BLOCKED`: all declared
swarm tasks complete, but accountable human acceptance is not recorded. Its
synthetic economics are `$75.00` price, `$61.50` modeled cost, and `$13.50`
contribution margin (18.0000%). These are invented inputs, not a market result,
customer evidence, hiring performance, payment settlement, or production
benchmark.

## What this is not

- It is not a live Laya integration or a Jev implementation.
- It does not spawn agents, call tools, hire people, authenticate reviewers,
  process payments, or move customer data.
- It does not claim superiority over RentAHuman, micro1, Ruflo, LangChain, or
  any other platform.

## Intended commercial boundary

The future OSS surface can contain contracts, local runners, replay, adapters,
and synthetic evaluation fixtures. A hosted product may later add tenant
isolation, private evaluation packs, enterprise connectors, settlement,
support, and confidential benchmark data. No private benchmark, customer
record, negotiated rate, or credential belongs in this repository.
