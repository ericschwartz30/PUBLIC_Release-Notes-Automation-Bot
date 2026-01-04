"""
Customer-Specific Release Notes Generator

This module extends the changelog bot to generate tailored release notes
for specific customers by:
1. Fetching recent Granola meeting notes for that customer
2. Extracting their pain points, requests, and interests
3. Cross-referencing with shipped features
4. Generating release notes that emphasize what matters to them
"""

import json
import os
from pathlib import Path
from datetime import datetime, timedelta
import anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Customer name aliases - maps various names to canonical folder search terms
# CUSTOMIZE THIS: Add your customer names and how they appear in Granola folders
# Example:
# CUSTOMER_ALIASES = {
#     "acme": ["acme", "acme corp"],
#     "globex": ["globex", "globex corporation"],
#     "initech": ["initech"],
# }
CUSTOMER_ALIASES = {
    # Add your customer aliases here
    # Format: "customer_name": ["search", "terms", "in", "folders"]
}


def load_granola_cache():
    """Load the Granola cache from the local filesystem."""
    cache_path = Path.home() / "Library/Application Support/Granola/cache-v3.json"

    if not cache_path.exists():
        print("Warning: Granola cache not found")
        return None

    with open(cache_path) as f:
        data = json.load(f)

    cache = json.loads(data['cache'])
    return cache.get('state', {})


def find_customer_meetings(customer_name: str, days_back: int = 30) -> list[dict]:
    """
    Find recent meetings for a specific customer.

    Tries local Granola cache first, falls back to API if unavailable.

    Args:
        customer_name: Customer name (e.g., "ACME", "Globex")
        days_back: How many days back to search (default 30)

    Returns:
        List of meeting documents with notes
    """
    state = load_granola_cache()

    # If no local cache, try the API
    if not state:
        print("Local Granola cache not available, trying API...")
        from granola_api import find_customer_meetings_api
        return find_customer_meetings_api(customer_name, days_back)

    docs = state.get('documents', {})
    doc_lists = state.get('documentLists', {})
    lists_meta = state.get('documentListsMetadata', {})

    # Normalize customer name and get search terms
    customer_lower = customer_name.lower().strip()
    search_terms = CUSTOMER_ALIASES.get(customer_lower, [customer_lower])

    # Find matching folder IDs
    matching_folder_ids = []
    for list_id, meta in lists_meta.items():
        folder_title = (meta.get('title') or '').lower()
        if any(term in folder_title for term in search_terms):
            matching_folder_ids.append(list_id)
            print(f"  Found folder: {meta.get('title')}")

    # Get document IDs from matching folders
    customer_doc_ids = set()
    for folder_id in matching_folder_ids:
        if folder_id in doc_lists:
            for doc_id in doc_lists[folder_id]:
                customer_doc_ids.add(doc_id)

    # Filter to recent meetings with content
    cutoff_date = datetime.now() - timedelta(days=days_back)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d")

    meetings = []
    for doc_id in customer_doc_ids:
        if doc_id not in docs:
            continue

        doc = docs[doc_id]
        created = doc.get('created_at', '')[:10]

        if created >= cutoff_str:
            notes = doc.get('notes_markdown') or doc.get('notes_plain') or ''
            if notes and len(notes) > 50:  # Has meaningful content
                meetings.append({
                    'title': doc.get('title', 'Untitled'),
                    'date': created,
                    'notes': notes,
                    'summary': doc.get('summary', ''),
                })

    # Sort by date descending
    meetings.sort(key=lambda x: x['date'], reverse=True)
    return meetings


def extract_customer_context(meetings: list[dict], customer_name: str) -> str:
    """
    Use Claude to extract key themes, pain points, and interests from meeting notes.
    """
    if not meetings:
        return "No recent meetings found for this customer."

    # Combine meeting notes
    meetings_text = "\n\n".join([
        f"=== {m['title']} ({m['date']}) ===\n{m['notes']}"
        for m in meetings
    ])

    prompt = f"""Analyze these meeting notes from calls with {customer_name} and extract:

1. **Pain points**: What problems or frustrations did they mention?
2. **Feature requests**: What did they ask for or wish existed?
3. **Interests**: What capabilities seemed most interesting/useful to them?
4. **Context**: What's their environment like? (tools they use, team structure, workflows)

Be specific and quote or paraphrase their actual words where possible.

MEETING NOTES:
{meetings_text}

Provide a structured summary that can be used to tailor release notes for this customer."""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text


