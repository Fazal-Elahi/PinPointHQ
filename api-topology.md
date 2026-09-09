# Pinpoint API — Topological Map

> Derived from all 157 pages of `developers.pinpointhq.com/llms.txt` (OpenAPI parsed
> from 111 reference pages: 572 schemas, 111 path-operations).
> Base URL: `https://{subdomain}.pinpointhq.com/api/v1` · Auth: `X-API-KEY` header
> Spec: JSON:API (append `.json` for plain JSON) · 3rd parties must also send `x-vendor-name`

---

## 1. The three "person" surfaces

Pinpoint does not have one person object. It has three, and knowing which one you're
holding is the single most important thing in any integration.

| Surface | CRUD | Means | PII held |
|---|---|---|---|
| `candidates` | **GET, PUT only** | The identity spine. One human. | name, email, phone, DOB, address, `national_identifier`, documents |
| `applications` | GET, POST, PUT, DELETE | Person × Job. The event. | denormalised copy of the above + CV/cover letter |
| `job_seekers` | GET, POST, PUT, DELETE | Person × Talent Pipeline. No job. | name, email, phone, DOB, address, CV |

```
                    ┌──────────────┐
                    │  candidates  │  ← identity spine (GET/PUT only)
                    └──────┬───────┘
           ┌───────────────┼───────────────┬──────────────┐
           │               │               │              │
    ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼─────┐ ┌──────▼──────────┐
    │applications │ │ job_seekers │ │   skills   │ │ hris_references │
    └──────┬──────┘ └─────────────┘ └────────────┘ └─────────────────┘
           │
           ├─► stage ─► hiring_workflow
           ├─► job ─► job_postings / department / division / location
           ├─► answers ─► questions
           ├─► offers, comments, custom_attributes, document_requests
           ├─► candidate_assessments · background_checks · reference_checks
           ├─► one_way_video_interviews · onboarding_application ─► onboarding_answers
           └─► user_scorecards ─► scorecard_ratings / answers / notes
```

**Critical:** there is **no `POST /candidates` and no `DELETE /candidates`.** A candidate
comes into existence as a *side effect* of `POST /applications` or `POST /job_seekers`
(both accept `first_name`, `email`, `phone`… directly as attributes). Deduplication is
therefore an application-level concern, never a candidate-level one.

---

## 2. Full entity graph

**Identity**
- `candidates` → applications*, job_seekers*, skills*, custom_attributes*, hris_references*
- `job_seekers` → candidate, answers*, comments*, custom_attributes*, structured_section_responses*, user_scorecards*
- `applications` → candidate, job, job_posting, stage, furthest_stage, answers*, comments*,
  custom_attributes*, document_requests*, offers*, onboarding_application, hris_reference,
  scorecard_answers/notes/ratings*, user_scorecards*, structured_section_responses*

**Org structure**
- `jobs` → company, department, division, location, structure_custom_group_one, structure_link,
  creator_user, hiring_manager_user, recruitment_manager_user, stages*, questions*,
  job_postings*, applications*, custom_attributes*
- `structure_links` → department + division + location + structure_custom_group_one
  *(the join record — the valid combination, not a free cross-product)*
- `requisitions` → requisition_template → requisition_template_fields → requisition_details
- `positions` → parent_position, child_positions*, position_openings* → (job, requisition, position_holder)

**Workflow**
- `hiring_workflows` → stages*; `stages` → applications*, stageable *(read-only via API)*
- `scorecards` → scorecard_sections* → scorecard_options*; → user_scorecards* → ratings/answers/notes
- `interviews` → interview_parts* → interviewing_users*; `interviewable` is polymorphic
  (application **or** job_seeker)

**Extension (the escape hatch)**
- `custom_fields` *(definition; has `resource_type`, `field_type`, `unique_reference`)*
  → `custom_field_options`
- `custom_attributes` *(value; polymorphic via `custom_attributable_id` + `custom_attributable_type`)*
  Attaches to: **applications, candidates, jobs, job_seekers, job_templates, offers, positions**

**Vendor / downstream** — all hang off `application`:
`candidate_assessments`, `background_checks`, `reference_checks`, `one_way_video_interviews`,
`onboarding_applications` → `onboarding_answers`, `hris_exports`

---

## 3. Query surface (what you can actually ask for)

`page[size]` default **100**, max **1000**. Offset pagination only — **no cursor.**
`stats[total]=count` returns the match count in `meta`.
`sort` is limited to **`id`, `created_at`, `updated_at`** (± prefix) on *every* resource.

| Resource | Notable filters |
|---|---|
| `candidates` | `phone`, `blocked`, `external_system_reference`, `created_at`/`updated_at` [gt/lt] — **no email filter** |
| `applications` | `uuid`, `candidate_id`, `candidate_email`, `candidate_phone`, `job_id`, `job_posting_id`, `stage_id`, `stage_basic_type`, `internal_candidate`, `concealed`, `job_visibility`, `locale`, `external_system_reference` |
| `jobs` | `status`, `visibility`, `employment_type`, `workplace_type`, `remote`, `department_id`/`_name`, `division_id`/`_name`, `location_id`/`_name`, `structure_custom_group_one_id`/`_name`, `hiring_manager_user_id`, `recruitment_manager_user_id`, `requisition_id`, `non_rejected_applications`, `search` |
| `job_seekers` | `candidate_id`, `search`, `external_system_reference`, timestamps |
| `interviews` | `start_at`[gt/lt], `interviewable_id`, `interviewable_type`, `presence`, `job_visibility` |
| `custom_attributes` | `custom_attributable_id`, `custom_attributable_type` |
| `users` | `email`, `employee`, `hiring_manager_job_id`, `recruitment_manager_job_id`, `interviewing_user_id` |
| `job_postings` | `job_id`, `status`, `default_for_job`, `location_city_state_name`, `department_id`… |

