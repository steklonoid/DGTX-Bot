from threading import Thread
import websocket
import json
import time


class WSSCore(Thread):
    def __init__(self, pc, q):
        super(WSSCore, self).__init__()
        self.pc = pc
        self.q = q
        self.flClosing = False

    def run(self) -> None:
        def on_open(wsapp):
            self.pc.flCoreConnect = True
            self.pc.l_core.setText('Соединение с ядром установлено')

        def on_close(wsapp, close_status_code, close_msg):
            pass

        def on_error(wsapp, error):
            self.pc.flCoreConnect = False
            self.pc.l_core.setText('Ошибка соединения с ядром')

        def on_message(wssapp, message):
            mes = json.loads(message)
            message_type = mes.get('message_type')
            data = mes.get('data')
            if message_type == 'cb':
                self.q.put(data)
            else:
                pass

        while not self.flClosing:
            try:
                self.pc.l_core.setText('Устанавливаем соединение с ядром')
                self.wsapp = websocket.WebSocketApp("ws://localhost:6789", on_open=on_open,
                                                               on_close=on_close, on_error=on_error, on_message=on_message)
                self.wsapp.run_forever()
            except:
                pass
            finally:
                time.sleep(1)

    def send_bc(self, data):
        str = {'message_type':'bc', 'data':data}
        str = json.dumps(str)
        self.wsapp.send(str)


class CoreReceiver(Thread):

    def __init__(self, f, q):
        super(CoreReceiver, self).__init__()
        self.f = f
        self.q = q

    def run(self) -> None:
        while True:
            data = self.q.get()
            self.f(data)


class CoreSender(Thread):

    def __init__(self, q, th):
        super(CoreSender, self).__init__()
        self.q = q
        self.th = th

    def run(self) -> None:
        while True:
            data = self.q.get()
            self.th.send_bc(data)


class Timer(Thread):

    def __init__(self, f, delay):
        super(Timer, self).__init__()
        self.f = f
        self.delay = delay

    def run(self) -> None:
        while True:
            self.f()
            time.sleep(self.delay)

