import unittest
import mock
import os
from puppet_compiler import controller, threads


class TestController(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')

    def test_initialize_no_configfile(self):
        c = controller.Controller(None, 19, 224570, ['test.eqiad.wmnet'])
        self.assertEquals(c.hosts, ['test.eqiad.wmnet'])
        self.assertEquals(c.config['http_url'],
                          'https://puppet-compiler.wmflabs.org/html')
        self.assertEquals(c.config['base'], '/mnt/jenkins-workspace')

    def test_parse_config(self):
        filename = os.path.join(self.fixtures, 'test_config.yaml')
        c = controller.Controller(filename, 19, 224570, ['test.eqiad.wmnet'])
        self.assertEquals(len(c.config['test_non_existent']),2)
        self.assertEquals(c.config['http_url'],
                          'http://www.example.com/garbagehere')

    @mock.patch('puppet_compiler.presentation.html.Index')
    @mock.patch('puppet_compiler.controller.HostWorker.run_host')
    def test_run_single_host(self, mocker, html_mocker):
        c = controller.Controller(None, 19, 224570, ['test.eqiad.wmnet'])
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
        c = controller.Controller(None, 19, 224570, ['test.eqiad.wmnet'])
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
