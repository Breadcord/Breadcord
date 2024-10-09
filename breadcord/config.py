from __future__ import annotations

from functools import partial, wraps
from logging import getLogger
from typing import TYPE_CHECKING, Any, TypeVar

import tomlkit
from tomlkit import TOMLDocument
from tomlkit.items import Comment, Item, Key, Table, Whitespace
from tomlkit.toml_file import TOMLFile

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, KeysView, ValuesView
    from os import PathLike

_logger = getLogger('breadcord.config')


_T = TypeVar('_T')


class SettingsNode:
    """An abstract base class representing a node in a settings tree structure.

    This class is subclassed by :class:`Setting` and :class:`SettingsGroup`.

    :ivar description: A description of the node, usually specified in the settings schema using TOML comments.
    :ivar parent: The parent node, or ``None`` if it is a root node.
    :ivar in_schema: Whether the node is present in the settings schema.
    :param key: The identifier used for this node by the parent node in the settings tree.
    :param parent: The parent node, or ``None`` if it is a root node.
    :param in_schema: Whether the node is present in the settings schema.
    """

    def __init__(
        self,
        key: str,
        *,
        description: str = '',
        parent: SettingsGroup | None = None,
        in_schema: bool = False,
    ):
        self._key = key
        self._path = (self,)

        self.description = description
        self.parent = parent
        self.in_schema = in_schema

    def __repr__(self) -> str:
        return f'<{self.__class__.__name__} {self.path_id()}>'

    @property
    def key(self) -> str:
        """The identifier used for this node by the parent node in the settings tree."""
        return self._key

    def path(self) -> tuple[SettingsNode | Setting | SettingsGroup, ...]:
        """Return a series of node references representing the path to this node from the root node."""
        if self.parent is None:
            return (self,)
        return *self.parent.path(), self

    def path_id(self):
        """Return a string identifier representing the path to this node from the root node."""
        return '.'.join(node.key for node in self.path())

    def root(self) -> SettingsGroup:
        """Return the root node of the settings tree this node belongs to.

        This method is equivalent to calling ``node.path()[0]``.
        """
        node = self
        while node.parent is not None:
            node = node.parent
        return node


class Setting(SettingsNode):
    """A single setting key-value pair, plus metadata such as the setting description.

    A :class:`Setting` instance is equivalent to a leaf node in a tree structure, or a file in a filesystem.

    The data type of the setting is inferred from the initial value's data type, and it is enforced in subsequent
    writes to the value of this setting.

    :ivar type: The data type held by the setting.
    :param key: The identifier used for this node by the parent node in the settings tree.
    :param value: The value for the setting to hold.
    :param description: A description of the setting, usually specified in the settings schema using TOML comments.
    :param parent: The parent node, or ``None`` if it is a root node.
    :param in_schema: Whether the setting is present in the settings schema.
    """

    def __init__(
        self,
        key: str,
        value: Any,
        *,
        description: str = '',
        parent: SettingsGroup | None = None,
        in_schema: bool = False,
    ) -> None:

        super().__init__(key=key, description=description, parent=parent, in_schema=in_schema)

        self._value = value

        self.type: type = type(value)

    @property
    def value(self) -> Any:
        """The value held by the setting."""
        return self._value

    @value.setter
    def value(self, new_value: Any) -> None:
        """Assign a new value to the setting, validating the new value type and triggering necessary observers."""
        if isinstance(new_value, int) and self.type == float:  # noqa: E721
            new_value = float(new_value)
        if not isinstance(new_value, self.type):
            raise TypeError(
                f"Cannot assign type '{type(new_value).__name__}' to setting with type '{self.type.__name__}' "
                f"({self.path_id()})",
            )

        old_value = self._value
        self._value = new_value

        root_observers = self.root().observers
        path_id = self.path_id()
        if path_id not in root_observers:
            return
        for observer in root_observers[path_id]:
            observer(old_value, new_value)

    def observe(
        self,
        observer: Callable[[Any, Any], Any] | None = None,
        *,
        always_trigger: bool = False,
    ) -> Callable[[Any, Any], None]:
        """Register an observer function which is called whenever the setting value is updated.

        This method can be used as a decorator, with optional parentheses for arguments.

        :param observer: The callback function. Takes two parameters ``old`` and ``new``, which correspond to the value
            of the setting before and after it is updateed respectively.
        :param always_trigger: If the observer should be called even if the updated value is equal to the previous
            value.
        """
        if observer is None:
            return partial(self.observe, always_trigger=always_trigger)

        @wraps(observer)
        def wrapper(old: Any, new: Any) -> None:
            if not always_trigger and old == new:
                return
            observer(old, new)

        observers = self.root().observers
        path_id = self.path_id()
        if path_id not in observers:
            observers[path_id] = []
        observers[path_id].append(wrapper)

        return wrapper


