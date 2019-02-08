""" @package jsocket
	@brief Main package importing two modules, jsocket_base and tserver into the scope of jsocket.
	
	@example example_servers.py
	
	@mainpage JSocket - Fast & Scalable JSON Server & Client 
	@section Installation
	
	The jsocket package should always be installed using the stable PyPi releases.
	Either use "easy_install jsocket" or "pip install jsocket" to get the latest stable version.
	
	@section Usage
	
	The jsocket package is for use during the development of distributed systems. There are two ways to 
	use the package. The first and simplest is to create a custom single threaded server by overloading the
	the jsocket.ThreadedServer class (see example one below).
	
	The second, is to use the server factory functionality by overloading the jsocket.ServerFactoryThread
	class and passing the declaration to the jsocket.ServerFactory(FactoryThread) object. This creates a
	multithreaded custom JSON server for any number of simultaneous clients (see example two below).
	
	@section Examples
	@b 1: The following snippet simply creates a custom single threaded server by overloading jsocket.ThreadedServer
	@code
	class MyServer(jsocket.ThreadedServer):
		# This is a basic example of a custom ThreadedServer.
		def __init__(self):
			super(MyServer, self).__init__()
			self.timeout = 2.0
			logger.warning("MyServer class in customServer is for example purposes only.")
		
		def _process_message(self, obj):
			# virtual method
			if obj != '':
				if obj['message'] == "new connection":
					logger.info("new connection.")
	@endcode
				
	@b 2: The following snippet creates a custom factory thread and starts a factory server. The factory server
	will allocate and run a factory thread for each new client.
	
	@code
	import jsocket
	
	class MyFactoryThread(jsocket.ServerFactoryThread):
		# This is an example factory thread, which the server factory will
		# instantiate for each new connection.
		def __init__(self):
			super(MyFactoryThread, self).__init__()
			self.timeout = 2.0
		
		def _process_message(self, obj):
			# virtual method - Implementer must define protocol
			if obj != '':
				if obj['message'] == "new connection":
					logger.info("new connection.")
				else:
					logger.info(obj)
		
	server = jsocket.ServerFactory(MyFactoryThread)
	server.timeout = 2.0
	server.start()
	
	client = jsocket.JsonClient()
	client.connect()
	client.send_obj({"message": "new connection"})
	
	client.close()
	server.stop()
	server.join()
	@endcode
	
"""
from jsocket.jsocket_base import *
from jsocket.tserver import *
