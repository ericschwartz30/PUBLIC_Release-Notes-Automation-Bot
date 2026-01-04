import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")
STATE_FILE = Path(__file__).parent / ".changelog_state.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def load_last_run():
    """Load the timestamp of the last run."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            state = json.load(f)
            return state.get("last_run")
    return None


def save_last_run(timestamp):
    """Save the current timestamp as the last run."""
    with open(STATE_FILE, "w") as f:
        json.dump({"last_run": timestamp}, f)

def fetch_completed_issues(since_date):
    """Fetch issues that are in a completed state, updated since the given date."""
    query = """
    query CompletedIssues($since: DateTimeOrDuration!) {
        issues(
            filter: {
                state: { type: { eq: "completed" } }
                updatedAt: { gte: $since }
            }
            first: 100
            orderBy: updatedAt
        ) {
            nodes {
                id
                title
                description
                updatedAt
                state { name }
                team { name }
                assignee {
                    name
                    email
                }
                project {
                    name
                    initiatives {
                        nodes { name }
                    }
                }
                labels { nodes { name } }
                comments {
                    nodes {
                        body
                        user { name }
                    }
                }
            }
        }
    }
    """
    response = requests.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": LINEAR_API_KEY},
        json={"query": query, "variables": {"since": since_date}}
    )
    return response.json().get("data", {}).get("issues", {}).get("nodes", [])


def get_initiative_names(issue):
    """Extract initiative names from an issue."""
    project = issue.get('project')
    if not project:
        return []
    initiatives = project.get('initiatives', {}).get('nodes', [])
    return [init['name'] for init in initiatives]


def filter_customer_worthy(issues):
    """Use Claude to filter issues that are worth announcing to customers."""

    if not issues:
        return []

    # Prepare issues for the prompt, including initiative and assignee info
    def get_assignee(issue):
        assignee = issue.get('assignee')
        if not assignee:
            return "Unassigned"
        return f"{assignee.get('name', 'Unknown')} ({assignee.get('email', '')})"

    def get_comments(issue, max_chars=800):
        comments = issue.get('comments', {}).get('nodes', [])
        if not comments:
            return ""
        comment_texts = []
        total_chars = 0
        for c in comments[:5]:  # Max 5 comments
            user_obj = c.get('user')
            user = user_obj.get('name', 'Unknown') if user_obj else 'Unknown'
            body = (c.get('body') or '')[:300]  # Truncate each comment
            if not body:
                continue
            if total_chars + len(body) > max_chars:
                break
            comment_texts.append(f"  - {user}: {body}")
            total_chars += len(body)
        if comment_texts:
            return "Comments:\n" + "\n".join(comment_texts)
        return ""

    issues_text = "\n\n".join([
        f"ID: {i['id']}\n"
        f"Title: {i['title']}\n"
        f"Assignee: {get_assignee(i)}\n"
        f"Initiative: {', '.join(get_initiative_names(i)) or 'None'}\n"
        f"Project: {i.get('project', {}).get('name', 'None') if i.get('project') else 'None'}\n"
        f"Labels: {', '.join([l['name'] for l in i.get('labels', {}).get('nodes', [])])}\n"
        f"Description: {(i.get('description') or 'No description')[:1500]}\n"
        f"{get_comments(i)}"
        for i in issues
    ])

    prompt = f"""You are helping a B2B SaaS company decide which completed tickets belong in customer-facing release notes.

Your objective is to help the team create release notes that get sent to customers. These need to be a customer-facing summary of the key things that have shipped since the last update.

Your main data source will be Linear, where the team tracks tickets that engineers work on. There are lots of things in Linear that are not customer-facing, and you need to help the team filter out the stuff that is not worth mentioning in the release notes.

================================================================================
CUSTOMIZATION GUIDE - IMPORTANT: Edit this section to match YOUR company!
================================================================================

