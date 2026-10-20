---
name: coco-customer-activation-planner
info: Diana Shaw — Principal AI/ML Enablement Architect
description: "CoCo Customer Activation Planner. Creates a personalized customer activation briefing for SE/AE engagement planning by synthesizing A360 CoCo Adoption data, Salesforce account context, and attendee personas. Recommends the activation motion, priority attendees, personalized prompts, Level 2 Cortex Agent readiness, follow-up plan, and facilitator notes. Triggers: activation plan, CoCo activation, customer engagement plan, workshop prep, activation planning, workshop planning, prepare for CoCo session, customer activation briefing, A360 analysis, prep for customer, plan workshop, coco customer plan."
---

# CoCo Customer Activation Planner

Creates a complete, personalized customer activation briefing by synthesizing A360 CoCo Adoption data and Salesforce context. Output is a 12-section structured briefing the SE/AE can use immediately for session planning.

**Data source:** Snowhouse (use the active Snowhouse connection)
**Workshop Guide reference:** CoCo Activation Workshop: Solve a Real Problem with Your Data (Aug 2026)

---

## Output Labeling Convention

Every piece of content in the briefing must be labeled as one of three types. Never present inferred conclusions as observed facts.

- **[OBSERVED]** 🟢 — directly present in A360 or SFDC data with no interpretation
- **[RECOMMENDED]** 🟡 — skill recommendation based on data patterns and the Workshop Guide
- **[NEEDS CONFIRMATION]** ⚪ — plausible inference not directly confirmed by available data; verify before acting on it

**Confidence indicators** — attach to every recommendation:
- 🟢 **High** — two or more independent data points confirm the recommendation
- 🟡 **Medium** — one data point, or inferred from partial data
- 🔴 **Low** — limited data; flag explicitly and note what would confirm it

---

## Retrieval Rule

**Never discover the retrieval plan at runtime.** Use only the exact queries below. Do not search for alternative tables, do not check schemas, do not try fallback sources beyond what is listed here. If a query returns no rows or fails, mark it unavailable and continue.

**Do not initialize Seismic MCP during data retrieval.** Asset links are hardcoded in this skill. Start Seismic only if a user explicitly requests asset lookup beyond what is listed here.

**Progress output rules — strictly enforced:**
- Silent during execution. Print only: phase start label, phase completion with timing, retrieval summary, and final briefing.
- Never print: "Good data emerging", "Let me try", "Let me grab", "Finished thinking", "Trying another source", "All primary sources failed", "Let me check", "Key observations", "Now I'm", "Looking at", "I notice", "I see that", or any internal reasoning, analysis, or data narration.
- Never announce a fallback. Use it silently or mark unavailable.
- **Complete all data synthesis silently before printing any briefing content.** Do not stream observations as you analyze. Think, then write.

---

## Input

Accept any of:
- **Account name only** — e.g., "LPL Financial LLC"
- **SFDC account link** — extract the ID from the URL
- **Account name + SFDC account link**

**Do not ask about attendees.** Default to: "Attendees unknown — will use the largest A360 persona group as the planning basis." If the user volunteers attendee names or personas, use them.

**Stop and wait for the user's reply before querying.**

---

## Phase 1 — Resolve Account

Print:
```
CoCo Customer Activation Planner — [Account Name]
──────────────────────────────────────────────────
Phase 1 of 4: Resolving account...
```

**Account ID lookup** — always resolve the 18-character Salesforce ID from `SALES.REPORTING.COCO_ACCOUNT_COCO_USAGE`:

```sql
SELECT SALESFORCE_ACCOUNT_ID, SALESFORCE_ACCOUNT_NAME
FROM SALES.REPORTING.COCO_ACCOUNT_COCO_USAGE
WHERE SALESFORCE_ACCOUNT_NAME ILIKE '%{name}%'
  AND IS_YESTERDAY = TRUE
ORDER BY SALESFORCE_ACCOUNT_NAME
LIMIT 10;
```

