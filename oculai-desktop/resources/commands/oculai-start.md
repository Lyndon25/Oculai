# /oculai-start

Start a new talent sourcing run. Activates the Oculai talent sourcing skill with a fresh job description.

## Usage

```
/oculai-start "Senior NLP Researcher — LLM Inference Optimization"
```

Then paste the full job description when prompted.

## Parameters

- `job_title` (required): The position title
- `jd_text` (required): Full job description text
- `required_skills` (optional): Comma-separated list of must-have skills
- `target_domains` (optional): Comma-separated academic domains (e.g., "cs.AI, cs.CL")
- `config` (optional): JSON configuration overrides

## What Happens

1. Creates a new SourcingRun in PostgreSQL
2. Discovers available data sources
3. Launches Search Strategist subagent
4. Presents the strategy for your review
5. Upon your approval, creates the Task DAG and begins parallel search

## Subagents Activated

- Search Strategist (initial)
- Source Researchers (after strategy approval)
