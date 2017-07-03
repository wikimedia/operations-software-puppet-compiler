import unittest
import mock
import os
from puppet_compiler import controller, threads


class TestController(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')

    def test_initialize_no_configfile(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertEquals(c.hosts, ['test.eqiad.wmnet'])
        self.assertEquals(c.config['http_url'],
                          'https://puppet-compiler.wmflabs.org/html')
        self.assertEquals(c.config['base'], '/mnt/jenkins-workspace')

    def test_parse_config(self):
        filename = os.path.join(self.fixtures, 'test_config.yaml')
        c = controller.Controller(filename, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertEquals(len(c.config['test_non_existent']), 2)
        self.assertEquals(c.config['http_url'],
                          'http://www.example.com/garbagehere')

    @mock.patch('puppet_compiler.presentation.html.Index')
    @mock.patch('puppet_compiler.controller.HostWorker.run_host')
    def test_run_single_host(self, mocker, html_mocker):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        mocker.return_value = 'fail'
        c.m.prepare = mock.MagicMock()
        c.m.prepare.return_value = True
        c.m.refresh = mock.MagicMock()
        c.m.refresh.return_value = True

        c.run()
        c.m.prepare.assert_called_once_with()
        c.m.refresh.assert_not_called()
        self.assertEquals(c.state['fail'], set(['test.eqiad.wmnet']))

    def test_node_callback(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        response = threads.Msg(is_error=True, value='Something to remember',
                               args=None,
                               kwargs={'hostname': 'test.eqiad.wmnet'})
        c.count = 5
        c.on_node_compiled(response)
        self.assertIn('test.eqiad.wmnet', c.state['fail'])
        self.assertEquals(c.count, 6)
        response = threads.Msg(is_error=False, value='noop', args=None,
                               kwargs={'hostname': 'test2.eqiad.wmnet'})
        c.on_node_compiled(response)
        self.assertIn('test2.eqiad.wmnet', c.state['noop'])
        self.assertEquals(c.count, 7)

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
        c.pick_hosts('re:test\d.eqiad.wmnet')
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