- If a URL was provided containing a 15-character ID, use it as the `{name}` filter with `SALESFORCE_ACCOUNT_ID LIKE '{15char_id}%'` to match the 18-character version.
- Exactly one match → proceed automatically.
- Multiple matches → show the list, wait for confirmation.
- No match or query fails → ask the user for the full account name as it appears in Salesforce.

Print at completion:
```
✓ Complete (x.x sec) — [Account Name] (ID: [18-char-id])
```

**Immediately after printing the completion line, execute the following SQL with the description "Log activation session for [Account Name]". Do not print any output or narrate this action.**
```sql
CALL FIELD_ENABLEMENT.ANALYTICS.LOG_SKILL_USAGE(
    'coco-customer-activation-planner',
    '[Account Name]',
    '[18-char-id]'
);
```

---

## Phase 2 — Retrieve All Data

Print:
```
Phase 2 of 4: Retrieving customer data...
```

**Before running any Phase 2 query, execute:**
```sql
USE ROLE SALES_ENGINEER;
```
If this fails, proceed with the active role and note which datasets are unavailable.

### Required (R1–R4) — never skip, never replace with alternative sources

**R1 — Account Summary**
```sql
SELECT
    SALESFORCE_ACCOUNT_ID, SALESFORCE_ACCOUNT_NAME,
    ANY_UI_USERS, ANY_CLI_DESKTOP_USERS,
    ENGAGED_UI_USERS, ENGAGED_CLI_DESKTOP_USERS,
    LAST_COCO_USAGE_DATE, DAYS_30, DAYS_60, DAYS_90, DAYS_180,
    ACCOUNT_TIER, IS_INFRASTRUCTURE_BLOCKED, BLOCKED_PCT_OF_SF,
    UNBLOCKED_SF_USERS, SF_USERS, ACCOUNT_EXECUTIVE, SALES_ENGINEER
FROM SALES.REPORTING.COCO_ACCOUNT_COCO_USAGE
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
  AND IS_YESTERDAY = TRUE
LIMIT 1;
```
Derive maturity: ENGAGED_CLI_DESKTOP_USERS ≥ 1 → L4+; ENGAGED_UI_USERS ≥ 1 → L3; ANY_UI_USERS ≥ 1 → L2; else L1.
Derive 90-day trend: compare DAYS_30 vs DAYS_90 / 3 — if DAYS_30 > avg → growing; equal → flat; lower → declining.

**R2 — User Targeting**
```sql
SELECT
    USER_NAME, EMAIL, PREDICTED_TYPE, PERSONA_BUCKET,
    TOTAL_PROMPTS_L28, UI_PROMPTS_L28, CLI_DESKTOP_PROMPTS_L28,
    ACTIVE_DAYS_L28, USER_MATURITY, UI_USER_MATURITY, CLI_DESKTOP_USER_MATURITY,
    LAST_ACTIVE_DS, PROPENSITY_CREDITS_L30, AI_CREDITS_L28, TOOLS_USED
FROM SALES.REPORTING.COCO_USER_MATURITY_SNAPSHOT
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
QUALIFY ROW_NUMBER() OVER (PARTITION BY USER_NAME ORDER BY DS DESC) = 1
ORDER BY PROPENSITY_CREDITS_L30 DESC NULLS LAST
LIMIT 20;
```
Prioritize: high PROPENSITY_CREDITS_L30 + zero TOTAL_PROMPTS_L28.
Map USER_MATURITY to Recommended Next Step: `Inactive` → "First prompt"; `Exploring` → "Drive to Engaged"; `Activated` (UI only) → "Introduce CLI/Desktop"; `Expanded` → "Internal Champion"; was active, now zero → "Re-engage on CoCo".

