from __future__ import annotations

import logging
import sys
from asyncio import CancelledError
from typing import TYPE_CHECKING

from rich.text import Text
from textual import app, binding, widgets, work, worker

from breadcord.app.widgets import BetterHeader, TableLog, ColouredHeaderTitle
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
        binding.Binding(key='ctrl+c', action='quit', description='Quit', priority=True),
        binding.Binding(key='ctrl+p', action='toggle_bot', description='Toggle Bot On/Off')
    ]

    def __init__(self, args: Namespace) -> None:
        super().__init__()
        self.args = args
        self.handler = TUIHandler(self)
        self.output_log: TableLog | None = None
        self.bot_worker: worker.Worker | None = None
        self._online = False

    def compose(self) -> app.ComposeResult:
        header = BetterHeader(id='header', show_clock=True)
        yield header

        self.output_log = TableLog(id='output_log')
        yield self.output_log

        yield widgets.Footer()

    def on_mount(self) -> None:
        self.online = False
        self.bot_worker = self.start_bot()

    @property
    def online(self) -> bool:
        return self._online

    @online.setter
    def online(self, value: bool) -> None:
        # noinspection PyTypeChecker
        header_title = self.query_one('HeaderTitle', expect_type=ColouredHeaderTitle)
        previous = 'Offline' if isinstance(header_title.sub_text, str) else header_title.sub_text.plain

        if value:
            sub_text = Text(current := 'Online ', self.get_css_variables()['success'])
            if previous != current:
                self.notify('Bot is online!', severity='information')
        else:
            sub_text = Text(current := 'Offline', self.get_css_variables()['error'])
            if previous != current:
                self.notify('Bot is offline!', severity='error')

        header_title.sub_text = sub_text
        self._online = value

    @work(exclusive=True)
    async def start_bot(self) -> None:
        bot = Bot(tui_app=self, args=self.args)
        try:
            await bot.start()
        except CancelledError:
            _logger.info('Interrupt received')
        except:  # noqa
            sys.excepthook(*sys.exc_info())
        finally:
            if not bot.is_closed():
                await bot.close()

    def on_worker_state_changed(self, event: worker.Worker.StateChanged) -> None:
        if event.worker is not self.bot_worker:
            return

        if event.state is not worker.WorkerState.RUNNING:
            self.online = False

    def action_toggle_bot(self) -> None:
        if self.bot_worker.state is worker.WorkerState.RUNNING:
            self.bot_worker.cancel()
        else:
            self.bot_worker = self.start_bot()
