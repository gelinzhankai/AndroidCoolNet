import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import gms_assets as assets


class Response(io.BytesIO):
    def __init__(self, data, url='https://release-assets.githubusercontent.com/test', length=None):
        super().__init__(data)
        self.headers = {'Content-Length': str(len(data) if length is None else length)}
        self.url = url

    def geturl(self):
        return self.url


class AssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'tool'
        self.source = Path(self.temp.name) / 'downloads'
        self.source.mkdir()
        self.data = [b'framework fixture', b'play services fixture', b'store fixture']
        self.entries = [dict(package=p, file=f'{i}.apk', version_name='test', bytes=len(data),
                             sha256=hashlib.sha256(data).hexdigest())
                        for i, (p, data) in enumerate(zip(assets.LABELS, self.data))]
        self.output = io.StringIO()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(contextlib.redirect_stdout(self.output))

    def bundle(self, indices=(0, 1, 2), name='offline.zip'):
        path = self.source / name
        with zipfile.ZipFile(path, 'w') as archive:
            for i in indices:
                archive.writestr(f'nested/renamed-{i}.apk', self.data[i])
        return path

    def assert_cached(self, indices):
        for i in indices:
            self.assertTrue(assets.cached(self.root, self.entries[i]))

    def test_windows_quoted_paths_and_semicolons(self):
        value = ' "D:\\下载文件\\offline.zip" ; "E:\\a;b\\store.apk"；C:\\文件 夹 '
        self.assertEqual([str(p) for p in assets.split_paths(value)],
                         ['D:\\下载文件\\offline.zip', 'E:\\a;b\\store.apk', 'C:\\文件 夹'])
        with self.assertRaises(assets.AssetError):
            assets.split_paths('"unclosed')

    def test_manual_bundle_selects_only_requested_components(self):
        path = self.bundle()
        with mock.patch('builtins.input', side_effect=['2', '', str(path)]), mock.patch.object(assets.webbrowser, 'open') as browser:
            assets.ensure_google_assets([self.entries[1]], self.root)
        browser.assert_called_once_with(assets.RELEASE_PAGE)
        self.assert_cached([1])
        self.assertFalse(assets.cached(self.root, self.entries[0]))
        self.assertFalse(assets.cached(self.root, self.entries[2]))

    def test_multiple_apks_unordered_and_renamed(self):
        paths = []
        for i in (2, 0, 1):
            path = self.source / f'任意 名称 {i}.apk'
            path.write_bytes(self.data[i])
            paths.append(f'"{path}"')
        self.assertEqual(assets.import_paths(';'.join(paths), self.entries, self.root), {'0.apk', '1.apk', '2.apk'})
        self.assert_cached(range(3))

    def test_folder_and_multiple_archives(self):
        self.bundle([0], 'one.zip')
        nested = self.source / 'nested'
        nested.mkdir()
        (nested / 'any.apk').write_bytes(self.data[1])
        self.assertEqual(assets.import_paths(str(self.source), self.entries, self.root), {'0.apk', '1.apk'})

    def test_untrusted_archive_names_cannot_escape_cache(self):
        path = self.source / 'unsafe.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('../../outside.apk', self.data[0])
            archive.writestr('C:/Windows/startup.cmd', b'not executed')
        assets.import_paths(str(path), self.entries, self.root)
        self.assert_cached([0])
        self.assertFalse((Path(self.temp.name) / 'outside.apk').exists())
        self.assertEqual(sorted(p.name for p in (self.root / 'cache/gms').iterdir()), ['0.apk'])

    def test_same_size_wrong_hash_and_truncated_zip_rejected(self):
        bad = self.source / 'bad.apk'
        bad.write_bytes(b'x' * len(self.data[0]))
        broken = self.source / 'broken.zip'
        broken.write_bytes(b'PK incomplete')
        unsupported = self.bundle([0], 'unsupported.zip')
        content = bytearray(unsupported.read_bytes())
        content[8:10] = (99).to_bytes(2, 'little')
        offset = content.index(b'PK\x01\x02') + 10
        content[offset:offset+2] = (99).to_bytes(2, 'little')
        unsupported.write_bytes(content)
        self.assertEqual(assets.import_paths(f'{bad};{broken};{unsupported}', self.entries, self.root), set())
        self.assertFalse(assets.cached(self.root, self.entries[0]))
        self.assertEqual(list((self.root / 'cache/gms').glob('*.part')), [])

    def test_manual_retry_can_accumulate_files(self):
        one, rest = self.bundle([0], 'one.zip'), self.bundle([1, 2], 'rest.zip')
        with mock.patch('builtins.input', side_effect=['bad-choice', '2', '', str(self.source / 'missing.zip'), str(one), str(rest)]), \
                mock.patch.object(assets.webbrowser, 'open'):
            assets.ensure_google_assets(self.entries, self.root)
        self.assert_cached(range(3))
        self.assertIn('请输入 1 或 2', self.output.getvalue())

    def test_user_skip_does_not_open_browser_or_fetch(self):
        with mock.patch('builtins.input', return_value=''), mock.patch.object(assets.webbrowser, 'open') as browser, \
                mock.patch.object(assets, 'download_archive') as download:
            with self.assertRaises(assets.AssetError):
                assets.ensure_google_assets(self.entries, self.root)
        browser.assert_not_called()
        download.assert_not_called()

    def test_valid_cache_requires_no_input(self):
        assets.import_file(self.bundle(), self.entries, self.root)
        with mock.patch('builtins.input', side_effect=AssertionError('Unexpected prompt')):
            assets.ensure_google_assets(self.entries, self.root)

    def download_entry(self):
        data = self.bundle([0]).read_bytes()
        entry = dict(self.entries[0], download_asset='0.apk.zip', download_bytes=len(data),
                     download_sha256=hashlib.sha256(data).hexdigest())
        return entry, data

    def test_auto_download_stream_progress_and_import(self):
        entry, data = self.download_entry()
        opener = mock.Mock()
        opener.open.return_value = Response(data)
        with mock.patch('builtins.input', return_value='1'), \
                mock.patch.object(assets.urllib.request, 'build_opener', return_value=opener):
            assets.ensure_google_assets([entry], self.root)
        self.assert_cached([0])
        self.assertIn('100.0%', self.output.getvalue())
        self.assertEqual(list((self.root / 'cache/gms').glob('download-*')), [])

    def test_download_length_hash_and_https_guards(self):
        entry, data = self.download_entry()
        for response in (Response(data, length=len(data)+1), Response(data[:-1], length=len(data)),
                         Response(b'x'*len(data)), Response(data, url='http://unsafe.example/file')):
            with self.subTest(url=response.url, length=response.headers['Content-Length']):
                opener = mock.Mock(); opener.open.return_value = response
                with mock.patch.object(assets.urllib.request, 'build_opener', return_value=opener):
                    with self.assertRaises(assets.AssetError):
                        assets.download_archive(entry, self.source/'output.zip')

    def test_auto_failure_manual_fallback_reuses_success(self):
        one, rest = self.bundle([0], 'one.zip'), self.bundle([1, 2], 'rest.zip')
        calls = []
        def download(entry, target, proxy):
            calls.append(entry['file'])
            if entry['file'] == '0.apk':
                target.write_bytes(one.read_bytes())
            else:
                raise assets.AssetError('simulated network failure')
        with mock.patch('builtins.input', side_effect=['1', '', str(rest)]), \
                mock.patch.object(assets, 'download_archive', side_effect=download), \
                mock.patch.object(assets.webbrowser, 'open') as browser:
            assets.ensure_google_assets(self.entries, self.root)
        self.assertEqual(calls, ['0.apk', '1.apk'])
        self.assert_cached(range(3))
        browser.assert_called_once()

    def test_eof_during_manual_does_not_loop_forever(self):
        with mock.patch('builtins.input', side_effect=['2', '', EOFError]), mock.patch.object(assets.webbrowser, 'open'):
            with self.assertRaises(assets.AssetError):
                assets.ensure_google_assets(self.entries, self.root)


if __name__ == '__main__':
    unittest.main()