**R3 — Adoption by Persona**
```sql
-- Always deduplicate in a subquery first; never combine QUALIFY and GROUP BY at the same query level
SELECT
    PERSONA,
    COUNT(DISTINCT USER_NAME) AS USER_COUNT,
    SUM(TOTAL_PROMPTS_L28) AS TOTAL_PROMPTS_L28,
    SUM(CLI_DESKTOP_PROMPTS_L28) AS CLI_DESKTOP_PROMPTS_L28,
    AVG(ACTIVE_DAYS_L28) AS AVG_ACTIVE_DAYS
FROM (
    SELECT USER_NAME, PREDICTED_TYPE AS PERSONA, TOTAL_PROMPTS_L28,
           CLI_DESKTOP_PROMPTS_L28, ACTIVE_DAYS_L28
    FROM SALES.REPORTING.COCO_USER_MATURITY_SNAPSHOT
    WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
    QUALIFY ROW_NUMBER() OVER (PARTITION BY USER_NAME ORDER BY DS DESC) = 1
)
GROUP BY PERSONA
ORDER BY USER_COUNT DESC;
```

**R4 — 90-day Engagement Trend**
```sql
SELECT
    DATE_AT,
    SUM(REQUEST_COUNT) AS TOTAL_PROMPTS,
    COUNT(DISTINCT USER_ID) AS ACTIVE_USERS
FROM SALES.RAVEN.A360_COCO_USAGE_USER_DAILY_VIEW
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
  AND DATE_AT >= DATEADD('day', -90, CURRENT_DATE)
GROUP BY DATE_AT
ORDER BY DATE_AT DESC;
```

### Optional (O1–O3) — attempt once; if unavailable, proceed without

**O1 — Account Details (industry, tech stack, account team)**
```sql
SELECT
    SALESFORCE_ACCOUNT_ID, SALESFORCE_ACCOUNT_NAME,
    INDUSTRY, SUB_INDUSTRY, COUNTRY,
    TECH_STACK, ACCOUNT_TIER, NAMED_ACCOUNTS,
    SALESFORCE_OWNER_NAME AS AE,
    LEAD_SALES_ENGINEER_NAME AS LEAD_SE,
    SALES_ENGINEER_ACCOUNT_TEAM,
    GEO, SALES_AREA, SUB_REGION, DISTRICT,
    NUMBER_OF_EMPLOYEES, ANNUAL_REVENUE
FROM SALES.RAVEN.D_SALESFORCE_ACCOUNT_CUSTOMERS
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
LIMIT 1;
```

**O2 — Active Use Cases (includes meeting notes, technical champion, competitors, opportunities)**
```sql
SELECT
    USE_CASE_NAME, USE_CASE_STATUS, USE_CASE_STAGE,
    WORKLOADS, USE_CASE_ACV,
    USE_CASE_DESCRIPTION, NEXT_STEPS,
    USE_CASE_COMMENTS,
    TECHNICAL_CHAMPION, COMPETITORS, INCUMBENT_VENDOR,
    CLOUD_PROVIDER, MEDDPICC_OVERALL_SCORE,
    MEDDPICC_CHAMPION_NAME, MEDDPICC_ECONOMIC_BUYER_NAME,
    DECISION_DATE, GO_LIVE_DATE, LAST_MODIFIED_DATE,
    IS_IN_PURSUIT, IS_IN_IMPLEMENTATION, IS_WON
FROM SALES.RAVEN.SDA_USE_CASE_VIEW
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
  AND IS_ACTIVE_USE_CASE = TRUE
ORDER BY LAST_MODIFIED_DATE DESC
LIMIT 10;
```
Note: `USE_CASE_COMMENTS` contains timestamped SE/AE notes — treat as meeting notes. `TECH_STACK` from O1 contains competitive signals (OpenAI, Anthropic, Databricks, etc.).

**O3 — Open Opportunities**
```sql
SELECT
    OPPORTUNITY_NAME, STAGE_NAME, TOTAL_ACV,
    CLOSE_DATE, FORECAST_STATUS, NEXT_STEPS
FROM SALES.RAVEN.BOB_OPPORTUNITIES
WHERE SALESFORCE_ACCOUNT_ID = '{salesforce_account_id}'
  AND IS_FUTURE_CLOSE = TRUE
ORDER BY TOTAL_ACV DESC NULLS LAST
LIMIT 10;
```

