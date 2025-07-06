# llm-commit-gen

[LLM](https://llm.datasette.io/) plugin for generating Git commit messages using an LLM.

## Installation

Install this plugin in the same environment as LLM.

```bash
llm install llm-commit-gen
```

## Usage

The plugin adds a new command, `llm commit-gen`. This command generates a commit message from your staged Git diff and then commits the changes.

For example, to generate and commit changes:

```bash
# Stage your changes first
git add .

# Generate and commit with an LLM-generated commit message
llm commit-gen
```

You can also customize options:

```bash
# Enforce a specific commit style
llm commit-gen --semantic
llm commit-gen --conventional

# Skip the confirmation prompt
llm commit-gen --yes

# Use a different LLM model, adjust max tokens, or change the temperature
llm commit-gen --model gpt-4 --max-tokens 150 --temperature 0.8

# Control diff truncation behavior
llm commit-gen --truncation-limit 2000  # Truncate diffs longer than 2000 characters
llm commit-gen --no-truncation         # Never truncate diffs (use with caution on large changes)
```

You can also set defaults for options:

```
# Set commit style via environment variable
export LLM_COMMIT_STYLE=conventional
llm commit-gen
```

## Development

To set up this plugin locally, first check out the code. Then create a new virtual environment:

```bash
cd llm-commit-gen
python3 -m venv venv
source venv/bin/activate
```

Now install the dependencies and test dependencies:

```bash
pip install -e '.[test]'
```

To run the tests:

```bash
python -m pytest
```
