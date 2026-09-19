"""Declarative descriptions of SMART's ``get <key>`` / ``set <key>=<value>`` settings.

Almost every command in the SMART RS-232 reference follows one convention. Rather
than writing a ``get_x`` / ``set_x`` / ``adjust_x`` trio per key, a driver *declares*
each setting once::

    class SmartUX60(SmartDevice):
        brightness = IntSetting("brightness", range(101), per_source=True)
        display_mode = EnumSetting("displaymode", DisplayMode)

Accessed on an **instance**, a setting gives typed ``get()`` / ``set()`` (and, for
integers, ``adjust()``) coroutines::

    await projector.brightness.set(65)
    await projector.display_mode.get()          # -> DisplayMode

Accessed on the **class**, it gives the declaration itself, which carries metadata
(``bounds``, ``enum``, ``max_length``, ``doc``) that a generic integration can use
to build UI without hand-written per-setting code. See
:meth:`SmartDevice.settings`.
"""

from __future__ import annotations

import ipaddress
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Generic, NoReturn, Protocol, Self, TypeVar, overload

from ..exceptions import UnexpectedResponseError
from ..source import Source

T = TypeVar("T")
E = TypeVar("E", bound=StrEnum)


# --------------------------------------------------------------------------- codecs


class Codec(ABC, Generic[T]):
    """Converts between a Python value and the text the device uses.

    :meth:`parse` and :meth:`format` raise :class:`ValueError` on bad input.
    """

    @abstractmethod
    def parse(self, raw: str) -> T: ...

    def format(self, value: T) -> str:
        return str(value)


class IntCodec(Codec[int]):
    def __init__(self, bounds: range | None = None) -> None:
        self.bounds: range | None = bounds

    def parse(self, raw: str) -> int:
        return int(raw.strip())

    def format(self, value: int) -> str:
        if self.bounds is not None and value not in self.bounds:
            raise ValueError(
                f"{value} is out of range (valid: {self.bounds.start} to {self.bounds.stop - 1})"
            )
        return str(value)


class BoolCodec(Codec[bool]):
    """Parses ``on``/``true`` and ``off``/``false``; writes ``on``/``off``."""

    def parse(self, raw: str) -> bool:
        text = raw.strip().lower()
        if text in ("on", "true"):
            return True
        if text in ("off", "false"):
            return False
        raise ValueError(f"expected on/off, got {raw!r}")

    def format(self, value: bool) -> str:
        return "on" if value else "off"


class StrCodec(Codec[str]):
    def __init__(self, max_length: int | None = None) -> None:
        self.max_length: int | None = max_length

    def parse(self, raw: str) -> str:
        return raw

    def format(self, value: str) -> str:
        if self.max_length is not None and len(value) > self.max_length:
            raise ValueError(f"value is longer than {self.max_length} characters")
        return value


class EnumCodec(Codec[E]):
    def __init__(self, enum: type[E]) -> None:
        self.enum: type[E] = enum

    def parse(self, raw: str) -> E:
        return self.enum(raw.strip())

    def format(self, value: E) -> str:
        # Going through the enum also accepts (and validates) a plain string.
        return str(self.enum(value).value)


class IPv4Codec(Codec[ipaddress.IPv4Address]):
    def parse(self, raw: str) -> ipaddress.IPv4Address:
        return ipaddress.IPv4Address(raw.strip())


class SourceCodec(Codec[Source]):
    def parse(self, raw: str) -> Source:
        return Source(raw)

    def format(self, value: Source) -> str:
        return Source.coerce(value).value


class SourceListCodec(Codec[tuple[Source, ...]]):
    """A comma-separated list of inputs, e.g. ``vga1,hdmi1,hdmi2``."""

    def parse(self, raw: str) -> tuple[Source, ...]:
        return tuple(Source(part) for part in raw.split(",") if part.strip())


