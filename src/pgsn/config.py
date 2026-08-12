"""Configuration for PGSN.

`Config` is an immutable settings object.  It is passed explicitly to the
loading functions::

    cfg = pgsn.Config(jails={"lib": "/opt/pgsn-lib"})
    term = pgsn.load_xml("main.xml", config=cfg)

`configure()` installs a process-wide default used whenever no configuration is
given.  That default is a convenience only, *not* a security boundary: what
confines an XML document is the `Jails` table carried by the `Config` actually
used for the call.  Untrusted input to PGSN is XML, and XML cannot reach these
functions, so a caller that can change the default could equally well open the
files directly.

New settings belong on `Config`.  Per-document traversal state (the current
directory, the confinement root, the import stack) does not: that lives in the
compiler and changes on every import.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from pgsn.jail import Jails

__all__ = ["Config", "configure", "get_config"]


class Config:
    """Immutable PGSN settings.

    Currently holds the jail table only; further settings are added as fields
    here so that callers keep passing a single `config=` argument.
    """

    __slots__ = ("_jails",)

    def __init__(self,
                 jails: "Jails | Mapping[str, str | Path] | None" = None):
        self._jails = jails if isinstance(jails, Jails) else Jails(jails)

    @property
    def jails(self) -> Jails:
        """The jail table confining XML imports."""
        return self._jails

    def replace(self, **changes) -> "Config":
        """Return a copy of this configuration with the given fields changed."""
        jails = changes.pop("jails", self._jails)
        if changes:
            raise TypeError(
                f"Unknown configuration field(s): {', '.join(sorted(changes))}")
        return Config(jails=jails)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Config):
            return NotImplemented
        return self._jails == other._jails

    def __hash__(self) -> int:
        return hash(self._jails)

    def __repr__(self) -> str:
        return f"Config(jails={self._jails!r})"


_default = Config()


def configure(config: "Config | None" = None, *,
              jails: "Jails | Mapping[str, str | Path] | None" = None) -> Config:
    """Install the default configuration and return it.

    Accepts either a ready-made `Config` or the individual settings::

        pgsn.configure(jails={"lib": "/opt/pgsn-lib"})
        pgsn.configure(pgsn.Config(jails=my_jails))

    This may be called more than once; each call replaces the default.
    """
    global _default
    if config is not None:
        if jails is not None:
            raise TypeError("pass either a Config or individual settings, not both")
        if not isinstance(config, Config):
            raise TypeError(f"expected a Config, got {type(config).__name__}")
        _default = config
    else:
        _default = Config(jails=jails)
    return _default


def get_config(config: "Config | None" = None) -> Config:
    """Return `config` if given, otherwise the installed default."""
    if config is None:
        return _default
    if not isinstance(config, Config):
        raise TypeError(f"expected a Config, got {type(config).__name__}")
    return config
