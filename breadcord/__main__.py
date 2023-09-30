import argparse
from pathlib import Path

from breadcord import Bot

parser = argparse.ArgumentParser(prog='breadcord')
parser.add_argument(
    '-d', '--data',
    type=Path,
    help='specify an alternative data directory to load from',
    metavar='<path>',
    dest='data_dir',
)
parser.add_argument(
    '-l', '--logs',
    type=Path,
    help='specify an alternative directory to place logs in',
    metavar='<path>',
    dest='logs_dir',
)
parser.add_argument(
    '-s', '--storage',
    type=Path,
    help='specify an alternative directory for modules to store data in',
    metavar='<path>',
    dest='storage_dir',
)
parser.add_argument(
    '-c', '--settings', '--config',
    type=Path,
    help='specify an alternative settings file to load',
    metavar='<path>',
    dest='setting_file',
)
parser.add_argument(
    '-m', '--module',
    nargs='+',
    default=[],
    type=Path,
    help='specify an additional module path to load from',
    metavar='<path>',
    dest='module_dirs',
)
parser.add_argument(
    '-u', '--no-ui',
    action='store_false',
    help="don't use the visual user interface",
    dest='ui',
)
args = parser.parse_args()

if args.ui:
    from breadcord.app import Breadcord
    app = Breadcord(args=args)
else:
    app = Bot(args=args)

if __name__ == '__main__':
    app.run()
