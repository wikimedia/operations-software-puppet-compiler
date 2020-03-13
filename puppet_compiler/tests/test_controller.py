import os
import unittest

import mock
import requests_mock

from puppet_compiler import controller, state, threads
from puppet_compiler.presentation import html


PUPPETDB_URI = 'http://localhost:8080/pdb/query/v4/resources/Class/{}'


def get_mocked_response(check=None):
    json_data = [
        {
            'certname': 'grafana2001.codfw.wmnet',
            'tags': ["role", "class", "role::grafana", "grafana"]
        },
        {
            'certname': 'grafana1001.eqiad.wmnet',
            'tags': ["role", "class", "role::grafana", "grafana"]
        },
        {
            'certname': 'cloudmetrics1002.eqiad.wmnet',
            'tags': ["role", "production", "class", "profile",
                     "role::grafana", "grafana", "profile::grafana::production"]
        },
        {
            'certname': 'cloudmetrics2002.codfw.wmnet',
            'tags': ["role", "production", "class", "profile",
                     "role::grafana", "grafana", "profile::grafana::production"]
        },
    ]
    if check == 'role':
        return filter(lambda x: x['certname'].startswith('grafana'), json_data)
    if check == 'empty':
        return []
    return json_data


class TestController(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixtures = os.path.join(os.path.dirname(__file__), 'fixtures')
        os.environ['PUPPET_VERSION'] = '4'
        os.environ['PUPPET_VERSION_FULL'] = '4.8.10'

    def test_initialize_no_configfile(self):
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet', nthreads=2)
        self.assertEquals(c.hosts, set(['test.eqiad.wmnet']))
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
        self.assertEquals(c.hosts, set(['test1.eqiad.wmnet']))
        # Comma-separated nodes
        c.pick_hosts('test.eqiad.wmnet,test1.eqiad.wmnet')
        self.assertEquals(c.hosts, set(['test.eqiad.wmnet', 'test1.eqiad.wmnet']))
        # Comma-separated nodes trailing comma
        c.pick_hosts('test.eqiad.wmnet,test1.eqiad.wmnet,')
        self.assertEquals(c.hosts, set(['test.eqiad.wmnet', 'test1.eqiad.wmnet']))
        # Regex-based matching
        c.pick_hosts(r're:test\d.eqiad.wmnet')
        self.assertEquals(c.hosts, set(['test1.eqiad.wmnet', 'test2.eqiad.wmnet']))
        # Nodegen based on parsing site.pp
        c.pick_hosts(None)
        s1 = set(['test.eqiad.wmnet', 'test1.eqiad.wmnet'])
        s2 = set(['test.eqiad.wmnet', 'test2.eqiad.wmnet'])
        s = c.hosts
        assert (s == s1 or s == s2)

    @requests_mock.mock()
    def test_pick_puppetdb_hosts(self, r_mock):
        # Initialize a simple controller
        c = controller.Controller(None, 19, 224570, 'test.eqiad.wmnet')
        c.config['puppet_var'] = os.path.join(self.fixtures, 'puppet_var')
        c.config['puppet_src'] = self.fixtures
        # Role-based matching
        r_mock.get(PUPPETDB_URI.format('Role::Grafana'),
                   json=get_mocked_response('role'),
                   status_code=200)
        c.pick_hosts('O:grafana')
        self.assertEqual(c.hosts, set(['grafana2001.codfw.wmnet']))
        # Profile-based matching
        r_mock.get(PUPPETDB_URI.format('Profile::Grafana::Production'),
                   json=get_mocked_response(),
                   status_code=200)
        c.pick_hosts('P:grafana::production')
        self.assertEqual(c.hosts, set(['grafana2001.codfw.wmnet', 'cloudmetrics1002.eqiad.wmnet']))
        # Class-based matching
        r_mock.get(PUPPETDB_URI.format('Grafana'),
                   json=get_mocked_response(),
                   status_code=200)
        c.pick_hosts('C:grafana')
        self.assertEqual(c.hosts, set(['grafana2001.codfw.wmnet', 'cloudmetrics1002.eqiad.wmnet']))
        # Class-based matching (empty result)
        r_mock.get(PUPPETDB_URI.format('Grafana'),
                   json=get_mocked_response('empty'),
                   status_code=200)
        c.pick_hosts('C:grafana')
        self.assertEqual(c.hosts, set())

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
