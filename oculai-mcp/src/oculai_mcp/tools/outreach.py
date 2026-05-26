"""Outreach tools — draft generation, human approval gate.

All external-contact actions (email, LinkedIn message, etc.) must pass
through the human approval gate. These tools NEVER send messages
autonomously — they only prepare drafts and request approval.
"""

import logging
from typing import Any
from uuid import UUID, uuid4

from oculai_mcp.db.client import fetch_with_retry, fetchrow_with_retry, execute_with_retry

logger = logging.getLogger(__name__)

APPROVAL_ACTIONS = {
    "send_email": "Send email to candidate",
    "send_linkedin_message": "Send LinkedIn message",
    "send_linkedin_connection": "Send LinkedIn connection request",
    "send_wechat_message": "Send WeChat message",
    "create_calendar_invite": "Create calendar invitation",
    "export_shortlist": "Export candidate shortlist externally",
}


async def create_outreach_draft(
    run_id: UUID,
    person_id: UUID,
    strategy: str,
    template: str = "standard",
    channel: str = "email",
    draft_content: str = "",
    subject: str = "",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Create an outreach draft for a candidate.

    This only creates a draft — it does NOT send anything.
    The draft must be approved via oculai_request_approval before
    any message is sent.

    Args:
        run_id: The run UUID
        person_id: Target candidate Person UUID
        strategy: Outreach strategy (warm_intro, cold_email, linkedin_inmail, etc.)
        template: Template name to base the draft on
        channel: Contact channel (email, linkedin, wechat)
        draft_content: The draft message body
        subject: Email subject line (for email channel)
        agent_id: Agent creating the draft
    """
    # Verify candidate exists
    person = await fetchrow_with_retry(
        "SELECT canonical_name, latest_institution, latest_position FROM person WHERE person_id = $1",
        person_id,
    )
    if not person:
        return {"error": "person not found"}

    outreach_id = uuid4()
    content_preview = draft_content[:200] if draft_content else ""
    await execute_with_retry(
        """
        INSERT INTO outreachrecord
            (record_id, run_id, person_id, channel, strategy, subject,
             content_preview, content_full, template_id, status, created_by_agent, updated_by_agent)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'draft', $10, $10)
        """,
        outreach_id, run_id, person_id, channel, strategy,
        subject or "", content_preview, draft_content or "", template,
        agent_id,
    )

    logger.info(
        "Outreach draft %s created for person %s (channel=%s, strategy=%s)",
        outreach_id, person_id, channel, strategy,
    )

    return {
        "outreach_id": str(outreach_id),
        "person_id": str(person_id),
        "person_name": person["canonical_name"],
        "channel": channel,
        "strategy": strategy,
        "status": "draft",
        "requires_approval": True,
    }


async def request_human_approval(
    run_id: UUID,
    action_type: str,
    action_context: dict[str, Any],
    draft_content: str = "",
    agent_id: str = "system",
) -> dict[str, Any]:
    """Request human approval for an action that has external side effects.

    This is the GATE that all external actions must pass through:
    - Sending outreach messages
    - Exporting candidate data externally
    - Any write to external systems

    The action is blocked until a human approves via the database.

    Args:
        run_id: The run UUID
        action_type: Type of action needing approval (see APPROVAL_ACTIONS)
        action_context: Full context dict describing what, who, and why
        draft_content: The draft content to be approved
        agent_id: Agent requesting approval
    """
    if action_type not in APPROVAL_ACTIONS and not action_type.startswith("custom:"):
        return {
            "status": "error",
            "error": {
                "code": "unknown_action_type",
                "message": f"Unknown action type '{action_type}'. Valid types: {list(APPROVAL_ACTIONS.keys())} or 'custom:<name>'.",
            },
        }

    approval_id = uuid4()
    await execute_with_retry(
        """
        INSERT INTO humanapproval
            (approval_id, run_id, action_type, action_context, draft_content,
             status, requested_by, created_by_agent, updated_by_agent)
        VALUES ($1, $2, $3, $4, $5, 'pending', $6, $6, $6)
        """,
        approval_id, run_id, action_type, action_context, draft_content, agent_id,
    )

    logger.info(
        "Approval %s requested for action %s in run %s",
        approval_id, action_type, run_id,
    )

    return {
        "approval_id": str(approval_id),
        "run_id": str(run_id),
        "action_type": action_type,
        "action_label": APPROVAL_ACTIONS.get(action_type, action_type),
        "status": "pending",
        "message": "Human approval required before this action proceeds.",
    }


async def check_approval_status(approval_id: UUID) -> dict[str, Any]:
    """Check the status of a human approval request."""
    row = await fetchrow_with_retry(
        "SELECT * FROM humanapproval WHERE approval_id = $1", approval_id,
    )
    if not row:
        return {"error": "approval not found"}

    d = dict(row)
    for k in ("created_at", "updated_at", "reviewed_at"):
        if d.get(k):
            d[k] = str(d[k])

    return {
        "approval_id": str(approval_id),
        "status": d["status"],
        "action_type": d["action_type"],
        "approved": d["status"] == "approved",
        "details": d,
    }


async def list_pending_approvals(run_id: UUID | None = None) -> dict[str, Any]:
    """List all pending human approval requests.

    Args:
        run_id: Optional run UUID to filter by
    """
    if run_id:
        rows = await fetch_with_retry(
            "SELECT * FROM humanapproval WHERE status = 'pending' AND run_id = $1 ORDER BY created_at DESC",
            run_id,
        )
    else:
        rows = await fetch_with_retry(
            "SELECT * FROM humanapproval WHERE status = 'pending' ORDER BY created_at DESC",
        )

    approvals = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at", "reviewed_at"):
            if d.get(k):
                d[k] = str(d[k])
        approvals.append({
            "approval_id": str(d["approval_id"]),
            "run_id": str(d["run_id"]),
            "action_type": d["action_type"],
            "action_label": APPROVAL_ACTIONS.get(d["action_type"], d["action_type"]),
            "requested_by": d["requested_by"],
            "created_at": d["created_at"],
        })

    return {"pending_approvals": approvals, "count": len(approvals)}


async def get_outreach_history(
    person_id: UUID,
    limit: int = 50,
) -> dict[str, Any]:
    """Get outreach history for a candidate."""
    rows = await fetch_with_retry(
        """
        SELECT * FROM outreachrecord
        WHERE person_id = $1
        ORDER BY created_at DESC
        LIMIT $2
        """,
        person_id, limit,
    )

    history = []
    for r in rows:
        d = dict(r)
        for k in ("created_at", "updated_at", "sent_at"):
            if d.get(k):
                d[k] = str(d[k])
        history.append(d)

    return {
        "person_id": str(person_id),
        "outreach_history": history,
        "count": len(history),
    }
