import sys
import time
import queue

from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import QSettings, pyqtSlot
from mainWindow import UiMainWindow
from wssclient import WSSClient, FromQToF, TimeToF
from loginWindow import LoginWindow
from threading import Lock
from strategy import LM_1, LM_2


ex = {'BTCUSD-PERP':{'TICK_SIZE':5, 'TICK_VALUE':0.1},'ETHUSD-PERP':{'TICK_SIZE':1, 'TICK_VALUE':1}}


class MainWindow(QMainWindow, UiMainWindow):

    settings = QSettings("./config.ini", QSettings.IniFormat)
    serveraddress = settings.value('serveraddress')
    serverport = settings.value('serverport')

    version = '1.4.2'
    lock = Lock()

    #   -----------------------------------------------------------
    flDGTXConnect = False       #   флаг соединения с сайтом DGTX
    flCoreConnect = False       #   флаг соединения с ядром
    flDGTXAuth = False          #   флаг авторизации на сайте (введения правильного API KEY)
    flCoreAuth = False          #   флаг авторизации в ядре

    pilot = None
    symbol = None
    flRace = False

    pnl = 0.0  # текущий PnL
    workingStartTime = 0.0

    info = {'contractmined':0.0,
            'contractcount':0,
            'fundingmined':0.0,
            'fundingcount':0,
            'racetime':0.0,
            'maxBalance':0.0,
            'balance':0.0}

    def __init__(self):

        super().__init__()

        # создание визуальной формы
        self.setupui(self)
        self.show()

        # -----------------------------------------------------------------------

        corereceiveq = queue.Queue()
        serveraddress = 'ws://' + self.serveraddress + ':' + self.serverport
        self.wsscore = WSSClient(corereceiveq, serveraddress)
        self.wsscore.daemon = True
        self.wsscore.start()

        self.corereceiver = FromQToF(corereceiveq, self.receivemessagefromcore)
        self.corereceiver.daemon = True
        self.corereceiver.start()

        self.coresendq = queue.Queue()
        self.coresender = FromQToF(self.coresendq, self.wsscore.send)
        self.coresender.daemon = True
        self.coresender.start()

        # -----------------------------------------------------------------------

        dgtxreceiveq = queue.Queue()
        self.wssdgtx = WSSClient(dgtxreceiveq, "wss://ws.mapi.digitexfutures.com")
        self.wssdgtx.daemon = True
        self.wssdgtx.start()

        self.dgtxreceiver = FromQToF(dgtxreceiveq, self.receivemessagefromdgtx)
        self.dgtxreceiver.daemon = True
        self.dgtxreceiver.start()

        self.dgtxsendq = queue.Queue()
        self.dgtxsender = FromQToF(self.dgtxsendq, self.wssdgtx.send)
        self.dgtxsender.daemon = True
        self.dgtxsender.start()

        #   ---------------------------------------------------------------------

        self.listf = {'orderbook_5': {'q': queue.LifoQueue(), 'f': self.message_orderbook_5},
                      'index': {'q': queue.LifoQueue(), 'f': self.message_index},
                      'tradingStatus': {'q': queue.Queue(), 'f': self.message_tradingStatus},
                      'orderStatus': {'q': queue.Queue(), 'f': self.message_orderStatus},
                      'orderFilled': {'q': queue.Queue(), 'f': self.message_orderFilled},
                      'orderCancelled': {'q': queue.Queue(), 'f': self.message_orderCancelled},
                      'contractClosed': {'q': queue.Queue(), 'f': self.message_contractClosed},
                      'traderStatus': {'q': queue.Queue(), 'f': self.message_traderStatus},
                      'leverage': {'q': queue.Queue(), 'f': self.message_leverage},
                      'funding': {'q': queue.Queue(), 'f': self.message_funding}}
        self.listp = []
        for v in self.listf.values():
            p = FromQToF(v['q'], v['f'])
            self.listp.append(p)
            p.daemon = True
            p.start()

        self.bc_raceinfo_th = TimeToF(self.bc_raceinfo, 10)
        self.bc_raceinfo_th.daemon = True
        self.bc_raceinfo_th.start()

        self.strategy = LM_2(self.dgtxsendq)

    def closeEvent(self, *args, **kwargs):
        self.strategy.stoprace()
        time.sleep(1)

    def receivemessagefromcore(self, data):
        command = data.get('command')
        if command == 'on_open':
            self.flCoreConnect = True
            self.l_core.setText('Соединение с ядром установлено')
        elif command == 'on_close':
            self.flCoreConnect = False
            self.l_core.setText('Устанавливаем соединение с ядром')
        elif command == 'on_error':
            self.flCoreConnect = False
            self.l_core.setText('Ошибка соединения с ядром')
        elif command == 'cb_registration':
            status = data.get('status')
            if status == 'ok':
                self.flCoreAuth = True
                pilot = data.get('pilot')
                ak = data.get('ak')
                self.pilot = pilot
                self.l_info.setText(pilot)
                data = {'id': 4, 'method': 'auth', 'params': {'type':'token', 'value':ak}}
                self.dgtxsendq.put(data)
                self.pb_enter.setText('вход выполнен: ')
            else:
                self.flCoreAuth = False
                message = data.get('message')
                self.l_info.setText(message)
                self.pb_enter.setText('вход не выполнен')
        elif command == 'cb_setparameters':
            parameters = data.get('parameters')
            self.cb_setparameters(parameters)
        elif command == 'cb_marketinfo':
            marketinfo = data.get('info')
            self.cb_marketinfo(marketinfo)
        else:
            pass

    def receivemessagefromdgtx(self, mes):
        ch = mes.get('ch')
        if ch:
            if ch == 'on_open':
                self.flDGTXConnect = True
                self.l_DGTX.setText('Соединение с DGTX установлено')
            elif ch == 'on_close':
                self.flDGTXConnect = False
                self.l_DGTX.setText('Устанавливаем соединение с DGTX')
            elif ch == 'on_error':
                self.flDGTXConnect = False
                self.l_DGTX.setText('Ошибка соединения с DGTX')
            else:
                self.listf[ch]['q'].put(mes.get('data'))

    def userlogined(self, psw):
        data = {'command':'bc_registration', 'psw':psw}
        self.coresendq.put(data)

    @pyqtSlot()
    def buttonLogin_clicked(self):
        if self.flCoreConnect and not self.flCoreAuth:
            rw = LoginWindow()
            rw.userlogined.connect(lambda: self.userlogined(rw.psw))
            rw.setupUi()
            rw.exec_()

    def cb_setparameters(self, parameters):
        self.lock.acquire()
        self.strategy.parameters = parameters
        symbol = parameters.get('symbol')
        if symbol != self.symbol:
            if self.symbol:
                data = {'id': 2, 'method': 'unsubscribe', 'params':[self.symbol + '@index', self.symbol + '@orderbook_5']}
                self.dgtxsendq.put(data)
            data = {'id': 1, 'method': 'subscribe', 'params': [symbol + '@index', symbol + '@orderbook_5']}
            self.dgtxsendq.put(data)
            self.symbol = symbol

        flRace = parameters['flRace']
        if  flRace != self.flRace:
            if flRace:
                self.strategy.startrace()
                self.workingStartTime = time.time()
            else:
                self.strategy.stoprace()
            self.flRace = flRace
        self.lock.release()

        data = {'command':'bc_raceinfo', 'parameters':self.strategy.parameters, 'info':self.info}
        self.coresendq.put(data)

    def cb_marketinfo(self, marketinfo):
        self.lock.acquire()
        self.strategy.setmarketinfo(marketinfo)
        self.lock.release()

    def bc_raceinfo(self):
        if self.flDGTXAuth:
            self.lock.acquire()
            self.info['contractcount'] = self.strategy.contractcount
            if self.flRace:
                self.info['racetime'] = time.time() - self.workingStartTime
            else:
                self.info['racetime'] = 0
            self.lock.release()
            data = {'command': 'bc_raceinfo', 'parameters': self.strategy.parameters, 'info': self.info}
            self.coresendq.put(data)
