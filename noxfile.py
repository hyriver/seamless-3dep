"""Nox sessions."""

from __future__ import annotations

import nox

py39 = ["3.9"]
py313 = ["3.13"]
nox.options.sessions = (
    "pre-commit",
    "type-check",
    "tests",
)


@nox.session(name="pre-commit", python=py313)
def pre_commit(session: nox.Session) -> None:
    """Lint using pre-commit."""
    session.install("pre-commit")
    session.run(
        "pre-commit",
        "run",
        "--all-files",
        "--hook-stage=manual",
        *session.posargs,
    )


@nox.session(name="update-hooks", python=py313)
def update_hooks(session: nox.Session) -> None:
    """Update pre-commit hooks."""
    session.install("pre-commit")
    session.run("pre-commit", "autoupdate", *session.posargs)


@nox.session(python=py313)
def spell(session: nox.Session) -> None:
    """Fix spelling errors."""
    session.install("codespell")
    session.run("codespell", "-w", *session.posargs)


@nox.session(name="type-check", python=py313)
def type_check(session: nox.Session) -> None:
    """Run Pyright."""
    session.install(".")
    session.install("pyright")
    session.run("pyright")


@nox.session(python=py39, venv_backend="micromamba")
def tests(session: nox.Session) -> None:
    """Run the test suite."""
    session.conda_install("gdal", channel="conda-forge")
    session.install(".[test]")
    session.run("pytest", *session.posargs)
    session.notify("cover")


@nox.session(python=py313)
def cover(session: nox.Session) -> None:
    """Coverage analysis."""
    session.install("coverage[toml]")
    session.run("coverage", "report")
    session.run("coverage", "html")


@nox.session(python=py313)
def docs(session: nox.Session) -> None:
    """Coverage analysis."""
    session.install(".[docs]")
    session.run("mkdocs", "build", "--strict")
    session.run("mkdocs", "serve")
