
from pythonosc import dispatcher, osc_server

def start_osc(port=9000):
    disp = dispatcher.Dispatcher()
    disp.map("/*", print)
    server = osc_server.ThreadingOSCUDPServer(("0.0.0.0", port), disp)
    server.serve_forever()
