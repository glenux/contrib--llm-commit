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

def get_staged_diff():
    diff = run_git(["git", "diff", "--cached"])
    if not diff:
        logging.error("No staged changes. Use 'git add'.")
        sys.exit(1)
    if len(diff) > 4000:
        logging.warning("Diff is large; truncating to 4000 characters.")
        diff = diff[:4000] + "\n[Truncated]"
    return diff

def generate_commit_message(diff, model="gpt-3.5-turbo", max_tokens=100, temperature=0.7):
    import llm
    from llm.cli import get_default_model
    from llm import get_key
    # ... rest of the function
    prompt = (
        "Generate a concise and professional Git commit message based on the following diff. "
        "The commit message should include a one-line summary at the top, followed by bullet points "
        "for the key changes. Keep it short and include relevant details:\n\n" + diff
    )
    model_obj = llm.get_model(model or get_default_model())
    if model_obj.needs_key:
        model_obj.key = get_key("", model_obj.needs_key, model_obj.key_env_var)
    response = model_obj.prompt(
        prompt,
        system="You are an expert assistant specialized in creating concise, professional Git commit messages from code diffs. Provide a clear one-line summary followed by bullet points detailing key changes, using standard Git commit conventions.",
        max_tokens=max_tokens,
        temperature=temperature
    )
    return response.text().strip()

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

@llm.hookimpl
def register_commands(cli):
    import llm
    from llm.cli import get_default_model
    from llm import get_key
    # ... rest of the function
    @cli.command(name="commit")
    @click.option("-y", "--yes", is_flag=True, help="Commit without prompting")
    @click.option("--model", default="gpt-3.5-turbo", help="LLM model to use")
    @click.option("--max-tokens", type=int, default=100, help="Max tokens")
    @click.option("--temperature", type=float, default=0.3, help="Temperature")
    def commit_cmd(yes, model, max_tokens, temperature):
        if not is_git_repo():
            logging.error("Not a Git repository.")
            sys.exit(1)
        diff = get_staged_diff()
        message = generate_commit_message(diff, model=model, max_tokens=max_tokens, temperature=temperature)
        if confirm_commit(message, auto_yes=yes):
            commit_changes(message)
        else:
            logging.info("Commit aborted.")
            sys.exit(0)