CONTEXT ON HOW YOUR LINEAR IS SET UP:
Replace this section with information about:
- Your Linear initiatives/projects and what they represent
- Which projects/teams tend to do customer-facing work vs internal work
- Your team structure and how work is organized
- Any special naming conventions or labels you use

Example structure:
- "Core Product" initiative = customer-facing work
- "Infrastructure" initiative = mostly internal
- Specific project names and what they mean for your product

ENGINEER CONTEXT (customize with your team members):
List your engineers and whether their work tends to be customer-facing:
- Frontend engineers: Usually customer-facing (UI work)
- Full-stack engineers: Mix of customer-facing and internal
- Backend/Infrastructure engineers: Usually internal unless working on APIs/features

PRODUCT-SPECIFIC PATTERNS (customize for your domain):
Describe patterns specific to your product that help identify customer-worthy tickets:
- What types of new capabilities matter to customers?
- What are your core features/integrations?
- What terminology does your team use for customer-facing work?

For example, if you're building a developer tool:
- New integrations (GitHub, Jira, etc.) = always customer-facing
- API endpoints = usually internal unless it's a new user-facing API
- Performance improvements = customer-facing if noticeable

================================================================================

GENERAL POSITIVE SIGNALS (more likely to include):
- New integrations or capabilities
- Major UI/UX changes that alter workflows
- Performance improvements users will clearly notice
- Bug fixes that affected many customers
- New user-facing features

EXCLUDE - look for these signals:
- Testing/QA: "Test X", "QA findings", "Validate", "Run evaluations"
- Planning: "PRD", "Requirements", "Spec"
- Design-only tickets: Just creating designs, not implementing features
- Investigation: "Investigate", "Debug", "Answer X question", "Follow up on"
- Backend details: "schema", "endpoint", "route", "API", "backend", "migration" (unless user-facing)
- Internal infrastructure: Secret management, provisioning scripts, DNS config, CI/CD
- Parent tickets: Vague titles like "Improve X", "Enhance Y" without concrete deliverables

CATEGORIZATION:
For EACH ticket, decide: feature, fix, or exclude.
- "feature" = NEW capability that didn't exist before. Something you'd promote to customers.
- "fix" = Bug fixes, quality-of-life improvements, polish. Still worth mentioning but not headline news.
- "exclude" = Internal work, not customer-facing

WHAT GOES IN "fix" (NOT "feature"):
- Copy/text changes (e.g., "renamed X to Y", "updated error message")
- Performance/speed improvements (e.g., "faster loading", "pagination")
- Renaming or clarifying existing things
- Bug fixes
- Minor UI polish

WHAT GOES IN "feature":
- Any major NEW capability customers would care about
- New integrations or tools
- Significant UI changes that enable new workflows
- Features you'd announce on your website or in marketing

DECISION FRAMEWORK:
- For features: "Is this a NEW capability that didn't exist before? Would we promote this to customers?"
- For fixes: "Is this an improvement to something that already existed? Copy change? Performance boost? Bug fix?"
- If neither, exclude entirely.

Return a JSON array where each item has:
- "id": the ticket ID
- "title": the ticket title
- "decision": "feature", "fix", or "exclude"
- "reason": 5-10 word explanation

Example:
[
  {{"id": "abc", "title": "GitHub integration", "decision": "feature", "reason": "New integration with GitHub"}},
  {{"id": "def", "title": "Test login flow", "decision": "exclude", "reason": "Internal testing ticket"}}
]

Return ONLY the JSON array.

