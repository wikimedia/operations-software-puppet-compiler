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
from puppet_compiler.directories import HostFiles
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


def json_iter_to_sorted_list(obj):
    """
    Convert iterables (set) to list to allow their json serialization

    The resulting list is sorted.

    Non iterables are passed to the base default handler.

    Taken from Python documentation for `json.JSONEncoder.default`

    Example:
      >>> json.dumps(set(3, 2, 1))
      TypeError: Object of type set is not JSON serializable
      >>> json.dumps(set(3, 2, 1), default=json_iter_to_list)
      "{[1, 2, 3]}"
    """
    try:
        iterable = iter(obj)
    except TypeError:
        pass
    else:
        return sorted(list(iterable))

    # Pass anything else to the base default
    return json.JSONEncoder.default(obj)


class Host:
    """Outcome of a host compilation"""

    def __init__(self, hostname: str, files: HostFiles, retcode: str):
        self.retcode = retcode
        self.hostname = hostname
        self.outfile = files.outdir / "host.json"

    def render(
        self, diffs: Optional[Dict] = None, core_diffs: Optional[Dict] = None, full_diffs: Optional[Dict] = None
    ) -> None:
        host = {
            "host": self.hostname,
            "state": self.retcode,
            "description": state_description.get(self.retcode, "Undescribed state"),
            "diff": {
                "full": full_diffs,
                "core": core_diffs,
                "main": diffs,
            },
        }

        _log.debug("Generating %s", self.outfile)

        host_json = json.dumps(host, sort_keys=False, default=json_iter_to_sorted_list)
        with open(self.outfile, "w") as outfile:
            outfile.write(host_json)


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
