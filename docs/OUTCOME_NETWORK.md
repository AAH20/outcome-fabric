# Outcome Network: first permissioned-pilot boundary

Outcome Network is the proposed production service around the open Outcome Fabric protocol. Its first buyer workflow is **accepted AI-assisted support resolution per full attributable dollar**. The repo now includes a bounded, read-only Zendesk OAuth collector, an offline intake and an assembly path into the existing Evidence Bridge. The collector has been tested with mocked responses, **not a live customer account**. The code does not authenticate customer permission, reviewers, cost records, source completeness, or a public verified claim. The committed data is synthetic.

## Read-only live-source pilot path

The collector uses the documented cursor-based incremental ticket endpoint, sends an OAuth bearer token only to the exact `https://<subdomain>.zendesk.com/api/v2/incremental/tickets/cursor.json` endpoint, rejects redirects and cross-origin cursor URLs, and limits pages and response size. It retains only ticket ID, status, and update time in private files. Raw API response digests are recorded but raw ticket content is discarded. Put the OAuth token in `ZENDESK_OAUTH_TOKEN` in the local process environment; never put it in an argument, config file, repository, or issue.

```bash
PYTHONPATH=src python3 -m outcome_fabric.zendesk_fetch_cli --subdomain YOUR_SUBDOMAIN --start-time UNIX_START_TIME --output-dir /private/path/collection
PYTHONPATH=src python3 -m outcome_fabric.zendesk_pilot_cli /private/path/collection /private/path/pilot-sidecars.json /private/path/pilot-package
PYTHONPATH=src python3 -m outcome_fabric.zendesk_intake_cli verify /private/path/pilot-package/intake.json /private/path/pilot-package/derived
```

`pilot-sidecars.json` has the same structure as [`fixtures/zendesk-intake/pilot-sidecars.json`](../fixtures/zendesk-intake/pilot-sidecars.json): tenant and Passport IDs, subject, protocol, and digest-locked `cohort.csv`, `decisions.csv`, and `costs.csv`. The sidecar files must be in the same private directory as that JSON. The cohort is explicitly selected by an operator; `solved` and `closed` ticket status only establish eligibility. The separate decision file is still operator supplied and unauthenticated. Assembly checks the collection receipt and digests, copies minimal snapshots into a private package, and runs the Bridge end to end. The command refuses to overwrite output.

The OAuth token proves only that a request was accepted by the configured Zendesk account. It does not prove that the organization authorized this measurement, that the chosen interval is complete for the intended question, or that the reviewers' decisions are genuine. Those require separate customer governance and an authenticated review service.

## What this release actually adds

`outcome-zendesk-intake` accepts locked local JSON pages, a manually defined eligible cohort, separate acceptance decisions, and all seven cost categories. It rejects tampered files, incomplete page sequences, unresolved cohort tickets, duplicate cohort IDs, missing decisions, and incomplete costs. A newer ticket snapshot supersedes an older one. The output is a private Bridge package with only minimal case rows; ticket subject and other source fields are not copied into the derived cases CSV. The output directory is created privately and only after the Bridge validates the complete package. `verify` re-reads every locked input and recomputes each output byte.

Zendesk's [incremental ticket export documentation](https://developer.zendesk.com/api-reference/ticketing/ticket-management/incremental_exports/) describes cursor-based pages and `end_of_stream`. This adapter consumes a saved sequence of those page shapes; it does not infer that the operator exported every relevant page. A ticket marked `solved` or `closed` is merely eligible for the declared cohort. It is **not** automatically accepted by a customer or reviewer.

```bash
PYTHONPATH=src python3 -m outcome_fabric.zendesk_intake_cli run fixtures/zendesk-intake/intake.json /tmp/outcome-network-pilot-demo
PYTHONPATH=src python3 -m outcome_fabric.zendesk_intake_cli verify fixtures/zendesk-intake/intake.json /tmp/outcome-network-pilot-demo
PYTHONPATH=src python3 -m outcome_fabric.bridge_cli build /tmp/outcome-network-pilot-demo/manifest.json --output /tmp/outcome-network-bridge-demo.json
PYTHONPATH=src python3 -m outcome_fabric.bridge_cli verify /tmp/outcome-network-pilot-demo/manifest.json /tmp/outcome-network-bridge-demo.json
```

