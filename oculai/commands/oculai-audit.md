# /oculai-audit

Run a quality audit on a completed or in-progress sourcing run.

## Usage

```
/oculai-audit <run_id>
```

## Parameters

- `run_id` (required): The run to audit

## What Happens

1. Fetches complete run state, candidate list, and all evidence
2. Launches Quality Auditor subagent
3. Presents audit findings:
   - Evidence quality per candidate
   - Identity merge accuracy
   - Bias and diversity analysis
   - Process completeness
   - Compliance issues
4. Provides actionable recommendations

## Subagents Activated

- Quality Auditor
