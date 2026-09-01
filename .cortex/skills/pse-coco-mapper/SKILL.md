---
name: PSE_COCO_MAPPER
description: "Map Cortex Code (CoCo) skill tag names to a list of Snowflake partner use cases based on their TECHNICAL_USE_CASE category. Use when: generating CoCo skill tag suggestions for use cases in a PSE email, mapping CoCo skill names to a batch of use cases, filling the 'USED / WILL USE COCO' field. Triggers: map coco skills, coco skill mapping, used will use coco, coco suggestion for use case, pse email coco."
---

# PSE CoCo Mapper

## Purpose

You receive a structured list of Snowflake partner use cases and must return the relevant
Cortex Code (CoCo) skill tag names for each use case, formatted for the USED / WILL USE COCO
field in a PSE partner confirmation email.

## Input Format

The user will provide a list of use cases in this format:

```
- UC-XXXXXX: <UC Name> | <Account Name> | <Stage> | <Technical Use Case> | <EACV>
```

## Instructions

1. Use the PSE_UC_PORTFOLIO_ANALYSIS skill
   (snow://skill_catalog/USER$DSHAVKANI.SKILL_SHARING_89F4D7DE.PSE_UC_PORTFOLIO_ANALYSIS)
   to determine which specific Cortex Code skill tags apply to each use case based on
   its TECHNICAL_USE_CASE category.

2. Apply this mapping (TECHNICAL_USE_CASE → CoCo skill tags):
   - AI: Conversational Assistants → cortex-agent
   - AI: Machine Learning → machine-learning, snowflake-notebooks
   - AI: Cortex AI Functions → cortex-ai-functions
   - AI: Snowflake Intelligence & Agents → agent-optimization, cortex-agent
   - DE: Ingestion → openflow, snowpark-python, snowpipe-streaming
   - DE: Transformation → dbt-data-modeling, dynamic-tables, snowpark-python
   - DE: Interoperable Storage → iceberg
   - Analytics: Business Intelligence → dashboard, semantic-view
   - Analytics: Applied Analytics → dashboard, semantic-view
   - Analytics: Lakehouse Analytics → iceberg, snowflake-notebooks
   - Analytics: Interactive Analytics → dashboard, semantic-view
   - Platform: Storage → iceberg, storage-lifecycle-policy
   - Platform: Compliance/Security/Governance → data-governance, lineage, trust-center
   - Apps & Collab: Build → developing-with-streamlit
   - Apps & Collab: External Collaboration → data-cleanrooms
   - Migration (any keyword) → migration-guide, snowconvert-assessment

3. A use case can have multiple TECHNICAL_USE_CASE values separated by semicolons.
   Include tags for ALL matching categories.

## Output Format

Return ONLY lines in this exact format — one per use case, comma-separated skill tags:

```
UC-XXXXXX: skill-tag-1, skill-tag-2, skill-tag-3
UC-YYYYYY: skill-tag-1, skill-tag-2
```

No headers, no explanations, no markdown, no sentences. Just UC lines with skill tags.
