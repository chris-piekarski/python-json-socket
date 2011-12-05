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
import time

logger = logging.getLogger("jsocket")
logger.setLevel(logging.DEBUG)
FORMAT = '[%(asctime)-15s][%(levelname)s][%(module)s][%(funcName)s] %(message)s'
logging.basicConfig(format=FORMAT)

class JsonSocket(object):
	def __init__(self, address='127.0.0.1', port=5489):
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.conn = self.socket
		self._timeout = None
		self._address = address
		self._port = port
	
	def send_obj(self, obj):
		msg = json.dumps(obj)
		if self.socket:
			frmt = "=%ds" % len(msg)
			packed_msg = struct.pack(frmt, msg)
			packed_hdr = struct.pack('=I', len(packed_msg))
			
			self._send(packed_hdr)
			self._send(packed_msg)
			
	def _send(self, msg):
		sent = 0
		while sent < len(msg):
			sent += self.conn.send(msg[sent:])
			
	def _read(self, size):
		data = ''
		while len(data) < size:
			data_tmp = self.conn.recv(size-len(data))
			data += data_tmp
			if data_tmp == '':
				raise RuntimeError("socket connection broken")
		return data

	def _msg_length(self):
		d = self._read(4)
		s = struct.unpack('=I', d)
		return s[0]
	
	def read_obj(self):
		size = self._msg_length()
		data = self._read(size)
		frmt = "=%ds" % size
		msg = struct.unpack(frmt, data)
		return json.loads(msg[0])
	
	def close(self):
		self._close_socket()
		if self.socket is not self.conn:
			self._close_connection()
			
	def _close_socket(self):
		logger.debug("closing main socket")
		self.socket.close()
		
	def _close_connection(self):
		logger.debug("closing the connection socket")
		self.conn.close()
	
	def _get_timeout(self):
		return self._timeout
	
	def _set_timeout(self, timeout):
		self._timeout = timeout
		self.socket.settimeout(timeout)
		
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
	
	def accept_connection(self):
		self._listen()
		self.conn, addr = self._accept()
		self.conn.settimeout(self.timeout)
		logger.debug("connection accepted, conn socket (%s,%d)" % (addr[0],addr[1]))
	
	def _is_connected(self):
		return True if not self.conn else False
	
	connected = property(_is_connected, doc="True if server is connected")

	
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
	
	def server_thread():
		logger.debug("starting JsonServer")
		server = JsonServer()
		server.accept_connection()
		while 1:
			try:
				msg = server.read_obj()
				logger.info("server received: %s" % msg)
				server.send_obj(msg)
			except socket.timeout as e:
				logger.debug("server socket.timeout: %s" % e)
				continue
			except Exception as e:
				logger.error("server: %s" % e)
				break
			
		server.close()
			
	t = threading.Timer(1,server_thread)
	t.start()
	
	time.sleep(2)
	logger.debug("starting JsonClient")
	
	client = JsonClient()
	client.connect()
		
	i = 0
	while i < 10:
		client.send_obj({"i": i})
		try:
			msg = client.read_obj()
			logger.info("client received: %s" % msg)
		except socket.timeout as e:
			logger.debug("client socket.timeout: %s" % e)
			continue
		except Exception as e:
			logger.error("client: %s" % e)
			break
		i = i + 1
	
	client.close()