""" @namespace tserver
	Contains ThreadedServer, ServerFactoryThread and ServerFactory implementations. 
"""

__author__	  = "Christopher Piekarski"
__email__	   = "chris@cpiekarski.com"
__copyright__= """
	This file is part of the jsocket package.
	Copyright (C) 2011 by 
	Christopher Piekarski <chris@cpiekarski.com>

	The tserver module is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	The jsocket package is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with tserver module.  If not, see <http://www.gnu.org/licenses/>."""
__version__	 = "1.0.2"

import jsocket.jsocket_base as jsocket_base
import threading
import socket
import time
import logging

logger = logging.getLogger("jsocket.tserver")

class ThreadedServer(threading.Thread, jsocket_base.JsonServer):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self)
		jsocket_base.JsonServer.__init__(self, **kwargs)
		self._isAlive = False
		
	def _process_message(self, obj):
		""" Pure Virtual Method
		
			This method is called every time a JSON object is received from a client
			
			@param	obj	JSON "key: value" object received from client
			@retval	None
		"""
		pass
	
	def run(self):
		while self._isAlive:
			try:
				self.accept_connection()
			except socket.timeout as e:
				logger.debug("socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.exception(e)
				continue
			
			while self._isAlive:
				try:
					obj = self.read_obj()
					self._process_message(obj)
				except socket.timeout as e:
					logger.debug("socket.timeout: %s" % e)
					continue
				except Exception as e:
					logger.exception(e)
					self._close_connection()
					break
			self.close()
	
	def start(self):
		""" Starts the threaded server. 
			The newly living know nothing of the dead
			
			@retval None	
		"""
		self._isAlive = True
		super(ThreadedServer, self).start()
		logger.debug("Threaded Server has been started.")
		
	def stop(self):
		""" Stops the threaded server.
			The life of the dead is in the memory of the living 
		
			@retval None	
		"""
		self._isAlive = False
		logger.debug("Threaded Server has been stopped.")

class ServerFactoryThread(threading.Thread, jsocket_base.JsonSocket):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self, **kwargs)
		jsocket_base.JsonSocket.__init__(self, **kwargs)
		self._isAlive = False
	
	def swap_socket(self, new_sock):
		""" Swaps the existing socket with a new one. Useful for setting socket after a new connection.
		
			@param	new_sock	socket to replace the existing default jsocket.JsonSocket object	
			@retval	None
		"""
		del self.socket
		self.socket = new_sock
		self.conn = self.socket
	
	def run(self):
		""" Should exit when client closes socket conn.
		    Can force an exit with force_stop.
		"""
		while self._isAlive:
			try:
				obj = self.read_obj()
				self._process_message(obj)
			except socket.timeout as e:
				logger.debug("socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.info("client connection broken, closing socket")
				self._close_connection()
				self._isAlive = False
				break
		self.close()

	def start(self):
		""" Starts the factory thread. 
			The newly living know nothing of the dead

			@retval None
		"""
		self._isAlive = True
		super(ServerFactoryThread, self).start()
		logger.debug("ServerFactoryThread has been started.")

	def force_stop(self):
		""" Force stops the factory thread.
		    Should exit when client socket is closed under normal conditions.
			The life of the dead is in the memory of the living.

			@retval None
		"""
		self._isAlive = False
		logger.debug("ServerFactoryThread has been stopped.")
		
		
class ServerFactory(ThreadedServer):
	def __init__(self, server_thread, **kwargs):
		ThreadedServer.__init__(self, address=kwargs['address'], port=kwargs['port'])
		if not issubclass(server_thread, ServerFactoryThread):
			raise TypeError("serverThread not of type", ServerFactoryThread)
		self._thread_type = server_thread
		self._threads = []
		self._thread_args = kwargs
		self._thread_args.pop('address', None)
		self._thread_args.pop('port', None)
	
	def run(self):
		while self._isAlive:
			tmp = self._thread_type(**self._thread_args)
			self._purge_threads()
			while not self.connected and self._isAlive:
				try:
					self.accept_connection()
				except socket.timeout as e:
					logger.debug("socket.timeout: %s" % e)
					continue
				except Exception as e:
					logger.exception(e)
					continue
				else:
					tmp.swap_socket(self.conn)
					tmp.start()
					self._threads.append(tmp)
					break
		
		self._wait_to_exit()
		self.close()
		
	def stop_all(self):
		for t in self._threads:
			if t.is_alive():
				t.force_stop()
				t.join()
			
	def _purge_threads(self):
		for t in self._threads:
			if not t.is_alive():
				self._threads.remove(t)
			
	def _wait_to_exit(self):
		while self._get_num_of_active_threads():
			time.sleep(0.2)
			
	def _get_num_of_active_threads(self):
		return len([True for x in self._threads if x.is_alive()])
	
	active = property(_get_num_of_active_threads, doc="number of active threads")
