import logging
import subprocess
import pytest
import llm_commit
from click.testing import CliRunner
from click import Group

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning,
                        module="pydantic._internal._config")


# Dummy subprocess.run for successful execution
def dummy_run_success(cmd, capture_output, text, check):
    class DummyCompletedProcess:
        def __init__(self):
            self.stdout = "dummy output"
        returncode = 0
        stderr = ""
    return DummyCompletedProcess()


# Dummy subprocess.run that raises an error
def dummy_run_failure(cmd, capture_output, text, check):
    raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="",
                                        stderr="error message")


# --- run_git Tests ---
def test_run_git_success(monkeypatch):
    monkeypatch.setattr(subprocess, "run", dummy_run_success)
    output = llm_commit.run_git(["git", "status"])
    assert output == "dummy output"


def test_run_git_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(subprocess, "run", dummy_run_failure)
    with pytest.raises(SystemExit) as exc_info:
        llm_commit.run_git(["git", "status"])
    assert exc_info.value.code == 1
    assert "Git error" in caplog.text


# --- is_git_repo Tests ---
def test_is_git_repo_true(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: None)
    assert llm_commit.is_git_repo() is True


def test_is_git_repo_false(monkeypatch):
    def failing_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])
    monkeypatch.setattr(subprocess, "run", failing_run)
    assert llm_commit.is_git_repo() is False


# --- get_staged_diff Tests ---
def test_get_staged_diff_success(monkeypatch):
    monkeypatch.setattr(llm_commit, "run_git", lambda cmd: "diff text")
    diff = llm_commit.get_staged_diff()
    assert diff == "diff text"


