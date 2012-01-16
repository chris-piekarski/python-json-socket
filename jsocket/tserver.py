""" Example of a threaded server based on a JsonServer object in the jsonSocket module """
import jsocket
import threading
import socket
import time
import logging

logger = logging.getLogger("jsocket.tserver")

class ThreadedServer(threading.Thread, jsocket.JsonServer):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self)
		jsocket.JsonServer.__init__(self)
		self._isAlive = False
		
	def _process_message(self, obj):
		""" virtual method """
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
		""" The newly living know nothing of the dead """
		self._isAlive = True
		super(ThreadedServer, self).start()
		logger.debug("Threaded Server has been started.")
		
	def stop(self):
		""" The life of the dead is in the memory of the living """
		self._isAlive = False
		logger.debug("Threaded Server has been stopped.")

class ServerFactoryThread(threading.Thread, jsocket.JsonSocket):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self, **kwargs)
		jsocket.JsonSocket.__init__(self, **kwargs)
	
	def swap_socket(self, new_sock):
		del self.socket
		self.socket = new_sock
		self.conn = self.socket
	
	def run(self):
		while self.isAlive():
			try:
				obj = self.read_obj()
				self._process_message(obj)
			except socket.timeout as e:
				logger.debug("socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.info("client connection broken, closing socket")
				self._close_connection()
				break
		self.close()
		
		
class ServerFactory(ThreadedServer):
	def __init__(self, server_thread, **kwargs):
		ThreadedServer.__init__(self, **kwargs)
		if not issubclass(server_thread, ServerFactoryThread):
			raise TypeError("serverThread not of type", ServerFactoryThread)
		self._thread_type = server_thread
		self._threads = []
	
	def run(self):
		while self._isAlive:
			tmp = self._thread_type()
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
			if t.isAlive():
				t.exit()
				t.join()
			
	def _purge_threads(self):
		for n, t in enumerate(self._threads):
			if not t.isAlive():
				print n
				print self._threads
				self._threads.remove(n)
			
	def _wait_to_exit(self):
		while self._get_num_of_active_threads():
			time.sleep(0.2)
			
	def _get_num_of_active_threads(self):
		return len([True for x in self._threads if x.isAlive()])
	
	active = property(_get_num_of_active_threads, doc="number of active threads")