#   ====================================================================================================================


    def fill_data(self, data):
        balance = data['traderBalance']
        self.info['balance'] = balance
        self.info['maxBalance'] = max(self.info['maxBalance'], balance)

    # ========== обработчики сообщений ===========
    # ==== публичные сообщения
    def message_orderbook_5(self, data):
        self.lock.acquire()
        self.strategy.message_orderbook_5(data)
        self.lock.release()

    def message_index(self, data):
        self.lock.acquire()
        self.strategy.message_index(data)
        self.lock.release()

    # ==== приватные сообщения
    def message_tradingStatus(self, data):
        status = data.get('available')
        if status:
            self.flDGTXAuth = True
            coredata = {'command':'bc_authpilot', 'status':'ok', 'pilot':self.pilot}
            self.coresendq.put(coredata)
            dgtxdata = {'id': 5, 'method': 'getTraderStatus', 'params': {'symbol':self.strategy.parameters['symbol']}}
            self.dgtxsendq.put(dgtxdata)
        else:
            self.flDGTXAuth = False
            coredata = {'command': 'bc_authpilot', 'status': 'error', 'pilot':self.pilot}
            self.coresendq.put(coredata)

    def message_orderStatus(self, data):
        self.lock.acquire()
        self.fill_data(data)
        self.strategy.message_orderStatus(data)
        self.lock.release()

    def message_orderFilled(self, data):
        self.lock.acquire()
        self.info['contractmined'] += (data['pnl'] - self.pnl)
        self.pnl = data['pnl']
        self.strategy.message_orderFilled(data)
        self.fill_data(data)
        self.lock.release()

    def message_orderCancelled(self, data):
        self.lock.acquire()
        self.strategy.message_orderCancelled(data)
        self.lock.release()

    def message_contractClosed(self, data):
        self.lock.acquire()
        self.strategy.message_contractClosed(data)
        self.lock.release()

    def message_traderStatus(self, data):
        self.lock.acquire()
        self.fill_data(data)
        self.pnl = data['pnl']
        self.lock.release()
        self.bc_raceinfo()

    def message_leverage(self, data):
        self.lock.acquire()
        self.strategy.message_leverage(data)
        self.lock.release()

    def message_funding(self, data):
        self.lock.acquire()
        self.info['fundingcount'] += 1
        self.info['fundingmined'] += data['payout']
        self.pnl = data['pnl']

        self.strategy.message_funding()
        self.lock.release()

app = QApplication([])
win = MainWindow()
sys.exit(app.exec_())
