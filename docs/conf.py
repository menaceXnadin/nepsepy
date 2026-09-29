"""Sphinx configuration for nepsepy Read the Docs builds."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))

project = "nepsepy"
author = "nepsepy contributors"
copyright = "nepsepy contributors"
release = "1.0.2"
version = "1.0.2"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosectionlabel",
    "myst_parser",
]

# Accept both reST and Markdown sources. Existing generated docs
# (API.md, METHOD.md, nepse-api-catalog.md) are plain Markdown and are
# rendered via MyST.
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "tasklist",
]
myst_heading_anchors = 3

autodoc_member_order = "bysource"
autodoc_typehints = "signature"
autosectionlabel_prefix_document = True

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

templates_path = ["_templates"]
# Internal research notes (gitignored, not published).
exclude_patterns = [
    "_build",
    "Thumbs.db",
    ".DS_Store",
    "METHOD.md",
    "nepse-api-catalog.md",
]

html_theme = "sphinx_rtd_theme"
