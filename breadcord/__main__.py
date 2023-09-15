import argparse
from pathlib import Path

from breadcord import Bot

parser = argparse.ArgumentParser(prog='breadcord')
parser.add_argument(
    '-d', '--data',
    type=Path,
    help='specify an alternative data directory to load from',
    metavar='<path>',
)
parser.add_argument(
    '-m', '--module',
    nargs='+',
    default=[],
    type=Path,
    help='specify an additional module path to load from',
    metavar='<path>',
    dest='module_paths',
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
