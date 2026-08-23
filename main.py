import argparse
import asyncio

from core import ModManager
from server import CraftLinkServer

MODS_DIR = "mods"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    mods = ModManager(MODS_DIR)
    mods.load_all()
    asyncio.run(CraftLinkServer(args.host, args.port, mods).serve_forever())


if __name__ == "__main__":
    main()
