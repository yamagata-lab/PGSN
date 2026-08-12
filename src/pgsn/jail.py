"""Jail table for PGSN XML imports.

A *jail* is a named directory root.  XML documents reach files inside a jail
with an absolute-looking path whose first component is the jail name::

    <from file="/lib/security.xml" import="secureGoal"/>

Nothing outside a registered jail root can be named this way.  A jailed path is
resolved against the registered root and the result is verified to still lie
inside that root *after* symbolic links have been expanded, so a symlink
planted inside a jail cannot be used to escape it.

Jail names are deliberately restricted to ``[A-Za-z0-9_-]+`` so that a name can
never be confused with a path component such as ``..`` or with a drive letter.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping

__all__ = ["Jails", "JailError"]


class JailError(Exception):
    """Raised when a jail definition or a jailed path is rejected."""


_JAIL_NAME = re.compile(r"\A[A-Za-z0-9_-]+\Z")


def is_within(path: Path, root: Path) -> bool:
    """True if `path` is `root` itself or lies below it.

    Both arguments are expected to be fully resolved already.  `Path.parents`
    is used rather than `Path.is_relative_to` so the check does not depend on
    the newer API.
    """
    return path == root or root in path.parents


def _resolve_root(name: str, root: str | Path) -> Path:
    """Validate a jail root and return its fully resolved path."""
    try:
        resolved = Path(root).expanduser().resolve(strict=True)
    except FileNotFoundError:
        raise JailError(
            f"Jail {name!r}: no such directory: {str(root)!r}") from None
    except (OSError, RuntimeError) as exc:
        raise JailError(
            f"Jail {name!r}: cannot resolve {str(root)!r}: {exc}") from None
    if not resolved.is_dir():
        raise JailError(
            f"Jail {name!r}: not a directory: {str(root)!r}")
    return resolved


class Jails:
    """An immutable mapping from jail names to resolved directory roots.

    Construct from any mapping of name to path::

        Jails({"lib": "/opt/pgsn-lib", "proj": "./modules"})

    Roots are validated and resolved once, at construction time.  A `Jails`
    instance is the security boundary for XML imports: a document can only
    reach files below one of these roots.
    """

    __slots__ = ("_roots",)

    def __init__(self, roots: "Jails | Mapping[str, str | Path] | None" = None):
        if isinstance(roots, Jails):
            self._roots: dict[str, Path] = dict(roots._roots)
            return
        if roots is None:
            self._roots = {}
            return
        if not isinstance(roots, Mapping):
            raise JailError(
                f"Jails expects a mapping of name to path, got {type(roots).__name__}")
        table: dict[str, Path] = {}
        for name, root in roots.items():
            if not isinstance(name, str) or not _JAIL_NAME.match(name):
                raise JailError(
                    f"Invalid jail name: {name!r} "
                    "(only letters, digits, '_' and '-' are allowed)")
            table[name] = _resolve_root(name, root)
        self._roots = table

    # -------------------------------------------------------------- #
    # Mapping-like access
    # -------------------------------------------------------------- #

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._roots))

    def root_of(self, name: str) -> Path:
        """Return the root of the named jail, or raise `JailError`."""
        try:
            return self._roots[name]
        except KeyError:
            raise JailError(
                f"Unknown jail {name!r}. Registered jails: "
                f"{', '.join(self.names) or '(none)'}") from None

    def __contains__(self, name: object) -> bool:
        return name in self._roots

    def __iter__(self) -> Iterator[str]:
        return iter(self.names)

    def __len__(self) -> int:
        return len(self._roots)

    def __bool__(self) -> bool:
        return bool(self._roots)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Jails):
            return NotImplemented
        return self._roots == other._roots

    def __hash__(self) -> int:
        return hash(frozenset(self._roots.items()))

    def __repr__(self) -> str:
        body = ", ".join(f"{n}={str(self._roots[n])!r}" for n in self.names)
        return f"Jails({body})"

    # -------------------------------------------------------------- #
    # Path resolution
    # -------------------------------------------------------------- #

    def resolve(self, spec: str) -> tuple[Path, Path]:
        """Resolve a jailed path ``/name/sub/file.xml``.

        Returns the pair (jail root, resolved file).  Raises `JailError` if the
        path is malformed, names an unknown jail, escapes the jail root, or
        does not point at an existing file.
        """
        if not spec.startswith("/"):
            raise JailError(
                f"Not a jailed path: {spec!r} (expected '/<jail>/...')")
        if "\\" in spec:
            raise JailError(
                f"Unsafe file path: {spec!r} (backslashes are not allowed)")

        parts = PurePosixPath(spec).parts
        # PurePosixPath keeps a leading '//' as a single distinct root part.
        if not parts or parts[0] != "/":
            raise JailError(f"Unsafe file path: {spec!r}")
        if len(parts) < 3:
            raise JailError(
                f"Unsafe file path: {spec!r} "
                "(a jailed path must name a file inside the jail)")

        name, rest = parts[1], parts[2:]
        if ".." in rest:
            raise JailError(
                f"Unsafe file path: {spec!r} ('..' is not allowed in a jailed path)")

        root = self.root_of(name)
        try:
            candidate = root.joinpath(*rest).resolve()
        except (OSError, RuntimeError) as exc:
            raise JailError(f"Cannot resolve {spec!r}: {exc}") from None
        if not is_within(candidate, root):
            raise JailError(
                f"Unsafe file path: {spec!r} escapes jail {name!r}")
        if not candidate.is_file():
            raise JailError(f"No such file in jail {name!r}: {spec!r}")
        return root, candidate

    def containing_root(self, path: Path) -> Path | None:
        """Return the innermost jail root containing `path`, if any.

        Used to decide the confinement boundary of an entry document that was
        opened directly by path: if it happens to live inside a registered
        jail, that jail is its boundary.
        """
        best: Path | None = None
        for root in self._roots.values():
            if is_within(path, root):
                if best is None or len(root.parts) > len(best.parts):
                    best = root
        return best
