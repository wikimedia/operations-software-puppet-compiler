"""Track State changes"""
from typing import Optional


class StatesCollection:
    """Helper class that is used to store the state of each host."""

    def __init__(self):
        self.states = {}

    def add(self, state):
        """
        Add a state object to the collection.

        Params:
          state - a ChangeState (or derived) object for a run on a specific host.
        """
        if state.name not in self.states:
            self.states[state.name] = set([state.host])
        else:
            self.states[state.name].add(state.host)

    def summary(self):
        """
        Outputs a summary of the status.
        """
        output = "Nodes: "
        for state, hosts in self.states.items():
            output += f"{len(hosts)} {state.upper()} "
        return output


class ChangeState:
    def __init__(
        self,
        hostname: str,
        base_error: bool,
        change_error: bool,
        has_diff: Optional[bool],
    ):
        """Class for the state of the change catalog.

        Arguments:
            hostname: the name of the host we're compiling for (str)
            prod_error: True if there were errors in the base compilation, False otherwise
            change_error: Same as base, but for the change.
            has_diff: Outcome of the diff between the two catalogs. Can either be True (diffs are present),
                False (the diffing process failed) or None (for no changes, or if a catalog failed).

        """
        self.host = hostname
        self.base_error = base_error
        self.change_error = change_error
        self.has_diff = has_diff

    @property
    def name(self) -> str:
        """
        Return the name of the state, depending on the outcomes registered.

        For this class:
            'fail' if both catalogs failed to compile, or if the diff process errors out
            'error' if the change breaks compilation
            'noop' if there is no diff, or the change fixes compilation
            'diff' if there are differences.

        """
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
        return "diff"
