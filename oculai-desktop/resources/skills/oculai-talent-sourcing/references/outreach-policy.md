# Outreach Policy

## Core Rule

**Never autonomously send outreach or write to external systems.** All external actions require explicit human approval via `oculai_request_human_approval`.

## Approval-Required Actions

### Outreach
- Sending emails, LinkedIn messages, InMail, WeChat messages
- Any direct candidate contact
- Any communication that appears to come from a human recruiter

### External System Writes
- Writing to ATS (Applicant Tracking System)
- Updating CRM records
- Posting job listings
- Any API call with write/update/delete semantics to external systems

### Browser Sessions
- Any operation using logged-in browser state
- Any scraping behind authentication
- Any form submission on external websites

## Approval Workflow

1. Main Agent calls `oculai_request_human_approval` with:
   - `action_type`: "outreach_email", "linkedin_message", etc.
   - `action_context`: {candidate_name, channel, template_used, personalization}
   - `draft_content`: Full text of proposed outreach

2. Human reviews and either approves or denies

3. If approved, main Agent may proceed
   If denied, main Agent adjusts based on feedback

## Outreach Best Practices

### Personalization
- Reference specific candidate work (paper, project, talk)
- Explain why this role specifically fits their profile
- Avoid generic templates

### Compliance
- Respect candidate privacy
- Comply with local anti-spam laws (CAN-SPAM, GDPR, PIPL)
- Include opt-out mechanism
- Do not misrepresent identity

### Channel Selection
- Academic candidates: Email (from institution page) > LinkedIn
- Industry engineers: GitHub issue/email > LinkedIn
- Chinese candidates: Email > WeChat (with approval) > BOSS直聘 (with approval)

### Frequency
- Maximum 1 outreach attempt per candidate per sourcing run
- Minimum 7 days between follow-ups
- Stop after 2 failed attempts (no reply)

## Outreach Draft Structure

Each outreach draft should include:
1. **Greeting**: Personalized, referencing specific work
2. **Context**: Why you're reaching out (specific role)
3. **Value Proposition**: Why this role fits their profile (specific evidence)
4. **Call to Action**: Clear next step (reply, schedule call, etc.)
5. **Opt-out**: How to decline further contact

## Prohibited Actions

- Mass/bulk outreach (must be individually personalized)
- Misrepresenting identity or organization
- Scraping contact information at scale
- Using contacts obtained from data breaches
- Automated follow-ups without explicit opt-in
