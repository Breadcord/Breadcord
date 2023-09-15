from __future__ import annotations

from typing import TYPE_CHECKING

from rich.traceback import Traceback
from textual.strip import Strip
from textual.widgets import DataTable

from breadcord.app.screens import ExceptionModal

if TYPE_CHECKING:
    from logging import LogRecord
    from typing import ClassVar

    from rich.style import Style

    from breadcord.app.app import TUIHandler


class TableLog(DataTable):
    COMPONENT_CLASSES: ClassVar[set[str]] = {
        'tablelog--debug',
        'tablelog--info',
        'tablelog--warning',
        'tablelog--error',
        'tablelog--critical',
        'tablelog--unknown',
    }

    # noinspection ALL
    # language=SCSS
    DEFAULT_CSS = '''
    TableLog > .tablelog--debug {
        color: $accent;
    }

    TableLog > .tablelog--warning {
        color: $warning;
    }

    TableLog > .tablelog--error {
        color: $error;
    }

    TableLog > .tablelog--critical {
        background: $error;
    }

    TableLog > .tablelog--unknown {
        background: $accent;
    }
    '''

    def __init__(self, handler: TUIHandler, **kwargs):
        super().__init__(**kwargs)
        self.handler = handler
        self.add_column('Time', key='time')
        self.add_column('Level', key='level', width=8)
        self.add_column('Source', key='source')
        self.add_column('Message', key='message')

    def _render_line(self, y: int, x1: int, x2: int, base_style: Style) -> Strip:
        try:
            row_key, _ = self._get_offsets(y)
        except LookupError:
            return Strip.blank(self.size.width, base_style)

        if row_key.value is not None:
            component_class = f'tablelog--{self.get_row(row_key)[1].lower()}'
            if component_class not in self.COMPONENT_CLASSES:
                component_class = 'tablelog--unknown'
            base_style = self.get_component_rich_style(component_class)

        return super()._render_line(y, x1, x2, base_style)

    def add_record(self, record_id: int, record: LogRecord):
        self.add_row(
            record.asctime.split()[1],
            record.levelname,
            record.name,
            record.message,
            key=str(record_id),
            height=record.message.count('\n') + 1,
        )

        if round(self.max_scroll_y - self.scroll_y) <= 1:
            self.action_scroll_end()

    def on_data_table_cell_selected(self, event: DataTable.CellSelected):
        key = int(event.cell_key.row_key.value)
        if key in self.handler.exceptions:
            traceback = Traceback.from_exception(*self.handler.exceptions[key])
            self.app.push_screen(ExceptionModal(traceback))
