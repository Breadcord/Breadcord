import argparse
from pathlib import Path

from breadcord import Bot

parser = argparse.ArgumentParser(prog='breadcord')
parser.add_argument(
    '-d', '--data',
    type=Path,
    help='specify an alternative data directory to load from',
    metavar='<path>'
)

bot = Bot(args=parser.parse_args())

if __name__ == '__main__':
    bot.run()
