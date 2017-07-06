from collections import defaultdict


class StatesCollection(object):
    """
    Helper class that is used to store the state of each host,
    for every different run mode that has been selected.
    """
    def __init__(self):
        # For every run mode, we need to store a dictionary
        # of sets of hosts. Use a defaultdict for that purpose.
        self.modes = defaultdict(dict)

    def add(self, state):
        """
        Add a state object to the collection.

        Params:
          state - a ChangeState (or derived) object for a run on a specific host.
        """
        if state.name not in self.modes[state.mode]:
            self.modes[state.mode][state.name] = set([state.host])
        else:
            self.modes[state.mode][state.name].add(state.host)

    def mode_to_str(self, mode):
        """
        Outputs a summary of the status for a specific run mode.
        """
        output = '[%s] Nodes: ' % mode
        for state, hosts in self.modes[mode].items():
            output += "%s %s " % (len(hosts), state.upper())
        return output


class ChangeState(object):

    def __init__(self, mode, hostname, base, change, diff):
        """
        Class for storing the state for a traditional run that
        diffs between the current production repo and the proposed change.

        Params:
        mode: the current run mode. (str)
        hostname: the name of the host we're compiling for (str)
        base: True if there were errors in the base compilation, False otherwise
        change: Same as base, but for the change.
        diff: Outcome of the diff between the two catalogs. Can either be True (diffs are present),
              False (the diffing process failed) or None (for no changes, or if a catalog failed).
        """
        self.mode = mode
        self.host = hostname
        self.prod_error = base
        self.change_error = change
        self.diff = diff

    @property
    def name(self):
        """
        Return the name of the state, depending on the outcomes registered.

        For this class:
        'fail' if both catalogs failed to compile, or if the diff process errors out
        'error' if the change breaks compilation
        'noop' if there is no diff, or the change fixes compilation
        'diff' if there are differences.
        """
        if self.prod_error:
            if self.change_error:
                return 'fail'
            else:
                return 'noop'
        elif self.change_error:
            return 'error'
        elif self.diff is None:
            return 'noop'
        elif self.diff is False:
            return 'fail'
        else:
            return 'diff'


class FutureState(ChangeState):

    @property
    def name(self):
        if self.prod_error:
            return 'break'
        elif self.change_error or self.diff is False:
            return 'error'
        elif self.diff is None:
            return 'ok'
        else:
            return 'diff'
