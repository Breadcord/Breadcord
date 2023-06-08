from __future__ import annotations

import inspect
from collections import defaultdict
from typing import TYPE_CHECKING, TypeVar, Callable, overload

import discord
from rapidfuzz.fuzz import partial_ratio_alignment

import breadcord

if TYPE_CHECKING:
    # noinspection PyProtectedMember
    from discord.ui.button import V, Button
    # noinspection PyProtectedMember
    from discord.ui.item import ItemCallbackType


_T = TypeVar('_T')
_Transformer = TypeVar('_Transformer', bound=discord.app_commands.Transformer)


async def administrator_check(interaction: discord.Interaction) -> bool:
    if not await interaction.client.is_owner(interaction.user):
        raise breadcord.errors.NotAdministratorError
    return True


def _search_with_key(
    query: str,
    objects: list[_T],
    *,
    key: Callable[[_T], str],
    threshold: float,
    max_results: int | None
) -> list[_T]:
    query = query.strip().lower()
    scored_objs: defaultdict[tuple[float, int], list[_T]] = defaultdict(list)
    strings = objects if key is None else map(key, objects)

    if not query:
        return objects[:max_results]

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


@overload
def search_for(
    query: str,
    objects: list[str],
    *,
    threshold: float = 80,
    max_results: int | None = 25
) -> list[str]:
    ...


@overload
def search_for(
    query: str,
    objects: list[_T],
    *,
    key: Callable[[_T], str],
    threshold: float = 80,
    max_results: int | None = 25
) -> list[_T]:
    ...


def search_for(
    query: str,
    objects: list[_T],
    *,
    key: Callable[[_T], str] | None = None,
    threshold: float = 80,
    max_results: int | None = 25
) -> list[_T]:
    if key is None:
        def dummy_key(item: _T) -> _T:
            return item
        key = dummy_key

    return _search_with_key(query=query, objects=objects, key=key, threshold=threshold, max_results=max_results)


def simple_button(
    label: str | None = None,
    disabled: bool = False,
    style: discord.ButtonStyle = discord.ButtonStyle.grey,
    emoji: str | discord.Emoji | discord.PartialEmoji | None = None,
    row: int | None = None,
):
    def decorator(func: ItemCallbackType[V, Button[V]]) -> ItemCallbackType[V, Button[V]]:
        if not inspect.iscoroutinefunction(func):
            raise TypeError('button function must be a coroutine function')

        # noinspection PyUnresolvedReferences
        custom_id = f'{func.__module__}:{func.__qualname__}'.removeprefix('breadcord.')
        if len(custom_id) > 100:
            raise RuntimeError(f'decorated function path exceeds 100 characters: {custom_id}')

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
    def decorator(cls: type[_Transformer]) -> _Transformer:
        return discord.app_commands.Transform.__class_getitem__((to, cls))

    return decorator