TICKETS:
{issues_text}"""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    # Parse the response - extract JSON array with decisions (skip thinking blocks)
    response_text = next(block.text for block in response.content if block.type == "text").strip()
    try:
        decisions = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\[[\s\S]*\]', response_text)
        if match:
            try:
                decisions = json.loads(match.group())
            except json.JSONDecodeError:
                print(f"Warning: Could not parse JSON")
                return {"features": [], "fixes": [], "excluded": [], "decisions": []}
        else:
            print(f"Warning: Could not find JSON in LLM response")
            return {"features": [], "fixes": [], "excluded": [], "decisions": []}

    # Create lookup by ID
    decision_map = {d['id']: d for d in decisions}

    features = []
    fixes = []
    excluded = []

    for issue in issues:
        d = decision_map.get(issue['id'], {})
        decision = d.get('decision', 'exclude')
        reason = d.get('reason', 'No reason given')

        issue_with_reason = {**issue, 'reason': reason}

        if decision == 'feature':
            features.append(issue_with_reason)
        elif decision == 'fix':
            fixes.append(issue_with_reason)
        else:
            excluded.append(issue_with_reason)

    return {
        "features": features,
        "fixes": fixes,
        "excluded": excluded,
        "decisions": decisions
    }


def group_related_tickets(categorized_issues):
    """Group related tickets into themes/features, including backend work that supports frontend features."""

    features = categorized_issues.get("features", [])
    fixes = categorized_issues.get("fixes", [])
    excluded = categorized_issues.get("excluded", [])

    if not features and not fixes:
        return {"groups": [], "ungrouped_fixes": []}

    # Include excluded backend tickets that might support frontend features
    potential_backend = [
        e for e in excluded
        if any(keyword in e.get('reason', '').lower() for keyword in ['backend', 'endpoint', 'api', 'schema'])
    ]

    def format_ticket(t):
        assignee = t.get('assignee', {})
        assignee_name = assignee.get('name', 'Unassigned') if assignee else 'Unassigned'
        project_name = t.get('project', {}).get('name', 'None') if t.get('project') else 'None'
        updated = t.get('updatedAt', 'Unknown')[:10]  # Just the date
        return (
            f"ID: {t['id']}\n"
            f"Title: {t['title']}\n"
            f"Assignee: {assignee_name}\n"
            f"Project: {project_name}\n"
            f"Completed: {updated}\n"
            f"Was: {'feature' if t in features else 'fix' if t in fixes else 'excluded (backend)'}"
        )

    all_tickets = features + fixes + potential_backend
    tickets_text = "\n\n".join([format_ticket(t) for t in all_tickets])

    prompt = f"""You are grouping related tickets into customer-facing features for release notes.

THE KEY QUESTION: "Would a customer think of these as ONE feature or MULTIPLE features?"

GROUP TOGETHER when:
- Same underlying CAPABILITY even if different implementations
  - Example: "Export to PDF" + "Export to CSV" + "Export to Excel" = ONE feature called "Data export"
  - Example: "Pagination" + "Server-side filtering" = ONE feature called "Performance improvements"
- Related frontend + backend work for the same user-facing feature
- Different engineers working on different parts of the same capability
- Tickets that would be described to a customer as ONE improvement
- Multiple tickets that together deliver a single cohesive feature

KEEP SEPARATE when:
- Different capabilities, even if related
  - Example: "GitHub integration" vs "Jira integration" = SEPARATE (different integrations)
  - Example: "Dark mode" vs "Keyboard shortcuts" = SEPARATE (different features)
- Unrelated capabilities even if same project or same engineer
- Features that target different use cases or user workflows

EXAMPLES (customize based on YOUR product):
- "GitHub auth" + "GitHub webhooks" + "GitHub API integration" -> GROUP as "GitHub integration"
- "Dashboard loading optimization" + "Report caching" -> GROUP as "Performance improvements"
- "Email notifications" + "Slack notifications" -> Could group as "Notification system" OR keep separate depending on how customers think about them
- "User authentication" + "Data export" -> SEPARATE (unrelated features)

For each group, provide:
- "name": A customer-friendly name that describes the overall capability
- "tickets": Array of ticket IDs that belong to this group
- "summary": 1 sentence describing the customer benefit

Standalone fixes go in "ungrouped_fixes".

Return JSON:
{{
  "groups": [
    {{"name": "Feature Name", "tickets": ["id1", "id2"], "summary": "Customer benefit"}}
  ],
  "ungrouped_fixes": ["id3", "id4"]
}}

