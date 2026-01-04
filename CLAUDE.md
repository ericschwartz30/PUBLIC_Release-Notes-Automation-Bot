# Release Notes Bot - Claude Instructions

## Project Overview
This bot generates customer-facing release notes from Linear tickets. It has two modes:
- **Generic notes**: Run via GitHub Actions or locally with `changelog_bot.py`
- **Customer-specific notes**: Run locally with `customer_release_notes.py` (requires Granola meeting data)

## Key Workflows

### Sending to Slack
**Important**: If you've already generated release notes in the terminal and the user asks to send to Slack, DO NOT re-run the pipeline. Instead, take the output text and send it directly to the Slack webhook using a simple POST request. This saves time and API costs.

```python
import requests
webhook = "..."  # from .env
requests.post(webhook, json={"text": notes, "unfurl_links": False})
```

### Customer-Specific Notes
- Uses local Granola cache to find customer meeting notes
- Matches customer names via aliases in `CUSTOMER_ALIASES` dict
- Extracts pain points, requests, and context from meetings
- Tailors release notes to emphasize what matters to that customer

## Commands

```bash
# Generic (sends to Slack automatically)
python changelog_bot.py

# Customer-specific (preview only)
python customer_release_notes.py CUSTOMER_NAME --since 2025-12-15

# Customer-specific (send to Slack)
python customer_release_notes.py CUSTOMER_NAME --since 2025-12-15 --slack
```

## Customization Guide

### First-time setup
1. **Edit the prompts in `changelog_bot.py`**:
   - Search for "CUSTOMIZATION GUIDE" comments
   - Fill in your company context, team structure, and Linear setup
   - Describe your product and brand voice
   - Add examples of your specific feature patterns

2. **Edit `customer_release_notes.py`**:
   - Update `CUSTOMER_ALIASES` dict with your customer names
   - Map customer names to how they appear in your Granola folders

3. **Set up `.env` file** with your API keys:
   ```
   LINEAR_API_KEY=your_key_here
   ANTHROPIC_API_KEY=your_key_here
   SLACK_WEBHOOK_URL=your_webhook_here
   ```

4. **Test locally** before setting up automation:
   ```bash
   python changelog_bot.py
   ```

### Iterating on your prompts
The quality of your release notes depends on how well you customize the prompts. As you use the tool:
- Note when it incorrectly categorizes tickets
- Add those patterns to the CUSTOMIZATION sections
- Include engineer names and their typical work patterns
- Describe your specific features and how customers think about them

## Future Improvements

### Richer context when Granola notes are sparse
When there aren't many recent Granola meetings for a customer, pull context from other sources:
- **Notion**: Customer pages/docs for background context
- **Internal Slack channels**: Team discussions about the customer (what's broken, what they're waiting for)
- **External Slack channels**: Direct conversations with the customer team

Slack access is already available via MCP. Challenge is mapping customer names to channel names and filtering for relevant/recent messages.

### Feedback loop for refining notes
After generating notes locally, ask if the user wants to refine before sending. Accept feedback like "too formal", "emphasize X more", "remove the bug fixes section" and regenerate with that context. This is just a conversational pattern - no code changes needed.

### Interactive terminal UI
When running locally without specifying customer/date in the initial prompt, show an interactive prompt:
- Autocomplete for customer names (from alias list)
- Date picker or sensible defaults ("last 2 weeks")
- Confirmation before sending to Slack

Could use `questionary` or `inquirer` libraries, or simple `input()` prompts.

### Learn from edits over time
When the user asks for edits to release notes (e.g., "make it less formal", "emphasize X", "don't include Y"), store that feedback in a preferences file (e.g., `release_notes_style.md`). Include this context when generating future notes so the output improves over time and matches your voice/preferences without needing repeated instructions.

### Sub-agents for parallelization
Use sub-agents to speed up batch operations:

**Multi-customer runs**: Generate notes for multiple customers in parallel instead of sequentially (15-20 min → 5 min)

**Parallel context gathering**: When building customer context, fetch from all sources simultaneously:
```
┌─ Agent 1: Granola meetings ──┐
├─ Agent 2: Slack channels    ─┼→ Merge contexts → Draft notes
└─ Agent 3: Notion docs       ─┘
```
Each agent searches its source for customer-relevant info (pain points, requests, recent discussions) and returns structured context. Results merge into a single customer context blob before drafting. Cuts context gathering from ~35s sequential to ~15s parallel.

Main bottleneck is Claude API calls, so this helps most when doing independent work that can run concurrently.

### Other
- Zapier → Notion integration would allow customer-specific notes from GitHub Actions (removes local Granola dependency)
- Consider curated customer context files in repo as alternative to live Granola access
