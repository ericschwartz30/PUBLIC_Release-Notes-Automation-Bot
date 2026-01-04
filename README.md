# AI-Powered Release Notes Bot

Automatically generate customer-facing release notes from your Linear tickets using Claude AI. This bot filters completed tickets, intelligently categorizes them as features or fixes, groups related work, and drafts polished release notes ready to send to customers.

## Features

- **Intelligent Filtering**: Uses Claude to automatically identify which tickets are customer-worthy
- **Smart Categorization**: Distinguishes between features, bug fixes, and internal work
- **Automatic Grouping**: Combines related tickets into cohesive feature announcements
- **Two Modes**:
  - **Generic notes**: For all customers (can run via GitHub Actions)
  - **Customer-specific notes**: Tailored to individual customers using meeting notes from Granola
- **Slack Integration**: Automatically post release notes to Slack channels
- **Stateful**: Remembers the last run to avoid duplicate announcements

## How It Works

1. **Fetch**: Pulls completed tickets from Linear since the last run
2. **Filter**: Claude analyzes each ticket to determine if it's customer-worthy
3. **Categorize**: Separates features from bug fixes and quality-of-life improvements
4. **Group**: Combines related tickets into single feature announcements
5. **Draft**: Generates polished, customer-friendly release notes
6. **Send**: Posts to Slack (optional)

## Quick Start

### Prerequisites

- Python 3.11+
- [Linear](https://linear.app) account with API access
- [Anthropic](https://anthropic.com) API key
- (Optional) [Slack](https://slack.com) webhook URL
- (Optional) [Granola](https://granola.so) for customer-specific notes

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/release-notes-bot.git
   cd release-notes-bot
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

4. **IMPORTANT**: Customize the prompts for your company:
   - Open `changelog_bot.py`
   - Search for `CUSTOMIZATION GUIDE` comments
   - Fill in your company context, team structure, and product details
   - See [Customization Guide](#customization-guide) below

### Running the Bot

**Generate generic release notes:**
```bash
python changelog_bot.py
```

**Generate customer-specific notes:**
```bash
# Preview only
python customer_release_notes.py CUSTOMER_NAME --since 2025-01-01

# Send to Slack
python customer_release_notes.py CUSTOMER_NAME --since 2025-01-01 --slack
```

## Customization Guide

This bot is designed to be highly customizable to match your company's workflow and voice. **You MUST customize the prompts** for best results.

### 1. Edit the Filtering Prompt

In `changelog_bot.py`, find the `filter_customer_worthy()` function and customize:

- **Linear setup**: Describe your initiatives, projects, and teams
- **Engineer context**: List your team members and their typical work
- **Product patterns**: Define what makes a ticket customer-worthy for YOUR product
- **Examples**: Add specific examples from your domain

### 2. Edit the Grouping Prompt

In `group_related_tickets()`, customize how tickets should be grouped based on how YOUR customers think about features.

### 3. Edit the Drafting Prompt

In `draft_release_notes()`, customize:
- Product description
- Brand voice and tone
- Formatting preferences
- Example release notes in your style

### 4. Add Customer Aliases

In `customer_release_notes.py`, update the `CUSTOMER_ALIASES` dict with your customer names and how they appear in Granola folders.

### Tips for Great Prompts

- **Be specific**: The more context you give Claude about your team and product, the better the results
- **Use examples**: Show Claude what good categorization looks like for your specific tickets
- **Iterate**: Run the bot, see what it gets wrong, and refine the prompts
- **Engineer names**: Including engineer names and their typical work patterns helps a lot

## GitHub Actions Setup

Automate release notes generation with GitHub Actions:

1. Add secrets to your repository:
   - `LINEAR_API_KEY`
   - `ANTHROPIC_API_KEY`
   - `SLACK_WEBHOOK_URL`

2. Enable the workflow in `.github/workflows/changelog.yml` by uncommenting the schedule trigger

3. The bot will run automatically on your schedule and post to Slack

## Architecture

```
┌──────────────┐
│   Linear     │  Fetch completed tickets
│   GraphQL    │  since last run
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  Filter (Claude)                                     │
│  • Analyze each ticket                              │
│  • Decide: feature / fix / exclude                  │
│  • Use company context and patterns                 │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  Group (Claude)                                      │
│  • Combine related tickets                          │
│  • Create customer-friendly feature names           │
│  • Separate standalone fixes                        │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  Draft (Claude)                                      │
│  • Write customer-facing descriptions               │
│  • Explain benefits, not just features              │
│  • Match company brand voice                        │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   Slack      │  Post formatted notes
│   Webhook    │  with date range
└──────────────┘
```

## Customer-Specific Notes

The bot can generate tailored release notes for specific customers by:

1. Finding recent meetings with that customer from Granola
2. Extracting pain points, feature requests, and interests
3. Emphasizing relevant features and skipping irrelevant ones
4. Using customer-specific language and examples
5. Crediting individuals who requested features

**Requirements:**
- Granola app installed with meeting notes
- Customer folders organized in Granola
- Customer aliases configured in `customer_release_notes.py`

**Example:**
```bash
python customer_release_notes.py "ACME Corp" --since 2025-01-01 --days 60 --slack
```

This will:
- Find all meetings with ACME Corp in the last 60 days
- Analyze their pain points and requests
- Generate notes highlighting features that matter to them
- Send to Slack if `--slack` flag is used

## File Structure

```
.
├── changelog_bot.py              # Main bot (generic notes)
├── customer_release_notes.py     # Customer-specific notes
├── fetch_tickets.py              # Standalone ticket fetcher
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .changelog_state.json         # Tracks last run timestamp
├── .github/
│   └── workflows/
│       └── changelog.yml         # GitHub Actions workflow
└── CLAUDE.md                     # Instructions for Claude Code
```

## API Usage

This bot uses Claude Opus 4.5 (with extended thinking) for all three stages. Typical API costs per run:
- **Small batch** (10-20 tickets): ~$0.20-0.40
- **Medium batch** (30-50 tickets): ~$0.50-1.00
- **Large batch** (100+ tickets): ~$1.50-3.00

Costs scale with the number of tickets and complexity of descriptions.

## Tips & Tricks

### Adjust the Date Range

Override the start date:
```bash
START_DATE=2025-01-01 python changelog_bot.py
```

Or edit `.changelog_state.json` to change the last run timestamp.

### Preview Without Sending to Slack

Just run the bot - it prints to the terminal. To send to Slack, ensure `SLACK_WEBHOOK_URL` is set in `.env`.

### Skip Customer-Specific Setup

If you don't use Granola or don't need customer-specific notes, you can ignore `customer_release_notes.py` entirely. Just use `changelog_bot.py`.

### Iterate on Prompts Quickly

1. Run the bot once to generate tickets
2. Edit the prompts in the code
3. Re-run to see how the output changes
4. Repeat until you're happy with the results

### Debug Linear Connection

Use the included debug scripts:
```bash
python debug_linear.py          # Test Linear API connection
python fetch_tickets.py         # Fetch and display tickets
```

## Contributing

Contributions welcome! Feel free to:
- Open issues for bugs or feature requests
- Submit PRs with improvements
- Share your customization patterns

## License

MIT License - feel free to use this for your company's release notes!

## Credits

Built for internal use and open-sourced for the community.

Powered by:
- [Anthropic Claude](https://anthropic.com) - AI for filtering, grouping, and drafting
- [Linear](https://linear.app) - Issue tracking
- [Granola](https://granola.so) - Meeting notes (optional)

---

**Questions?** Open an issue or reach out on Twitter.
