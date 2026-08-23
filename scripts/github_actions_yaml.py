"""Parse GitHub Actions workflow YAML without coercing the ``on`` key to bool.

PyYAML's default implicit resolvers treat YAML 1.1 booleans ``on``/``off``
as ``True``/``False``, which would drop the workflow trigger mapping.
GitHub Actions keeps ``on`` as a string key. This loader matches that
behavior while still parsing ``true``/``false`` as booleans.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_TRUE_FALSE_BOOL = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class GitHubActionsLoader(yaml.SafeLoader):
    """SafeLoader that does not implicitly resolve ``on``/``off``/``yes``/``no``."""


def _install_github_actions_bool_resolver() -> None:
    preserved: dict[Any, list[tuple[str, Any]]] = {}
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items():
        kept = [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"]
        if kept:
            preserved[first] = kept
    GitHubActionsLoader.yaml_implicit_resolvers = preserved
    GitHubActionsLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        _TRUE_FALSE_BOOL,
        list("tTfF"),
    )


_install_github_actions_bool_resolver()


def load_github_actions_yaml(text: str) -> Any:
    """Parse a GitHub Actions workflow document. Raises ``yaml.YAMLError`` on malformed input."""

    return yaml.load(text, Loader=GitHubActionsLoader)


def load_github_actions_yaml_file(path: Path) -> Any:
    return load_github_actions_yaml(path.read_text(encoding="utf-8"))
