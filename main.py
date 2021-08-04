import random
import sys
import time
import queue
import logging

from PyQt5.QtWidgets import QMainWindow, QApplication
from PyQt5.QtCore import pyqtSlot
from mainWindow import UiMainWindow
from wssdgtx import WSSDGTX, Worker, Senderq, InTimer
from wsscore import WSSCore, CoreReceiver, CoreSender, Timer
from loginWindow import LoginWindow
import math
from threading import Lock

# = order type
AUTO = 0
MANUAL = 1
OUTSIDE = 2
# = order status
OPENING = 0
ACTIVE = 1
CLOSING = 2

MAXORDERDIST = 5

ex = {'BTCUSD-PERP':{'TICK_SIZE':5, 'TICK_VALUE':0.1},'ETHUSD-PERP':{'TICK_SIZE':1, 'TICK_VALUE':1}}

class Order():
    def __init__(self, **kwargs):
        self.clOrdId = kwargs['clOrdId']
        self.origClOrdId = kwargs['origClOrdId']
        self.orderSide = kwargs['orderSide']
        self.orderType = kwargs['orderType']
        self.px = kwargs['px']
        self.qty = kwargs['qty']
        self.leverage = kwargs['leverage']
        self.paidPx = kwargs['paidPx']
        self.type = kwargs['type']
        self.status = kwargs['status']

class Contract():
    def __init__(self, **kwargs):
        self.contractId = kwargs['contractId']
        self.origContractId = kwargs['origContractId']
        self.status = kwargs['status']