TICKETS TO GROUP:
{tickets_text}"""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = next(block.text for block in response.content if block.type == "text").strip()
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{[\s\S]*\}', response_text)
        if match:
            try:
                result = json.loads(match.group())
            except:
                return {"groups": [], "ungrouped_fixes": [t['id'] for t in fixes]}
        else:
            return {"groups": [], "ungrouped_fixes": [t['id'] for t in fixes]}

    # Enrich groups with full ticket data
    all_by_id = {t['id']: t for t in all_tickets}
    enriched_groups = []
    for group in result.get("groups", []):
        enriched_groups.append({
            "name": group["name"],
            "summary": group.get("summary", ""),
            "tickets": [all_by_id.get(tid, {"id": tid, "title": "Unknown"}) for tid in group.get("tickets", [])]
        })

    ungrouped_ids = result.get("ungrouped_fixes", [])
    ungrouped = [all_by_id.get(tid, {"id": tid, "title": "Unknown"}) for tid in ungrouped_ids]

    return {
        "groups": enriched_groups,
        "ungrouped_fixes": ungrouped
    }


def draft_release_notes(categorized_issues, grouped_data):
    """Use Claude to draft customer-friendly release notes from grouped tickets."""

    groups = grouped_data.get("groups", [])
    ungrouped_fixes = grouped_data.get("ungrouped_fixes", [])

    features = categorized_issues.get("features", [])
    fixes = categorized_issues.get("fixes", [])

    if not features and not fixes:
        return ""

    # Format grouped features
    def format_group(group):
        tickets_text = "\n".join([
            f"  - {t['title']}: {(t.get('description') or 'No description')[:800]}"
            for t in group.get("tickets", [])
        ])
        return (
            f"GROUP: {group['name']}\n"
            f"Summary: {group.get('summary', 'N/A')}\n"
            f"Related tickets:\n{tickets_text}"
        )

    # Format ungrouped tickets
    def format_ticket(t):
        return (
            f"Title: {t['title']}\n"
            f"Description: {(t.get('description') or 'No description')[:1000]}"
        )

    # Build the features section from groups
    if groups:
        features_text = "\n\n".join([format_group(g) for g in groups])
    else:
        features_text = "\n\n".join([format_ticket(f) for f in features]) if features else "None"

    # Build the fixes section - prefer ungrouped_fixes if available, else use all fixes
    if ungrouped_fixes:
        fixes_text = "\n\n".join([format_ticket(f) for f in ungrouped_fixes])
    else:
        fixes_text = "\n\n".join([format_ticket(f) for f in fixes]) if fixes else "None"

    prompt = f"""You are writing customer-facing release notes in a casual, friendly tone.

================================================================================
CUSTOMIZATION GUIDE - Edit this section for YOUR product and voice!
================================================================================

YOUR PRODUCT CONTEXT:
Replace this with 1-2 sentences describing your product and who uses it.
Example: "We build an analytics platform for e-commerce companies."

YOUR BRAND VOICE:
Describe the tone you want for release notes:
- Casual and friendly vs. formal and professional?
- Use "we" or "the team" or third person?
- Technical details vs. high-level benefits?
- Any specific words/phrases to use or avoid?

Example preferences:
- "Be casual and friendly, like a Slack message to customers"
- "Use 'we' naturally, technical enough for engineers but not jargon-heavy"
- "No marketing-speak or buzzwords"

================================================================================

WRITING GUIDELINES:

1. Each GROUP below represents ONE feature - write a single bullet point for each group.

2. Be CASUAL and FRIENDLY - like you're telling a colleague about improvements:
   - BAD: "The system now automatically syncs with external databases"
   - GOOD: "Database sync - automatically pull data from external databases"

