import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("LINEAR_API_KEY")

def run_query(query):
    response = requests.post(
        "https://api.linear.app/graphql",
        headers={"Authorization": API_KEY},
        json={"query": query}
    )
    return response.json()

# Check teams
print("=== Teams ===")
result = run_query("{ teams { nodes { id name } } }")
teams = result.get("data", {}).get("teams", {}).get("nodes", [])
for t in teams:
    print(f"  - {t['name']}")

# Check workflow states
print("\n=== Workflow States (first team) ===")
if teams:
    result = run_query("""{ workflowStates { nodes { name type } } }""")
    states = result.get("data", {}).get("workflowStates", {}).get("nodes", [])
    for s in states:
        print(f"  - {s['name']} ({s['type']})")

# Check recent issues (any state)
print("\n=== Recent Issues (any state, last 100) ===")
result = run_query("""{
    issues(first: 10, orderBy: updatedAt) {
        nodes {
            title
            state { name type }
            completedAt
        }
    }
}""")
issues = result.get("data", {}).get("issues", {}).get("nodes", [])
if not issues:
    print("  No issues found at all")
else:
    for i in issues:
        state = i.get("state", {})
        completed = i.get("completedAt", "not completed")
        print(f"  - {i['title'][:50]}")
        print(f"    State: {state.get('name')} ({state.get('type')}) | Completed: {completed}")
