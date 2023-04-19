from collections import defaultdict
from typing import TypeVar, Callable, overload
from rapidfuzz.fuzz import partial_ratio_alignment

_T = TypeVar('_T')


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
