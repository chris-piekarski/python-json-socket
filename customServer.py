__author__      = "Christopher Piekarski"
__email__       = "polo1065@gmail.com"
__copyright__= " Copyright, 2011"
__version__     = "1.0.0"


import threadedServer
import jsonSocket
import logging

logger = logging.getLogger("jsonSocket.customServer")

class MyServer(threadedServer.ThreadedServer):
    def __init__(self):
        super(MyServer, self).__init__()
        self.timeout = 2.0
        logger.warning("MyServer class in customServer is for example purposes only.")
    
    def _processMessage(self, obj):
        """ virtual method """
        if obj != '':
            if obj['message'] == "new connection":
                logger.info("new connection.")
               
    
if __name__ == "__main__":
    import time
    server = MyServer()
    server.start()
    
    time.sleep(1)
    
    client = jsonSocket.JsonClient()
    client.connect()
    
    time.sleep(1)
    
    client.close()
    server.stop()
