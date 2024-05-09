import argparse
import random
import zipfile
from collections import deque
from pathlib import Path

from rich.console import Console
from rich.markup import escape

from breadcord.config import load_toml
from breadcord.module import parse_manifest

console = Console()

try:
    from gitignore_parser import parse_gitignore
except ImportError:
    console.print(
        '[red]! gitignore_parser dependency missing. Did you install dev dependencies?\n'
        '  $ [bold bright_red]python -m pip install breadcord[dev]',
    )
    raise SystemExit(1) from None

BREAD = '🍞🥐🥖🥪🫓🥙'

parser = argparse.ArgumentParser(description='Build an unpacked Breadcord module into a .loaf file.')
parser.add_argument('path', nargs='?', type=Path, default=Path())


def build(module_path: Path) -> None:
    build_string = f'[bold yellow]Building module... [bright_black]({escape(str(module_path))})'
    console.print(build_string)

    with console.status(build_string, spinner='dots', spinner_style='blue'):
        manifest_file = module_path / 'manifest.toml'
        if not manifest_file.is_file():
            console.print('[red]! manifest.toml file not found')
            raise SystemExit(1)

        manifest = parse_manifest(load_toml(manifest_file))
        console.print(f'[blue]* Manifest loaded for module: [bold cyan]{escape(manifest.id)}')

        if (loafignore_path := module_path / '.loafignore').is_file():
            should_ignore = parse_gitignore(loafignore_path)
            console.print('[blue]* .loafignore file loaded')
        else:
            console.print('[yellow]! .loafignore file not found, including all files')
            should_ignore = lambda _: False  # noqa: E731

        console.print('[blue]* Adding source files:')
        dist_path = module_path / 'dist'
        dist_path.mkdir(exist_ok=True)
        output_path = dist_path / f'{manifest.id}-{manifest.version}.loaf'

        try:
            with zipfile.ZipFile(file=output_path, mode='w', compression=zipfile.ZIP_LZMA) as archive:
                file_queue = deque(module_path.iterdir())
                while file_queue:
                    file = file_queue.popleft()

                    if should_ignore(file.as_posix()) or file == output_path:
                        zip_bomb_warning = '[bright_magenta] (oops, zip bomb!)' if file == output_path else ''
                        console.print(f'[blue]│ [red]- {escape(str(file.relative_to(module_path)))}{zip_bomb_warning}')
                        continue

                    if file.is_dir():
                        file_queue.extendleft(file.iterdir())

                    console.print(f'[blue]│ [green]+ {escape(str(file.relative_to(module_path)))}')
                    archive.write(file, arcname=file.relative_to(module_path))

        except BaseException:
            console.print('[blue]X [red]Build interrupted, deleting build output')
            if output_path.is_file():
                output_path.unlink()
            raise

        console.print('[blue]* Build complete')

    bread = random.choice(BREAD) * 3
    console.print(f'\n[bold green]{bread} Successfully built dist/[bright_green]{escape(output_path.name)}[/] {bread}')


if __name__ == '__main__':
    args = parser.parse_args()
    try:
        build(module_path=args.path.resolve())
    except KeyboardInterrupt as error:
        console.print('[red]! Keyboard interrupt received')
        raise SystemExit(1) from error
