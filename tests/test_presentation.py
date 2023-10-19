from unittest.mock import MagicMock, mock_open, patch

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
