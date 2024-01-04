from __future__ import annotations

import inspect
import sys
from collections import defaultdict
from typing import TYPE_CHECKING, Callable, TypeVar, overload

import aiohttp
import discord
from rapidfuzz.fuzz import partial_ratio_alignment
from typing_extensions import Self

import breadcord
from breadcord.module import ModuleCog

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from collections.abc import Sequence

    from discord.ui.button import Button, V

    # noinspection PyProtectedMember
    from discord.ui.item import ItemCallbackType


_T = TypeVar('_T')
_Transformer = TypeVar('_Transformer', bound=discord.app_commands.Transformer)


async def administrator_check(interaction: discord.Interaction) -> bool:
    """A discord.py check to ensure that the interaction user is an administrator.

    An administrator is either an owner of the bot application as seen on the Discord developer portal, or a user
    granted administrator privileges under the ``settings.administrators`` setting.

    This function should not be invoked directly, and should instead be passed to the ``discord.app_commands.check``
    function and used as a decorator.

    Example::

        @app_commands.command()
        @app_commands.check(breadcord.helpers.administrator_check)
        async def do_admin_stuff(self, interaction: discord.Interaction, ...):
            ...

    :param interaction: The current interaction which the check should apply to.
    """
    if not await interaction.client.is_owner(interaction.user):
        raise breadcord.errors.NotAdministratorError
    return True


@overload
def search_for(
    query: str,
    objects: Sequence[str],
    *,
    threshold: float = 80,
    max_results: int | None = 25,
) -> Sequence[str]:
    ...


@overload
def search_for(
    query: str,
    objects: Sequence[_T],
    *,
    key: Callable[[_T], str],
    threshold: float = 80,
    max_results: int | None = 25,
) -> Sequence[_T]:
    ...


def search_for(
    query: str,
    objects: Sequence[_T],
    *,
    key: Callable[[_T], str] | None = None,
    threshold: float = 80,
    max_results: int | None = 25,
) -> Sequence[_T]:
    """A custom implementation of a fuzzy search algorithm.

    The algorithm works by assigning each string a two-part score: The partial ratio score (a metric for similarity),
    and how far from the start of the string the optimal alignment is. Results are then sorted by highest partial ratio
    score first, with a secondary sort of earliest alignment to ensure that matches near the start of the string are
    shown earlier.

    :param query: The string to search for.
    :param objects: The sequence of strings, or other objects if using a key, to search through.
    :param key: An optional function which is called for each object, taking it as a parameter and returning a string to
    be used in the search process.
    :param threshold: A number between 0 and 100 inclusive which determines the cutoff point for the similarity score.
        A threshold of 0 means that every object will be returned in the results, whereas a threshold of 100 means that
        only exact matches will be returned.
    :param max_results: The maximum number of results to be returned from the search. This can be set to ``None`` to
        return all results which pass the threshold.
    """
    if not query:
        return objects[:max_results]

    query = query.strip().lower()
    scored_objs: defaultdict[tuple[float, int], list[_T]] = defaultdict(list)
    strings = objects if key is None else map(key, objects)

    for i, string in enumerate(strings):
        alignment = partial_ratio_alignment(query, string)
        score = (alignment.score, -alignment.dest_start)
        scored_objs[score].append(objects[i])

    results = []
    for score, objs in sorted(scored_objs.items(), key=lambda item: item[0], reverse=True):
        if score[0] < threshold:
            break
        results.extend(objs)

    return results[:max_results]