Choose a fresh private output directory. The command refuses to overwrite a directory. Keep customer source pages, cohort, decisions, costs, derived files, and report outside the public repository. Local file permissions are restrictive, but this is not a hosted custody system.

## Current architecture and precise claim boundary

```mermaid
flowchart LR
  API["Zendesk cursor API - read only"] --> F["Bounded OAuth collector"]
  F --> Z["Private minimal pages and raw response digests"]
  Z --> L["SHA-256 lock and page checks"]
  H["Operator-defined cohort"] --> L
  D["Separate declared acceptance decisions"] --> L
  C["Seven declared cost categories"] --> L
  L --> A["Pilot assembly"]
  A --> I["Offline Zendesk intake"]
  I --> B["Existing Evidence Bridge"]
  B --> P["Local Outcome Passport"]
  P --> V["Offline recomputation"]
  V --> S["Customer-supplied, unverified evidence class"]
```

The same human who supplied an export may also have authored the decision CSV. SHA-256 establishes local file identity relative to the configuration, not source authenticity. The generated Passport remains `CUSTOMER_SUPPLIED_UNVERIFIED`, and its cost difference is descriptive, not causal.

## Production service target

```mermaid
flowchart TB
  subgraph Customer["Customer-controlled systems"]
    T["Ticket source"]
    A["Agent and human attempt logs"]
    K["Cost ledger"]
    R["Named reviewers"]
  end
  subgraph Boundary["Permissioned tenant boundary - proposed"]
    O["Read-only OAuth connector"]
    I["Tenant identity and roles"]
    Q["Source completeness and exception queue"]
    E["Private encrypted evidence"]
    W["Authenticated two-review workflow"]
  end
  subgraph Open["Open measurement kernel - partly implemented"]
    P["Versioned protocol"]
    B["Bridge and benchmarks"]
    V["Passport and offline verifier"]
  end
  T --> O --> Q --> E --> B
  A --> Q
  K --> Q
  R --> I --> W
  E --> W
  P --> W
  W --> B --> V
  V --> U["Private customer decision"]
  U -->|separate authorization| X["Approved external report"]
```

The proposed hosted boundary is **not built**. The current collector is a local command, not managed OAuth lifecycle or a tenant service. In particular, a localhost alias in Acceptance Ledger is not reviewer authentication. A real deployment needs SSO/OIDC, tenant isolation, role enforcement, source-scoped credentials, credential rotation, encrypted custody, retention and deletion rules, backup recovery, abuse monitoring, independent review, and customer-controlled publication approval. None of those can be inferred from this pilot path.

## Pilot gates

1. **Data rights and protocol:** a customer approves the exact export fields, retention, eligible cohort, acceptance rule, measurement window, and cost allocation. Keep the authorization record outside the open-source report until a permission workflow is implemented.
2. **Reconciliation:** compare exported counts and page cursor boundaries with the customer's source system; investigate gaps and late updates. This release only checks the pages it receives.
3. **Independent review:** two named reviewers inspect the exact work version. A conflict needs a third reviewer. The existing local ledger demonstrates mechanics but cannot authenticate people.
4. **Unit economics:** report all attempted cases in cost, accepted cases in the denominator, human review and rework, data coverage, and case mix. Withhold causal savings claims without a credible experimental design.
5. **Repeatability:** onboard a second customer using the same protocol and adapter contract without bespoke calculation logic. Only then consider managed cross-customer comparison or procurement workflows.

Commercial value comes from operating these controls and integrations reliably. The protocol, local adapter, calculator and verifier should remain inspectable OSS. Customer records and derived results remain customer-controlled; a public case study requires a separate approval and scope review.
