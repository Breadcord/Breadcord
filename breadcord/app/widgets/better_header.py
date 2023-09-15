from rich.text import Text
from textual.app import RenderResult
from textual.events import Mount
from textual.widget import Widget

# noinspection PyProtectedMember
from textual.widgets._header import HeaderClock, HeaderClockSpace, HeaderTitle


class ColouredHeaderTitle(HeaderTitle):
    """Display the title / subtitle in the header, with better coloured text options."""

    def render(self) -> RenderResult:
        """Render the title and sub-title.

        :returns: The value to render.
        """
        text = Text(self.text, no_wrap=True, overflow='ellipsis')
        if self.sub_text:
            text = Text.assemble(text, (' — ', 'dim'), self.sub_text)
        return text


class BetterHeader(Widget):
    """A modified header widget to better suit my needs."""

    # noinspection ALL
    # language=SCSS
    DEFAULT_CSS = '''
    BetterHeader {
        dock: top;
        width: 100%;
        background: $foreground 5%;
        color: $text;
        height: 1;
    }
    '''

    # noinspection PyShadowingBuiltins
    def __init__(
        self,
        show_clock: bool = False,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        """Initialise the header widget.

        :param show_clock: ``True`` if the clock should be shown on the right of the header.
        :param name: The name of the header widget.
        :param id: The ID of the header widget in the DOM.
        :param classes: The CSS classes of the header widget.
        """
        super().__init__(name=name, id=id, classes=classes)
        self._show_clock = show_clock

    def compose(self):
        yield ColouredHeaderTitle()
        yield HeaderClock() if self._show_clock else HeaderClockSpace()

    def _on_mount(self, _: Mount) -> None:
        def set_title(title: str) -> None:
            self.query_one(HeaderTitle).text = title

        def set_sub_title(sub_title: str) -> None:
            self.query_one(HeaderTitle).sub_text = sub_title

        self.watch(self.app, 'title', set_title)
        self.watch(self.app, 'sub_title', set_sub_title)
