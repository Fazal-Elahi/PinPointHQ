# Reconstructed Pinpoint OpenAPI

Machine-readable contract, extracted from the OpenAPI fragments embedded in the public Pinpoint
documentation and merged into single documents. Built so the mock and the client can be generated
from and validated against the *same* source, rather than against each other's assumptions.

| File | Contents |
|---|---|
| `pinpoint-openapi.json` | Full merge — 64 paths, **111 operations**, 572 schemas, 269 parameters, 35 request bodies, 87 responses, 97 examples, 93 links. Spec version `v1.0.27`. |
| `milestone-1-slice.json` | **The contract the mock implements for Milestone 1** — 12 operations, 186 schemas, every `$ref` resolved inside the document. Verified closed: no dangling references. |
| `provenance.json` | Per-source-page URL, SHA256 as retrieved, spec version, and the operations that page contributed. Re-fetch and re-hash to detect drift. |

## Status and limits

- **Not an official Pinpoint artifact.** Reconstructed from documentation pages on 2026-09-09.
- **Not live-validated.** No authenticated request has been made against any Pinpoint account.
  A documented schema is evidence of the public contract, not proof of production behaviour.
- Some write requirements appear in documentation **prose** rather than in schema `required`
  arrays — notably the status-dependent required attributes for job creation, and the fact that
  required application questions are not validated server-side. These are captured in
  `../implementation.md` §12 and are **not** discoverable from these JSON files alone.

## Milestone 1 slice — the 12 operations

| Purpose | Operation |
|---|---|
| Target discovery | `GET /api/v1/jobs`, `GET /api/v1/hiring_workflows`, `GET /api/v1/custom_fields` |
| Identity index | `GET /api/v1/candidates`, `GET /api/v1/applications`, `GET /api/v1/job_seekers` |
| Writes | `POST /api/v1/applications`, `POST /api/v1/job_seekers` |
| Contract-negative | `POST /api/v1/custom_attributes` — **never issued in normal operation.** Its attributes schema is `additionalProperties: false` with no `external_system_reference`, so a standalone attribute write has no idempotency key. Custom attributes are created *nested* in the parent via `included` + `temp-id` (see `../implementation.md` §6.7). It stays in the slice so the mock can implement the rejection path that proves this. |
| Reconciliation | `GET /api/v1/applications/{id}`, `GET /api/v1/job_seekers/{id}`, `GET /api/v1/custom_attributes` |

Job creation, structure links, custom-field provisioning and every other resource are deliberately
outside this slice. Do not mock them for Milestone 1.

## Two contract facts that are not visible in these files

Both were found by generating payloads and validating them, and both changed the design:

1. **`custom_attributes_attributes_post` has no `external_system_reference`** and is
   `additionalProperties: false`. Standalone custom-attribute writes are therefore not idempotent.
   The nested `included` + `temp-id` path is the supported alternative — the relationship entry
   requires all four of `type`, `id`, `temp-id`, `method`.
2. **Both create endpoints accept an explicit `candidate` relationship.** This is what makes a
   second application for an already-created person safe, and it is what the within-run person
   index in `../implementation.md` §6.5b depends on.

## Regenerating

Both documents are derived artifacts. To rebuild, re-fetch every `.md` URL listed in
`provenance.json`, extract the fenced block following the `# OpenAPI definition` heading in each,
and merge — first definition wins on key collision. Compare the new SHA256s against
`provenance.json` to see what changed upstream.
