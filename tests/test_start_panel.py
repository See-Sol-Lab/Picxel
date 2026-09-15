"""Panel-first startup: dependency setup, identity checks and reuse without drawing."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import start_panel as start


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        patch = mock.patch.object(start, 'ROOT', self.root)
        patch.start(); self.addCleanup(patch.stop)
        self.info = {'app':'Picxel', 'root':str(self.root), 'python':sys.executable, 'pid':123}

    def test_healthy_panel_reuses_process_and_opens_browser(self):
        with mock.patch.object(start, 'running_panel', return_value=self.info), \
             mock.patch.object(start, 'prepare_python') as prepare, \
             mock.patch.object(start.subprocess, 'Popen') as launch, \
             mock.patch.object(start.webbrowser, 'open', return_value=True) as browser:
            result = start.start_panel()
        self.assertTrue(result['reused'])
        prepare.assert_not_called(); launch.assert_not_called()
        browser.assert_called_once_with('http://127.0.0.1:8770/')

    def test_missing_panel_starts_hidden_and_confirms_ready(self):
        process = mock.Mock(stdout=io.StringIO('Picxel panel: http://127.0.0.1:8770/  (Ctrl+C to stop)\n'))
        with mock.patch.object(start, 'running_panel', side_effect=[None,self.info]), \
             mock.patch.object(start, 'prepare_python', return_value=sys.executable), \
             mock.patch.object(start.subprocess, 'Popen', return_value=process) as launch, \
             mock.patch.object(start.webbrowser, 'open') as browser:
            result = start.start_panel(open_browser=False)
        self.assertFalse(result['reused']); browser.assert_not_called()
        command = launch.call_args.args[0]
        self.assertEqual(command[-4:], ['panel','--port','8770','--no-open'])
        self.assertIn('creationflags' if sys.platform=='win32' else 'start_new_session', launch.call_args.kwargs)

    def test_port_identity_is_checked(self):
        with mock.patch.object(start, 'urlopen', return_value=io.BytesIO(json.dumps(self.info).encode())):
            self.assertEqual(start.running_panel('http://127.0.0.1:8770/'), self.info)
        other = dict(self.info, root=str(self.root/'other'))
        with mock.patch.object(start, 'urlopen', return_value=io.BytesIO(json.dumps(other).encode())):
            with self.assertRaisesRegex(RuntimeError, 'another app'):
                start.running_panel('http://127.0.0.1:8770/')
        with mock.patch.object(start, 'urlopen', side_effect=HTTPError('url',404,'missing',{},None)):
            with self.assertRaisesRegex(RuntimeError, 'occupied'):
                start.running_panel('http://127.0.0.1:8770/')
        with mock.patch.object(start, 'urlopen', side_effect=URLError(ConnectionRefusedError())):
            self.assertIsNone(start.running_panel('http://127.0.0.1:8770/'))

    def test_failed_start_never_reports_a_ready_panel(self):
        process = mock.Mock(stdout=io.StringIO(''))
        with mock.patch.object(start, 'running_panel', return_value=None), \
             mock.patch.object(start, 'prepare_python', return_value=sys.executable), \
             mock.patch.object(start.subprocess, 'Popen', return_value=process), \
             mock.patch.object(start.webbrowser, 'open') as browser:
            with self.assertRaisesRegex(RuntimeError, 'did not start'):
                start.start_panel()
        browser.assert_not_called()

    def test_missing_pillow_is_installed_only_in_local_environment(self):
        with mock.patch.object(start.importlib.util, 'find_spec', return_value=None), \
             mock.patch.object(start.venv, 'EnvBuilder') as builder, \
             mock.patch.object(start.subprocess, 'run', side_effect=[mock.Mock(returncode=1),mock.Mock(returncode=0)]) as run:
            python = start.prepare_python()
        builder.return_value.create.assert_called_once_with(self.root/'.venv')
        self.assertTrue(Path(python).is_relative_to(self.root/'.venv'))
        self.assertEqual(run.call_args.args[0], [python,'-m','pip','install','Pillow'])

    def test_existing_pillow_requires_no_install(self):
        with mock.patch.object(start.importlib.util, 'find_spec', return_value=object()), \
             mock.patch.object(start.subprocess, 'run') as run:
            self.assertEqual(start.prepare_python(), sys.executable)
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
