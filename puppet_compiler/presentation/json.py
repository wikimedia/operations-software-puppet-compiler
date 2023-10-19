import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

if sys.version_info < (3, 8):
    from typing_extensions import TypedDict
else:
    from typing import TypedDict

from puppet_compiler import _log
from puppet_compiler.state import StatesCollection

change_id: Optional[int] = None
job_id: Optional[int] = None

state_description = {
    "cancelled": "Not run due to --fail-fast",
    "core_diff": "Differences to core resources",
    "diff": "Differences to Puppet defined resources",
    "error": "Failed to compile when change is applied",
    "fail": "Both catalogs failed to compile or diff errored",
    "noop": "No difference or change fixed compilation",
}


class Build:
    """Summary of the build as json"""

    def __init__(self, outdir: Path, hosts_raw: str) -> None:
        self.outfile = outdir / "build.json"
        self.hosts_raw = hosts_raw

    def render(self, states_col: StatesCollection) -> None:
        """
        Render the build json with info coming from state

        Unlike `html.Index`, `partial` is not supported, hosts that are still
        compiled can be infered by comparing the `hosts` list and the
        `states[].hosts` fields.
        """
        _log.debug("Generating %s", self.outfile)

        BuildState = TypedDict(
            "BuildState",
            {
                "description": str,
                "hosts": List[str],
            },
        )
        BuildDict = TypedDict(
            "BuildDict",
            {
                "puppet_version": str,
                "job_id": Optional[int],
                "change_id": Optional[int],
                "hosts": List[str],
                "states": Dict[str, BuildState],
            },
        )

        build: BuildDict = {}  # type: ignore
        build["puppet_version"] = os.environ["PUPPET_VERSION_FULL"]
        build["job_id"] = job_id
        build["change_id"] = change_id
        build["hosts"] = sorted(self.hosts_raw.split(","))

        build["states"] = {}
        for state_name, hosts_set in sorted(states_col.states.items()):
            description = state_description.get(state_name, "Undescribed state")
            build["states"][state_name] = {
                "description": description,
                "hosts": sorted(list(hosts_set)),
            }

        build_json = json.dumps(build, sort_keys=False)
        with open(self.outfile, "w") as outfile:
            outfile.write(build_json)
