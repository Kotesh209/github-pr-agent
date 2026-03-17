import argparse
import os
import sys
import urllib3
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

# Disable SSL warnings for corporate network
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv()

# Force UTF-8 output for Windows terminal
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

console = Console(highlight=False)

def main():
    parser = argparse.ArgumentParser(
        description="GitHub PR Agent - Find similar PRs and summarize reviewer feedback"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pr", type=int, help="PR number to analyze")
    group.add_argument("--feature", type=str, help="Feature description to search for")

    parser.add_argument(
        "--repo",
        type=str,
        default=os.getenv("GITHUB_REPO", "microsoft/vscode"),
        help="GitHub repo in owner/repo format (default: microsoft/vscode)"
    )
    parser.add_argument(
        "--max",
        type=int,
        default=5,
        help="Max number of similar PRs to analyze (default: 5)"
    )

    args = parser.parse_args()

    from github_client import get_pr, collect_all_feedback
    from similarity import find_similar_prs
    from summarizer import summarize

    console.print(Rule("[bold blue]GitHub PR Agent[/bold blue]"))
    console.print(f"[cyan]Repository:[/cyan] {args.repo}")

    # Step 1: Get context
    pr_data = None
    context_description = ""

    if args.pr:
        console.print(f"[cyan]Analyzing PR:[/cyan] #{args.pr}")
        console.print("\n[yellow]Step 1: Fetching PR details...[/yellow]")
        try:
            pr_data = get_pr(args.repo, args.pr)
            context_description = f"PR #{args.pr}: {pr_data['title']}"
            console.print(f"  [green]OK[/green] Found: {pr_data['title']}")
            console.print(f"  [green]OK[/green] State: {pr_data['state']}")
            console.print(f"  [green]OK[/green] Author: {pr_data['user']['login']}")
        except Exception as e:
            console.print(f"  [red]FAILED - Could not fetch PR #{args.pr}: {e}[/red]")
            sys.exit(1)
    else:
        context_description = args.feature
        console.print(f"[cyan]Feature:[/cyan] {args.feature}")

    # Step 2: Find similar PRs
    console.print("\n[yellow]Step 2: Finding similar past PRs...[/yellow]")
    try:
        similar_prs = find_similar_prs(
            args.repo,
            pr_data=pr_data,
            feature_description=args.feature if not pr_data else None,
            max_results=args.max
        )
        if not similar_prs:
            console.print("  [red]No similar PRs found.[/red]")
            sys.exit(0)
        console.print(f"  [green]OK[/green] Found {len(similar_prs)} similar PRs:")
        for pr in similar_prs:
            console.print(f"    - PR #{pr['number']}: {pr['title'][:70]}")
    except Exception as e:
        console.print(f"  [red]FAILED - Error finding similar PRs: {e}[/red]")
        sys.exit(1)

    # Step 3: Collect all feedback
    console.print("\n[yellow]Step 3: Collecting all feedback from similar PRs...[/yellow]")
    similar_prs_feedback = []
    for pr in similar_prs:
        pr_number = pr["number"]
        console.print(f"  Fetching feedback for PR #{pr_number}: {pr['title'][:50]}...")
        try:
            feedback = collect_all_feedback(args.repo, pr_number)
            total = (
                len(feedback["reviews"]) +
                len(feedback["review_comments"]) +
                len(feedback["issue_comments"]) +
                len(feedback["commit_comments"])
            )
            console.print(f"  [green]OK[/green] {total} feedback items collected")
            if total > 0:
                similar_prs_feedback.append({
                    "pr_number": pr_number,
                    "pr_title": pr["title"],
                    "pr_url": pr["url"],
                    "feedback": feedback
                })
        except Exception as e:
            console.print(f"  [red]FAILED - Could not fetch feedback for PR #{pr_number}: {e}[/red]")

    if not similar_prs_feedback:
        console.print("\n[red]No feedback found in any similar PRs.[/red]")
        sys.exit(0)

    # Step 4: Summarize with QGenie
    console.print(f"\n[yellow]Step 4: Summarizing with AI ({os.getenv('MODEL', 'anthropic::claude-sonnet-4-6')})...[/yellow]")
    try:
        summary = summarize(context_description, similar_prs_feedback)
    except Exception as e:
        console.print(f"  [red]FAILED - AI summarization failed: {e}[/red]")
        sys.exit(1)

    # Step 5: Print the report
    console.print("\n")
    console.print(Rule("[bold green]AI Summary Report[/bold green]"))
    console.print(Panel(
        summary,
        title=f"[bold]Reviewer Expectations for: {context_description[:60]}[/bold]",
        border_style="green",
        padding=(1, 2)
    ))

    console.print(Rule())
    console.print("\n[cyan]Similar PRs analyzed:[/cyan]")
    for item in similar_prs_feedback:
        console.print(f"  - PR #{item['pr_number']}: {item['pr_title'][:70]}")
        console.print(f"    {item['pr_url']}")

    console.print("\n[bold green]Done![/bold green]")

if __name__ == "__main__":
    main()