class MainWindow(QMainWindow, UiMainWindow):

    version = '1.1.1'
    lock = Lock()
    leverage = 0                #   текущее плечо
    #   -----------------------------------------------------------
    flDGTXConnect = False       #   флаг соединения с сайтом DGTX
    flCoreConnect = False       #   флаг соединения с ядром
    flDGTXAuth = False          #   флаг авторизации на сайте (введения правильного API KEY)
    flCoreAuth = False          #   флаг авторизации в ядре

    pilot = False
    lastsymbol = None

    listOrders = []  # список активных ордеров
    listContracts = []  # список открытых контрактов

    maxBalance = 0  # максимальный баланс за текущую сессию
    current_cellprice = 0  # текущая тик-цена
    last_cellprice = 0  # прошлая тик-цена
    current_maxbid = 0  # текущая нижняя граница стакана цен
    last_maxbid = 0  # прошлая нижняя граница стакана цен
    current_minask = 0  # текущая верхняя граница стакана цен
    last_minask = 0  # прошлая верхняя граница стакана цен
    spotPx = 0  # текущая spot-цена
    exDist = 0  # TICK_SIZE для текущей валюты
    pnl = 0  # текущий PnL
    timerazban = 0

    parameters = {'symbol':'',
                  'numconts':0,
                  'dist1':0,
                  'dist2':0,
                  'dist3':0,
                  'dist4':0,
                  'dist5':0,
                  'dist1_k':0.0,
                  'dist2_k':0.0,
                  'dist3_k':0.0,
                  'dist4_k':0.0,
                  'dist5_k':0.0,
                  'delayaftermined':0,
                  'bandelay':0.0,
                  'flRace':False}

    marketinfo = {'BTCUSD-PERP':{'avarage_volatility_128':0}, 'ETHUSD-PERP':{'avarage_volatility_128':0}}

    info = {'contractmined':0,
            'contractcount':0,
            'fundingmined':0,
            'fundingcount':0,
            'racetime':0,
            'maxBalance':0,
            'balance':0}

    def __init__(self):

        super().__init__()
        logging.basicConfig(filename='info.log', level=logging.INFO, format='%(asctime)s %(message)s')

        # создание визуальной формы
        self.setupui(self)
        self.show()

    def closeEvent(self, *args, **kwargs):
        self.lock.acquire()
        self.parameters['flRace'] = False
        self.lock.release()
        if self.flDGTXAuth:
            self.dxthread.send_privat('cancelAllOrders', symbol=self.parameters.get('symbol'))
            self.dxthread.send_privat('closePosition', symbol=self.parameters.get('symbol'), ordType='MARKET')
        time.sleep(1)
        self.intimer.flClosing = True
        self.senderq.flClosing = True
        self.dxthread.flClosing = True
        self.dxthread.wsapp.close()
        self.wsscore.flClosing = True
        self.wsscore.wsapp.close()

    def receivemessagefromcore(self, data):
        command = data.get('command')
        if command == 'cb_registration':
            status = data.get('status')
            if status == 'ok':
                self.flCoreAuth = True
            else:
                self.flCoreAuth = False
            self.change_auth_status()
        elif command == 'cb_authpilot':
            if self.flDGTXConnect and not self.flDGTXAuth:
                pilot = data.get('pilot')
                ak = data.get('ak')
                self.cb_authpilot(pilot, ak)
            else:
                data = {'command':'bc_authpilot', 'status':'error', 'pilot':None}
                self.coresendq.put(data)
        elif command == 'cb_setparameters':
            parameters = data.get('parameters')
            self.setparameters(parameters)
        elif command == 'cb_marketinfo':
            marketinfo = data.get('info')
            self.setmarketinfo(marketinfo)

    def userlogined(self, psw):
        if self.flCoreConnect and not self.flCoreAuth:
            data = {'command':'bc_registration', 'psw':psw}
            self.coresendq.put(data)

    @pyqtSlot()
    def pb_start_clicked(self):
        corereceiveq = queue.Queue()

        self.wsscore = WSSCore(self, corereceiveq)
        self.wsscore.daemon = True
        self.wsscore.start()

        self.corereceiver = CoreReceiver(self.receivemessagefromcore, corereceiveq)
        self.corereceiver.daemon = True
        self.corereceiver.start()

        self.coresendq = queue.Queue()

        self.coresender = CoreSender(self.coresendq, self.wsscore)
        self.coresender.daemon = True
        self.coresender.start()

        self.dxthread = WSSDGTX(self)
        self.dxthread.daemon = True
        self.dxthread.start()

        self.sendq = queue.Queue()

        self.senderq = Senderq(self.sendq, self.dxthread)
        self.senderq.daemon = True
        self.senderq.start()

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
        for ch in self.listf.keys():
            p = Worker(self.listf[ch]['q'], self.listf[ch]['f'])
            self.listp.append(p)
            p.daemon = True
            p.start()

        self.intimer = InTimer(self)
        self.intimer.daemon = True
        self.intimer.start()

        self.timer = Timer(self.sendinfo, 10)
        self.timer.daemon = True
        self.timer.start()

    @pyqtSlot()
    def buttonLogin_clicked(self):
        if self.flCoreConnect and not self.flCoreAuth:
            rw = LoginWindow()
            rw.userlogined.connect(lambda: self.userlogined(rw.psw))
            rw.setupUi()
            rw.exec_()

    def change_auth_status(self):
        if self.flCoreAuth:
            self.pb_enter.setText('вход выполнен: ')
            self.pb_enter.setStyleSheet("color:rgb(64, 192, 64); font: bold 12px;border: none")
        else:
            self.pb_enter.setText('вход не выполнен')
            self.pb_enter.setStyleSheet("color:rgb(255, 96, 96); font: bold 12px;border: none")

    def cb_authpilot(self, pilot, ak):
        self.pilot = pilot
        self.dxthread.send_privat('auth', type='token', value=ak)

    def setsymbol(self, symbol):
        self.parameters['symbol'] = symbol
        self.exDist = ex[symbol]['TICK_SIZE']
        if symbol != self.lastsymbol:
            self.dxthread.changeEx(symbol, self.lastsymbol)
            self.lastsymbol = symbol

    def setparameters(self, parameters):
        newsymbol = parameters.get('symbol')
        lastsymbol = self.parameters.get('symbol')
        self.lock.acquire()
        if newsymbol != lastsymbol:
            self.setsymbol(newsymbol)
        if parameters['flRace'] != self.parameters['flRace']:
            if parameters['flRace']:
                self.last_cellprice = 0
                self.intimer.pnlStartTime = self.intimer.workingStartTime = time.time()
                self.intimer.flWorking = True
            else:
                self.dxthread.send_privat('cancelAllOrders', symbol=self.parameters.get('symbol'))
                self.dxthread.send_privat('closePosition', symbol=self.parameters.get('symbol'), ordType='MARKET')
                self.intimer.flWorking = False
        self.parameters = parameters
        self.lock.release()

        data = {'command':'bc_raceinfo', 'parameters':self.parameters, 'info':None}
        self.coresendq.put(data)

    def setmarketinfo(self, marketinfo):
        self.lock.acquire()
        self.marketinfo[marketinfo['symbol']]['avarage_volatility_128'] = marketinfo['market_volatility_128']
        self.lock.release()

    def sendinfo(self):
        if self.flDGTXAuth:
            self.lock.acquire()
            self.info['racetime'] = self.intimer.workingTime
            self.lock.release()
            data = {'command': 'bc_raceinfo', 'parameters': None, 'info': self.info}
            self.coresendq.put(data)
