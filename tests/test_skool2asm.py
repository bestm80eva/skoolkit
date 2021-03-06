import os
import unittest
from unittest.mock import patch, Mock

from skoolkittest import SkoolKitTestCase
import skoolkit
from skoolkit import skool2asm, SkoolKitError, VERSION
from skoolkit.config import COMMANDS
from skoolkit.skoolparser import BASE_10, BASE_16, CASE_LOWER, CASE_UPPER

def mock_run(*args):
    global run_args
    run_args = args

def mock_config(name):
    return {k: v[0] for k, v in COMMANDS[name].items()}

class MockSkoolParser:
    def __init__(self, skoolfile, case, base, asm_mode, warnings, fix_mode, html,
                 create_labels, asm_labels, min_address, max_address):
        global mock_skool_parser
        mock_skool_parser = self
        self.skoolfile = skoolfile
        self.case = case
        self.base = base
        self.asm_mode = asm_mode
        self.warnings = warnings
        self.fix_mode = fix_mode
        self.html = html
        self.create_labels = create_labels
        self.asm_labels = asm_labels
        self.min_address = min_address
        self.max_address = max_address
        self.properties = {}
        self.asm_writer_class = ''

class MockAsmWriter:
    def __init__(self, parser, properties):
        global mock_asm_writer
        mock_asm_writer = self
        self.parser = parser
        self.properties = properties
        self.wrote = False

    def write(self):
        self.wrote = True