### `extra_fields` — not returned unless asked for
| Resource | Available |
|---|---|
| `applications` | `attachments`, `average_rating`, `tags`, **`days_in_current_stage`** |
| `candidates` | `attachments`, `tags` |
| `job_seekers` | `attachments`, `average_rating`, `tags` |
| `jobs` | `hiring_user_id`, `recruitment_manager_user_id`, `assigned_onboarding_process_id`/`_name`, `assigned_onboarding_candidate_owner_user_id`/`_email`, `users_emails_with_job_level_visibility` |

---

## 4. Tags

Tags are `{name, context}` pairs, **not** flat strings.

- Read: `extra_fields[applications]=tags` → `[{"context":"custom_green","name":"Celery"}, {"context":"rejection","name":"Availability"}]`
- Write: `add_tag_with_context` (object), `add_tags_with_context` (array), `remove_tag_with_context` (object) — all **write-only** attributes on `applications`, `candidates`, `job_seekers`.
- There is no tag-list endpoint and no filter-by-tag. Tag inventory must be reconstructed by scanning.

---

## 5. Sharp edges (the things that generate tickets)

1. **No batch/bulk endpoint anywhere.** Every mass update is N sequential PUTs.
2. **Rate limit is undocumented.** `429 Too Many Requests` is in the spec with no published
   ceiling — so any bulk tool must be *adaptive* (backoff on 429), never *configured*.
3. **`sort` can't touch business fields.** No "oldest in stage first", no "lowest rated first".
   Every ranking is client-side, which means you must pull the full set before you can prioritise.
4. **`extra_fields` are silently absent.** `days_in_current_stage` / `average_rating` / `tags`
   come back missing, not erroring, if you forget the param. Classic "the API is wrong" ticket.
5. **Email asymmetry.** `/candidates` has no `filter[email]`; `/applications` has
   `filter[candidate_email]`. The only email→identity path runs through applications.
6. **Offset pagination over mutating data.** Deep scans skip/duplicate rows if records change
   mid-scan. Mitigate with `filter[updated_at]` windows + `sort=id`.
7. **US vs non-US address split.** `address2` returns null and is unwritable when `country`
   is `US`; `state_province` is the mirror image. A migration landmine.
8. **`concealed` (application) + `blind_screening` (job)** — Pinpoint *already* has a native
   anonymisation concept. Reusable precedent for any privacy boundary you build.
9. **Webhooks: 5s timeout, 10 retries over 24h, then auto-disabled + email.**
   Receivers must ack immediately and process async.
10. **Stage Actions failures** land in an "Incomplete Actions" dashboard requiring manual
    intervention — named, documented, recurring friction.
11. **`external_system_reference`** exists on nearly every resource **and is filterable.**
    This is the idempotency key for every import and re-run.
12. `ai_score` already exists on applications (AI Match Score, when enabled).

---

## 6. Webhook events

Applicant hired · Application moved · Application stage changed · Background check completed ·
Document request accepted · Interview scheduled · Job created · Job deleted · Job updated ·
New application · Offer accepted · Onboarding completed · Onboarding stage completed (v2) ·
Onboarding workflow completed · Requisition approved · Requisition created ·
Talent Pipeline candidate created · User created on company

---

## 7. Integration Plugin Framework (public beta)

Three action types, three provider shapes:
- `exportCandidate` → HRIS (BambooHR, Workday, Personio)
- `createAssessment` → assessment platforms (Codility, SHL, Criteria)
- `createBackgroundCheck` → background check providers (Checkr, Sterling, Certn)

Plugin implements a **meta endpoint** + action endpoints + (for Stage Actions) **list endpoints**
for every dropdown. Customer maps Pinpoint fields via `{{candidate_first_name}}`-style
mapping variables. Registration is manual, via `integrations@pinpointhq.com`.
Schema validator: https://musical-strudel-69b50d.netlify.app/

---

## 8. PII surface (what must never reach a model)

**Direct identifiers** — `first_name`, `last_name`, `middle_name`, `preferred_name`, `full_name`,
`email`, `phone`, `date_of_birth`, `national_identifier`, `linkedin_url`, `address1`, `address2`,
`town`, `state_province`, `postcode`, `summary`, `preferred_pronouns`
**Documents** — `cv_base64_data`, `cover_letter_base64_data`, `documents_base64`, `attachments`
**Special category** — `equality_monitoring_categories` / `_options` (protected characteristics),
`candidate_surveys`, `background_checks.result_details`, `reference_checks.referee_name`/`_email`
**Free text (unbounded risk)** — `comments.body_text`, `answers.text_answer`,
`scorecard_notes`, `interviews.summary`, `onboarding_answers.*`

**Safe to reason over** — ids, uuids, `stage_id`, `job_id`, `created_at`/`updated_at`,
`days_in_current_stage`, `average_rating`, `country_code`, `status`, `channel`,
`employment_type`, tag *contexts*, counts, error codes.
