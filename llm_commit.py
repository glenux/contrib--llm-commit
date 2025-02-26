import click
import sys
import os
import logging
import subprocess
from pathlib import Path
import llm

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def run_git(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError as e:
        logging.error("Git error: %s", e)
        sys.exit(1)

def is_git_repo():
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
        return True
    except subprocess.CalledProcessError:
        return False

def get_staged_diff(truncation_limit=4000, no_truncation=False):
    diff = run_git(["git", "diff", "--cached"])
    if not diff:
        logging.error("No staged changes. Use 'git add'.")
        sys.exit(1)
    if not no_truncation and len(diff) > truncation_limit:
        logging.warning(f"Diff is large; truncating to {truncation_limit} characters.")
        diff = diff[:truncation_limit] + "\n[Truncated]"
    return diff

def generate_commit_message(diff, commit_style=None, model=None, max_tokens=100, temperature=0.7):
    import llm
    from llm.cli import get_default_model
    from llm import get_key

    if commit_style == "semantic":
        style_description = (
            "Generate a Git commit message following the Semantic Commit "
            "Messages format: <type>[optional scope in parentheses]: <subject>.\n"
        )
    elif commit_style == "conventional":
        style_description = (
            "Generate a Git commit message following the Conventional Commits "
            "specification: <type>[optional scope in parentheses]: <description>.\n"
            "Include optional BREAKING CHANGE if applicable."
        )
    else:
        style_description = (
            "Generate a concise and professional Git commit message based on "
            "the following diff. The commit message should include a one-line "
            "summary at the top, followed by bullet points for the key "
            "changes. Keep it short and include relevant details."
        )

    prompt = (
        f"<commit-style>\n{style_description}\n</commit-style>\n"
        f"<diff>\n{diff}\n</diff>\n"
        f"<request>\nGenerate a Git commit title and commit message based on the above diff, following the specified commit style.\n</request>\n"
        f"<constraints>\n"
        f"* Use the {commit_style.capitalize()} Commit Messages format.\n"
        f"* Ensure the commit message is concise and follows professional standards.\n"
        f"* Ensure the subject is in present tense and concise.\n"
        f"* Avoid using markdown, HTML, or other syntax markers.\n"
        f"</constraints>"
    )
    model_obj = llm.get_model(model or get_default_model())
    if model_obj.needs_key:
        model_obj.key = get_key("", model_obj.needs_key, model_obj.key_env_var)
    response = model_obj.prompt(
        prompt,
        system=(
            "You are a professional developer with more than 20 years of "
            "experience. You're an expert at writing Git commit messages from "
            "code diffs. Focus on highlighting the added value of changes "
            "(meta-analysis, what could have happened without this change?), "
            "followed by bullet points detailing key changes (avoid "
            "paraphrasing). Use the specified commit Git style, while forbidding "
            "other syntax markers or tags (e.g., markdown, HTML, etc.)"
        ),
        max_tokens=max_tokens,
        temperature=temperature
    )
    return clean_message(response)

def commit_changes(message):
    try:
        subprocess.run(["git", "commit", "-s", "-m", message],
                       check=True, capture_output=True, text=True)
        logging.info("Committed:\n%s", message)
    except subprocess.CalledProcessError as e:
        logging.error("Commit failed: %s", e)
        sys.exit(1)

def confirm_commit(message, auto_yes=False):
    click.echo(f"Commit message:\n{message}\n")
    if auto_yes:
        return True
    while True:
        ans = input("Commit this message? (yes/no): ").strip().lower()
        if ans in ("yes", "y"):
            return True
        elif ans in ("no", "n"):
            return False
        click.echo("Please enter 'yes' or 'no'.")

def clean_message(message):
    message = message.text().strip()
    # Remove triple backticks at the beginning and end, if present
    if message.startswith("```") and message.endswith("```"):
        message = message[3:-3].strip()
    return message

@llm.hookimpl
def register_commands(cli):
    import llm
    from llm.cli import get_default_model
    from llm import get_key

    @cli.command(name="commit")
    @click.option("-y", "--yes", is_flag=True, help="Commit without prompting")
    @click.option("--model", help="LLM model to use")
    @click.option("--max-tokens", type=int, default=100, help="Max tokens")
    @click.option("--temperature", type=float, default=0.3, help="Temperature")
    @click.option("--truncation-limit", type=int, default=4000, help="Character limit for diff truncation")
    @click.option("--no-truncation", is_flag=True, help="Disable diff truncation. Can cause issues with large diffs")
    @click.option("--semantic", is_flag=True, help="Enforce Semantic Commit Messages format")
    @click.option("--conventional", is_flag=True, help="Enforce Conventional Commits format")
    def commit_cmd(yes, model, max_tokens, temperature, truncation_limit, no_truncation, semantic, conventional):
        if semantic and conventional:
            logging.error("Cannot use both --semantic and --conventional simultaneously.")
            sys.exit(1)
        if semantic:
            commit_style = "semantic"
        elif conventional:
            commit_style = "conventional"
        else:
            commit_style = "default"

        if not is_git_repo():
            logging.error("Not a Git repository.")
            sys.exit(1)
        diff = get_staged_diff(truncation_limit=truncation_limit, no_truncation=no_truncation)
        message = generate_commit_message(diff, commit_style, model=model, max_tokens=max_tokens, temperature=temperature)
        if confirm_commit(message, auto_yes=yes):
            commit_changes(message)
        else:
            logging.info("Commit aborted.")
            sys.exit(0)
