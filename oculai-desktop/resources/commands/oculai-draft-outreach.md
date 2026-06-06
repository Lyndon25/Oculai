# /oculai-draft-outreach

Generate personalized outreach drafts for shortlisted candidates. Requires human approval before sending.

## Usage

```
/oculai-draft-outreach <run_id> [candidate_id] [candidate_id ...]
```

## Parameters

- `run_id` (required): The sourcing run
- `candidate_ids` (optional): Specific candidates to draft for. If omitted, drafts for all shortlisted candidates.

## What Happens

1. Fetches candidate profiles and assessments
2. Launches Outreach Strategist subagent for each candidate
3. Presents outreach drafts for review:
   - Personalized message
   - Recommended channel
   - Personalization rationale
4. Awaits your explicit approval before any message is sent
5. Approved messages are queued for sending (actual send requires further confirmation)

## Subagents Activated

- Outreach Strategist (one per candidate)

## Critical

**No messages are sent autonomously.** You must explicitly approve each draft before it is queued, and explicitly confirm before any actual send.
