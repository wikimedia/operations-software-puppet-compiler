import json as python_json
from unittest.mock import MagicMock, mock_open, patch

from test_html import TestHost

from puppet_compiler.presentation import json
from puppet_compiler.state import ChangeState, StatesCollection


@patch.dict("os.environ", {"PUPPET_VERSION_FULL": "12.34"})
def test_json_render():
    j = json.Build(outdir=MagicMock(), hosts_raw="hostZzz,hostAaa")
    with patch("builtins.open", mock_open()) as m_open:
        states_col = StatesCollection()
        states_col.add(
            ChangeState(
                host="hostAaa",
                base_error=False,
                change_error=False,
                has_diff=True,
                has_core_diff=True,
                cancelled=False,
            )
        )

        # Will be serialized to `null`
        json.change_id = None
        json.job_id = None

        j.render(states_col)

        m_open().write.assert_called_with(
            (
                # Json payload:
                '{"puppet_version": "12.34",'
                ' "job_id": null,'
                ' "change_id": null,'
                ' "hosts": ["hostAaa", "hostZzz"],'
                ' "states": {'
                '"core_diff":'
                ' {"description": "Differences to core resources",'
                ' "hosts": ["hostAaa"]}}}'
            )
        )

        # Will be serialized to numbers
        json.change_id = 12345
        json.job_id = 99

        j.render(states_col)

        m_open().write.assert_called_with(
            (
                # Json payload:
                '{"puppet_version": "12.34",'
                ' "job_id": 99,'
                ' "change_id": 12345,'
                ' "hosts": ["hostAaa", "hostZzz"],'
                ' "states": {'
                '"core_diff":'
                ' {"description": "Differences to core resources",'
                ' "hosts": ["hostAaa"]}}}'
            )
        )


class TestJsonHost(TestHost):
    def test_init(self):
        h = json.Host("srv1001.example.org", self.files, "diff")
        self.assertEqual(h.retcode, "diff")
        self.assertEqual(h.hostname, "srv1001.example.org")
        self.assertEqual(h.outfile, self.files.outdir / "host.json")

    def test_render(self):
        h = json.Host("srv1002.example.org", self.files, "diff")
        h.render(self.diffs)
        assert h.outfile.is_file()

        with open(h.outfile) as f:
            j = python_json.load(f)

        self.assertDictContainsSubset(
            {
                "description": "Differences to Puppet defined resources",
                "host": "srv1002.example.org",
                "state": "diff",
            },
            j,
        )
        self.assertIn("diff", j)

        self.assertDictContainsSubset(
            {
                "core": None,
                "full": None,
            },
            j["diff"],
        )
        self.assertIn("main", j.get("diff", {}))

        self.assertEquals(
            {"only_in_other", "only_in_self", "perc_changed", "resource_diffs", "total"}, set(list(j["diff"]["main"]))
        )
