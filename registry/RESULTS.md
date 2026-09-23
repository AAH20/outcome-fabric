# OutcomeBench synthetic results

Every result below is a reproducible **synthetic reference** with invented cases and costs. The table is not a vendor ranking, customer outcome, causal effect, or production recommendation.

| Run | Mode | Protocol | Baseline accepted | Candidate accepted | Baseline cost / accepted | Candidate cost / accepted | Status |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Support prediction replay | PREDICTION_REPLAY | outcomebench-support 0.1.0 | 20/40 | 36/40 | 40.0000 | 13.8889 | DESCRIPTIVE_COMPARISON_ONLY |
| Support rules reference | BUILTIN_ADAPTERS | outcomebench-support 0.1.0 | 20/40 | 40/40 | 40.0000 | 12.5000 | DESCRIPTIVE_COMPARISON_ONLY |

Results are regenerated from the registered scenario and protocol in CI. The underlying fixture is deliberately simple and can be gamed; it demonstrates the harness, not real-world generalization.
