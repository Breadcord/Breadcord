from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from rich.text import Text
from textual import app, binding, containers, widgets

from breadcord.app.widgets import BetterHeader, TableLog
from breadcord.bot import Bot

if TYPE_CHECKING:
    from argparse import Namespace

_logger = logging.getLogger('breadcord.app')


class TUIHandler(logging.Handler):
    def __init__(self, tui_app: Breadcord):
        super().__init__()
        self.tui = tui_app
        self._record_id = 0

    def allocate_id(self) -> int:
        allocated = self._record_id
        self._record_id += 1
        return allocated

    def emit(self, record: logging.LogRecord) -> None:
        self.format(record)
        self.tui.output_log.add_record(self.allocate_id(), record)


class Breadcord(app.App):
    CSS_PATH = 'app.tcss'
    BINDINGS = [
        binding.Binding(key='ctrl+c', action='quit', description='Quit', priority=True)
    ]

    def __init__(self, args: Namespace) -> None:
        super().__init__()
        self.bot = Bot(tui_app=self, args=args)
        self.handler = TUIHandler(self)
        self.output_log: TableLog | None = None
        self._online = False

    def compose(self) -> app.ComposeResult:
        header = BetterHeader(id='header', show_clock=True)
        yield header

        self.output_log = TableLog(id='output_log')
        yield self.output_log

        yield containers.Horizontal(
            widgets.Static('❯', id='input_prompt'),
            widgets.Input(id='input', placeholder='Type your command here...'),
            id='input_container'
        )

        yield widgets.Footer()

    def on_mount(self) -> None:
        self.online = False
        self.query_one('#input').focus()

        async def start_bot() -> None:
            # noinspection PyBroadException
            try:
                await self.bot.start()
            except Exception:
                sys.excepthook(*sys.exc_info())

        self.run_worker(start_bot(), exclusive=True)

    @property
    def online(self) -> bool:
        return self._online

    @online.setter
    def online(self, value: bool) -> None:
        if value:
            sub_text = Text('Online ', self.get_css_variables()['success'])
        else:
            sub_text = Text('Offline', self.get_css_variables()['error'])
        self.query_one('HeaderTitle').sub_text = sub_text
        self._online = value

    async def on_input_submitted(self, message: widgets.Input.Submitted) -> None:
        # TODO: Implement console commands
        ...
