import argparse
from pathlib import Path

from breadcord import Bot
from breadcord.app import Breadcord

parser = argparse.ArgumentParser(prog='breadcord')
parser.add_argument(
    '-d', '--data',
    type=Path,
    help='specify an alternative data directory to load from',
    metavar='<path>'
)
parser.add_argument(
    '-u', '--no-ui',
    action='store_false',
    help="don't use the visual user interface",
    dest='ui'
)
args = parser.parse_args()

app = Breadcord(args=args)
bot = Bot(args=args)

if __name__ == '__main__':
    if args.ui:
        app.run()
    else:
        bot.run()
