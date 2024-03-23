import argparse
import subprocess
from pathlib import Path

from tomlkit.toml_file import TOMLFile

SETTINGS_PATH = Path("data/settings.toml")


def set_token(token: str) -> None:
    if not token:
        raise ValueError('Token cannot be empty')

    settings = TOMLFile(SETTINGS_PATH).read()
    settings["token"] = token
    TOMLFile(SETTINGS_PATH).write(settings)


parser = argparse.ArgumentParser()
parser.add_argument('token', type=str)
parsed_args = parser.parse_args()

if __name__ == '__main__':
    process = subprocess.run(("python", "-m", "breadcord", '--no-ui'), timeout=10)
    set_token(parsed_args.token)
