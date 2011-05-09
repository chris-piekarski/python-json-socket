""" contains a json object message passing server and client """

__author__	  = "Christopher Piekarski"
__email__	   = "polo1065@gmail.com"
__copyright__= """
	This file is part of the jsonSocket module.
	Copyright (C) 2011 by 
	Christopher Piekarski <polo1065@gmail.com>

	The jsonSocket module is free software: you can redistribute it and/or modify
	it under the terms of the GNU General Public License as published by
	the Free Software Foundation, either version 3 of the License, or
	(at your option) any later version.

	The jsonSocket module is distributed in the hope that it will be useful,
	but WITHOUT ANY WARRANTY; without even the implied warranty of
	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
	GNU General Public License for more details.

	You should have received a copy of the GNU General Public License
	along with jsonSocket module.  If not, see <http://www.gnu.org/licenses/>."""
__version__	 = "1.0.0"

import json
import socket
import struct
import logging

logger = logging.getLogger("jsonSocket")
logger.setLevel(logging.DEBUG)
FORMAT = '[%(asctime)-15s][%(levelname)s][%(funcName)s] %(message)s'
logging.basicConfig(format=FORMAT)

class JsonSocket(object):
	def __init__(self, address='127.0.0.1', port=5489):
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.conn = self.socket
		self._timeout = None
		self._address = address
		self._port = port
	
	def sendObj(self, obj):
		msg = json.dumps(obj)
		if self.socket:
			frmt = "=%ds" % len(msg)
			packedMsg = struct.pack(frmt, msg)
			packedHdr = struct.pack('=I', len(packedMsg))
			
			self._send(packedHdr)
			self._send(packedMsg)
			
	def _send(self, msg):
		sent = 0
		while sent < len(msg):
			sent += self.conn.send(msg[sent:])
			
	def _read(self, size):
		data = ''
		while len(data) < size:
			dataTmp = self.conn.recv(size-len(data))
			data += dataTmp
			if dataTmp == '':
				raise RuntimeError("socket connection broken")
		return data

	def _msgLength(self):
		d = self._read(4)
		s = struct.unpack('=I', d)
		return s[0]
	
	def readObj(self):
		size = self._msgLength()
		data = self._read(size)
		frmt = "=%ds" % size
		msg = struct.unpack(frmt,data)
		return json.loads(msg[0])
	
	def close(self):
		logger.debug("closing main socket")
		self._closeSocket()
		if self.socket is not self.conn:
			logger.debug("closing connection socket")
			self._closeConnection()
			
	def _closeSocket(self):
		self.socket.close()
		
	def _closeConnection(self):
		self.conn.close()
	
	def _get_timeout(self):
		return self._timeout
	
	def _set_timeout(self, timeout):
		self._timeout = timeout
		self.settimeout(timeout)
		
	def _get_address(self):
		return self._address
	
	def _set_address(self, address):
		pass
	
	def _get_port(self):
		return self._port
	
	def _set_port(self, port):
		pass
			
	timeout = property(_get_timeout, _set_timeout,doc='Get/set the socket timeout')
	address = property(_get_address, _set_address,doc='read only property socket address')
	port = property(_get_port, _set_port,doc='read only property socket port')

	
class JsonServer(JsonSocket):
	def __init__(self, address='127.0.0.1', port=5489):
		super(JsonServer, self).__init__(address, port)
		self._bind()
	
	def _bind(self):
		self.socket.bind( (self.address,self.port) )

	def _listen(self):
		self.socket.listen(1)
	
	def _accept(self):
		return self.socket.accept()
	
	def acceptConnection(self):
		self._listen()
		
		self.conn, addr = self._accept()
		self.conn.settimeout(self.timeout)
		logger.debug("connection accepted, conn socket (%s,%d)" % (addr[0],addr[1]))

	
class JsonClient(JsonSocket):
	def __init__(self, address='127.0.0.1', port=5489):
		super(JsonClient, self).__init__(address, port)
		
	def connect(self):
		for i in range(10):
			try:
				self.socket.connect( (self.address, self.port) )
			except socket.error as msg:
				logger.error("SockThread Error: %s" % msg)
				time.sleep(3)
				continue
			logger.info("...Socket Connected")
			return True
		return False

	
if __name__ == "__main__":
	""" basic json echo server """
	import threading, time
	
	def serverThread():
		logger.debug("starting JsonServer")
		server = JsonServer()
		server.acceptConnection()
		while 1:
			try:
				msg = server.readObj()
				logger.info("server received: %s" % msg)
				server.sendObj(msg)
			except socket.timeout as e:
				logger.debug("server socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.error("server: %s" % e)
				break
			
		server.close()
			
	t = threading.Timer(1,serverThread)
	t.start()
	
	time.sleep(2)
	logger.debug("starting JsonClient")
	
	client = JsonClient()
	client.connect()
		
	i = 0
	while i < 10:
		client.sendObj({"i": i})
		try:
			msg = client.readObj()
			logger.info("client received: %s" % msg)
		except socket.timeout as e:
			logger.debug("client socket.timeout: %s" % e)
			continue
		except Exception as e:
			logger.error("client: %s" % e)
			break
		i = i + 1
	
	client.close()