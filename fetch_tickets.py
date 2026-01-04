import os
import json
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("LINEAR_API_KEY")
GRAPHQL_URL = "https://api.linear.app/graphql"

def run_query(query, variables=None):
    """Execute a GraphQL query against Linear API."""
    response = requests.post(
        GRAPHQL_URL,
        headers={"Authorization": API_KEY},
        json={"query": query, "variables": variables or {}}
    )
    return response.json()

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
                state {
                    name
                }
                team {
                    name
                }
                project {
                    name
                }
                labels {
                    nodes {
                        name
                    }
                }
            }
        }
    }
    """

    result = run_query(query, {"since": since_date})
    return result.get("data", {}).get("issues", {}).get("nodes", [])

def main():
    # Default: look at tickets completed in the last 30 days
    since_date = datetime.now() - timedelta(days=30)
    since = since_date.strftime("%Y-%m-%d")

    print(f"Fetching tickets completed since {since}...\n")

    issues = fetch_completed_issues(since)

    if not issues:
        print("No completed tickets found in this time period.")
        return

    print(f"Found {len(issues)} completed tickets:\n")
    print("-" * 60)

    for issue in issues:
        project = issue.get("project", {})
        project_name = project.get("name") if project else "No Project"
        team = issue.get("team", {}).get("name", "Unknown")
        labels = [l["name"] for l in issue.get("labels", {}).get("nodes", [])]

        print(f"Title: {issue['title']}")
        print(f"Team: {team} | Project: {project_name}")
        if labels:
            print(f"Labels: {', '.join(labels)}")
        print(f"Updated: {issue['updatedAt'][:10]}")
        if issue.get("description"):
            desc = issue["description"][:150]
            if len(issue["description"]) > 150:
                desc += "..."
            print(f"Description: {desc}")
        print("-" * 60)

if __name__ == "__main__":
    main()