3. MOST IMPORTANT - Explain the "SO WHAT" for customers. Don't just describe what it does, explain WHY it matters and what it ENABLES:
   - BAD: "GitHub integration - now connects to GitHub"
   - GOOD: "GitHub integration - pull in PR history and code changes automatically, so you can see the full context of what shipped without leaving the app"
   - BAD: "Faster loading times"
   - GOOD: "Faster loading - dashboards now load 3x faster, so you can get to your data without waiting"
   - BAD: "New export feature"
   - GOOD: "Data export - download any report as PDF or CSV, so you can share results with stakeholders who aren't in the tool"

4. Think about the CUSTOMER WORKFLOW - how does this feature fit into their workflow? What can they do now that they couldn't before? What's faster/easier/more accurate?

5. Give SPECIFIC examples when helpful:
   - "Export to PDF, CSV, or Excel"
   - "Works with GitHub, GitLab, and Bitbucket"
   - "Reduced load times from 5s to under 1s"

6. Optionally include WHERE to find new features:
   - "You can find the export button in the top right of any report"

7. Keep bullets short but informative - 1-2 sentences for the main point, sub-bullets for extra context.

FORMAT - use Slack markdown (mrkdwn):
- Use *asterisks* for bold (not **double**)
- Use bullet points with proper indentation for sub-bullets

*New features*
• *Feature name* - what it does and why it matters
    ◦ Sub-bullet with helpful context (if it adds value)
• *Another feature* - brief description

*Bug fixes / quality of life*
• *Fix name* - brief context if helpful

EXAMPLES (match this style, using Slack mrkdwn):

Example 1 - Simple improvements:
• *Better error messages* - clearer explanations when something goes wrong
• *Improved navigation* - easier to find what you're looking for
• *Faster search* - results now load instantly

Example 2 - Feature with sub-bullets:
• *GitHub integration* - automatically sync PRs and commits to see what shipped
    ◦ Works with GitHub, GitLab, and Bitbucket
    ◦ Find it in Settings > Integrations

Example 3 - Feature with "previously → now" framing:
• *Advanced filters* - narrow down results by date, user, or status
    ◦ Previously you could only filter by one thing at a time
    ◦ Now you can combine multiple filters for precise results

KEY RULES:
- Make feature/fix names bold with *asterisks*
- Use • for main bullets and ◦ for sub-bullets (with 4-space indent)
- Sub-bullets are OPTIONAL - use them when they add real value (helpful context, examples, "where to find it")
- Skip sub-bullets for straightforward features that don't need extra explanation
- Use "Previously X, now Y" framing when it helps explain WHY a change matters
- Focus on what's most impactful for customers to know

---

FEATURE GROUPS (each group = ONE bullet point):
{features_text}

BUG FIX / QOL TICKETS:
{fixes_text}

