
# llm-commit

[LLM](https://llm.datasette.io/) plugin for generating Git commit messages using an LLM.

**Note**: This project is a fork of the original [GNtousakis/llm-commit](https://github.com/GNtousakis/llm-commit) repository, which appears to be unmaintained. This fork integrates all pending pull requests from the original project while adding new fixes and features.

## Prerequisites & Dependencies

- [LLM](https://llm.datasette.io/) must be installed (this plugin runs within LLM).
- Python 3.7+ is recommended.

## Installation

Install this plugin in the same environment as LLM.

```bash
llm install llm-commit
```

For ease of use, it is also recommended to integrate llm-commit as a git alias.
To do this, modify the `~/.gitconfig` file and add a new line at the end of the
`[alias]` section:

```ini
[alias]
    # ...
    llmcommit = !llm commit --semantic --model 4o --max-tokens 1000
```

## Usage

The plugin adds a new command, `llm commit`. This command generates a commit message from your staged Git diff and then commits the changes.

For example, to generate and commit changes:

```bash
# Stage your changes first
git add .

# Generate and commit with an LLM-generated commit message
llm commit
```

You can also customize options:

```bash
# Enforce a specific commit style
llm commit --semantic
llm commit --conventional

# Skip the confirmation prompt
llm commit --yes

# Use a different LLM model, adjust max tokens, or change the temperature
llm commit --model gpt-4 --max-tokens 150 --temperature 0.8

# Control diff truncation behavior
llm commit --truncation-limit 2000  # Truncate diffs longer than 2000 characters
llm commit --no-truncation         # Never truncate diffs (use with caution on large changes)
```

## Configuration

To avoid repeating parameters on the command line, you can set defaults
settings throught environment variables:

| Environment variable           | Description                                                                       |
| ---                            | ---                                                                               |
| `LLM_COMMIT_STYLE`             | Sets the default commit style (e.g., conventional, semantic). <br/>Default: none. |
| `LLM_COMMIT_MODEL`             | Overrides the default model used for generation. <br/>Default: same as LLM        |
| `LLM_COMMIT_MAX_TOKENS`        | Sets the default maximum tokens. <br/>Default: ???                                |
| `LLM_COMMIT_TRUNCATION_LIMIT`  | Truncate diffs longer than the specified number of characters. <br/>Default: ???  |
| `LLM_COMMIT_SKIP_CONFIRMATION` | Skip the confirmation prompt. <br/>Default: `false`.                              |

Example:

```bash
export LLM_COMMIT_STYLE=conventional
llm commit
```

## Development (Building from Source)

To set up this plugin locally, first check out the code. Then create a new virtual environment:

```bash
cd llm-commit
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

## Contributors

- Original author (before the fork): Grigoris Ntousakis (GNtousakis)  
- Current maintainer: Glenn Rolland (glenux)

## License

This plugin is licensed under the terms of the MIT license.  

<!-- See the SPDX header in the repository for more details. -->