def generate_tailored_release_notes(
    features: list[dict],
    fixes: list[dict],
    customer_name: str,
    customer_context: str,
    meeting_notes_summary: str
) -> str:
    """
    Generate release notes tailored to a specific customer's interests.
    """
    # Format features and fixes
    features_text = "\n".join([
        f"- {f.get('title', 'Unknown')}: {(f.get('description') or 'No description')[:500]}"
        for f in features
    ])

    fixes_text = "\n".join([
        f"- {f.get('title', 'Unknown')}: {(f.get('description') or 'No description')[:300]}"
        for f in fixes
    ])

    prompt = f"""You are writing customer-specific release notes for {customer_name}.

CUSTOMER CONTEXT (from recent calls):
{customer_context}

RECENT MEETING NOTES SUMMARY:
{meeting_notes_summary}

FEATURES THAT SHIPPED:
{features_text or "None"}

BUG FIXES / QOL:
{fixes_text or "None"}

Write release notes that:

1. **Lead with what matters to them** - If a shipped feature addresses their pain points or requests, highlight it prominently and connect it to their specific use case.

2. **Use their language** - Reference specific things they mentioned (e.g., if they talked about specific features, tools, or workflows, use those terms).

3. **Skip irrelevant items** - Don't mention features that have nothing to do with their needs. It's okay to have a shorter list.

4. **Add "You asked, we built" moments** - If something directly addresses feedback from the meetings, call it out and credit the person who raised it: "Based on [Name]'s feedback about X, we've added Y"

5. **Be conversational** - This is going to a specific customer, so it can feel more personal than generic release notes.

IMPORTANT:
- Address the note to the TEAM (e.g., "Hey [Company] team!" or "Hi team!"), NOT to an individual person
- These notes go to the whole customer team, not just one person you spoke with
- DO reference individuals BY NAME when citing their specific feedback (e.g., "[Name] mentioned wanting X" or "Based on [Name]'s request for Y")

FORMAT:
- Use Slack mrkdwn (*bold*, bullet points)
- Keep it concise but personalized
- Include a brief intro acknowledging the relationship

Example tone:
"Hey team! Here's what we've shipped recently that we think you'll find useful based on our conversations..."
"""

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=16000,
        thinking={
            "type": "enabled",
            "budget_tokens": 10000
        },
        messages=[{"role": "user", "content": prompt}]
    )

    return next(block.text for block in response.content if block.type == "text")


def generate_generic_release_notes(features: list[dict], fixes: list[dict]) -> str:
    """
    Generate standard (non-customer-specific) release notes.
    This is the existing behavior from changelog_bot.py.
    """
    # Import the existing draft function
    from changelog_bot import draft_release_notes, group_related_tickets

    categorized = {
        "features": features,
        "fixes": fixes,
        "excluded": []
    }

    grouped = group_related_tickets(categorized)
    return draft_release_notes(categorized, grouped)