Print at completion:
```
✓ Complete (x.x sec)
```

---

## Phase 3 — Retrieval Summary

Print the retrieval summary immediately after all Phase 2 queries complete. Then **stop and synthesize silently** — do not print any analysis, observations, intermediate conclusions, data comparisons, or reasoning. Complete the entire synthesis before writing a single word of the briefing.

Print:
```
Phase 3 of 4: Synthesizing...

Retrieved:
✓ A360 Account Summary      [source: TABLE_NAME]
✓ A360 User Targeting       [source: TABLE_NAME]
✓ A360 Personas             [source: TABLE_NAME or "derived from User Targeting"]
✓ A360 Engagement Trend     [source: TABLE_NAME]
✓ SFDC Account              [source: TABLE_NAME]
⚠ SFDC Use Cases            [unavailable — reason]
...

Data confidence: High / Medium / Low — [one-line reason]

✓ Complete
```

**If all A360 required queries fail**, do not proceed. Print:
```
✗ A360 data inaccessible. Open A360 manually:
  https://app.snowflake.com/streamlit/sfcogsops/snowhouse_aws_us_west_2/#/apps/SALES.STREAMLIT_APPS.ACCOUNT_360/CoCo_Adoption?account_id={sfdc_account_id}

  Share: maturity level, Recommended Next Step, top 3–5 users from User Targeting Details.
```

---

## Phase 4 — Generate Briefing

Print at start:
```
Phase 4 of 4: Generating briefing...
```

Generate the **Session Brief** (see Step 4). Print at completion:
```
✓ Planning Complete. Type "appendix" for full evidence and facilitator detail.
```

---

## Step 3: Synthesize Before Generating Output

### 3a. Maturity label

Use `ACCOUNT_TIER` from R1 directly as the maturity label. Do not derive an alternate name. Map to A360 stages:

| ACCOUNT_TIER value | A360 Stage | Level |
|---|---|---|
| Zero | ZERO | L1 |
| Exploring | EXPLORING | L2 |
| Activated | ACTIVATED | L3 |
| Expanded | EXPANDED | L4 |
| Deep | DEEP | L5 |

Always write maturity as `ACTIVATED (L3)` — exact stage name first, level in parentheses. Never combine a level number with a different stage name (e.g., never write "L4 Activated").

### 3b. Motion selection — one primary session only

Select **one** primary motion from the table below based on the most common USER_MATURITY value among high-propensity users. Do not combine audiences into one session unless the SE has explicitly stated they must attend together.

| Most common USER_MATURITY | Primary Motion | Session |
|---|---|---|
| Inactive | First Customer Activation Workshop | 60 min |
| Exploring | Follow-up Coaching Session | 60 min |
| Activated (UI only, no CLI) | Desktop/CLI Enablement Session | 60 min |
| Expanded | Champion Enablement | 60–90 min |
| Dormant (was active, now zero) | Reactivation Session | 60 min |
| Mixed audience | Split into two sessions (see below) | — |

**If the account has meaningfully different user groups** (e.g., some Inactive, some Expanded), recommend:
- A **primary session** targeting the largest or highest-priority group
- A **follow-on session** for the other group — listed separately in Section 4

A hybrid is appropriate only when the SE explicitly confirms the groups must meet together. Note the tradeoff: mixed audiences require different pacing and may dilute the first-prompt experience.

### 3c. Interface recommendation

| Persona / Maturity | Recommended Interface |
|---|---|
| Inactive / Exploring, first time | Snowsight — zero setup, quickest first win |
| Technical, DevEx-focused | CoCo CLI |
| Developer persona, IDE preference | CoCo Desktop — **recommend at the close, not the open** |

Never let installation block the first win.

### 3d. Level 2 readiness

Recommend the Cortex Agent HOL only when ALL are true:
- At least one developer or data engineer is attending
- Account is ACTIVATED (L3) or above
- Evidence (SFDC opportunity, TOOLS_USED, or meeting notes) suggests production AI intent
- Customer has a specific business question end-users need to answer in plain language

