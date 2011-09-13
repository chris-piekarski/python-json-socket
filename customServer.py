__author__      = "Christopher Piekarski"
__email__       = "polo1065@gmail.com"
__copyright__= " Copyright, 2011"
__version__     = "1.0.0"


import threadedServer

class MyServer(threadedServer.ThreadedServer):
    def __init__(self):
        super(MyServer, self).__init__()
        self.timeout = 2.0
    
    def _processMessage(self, obj):
        """ virtual method """
        if obj != '':
            if obj['message'] == "new connection":
                pass
               
    
if __name__ == "__main__":
    c = MyServer()
    c.start()