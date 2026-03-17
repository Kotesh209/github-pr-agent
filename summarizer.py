import os
from dotenv import load_dotenv
from qgenie import QGenieClient

load_dotenv()


QGENIE_API_KEY = os.getenv("QGENIE_API_KEY")
MODEL = os.getenv("MODEL", "anthropic::claude-sonnet-4-6")

client = QGenieClient(
    
    api_key=QGENIE_API_KEY,
    verify=False
)

def build_feedback_text(pr_number, pr_title, feedback):
    """Build a readable text block from all feedback."""
    lines = []
    lines.append(f"PR #{pr_number}: {pr_title}")
    lines.append("=" * 60)

    if feedback["reviews"]:
        lines.append("\n--- REVIEWS ---")
        for r in feedback["reviews"]:
            lines.append(f"[{r['author']} - {r['state']}]: {r['body'][:500]}")

    if feedback["review_comments"]:
        lines.append("\n--- LINE COMMENTS ---")
        for c in feedback["review_comments"]:
            lines.append(f"[{c['author']} on {c['file']}:{c['line']}]: {c['body'][:500]}")

    if feedback["issue_comments"]:
        lines.append("\n--- THREAD COMMENTS ---")
        for c in feedback["issue_comments"]:
            lines.append(f"[{c['author']}]: {c['body'][:500]}")

    if feedback["commit_comments"]:
        lines.append("\n--- COMMIT COMMENTS ---")
        for c in feedback["commit_comments"]:
            lines.append(f"[{c['author']} on commit {c['sha']}]: {c['body'][:500]}")

    return "\n".join(lines)

def summarize(context_description, similar_prs_feedback):
    """
    Send all collected feedback to QGenie and get a summary.
    context_description: the new PR title or feature description
    similar_prs_feedback: list of dicts with pr_number, pr_title, feedback
    """

    # Build the full context
    feedback_blocks = []
    for item in similar_prs_feedback:
        block = build_feedback_text(
            item["pr_number"],
            item["pr_title"],
            item["feedback"]
        )
        feedback_blocks.append(block)

    all_feedback = "\n\n".join(feedback_blocks)

    if not all_feedback.strip():
        return "No feedback found in similar PRs to summarize."

    prompt = f"""You are a senior code reviewer assistant. 

A developer is working on: "{context_description}"

Below is feedback from similar past Pull Requests in the same repository.
Analyze all the feedback and provide:

1. **Key Themes** - What are the most common concerns reviewers raised?
2. **What Leads Expect** - What do senior reviewers/leads consistently look for?
3. **Common Mistakes** - What mistakes were flagged repeatedly?
4. **Recommendations** - What should the developer focus on before pushing/merging?
5. **Positive Patterns** - What approaches were praised?

--- FEEDBACK FROM SIMILAR PAST PRs ---
{all_feedback[:8000]}
--- END OF FEEDBACK ---

Provide a clear, actionable summary that helps the developer anticipate reviewer expectations."""

    messages = [
        {"role": "system", "content": "You are a helpful senior code reviewer assistant that analyzes PR feedback patterns."},
        {"role": "user", "content": prompt}
    ]

    response = client.chat(
        messages=messages,
        model=MODEL,
        temperature=0.3,
        max_tokens=2000
    )

    return response.choices[0].message.content


def summarize_feature_history(query, history_items, month=None, year=None):
    """Summarize version-to-version style history for a feature query."""
    if not history_items:
        return "No feature history items found for the selected query and time range."

    time_scope = f"{month:02d}/{year}" if month and year else "all available time"
    history_text = "\n".join(
        f"- PR #{item['number']}: {item['title']} (created: {item.get('created_at')}, updated: {item.get('updated_at')})"
        for item in history_items[:30]
    )

    prompt = f"""You are analyzing the evolution of a feature across repository pull requests.

Feature query: \"{query}\"
Time scope: {time_scope}

Below are matching PRs related to this feature:
{history_text}

Create a report with:
1. **Version-to-Version Changes** - How the feature evolved over time.
2. **January/Time Window Highlights** - Important updates in the requested period.
3. **Patterns** - Repeated areas of change.
4. **Impact Summary** - What a developer or reviewer should know.

Be concise, specific, and structured in markdown."""

    response = client.chat(
        messages=[
            {"role": "system", "content": "You summarize feature evolution across pull requests."},
            {"role": "user", "content": prompt}
        ],
        model=MODEL,
        temperature=0.2,
        max_tokens=1500
    )
    return response.choices[0].message.content


def summarize_review_insights(most_reviewed_prs, frequent_features):
    """Build a markdown report for historical review hotspots."""
    lines = ["## Historical Review Insights", ""]

    lines.append("### Most Reviewed / Most Visited PRs")
    if most_reviewed_prs:
        for pr in most_reviewed_prs:
            lines.append(
                f"- **PR #{pr['number']}**: {pr['title']}  "
                f"(feedback items: {pr['review_count']}, changed files: {pr['changed_files']})"
            )
    else:
        lines.append("- No reviewed PR data available.")

    lines.append("")
    lines.append("### Frequently Reviewed Features / Files")
    if frequent_features:
        for feature in frequent_features:
            lines.append(
                f"- **{feature['feature']}** reviewed in **{feature['review_frequency']}** recent PRs"
            )
            for example in feature.get("examples", []):
                lines.append(
                    f"  - Example: PR #{example['number']} - {example['title']}"
                )
    else:
        lines.append("- No frequent feature data available.")

    return "\n".join(lines)
