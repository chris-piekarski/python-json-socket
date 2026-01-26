""" @namespace tserver
    Contains ThreadedServer, ServerFactoryThread and ServerFactory implementations. 
"""

__author__   = "Christopher Piekarski"
__email__    = "chris@cpiekarski.com"
__copyright__= """
    Copyright (C) 2011 by
    Christopher Piekarski <chris@cpiekarski.com>

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""
__version__  = "1.0.3"

import threading
import socket
import time
import logging
import abc
from typing import Optional
from jsocket import jsocket_base

logger = logging.getLogger("jsocket.tserver")


class ThreadedServer(threading.Thread, jsocket_base.JsonServer, metaclass=abc.ABCMeta):
    """Single-threaded server that accepts one connection and processes messages in its thread."""

    def __init__(self, **kwargs):
        threading.Thread.__init__(self)
        jsocket_base.JsonServer.__init__(self, **kwargs)

    @abc.abstractmethod
    def _process_message(self, obj) -> Optional[dict]:
        """Pure Virtual Method

        This method is called every time a JSON object is received from a client

        @param obj JSON "key: value" object received from client
        @retval None or a response object
        """
        # Return None in the base class to satisfy linters; subclasses should override.
        return None

    def run(self):
        # Ensure the run loop is active even when run() is invoked directly
        # (tests may call run() in a separate thread without invoking start()).
        while True:
            self.accept_connection()
            self.send_obj(self._process_message(self.read_obj()))

    def start(self):
        """ Starts the threaded server. 
            The newly living know nothing of the dead
            
            @retval None 
        """
        super().start()
        logger.debug("Threaded Server started on %s:%s", self.address, self.port)

    def stop(self):
        """ Stops the threaded server.
            The life of the dead is in the memory of the living 

            @retval None 
        """
        logger.debug("Threaded Server stopped on %s:%s", self.address, self.port)


class ServerFactoryThread(threading.Thread, jsocket_base.JsonSocket, metaclass=abc.ABCMeta):
    """Per-connection worker thread used by ServerFactory."""

    def __init__(self, **kwargs):
        threading.Thread.__init__(self, **kwargs)
        self.socket = None
        self.conn = None
        jsocket_base.JsonSocket.__init__(self, **kwargs)
        self._is_alive = False

    def swap_socket(self, new_sock):
        """ Swaps the existing socket with a new one. Useful for setting socket after a new connection.

            @param new_sock socket to replace the existing default jsocket.JsonSocket object 
            @retval None
        """
        self.socket = new_sock
        self.conn = self.socket

    def run(self):
        """ Should exit when client closes socket conn.
            Can force an exit with force_stop.
        """
        while self._is_alive:
            try:
                obj = self.read_obj()
                resp_obj = self._process_message(obj)
                if resp_obj is not None:
                    logger.debug("sending response (%s)", _response_summary(resp_obj))
                    self.send_obj(resp_obj)
            except socket.timeout as e:
                logger.debug("worker read timeout waiting for data: %s", e)
                continue
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.info("client connection broken, closing connection: %s", e)
                self._is_alive = False
                break
        self._close_connection()
        if hasattr(self, "socket"):
            self._close_socket()

    @abc.abstractmethod
    def _process_message(self, obj) -> Optional[dict]:
        """Pure Virtual Method - Implementer must define protocol

        @param obj JSON "key: value" object received from client
        @retval None or a response object
        """
        # Return None in the base class to satisfy linters; subclasses should override.
        return None

    def start(self):
        """ Starts the factory thread. 
            The newly living know nothing of the dead

            @retval None
        """
        self._is_alive = True
        super().start()
        logger.debug("ServerFactoryThread started (%s)", self.name)

    def force_stop(self):
        """ Force stops the factory thread.
            Should exit when client socket is closed under normal conditions.
            The life of the dead is in the memory of the living.

            @retval None
        """
        self._is_alive = False
        logger.debug("ServerFactoryThread stopped (%s)", self.name)


class ServerFactory(ThreadedServer):
    """Accepts clients and spawns a ServerFactoryThread per connection."""
    def __init__(self, server_thread, **kwargs):
        ThreadedServer.__init__(self, address=kwargs['address'], port=kwargs['port'])
        if not issubclass(server_thread, ServerFactoryThread):
            raise TypeError("serverThread not of type", ServerFactoryThread)
        self._thread_type = server_thread
        self._threads = []
        self._thread_args = kwargs
        self._thread_args.pop('address', None)
        self._thread_args.pop('port', None)

    def _process_message(self, obj) -> Optional[dict]:
        """ServerFactory does not process messages itself."""
        return None

    def run(self):
        # Ensure the run loop is active even when run() is invoked directly
        # (tests may call run() in a separate thread without invoking start()).
        if not self._is_alive:
            self._is_alive = True
        while self._is_alive:
            tmp = self._thread_type(**self._thread_args)
            self._purge_threads()
            while not self.connected and self._is_alive:
                try:
                    self.accept_connection()
                except socket.timeout as e:
                    logger.debug("factory accept timeout on %s:%s: %s", self.address, self.port, e)
                    continue
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.exception("accept error: %s", e)
                    continue
                else:
                    # Hand off the accepted connection to the worker
                    accepted_conn = self.conn
                    # Reset server connection reference so we can accept again
                    self._reset_connection_ref()
                    tmp.swap_socket(accepted_conn)
                    tmp.start()
                    self._threads.append(tmp)
                    break

        self._wait_to_exit()
        self.close()

    def stop_all(self):
        """Stop and join all active worker threads."""
        for t in self._threads:
            if t.is_alive():
                t.force_stop()
                t.join()

    def _purge_threads(self):
        # Rebuild list to avoid mutating while iterating
        self._threads = [t for t in self._threads if t.is_alive()]

    def stop(self):
        # Stop accepting and stop all workers
        self._is_alive = False
        try:
            self.stop_all()
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        logger.debug("ServerFactory stopped on %s:%s", self.address, self.port)

    def _wait_to_exit(self):
        """Block until all worker threads have finished."""
        while self._get_num_of_active_threads():
            time.sleep(0.2)

    def _get_num_of_active_threads(self):
        return len([True for x in self._threads if x.is_alive()])

    active = property(_get_num_of_active_threads, doc="number of active threads")
