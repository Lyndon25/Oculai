# /oculai-status

Show the current status of a sourcing run.

## Usage

```
/oculai-status <run_id>
```

Or:

```
/oculai-status  (shows all runs)
```

## Parameters

- `run_id` (optional): Specific run to inspect. If omitted, lists all runs.

## What Happens

1. If no run_id: Lists all runs with status, candidate counts, creation dates
2. If run_id provided: Shows detailed status:
   - Run metadata (title, status, created_at)
   - Active Plan (strategy summary, task stats)
   - Task breakdown by type and status
   - Candidate count and shortlist status
   - Recent errors or warnings
