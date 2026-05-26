# /oculai-resume

Resume an incomplete sourcing run. Recovers state from PostgreSQL and continues from where it left off.

## Usage

```
/oculai-resume <run_id>
```

## Parameters

- `run_id` (required): The UUID of the run to resume

## What Happens

1. Fetches run state from PostgreSQL via `oculai_get_run_state`
2. Shows current progress: completed tasks, pending tasks, candidate count
3. Resumes from the next incomplete step:
   - If no strategy yet → launch Search Strategist
   - If strategy exists but tasks pending → claim and execute tasks
   - If tasks done but no shortlist → launch Fit Evaluator
   - If shortlist done → present results

## Subagents Activated

- Depends on run state — only incomplete steps are executed