class OptionalCodec(Codec[T | None]):
    """Maps a sentinel word (default ``disabled``) to ``None``."""

    def __init__(self, inner: Codec[T], none_token: str = "disabled") -> None:
        self.inner: Codec[T] = inner
        self.none_token: str = none_token

    def parse(self, raw: str) -> T | None:
        if raw.strip().lower() == self.none_token:
            return None
        return self.inner.parse(raw)

    def format(self, value: T | None) -> str:
        return self.none_token if value is None else self.inner.format(value)


INT = IntCodec()
BOOL = BoolCodec()
STR = StrCodec()


def parse_reply(codec: Codec[T], raw: str, command: str) -> T:
    """Parse ``raw`` with ``codec``, turning failures into :class:`UnexpectedResponseError`."""
    try:
        return codec.parse(raw)
    except ValueError as exc:
        raise UnexpectedResponseError(command, raw, str(exc)) from exc


# ----------------------------------------------------------------------- bound access


class _Client(Protocol):
    """The slice of :class:`SmartDevice` that bound settings talk to."""

    async def get_value(self, key: str) -> str: ...

    async def set_value(
        self, key: str, value: str, *, source: Source | str | None = None
    ) -> str: ...

    async def adjust_value(
        self, key: str, delta: int, *, source: Source | str | None = None
    ) -> str: ...


class BoundReadOnlySetting(Generic[T]):
    """A read-only setting bound to a device instance."""

    __slots__ = ("_client", "_spec")

    def __init__(self, client: _Client, spec: ReadOnlySetting[T]) -> None:
        self._client: _Client = client
        self._spec: ReadOnlySetting[T] = spec

    @property
    def spec(self) -> ReadOnlySetting[T]:
        return self._spec

    async def get(self) -> T:
        """Query the device and return the parsed value."""
        raw = await self._client.get_value(self._spec.key)
        return parse_reply(self._spec.codec, raw, f"get {self._spec.key}")


class BoundSetting(BoundReadOnlySetting[T]):
    """A read/write setting bound to a device instance."""

    __slots__ = ("_setting",)

    def __init__(self, client: _Client, spec: Setting[T]) -> None:
        super().__init__(client, spec)
        self._setting: Setting[T] = spec

    async def set(self, value: T, *, source: Source | str | None = None) -> T:
        """Set the value and return the value the device confirms.

        ``source`` targets a currently-inactive video input instead of the active one;
        only settings declared ``per_source=True`` accept it.

        Raises:
            ValueError: ``value`` is invalid (e.g. out of range) or ``source`` isn't
                supported for this setting. Nothing is sent in that case.
        """
        target = self._check_source(source)
        try:
            raw_value = self._setting.codec.format(value)
        except ValueError as exc:
            raise ValueError(f"Invalid value for {self._setting.name!r}: {exc}") from exc
        reply = await self._client.set_value(self._setting.key, raw_value, source=target)
        return parse_reply(self._setting.codec, reply, f"set {self._setting.key}={raw_value}")

    def _check_source(self, source: Source | str | None) -> Source | None:
        if source is None:
            return None
        if not self._setting.per_source:
            raise ValueError(f"{self._setting.name!r} cannot target a specific source")
        return Source.coerce(source)


class BoundAdjustableIntSetting(BoundSetting[int]):
    """A bound integer setting that also supports relative adjustment."""

    __slots__ = ()

    async def adjust(self, delta: int, *, source: Source | str | None = None) -> int:
        """Change the value by ``delta`` on the device (``set <key>+n`` / ``set <key>-n``)."""
        target = self._check_source(source)
        reply = await self._client.adjust_value(self._setting.key, delta, source=target)
        return parse_reply(self._setting.codec, reply, f"adjust {self._setting.key} {delta:+d}")


# ---------------------------------------------------------------------- declarations


