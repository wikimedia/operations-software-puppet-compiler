import threading
import time
from collections import namedtuple
from puppet_compiler import _log
try:
    # python 2.x
    import Queue as queue
    # Work around for pyflakes < 0.6.
    # TODO: Remove when pyflakes has been updated.
    queue
except ImportError:
    # python 3.x
    import queue

Msg = namedtuple('Msg', ['is_error', 'value', 'args', 'kwargs'])


class ThreadExecutor(threading.Thread):
    """
    Manages execution of payloads coming from the ThreadOrchestrator
    """

    def __init__(self, queue, out_queue):
        super(ThreadExecutor, self).__init__()
        self.queue = queue
        self.out_queue = out_queue

    def run(self):
        _log.debug('Spawning a Thread executor')
        while True:
            # grab data from queue
            (payload, args, kwargs) = self.queue.get()
            if payload == '__exit__':
                _log.debug('Stopping Thread')
                return
            _log.debug('Executing payload %s', payload)
            try:
                retval = payload(*args, **kwargs)
                msg = Msg(is_error=False, value=retval, args=args, kwargs=kwargs)
                _log.debug(msg)
                self.out_queue.put(msg)
            except Exception as e:
                # TODO: log correctly
                _log.error("Error in payload")
                _log.debug(str(e))
                msg = Msg(is_error=True, value=e, args=args, kwargs=kwargs)
                self.out_queue.put(msg)
            finally:
                _log.debug('Execution terminated')
                self.queue.task_done()


class ThreadOrchestrator(object):

    def __init__(self, pool_size=4):
        self.pool_size = int(pool_size)
        self._TP = []
        self._payload_queue = queue.Queue()
        self._incoming_queue = queue.Queue()
        for i in range(self.pool_size):
            t = ThreadExecutor(self._payload_queue, self._incoming_queue)
            # this thread will exit with the main program
            self._TP.append(t)
            t.start()

    def add(self, payload, *args, **kwdargs):
        self._payload_queue.put((payload, args, kwdargs))

    def _process_result(self, callback):
        """
        Execute the callback, with the threads.Msg received from the
        executor as an argument.
        """
        res = self._incoming_queue.get(True)
        try:
            callback(res)
        except Exception as e:
            _log.warn('post-exec callback failed: %s', e)
        self._incoming_queue.task_done()

    def fetch(self, callback):
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
        for i in range(len(self._TP)):
            self._payload_queue.put(('__exit__', None, None))
        self._TP = []
        return
