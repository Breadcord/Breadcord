from __future__ import annotations

from functools import partial, wraps
from logging import getLogger
from os import PathLike
from typing import Optional, Any, Callable

import tomlkit
from tomlkit.items import Key, Item, Comment, Whitespace, Table
from tomlkit.toml_file import TOMLDocument, TOMLFile

_logger = getLogger('breadcord.config')


class Setting:
    """Holds a single setting key-value pair, and optionally a description of the setting.

    The data type is enforced in subsequent writes to the value of this setting, inferring from the initial data type.
    """

    def __init__(self, key: str, value: Any, description: str = '', *, in_schema: bool = False) -> None:
        self.key = key
        self._value = value
        self.description = description
        self.type: type = type(value)
        self.in_schema = in_schema
        self._observers = []

    def __repr__(self) -> str:
        return (
            f'Setting('
            f'key={self.key!r}, '
            f'value={self._value!r}, '
            f'description={self.description!r}, '
            f'in_schema={self.in_schema!r}'
            f')'
        )

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        old_value = self._value
        self._value = new_value
        for observer in self._observers:
            observer(old_value, new_value)

    def new_observer(
        self,
        observer: Callable[[Any, Any], Any] | None = None,
        *,
        always_trigger: bool = False
    ) -> Callable[[Any, Any], None]:
        """Registers an observer function which is called whenever the setting value is updated.

        :param observer: The callback function. Takes two parameters ``old`` and ``new``, which correspond to the value
            of the setting before and after it is updateed respectively.
        :param always_trigger: If the observer should be called even if the updated value is equal to the previous
            value.
        """

        if observer is None:
            return partial(self.new_observer, always_trigger=always_trigger)

        @wraps(observer)
        def wrapper(old: Any, new: Any) -> None:
            if not always_trigger and old == new:
                return
            observer(old, new)

        self._observers.append(wrapper)
        return wrapper


