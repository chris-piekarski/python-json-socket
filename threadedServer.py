""" Example of a threaded server based on a JsonServer object in the jsonSocket module """
import jsonSocket
import threading
import socket

import logging

logger = logging.getLogger("threadedServer")
logger.setLevel(logging.DEBUG)
FORMAT = '[%(asctime)-15s][%(levelname)s][%(funcName)s] %(message)s'
logging.basicConfig(format=FORMAT)

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
	
	def start(self):
		self._isAlive = True
		super(ThreadedServer, self).start()
		
	def stop(self):
		""" The life of the dead is in the memory of the living """
		self._isAlive = False
