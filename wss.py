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

        def on_close(wsapp, close_status_code, close_msg):
            pass

        def on_error(wsapp, error):
            self.pc.flCoreConnect = False
            self.pc.l_core.setText('Ошибка соединения с ядром')

        def on_message(wssapp, message):
            print(message)
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
                self.pc.change_auth_status()
            elif message_type == 'cb':
                command = data.get('command')
                if command == 'authpilot' and not self.pilot:
                    if self.pc.flDGTXConnect and not self.pc.flDGTXAuth:
                        pilot = data.get('pilot')
                        ak = data.get('ak')
                        self.pc.authpilot(pilot, ak)
                    else:
                        self.authpilot('error')
                elif command == 'cb_setparameters':
                    parameters = data.get('parameters')
                    self.pc.setparameters(parameters)

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

    def authpilot(self, status, pilot):
        str = {'command': 'authpilot', 'status': status, 'pilot':pilot}
        self.send_bc(str)

    def race_info(self, pilot, parameters, info):
        str = {'command':'race_info', 'pilot':pilot, 'parameters':parameters, 'info':info}
        self.send_bc(str)

    def send_registration(self, psw):
        str = {'id': 10, 'message_type': 'registration', 'data': {'typereg': 'rocket', 'psw':psw, 'version': self.pc.version}}
        str = json.dumps(str)
        self.wsapp.send(str)

    def send_bc(self, data):
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
            if self.pc.flDGTXAuth:
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

    def changeEx(self, name, lastname):
        if lastname:
            self.send_public('unsubscribe', lastname + '@index', lastname + '@orderbook_5')
        self.send_public('subscribe', name + '@index', name + '@orderbook_5')

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

