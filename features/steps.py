from lettuce import *
import json
import jsonSocket

import threadedServer

convert = lambda s : json.loads(s)

class MyServer(threadedServer.ThreadedServer):
	def __init__(self):
		super(MyServer, self).__init__()
		self.timeout = 2.0
		self.isConnected = False 
	
	def _processMessage(self, obj):
		""" virtual method """
		if obj != '':
			if obj['message'] == "new connection":
				self.isConnected = True
	
	def isAlive(self):
		return self._isAlive

@step('I start the server')
def startTheServer(step):
	world.jsonserver = MyServer()
	world.jsonserver.start()
	
@step('I stop the server')
def stopTheServer(step):
	world.jsonserver.stop()

@step('I connect the client')
def startTheClient(step):
	world.jsonclient = jsonSocket.JsonClient()
	world.jsonclient.connect()
	
@step('I send the object (\{.*\})')
def sendTheObject(step, obj):
	world.jsonclient.sendObj(convert(obj))
	

@step('I see a connection')
def checkConnection(step):
	expected = True
	assert world.jsonserver.isConnected == expected, "%d" % False
	
@step('I see a stopped server')
def checkServerStopped(step):
	expected = False
	assert world.jsonserver.isAlive() == expected, "%d" % False