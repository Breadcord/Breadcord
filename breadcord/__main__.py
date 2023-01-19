import argparse
from pathlib import Path

from breadcord import Bot

parser = argparse.ArgumentParser(prog='Breadcord')
parser.add_argument(
    '-i', '--include',
    nargs='+',
    type=Path,
    help='include additional modules to discover and load from',
    metavar='<module_path>'
)

bot = Bot(args=parser.parse_args())

if __name__ == '__main__':
    bot.run()
