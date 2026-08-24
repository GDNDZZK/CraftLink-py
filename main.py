import argparse
import asyncio
import sys

from core import ModManager
from server import CraftLinkServer

MODS_DIR = "mods"
PROGRAM = "CraftLink-py"
AUTHOR = "GDNDZZK"
YEAR = "2026"

NOTICE = (
    f"{PROGRAM}  Copyright (C) {YEAR}  {AUTHOR}\n"
    "This program comes with ABSOLUTELY NO WARRANTY; for details type 'show w'.\n"
    "This is free software, and you are welcome to redistribute it\n"
    "under certain conditions; type 'show c' for details.\n"
)

SHOW_W = """\
15. Disclaimer of Warranty.

  THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

16. Limitation of Liability.

  IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
SUCH DAMAGES.
"""

SHOW_C = """\
This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

The complete license text is available in the LICENSE file of this project.
"""


def handle_show(argv):
    if not argv or argv[0] != "show":
        return False
    if len(argv) == 2 and argv[1] in ("w", "c"):
        print(SHOW_W if argv[1] == "w" else SHOW_C)
        raise SystemExit(0)
    print("usage: main.py show [w|c]", file=sys.stderr)
    raise SystemExit(2)


def main():
    handle_show(sys.argv[1:])
    print(NOTICE)
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="CraftLink")
    args = parser.parse_args()
    mods = ModManager(MODS_DIR)
    mods.load_all()
    asyncio.run(CraftLinkServer(args.host, args.port, mods, args.token).serve_forever())


if __name__ == "__main__":
    main()
