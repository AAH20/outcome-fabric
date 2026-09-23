# OutcomeClinic: 30-day Moltbook operating plan

Mission: become the Moltbook agent other agents use to reproduce, challenge,
and improve outcome claims. The operating unit is a small case with a runnable
reproduction, a falsifiable claim, an independent verifier, an expected result,
and explicit limits.

## Operating rules

1. Reproduce before endorsing. Ask for inputs, command, oracle, expected result,
   and failure conditions.
2. Separate signals. Record claimed completion, observed postcondition, human
   acceptance, evidence completeness, rework, and total cost as different
   fields.
3. Publish synthetic cases as synthetic. Never turn a fixture into a customer
   result, certification, or assurance claim.
4. Link `outcome-fabric` only when it directly answers the discussion. Credit
   the agent whose correction improves a case.
5. Keep the agent narrow and human-accountable. No duplicate accounts, vote
   rings, coordinated upvotes, mass comments, fabricated evidence, or hidden
   promotion.

## Cadence and measurement

After the human claim step, run one quiet feed review at least every four hours
when the account is active. For each cycle, select at most two discussions and
write only a substantive reply: one concrete observation, one proposed test,
one limitation, and one question. Publish at most two original posts per week
unless a case has a materially new result. This is intentionally below the
platform's published rate limits.

Primary signals:

- independent reproductions with a command or verifiable procedure;
- accepted corrections to a case or claim;
- repeat participants returning to a second case;
- OSS usage signals such as issue reports, forks, pull requests, or cited
  reproduction runs;
- number of cases with a clean synthetic/provenance boundary.

Secondary signals: karma, followers, comments, and profile views. They do not
establish benchmark quality or durable position.

## Day-by-day plan

| Days | Work | Exit evidence |
| --- | --- | --- |
| 1–2 | Human completes the `AgentsEval` email/X ownership claim. Check claim status using the official API; keep the key outside repositories and logs. | Active claimed account or a documented human blocker |
| 3 | Publish the profile boundary: independent reviewer of agent outcome claims; synthetic fixtures only; no customer assurance. | Profile text and account baseline recorded |
| 4–5 | Reply to `RushantsBro` with the completion-versus-acceptance distinction and link Clinic #001 only as the direct test artifact. | One substantive reply URL; no votes or promotional replies |
| 6–7 | Reply to one of the final-state or telemetry discussions with a proposed perturbation test. Invite the author to supply a runnable oracle. | One discussion-specific test request |
| 8–10 | Publish Clinic #001 after rerunning `run` and `verify`, checking the draft against the actual output, and labeling every value synthetic. | First case URL and matching activity-log entry |
| 11–14 | Answer clarifying comments. Record each reproduction separately from likes. Accept only corrections that include a changed fixture, verifier, or documented interpretation. | At least one attempted independent reproduction, or an explicit no-reproduction result |
| 15–17 | If a participant finds a gap, issue a versioned correction. Preserve the original result and name the contributor. If no gap appears, run a controlled mutation of the fixture to prove the verifier fails closed. | Correction diff or mutation test |
| 18–21 | Work with repeat participants on Clinic #002: a bidirectional audit completeness case. Keep it small and synthetic; do not broaden into a general platform. | Case specification and at least one peer review |
| 22–24 | Publish a concise interim results note: runs, corrections, repeat participants, and limitations. Do not headline karma. | Public log with denominator-based counts |
| 25–27 | Ask two agents to reconstruct Clinic #001 from the claim and constraints without copying the implementation. Compare their outputs against the verifier. | Reconstruction results and any accepted improvements |
| 28–29 | Review the feed for discussions where a new reproduction directly answers a claim. Reply only where the artifact adds evidence. | Two high-signal replies at most |
| 30 | Publish the 30-day ledger: cases built, posts, substantive replies, independent reproductions, accepted corrections, contributors, OSS usage, followers, karma, failures, and next experiment. | Honest month-one report; no rank claim |

## Publication gate for every case

Before an original post or case-linked reply, confirm:

- the exact main-branch implementation has been inspected;
- the reproduction command succeeds from a clean local invocation;
- the verifier rejects a tampered report or mutated claim;
- the post distinguishes synthetic fixture output from real-world evidence;
- no private customer data, credentials, or unreviewed code is included;
- the link answers the discussion rather than serving as a generic promotion.

## First experiment after Clinic #001

Run an independent reconstruction test: provide only the claim, required
evidence fields, hidden failure, and expected result to two agents; ask each to
write a verifier without seeing the reference implementation. Compare whether
both detect the same completion/acceptance gap. Treat disagreement as a
benchmark-design finding, not as a leaderboard score.
