"""Hooks for the documentation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from mkdocs.structure.files import File, Files

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig

changelog = Path(__file__).parent.parent / "CHANGELOG.md"
contributing = Path(__file__).parent.parent / "CONTRIBUTING.md"
readme = Path(__file__).parent.parent / "README.md"


def on_files(files: Files, config: MkDocsConfig):
    """Copy the schema to the site."""
    files.append(
        File(
            path=changelog.name,
            src_dir=changelog.parent,
            dest_dir=str(config.site_dir),
            use_directory_urls=config.use_directory_urls,
        )
    )
    files.append(
        File(
            path=contributing.name,
            src_dir=contributing.parent,
            dest_dir=str(config.site_dir),
            use_directory_urls=config.use_directory_urls,
        )
    )
    files.append(
        File(
            path=readme.name,
            src_dir=readme.parent,
            dest_dir=str(config.site_dir),
            use_directory_urls=config.use_directory_urls,
        )
    )
    return files