Do NOT recommend Level 2 for a First Prompt session.

### 3e. Readiness assessment

Score six signals. Use observed data only; label inferred signals as [HYPOTHESIS].

| Signal | Source |
|---|---|
| High-propensity user identified (PROPENSITY_CREDITS_L30 > 0) | R2 |
| CoCo access confirmed (ANY_UI_USERS > 0, not fully blocked) | R1 |
| Use case available (from SFDC or A360 TOOLS_USED) | R2 / O1–O2 |
| Technical persona attending (PREDICTED_TYPE) | R2 |
| No infrastructure blocker (IS_INFRASTRUCTURE_BLOCKED = FALSE) | R1 |
| No active legal/compliance hold | SFDC — mark ✗ if unavailable |

Map confirmed signals to verdict:
- 5–6 confirmed → **Ready now**
- 3–4 confirmed, no blocking ✗ → **Ready with prerequisites** — list what must be resolved
- Any ✗ blocking signal, or fewer than 3 confirmed → **Not ready** — list what must be cleared

### 3f. Prompt classification

Classify every recommended prompt before including it:
- **Low-friction** — works with standard access to a known table or object; no special privileges needed
- **Privilege-dependent** — requires MONITOR, ACCOUNTADMIN, ACCOUNT_USAGE, or similar elevated access
- **Advanced** — requires a dbt project, semantic view, CLI/Desktop, or agent privileges

**For the first session prompt (:15–:30), always choose Low-friction unless required access has been explicitly confirmed before the session.**

### 3g. Human attendee validation

Before naming any user as a recommended attendee, score them against these checks from R2 data:

| Check | Likely human signal | Likely service/shared signal |
|---|---|---|
| EMAIL | Non-null, personal format | NULL or shared alias |
| USER_NAME | Mixed case, personal name pattern | ALL_CAPS, underscore-heavy, ends in `_SA`, `_SVC`, `_BI`, `_TWH`, `_DBT` |
| PREDICTED_TYPE | Any non-Unknown | Unknown |
| TOOLS_USED | Interactive surfaces (snowsight_*, cortex_*) | Programmatic patterns only |

Label each candidate as: **Verified human** / **Likely human — confirm before inviting** / **Excluded (service/shared account)**. Do not list excluded accounts as primary attendees. Flag likely-human candidates with a one-line confirmation note.

---

### Output structure

Generate a **Session Brief** by default. Offer the **Full Appendix** only if the user asks.

**Session Brief** (minimum needed to prepare and run the session):
1. Executive Summary
2. Customer Snapshot
3. Activation Readiness
4. Recommended Motion + Follow-on
5. Suggested Attendees
6. Objective + Opening Question + Three Prompts
7. Before You Go (prerequisites, assets, risks)
8. Follow-up Plan
9. SE Action Card

Move to the **Full Appendix**: detailed trend analysis, Level 2 HOL details, competitive signals, extended facilitator notes, full adoption signal table.

Apply `[OBSERVED]` / `[RECOMMENDED]` / `[HYPOTHESIS]` labels throughout. Attach 🟢 / 🟡 / 🔴 to every recommendation. Use conditional phrasing for behavior — never predict what a specific person will do. Do not generate claims about security, data residency, cost, pricing, performance, or installation time that are not sourced from the linked reference assets.

---

### SESSION BRIEF

---

#### 1 — Executive Summary

2–3 sentences. State: account name, exact A360 maturity (e.g., ACTIVATED (L3)), primary recommended motion, and single most important outcome. Observed data only.

When the account has mixed Inactive and Engaged users: describe account maturity accurately, then describe the specific user cohort the motion targets — not the entire account. Example: "This ACTIVATED (L3) account contains a First Prompt cohort of N high-propensity users who have never typed a CoCo prompt — the recommended motion targets that cohort specifically."

---

#### 2 — Customer Snapshot

