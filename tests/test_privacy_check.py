import contextlib
import ctypes
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('privacy_test', ROOT/'setup_tool.py')
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
TARGET = s.ANTIFRAUD_PACKAGE


class FakeAdb:
    def __init__(self):
        self.installed = {TARGET, 'com.example.unrelated'}
        self.mutations = []
        self.outcome = 'Success'
        self.remove = True
        self.package_queries = 0
        self.postcheck_error = False
        self.version_error = False

    def packages(self):
        self.package_queries += 1
        if self.postcheck_error and self.package_queries == 2:
            raise s.SetupError('ADB 操作超时')
        return set(self.installed)

    def shell(self, *args, **kwargs):
        if args == ('dumpsys', 'package', TARGET):
            if self.version_error:
                raise s.SetupError('Version unavailable')
            return 'versionName=2.0.27\n'
        assert args == ('pm', 'uninstall', '--user', '0', TARGET)
        assert kwargs == dict(timeout=90, check=False, include_stderr=True)
        self.mutations.append(args)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        if self.remove:
            self.installed.discard(TARGET)
        return self.outcome


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.adb = FakeAdb()
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def invoke(self, answers=('',), installed=None, detect_only=False):
        with mock.patch('builtins.input', side_effect=answers) as prompt:
            result = s.optional_antifraud_removal(self.adb, self.adb.installed if installed is None else installed, detect_only)
        self.assertIn('com.example.unrelated', self.adb.installed)
        return result, prompt

    def test_absent_and_lookalike_packages_do_not_prompt(self):
        result, prompt = self.invoke(installed={TARGET+'.backup', 'com.example.antifraud'})
        self.assertEqual(result['status'], 'not_installed')
        prompt.assert_not_called()
        self.assertEqual(self.adb.mutations, [])

    def test_enter_defaults_to_current_user_uninstall(self):
        result, prompt = self.invoke()
        self.assertEqual(result['status'], 'uninstalled')
        self.assertTrue(result['uninstall_attempted'])
        self.assertEqual(result['version'], '2.0.27')
        self.assertEqual(len(self.adb.mutations), 1)
        self.assertIn('1 卸载后继续', prompt.call_args.args[0])
        self.assertIn('2 保留并继续', prompt.call_args.args[0])
        self.assertIn(s.PRIVACY_WARNING, self.output.getvalue())
        self.assertIn('本地数据', self.output.getvalue())

    def test_explicit_one_uninstalls(self):
        self.assertEqual(self.invoke(['1'])[0]['status'], 'uninstalled')

    def test_two_keeps_application(self):
        result, _ = self.invoke(['2'])
        self.assertEqual(result['status'], 'kept')
        self.assertFalse(result['uninstall_attempted'])
        self.assertEqual(self.adb.mutations, [])

    def test_invalid_input_reprompts_without_uninstalling(self):
        result, prompt = self.invoke(['y', '0', '2'])
        self.assertEqual(result['status'], 'kept')
        self.assertEqual(prompt.call_count, 3)
        self.assertEqual(self.adb.mutations, [])

    def test_eof_is_not_default_consent(self):
        result, _ = self.invoke([EOFError])
        self.assertEqual(result['status'], 'kept_no_input')
        self.assertEqual(self.adb.mutations, [])

    def test_read_only_mode_does_not_prompt_or_uninstall(self):
        result, prompt = self.invoke(detect_only=True)
        self.assertEqual(result['status'], 'detected_only')
        prompt.assert_not_called()
        self.assertEqual(self.adb.mutations, [])

    def test_device_policy_failure_is_reported_without_raising(self):
        self.adb.remove = False
        self.adb.outcome = 'Failure [DELETE_FAILED_DEVICE_POLICY_MANAGER]'
        result, _ = self.invoke()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason'], 'DELETE_FAILED_DEVICE_POLICY_MANAGER')
        self.assertIn('继续后续安装流程', self.output.getvalue())

    def test_timeout_and_process_error_do_not_raise(self):
        for error in (s.SetupError('ADB 操作超时'), OSError('fake process error')):
            self.adb = FakeAdb()
            self.adb.outcome = error
            result, _ = self.invoke()
            self.assertEqual(result['status'], 'failed')
            self.assertTrue(result['uninstall_attempted'])

    def test_success_text_without_removal_is_not_success(self):
        self.adb.remove = False
        self.assertEqual(self.invoke()[0]['status'], 'failed')

    def test_postcheck_failure_is_not_reported_as_success(self):
        self.adb.postcheck_error = True
        self.assertEqual(self.invoke()[0]['status'], 'failed')

    def test_race_removal_does_not_submit_an_uninstall(self):
        self.adb.installed.remove(TARGET)
        self.assertEqual(self.invoke(installed={TARGET})[0]['status'], 'already_absent')
        self.assertEqual(self.adb.mutations, [])

    def test_version_read_failure_still_allows_choice(self):
        self.adb.version_error = True
        self.assertEqual(self.invoke(['2'])[0]['status'], 'kept')

    def test_main_detect_only_never_mutates(self):
        device = dict(model='mock', api=35, android='15', abis=['arm64-v8a'], gms={})
        with mock.patch.object(s, 'find_adb', return_value='fake'), \
                mock.patch.object(s, 'select_device', return_value='mock-device'), \
                mock.patch.object(s, 'Adb', return_value=self.adb), \
                mock.patch.object(s, 'inspect_device', return_value=(device, self.adb.installed)), \
                mock.patch.object(s, 'provision_google') as google, mock.patch.object(s, 'save_report') as report, \
                mock.patch('builtins.input') as prompt:
            self.assertEqual(s.main(['--detect-only']), 0)
        prompt.assert_not_called()
        google.assert_not_called()
        report.assert_not_called()
        self.assertEqual(self.adb.mutations, [])

    def test_redirected_warning_has_no_escape_codes(self):
        s.say_red(s.PRIVACY_WARNING)
        self.assertEqual(self.output.getvalue(), s.PRIVACY_WARNING+'\n')

    def test_ansi_warning_is_red_and_resets_color(self):
        with mock.patch.object(self.output, 'isatty', return_value=True), mock.patch.object(s, 'os', SimpleNamespace(name='posix')):
            s.say_red('notice')
        self.assertEqual(self.output.getvalue(), '\033[1;31mnotice\033[0m\n')

    def test_windows_warning_restores_original_console_attributes(self):
        kernel = mock.MagicMock()
        kernel.GetStdHandle.return_value = 123
        def fill(handle, info):
            info._obj.attributes = 7
            return 1
        kernel.GetConsoleScreenBufferInfo.side_effect = fill
        kernel.SetConsoleTextAttribute.return_value = 1
        with mock.patch.object(self.output, 'isatty', return_value=True), \
                mock.patch.object(s, 'os', SimpleNamespace(name='nt')), \
                mock.patch.object(ctypes, 'WinDLL', return_value=kernel, create=True):
            s.say_red('notice')
        self.assertEqual(kernel.SetConsoleTextAttribute.call_args_list, [mock.call(123, 12), mock.call(123, 7)])
        self.assertEqual(self.output.getvalue(), 'notice\n')


if __name__ == '__main__':
    unittest.main()
