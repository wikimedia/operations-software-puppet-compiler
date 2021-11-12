"""Class to manage threading"""
import queue
import threading
import time
from collections import namedtuple
from typing import Callable, Union

from puppet_compiler import _log

Msg = namedtuple("Msg", ["is_error", "value", "args", "kwargs"])


class ThreadExecutor(threading.Thread):
    """
    Manages execution of payloads coming from the ThreadOrchestrator
    """

    def __init__(self, in_queue: queue.Queue, out_queue: queue.Queue) -> None:
        super().__init__()
        self.queue = in_queue
        self.out_queue = out_queue

    def run(self) -> None:
        _log.debug("Spawning a Thread executor")
        while True:
            # grab data from queue
            (payload, args, kwargs) = self.queue.get()
            if payload == "__exit__":
                _log.debug("Stopping Thread")
                return
            _log.debug("Executing payload %s", payload)
            try:
                retval = payload(*args, **kwargs)
                msg = Msg(is_error=False, value=retval, args=args, kwargs=kwargs)
                _log.debug(msg)
                self.out_queue.put(msg)
            # pylint: disable=broad-except
            except Exception as err:
                _log.error("Error in payload")
                _log.exception(str(err))
                msg = Msg(is_error=True, value=err, args=args, kwargs=kwargs)
                self.out_queue.put(msg)
            finally:
                _log.debug("Execution terminated")
                self.queue.task_done()


class ThreadOrchestrator:
    """Manage threads"""

    def __init__(self, pool_size: int = 4):
        self.pool_size = int(pool_size)
        self._thread_processes = []
        self._payload_queue: queue.Queue = queue.Queue()
        self._incoming_queue: queue.Queue = queue.Queue()
        for _ in range(self.pool_size):
            theard = ThreadExecutor(self._payload_queue, self._incoming_queue)
            # this thread will exit with the main program
            self._thread_processes.append(theard)
            theard.start()

    def add(self, payload: Union[str, Callable], *args, **kwdargs) -> None:
        """Add an item to the queue

        Arguments:
            payload: The payload to add

        """
        self._payload_queue.put((payload, args, kwdargs))

    def _process_result(self, callback: Callable) -> None:
        """Execute the callback, with the threads.Msg received from the executor as an argument.

        Arguments:
            callback: The callback to execute

        """
        res = self._incoming_queue.get(True)
        try:
            callback(res)
        # pylint: disable=broad-except
        except Exception as err:
            _log.warning("post-exec callback failed: %s", err)
        self._incoming_queue.task_done()

    def fetch(self, callback: Callable) -> None:
        """Process all results

        Arguments:
            callback: The callback to execute

        """
        while not self._payload_queue.empty():
            if self._incoming_queue.empty():
                time.sleep(5)
                continue
            self._process_result(callback)

        # Wait for all queued jobs to terminate
        self._payload_queue.join()
        while not self._incoming_queue.empty():
            self._process_result(callback)

        # Now send a death signal to all workers.
        for _ in range(len(self._thread_processes)):
            self._payload_queue.put(("__exit__", None, None))
        self._thread_processes = []
