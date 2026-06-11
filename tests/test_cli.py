import pytest

from sbox_cli import cli


def test_parse_args_without_arguments_enters_existing_sandbox():
    assert cli.parse_args([]) == {
        "mode": "enter",
        "docker_opts": [],
        "sbox_name": None,
        "sbox_ro": False,
        "sbox_worktree": None,
        "image": None,
        "cmd": [],
    }


def test_parse_args_ls_mode():
    assert cli.parse_args(["ls"])["mode"] == "ls"


def test_parse_args_create_mode_with_sbox_and_docker_options():
    assert cli.parse_args(
        [
            "--sbox-ro",
            "--sbox-worktree",
            "feature-auth",
            "--sbox-name=auth-agent",
            "-p",
            "127.0.0.1:8000:8000",
            "python:3.12",
            "bash",
        ],
    ) == {
        "mode": "create",
        "docker_opts": ["-p", "127.0.0.1:8000:8000"],
        "sbox_name": "auth-agent",
        "sbox_ro": True,
        "sbox_worktree": "feature-auth",
        "image": "python:3.12",
        "cmd": ["bash"],
    }


def test_parse_args_requires_image_for_create_mode():
    with pytest.raises(SystemExit) as error:
        cli.parse_args(["--sbox-ro"])

    assert error.value.code == 2


def test_parse_args_rejects_unknown_sbox_options():
    with pytest.raises(SystemExit) as error:
        cli.parse_args(["--sbox-unknown", "python:3.12"])

    assert error.value.code == 2


def test_sanitize_helpers_make_docker_safe_components():
    assert cli.sanitize_component("Feature/Auth!", "fallback") == "feature-auth"
    assert cli.sanitize_component("!!!", "fallback") == "fallback"
    assert cli.sanitize_image("ghcr.io/acme/app:latest") == "ghcr.io-acme-app-latest"
    assert (
        cli.sanitize_hostname("sbox_repo.branch__python:3.12")
        == "sbox-repo-branch-python-3-12"
    )


def test_generated_name_uses_project_image_branch_and_date(monkeypatch):
    monkeypatch.setattr(cli, "today", lambda: "20260607")

    context = {
        "repo_or_dir": "shop-api",
        "branch": "feature-auth",
    }

    assert (
        cli.generated_name(context, "python:3.12")
        == "sbox-shop-api.feature-auth__python-3.12-20260607"
    )
