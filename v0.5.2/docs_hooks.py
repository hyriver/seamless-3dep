"""Hooks for the documentation."""

from __future__ import annotations

import pathlib
from pathlib import Path
from typing import TYPE_CHECKING

from mkdocs.structure.files import File, Files

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

# ---------------------------------------------------------------------------
# Monkeypatch mkdocs-jupyter's ``should_include`` so that ``.md`` files
# that are *not* in the ``include`` glob list are rejected **before**
# ``jupytext.read()`` is called.  Without this, jupytext invokes Pandoc
# (``--from markdown --to ipynb``) for every ``.md`` file it encounters
# and Pandoc emits dozens of "unclosed Div" warnings for files that
# contain HTML or mkdocstrings ``:::`` directives.
# ---------------------------------------------------------------------------
try:
    from mkdocs_jupyter.plugin import Plugin as _JupyterPlugin

    _orig_should_include = _JupyterPlugin.should_include

    def _patched_should_include(self, file):  # type: ignore[override]
        ext = pathlib.PurePath(file.abs_src_path).suffix
        if ext == ".md":
            srcpath = pathlib.PurePath(file.abs_src_path)
            if not any(srcpath.match(p) for p in self.config["include"]):
                return False
        return _orig_should_include(self, file)

    _JupyterPlugin.should_include = _patched_should_include
except ImportError:
    pass

_ROOT = Path(__file__).parent.parent

changelog = _ROOT / "CHANGELOG.md"
contributing = _ROOT / "CONTRIBUTING.md"
readme = _ROOT / "README.md"
license = _ROOT / "LICENSE"


def on_files(files: Files, config: MkDocsConfig) -> Files:
    """Add root-level markdown files to the documentation site."""
    for path in (changelog, contributing, readme):
        files.append(
            File(
                path=path.name,
                src_dir=str(path.parent),
                dest_dir=str(config.site_dir),
                use_directory_urls=config.use_directory_urls,
            )
        )
    lic = File(
        path="LICENSE.md",
        src_dir=str(license.parent),
        dest_dir=str(config.site_dir),
        use_directory_urls=config.use_directory_urls,
    )
    lic.abs_src_path = str(license)
    files.append(lic)
    return files