Write the release notes. Output the two sections with headers."""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    return next(block.text for block in response.content if block.type == "text").strip()


def send_to_slack(release_notes, since_date, end_date):
    """Send release notes to Slack via webhook."""
    if not SLACK_WEBHOOK_URL:
        print("No Slack webhook configured, skipping Slack notification")
        return False

    # Format the header with date range
    header = f"🚀 *Product Updates* ({since_date} → {end_date})\n{'─' * 40}\n\n"
    full_message = header + release_notes

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json={
                "text": full_message,
                "unfurl_links": False,
                "unfurl_media": False
            }
        )
        if response.status_code == 200:
            print("Successfully sent to Slack!")
            return True
        else:
            print(f"Slack error: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"Failed to send to Slack: {e}")
        return False


def main():
    print("=" * 60)
    print("CHANGELOG BOT")
    print("=" * 60)

    # Check for START_DATE env var first, then fall back to state file
    start_date_override = os.getenv("START_DATE")
    if start_date_override:
        since = start_date_override.strip()
        print(f"\nUsing manual start date: {since}")
    else:
        last_run = load_last_run()
        if last_run:
            since = last_run
            print(f"\nLast run: {since}")
        else:
            since_date = datetime.now() - timedelta(days=7)
            since = since_date.strftime("%Y-%m-%d")
            print(f"\nFirst run - looking back 7 days")

    print(f"Fetching completed tickets since {since}...")
    issues = fetch_completed_issues(since)
    print(f"Found {len(issues)} completed tickets.")

    if not issues:
        print("No tickets to process.")
        return

    print(f"\nAsking Claude to filter for customer-worthy items...")
    categorized = filter_customer_worthy(issues)

    features = categorized.get("features", [])
    fixes = categorized.get("fixes", [])
    excluded = categorized.get("excluded", [])

    # Helper to get assignee name
    def get_assignee_name(issue):
        assignee = issue.get('assignee')
        if not assignee:
            return "Unassigned"
        return assignee.get('name', assignee.get('email', 'Unknown'))

    # STAGE 1: Show selected features
    print("\n" + "=" * 70)
    print(f"STAGE 1: FEATURES SELECTED ({len(features)} tickets)")
    print("=" * 70)
    for item in features:
        print(f"\n✓ {item['title']}")
        print(f"  Assignee: {get_assignee_name(item)}")
        print(f"  Reason: {item.get('reason', 'N/A')}")

    # STAGE 2: Show selected fixes
    print("\n" + "=" * 70)
    print(f"STAGE 2: BUG FIXES / QOL SELECTED ({len(fixes)} tickets)")
    print("=" * 70)
    for item in fixes:
        print(f"\n✓ {item['title']}")
        print(f"  Assignee: {get_assignee_name(item)}")
        print(f"  Reason: {item.get('reason', 'N/A')}")

    # STAGE 3: Show excluded tickets
    print("\n" + "=" * 70)
    print(f"STAGE 3: EXCLUDED ({len(excluded)} tickets)")
    print("=" * 70)
    for item in excluded:
        print(f"\n✗ {item['title']}")
        print(f"  Assignee: {get_assignee_name(item)}")
        print(f"  Why excluded: {item.get('reason', 'N/A')}")

    if len(features) == 0 and len(fixes) == 0:
        print("\nNo customer-worthy tickets found.")
        return

    # STAGE 4: Group related tickets
    print("\n" + "=" * 70)
    print("STAGE 4: GROUPING RELATED TICKETS...")
    print("=" * 70)

    grouped_data = group_related_tickets(categorized)
    groups = grouped_data.get("groups", [])
    ungrouped_fixes = grouped_data.get("ungrouped_fixes", [])

    if groups:
        print(f"\nFound {len(groups)} feature groups:")
        for i, group in enumerate(groups, 1):
            print(f"\n{i}. {group['name']}")
            print(f"   Summary: {group.get('summary', 'N/A')}")
            print(f"   Tickets:")
            for ticket in group.get("tickets", []):
                assignee = ticket.get('assignee', {})
                assignee_name = assignee.get('name', 'Unassigned') if assignee else 'Unassigned'
                print(f"     - {ticket['title']} ({assignee_name})")
    else:
        print("\nNo groups found - tickets will be listed individually.")

    if ungrouped_fixes:
        print(f"\nUngrouped fixes ({len(ungrouped_fixes)}):")
        for ticket in ungrouped_fixes:
            print(f"  - {ticket.get('title', ticket.get('id', 'Unknown'))}")

    # STAGE 5: Draft release notes
    print("\n" + "=" * 70)
    print("STAGE 5: DRAFTING RELEASE NOTES...")
    print("=" * 70)

    release_notes = draft_release_notes(categorized, grouped_data)

    print("\n" + "=" * 70)
    print("FINAL OUTPUT: RELEASE NOTES DRAFT")
    print("=" * 70)
    print(f"\n{release_notes}\n")

    # Send to Slack if configured
    print("=" * 70)
    print("SENDING TO SLACK...")
    print("=" * 70)
    today = datetime.now().strftime("%Y-%m-%d")
    send_to_slack(release_notes, since, today)

    # Save current timestamp for next run
    save_last_run(today)
    print(f"\nSaved run timestamp: {today}")


if __name__ == "__main__":
    main()