def simple_button(
    label: str | None = None,
    disabled: bool = False,
    style: discord.ButtonStyle = discord.ButtonStyle.grey,
    emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
    row: int | None = None,
):
    """A substitute for ``discord.ui.button`` which generates a custom ID for you.

    The custom ID is generated based off the qualified name of the decorated method, which should ensure that the ID is
    both unique and idempotent. However, since custom IDs cannot exceed 100 characters in length, this may fail for
    exceptionally long names.

    :param label: The label of the button, if any.
    :param style: The style of the button. Defaults to :attr:`discord.ButtonStyle.grey`.
    :param disabled: Whether the button is disabled or not. Defaults to ``False``.
    :param emoji: The emoji of the button. This can be in string form or a :class:`discord.PartialEmoji` or a full
        :class:`discord.Emoji`.
    :param row: The relative row this button belongs to. A Discord component can only have 5 rows. By default, items are
    arranged automatically into those 5 rows. If you'd like to control the relative positioning of the row then passing
    an index is advised. For example, row=1 will show up before row=2. Defaults to ``None``, which is automatic
    ordering. The row number must be between 0 and 4 (i.e. zero indexed).
    """

    def decorator(func: ItemCallbackType[V, Button[V]]) -> ItemCallbackType[V, Button[V]]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError('button function must be a coroutine function')

        max_id_length = 100
        # noinspection PyUnresolvedReferences
        custom_id = f'{func.__module__}:{func.__qualname__}'.removeprefix('breadcord.')
        if len(custom_id) > max_id_length:
            raise RuntimeError(f'decorated function path exceeds {max_id_length} characters: {custom_id}')

        func.__discord_ui_model_type__ = discord.ui.Button
        func.__discord_ui_model_kwargs__ = {
            'style': style,
            'custom_id': custom_id,
            'url': None,
            'disabled': disabled,
            'label': label,
            'emoji': emoji,
            'row': row,
        }

        return func

    return decorator


def simple_transformer(to: type[_T]) -> Callable[[type[_Transformer]], _Transformer]:
    """A decorator for discord.py transformers to make them easier to use in type annotations.

    Before::

        class BooleanTransformer(app_commands.Transformer):
            def transform(self, interaction: discord.Interaction, value: str) -> bool:
                return True if value.strip().lower() in ('true', 'yes', 'y') else False

        @app_commands.command()
        async def say_hello(
            interaction: discord.Interaction,
            all_caps: app_commands.Transform[bool, BooleanTransforer]
        ):
            await interaction.response.send_message('HELLO' if all_caps else 'hello')

        transformer = BooleanTransformer()
        manual_transform = transformer.transform(some_interaction, 'yes')

    After::

        @breadcord.helpers.simple_transformer(bool)
        class BooleanTransformer(app_commands.Transformer):
            def transform(self, interaction: discord.Interaction, value: str) -> bool:
                return True if value.strip().lower() in ('true', 'yes', 'y') else False

        @app_commands.command()
        async def say_hello(interaction: discord.Interaction, all_caps: BooleanTransformer):
            await interaction.response.send_message('HELLO' if all_caps else 'hello')

        manual_transform = BooleanTransformer.transform(some_interaction, 'yes')

    :param to: The type which the transformer should output.
    """
    def decorator(cls: type[_Transformer]) -> _Transformer:
        return discord.app_commands.Transform.__class_getitem__((to, cls))

    return decorator


class HTTPModuleCog(ModuleCog):
    """A module cog which automatically creates and closes an aiohttp session."""

    def __init__(self, *args, headers: aiohttp.typedefs.LooseHeaders | None = None, **kwargs):
        super().__init__(*args, **kwargs)

        if headers:
            headers['User-Agent'] = headers.get('User-Agent') or (
                f'Breadcord (https://breadcord.com/) '
                f'{self.module.manifest.id}/{self.module.manifest.version} '
                f'Python/{".".join(map(str, sys.version_info[:3]))} '
                f'aiohttp/{aiohttp.__version__}'
            )
        self._session_headers = headers
        # White lie since the type checker doesn't know about cog_load
        self.session: aiohttp.ClientSession = None  # type: ignore[assignment]

    async def cog_load(self) -> None:
        await super().cog_load()
        self.session = aiohttp.ClientSession(headers=self._session_headers)

    async def cog_unload(self) -> None:
        await super().cog_unload()
        if self.session is not None and not self.session.closed:
            await self.session.close()

    async def _inject(self, *args, **kwargs) -> Self:
        try:
            return await super()._inject(*args, **kwargs)
        except Exception:
            # Extra check since putting it in cog_unload apparently isn't enough
            if isinstance(self.session, aiohttp.ClientSession) and not self.session.closed:
                self.logger.warning("Session wasn't closed properly, closing it now")
                await self.session.close()
            raise
