# Copyright (c) 2019, Riverbank Computing Limited
# All rights reserved.
#
# This copy of SIP is licensed for use under the terms of the SIP License
# Agreement.  See the file LICENSE for more details.
#
# This copy of SIP may also used under the terms of the GNU General Public
# License v2 or v3 as published by the Free Software Foundation which can be
# found in the files LICENSE-GPL2 and LICENSE-GPL3 included in this package.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.


from argparse import ArgumentParser
from sipbuild import handle_exception

from ..version import PYQTBUILD_VERSION_STR

from .bundle import bundle


def main():
    """ Bundle Qt with a wheel. """

    # Parse the command line.
    parser = ArgumentParser(
            description="Bundle a Qt installation with a wheel.")

    parser.add_argument('-V', '--version', action='version',
            version=PYQTBUILD_VERSION_STR)

    parser.add_argument('--qt-dir', metavar='DIR', required=True,
            help="the Qt installation in DIR to be bundled with the wheel")

    parser.add_argument(dest='wheels', nargs=1, help="the wheel to update",
            metavar="wheel")

    # TODO: --build-tag
    # TODO: OpenSSL DLLs and MSVC runtime DLLs.

    args = parser.parse_args()

    try:
        bundle(wheel=args.wheels[0], qt_dir=args.qt_dir)
    except Exception as e:
        handle_exception(e)

    return 0