class Skool2AsmTest(SkoolKitTestCase):
    def setUp(self):
        global mock_skool_parser, mock_asm_writer
        SkoolKitTestCase.setUp(self)
        mock_skool_parser = None
        mock_asm_writer = None

    @patch.object(skool2asm, 'run', mock_run)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_default_option_values(self):
        skoolfile = 'test.skool'
        skool2asm.main((skoolfile,))
        fname, options = run_args
        self.assertEqual(fname, skoolfile)
        self.assertFalse(options.quiet)
        self.assertIsNone(options.writer)
        self.assertEqual(options.case, 0)
        self.assertEqual(options.base, 0)
        self.assertEqual(options.asm_mode, 1)
        self.assertTrue(options.warn)
        self.assertEqual(options.fix_mode, 0)
        self.assertFalse(options.create_labels)
        self.assertEqual(options.start, 0)
        self.assertEqual(options.end, 65536)
        self.assertEqual(options.properties, [])
        self.assertEqual(options.params, [])

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_default_option_values_are_passed(self):
        skoolfile = 'test.skool'
        skool2asm.main((skoolfile,))

        self.assertEqual(mock_skool_parser.skoolfile, skoolfile)
        self.assertEqual(mock_skool_parser.case, 0)
        self.assertEqual(mock_skool_parser.base, 0)
        self.assertEqual(mock_skool_parser.asm_mode, 1)
        self.assertTrue(mock_skool_parser.warnings)
        self.assertEqual(mock_skool_parser.fix_mode, 0)
        self.assertFalse(mock_skool_parser.html)
        self.assertFalse(mock_skool_parser.create_labels)
        self.assertTrue(mock_skool_parser.asm_labels)
        self.assertEqual(mock_skool_parser.min_address, 0)
        self.assertEqual(mock_skool_parser.max_address, 65536)

        self.assertIs(mock_asm_writer.parser, mock_skool_parser)
        self.assertEqual({}, mock_asm_writer.properties)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'run', mock_run)
    def test_config_read_from_file(self):
        ini = '\n'.join((
            '[skool2asm]',
            'Base=16',
            'Case=1',
            'CreateLabels=1',
            'Quiet=1',
            'Set-bullet=-',
            'Set-indent=4',
            'Warnings=0'
        ))
        self.write_text_file(ini, 'skoolkit.ini')
        skoolfile = 'test.skool'
        skool2asm.main((skoolfile,))
        fname, options = run_args
        self.assertEqual(fname, skoolfile)
        self.assertTrue(options.quiet)
        self.assertIsNone(options.writer)
        self.assertEqual(options.case, 1)
        self.assertEqual(options.base, 16)
        self.assertEqual(options.asm_mode, 1)
        self.assertFalse(options.warn)
        self.assertEqual(options.fix_mode, 0)
        self.assertTrue(options.create_labels)
        self.assertEqual(options.start, 0)
        self.assertEqual(options.end, 65536)
        self.assertEqual(sorted(options.properties), ['bullet=-', 'indent=4'])

    @patch.object(skool2asm, 'run', mock_run)
    def test_invalid_option_values_read_from_file(self):
        ini = '\n'.join((
            '[skool2asm]',
            'Base=!',
            'Case=2',
            'Quiet=q'
        ))
        self.write_text_file(ini, 'skoolkit.ini')
        skoolfile = 'test.skool'
        skool2asm.main((skoolfile,))
        fname, options = run_args
        self.assertEqual(fname, skoolfile)
        self.assertFalse(options.quiet)
        self.assertIsNone(options.writer)
        self.assertEqual(options.case, 2)
        self.assertEqual(options.base, 0)
        self.assertEqual(options.asm_mode, 1)
        self.assertTrue(options.warn)
        self.assertEqual(options.fix_mode, 0)
        self.assertFalse(options.create_labels)
        self.assertEqual(options.start, 0)
        self.assertEqual(options.end, 65536)
        self.assertEqual(options.properties, [])

    def test_no_arguments(self):
        output, error = self.run_skool2asm('-x', catch_exit=2)
        self.assertEqual(len(output), 0)
        self.assertTrue(error.startswith('usage: skool2asm.py'))

    def test_invalid_option(self):
        output, error = self.run_skool2asm('-x', catch_exit=2)
        self.assertEqual(len(output), 0)
        self.assertTrue(error.startswith('usage: skool2asm.py'))

    def test_invalid_option_value(self):
        for args in ('-i ABC', '-f +'):
            output, error = self.run_skool2asm(args, catch_exit=2)
            self.assertEqual(len(output), 0)
            self.assertTrue(error.startswith('usage: skool2asm.py'))

    @patch.object(skool2asm, 'get_config', mock_config)
    def test_parse_stdin(self):
        skool = '\n'.join((
            '@start',
            '; Do nothing',
            'c60000 RET'
        ))
        self.write_stdin(skool)
        output, error = self.run_skool2asm('-', err_lines=True)
        self.assertEqual(error[0][:12], 'Parsed stdin')

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_S(self):
        for option, start in (('-S', 30000), ('--start', 40000)):
            output, error = self.run_skool2asm('-q {} {} test-S.skool'.format(option, start))
            self.assertEqual(error, '')
            self.assertEqual(mock_skool_parser.min_address, start)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_E(self):
        for option, end in (('-E', 50000), ('--end', 60000)):
            output, error = self.run_skool2asm('-q {} {} test-E.skool'.format(option, end))
            self.assertEqual(error, '')
            self.assertEqual(mock_skool_parser.max_address, end)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_options_S_and_E(self):
        start = 24576
        end = 32768
        output, error = self.run_skool2asm('-q -S {} -E {} test-S-and-E.skool'.format(start, end))
        self.assertEqual(error, '')
        self.assertEqual(mock_skool_parser.min_address, start)
        self.assertEqual(mock_skool_parser.max_address, end)
        self.assertTrue(mock_asm_writer.wrote)

    def test_option_V(self):
        for option in ('-V', '--version'):
            output, error = self.run_skool2asm(option, err_lines=True, catch_exit=0)
            self.assertEqual(['SkoolKit {}'.format(VERSION)], output + error)

    def test_option_p(self):
        for option in ('-p', '--package-dir'):
            output, error = self.run_skool2asm(option, catch_exit=0)
            self.assertEqual(error, '')
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0], os.path.dirname(skoolkit.__file__))

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_q(self):
        for option in ('-q', '--quiet'):
            output, error = self.run_skool2asm('{} test-q.skool'.format(option))
            self.assertEqual(error, '')
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_w(self):
        for option in ('-w', '--no-warnings'):
            output, error = self.run_skool2asm('-q {} test-w.skool'.format(option))
            self.assertEqual(mock_skool_parser.warnings, False)
            self.assertEqual({'warnings': '0'}, mock_asm_writer.properties)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_l(self):
        for option in ('-l', '--lower'):
            output, error = self.run_skool2asm('-q {} test-l.skool'.format(option))
            self.assertEqual(mock_skool_parser.case, CASE_LOWER)
            mock_skool_parser.case = None
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_u(self):
        for option in ('-u', '--upper'):
            output, error = self.run_skool2asm('-q {} test-u.skool'.format(option))
            self.assertEqual(mock_skool_parser.case, CASE_UPPER)
            mock_skool_parser.case = None
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_D(self):
        for option in ('-D', '--decimal'):
            output, error = self.run_skool2asm('-q {} test-D.skool'.format(option))
            self.assertEqual(mock_skool_parser.base, BASE_10)
            self.assertTrue(mock_asm_writer.wrote)
            mock_skool_parser.base = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_H(self):
        for option in ('-H', '--hex'):
            output, error = self.run_skool2asm('-q {} test-H.skool'.format(option))
            self.assertEqual(mock_skool_parser.base, BASE_16)
            self.assertTrue(mock_asm_writer.wrote)
            mock_skool_parser.base = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_f_0(self):
        output, error = self.run_skool2asm('-q -f 0 test-f0.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 0)
        self.assertEqual(mock_skool_parser.asm_mode, 1)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_f_1(self):
        output, error = self.run_skool2asm('-q --fixes 1 test-f1.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 1)
        self.assertEqual(mock_skool_parser.asm_mode, 1)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_f_2(self):
        output, error = self.run_skool2asm('-q -f 2 test-f2.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 2)
        self.assertEqual(mock_skool_parser.asm_mode, 1)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_f_3(self):
        output, error = self.run_skool2asm('-q --fixes 3 test-f3.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 3)
        self.assertEqual(mock_skool_parser.asm_mode, 3)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_s(self):
        for option in ('-s', '--ssub'):
            output, error = self.run_skool2asm('-q {} test-s.skool'.format(option))
            self.assertEqual(mock_skool_parser.asm_mode, 2)
            self.assertTrue(mock_asm_writer.wrote)
            mock_skool_parser.asm_mode = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_option_r(self):
        for option in ('-r', '--rsub'):
            output, error = self.run_skool2asm('-q {} test-r.skool'.format(option))
            self.assertEqual(mock_skool_parser.asm_mode, 3)
            self.assertEqual(mock_skool_parser.fix_mode, 1)
            self.assertTrue(mock_asm_writer.wrote)
            mock_skool_parser.asm_mode = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_options_r_f_0(self):
        output, error = self.run_skool2asm('-q -r -f 0 test-rf0.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 1)
        self.assertEqual(mock_skool_parser.asm_mode, 3)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_options_r_f_1(self):
        output, error = self.run_skool2asm('-q -r -f 1 test-rf1.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 1)
        self.assertEqual(mock_skool_parser.asm_mode, 3)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_options_r_f_2(self):
        output, error = self.run_skool2asm('-q -r -f 2 test-rf2.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 2)
        self.assertEqual(mock_skool_parser.asm_mode, 3)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_options_r_f_3(self):
        output, error = self.run_skool2asm('-q -r -f 3 test-rf3.skool')
        self.assertEqual(mock_skool_parser.fix_mode, 3)
        self.assertEqual(mock_skool_parser.asm_mode, 3)
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_c(self):
        for option in ('-c', '--create-labels'):
            output, error = self.run_skool2asm('-q {} test-c.skool'.format(option))
            self.assertTrue(mock_skool_parser.create_labels)
            self.assertTrue(mock_asm_writer.wrote)
            mock_skool_parser.create_labels = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'get_config', mock_config)
    def test_writer(self):
        skool = '\n'.join((
            '@start',
            '@writer={}',
            '; Begin',
            'c24576 RET',
        ))

        # Test a writer with no module or package name
        writer = 'AbsoluteAsmWriter'
        skoolfile = self.write_text_file(skool.format(writer), suffix='.skool')
        with self.assertRaisesRegex(SkoolKitError, "Invalid class name: '{}'".format(writer)):
            self.run_skool2asm(skoolfile)

        # Test a writer in a nonexistent module
        writer = 'nonexistentmodule.AsmWriter'
        skoolfile = self.write_text_file(skool.format(writer), suffix='.skool')
        with self.assertRaisesRegex(SkoolKitError, "Failed to import class nonexistentmodule.AsmWriter: No module named '?nonexistentmodule'?"):
            self.run_skool2asm(skoolfile)

        # Test a writer that doesn't exist
        writer = 'test_skool2asm.NonexistentAsmWriter'
        skoolfile = self.write_text_file(skool.format(writer), suffix='.skool')
        with self.assertRaisesRegex(SkoolKitError, "No class named 'NonexistentAsmWriter' in module 'test_skool2asm'"):
            self.run_skool2asm(skoolfile)

        # Test a writer that exists
        skoolfile = self.write_text_file(skool.format('test_skool2asm.MockAsmWriter'), suffix='.skool')
        output, error = self.run_skool2asm(skoolfile, err_lines=True)
        self.assertEqual(error[1], 'Using ASM writer test_skool2asm.MockAsmWriter')
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'get_class', Mock(return_value=MockAsmWriter))
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_W(self):
        skool = '\n'.join((
            '@start',
            '@writer=SomeWriterThatWillBeOverridden',
            'c32768 RET',
        ))
        skoolfile = self.write_text_file(skool, suffix='.skool')
        for option in ('-W', '--writer'):
            output, error = self.run_skool2asm('{} dummy_value {}'.format(option, skoolfile), err_lines=True)
            self.assertEqual(error[1], 'Using ASM writer dummy_value')
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'SkoolParser', MockSkoolParser)
    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_P(self):
        for option, prop, value in (('-P', 'crlf', '1'), ('--set', 'bullet', '+')):
            output, error = self.run_skool2asm('-q {} {}={} test-P.skool'.format(option, prop, value))
            self.assertEqual({prop: value}, mock_asm_writer.properties)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

    @patch.object(skool2asm, 'run', mock_run)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_I(self):
        for option, spec, attr, exp_value in (('-I', 'Base=16', 'base', 16), ('--ini', 'Case=1', 'case', 1)):
            self.run_skool2asm('{} {} test-I.skool'.format(option, spec))
            options = run_args[1]
            self.assertEqual(options.params, [spec])
            self.assertEqual(getattr(options, attr), exp_value)

    @patch.object(skool2asm, 'run', mock_run)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_I_multiple(self):
        self.run_skool2asm('-I Quiet=1 --ini Warnings=0 test-I-multiple.skool')
        options = run_args[1]
        self.assertEqual(options.params, ['Quiet=1', 'Warnings=0'])
        self.assertEqual(options.quiet, 1)
        self.assertEqual(options.warn, 0)

    @patch.object(skool2asm, 'run', mock_run)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_I_overrides_other_options(self):
        self.run_skool2asm('-H -I Base=10 -l --ini Case=2 test.skool')
        options = run_args[1]
        self.assertEqual(options.params, ['Base=10', 'Case=2'])
        self.assertEqual(options.base, 10)
        self.assertEqual(options.case, 2)

    @patch.object(skool2asm, 'run', mock_run)
    def test_option_I_overrides_config_read_from_file(self):
        ini = '\n'.join((
            '[skool2asm]',
            'Base=10',
            'Case=1'
        ))
        self.write_text_file(ini, 'skoolkit.ini')
        self.run_skool2asm('-I Base=16 --ini Case=2 test.skool')
        options = run_args[1]
        self.assertEqual(options.params, ['Base=16', 'Case=2'])
        self.assertEqual(options.base, 16)
        self.assertEqual(options.case, 2)

    @patch.object(skool2asm, 'run', mock_run)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_option_I_invalid_value(self):
        self.run_skool2asm('-I Quiet=x test-I-invalid.skool')
        options = run_args[1]
        self.assertEqual(options.quiet, 0)

    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_tab_property(self):
        skool = '\n'.join((
            '@start',
            '@set-tab={}',
            '; Data',
            'b40000 DEFB 0 ; Comment',
        ))

        for tab in ('0', '1'):
            skoolfile = self.write_text_file(skool.format(tab), suffix='.skool')
            self.run_skool2asm(skoolfile)
            self.assertEqual(mock_asm_writer.properties['tab'], tab)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

        # tab=0, overridden by --set option
        tab = '0'
        skoolfile = self.write_text_file(skool.format(tab), suffix='.skool')
        self.run_skool2asm('--set tab=1 {}'.format(skoolfile))
        self.assertEqual(mock_asm_writer.properties['tab'], '1')
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_crlf_property(self):
        skool = '\n'.join((
            '@start',
            '@set-crlf={}',
            '; Data',
            'b40000 DEFB 0 ; Comment',
        ))

        for crlf in ('0', '1'):
            skoolfile = self.write_text_file(skool.format(crlf), suffix='.skool')
            self.run_skool2asm(skoolfile)
            self.assertEqual(mock_asm_writer.properties['crlf'], crlf)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

        # crlf=0, overridden by --set option
        crlf = '0'
        skoolfile = self.write_text_file(skool.format(crlf), suffix='.skool')
        self.run_skool2asm('--set crlf=1 {}'.format(skoolfile))
        self.assertEqual(mock_asm_writer.properties['crlf'], '1')
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    @patch.object(skool2asm, 'get_config', mock_config)
    def test_warnings_property(self):
        skool = '\n'.join((
            '@start',
            '@set-warnings={}',
            '; Routine at 25000',
            ';',
            '; Used by the routine at 25000.',
            'c25000 JP 25000',
        ))

        for value in ('0', '1'):
            skoolfile = self.write_text_file(skool.format(value), suffix='.skool')
            self.run_skool2asm(skoolfile)
            self.assertEqual(mock_asm_writer.properties['warnings'], value)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

        # warnings=1, overridden by '-w' option
        skoolfile = self.write_text_file(skool.format(1), suffix='.skool')
        output, error = self.run_skool2asm('-w {}'.format(skoolfile))
        self.assertEqual(mock_asm_writer.properties['warnings'], '0')
        self.assertTrue(mock_asm_writer.wrote)

    @patch.object(skool2asm, 'AsmWriter', MockAsmWriter)
    def test_instruction_width_property(self):
        skool = '\n'.join((
            '@start',
            '@set-instruction-width={}',
            '; Data',
            'b40000 DEFB 0 ; Comment',
        ))

        for value in ('20', '25'):
            skoolfile = self.write_text_file(skool.format(value), suffix='.skool')
            self.run_skool2asm(skoolfile)
            self.assertEqual(mock_asm_writer.properties['instruction-width'], value)
            self.assertTrue(mock_asm_writer.wrote)
            mock_asm_writer.properties = None
            mock_asm_writer.wrote = False

        # instruction-width=27, overridden by --set option
        skoolfile = self.write_text_file(skool.format(27), suffix='.skool')
        width = '20'
        self.run_skool2asm('--set instruction-width={} {}'.format(width, skoolfile))
        self.assertEqual(mock_asm_writer.properties['instruction-width'], width)
        self.assertTrue(mock_asm_writer.wrote)

if __name__ == '__main__':
    unittest.main()