#   ====================================================================================================================
    def returnid(self):
        id = str(round(time.time()) * 1000000 + random.randrange(1000000))
        return id

    def fill_data(self, data):
        balance = data['traderBalance']
        self.info['balance'] = balance
        self.info['maxBalance'] = max(self.info['maxBalance'], balance)

    def changemarketsituation(self):

        def checkLimits():
            if time.time() <= self.timerazban:
                return False
            if self.intimer.pnlTime <= self.parameters['delayaftermined']:
                return False
            return True

        if self.current_cellprice != 0:
            distlist = {}
            for spotdist in range(-MAXORDERDIST, MAXORDERDIST + 1):
                price = self.current_cellprice + spotdist * self.exDist
                if price < self.current_maxbid:
                    bonddist = (self.current_maxbid - price) // self.exDist
                elif price > self.current_minask:
                    bonddist = (price - self.current_minask) // self.exDist
                else:
                    bonddist = 0
                bonddist = min(bonddist, MAXORDERDIST)

                bondmod = 0
                av128 = self.marketinfo[self.parameters['symbol']]['avarage_volatility_128']
                if bonddist == 1  and  av128 <= self.parameters['dist1_k']:
                    bondmod = self.parameters['dist1']
                elif bonddist == 2  and av128 <= self.parameters['dist2_k']:
                    bondmod = self.parameters['dist2']
                elif bonddist == 3  and av128 <= self.parameters['dist3_k']:
                    bondmod = self.parameters['dist3']
                elif bonddist == 4  and av128 <= self.parameters['dist4_k']:
                    bondmod = self.parameters['dist4']
                elif bonddist == 5  and av128 <= self.parameters['dist5_k']:
                    bondmod = self.parameters['dist5']

                if bondmod != 0:
                    distlist[price] = self.parameters['numconts'] * bondmod
        # завершаем ордеры, которые находятся не в списке разрешенных дистанций
        for order in self.listOrders:
            if order.status == ACTIVE:
                if order.px not in distlist.keys():
                    self.dxthread.send_privat('cancelOrder', symbol=self.parameters.get('symbol'),
                                                            clOrdId=order.clOrdId)
                    order.status = CLOSING
        # автоматически открываем ордеры
        if checkLimits():
            listorders = [x.px for x in self.listOrders]
            for dist in distlist.keys():
                if dist not in listorders:
                    if dist < self.current_maxbid:
                        side = 'BUY'
                    else:
                        side = 'SELL'
                    id = self.returnid()
                    self.dxthread.send_privat('placeOrder',
                                              clOrdId=id,
                                              symbol=self.parameters.get('symbol'),
                                              ordType='LIMIT',
                                              timeInForce='GTC',
                                              side=side,
                                              px=dist,
                                              qty=distlist[dist])
                    self.listOrders.append(Order(
                        clOrdId=id,
                        origClOrdId=id,
                        orderSide=side,
                        orderType='LIMIT',
                        px=dist,
                        qty=distlist[dist],
                        leverage=self.leverage,
                        paidPx=0,
                        type=AUTO,
                        status=OPENING))

    # ========== обработчики сообщений ===========
    # ==== публичные сообщения
    def message_orderbook_5(self, data):
        if self.parameters['flRace'] and self.flDGTXConnect:
            self.lock.acquire()
            self.current_maxbid = data.get('bids')[0][0]
            self.current_minask = data.get('asks')[0][0]
            if (self.current_maxbid != self.last_maxbid) or (self.current_minask != self.last_minask):
                self.changemarketsituation()
            self.last_maxbid = self.current_maxbid
            self.last_minask = self.current_minask
            self.lock.release()

    def message_index(self, data):
        if self.parameters['flRace'] and self.flDGTXConnect:
            self.lock.acquire()
            self.spotPx = data['spotPx']
            self.current_cellprice = math.floor(self.spotPx / self.exDist) * self.exDist
            if self.current_cellprice != self.last_cellprice:
                self.changemarketsituation()
            self.last_cellprice = self.current_cellprice
            self.lock.release()

    # ==== приватные сообщения
    def message_tradingStatus(self, data):
        status = data.get('available')
        if status:
            self.flDGTXAuth = True
            data = {'command':'bc_authpilot', 'status':'ok', 'pilot':self.pilot}
        else:
            self.flDGTXAuth = False
            self.pilot = False
            data = {'command': 'bc_authpilot', 'status': 'error', 'pilot':None}
        self.coresendq.put(data)

    def message_orderStatus(self, data):
        self.lock.acquire()
        self.fill_data(data)
        # если приходит сообщение о подтвержденном ордере
        if data['orderStatus'] == 'ACCEPTED':
            foundOrder = False
            origClOrdId = data['origClOrdId']
            for order in self.listOrders:
                if order.origClOrdId == origClOrdId and order.status == OPENING:
                    order.status = ACTIVE
                    order.paidPx = data['paidPx']
                    foundOrder = True
            if not foundOrder:
                self.listOrders.append(Order(clOrdId=data['clOrdId'],
                                             origClOrdId=data['origClOrdId'],
                                             orderSide=data['orderSide'],
                                             orderType=data['orderType'],
                                             px=data['px'],
                                             qty=data['qty'],
                                             leverage=data['leverage'],
                                             paidPx = data['paidPx'],
                                             type = OUTSIDE,
                                             status=ACTIVE))
        self.lock.release()

    def message_orderFilled(self, data):
        self.lock.acquire()
        self.info['contractmined'] += (data['pnl'] - self.pnl)
        self.pnl = data['pnl']

        listfilledorders = [x for x in data['contracts'] if x['qty'] != 0]
        if len(listfilledorders) != 0:
            self.timerazban = time.time() + self.parameters['bandelay']
            self.dxthread.send_privat('cancelAllOrders', symbol=self.parameters.get('symbol'))
            self.listOrders.clear()
            self.info['contractcount'] += len(listfilledorders)

        for cont in listfilledorders:
            self.dxthread.send_privat('closeContract', symbol=self.parameters.get('symbol'), contractId=cont['contractId'], ordType='MARKET')

        self.fill_data(data)
        self.lock.release()

    def message_orderCancelled(self, data):
        self.lock.acquire()
        # если статус отмена
        if data['orderStatus'] == 'CANCELLED':
            listtoremove = [x['origClOrdId'] for x in data['orders']]
            lo = list(self.listOrders)
            for order in lo:
                if order.origClOrdId in listtoremove:
                    self.listOrders.remove(order)
        self.lock.release()

    def message_contractClosed(self, data):
        pass

    def message_traderStatus(self, data):
        self.lock.acquire()
        self.fill_data(data)
        self.pnl = data['pnl']
        self.lock.release()

    def message_leverage(self, data):
        self.lock.acquire()
        self.leverage = data['leverage']
        self.lock.release()

    def message_funding(self, data):
        self.lock.acquire()
        self.info['fundingcount'] += 1
        self.info['fundingmined'] += data['payout']
        self.pnl = data['pnl']

        self.intimer.pnlStartTime = time.time()
        self.dxthread.send_privat('cancelAllOrders', symbol=self.parameters.get('symbol'))
        self.dxthread.send_privat('getTraderStatus', symbol=self.parameters.get('symbol'))
        self.listOrders.clear()
        self.lock.release()

app = QApplication([])
win = MainWindow()
sys.exit(app.exec_())