class Settings:
    """Holds a collection of :class:`Setting` instances."""

    def __init__(self, settings: list[Setting] = None) -> None:
        self._settings: dict[str, Setting] = {} if settings is None else {setting.key: setting for setting in settings}

    def __repr__(self) -> str:
        return f'Settings({", ".join(repr(setting) for setting in self._settings.values())})'

    def __getattr__(self, item: str) -> Setting | Settings:
        setting = self.get_full(item)
        return setting.value if setting.type == Settings else setting

    def __iter__(self):
        yield from self._settings.values()

    def __contains__(self, item: Any) -> bool:
        return item in self._settings.keys()

    def set_schema(self, file_path: str | PathLike[str]) -> None:
        """Loads and deserialises a settings schema, for the settings to follow.

        :param file_path: Path to the schema file.
        """

        body: list[tuple[Optional[Key], Item]] = TOMLFile(file_path).read().body
        body.append((None, Whitespace('')))

        chunk = []
        for item in body:
            chunk.append(item)
            if item[0] is None or not chunk:
                continue

            setting = parse_schema_chunk(chunk)
            self._settings[setting.key] = Setting(
                key=setting.key,
                value=self._settings[setting.key].value if setting.key in self else setting.value,
                description=setting.description,
                in_schema=True
            )
            chunk = []

    def get(self, key: str) -> Any:
        """Gets the value for a setting by its key.

        This method can be thought of as a shortcut for ``get_full().value``.

        :param key: The key for the setting (the identifier before the equals sign in a TOML document).
        """

        return self._settings[key].value

    def get_full(self, key: str) -> Setting:
        """Gets a :class:`Setting` object by its key.

        :param key: The key for the setting (the identifier before the equals sign in a TOML document).
        """

        return self._settings[key]

    def set(self, key: str, value: Any, *, strict: bool = True) -> None:
        """Sets the value for a setting by its key.

        :param key: The key for the setting (the identifier before the equals sign in a TOML document).
        :param value: The new value to set for the setting.
        :param strict: Whether KeyError should be thrown when the key doesn't exist in the schema.
        """

        if strict and (
            key not in self._settings
            or not self._settings[key].in_schema
        ):
            raise ValueError(f'{key!r} is not defined in the schema')

        if key not in self._settings:
            self._settings[key] = Setting(key, value, in_schema=False)
        elif not isinstance(value, self._settings[key].type):
            raise TypeError(
                f'{key!r} should be type {self._settings[key].type.__name__!r}, '
                f'but value has type {type(value).__name__!r}'
            )

        self._settings[key].value = value

    def update_from_dict(self, data: dict, *, strict: bool = True) -> None:
        """Recursively sets settings from a provided :class:`dict` object.

        Note that new :class:`Settings` instances will be created as necessary to match the structure of the
        :class:`dict`, regardless of the value of ``strict``.

        :param data: A dict containing key-value pairs.
        :param strict: Whether KeyError should be thrown when a key doesn't exist, instead of creating a new setting.
        """

        for key, value in data.items():
            if isinstance(value, dict):
                if key not in self._settings:
                    self.set(key, settings := Settings(), strict=False)
                elif (setting := self.get_full(key)).type == Settings:
                    settings = setting.value
                else:
                    raise ValueError(
                        f'cannot write to {setting.key!r} because it conflicts '
                        f'with an existing setting of type {setting.type.__name__!r}'
                    )
                settings.update_from_dict(value, strict=strict)
            else:
                self.set(key, value, strict=strict)

    def as_toml(self, *, table: bool = False, warn_schema: bool = True) -> TOMLDocument | Table:
        """Exports the settings as a :class:`TOMLDocument` or :class:`Table` instance.

        This method works recursively on any settings which have a value of a :class:`Settings` instance,
        adding them to the TOML document as tables.

        :param table: Whether a table should be generated instead of a document.
        :param warn_schema: Whether settings not declared in the schema should warn the user.
        """

        document = tomlkit.table() if table else TOMLDocument()
        top_level: list[Setting] = []
        nested: list[Setting] = []
        for setting in self:
            (nested if isinstance(setting.value, Settings) else top_level).append(setting)

        for setting in top_level:
            for line in setting.description.splitlines():
                document.add(tomlkit.comment(line))
            document.add(setting.key, setting.value)
            if not setting.in_schema:
                if warn_schema:
                    _logger.warning(f'{setting.key!r} setting is not declared in schema')
                    document.value[setting.key].comment('⚠️ Unrecognised setting')
            else:
                document.add(tomlkit.nl())

        for setting in nested:
            document.add(tomlkit.nl())
            table = setting.value.as_toml(table=True, warn_schema=setting.in_schema)
            if not setting.in_schema:
                table.comment('🚫 Disabled')
            document.append(setting.key, table)

        return document


def parse_schema_chunk(chunk: list[tuple[Optional[Key], Item]]) -> Setting:
    """Converts a TOMLDocument.body chunk representing a single schema setting into a :class:`Setting` instance.

    Any comments located before the key-value pair will be used for the setting's description.

    :param chunk: A sub-list of TOMLDocument.body. Must contain one key-value pair.
    """

    chunk = chunk.copy()

    description = ''
    while chunk[0][0] is None:
        if isinstance(chunk[0][1], Comment):
            description += chunk[0][1].indent(0).as_string().lstrip('# ')
        chunk.pop(0)

    return Setting(chunk[0][0].key, chunk[0][1].unwrap(), description.rstrip(), in_schema=True)


def load_settings(file_path: str | PathLike[str]) -> dict[str, Any]:
    """Loads and deserialises a TOML settings file into a :class:`TOMLDocument` instance.

    :param file_path: Path to the TOML settings file.
    :returns: A dict structure representing the hierarchy of the TOML document.
    """

    return TOMLFile(file_path).read().unwrap()
