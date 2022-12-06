from os import PathLike
from typing import Optional, Any

import tomlkit
from tomlkit.items import Key, Item, Comment, Whitespace, Table
from tomlkit.toml_file import TOMLDocument, TOMLFile


class Setting:
    """Holds a single setting key-value pair, and optionally a description of the setting."""

    def __init__(self, key: str, value: Any, description: str = '') -> None:
        self.key = key
        self.value = value
        self.description = description

    def __repr__(self) -> str:
        return f'Setting(key={repr(self.key)}, value={repr(self.value)}, description={repr(self.description)})'


class Settings:
    """Holds a collection of :class:`Setting` instances."""

    def __init__(self, settings: list[Setting] = None) -> None:
        self._settings: dict[str, Setting] = {} if settings is None else {setting.key: setting for setting in settings}

    def __repr__(self) -> str:
        return f'Settings({", ".join(repr(setting) for setting in self._settings.values())})'

    def __getattr__(self, item: str) -> Any:
        return self.get(item)

    def __setattr__(self, key: str, value: Any) -> None:
        if key == '_settings':
            super().__setattr__(key, value)
            return

        self.set(key, value)

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
        :param strict: Whether KeyError should be thrown when the key doesn't exist, instead of creating a new setting.
        """

        if not strict and key not in self._settings:
            self._settings[key] = Setting(key, value)
        self._settings[key].value = value

    def update_values(self, data: dict, strict: bool = True) -> None:
        """Overwrites existing values for settings, creating new :class:`Setting` entries if necessary.

        :param data: A dict containing key-value pairs.
        :param strict: Whether KeyError should be thrown when the key doesn't exist, instead of creating a new setting.
        """

        for item in data.items():
            self.set(*item, strict=strict)

    def as_toml(self, *, table: bool = False) -> TOMLDocument | Table:
        """Exports the settings as a :class:`TOMLDocument` or :class:`Table` instance.

        This method works recursively on any settings which have a value of a :class:`Settings` instance,
        adding them to the TOML document as tables.

        :param table: Whether a table should be generated instead of a document.
        """

        document = tomlkit.table() if table else TOMLDocument()
        for setting in self._settings.values():
            if isinstance(setting.value, Settings):
                document.append(setting.key, setting.value.as_toml(table=True))
            else:
                document.append(setting.key, setting.value)

        return document


def parse_chunk(chunk: list[tuple[Optional[Key], Item]]) -> Setting:
    """Converts a TOMLDocument.body chunk into a :class:`Setting` instance.

    Any lines of comments located before the key-value pair will be used for the setting description.

    :param chunk: A sub-list of TOMLDocument.body. Must contain one key-value pair.
    """

    chunk = chunk.copy()

    description = ''
    while chunk[0][0] is None:
        if isinstance(chunk[0][1], Comment):
            description += chunk[0][1].indent(0).as_string().lstrip('# ')
        chunk.pop(0)

    return Setting(chunk[0][0].key, chunk[0][1], description.rstrip())


def load_schema(file_path: str | PathLike[str]) -> Settings:
    """Loads and deserialises a settings schema.

    :param file_path: Path to the schema file.
    """

    body: list[tuple[Optional[Key], Item]] = TOMLFile(file_path).read().body
    body.append((None, Whitespace('')))
    settings = []

    chunk = []
    for item in body:
        chunk.append(item)
        if item[0] is not None:
            if chunk:
                settings.append(parse_chunk(chunk))
                chunk = []

    return Settings(settings)


def load_settings(file_path: str | PathLike[str]) -> dict[str, Any]:
    """Loads and deserialises a TOML settings file into a :class:`TOMLDocument` instance.

    :param file_path: Path to the TOML settings file.
    :returns: A dict structure representing the hierarchy of the TOML document.
    """

    return dict(TOMLFile(file_path).read())
