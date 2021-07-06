from threading import Thread
import websocket
import json
import time
import logging


class WSSCore(Thread):
    def __init__(self, pc):
        super(WSSCore, self).__init__()
        self.pc = pc
        self.flClosing = False

    def run(self) -> None:
        def on_open(wsapp):
            self.pc.flCoreConnect = True
            self.pc.l_core.setText('Соединение с ядром установлено')
            self.registration()

        def on_close(wsapp, close_status_code, close_msg):
            pass

        def on_error(wsapp, error):
            self.pc.flCoreConnect = False
            self.pc.l_core.setText('Ошибка соединения с ядром')

        def on_message(wssapp, message):
            mes = json.loads(message)
            id = mes.get('id')
            message_type = mes.get('message_type')
            data = mes.get('data')
            if message_type == 'registration':
                status = data.get('status')
                if status == 'ok':
                    self.pc.flCoreAuth = True
                else:
                    self.pc.flCoreAuth = False
            elif message_type == 'cb':
                command = data.get('command')
                if command == 'authpilot':
                    ak = data.get('ak')
                    self.pc.dxthread.send_privat('auth', type='token', value=ak)

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

    def registration(self):
        str = {'id': 10, 'message_type': 'registration', 'data': {'typereg': 'rocket', 'version': self.pc.version}}
        str = json.dumps(str)
        self.wsapp.send(str)

    def senddata(self, data):
        str = {'id':10, 'message_type':'bc', 'data':data}
        str = json.dumps(str)
        self.wsapp.send(str)


class WSSDGTX(Thread):
    methods = {'subscribe':1, 'unsubscribe':2, 'subscriptions':3, 'auth':4, 'placeOrder':5, 'cancelOrder':6,
               'cancelAllOrders':7, 'placeCondOrder':8, 'cancelCondOrder':9, 'closeContract':10, 'closePosition':11,
               'getTraderStatus':12, 'changeLeverageAll':13}
    def __init__(self, pc):
        super(WSSDGTX, self).__init__()
        self.pc = pc
        self.flClosing = False

    def run(self) -> None:
        def on_open(wsapp):
            logging.info('open')
            self.pc.flDGTXConnect = True
            self.pc.l_DGTX.setText('Соединение с DGTX установлено')
            if self.pc.flAuth:
                self.pc.authser()

        def on_close(wsapp, close_status_code, close_msg):
            logging.info('close / ' + str(close_status_code) + ' / ' + str(close_msg))

        def on_error(wsapp, error):
            self.pc.flDGTXConnect = False
            self.pc.l_DGTX.setText('Ошибка соединения с DGTX')
            time.sleep(1)

        def on_message(wssapp, message):
            if message == 'ping':
                wssapp.send('pong')
            else:
                self.message = json.loads(message)
                id = self.message.get('id')
                status = self.message.get('status')
                ch = self.message.get('ch')
                if ch:
                    self.pc.listf[ch]['q'].put(self.message.get('data'))
                elif status:
                    if status == 'error':
                        logging.info(self.message)

        while not self.flClosing:
            try:
                self.pc.l_DGTX.setText('Устанавливаем соединение с DGTX')
                self.wsapp = websocket.WebSocketApp("wss://ws.mapi.digitexfutures.com", on_open=on_open,
                                                    on_close=on_close, on_error=on_error, on_message=on_message)
                self.wsapp.run_forever()
            except:
                pass
            finally:
                time.sleep(1)

    def changeEx(self, name):
        self.send_public('subscribe', name + '@index', name + '@ticker', name + '@orderbook_1')

    def send_public(self, method, *params):
        pd = {'id':self.methods.get(method), 'method':method}
        if params:
            pd['params'] = list(params)
        strpar = json.dumps(pd)
        self.pc.sendq.put(strpar)

    def send_privat(self, method, **params):
        pd = {'id':self.methods.get(method), 'method':method, 'params':params}
        strpar = json.dumps(pd)
        self.pc.sendq.put(strpar)


class Worker(Thread):
    def __init__(self, q, f):
        super(Worker, self).__init__()
        self.q = q
        self.f = f

    def run(self) -> None:
        while True:
            data = self.q.get()
            self.f(data)


class Senderq(Thread):
    def __init__(self, q, th):
        super(Senderq, self).__init__()
        self.q = q
        self.th = th
        self.flClosing = False

    def run(self) -> None:
        while not self.flClosing:
            data = self.q.get()
            try:
                self.th.wsapp.send(data)
            except:
                pass
            time.sleep(0.1)


class InTimer(Thread):
    def __init__(self, pc):
        super(InTimer, self).__init__()
        self.pc = pc
        self.delay = 0.1
        self.pnlStartTime = 0
        self.pnlTime = 0
        self.workingStartTime = 0
        self.flWorking = False
        self.flClosing = False

    def run(self) -> None:
        while not self.flClosing:
            if self.flWorking:
                self.pnlTime = time.time() - self.pnlStartTime
            time.sleep(self.delay)


class Analizator(Thread):

    def __init__(self, f):
        super(Analizator, self).__init__()
        self.delay = 1
        self.flClosing = False
        self.f = f

    def run(self) -> None:
        while not self.flClosing:
            self.f()
            time.sleep(self.delay)