def main(customer_name: str = None, days_back: int = 30, since_date: str = None, send_to_slack: bool = False):
    """
    Main function to generate release notes.

    Args:
        customer_name: If provided, generates customer-specific notes.
                      If None, generates generic notes.
        days_back: How many days of Granola meetings to consider.
        since_date: Override start date for Linear tickets (YYYY-MM-DD).
        send_to_slack: If True, send the release notes to Slack.
    """
    # Import the Linear fetching and filtering from existing bot
    from changelog_bot import fetch_completed_issues, filter_customer_worthy, load_last_run

    print("=" * 60)
    print("CUSTOMER-SPECIFIC RELEASE NOTES GENERATOR")
    print("=" * 60)

    # Get the date range - prefer explicit since_date, then last_run, then 7 days ago
    if since_date:
        since = since_date
    else:
        last_run = load_last_run()
        since = last_run if last_run else (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    print(f"\nFetching completed tickets since {since}...")
    issues = fetch_completed_issues(since)
    print(f"Found {len(issues)} completed tickets.")

    if not issues:
        print("No tickets to process.")
        return

    # Filter for customer-worthy items
    print("\nFiltering for customer-worthy items...")
    categorized = filter_customer_worthy(issues)
    features = categorized.get("features", [])
    fixes = categorized.get("fixes", [])

    print(f"Found {len(features)} features and {len(fixes)} fixes.")

    if not features and not fixes:
        print("No customer-worthy items found.")
        return

    if customer_name:
        # Customer-specific flow
        print(f"\n{'=' * 60}")
        print(f"GENERATING TAILORED NOTES FOR: {customer_name.upper()}")
        print("=" * 60)

        # Find customer meetings
        print(f"\nSearching Granola for {customer_name} meetings (last {days_back} days)...")
        meetings = find_customer_meetings(customer_name, days_back)
        print(f"Found {len(meetings)} meetings with notes.")

        if meetings:
            for m in meetings:
                print(f"  - {m['title']} ({m['date']})")

        # Extract customer context
        print("\nExtracting customer context from meeting notes...")
        customer_context = extract_customer_context(meetings, customer_name)

        print("\n--- CUSTOMER CONTEXT ---")
        print(customer_context)

        # Generate tailored notes
        print("\n\nGenerating tailored release notes...")
        meeting_notes = "\n\n".join([m['notes'] for m in meetings])

        release_notes = generate_tailored_release_notes(
            features=features,
            fixes=fixes,
            customer_name=customer_name,
            customer_context=customer_context,
            meeting_notes_summary=meeting_notes[:3000]  # Truncate if too long
        )
    else:
        # Generic flow
        print("\n" + "=" * 60)
        print("GENERATING GENERIC RELEASE NOTES")
        print("=" * 60)
        release_notes = generate_generic_release_notes(features, fixes)

    print("\n" + "=" * 60)
    print("FINAL OUTPUT")
    print("=" * 60)
    print(f"\n{release_notes}\n")

    # Send to Slack if requested
    if send_to_slack:
        import requests
        slack_webhook = os.getenv("SLACK_WEBHOOK_URL")

        if not slack_webhook:
            print("⚠️  No SLACK_WEBHOOK_URL configured, skipping Slack")
        else:
            print("=" * 60)
            print("SENDING TO SLACK...")
            print("=" * 60)

            # Add header based on whether this is customer-specific
            today = datetime.now().strftime('%Y-%m-%d')
            if customer_name:
                header = f"🚀 *Product Updates for {customer_name.upper()}* ({since} → {today})\n{'─' * 40}\n\n"
            else:
                header = f"🚀 *Product Updates* ({since} → {today})\n{'─' * 40}\n\n"

            full_message = header + release_notes

            try:
                response = requests.post(
                    slack_webhook,
                    json={"text": full_message, "unfurl_links": False, "unfurl_media": False}
                )
                if response.status_code == 200:
                    print("✅ Successfully sent to Slack!")
                else:
                    print(f"❌ Slack error: {response.status_code} - {response.text}")
            except Exception as e:
                print(f"❌ Failed to send to Slack: {e}")

    return release_notes


if __name__ == "__main__":
    import sys

    # Parse command line args
    customer = None
    days = 30
    since = None
    send_slack = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--customer" and i + 1 < len(args):
            customer = args[i + 1]
            i += 2
        elif arg == "--days" and i + 1 < len(args):
            days = int(args[i + 1])
            i += 2
        elif arg == "--since" and i + 1 < len(args):
            since = args[i + 1]
            i += 2
        elif arg == "--slack":
            send_slack = True
            i += 1
        elif not arg.startswith("--"):
            # Positional arg - treat as customer name
            customer = arg
            i += 1
        else:
            i += 1

    main(customer_name=customer, days_back=days, since_date=since, send_to_slack=send_slack)
