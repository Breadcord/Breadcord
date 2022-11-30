from os import PathLike
from typing import Optional, Any

from tomlkit.items import Key, Item, Comment, Whitespace
from tomlkit.toml_file import TOMLFile


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
        self._settings: dict[str, Setting] = {setting.key: setting for setting in settings}

    def __repr__(self) -> str:
        return f'Settings({", ".join(repr(setting) for setting in self._settings.values())})'

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