class SettingsGroup(SettingsNode):
    """A collection of :class:`Setting` and child :class:`SettingsGroup` instances.

    A :class:`SettingsGroup` instance is equivalent to a parent node in a tree structure, or a directory in a
    filesystem.

    :param key: The identifier used for this node by the parent node in the settings tree.
    :param settings: A list of settings to add to this settings group.
    :param children: A list of :class:`SettingsGroup` nodes to attach to this node as children.
    :param parent: The parent node, or ``None`` if it is a root node.
    :param in_schema: Whether the setting is present in the settings schema.
    :param schema_path: The path to a settings schema to apply to this settings group.
    :param observers: The :class:`dict` of observers to assign the node. Should only be specified for root nodes.
    """

    def __init__(
        self,
        key: str,
        settings: list[Setting] | None = None,
        children: list[SettingsGroup] | None = None,
        *,
        parent: SettingsGroup | None = None,
        in_schema: bool = False,
        schema_path: str | PathLike[str] | None = None,
        observers: dict[str, list[Callable[[Any, Any], None]]] | None = None,
    ) -> None:

        self._settings: dict[str, Setting] = {setting.key: setting for setting in settings or ()}
        self._children: dict[str, SettingsGroup] = {child.key: child for child in children or ()}

        self.observers = observers

        super().__init__(key=key, parent=parent, in_schema=in_schema)

        if schema_path is not None:
            self.load_schema(file_path=schema_path)

    def __repr__(self) -> str:
        return (
            f'<{self.__class__.__name__} {self.path_id()} '
            f'settings:{len(self._settings)} children:{len(self._children)}>'
        )

    def __getattr__(self, item: str) -> Setting | SettingsGroup:
        if item in self._children:
            return self.get_child(item)
        return self._settings[item]

    def __contains__(self, item: str) -> bool:
        if not isinstance(item, str):
            raise TypeError(
                f"'in <{self.__class__.__name__}>' requires string as left operand, not '{type(item).__name__}'",
            )
        return item in self.keys()

    def __iter__(self) -> Generator[Setting, None, None]:
        yield from self._settings.values()

    def keys(self) -> KeysView[str]:
        return self._settings.keys()

    def child_keys(self) -> KeysView[str]:
        return self._children.keys()

    def children(self) -> ValuesView[SettingsGroup]:
        return self._children.values()

    def walk(self, *, skip_groups: bool = False, skip_settings: bool = False) -> list[SettingsNode]:
        """Recursively traverses all child nodes and returns them as a flat list.

        :param skip_groups: Whether :cls:`SettingsGroup` objects should be skipped
        :param skip_settings: Whether :cls:`Setting` objects should be skipped
        """
        discovered: list[SettingsNode] = [] if skip_groups else [self]
        if not skip_settings:
            discovered.extend(self)
        for child in self.children():
            discovered.extend(child.walk(skip_groups=skip_groups, skip_settings=skip_settings))
        return discovered

    def load_schema(
        self,
        *,
        file_path: str | PathLike[str] | None = None,
        body: list[tuple[Key | None, Item]] | None = None,
    ) -> None:
        """Load and deserialise a settings schema, for the settings to follow.

        :param file_path: Path to the schema file.
        :param body: The parsed TOML body data to interpret as. Overrides loading from ``file_path`` when present.
        """
        body: list[tuple[Key | None, Item]] = TOMLFile(file_path).read().body if body is None else body
        if body is None:
            raise ValueError('either file_path or body must be specified')
        body.append((None, Whitespace('')))

        chunk = []
        for item in body:
            chunk.append(item)
            if item[0] is None:
                continue

            setting = parse_schema_chunk(chunk)
            if setting.type == dict:  # noqa: E721
                group = self.get_child(setting.key, allow_new=True)
                group.description = setting.description
                group.in_schema = True
                table_document = tomlkit.loads(chunk[-1][1].as_string())
                group.load_schema(body=table_document.body)
                self.add_child(group)
            else:
                setting.parent = self
                if setting.key in self:
                    setting.value = self._settings[setting.key].value
                self._settings[setting.key] = setting

            next_chunk: list[tuple[Key | None, Item]] = []
            # This is required as comments after a table are considered a child of the table
            if isinstance(chunk[-1][1], tomlkit.items.Table):
                for line in reversed(chunk[-1][1].as_string().splitlines()):
                    if line.startswith('#'):
                        next_chunk.append((None, tomlkit.comment(line.lstrip('# '))))
                    elif line.strip():
                        break
                next_chunk.reverse()
            chunk = next_chunk

    def get(self, key: str, default: _T = None) -> Setting | _T:
        """Get a :class:`Setting` object by its key.

        :class:`SettingsGroup` implements ``__getattr__``, so a setting can be accessed by attribute as a shortcut.
        For example, ``settings.debug`` can be used instead of ``settings.get('debug')``.

        :param key: The key for the setting (the identifier before the equals sign in a TOML document).
        :param default: The value to return if the key doesn't exist, by default ``None``.
        :returns: The setting object if it exists, otherwise the default value.
        """
        return self._settings.get(key, default)

    def set(self, key: str, value: Any, *, strict: bool = True) -> None:
        """Set the value for a setting by its key, creating new settings as necessary if not using strict mode.

        :param key: The key for the setting (the identifier before the equals sign in a TOML document).
        :param value: The new value to set for the setting.
        :param strict: Whether :class:`KeyError` should be thrown when the key doesn't exist in the schema.
        """
        if strict and (
            key not in self
            or not self._settings[key].in_schema
        ):
            raise ValueError(f'{self.path_id()}.{key} is not declared in the schema')

        if key not in self:
            self._settings[key] = Setting(key, value, parent=self, in_schema=False)
        else:
            self._settings[key].value = value

    def get_child(self, key: str, allow_new: bool = False) -> SettingsGroup:
        """Get a child :class:`SettingsGroup` object by its key.

        :class:`SettingsGroup` implements ``__getattr__``, so a child node can be accessed by attribute as a shortcut.
        For example, ``settings.ExampleModule`` can be used instead of ``settings.get_child('ExampleModule')``.

        :param key: The key for the child group.
        :param allow_new: Whether a new :class:`SettingsGroup` instance should be created if it doesn't exist.
        """
        if allow_new and key not in self._children:
            self.add_child(SettingsGroup(key))
        return self._children[key]

    def add_child(self, child: SettingsGroup) -> None:
        """Set a child :class:`SettingsGroup` object as a child node to the current node.

        :param child: The settings group to attach as a child node.
        """
        self._children[child.key] = child
        child.parent = self

    def update_from_dict(self, data: dict, *, strict: bool = True) -> None:
        """Recursively sets settings from a provided :class:`dict` object.

        Note that new :class:`SettingsGroup` instances will be created as necessary to match the structure of the
        :class:`dict`, regardless of the value of ``strict``.

        :param data: A dict containing key-value pairs.
        :param strict: Whether :class:`KeyError` should be thrown when a key doesn't exist, instead of creating a new
            setting.
        """
        for key, value in data.items():
            if isinstance(value, dict):
                child = self.get_child(key, allow_new=True)
                child.update_from_dict(value, strict=strict)
            else:
                self.set(key, value, strict=strict)

    def as_toml(self, *, table: bool = False, warn_schema: bool = True) -> TOMLDocument | Table:
        """Export the descendent settings as a :class:`TOMLDocument` or :class:`Table` instance.

        This method works recursively on any settings which have a value of a :class:`SettingsGroup` instance,
        adding them to the TOML document as tables.

        :param table: Whether a table should be generated instead of a document.
        :param warn_schema: Whether settings not declared in the schema should warn the user.
        """
        document = tomlkit.table() if table else TOMLDocument()

        previous_setting_in_schema = False
        for setting in self:
            if previous_setting_in_schema:
                document.add(tomlkit.nl())
                previous_setting_in_schema = False
            for line in setting.description.splitlines():
                document.add(tomlkit.comment(line))
            document.add(setting.key, setting.value)
            if setting.in_schema:
                previous_setting_in_schema = True
            elif warn_schema:
                _logger.warning(f'{setting.path_id()} is not declared in the schema')
                document.value.item(setting.key).comment('⚠️ Unrecognised setting')

        for child in self.children():
            document.add(tomlkit.ws('\n\n'))
            table = child.as_toml(table=True, warn_schema=child.in_schema)
            if not child.in_schema:
                table.comment('🚫 Disabled')
            for line in child.description.splitlines():
                document.add(tomlkit.comment(line))
            document.append(child.key, table)
            table.trivia.indent = ''

        return document


def parse_schema_chunk(chunk: list[tuple[Key | None, Item]]) -> Setting:
    """Convert a TOMLDocument.body chunk representing a single schema setting into a :class:`Setting` instance.

    Any comments located before the key-value pair will be used for the setting's description.

    :param chunk: A sub-list of TOMLDocument.body. Must contain one key-value pair.
    """
    chunk = chunk.copy()

    description = ''
    while chunk[0][0] is None:
        if isinstance(chunk[0][1], Comment):
            description += chunk[0][1].indent(0).as_string().lstrip('# ')
        chunk.pop(0)

    return Setting(chunk[0][0].key, chunk[0][1].unwrap(), description=description.rstrip(), in_schema=True)


def load_toml(file_path: str | PathLike[str]) -> dict[str, Any]:
    """Load and deserialise a TOML file into a :class:`TOMLDocument` instance.

    :param file_path: Path to the TOML file.
    :returns: A dict structure representing the hierarchy of the TOML document.
    """
    return TOMLFile(file_path).read().unwrap()
