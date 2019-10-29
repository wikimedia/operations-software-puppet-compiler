import unittest
import mock
import os
from puppet_compiler import controller, threads, state
from puppet_compiler.presentation import html


class TestController(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        os.environ['PUPPET_VERSION'] = '4'
        os.environ['PUPPET_VERSION_FULL'] = '4.8.10'

    def test_initialize_no_configfile(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertEquals(c.hosts, ['test.eqiad.wmnet'])
        self.assertEquals(c.config['http_url'],
                          'https://puppet-compiler.wmflabs.org/html')
        self.assertEquals(c.config['base'], '/mnt/jenkins-workspace')
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet', nthreads=2, modes=['future'])
        self.assertEqual(c.run_modes.keys(), ['future'])

    def test_parse_config(self):
        filename = os.path.join(self.fixtures, 'test_config.yaml')
        c = controller.Controller(filename, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertEquals(len(c.config['test_non_existent']), 2)
        self.assertEquals(c.config['http_url'],
                          'http://www.example.com/garbagehere')
        # This will log an error, but not raise an exception
        controller.Controller('unexistent', 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertRaises(SystemExit, controller.Controller, filename + '.invalid', 1, 1, 'test.eqiad.wmnet')

    @mock.patch('subprocess.check_output')
    def test_set_puppet_version(self, mocker):
        del os.environ['PUPPET_VERSION']
        del os.environ['PUPPET_VERSION_FULL']
        mocker.return_value = '3.8.2\n'
        controller.Controller(None, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        mocker.assert_called_with(['puppet', '--version'])
        self.assertEqual(os.environ['PUPPET_VERSION'], '3')

    @mock.patch('puppet_compiler.worker.HostWorker.html_index')
    @mock.patch('puppet_compiler.worker.HostWorker.run_host')
    def test_run_single_host(self, mocker, html_mocker):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        mocker.return_value = (False, False, False)
        c.m.prepare = mock.MagicMock()
        c.m.prepare.return_value = True
        c.m.refresh = mock.MagicMock()
        c.m.refresh.return_value = True

        with mock.patch('time.sleep'):
            c.run()
        c.m.prepare.assert_called_once_with()
        c.m.refresh.assert_not_called()
        self.assertEquals(c.state.modes['change']['fail'], set(['test.eqiad.wmnet']))
        c.m.refresh.reset_mocks()
        c.config['puppet_src'] = '/src'
        c.config['puppet_private'] = '/private'
        mocker.return_value = (False, False, None)
        with mock.patch('time.sleep'):
            c.run()
        c.m.refresh.assert_has_calls([mock.call('/src'), mock.call('/private')])
        self.assertEquals(c.state.modes['change']['noop'], set(['test.eqiad.wmnet']))

    def test_node_callback(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        response = threads.Msg(is_error=True, value='Something to remember',
                               args=None,
                               kwargs={
                                   'hostname': 'test.eqiad.wmnet',
                                   'classes': (state.ChangeState, html.Index),
                                   'mode': 'change'})
        c.count['change'] = 5
        c.on_node_compiled(response)
        self.assertIn('test.eqiad.wmnet', c.state.modes['change']['fail'])
        self.assertEquals(c.count['change'], 6)
        response = threads.Msg(is_error=False, value=(False, False, None), args=None,
                               kwargs={
                                   'hostname': 'test2.eqiad.wmnet',
                                   'classes': (state.ChangeState, html.Index),
                                   'mode': 'change'})
        c.on_node_compiled(response)
        self.assertIn('test2.eqiad.wmnet', c.state.modes['change']['noop'])
        self.assertEquals(c.count['change'], 7)
        with mock.patch('puppet_compiler.presentation.html.Index') as mocker:
            response = threads.Msg(
                is_error=False, value=(False, False, None), args=None,
                kwargs={
                    'hostname': 'test2.eqiad.wmnet',
                    'classes': (state.ChangeState, html.Index),
                    'mode': 'change'}
            )
            c.count['change'] = 4
            c.on_node_compiled(response)
            mocker.assert_called_with(c.outdir)

    def test_pick_hosts(self):
        # Initialize a simple controller
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        c.config['puppet_var'] = os.path.join(self.fixtures, 'puppet_var')
        c.config['puppet_src'] = self.fixtures
        # Single node
        c.pick_hosts('test1.eqiad.wmnet')
        self.assertEquals(c.hosts, ['test1.eqiad.wmnet'])
        # Comma-separated nodes
        c.pick_hosts('test.eqiad.wmnet,test1.eqiad.wmnet')
        self.assertEquals(set(c.hosts), set(['test.eqiad.wmnet', 'test1.eqiad.wmnet']))
        # Regex-based matching
        c.pick_hosts(r're:test\d.eqiad.wmnet')
        self.assertEquals(set(c.hosts), set(['test1.eqiad.wmnet', 'test2.eqiad.wmnet']))
        # Nodegen based on parsing site.pp
        c.pick_hosts(None)
        s1 = set(['test.eqiad.wmnet', 'test1.eqiad.wmnet'])
        s2 = set(['test.eqiad.wmnet', 'test2.eqiad.wmnet'])
        s = set(c.hosts)
        assert (s == s1 or s == s2)

    def test_realm_detection(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        self.assertEquals(c.realm, 'production')

        c.pick_hosts('test.tools.eqiad.wmflabs')
        self.assertEquals(c.realm, 'labs')

        with self.assertRaises(SystemExit) as cm:
            c.pick_hosts('test.eqiad.wmnet,test.tools.eqiad.wmflabs')

        self.assertEqual(cm.exception.code, 2)
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmflabs')
        self.assertEqual(c.realm, 'labs')
        self.assertEqual(c.m.realm, 'labs')

    def test_success(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        # let's add just a successful run
        c.count['change'] = 2
        c.state.modes = {'change': {'noop': 1}}
        self.assertTrue(c.success)
        c.count['change'] = 0
        self.assertTrue(c.success)
