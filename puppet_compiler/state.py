"""Track State changes"""

from dataclasses import dataclass
from typing import Dict, Optional, Set


@dataclass
class ChangeState:
    """Class for the state of the change catalog.

    Arguments:
        hostname: the name of the host we're compiling for (str)
        prod_error: True if there were errors in the base compilation, False otherwise
        change_error: Same as base, but for the change.
        has_diff: Outcome of the diff between the two catalogs. Can either be True (diffs are present),
            False (the diffing process failed) or None (for no changes, or if a catalog failed).
        cancelled: True if the run was cancelled due to a parellel run failing and fail-fast was used.

    """

    host: str
    base_error: bool
    change_error: bool
    has_diff: Optional[bool]
    has_core_diff: Optional[bool]
    cancelled: bool = False

    @property
    def name(self) -> str:
        """Return the name of the state, depending on the outcomes registered.

        For this class:
            'cancelled' if there was no run (cancelled by fail fast)
            'fail' if both catalogs failed to compile, or if the diff process errors out
            'error' if the change breaks compilation
            'noop' if there is no diff, or the change fixes compilation
            'diff' if there are differences.

        """
        if self.cancelled:
            return "cancelled"
        if self.base_error:
            if self.change_error:
                return "fail"
            return "noop"
        if self.change_error:
            return "error"
        if self.has_diff is None:
            return "noop"
        if self.has_diff is False:
            return "fail"
        if self.has_core_diff:
            return "core_diff"
        return "diff"


class StatesCollection:
    """Helper class that is used to store the state of each host."""

    def __init__(self) -> None:
        self.states: Dict[str, Set[str]] = {}

    def add(self, state: ChangeState) -> None:
        """Add a state object to the collection.

        Arguments:
          state - a ChangeState (or derived) object for a run on a specific host.

        """
        if state.name not in self.states:
            self.states[state.name] = set([state.host])
        else:
            self.states[state.name].add(state.host)

    def summary(self, partial: bool = False) -> str:
        """Outputs a summary of the status."""
        output = "Nodes: "
        for state, hosts in self.states.items():
            state_name = "RUNNING" if partial and state == "cancelled" else state.upper()
            output += f"{len(hosts)} {state_name} "
        return output