def test_get_staged_diff_empty(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(llm_commit, "run_git", lambda cmd: "")
    with pytest.raises(SystemExit) as exc_info:
        llm_commit.get_staged_diff()
    assert exc_info.value.code == 1
    assert "No staged changes" in caplog.text


def test_get_staged_diff_truncation(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    long_diff = "a" * 5000
    monkeypatch.setattr(llm_commit, "run_git", lambda cmd: long_diff)
    
    # Test default truncation
    diff = llm_commit.get_staged_diff()
    expected = "a" * 4000 + "\n[Truncated]"
    assert diff == expected
    assert "Diff is large" in caplog.text
    
    # Test custom truncation limit
    caplog.clear()
    diff = llm_commit.get_staged_diff(truncation_limit=2000)
    expected = "a" * 2000 + "\n[Truncated]"
    assert diff == expected
    assert "truncating to 2000 characters" in caplog.text

    # Test no truncation
    caplog.clear()
    diff = llm_commit.get_staged_diff(no_truncation=True)
    expected = "a" * 5000
    assert diff == expected
    assert "truncating" not in caplog.text


# --- generate_commit_message Tests ---
class DummyResponse:
    def text(self):
        return "Summary\n- Change 1\n- Change 2"


class DummyModel:
    needs_key = False

    def prompt(self, prompt, system, max_tokens, temperature):
        return DummyResponse()


class DummyModelWithKey:
    needs_key = True
    key_env_var = "OPENAI_API_KEY"

    def prompt(self, prompt, system, max_tokens, temperature):
        # For testing, ensure our prompt mentions a one-line summary if
        # desired.
        assert "concise and professional Git commit message" in prompt
        return DummyResponse()


def test_generate_commit_message_no_key(monkeypatch):
    monkeypatch.setattr(llm_commit.llm, "get_model",
                        lambda model: DummyModel())
    message = llm_commit.generate_commit_message("diff text")
    assert message == "Summary\n- Change 1\n- Change 2"


# --- commit_changes Tests ---
def dummy_run_commit_success(cmd, capture_output, text, check):
    class DummyCompletedProcess:
        def __init__(self):
            self.stdout = ""
        returncode = 0
        stderr = ""
    return DummyCompletedProcess()


def dummy_run_commit_failure(cmd, capture_output, text, check):
    raise subprocess.CalledProcessError(returncode=1, cmd=cmd, output="",
                                        stderr="commit error")


def test_commit_changes_success(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(subprocess, "run", dummy_run_commit_success)
    llm_commit.commit_changes("Test message")
    # Check for "Committed:" which matches the logged output.
    assert "Committed:" in caplog.text


def test_commit_changes_failure(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    monkeypatch.setattr(subprocess, "run", dummy_run_commit_failure)
    with pytest.raises(SystemExit) as exc_info:
        llm_commit.commit_changes("Test message")
    assert exc_info.value.code == 1
    assert "Commit failed" in caplog.text


# --- confirm_commit Tests ---
def test_confirm_commit_yes(monkeypatch):
    inputs = iter(["yes"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    result = llm_commit.confirm_commit("Test message", auto_yes=False)
    assert result is True


def test_confirm_commit_no(monkeypatch):
    inputs = iter(["no"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    result = llm_commit.confirm_commit("Test message", auto_yes=False)
    assert result is False


def test_confirm_commit_auto_yes():
    result = llm_commit.confirm_commit("Test message", auto_yes=True)
    assert result is True


def test_confirm_commit_invalid_then_yes(monkeypatch):
    inputs = iter(["blah", "yes"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    result = llm_commit.confirm_commit("Test message", auto_yes=False)
    assert result is True


# --- CLI Tests ---
def get_cli_group():
    # Create a simple Click group and register commands.
    cli = Group()
    llm_commit.register_commands(cli)
    return cli


def test_commit_cmd_full_flow_yes(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(llm_commit, "generate_commit_message", lambda *args,
                        **kwargs: "Test message")
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen", "--model", "test-model",
                                 "--max-tokens", "50", "--temperature", "0.5"])
    assert result.exit_code == 0
    assert "Commit message:" in result.output
    assert "Test message" in result.output


def test_commit_cmd_auto_yes(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(llm_commit, "generate_commit_message", lambda *args,
                        **kwargs: "Test message")
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen", "-y"])
    assert result.exit_code == 0
    assert "Commit message:" in result.output
    assert "Test message" in result.output


def test_commit_cmd_no(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(llm_commit, "generate_commit_message", lambda *args,
                        **kwargs: "Test message")
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "Commit aborted" in caplog.text


def test_commit_cmd_not_git_repo(monkeypatch, caplog):
    caplog.set_level(logging.ERROR)
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: False)
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 1
    assert "Not a Git repository" in caplog.text


def test_generate_commit_message_triple_backticks_removal(monkeypatch):
    # Dummy response that returns a commit message wrapped in triple backticks.
    class DummyResponseWithBackticks:
        def text(self):
            return "```\nSummary\n- Change 1\n- Change 2\n```"

    class DummyModelWithBackticks:
        needs_key = False

        def prompt(self, prompt, system, max_tokens, temperature):
            return DummyResponseWithBackticks()

    # Monkey-patch the llm.get_model to return our dummy model.
    monkeypatch.setattr(llm_commit.llm, "get_model",
                        lambda model: DummyModelWithBackticks())

    # Call the function to generate the commit message.
    message = llm_commit.generate_commit_message("diff text")

    assert "```" not in message
    assert "Summary" in message


def test_commit_cmd_env_style(monkeypatch):
    runner = CliRunner()

    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(
        llm_commit,
        "generate_commit_message",
        lambda diff, commit_style, *args,
        **kwargs: f"Commit message with style {commit_style}"
    )
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"],
                           env={'LLM_COMMIT_STYLE': 'semantic'})

    assert result.exit_code == 0
    assert "Commit message with style semantic" in result.output


def test_commit_cmd_env_style_overridden(monkeypatch):
    def test_commit_cmd_defaults_truncation_limit_from_env(monkeypatch):
        runner = CliRunner()
        monkeypatch.setenv("LLM_COMMIT_TRUNCATION_LIMIT", "3000")
        monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
        # For testing, simulate get_staged_diff to include the truncation limit
        # value:
        monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                            **kwargs: f"diff truncated at {kwargs.get('truncation_limit')}")
        monkeypatch.setattr(llm_commit, "generate_commit_message", lambda diff,
                            **kwargs: f"Diff: {diff}")
        monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
        monkeypatch.setattr("builtins.input", lambda _: "yes")

        cli = Group()
        llm_commit.register_commands(cli)
        result = runner.invoke(cli, ["commit-gen"])
        assert result.exit_code == 0
        assert "diff truncated at 3000" in result.output
    """
    Test that command-line flags (--semantic or --conventional) override the
    LLM_COMMIT_STYLE environment variable.
    """
    runner = CliRunner()

    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(
        llm_commit,
        "generate_commit_message",
        lambda diff, commit_style, *args,
        **kwargs: f"Commit message with style {commit_style}"
    )
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    monkeypatch.setenv('LLM_COMMIT_STYLE', 'semantic')

    cli = get_cli_group()

    result = runner.invoke(cli, ["commit-gen", "--conventional"])

    assert result.exit_code == 0
    assert "Commit message with style conventional" in result.output


def test_commit_cmd_default_style(monkeypatch):
    """
    Test that the default commit style is used when neither the
    LLM_COMMIT_STYLE environment variable nor command-line flags are set.
    """
    runner = CliRunner()

    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")
    monkeypatch.setattr(
        llm_commit,
        "generate_commit_message",
        lambda diff, commit_style, *args,
        **kwargs: f"Commit message with style {commit_style}"
    )
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")

    monkeypatch.delenv('LLM_COMMIT_STYLE', raising=False)

    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])

    assert result.exit_code == 0
    assert "Commit message with style default" in result.output


def test_commit_cmd_custom_truncation(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)

    def mock_get_staged_diff(*args, **kwargs):
        truncation_limit = kwargs.get('truncation_limit', 4000)
        return f"diff text truncated at {truncation_limit}"

    monkeypatch.setattr(llm_commit, "get_staged_diff", mock_get_staged_diff)
    monkeypatch.setattr(llm_commit, "generate_commit_message", lambda diff,
                        *args, **kwargs: f"Test message\n\n{diff}")
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen", "--truncation-limit", "2000"])
    assert result.exit_code == 0
    assert "diff text truncated at 2000" in result.output


def test_commit_cmd_no_truncation(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)

    def mock_get_staged_diff(*args, **kwargs):
        no_truncation = kwargs.get('no_truncation', False)
        return f"diff text {'not ' if no_truncation else ''}truncated"

    monkeypatch.setattr(llm_commit, "get_staged_diff", mock_get_staged_diff)
    monkeypatch.setattr(llm_commit, "generate_commit_message", lambda diff,
                        *args, **kwargs: f"Test message\n\n{diff}")
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen", "--no-truncation"])
    assert result.exit_code == 0
    assert "diff text not truncated" in result.output


def test_format_commit_message_wrapping():
    """
    Verify that format_commit_message properly wraps the body lines to <= 72
    chars.
    """
    long_body = (
        "This line is definitely going to exceed seventy-two characters in "
        "length, so it should be wrapped automatically. Additionally, we want "
        "to ensure that even long lines with multiple words get wrapped to "
        "separate lines if they exceed the limit, maintaining readability and "
        "following best practices."
    )
    raw_msg = f"Short subject\n\n{long_body}"
    formatted = llm_commit.format_commit_message(raw_msg)

    lines = formatted.split('\n')
    # The first line is the subject, which is short
    assert lines[0] == "Short subject", "Subject didn't match expected."

    # Check wrapping for each body line
    for line in lines[1:]:
        assert len(line) <= 72, f"Line in the body is too long: {line}"


def test_commit_cmd_defaults_model_from_env(monkeypatch):
    """
    Verify that the model taken from the LLM_COMMIT_MODEL environment variable
    is propagated to generate_commit_message when no explicit --model flag is
    supplied on the CLI.
    """
    runner = CliRunner()
    monkeypatch.setenv("LLM_COMMIT_MODEL", "env-model")
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")

    def mock_generate_commit_message(diff, *args, **kwargs):
        return f"Model: {kwargs.get('model')}"

    monkeypatch.setattr(llm_commit, "generate_commit_message",
                        mock_generate_commit_message)
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda *_: "yes")

    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "Model: env-model" in result.output


def test_commit_cmd_defaults_temperature_from_env(monkeypatch):
    """
    Verify that the temperature taken from the LLM_COMMIT_TEMPERATURE
    environment variable is propagated to generate_commit_message when no
    explicit --temperature flag is supplied on the CLI.
    """
    runner = CliRunner()
    monkeypatch.setenv("LLM_COMMIT_TEMPERATURE", "0.95")
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")

    def mock_generate_commit_message(diff, *args, **kwargs):
        return f"Temperature: {kwargs.get('temperature')}"

    monkeypatch.setattr(llm_commit, "generate_commit_message",
                        mock_generate_commit_message)
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda *_: "yes")

    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "Temperature: 0.95" in result.output
    """
    Verify that the max_tokens taken from the LLM_COMMIT_MAX_TOKENS environment
    variable is propagated to generate_commit_message when no explicit
    --max-tokens flag is supplied on the CLI.
    """
    runner = CliRunner()
    monkeypatch.setenv("LLM_COMMIT_MAX_TOKENS", "150")
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")

    def mock_generate_commit_message(diff, *args, **kwargs):
        return f"Max tokens: {kwargs.get('max_tokens')}"

    monkeypatch.setattr(llm_commit, "generate_commit_message",
                        mock_generate_commit_message)
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda *_: "yes")

    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "Max tokens: 150" in result.output


def test_commit_cmd_defaults_truncation_limit_from_env(monkeypatch):
    """
    Verify that the truncation limit taken from the LLM_COMMIT_TRUNCATION_LIMIT
    environment variable is propagated to generate_commit_message when no
    explicit --truncation-limit flag is supplied on the CLI.
    """
    runner = CliRunner()
    monkeypatch.setenv("LLM_COMMIT_TRUNCATION_LIMIT", "3000")
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff",
                        lambda *args,
                        **kwargs: f"diff truncated at {kwargs.get('truncation_limit')}")

    def mock_generate_commit_message(diff, *args, **kwargs):
        return f"Diff: {diff}"

    monkeypatch.setattr(llm_commit, "generate_commit_message",
                        mock_generate_commit_message)
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda *_: "yes")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "diff truncated at 3000" in result.output


def test_commit_cmd_defaults_hint_from_env(monkeypatch):
    """
    Verify that the hint taken from the LLM_COMMIT_HINT environment
    variable is propagated to generate_commit_message when no explicit
    --hint flag is supplied on the CLI.
    """
    runner = CliRunner()
    monkeypatch.setenv("LLM_COMMIT_HINT", "ma valeur")
    monkeypatch.setattr(llm_commit, "is_git_repo", lambda: True)
    monkeypatch.setattr(llm_commit, "get_staged_diff", lambda *args,
                        **kwargs: "diff text")

    def mock_generate_commit_message(diff, *args, **kwargs):
        return f"Hint: {kwargs.get('hint')}"

    monkeypatch.setattr(llm_commit, "generate_commit_message",
                        mock_generate_commit_message)
    monkeypatch.setattr(llm_commit, "commit_changes", lambda msg: None)
    monkeypatch.setattr("builtins.input", lambda *_: "yes")
    cli = get_cli_group()
    result = runner.invoke(cli, ["commit-gen"])
    assert result.exit_code == 0
    assert "Hint: ma valeur" in result.output

#
