# Copyright (c) 2019, Riverbank Computing Limited
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
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


import os
import sys

from sipbuild import (Buildable, BuildableModule, Builder, Option, Project,
        PyProjectOptionException, UserException)

from .installable import QmakeTargetInstallable


class QmakeBuilder(Builder):
    """ A project builder that uses qmake as the underlying build system. """

    def apply_defaults(self, tool):
        """ Set default values for options that haven't been set yet. """

        if tool == 'sdist':
            # Make sure all documented attributes have a value even if they are
            # not applicalbe in this context.
            self.qt_version = 0
            self.qt_version_tag = ''
        else:
            # Check we have a qmake.
            if self.qmake is None:
                self.qmake = self._find_exe('qmake')
                if self.qmake is None:
                    raise PyProjectOptionException('qmake',
                            "specify a working qmake or add it to PATH")
            elif not self._is_exe(self.qmake):
                raise PyProjectOptionException('qmake',
                        "'{0}' is not a working qmake".format(self.qmake))

            self.qmake = self.quote(os.path.abspath(self.qmake))

            # Use qmake to get the Qt configuration.  We do this now before
            # Project.update() is called.
            self._get_qt_configuration()

            # Now apply defaults for any options that depend on the Qt
            # configuration.
            if self.spec is None:
                self.spec = self.qt_configuration['QMAKE_SPEC']

                # The binary OS/X Qt installer used to default to XCode.  If so
                # then use macx-clang.
                if self.spec == 'macx-xcode':
                    # This will exist (and we can't check anyway).
                    self.spec = 'macx-clang'

        super().apply_defaults(tool)

    def build_project(self, target_dir, wheel=None):
        """ Build the project. """

        project = self.project

        # Create the .pro file for each set of bindings.
        installed = []
        subdirs = []

        for buildable in project.buildables:
            if isinstance(buildable, BuildableModule):
                self._generate_module_pro_file(buildable, target_dir,
                        installed)
            elif type(buildable) is Buildable:
                for installable in buildable.installables:
                    installable.install(target_dir, installed,
                            do_install=False)
            else:
                raise UserException(
                        "QmakeBuilder cannot build '{0}' buildables".format(
                                type(buildable).__name__))

            subdirs.append(buildable.name)

        # Create the top-level .pro file.
        project.progress("Generating the top-level .pro file")

        pro_lines = []

        pro_lines.append('TEMPLATE = subdirs')
        pro_lines.append('CONFIG += ordered nostrip')
        pro_lines.append('SUBDIRS = {}'.format(' '.join(subdirs)))

        # Add any project-level installables.
        for installable in project.installables:
            self._install(pro_lines, installed, installable, target_dir)

        # Make the .dist-info directory.
        inventory_fn = os.path.join(project.build_dir, 'inventory.txt')
        inventory = project.open_for_writing(inventory_fn)

        for fn in installed:
            print(fn, file=inventory)

        inventory.close()

        args = ['sip-distinfo']

        args.append('--project-root')
        args.append(project.root_dir)

        args.append('--generator')
        args.append(os.path.basename(sys.argv[0]))

        args.append('--prefix')
        args.append('\\"$(INSTALL_ROOT)\\"')

        args.append('--inventory')
        args.append(inventory_fn)

        if wheel is not None:
            args.append('--wheel-tag')
            args.append(wheel.tag)

        for ep in project.console_scripts:
            args.append('--console-script')
            args.append(ep.replace(' ', ''))

        args.append(self.qmake_quote(project.get_distinfo_name(target_dir)))

        pro_lines.append('distinfo.extra = {}'.format(' '.join(args)))
        pro_lines.append(
                'distinfo.path = {}'.format(self.qmake_quote(target_dir)))
        pro_lines.append('INSTALLS += distinfo')

        pro_name = os.path.join(project.build_dir, project.name + '.pro')
        self._write_pro_file(pro_name, pro_lines)

        # Run qmake to generate the Makefiles.
        project.progress("Generating the Makefiles")
        self.run_qmake(pro_name, recursive=True)

        # Run make, if requested, to generate the bindings.
        if self.make:
            self._run_project_make()

        return None

    def get_options(self):
        """ Return the sequence of configurable options. """

        # Get the standard options.
        options = super().get_options()

        # Add our new options.
        options.append(
                Option('make', option_type=bool, inverted=True,
                        help="do not run make or nmake", tools='build'))

        options.append(
                Option('qmake', help="the pathname of qmake is FILE",
                        metavar="FILE", tools='build install wheel'))

        options.append(
                Option('qmake_settings', option_type=list,
                        help="add the 'NAME += VALUE' setting to any .pro file",
                        metavar="'NAME += VALUE'",
                        tools='build install wheel'))

        options.append(
                Option('spec', help="pass -spec SPEC to qmake",
                        metavar="SPEC", tools='build install wheel'))

        return options

    def install_project(self, target_dir, wheel=None):
        """ Install the project into a target directory. """

        # Run make install to install the bindings.
        self._run_project_make(install=True)

    @staticmethod
    def qmake_quote(path):
        """ Return a path quoted for qmake if it contains spaces. """

        # Also convert to Unix path separators.
        path = path.replace('\\', '/')

        if ' ' in path:
            path = '$$quote({})'.format(path)

        return path

    @staticmethod
    def quote(path):
        """ Return a path with quotes added if it contains spaces. """

        if ' ' in path:
            path = '"{}"'.format(path)

        return path

    def run_make(self, exe, makefile_name, debug, fatal=True):
        """ Run make against a Makefile to create an executable.  Returns the
        platform specific name of the executable, or None if an executable
        wasn't created.
        """

        project = self.project

        # Guess the name of make and set the default target and platform
        # specific name of the executable.
        if project.py_platform == 'win32':
            if debug:
                makefile_target = 'debug'
                platform_exe = os.path.join('debug', exe + '.exe')
            else:
                makefile_target = 'release'
                platform_exe = os.path.join('release', exe + '.exe')
        else:
            makefile_target = None

            if project.py_platform == 'darwin':
                platform_exe = os.path.join(exe + '.app', 'Contents', 'MacOS',
                        exe)
            else:
                platform_exe = os.path.join('.', exe)

        # Make sure the executable doesn't exist.
        self._remove_file(platform_exe)

        args = [self._find_make(), '-f', makefile_name]

        if makefile_target is not None:
            args.append(makefile_target)

        project.run_command(args, fatal=fatal)

        return platform_exe if os.path.isfile(platform_exe) else None

    def run_qmake(self, pro_name, makefile_name=None, fatal=True,
            recursive=False):
        """ Run qmake against a .pro file.  fatal is set if a qmake failure is
        considered a fatal error, otherwise False is returned if qmake fails.
        """

        # qmake doesn't behave consistently if it is not run from the directory
        # containing the .pro file - so make sure it is.
        pro_dir, pro_file = os.path.split(pro_name)
        if pro_dir != '':
            cwd = os.getcwd()
            os.chdir(pro_dir)
        else:
            cwd = None

        # Make sure the Makefile doesn't exist.
        mf_name = 'Makefile' if makefile_name is None else makefile_name
        self._remove_file(mf_name)

        # Build the command line.
        args = [self.qmake]

        # If the spec is the same as the default then we don't need to specify
        # it.
        if self.spec != self.qt_configuration['QMAKE_SPEC']:
            args.append('-spec')
            args.append(self.spec)

        if makefile_name is not None:
            args.append('-o')
            args.append(makefile_name)

        if recursive:
            args.append('-recursive')

        args.append(pro_file)

        self.project.run_command(args, fatal=fatal)

        # Check that the Makefile was created.
        if not os.path.isfile(mf_name):
            if fatal:
                raise UserException(
                        "{0} failed to create a makefile from {1}".format(
                                self.qmake, pro_name))

            return False

        # Restore the current directory.
        if cwd is not None:
            os.chdir(cwd)

        return True

    @classmethod
    def _find_exe(cls, exe):
        """ Find an executable, ie. the first on the path. """

        if sys.platform == 'win32':
            exe += '.exe'

        for d in os.environ.get('PATH', '').split(os.pathsep):
            exe_path = os.path.join(d, exe)

            if cls._is_exe(exe_path):
                return exe_path

        return None

    def _find_make(self):
        """ Return the name of a valid make program. """

        if self.project.py_platform == 'win32':
            if self.spec == 'win32-g++':
                make = 'mingw32-make'
            else:
                make = 'nmake'
        else:
            make = 'make'

        if self._find_exe(make) is None:
            raise UserException(
                    "'{0}' could not be found on PATH".format(make))

        return make

    def _generate_module_pro_file(self, buildable, target_dir, installed):
        """ Generate the .pro file for an extension module.  The list of
        installed files is updated.
        """

        project = self.project

        project.progress(
                "Generating the .pro file for the {0} module".format(
                            buildable.target))

        buildable.make_names_relative()

        pro_lines = ['TEMPLATE = lib']

        pro_lines.append('CONFIG += warn_on exceptions_off')

        if buildable.static:
            pro_lines.append('CONFIG += staticlib hide_symbols')
        else:
            # Note some version of Qt5 (probably incorrectly) implements
            # 'plugin_bundle' instead of 'plugin' so we specify both.
            pro_lines.append('CONFIG += plugin plugin_bundle')

        pro_lines.append(
                'CONFIG += {}'.format(
                        'debug' if buildable.debug else 'release'))

        if project.qml_debug:
            pro_lines.append('CONFIG += qml_debug')

        # Work around QTBUG-39300.
        pro_lines.append('CONFIG -= android_install')

        # Add any buildable-specific settings.
        pro_lines.extend(buildable.builder_settings)

        # Add any user-supplied settings.
        pro_lines.extend(self.qmake_settings)

        pro_lines.append('TARGET = {}'.format(buildable.target))

        # Qt (when built with MinGW) assumes that stack frames are 16 byte
        # aligned because it uses SSE.  However the Python Windows installers
        # are built with 4 byte aligned stack frames.  We therefore need to
        # tweak the g++ flags to deal with it.
        if self.spec == 'win32-g++':
            pro_lines.append('QMAKE_CFLAGS += -mstackrealign')
            pro_lines.append('QMAKE_CXXFLAGS += -mstackrealign')

        # Get the name of the extension module file.
        module = buildable.target

        if project.py_platform == 'win32' and project.py_debug:
            module += '_d'

        module += buildable.get_module_extension()

        if not buildable.static:
            # Without the 'no_check_exist' magic the target.files must exist
            # when qmake is run otherwise the install and uninstall targets are
            # not generated.
            shared = '''
win32 {
    PY_MODULE_SRC = $(DESTDIR_TARGET)
} else {
    macx {
        PY_MODULE_SRC = $(TARGET).plugin/Contents/MacOS/$(TARGET)
        QMAKE_LFLAGS += "-undefined dynamic_lookup"
    } else {
        PY_MODULE_SRC = $(TARGET)
    }
}

QMAKE_POST_LINK = $(COPY_FILE) $$PY_MODULE_SRC %s

target.CONFIG = no_check_exist
target.files = %s
''' % (module, module)

            pro_lines.extend(shared.split('\n'))

        buildable.installables.append(
                QmakeTargetInstallable(module, buildable.get_install_subdir()))

        # This optimisation could apply to other platforms.
        if 'linux' in self.spec and not buildable.static:
            exp = project.open_for_writing(
                    os.path.join(buildable.build_dir, buildable.name + '.exp'))
            exp.write('{ global: PyInit_%s; local: *; };' % buildable.name)
            exp.close()

            pro_lines.append(
                    'QMAKE_LFLAGS += -Wl,--version-script={}.exp'.format(
                            buildable.name))

        # Handle any #define macros.
        if buildable.define_macros:
            pro_lines.append('DEFINES += {}'.format(
                    ' '.join(buildable.define_macros)))

        # Handle the include directories.
        for include_dir in buildable.include_dirs:
            pro_lines.append(
                    'INCLUDEPATH += {}'.format(self.qmake_quote(include_dir)))

        pro_lines.append(
                'INCLUDEPATH += {}'.format(
                        self.qmake_quote(project.py_include_dir)))

        # Python.h on Windows seems to embed the need for pythonXY.lib, so tell
        # it where it is.
        # TODO: is this still necessary for Python v3.8?
        if not buildable.static:
            pro_lines.extend(['win32 {',
                    '    LIBS += -L{}'.format(project.py_pylib_dir),
                    '}'])

        # Handle any additional libraries.
        libs = []

        for l_dir in buildable.library_dirs:
            libs.append('-L' + self.qmake_quote(l_dir))

        for l in buildable.libraries:
            libs.append('-l' + l)

        if libs:
            pro_lines.append('LIBS += {}'.format(' '.join(libs)))

        headers = [self.qmake_quote(f) for f in buildable.headers]
        pro_lines.append('HEADERS = {}'.format(' '.join(headers)))

        sources = [self.qmake_quote(f) for f in buildable.sources]
        pro_lines.append('SOURCES = {}'.format(' '.join(sources)))

        # Add any installables from the buildable.
        for installable in buildable.installables:
            self._install(pro_lines, installed, installable, target_dir)

        # Write the .pro file.
        self._write_pro_file(
                os.path.join(buildable.build_dir, buildable.name + '.pro'),
                pro_lines)

    def _get_qt_configuration(self):
        """ Run qmake to get the details of the Qt configuration. """

        project = self.project

        project.progress("Querying qmake about your Qt installation")

        self.qt_configuration = {}

        for line in project.read_command_pipe(self.qmake + ' -query'):
            line = line.strip()

            tokens = line.split(':', maxsplit=1)
            if isinstance(tokens, list):
                if len(tokens) != 2:
                    raise UserException(
                            "Unexpected output from qmake: '{0}'".format(line))

                name, value = tokens
            else:
                name = tokens
                value = None

            name = name.replace('/', '_')

            self.qt_configuration[name] = value

        # Get the Qt version.
        self.qt_version = 0
        try:
            qt_version_str = self.qt_configuration['QT_VERSION']
            for v in qt_version_str.split('.'):
                self.qt_version <<= 8
                self.qt_version += int(v)
        except AttributeError:
            qt_version_str = "3"

        # Requiring Qt v5.6 allows us to drop some old workarounds.
        if self.qt_version < 0x050600:
            raise UserException(
                    "Qt v5.6 or later is required and you seem to be using "
                            "v{0}".format(qt_version_str))

        # Convert the version number to what would be used in a tag.
        major = (self.qt_version >> 16) & 0xff
        minor = (self.qt_version >> 8) & 0xff
        patch = self.qt_version & 0xff

        # Qt v5.12.4 was the last release where we updated for a patch version.
        if (major, minor) >= (5, 13):
            patch = 0
        elif (major, minor) == (5, 12):
            if patch > 4:
                patch = 4

        self.qt_version_tag = '{}_{}_{}'.format(major, minor, patch)

    def _install(self, pro_lines, installed, installable, target_dir):
        """ Add the lines to install files to a .pro file and a list of all
        installed files.
        """

        installable.install(target_dir, installed, do_install=False)

        pro_lines.append(
                '{}.path = {}'.format(installable.name,
                        installable.get_full_target_dir(target_dir).replace(
                                '\\', '/')))

        if not isinstance(installable, QmakeTargetInstallable):
            files = [fn.replace('\\', '/') for fn in installable.files]
            pro_lines.append(
                    '{}.files = {}'.format(installable.name, ' '.join(files)))

        pro_lines.append('INSTALLS += {}'.format(installable.name))

    @staticmethod
    def _is_exe(exe_path):
        """ Return True if an executable exists. """

        return os.access(exe_path, os.X_OK)

    @staticmethod
    def _remove_file(fname):
        """ Remove a file which may or may not exist. """

        try:
            os.remove(fname)
        except OSError:
            pass

    def _run_project_make(self, install=False):
        """ Run make on the project. """

        project = self.project

        project.progress(
                "{0} the project".format(
                        "Installing" if install else "Compiling"))

        make = self._find_make()

        args = [make]
        if install:
            args.append('install')

        saved_cwd = os.getcwd()
        os.chdir(project.build_dir)
        project.run_command(args)
        os.chdir(saved_cwd)

    def _write_pro_file(self, pro_fn, pro_lines):
        """ Write a .pro file. """

        pro = self.project.open_for_writing(pro_fn)
        pro.write('\n'.join(pro_lines))
        pro.write('\n')
        pro.close()