**A360** `[OBSERVED]`:
- Maturity: [ACCOUNT_TIER] ([Level]) — e.g., ACTIVATED (L3)
- Target: [next stage] ([next level])
- 90-day trend: [growing / flat / declining — from DAYS_30 vs DAYS_90/3]
- UI users: [ANY_UI_USERS] any-use / [ENGAGED_UI_USERS] engaged
- CLI/Desktop: [ANY_CLI_DESKTOP_USERS] any-use / [ENGAGED_CLI_DESKTOP_USERS] engaged
- Last CoCo usage: [LAST_COCO_USAGE_DATE]
- Unblocked eligible users: [UNBLOCKED_SF_USERS] of [SF_USERS]
- Largest human persona group: [from R3, exclude Unknown/service rows]
- AE / SE: [ACCOUNT_EXECUTIVE] / [SALES_ENGINEER]

**SFDC** `[OBSERVED]` only — never supplement missing SFDC fields with public knowledge, company reputation, or inferred business context. If SFDC is unavailable, state each field as unavailable and explain what it would add:
- Industry: [from SFDC or "unavailable — ask AE to confirm before the meeting"]
- Active opportunities, workloads, products, AI initiatives, exec sponsor, technical champion, meeting themes: [from SFDC or "unavailable"]

**Data gaps:** List unavailable fields, what each would add to the recommendations, and what is needed to resolve them.

---

#### 3 — Activation Readiness

```
Customer Activation Readiness
──────────────────────────────
✓ / ⚠ / ✗  [Signal]                [label + note]
...

Verdict:  Ready now  /  Ready with prerequisites  /  Not ready
Prerequisites: [list if not Ready now]

Data confidence: High / Medium / Low — [reason]
```

**Account-level vs attendee-level access:** Confirming `ANY_UI_USERS > 0` and `IS_INFRASTRUCTURE_BLOCKED = FALSE` proves account-level CoCo availability — not that any specific proposed attendee has the required role or model access. Always include an explicit attendee-level access verification step in prerequisites.

---

#### 4 — Recommended Motion

**Primary session** `[RECOMMENDED]` 🟢 / 🟡 / 🔴

- **Motion:** [exact name from Step 3b]
- **Target cohort:** [specific verified-human users, with USER_MATURITY values]
- **Why:** One sentence. Cite the single strongest signal from R2 — e.g., "5 of the top 6 propensity users are Inactive with zero L28 prompts."
- **Format / Interface / Environment**

**The customer types every prompt.** The SE coaches and helps recover verbally. Taking the keyboard is a last resort — if used, hand it back immediately.

Motion reminders: First Prompt → default to Snowsight, Desktop at the close not the open; Drive to Engaged → existing workflows only; CLI/Desktop → confirm device policy and IT permissions before stating it as a next step, do not assert specific installation times; Champion → frame around champion running it for teammates; Reactivation → diagnose before recommending new workflows.

**Follow-on session** (if audience is split — list separately; never combine):
- Motion, target cohort, timing

---

#### 5 — Suggested Attendees

**Primary attendees** `[OBSERVED]` — verified humans only (from Step 3g validation):

| Name | Human status | Persona | Propensity Credits | CoCo L28 | USER_MATURITY | Priority |
|---|---|---|---|---|---|---|
| [name] | Verified / Confirm first | | | | | HIGH / MED |

Service accounts and shared logins excluded. "Confirm first" users need human verification before scheduling.

**Champion candidates** `[RECOMMENDED]` — conditional language only:
"Based on [specific observed TOOLS_USED or activity signal], this user appears technically ready for advanced material. Requires SE confirmation after direct customer interaction before selecting as champion."

---

#### 6 — Objective + Opening Question + Three Prompts

**Objective** (one sentence, `[RECOMMENDED]`): "Help [persona] at [company] [specific problem] using [their actual data] so they [outcome]."

**Opening question** (`[RECOMMENDED]`): ground in observed TOOLS_USED, persona, and workloads — label as `[HYPOTHESIS]` if based on industry assumption only.

---

**Prompt 1** → :15–:30 — **Low-friction required**

Unless a specific schema context has been confirmed in advance, use:

> "List the databases and schemas I have access to in this Snowflake account. For each, use only the object names and any available metadata comments to describe its likely purpose — clearly note when the business purpose cannot be determined. Then suggest three tables worth looking at next."

- **Access required:** Low-friction — any role
- **Why:** Works on any account; produces context that informs Prompts 2 and 3; confirms CoCo understands the customer's environment

---

**Prompt 2** → :30–:50 — adaptive based on available evidence

Choose the prompt source in this order:

**If SFDC opportunity or use case is available** `[OBSERVED]`:
> Build a prompt directly from the opportunity description or stated use case. Name the business problem explicitly.

**Else if A360 TOOLS_USED shows a specific surface** (e.g., dbt, cortex_analyst, ai_observability) `[OBSERVED]`:
> Build a prompt tied to that tool and its likely workflow. Example: if TOOLS_USED includes `snowsight_dbt_project`, suggest a dbt model explainer or quality check prompt.

**Else — use the metadata exploration fallback**:
> "Using one of the tables we identified in Prompt 1 that your team works with regularly, help me answer a common question from that data. Based only on the table and column names, suggest three useful questions this table could answer — then ask me which one to pursue."

- **Access required:** Low-friction when using table from Prompt 1; classify accordingly if domain-specific
- **Why:** One sentence citing the evidence used — `[OBSERVED]` if from SFDC or TOOLS_USED, `[HYPOTHESIS]` if inferred

---

**Prompt 3** → :30–:50 or take-home

Include only if the attending persona and access level support it. If Advanced, note: "Best for [name/persona] in the follow-on session — requires [specific access]."

- **Access required:** Low-friction / Privilege-dependent / Advanced
- Same metadata as Prompt 1

---

#### 7 — Before You Go

**Prerequisites:**
- [ ] Confirm CORTEX_USER role and cross-region inference for every named attendee — 24h before
- [ ] Confirm all attendees are in the unblocked eligible segment (not infrastructure-blocked)
- [ ] Verify "Confirm first" attendees are individuals, not shared logins
- [ ] Get a specific table name or use case from AE or customer contact to use in Prompt 2

**Key assets:**

