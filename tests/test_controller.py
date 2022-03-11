import os
from pathlib import Path

import mock
import requests_mock
from aiounittest import AsyncTestCase  # type: ignore

from puppet_compiler import controller
from puppet_compiler.worker import RunHostResult

PUPPETDB_URI = "https://localhost/pdb/query/v4/resources/Class/{}"


def get_mocked_response(check=None):
    json_data = [
        {
            "certname": "grafana2001.codfw.wmnet",
            "tags": ["role", "class", "role::grafana", "grafana"],
        },
        {
            "certname": "grafana1001.eqiad.wmnet",
            "tags": ["role", "class", "role::grafana", "grafana"],
        },
        {
            "certname": "cloudmetrics1002.eqiad.wmnet",
            "tags": [
                "role",
                "production",
                "class",
                "profile",
                "role::grafana",
                "grafana",
                "profile::grafana::production",
            ],
        },
        {
            "certname": "cloudmetrics2002.codfw.wmnet",
            "tags": [
                "role",
                "production",
                "class",
                "profile",
                "role::grafana",
                "grafana",
                "profile::grafana::production",
            ],
        },
    ]
    if check == "role":
        return [host for host in json_data if host["certname"].startswith("grafana")]
    if check == "empty":
        return []
    return json_data


class TestController(AsyncTestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = Path(__file__).parent.resolve() / "fixtures"
        os.environ["PUPPET_VERSION"] = "4"
        os.environ["PUPPET_VERSION_FULL"] = "4.8.10"

    def test_initialize_no_configfile(self):
        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet", nthreads=2)
        self.assertEqual(c.prod_hosts, set(["test.eqiad.wmnet"]))
        self.assertEqual(c.config.http_url, "https://puppet-compiler.wmflabs.org/html")
        self.assertEqual(c.config.base, Path("/mnt/jenkins-workspace"))

    def test_parse_config(self):
        filename = self.fixtures / "test_config.yaml"
        c = controller.Controller(filename, 19, 224570, "test.eqiad.wmnet", nthreads=2)
        self.assertEqual(c.config.http_url, "http://www.example.com/garbagehere")
        # This will log an error, but not raise an exception
        controller.Controller(Path("nonexistent"), 19, 224570, "test.eqiad.wmnet", nthreads=2)
        with self.assertRaises(controller.ControllerError):
            controller.Controller(filename.parent / (filename.name + ".invalid"), 1, 1, "test.eqiad.wmnet")

    @mock.patch("subprocess.check_output")
    def test_set_puppet_version(self, mocker):
        del os.environ["PUPPET_VERSION"]
        del os.environ["PUPPET_VERSION_FULL"]
        mocker.return_value = b"3.8.2\n"
        controller.Controller(None, 19, 224570, "test.eqiad.wmnet", nthreads=2)
        mocker.assert_called_with(["puppet", "--version"])
        self.assertEqual(os.environ["PUPPET_VERSION"], "3")

    @mock.patch("puppet_compiler.presentation.html.Index.render")
    @mock.patch("puppet_compiler.worker.HostWorker.run_host")
    async def test_run_single_host(self, run_host_mock, _):
        # TODO: Improve this tests
        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet")
        run_host_mock.return_value = RunHostResult(base_error=False, change_error=False, has_diff=False)
        c.managecode.prepare = mock.MagicMock(return_value=True)
        c.managecode.refresh = mock.MagicMock(return_value=True)
        c.managecode.update_config = mock.MagicMock()

        with mock.patch("time.sleep"):
            run_failed = await c.run()
        c.managecode.prepare.assert_called_once_with()
        self.assertFalse(run_failed)
        c.managecode.refresh.reset_mocks()
        c.config.puppet_src = "/src"
        c.config.puppet_private = "/private"
        c.config.puppet_netbox = "/netbox-hiera"
        run_host_mock.return_value = RunHostResult(base_error=False, change_error=False, has_diff=None)
        with mock.patch("time.sleep"):
            run_failed = await c.run()
        c.managecode.refresh.assert_has_calls([mock.call("/src"), mock.call("/private")])
        self.assertFalse(run_failed)

    def test_pick_hosts(self):
        # Initialize a simple controller
        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet")
        c.config.puppet_var = self.fixtures / "puppet_var"
        c.config.puppet_src = self.fixtures
        # Single node
        c.pick_hosts("test1.eqiad.wmnet")
        self.assertEqual(c.prod_hosts, set(["test1.eqiad.wmnet"]))
        # Comma-separated nodes
        c.pick_hosts("test.eqiad.wmnet,test1.eqiad.wmnet")
        self.assertEqual(c.prod_hosts, set(["test.eqiad.wmnet", "test1.eqiad.wmnet"]))
        # Comma-separated nodes trailing comma
        c.pick_hosts("test.eqiad.wmnet,test1.eqiad.wmnet,")
        self.assertEqual(c.prod_hosts, set(["test.eqiad.wmnet", "test1.eqiad.wmnet"]))
        # Regex-based matching
        c.pick_hosts(r"re:test\d.eqiad.wmnet")
        self.assertEqual(c.prod_hosts, set(["test1.eqiad.wmnet", "test2.eqiad.wmnet"]))
        # Nodegen based on parsing site.pp
        c.pick_hosts(None)
        s1 = set(["test.eqiad.wmnet", "test1.eqiad.wmnet"])
        s2 = set(["test.eqiad.wmnet", "test2.eqiad.wmnet"])
        s = c.prod_hosts
        assert s == s1 or s == s2

    @requests_mock.mock()
    def test_pick_puppetdb_hosts(self, r_mock):
        # Initialize a simple controller
        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet")
        c.config.puppet_var = self.fixtures / "puppet_var"
        c.config.puppet_src = self.fixtures
        # Role-based matching
        r_mock.get(
            PUPPETDB_URI.format("Role::Grafana"),
            json=get_mocked_response("role"),
            status_code=200,
        )
        c.pick_hosts("O:grafana")
        self.assertEqual(c.prod_hosts, set(["grafana2001.codfw.wmnet"]))
        # Profile-based matching
        r_mock.get(
            PUPPETDB_URI.format("Profile::Grafana::Production"),
            json=get_mocked_response(),
            status_code=200,
        )
        c.pick_hosts("P:grafana::production")
        self.assertEqual(
            c.prod_hosts,
            set(["grafana2001.codfw.wmnet", "cloudmetrics1002.eqiad.wmnet"]),
        )
        # Class-based matching
        r_mock.get(PUPPETDB_URI.format("Grafana"), json=get_mocked_response(), status_code=200)
        c.pick_hosts("C:grafana")
        self.assertEqual(
            c.prod_hosts,
            set(["grafana2001.codfw.wmnet", "cloudmetrics1002.eqiad.wmnet"]),
        )
        # Class-based matching (empty result)
        r_mock.get(
            PUPPETDB_URI.format("Grafana"),
            json=get_mocked_response("empty"),
            status_code=200,
        )

        with self.assertRaises(controller.ControllerNoHostsError):
            c.pick_hosts("C:grafana")

    def test_mixed_nodes(self):
        c = controller.Controller(None, 19, 224570, "test.tools.eqiad.wmflabs")
        c.pick_hosts("test.tools.eqiad.wmflabs")
        self.assertEqual(c.cloud_hosts, set(["test.tools.eqiad.wmflabs"]))
        self.assertEqual(c.prod_hosts, set())

        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet")
        c.pick_hosts("test.eqiad.wmnet")
        self.assertEqual(c.cloud_hosts, set())
        self.assertEqual(c.prod_hosts, set(["test.eqiad.wmnet"]))

        c = controller.Controller(None, 19, 224570, "test.eqiad.wmnet,test.tools.eqiad.wmflabs")
        c.pick_hosts("test.eqiad.wmnet,test.tools.eqiad.wmflabs")
        self.assertEqual(c.cloud_hosts, set(["test.tools.eqiad.wmflabs"]))
        self.assertEqual(c.prod_hosts, set(["test.eqiad.wmnet"]))

    def test_has_failures(self):
        self.assertTrue(controller.Controller.has_failures(results=[Exception()]))
        self.assertTrue(
            controller.Controller.has_failures(
                results=[RunHostResult(base_error=True, change_error=False, has_diff=False)]
            )
        )
        self.assertTrue(
            controller.Controller.has_failures(
                results=[RunHostResult(base_error=False, change_error=True, has_diff=False)]
            )
        )

        self.assertFalse(controller.Controller.has_failures(results=[None]))
        self.assertFalse(
            controller.Controller.has_failures(
                results=[RunHostResult(base_error=False, change_error=False, has_diff=False)]
            )
        )
        self.assertFalse(
            controller.Controller.has_failures(
                results=[RunHostResult(base_error=False, change_error=False, has_diff=True)]
            )
        )
