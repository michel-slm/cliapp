# Copyright 2011  Lars Wirzenius
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


import logging
import optparse
import os
import re
import sys


class Application(object):

    '''A framework for Unix-like command line programs.
    
    This is a Python framework for writing Unix command line utilities.
    This base class contains logic to do the typical things
    a command line program should do:

    * parse command line options
    * iterate over input files
      - read from stdin if there are no named files
      - also recognize '-' as a name for stdin
    * write output to stdout
      - or a file named with --output option

    The user should subclass the base class for each application.
    The subclass does not need code for the mundane, boilerplate
    parts that are the same in every utility, and can concentrate on the 
    interesting part that is unique to it.

    Many programs need to adjust some parts of this typical scenario.
    For example, the non-option command line arguments might not be
    filenames, but URLs. The framework allows the user to override
    the necessary parts for this, but re-use all parts that do not need
    to be changed.
    
    To start the application, call the `run` method.
    
    The framework defines some options: --help, --output, --log,
    --log-level, perhaps others if this docstring has not been
    updated properly. Run application with --help to see the list of
    options.
    
    The application can define more options, which are called settings,
    in preparation for configuration file support. See the
    add_string_setting, add_string_list_setting, add_choice_setting,
    add_integer_setting, and add_boolean_setting methods. Each setting
    has a name and a mandatory help text, and can have a default value.
    
    Logging support: by default, no log file is written, it must be
    requested explicitly by the user. The default log level is info.
    
    Profiling support: if sys.argv[0] is 'foo', and the environment
    variable 'FOO_PROFILE' is set, then the execution of the 
    application (the 'run' method) is profiled, using cProfile, and
    the profile written to the file named in the environment variable.
    
    '''

    def __init__(self, progname=None, version='0.0.0'):
        self.progname = progname
        self.version = version
        self.fileno = 0
        self.global_lineno = 0
        self.lineno = 0
        self._init_parser()
        
    def _init_parser(self):
        '''Initialize the option parser with default options and values.'''
        self.parser = optparse.OptionParser(version=self.version,
                                            prog=self.progname)
        
        self.add_string_setting(['output'], 
                                'write output to named file, '
                                    'instead of standard output')

        self.add_string_setting(['log'], 'write log entries to file')
        self.add_string_setting(['log-level'], 
                                'log at given level, one of '
                                    'debug, info, warning, error, critical, '
                                    'fatal (default: %default)',
                                default='info')

        self.add_callback_setting(['dump-setting-names'],
                                  'write out all names of settings and quit',
                                  self._dump_setting_names, nargs=0)

    def _dump_setting_names(self): # pragma: no cover
        for option in self.parser.option_list:
            if option.dest:
                print option.dest
            else:
                x = option._long_opts[0]
                if x.startswith('--'):
                    x = x[2:]
                print x
        sys.exit(0)

    def _option_names(self, names):
        '''Turn setting names into option names.
        
        Names with a single letter are short options, and get prefixed
        with one dash. The rest get prefixed with two dashes.
        
        '''

        return ['--%s' % name if len(name) > 1 else '-%s' % name
                for name in names]

    def _attr_name(self, name):
        '''Turn setting name into attribute name.
        
        Dashes get turned into underscores.
        
        '''

        return '_'.join(name.split('-'))

    def _set_default_value(self, names, value):
        '''Set default value for a setting with names in names.'''
        self.parser.set_default(self._attr_name(names[0]), value)

    def add_string_setting(self, names, help, default=''):
        '''Add a setting with a string value.'''
        self.parser.add_option(*self._option_names(names), 
                               action='store', 
                               help=help)
        self._set_default_value(names, default)

    def add_string_list_setting(self, names, help, default=None):
        '''Add a setting which have multiple string values.
        
        An example would be an option that can be given multiple times
        on the command line, e.g., "--exclude=foo --exclude=bar".
        
        '''

        self.parser.add_option(*self._option_names(names), 
                               action='append', 
                               help=help)
        self._set_default_value(names, default or [])

    def add_choice_setting(self, names, possibilities, help, default=None):
        '''Add a setting which chooses from list of acceptable values.
        
        An example would be an option to set debugging level to be
        one of a set of accepted names: debug, info, warning, etc.
        
        The default value is the first possibility.
        
        '''

        self.parser.add_option(*self._option_names(names), 
                               action='store', 
                               type='choice',
                               choices=possibilities,
                               help=help)
        self._set_default_value(names, possibilities[0])

    def add_boolean_setting(self, names, help, default=False):
        '''Add a setting with a boolean value (defaults to false).'''
        self.parser.add_option(*self._option_names(names), 
                               action='store_true', 
                               help=help)
        self._set_default_value(names, default)

    def add_callback_setting(self, names, help, callback, nargs=1, 
                             default=None):
        '''Add a setting processed by a callback. 
        
        The callback will receive nargs argument strings, and will return
        the actual value of the setting.
        
        '''
        
        def callback_wrapper(option, opt_str, value, parser):
            if type(value) == str:
                value = (value,)
            setattr(parser.values, option.dest, callback(*value))

        self.parser.add_option(*self._option_names(names), 
                               action='callback',
                               callback=callback_wrapper,
                               nargs=nargs,
                               type='string',
                               help=help)
        self._set_default_value(names, default)

    def _parse_human_size(self, size):
        '''Parse a size using suffix into plain bytes.'''
        
        m = re.match(r'''(?P<number>\d+(\.\d+)?) \s* 
                         (?P<unit>k|ki|m|mi|g|gi|t|ti)? b? \s*$''',
                     size.lower(), flags=re.X)
        if not m:
            return 0
        else:
            number = float(m.group('number'))
            unit = m.group('unit')
            units = {
                'k': 10**3,
                'm': 10**6,
                'g': 10**9,
                't': 10**12,
                'ki': 2**10,
                'mi': 2**20,
                'gi': 2**30,
                'ti': 2**40,
            }
            return int(number * units.get(unit, 1))

    def add_bytesize_setting(self, names, help, default=0):
        '''Add a setting with a size in bytes.
        
        The user can use suffixes for kilo/mega/giga/tera/kibi/mibi/gibi/tibi.
        
        '''

        self.add_callback_setting(names, help, self._parse_human_size,
                                  default=default, nargs=1)

    def add_integer_setting(self, names, help, default=None):
        '''Add an integer setting.'''

        self.parser.add_option(*self._option_names(names), 
                               action='store',
                               type='long',
                               help=help)
        self._set_default_value(names, default)

    def get_setting(self, name):
        '''Return value of setting with a given name.
        
        Note that you may only call this method after the command line
        has been parsed.
        
        '''

        option = self.parser.get_option(self._option_names([name])[0])
        return getattr(self.options, option.dest)

    def __getitem__(self, setting_name):
        return self.get_setting(setting_name)
        
    def add_settings(self):
        '''Add application specific settings.'''

    def run(self, args=None, stderr=sys.stderr, sysargv=sys.argv):
        '''Run the application.'''
        
        def run_it():
            self._run(args=args, stderr=stderr)

        if self.progname is None and sysargv:
            self.progname = sysargv[0]
            self.parser.prog = self.progname
        envname = '%s_PROFILE' % self._envname(self.progname)
        profname = os.environ.get(envname, '')
        if profname: # pragma: no cover
            import cProfile
            cProfile.runctx('run_it()', globals(), locals(), profname)
        else:
            run_it()

    def _envname(self, progname):
        '''Create an environment variable name of the name of a program.'''
        
        basename = os.path.basename(progname)
        if '.' in basename:
            basename = basename.split('.')[0]
        
        ok = 'abcdefghijklmnopqrstuvwxyz0123456789'
        ok += ok.upper()
        
        return ''.join(x.upper() if x in ok else '_' for x in basename)

    def _run(self, args=None, stderr=sys.stderr):
        try:
            self.add_settings()
            args = sys.argv[1:] if args is None else args
            args = self.parse_args(args)
            
            self.setup_logging()
            
            if self.options.output:
                self.output = open(self.options.output, 'w')
            else:
                self.output = sys.stdout
            
            self.process_args(args)
        except SystemExit, e:
            sys.exit(e.code)
        except KeyboardInterrupt, e:
            sys.exit(255)
        except Exception, e:
            stderr.write('%s\n' % str(e))
            sys.exit(1)
        
    def setup_logging(self): # pragma: no cover
        '''Set up logging.'''
        
        if self.options.log:
            level_name = self.options.log_level
            levels = {
                'debug': logging.DEBUG,
                'info': logging.INFO,
                'warning': logging.WARNING,
                'error': logging.ERROR,
                'critical': logging.CRITICAL,
                'fatal': logging.FATAL,
            }
            level = levels.get(level_name, logging.INFO)
            
            logging.basicConfig(filename=self.options.log,
                                level=level)

    def parse_args(self, args):
        '''Parse the command line.
        
        Set self.options to a value like the options returned by
        OptionParser. Return list of non-option arguments.
        
        '''

        self.options, args = self.parser.parse_args(args)
        return args

    def process_args(self, args):
        '''Process command line non-option arguments.
        
        The default is to call process_inputs with the argument list.
        
        '''
        
        self.process_inputs(args)

    def process_inputs(self, args):
        '''Process all arguments as input filenames.
        
        The default implementation calls process_input for each
        input filename. If no filenames were given, then 
        process_input is called with '-' as the argument name.
        This implements the usual Unix command line practice of
        reading from stdin if no inputs are named.
        
        The attributes fileno, global_lineno, and lineno are set,
        and count files and lines. The global line number is the
        line number as if all input files were one.
        
        '''

        for arg in args or ['-']:
            self.process_input(arg)

    def open_input(self, name, mode='r'):
        '''Open an input file for reading.
        
        The default behaviour is to open a file named on the local
        filesystem. A subclass might override this behavior for URLs,
        for example.
        
        The optional mode argument speficies the mode in which the file
        gets opened. It should allow reading. Some files should perhaps
        be opened in binary mode ('rb') instead of the default text mode.
        
        '''
        
        if name == '-':
            return sys.stdin
        else:
            return open(name, mode)

    def process_input(self, name, stdin=sys.stdin):
        '''Process a particular input file.'''

        self.fileno += 1
        self.lineno = 0
        f = self.open_input(name)
        for line in f:
            self.global_lineno += 1
            self.lineno += 1
            self.process_input_line(name, line)
        if f != stdin:
            f.close()

    def process_input_line(self, name, f):
        '''Process one line of the input file.
        
        Applications that are line-oriented can redefine only this method in
        a subclass, and should not need to care about the other methods.
        
        '''
        