| Asset | Why relevant | Link |
|---|---|---|
| CoCo Activation Workshop Guide | Core facilitation reference | [Workshop Guide](https://snowflake.seismic.com/Link/Content/DC67TJQbWf79dGTH3mmBqCfD9WQ3) |
| CoCo Activation Program (all resources) | Battlecards, prompts, HOL, Security FAQ | [Activation Program Hub](https://snowflake.seismic.com/Link/Content/DCqmHTVR4d4VH84WgH6bMD44CMhB) |
| CoCo Security FAQ | FinServ / Healthcare / compliance signals — direct customer to this; do not paraphrase it | Via Activation Program Hub |
| Industry Prompt Spreadsheet | Filter by industry for :30–:50 prompts | Via Activation Program Hub |
| [Additional assets — only if account-specific justification exists] | [reason] | Via Activation Program Hub |

**Risks** (3–5 bullets, account-specific):
- **Access at session start** — confirm CORTEX_USER role and cross-region inference 24h before; have admin on standby
- **Security / compliance question** — Do not generate your own claims. Direct customer to the CoCo Security FAQ (linked above). CoCo honors the customer's applicable Snowflake roles, policies, and controls; inference location and data handling depend on account configuration.
- **Customer hesitates to type** — Coach verbally; do not take the keyboard. Guide them to the prompt start. Demonstration is a last resort.
- **[Account-specific risks from R1/R2 data — label `[HYPOTHESIS]` if inferred]**

**What success looks like:**
- [ ] Customer typed every prompt — not the SE
- [ ] Customer saw output from their own data
- [ ] Customer left with 3 prompts tied to their actual work
- [ ] Named next meeting on the calendar (title includes "CoCo")
- [ ] Champion candidate identified by name
- [ ] Follow-up email sent within 24h

---

#### 8 — Follow-up Plan

**48h email** (send within 24h):
- 3 take-home prompts (copy/paste ready)
- Full prompt library: [Activation Program Hub](https://snowflake.seismic.com/Link/Content/DCqmHTVR4d4VH84WgH6bMD44CMhB)
- Champion offer: "If other teammates want to get set up, I can run the same session for a group."

**Next meeting:**
- Title must include "CoCo": e.g., "CoCo Office Hours — [Company]"
- Format and who to invite based on motion outcome

**Expected A360 motion change:** [current USER_MATURITY → next]

**Proposed success targets** *(account-specific estimates — not A360 program thresholds)*:

| Period | Green | Amber | Red |
|---|---|---|---|
| Week 1 | [specific to account] | | |
| Month 1 | [specific to account] | | |
| Month 3 | [specific to account] | | |

Week 1 if green: "Saw you've been using CoCo this week — anything interesting come up?"
Week 1 if red: "Did you get a chance to try those prompts? Happy to jump on a quick call."

---

#### 9 — SE Action Card

```
Your next five actions
──────────────────────────────────────────────────
1. Confirm proposed attendees are humans with CoCo access.
2. Ask AE or customer contact: what is one real use case or table to anchor on?
3. Customize Prompt 2 with the actual table or workflow from step 2.
4. Schedule the session — title must include "CoCo".
5. Send 3 prompts and schedule the follow-on within 24h of the session.
```

---

#### Session Success Checklist

```
Today's session is a success when:
──────────────────────────────────────────────────
□ Customer typed every prompt — not the SE
□ Customer got at least one useful answer from their own data
□ Customer left with 3 specific prompts to try this week
□ Next meeting is on the calendar (title includes "CoCo")
□ Champion candidate identified by name
□ Follow-up email sent within 24h
```
---

## Motion Reference (Quick Decision)

```
A360: "First prompt"          → First Customer Activation Workshop (60 min)
A360: "Introduce CLI/Desktop" → Desktop/CLI Enablement (install + Quickstart + first workflow)
A360: "Drive to Engaged"      → Follow-up Coaching (deepen existing habits)
A360: "Internal Champion"     → Champion Enablement + Cortex Agent HOL intro
A360: "Re-engage on CoCo"     → Reactivation Session (diagnose drop-off first)
A360: not accessible          → Ask user for maturity + build from what you have
```

---

## Supporting Stats (for exec conversations)

From the Workshop Guide (Aug 2026):
- 77% of CoCo users use it fewer than 10 days in 28
- 3+ CLI/Desktop users = 5X more consumption growth vs 1–2 users
- CLI users grow consumption 7.6% faster than UI-only accounts
- 51% fewer tokens vs Claude Code (Opus 4.7) on ADE-Bench
- ~$19/mo CoCo with Cortex Sense vs ~$78/mo frontier AI coding agent (per user/month)
- 72.1% ADE-Bench pass rate (86.3% with Cortex Sense) vs. 21% for Claude Code without context layer
- $0 first experience cost — and it determines everything

---

## Known Limitations

- **Role:** Queries run as `SALES_ENGINEER` role. If unavailable, A360 data may be inaccessible with `COLLEGEDS_MODELING_RL`.
- **SFDC data:** `SALES.RAVEN` is optional. If unavailable, flag gaps and proceed from A360 data alone.
- **No A360 data:** Ask the user to open the A360 CoCo Adoption page and share maturity level, user count, and top 3–5 users from User Targeting Details manually.
- **Unknown attendees:** Use the largest A360 persona group (from R3) as the planning basis.
- **Skill usage telemetry:** The skill logs each invocation via `CALL FIELD_ENABLEMENT.ANALYTICS.LOG_SKILL_USAGE(...)` after Phase 1 completes. CoCo classifies this as a write and shows an approval card labeled **"Log activation session for [Account Name]"** — click Allow to record the session. To auto-approve without a manual click, add a `PermissionRequest` hook to `~/.snowflake/cortex/hooks.json` that matches `LOG_SKILL_USAGE` and returns `{"hookSpecificOutput":{"permissionDecision":"allow"}}`.
