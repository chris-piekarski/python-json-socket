""" Example of a threaded server based on a JsonServer object in the jsonSocket module """
import jsonSocket
import threading
import socket

import logging

logger = logging.getLogger("jsonSocket.threadedServer")

class ThreadedServer(threading.Thread, jsonSocket.JsonServer):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self)
		jsonSocket.JsonServer.__init__(self)
		self._isAlive = False
		
	def _processMessage(self, obj):
		""" virtual method """
		pass
	
	def run(self):
		while self._isAlive:
			try:
				self.acceptConnection()
			except socket.timeout as e:
				logger.debug("socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.exception(e)
				continue
			
			while self._isAlive:
				try:
					obj = self.readObj()
					self._processMessage(obj)
				except socket.timeout as e:
					logger.debug("socket.timeout: %s" % e)
					continue
				except Exception as e:
					logger.exception(e)
					self._closeConnection()
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

class FactoryServerThread(threading.Thread, jsonSocket.JsonSocket):
	def __init__(self, **kwargs):
		threading.Thread.__init__(self, **kwargs)
		jsonSocket.JsonSocket.__init__(self, **kwargs)
	
	def swapSocket(self, newSock):
		del self.socket
		self.socket = newSock
		self.conn = self.socket
	
	def run(self):
		while self.isAlive():
			try:
				obj = self.readObj()
				self._processMessage(obj)
			except socket.timeout as e:
				logger.debug("socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.info("client connection broken, closing socket")
				self._closeConnection()
				break
		self.close()
		
		
class FactoryServer(ThreadedServer):
	def __init__(self, serverThread, **kwargs):
		ThreadedServer.__init__(self, **kwargs)
		if not issubclass(serverThread, FactoryServerThread):
			raise TypeError("serverThread not of type", FactoryServerThread)
		self._threadType = serverThread
		self._threads = []
	
	def run(self):
		while self._isAlive:
			tmp = self._threadType()
			self._purgeThreads()
			while not self.connected:
				try:
					self.acceptConnection()
				except socket.timeout as e:
					logger.debug("socket.timeout: %s" % e)
					continue
				except Exception as e:
					logger.exception(e)
					continue
				else:
					tmp.swapSocket(self.conn)
					tmp.start()
					self._threads.append(tmp)
					break
		
		self._waitToExit()		
		self.close()
			
	def stopAll(self):
		for t in self._threads:
			if t.isAlive():
				t.exit()
				t.join()
			
	def _purgeThreads(self):
		for n, t in enumerate(self._threads):
			if not t.isAlive():
				print n
				print self._threads
				self._threads.remove(n)
			
	def _waitToExit(self):
		while _getNumOfActiveThreads():
			time.sleep(0.2)
			
	def _getNumOfActiveThreads(self):
		return len([True for x in self._threads if x.isAlive()])
	
	active = property(_getNumOfActiveThreads, doc="number of active threads")