class ReadOnlySetting(Generic[T]):
    """Declaration of a setting that can only be queried."""

    def __init__(self, key: str, codec: Codec[T], *, doc: str = "") -> None:
        self.key: str = key
        self.codec: Codec[T] = codec
        self.doc: str = doc
        self.name: str = key  # replaced by the attribute name in __set_name__

    def __set_name__(self, owner: type, name: str) -> None:
        self.name = name

    @overload
    def __get__(self, obj: None, owner: type[Any]) -> Self: ...
    @overload
    def __get__(self, obj: _Client, owner: type[Any]) -> BoundReadOnlySetting[T]: ...
    def __get__(self, obj: _Client | None, owner: type[Any]) -> Self | BoundReadOnlySetting[T]:
        return self if obj is None else BoundReadOnlySetting(obj, self)

    def __set__(self, obj: object, value: object) -> NoReturn:
        # Being a data descriptor stops ``device.brightness = 5`` from silently
        # shadowing the setting with a plain instance attribute.
        raise AttributeError(
            f"{self.name!r} is a setting, not a value: use "
            f"`await device.{self.name}.get()` (and `.set(...)` if writable)"
        )


class Setting(ReadOnlySetting[T]):
    """Declaration of a readable and writable setting.

    ``per_source=True`` marks settings whose ``set`` command also exists in the
    ``set <key> <source>=<value>`` form for targeting an inactive input.
    """

    def __init__(
        self, key: str, codec: Codec[T], *, per_source: bool = False, doc: str = ""
    ) -> None:
        super().__init__(key, codec, doc=doc)
        self.per_source: bool = per_source

    @overload
    def __get__(self, obj: None, owner: type[Any]) -> Self: ...
    @overload
    def __get__(self, obj: _Client, owner: type[Any]) -> BoundSetting[T]: ...
    def __get__(self, obj: _Client | None, owner: type[Any]) -> Self | BoundSetting[T]:
        return self if obj is None else BoundSetting(obj, self)


class IntSetting(Setting[int]):
    """An integer setting with a fixed valid range (``bounds``)."""

    def __init__(self, key: str, bounds: range, *, per_source: bool = False, doc: str = "") -> None:
        super().__init__(key, IntCodec(bounds), per_source=per_source, doc=doc)
        self.bounds: range = bounds


class AdjustableIntSetting(IntSetting):
    """An integer setting that also accepts relative changes (``set <key>+<n>`` / ``-<n>``).

    Only declare this where the command reference documents the relative form;
    ``adjust()`` does not exist on a plain :class:`IntSetting`, so the type checker
    and editor completion won't offer it there.
    """

    @overload
    def __get__(self, obj: None, owner: type[Any]) -> Self: ...
    @overload
    def __get__(self, obj: _Client, owner: type[Any]) -> BoundAdjustableIntSetting: ...
    def __get__(self, obj: _Client | None, owner: type[Any]) -> Self | BoundAdjustableIntSetting:
        return self if obj is None else BoundAdjustableIntSetting(obj, self)


class BoolSetting(Setting[bool]):
    """An on/off setting."""

    def __init__(self, key: str, *, doc: str = "") -> None:
        super().__init__(key, BOOL, doc=doc)


class EnumSetting(Setting[E]):
    """A setting that takes one of the members of ``enum``."""

    def __init__(self, key: str, enum: type[E], *, doc: str = "") -> None:
        super().__init__(key, EnumCodec(enum), doc=doc)
        self.enum: type[E] = enum


class StrSetting(Setting[str]):
    """A free-text setting with an optional length limit."""

    def __init__(self, key: str, *, max_length: int | None = None, doc: str = "") -> None:
        super().__init__(key, StrCodec(max_length), doc=doc)
        self.max_length: int | None = max_length


class IPv4Setting(Setting[ipaddress.IPv4Address]):
    """An IPv4 address."""

    def __init__(self, key: str, *, doc: str = "") -> None:
        super().__init__(key, IPv4Codec(), doc=doc)
