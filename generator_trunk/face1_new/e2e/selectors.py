"""Typed access to the selector data kept outside the Page Object code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping


SELECTOR_FILE = Path(__file__).with_name("selectors.toml")


@dataclass(frozen=True)
class SelectorRegistry:
    """The single selector/label source used by Page Objects and contract tests."""

    data: Mapping[str, Any]

    @classmethod
    def load(cls, path: Path | str = SELECTOR_FILE) -> "SelectorRegistry":
        with Path(path).open("rb") as handle:
            data = tomllib.load(handle)
        if int(data.get("version", 0)) != 1:
            raise ValueError(f"unsupported Face 1 selector registry version: {data.get('version')!r}")
        return cls(data)

    def value(self, section: str, key: str) -> str:
        try:
            return str(self.data[section][key])
        except KeyError as exc:
            raise KeyError(f"unknown selector {section}.{key}") from exc

    def section(self, name: str) -> Mapping[str, Any]:
        try:
            value = self.data[name]
        except KeyError as exc:
            raise KeyError(f"unknown selector section {name!r}") from exc
        if not isinstance(value, Mapping):
            raise TypeError(f"selector section {name!r} is not a table")
        return value

    @property
    def tabs(self) -> Mapping[str, Any]:
        return self.section("tabs")

    @property
    def buttons(self) -> Mapping[str, Any]:
        return self.section("buttons")

    @property
    def fields(self) -> Mapping[str, Any]:
        return self.section("fields")

    def format(self, section: str, key: str, **values: object) -> str:
        return self.value(section, key).format(**values)


DEFAULT_SELECTORS = SelectorRegistry.load()
