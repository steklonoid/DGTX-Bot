import random
import sys
import os
import time
import queue
import logging

from PyQt5.QtWidgets import QMainWindow, QApplication, QMessageBox
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import QSettings, pyqtSlot
from PyQt5.QtSql import QSqlDatabase, QSqlQuery
from mainWindow import UiMainWindow
from wss import WSSDGTX, Worker, Senderq, InTimer, Analizator, WSSCore
from loginWindow import LoginWindow
import hashlib
from Crypto.Cipher import AES # pip install pycryptodome
import math
import numpy as np
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
NUMTICKS = 128

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
    version = '1.0.3'
    settings = QSettings("./config.ini", QSettings.IniFormat)   # файл настроек
    lock = Lock()

    user = ''
    psw = ''

    #   получаемые данные
    leverage = 0                #   текущее плечо
    traderBalance = 0           #   текущий баланс
    traderBalance_usd = 0       #   текущий баланс в usd
    contractValue = 0           #   величина контракта
    dgtxUsdRate = 0             #   курс DGTX / USD
    current_cellprice = 0       #   текущая тик-цена
    last_cellprice = 0          #   прошлая тик-цена
    current_maxbid = 0          #   текущая нижняя граница стакана цен
    last_maxbid = 0             #   прошлая нижняя граница стакана цен
    current_minask = 0          #   текущая верхняя граница стакана цен
    last_minask = 0             #   прошлая верхняя граница стакана цен

    spotPx = 0                  #   текущая spot-цена
    lastSpotPx = 0              #   прошлая spot-цена
    exDist = 0                  #   TICK_SIZE для текущей валюты
    maxBalance = 0              #   максимальный баланс за текущую сессию

    listOrders = []             #   список активных ордеров
    listContracts = []          #   список открытых контрактов
    listTick = np.zeros((NUMTICKS, 3), dtype=float)          #   массив последних тиков
    tickCounter = 0             #   счетчик тиков
    market_volatility = 0       #   текущая волатильность
    contractmined = 0           #   добыто на контрактах
    contractcount = 0           #   количество сорванных контрактов
    pnl = 0                     #   текущий PnL
    fundingcount = 0            #   выплат за текущую сессию
    fundingmined = 0            #   добыто за текущую сессию

    timerazban = 0

    flDGTXConnect = False       #   флаг соединения с сайтом DGTX
    flCoreConnect = False       #   флаг соединения с ядром
    flDGTXAuth = False          #   флаг авторизации на сайте (введения правильного API KEY)
    flCoreAuth = False          #   флаг авторизации в ядре

    flAutoLiq = False           #   флаг разрешенного авторазмещения ордеров (нажатия кнопки СТАРТ)

    def __init__(self):

        super().__init__()
        logging.basicConfig(filename='info.log', level=logging.INFO, format='%(asctime)s %(message)s')

        # создание визуальной формы
        self.setupui(self)
        self.show()

        self.sendq = queue.Queue()

        self.wsscore = WSSCore(self)
        self.wsscore.daemon = True
        self.wsscore.start()

        self.dxthread = WSSDGTX(self)
        self.dxthread.daemon = True
        self.dxthread.start()

        self.senderq = Senderq(self.sendq, self.dxthread)
        self.senderq.daemon = True
        self.senderq.start()

        self.listf = {'orderbook_1':{'q':queue.LifoQueue(), 'f':self.message_orderbook_1},
                      'index':{'q':queue.LifoQueue(), 'f':self.message_index},
                      'ticker':{'q':queue.LifoQueue(), 'f':self.message_ticker},
                      'tradingStatus': {'q': queue.Queue(), 'f': self.message_tradingStatus},
                      'orderStatus': {'q': queue.Queue(), 'f': self.message_orderStatus},
                      'orderFilled': {'q': queue.Queue(), 'f': self.message_orderFilled},
                      'orderCancelled': {'q': queue.Queue(), 'f': self.message_orderCancelled},
                      'contractClosed': {'q': queue.Queue(), 'f': self.message_contractClosed},
                      'traderStatus': {'q': queue.Queue(), 'f': self.message_traderStatus},
                      'leverage': {'q': queue.Queue(), 'f': self.message_leverage},
                      'funding': {'q': queue.Queue(), 'f': self.message_funding},
                      'position': {'q': queue.Queue(), 'f': self.message_position}}
        self.listp = []
        for ch in self.listf.keys():
            p = Worker(self.listf[ch]['q'], self.listf[ch]['f'])
            self.listp.append(p)
            p.daemon = True
            p.start()
        #
        # self.intimer = InTimer(self)
        # self.intimer.daemon = True
        # self.intimer.start()
        #
        # self.analizator = Analizator(self.midvol)
        # self.analizator.daemon = True
        # self.analizator.start()

    def closeEvent(self, *args, **kwargs):
        pass

    def userlogined(self, psw):
        if self.flCoreConnect and not self.flCoreAuth:
            self.wsscore.send_registration(psw)

    @pyqtSlot()
    def buttonLogin_clicked(self):
        if self.flCoreConnect and not self.flCoreAuth:
            rw = LoginWindow()
            rw.userlogined.connect(lambda: self.userlogined(rw.psw))
            rw.setupUi()
            rw.exec_()

    def change_auth_status(self):
        if self.flCoreAuth:
            self.pb_enter.setText('вход выполнен: ' + self.user)
            self.pb_enter.setStyleSheet("color:rgb(64, 192, 64); font: bold 12px;border: none")
        else:
            self.pb_enter.setText('вход не выполнен')
            self.pb_enter.setStyleSheet("color:rgb(255, 96, 96); font: bold 12px;border: none")

    def returnid(self):
        id = str(round(time.time()) * 1000000 + random.randrange(1000000))
        return id

    def fill_data(self, data):
        self.traderBalance = data['traderBalance']
        self.maxBalance = max(self.maxBalance, self.traderBalance)
        self.traderBalance_usd = data['traderBalance'] * self.dgtxUsdRate
        self.leverage = data['leverage']

    def changemarketsituation(self):

        def checkLimits():
            if not self.flAutoLiq:
                return False
            if time.time() <= self.timerazban:
                return False
            if self.tickCounter < NUMTICKS:
                return False
            if self.intimer.pnlTime <= self.l_delayaftermined:
                return False
            if self.traderBalance <= self.l_losslimit_b:
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
                if bonddist == 1  and self.market_volatility <= self.l_dist1_k:
                    bondmod = self.l_dist1
                elif bonddist == 2  and self.market_volatility <= self.l_dist2_k:
                    bondmod = self.l_dist2
                elif bonddist == 3  and self.market_volatility <= self.l_dist3_k:
                    bondmod = self.l_dist3
                elif bonddist == 4  and self.market_volatility <= self.l_dist4_k:
                    bondmod = self.l_dist4
                elif bonddist == 5  and self.market_volatility <= self.l_dist5_k:
                    bondmod = self.l_dist5

                if bondmod != 0:
                    distlist[price] = self.l_numconts * bondmod

        # завершаем ордеры, которые находятся не в списке разрешенных дистанций
        for order in self.listOrders:
            if order.status == ACTIVE:
                if order.px not in distlist.keys():
                    self.dxthread.send_privat('cancelOrder', symbol=self.symbol,
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
                                              symbol=self.symbol,
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
    # ========== обработчик респонсов ============
    def message_response(self, id, status):
        pass
    # ========== обработчики сообщений ===========
    # ==== публичные сообщения
    def message_orderbook_1(self, data):
        self.lock.acquire()
        self.current_maxbid = data.get('bids')[0][0]
        self.current_minask = data.get('asks')[0][0]
        if ((self.current_maxbid != self.last_maxbid) or (self.current_minask != self.last_minask)) and self.flConnect:
            self.changemarketsituation()
        self.last_maxbid = self.current_maxbid
        self.last_minask = self.current_minask
        self.lock.release()

    def message_kline(self, data):
        pass

    def message_trades(self, data):
        pass

    def message_liquidations(self, data):
        pass

    def message_ticker(self, data):
        self.dgtxUsdRate = data['dgtxUsdRate']
        self.contractValue = data['contractValue']

    def message_fundingInfo(self, data):
        pass

    def message_index(self, data):
        self.lock.acquire()
        self.spotPx = data['spotPx']

        if self.tickCounter < NUMTICKS:
            if self.tickCounter > 1:
                self.listTick[self.tickCounter] = [data['ts'], self.spotPx, np.absolute(self.spotPx - self.listTick[self.tickCounter - 1][1])]
        else:
            res = np.empty_like(self.listTick)
            res[:-1] = self.listTick[1:]
            res[-1] = [data['ts'], self.spotPx, np.absolute(self.spotPx - res[-2][1])]
            self.listTick = res

        self.tickCounter += 1
        if self.flConnect:
            self.current_cellprice = math.floor(self.spotPx / self.exDist) * self.exDist
            if self.current_cellprice != self.last_cellprice:
                self.changemarketsituation()
            self.last_cellprice = self.current_cellprice

        self.lock.release()

    # ==== приватные сообщения
    def message_tradingStatus(self, data):
        status = data.get('available')
        if status:
            self.wsscore.authpilot('ok')
        else:
            self.wsscore.authpilot('error')


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
        self.contractmined += (data['pnl'] - self.pnl)
        self.pnl = data['pnl']

        listfilledorders = [x for x in data['contracts'] if x['qty'] != 0]
        if len(listfilledorders) != 0:
            self.timerazban = time.time() + self.l_bandelay
            self.dxthread.send_privat('cancelAllOrders', symbol=self.symbol)
            self.listOrders.clear()
            self.contractcount += len(listfilledorders)

        for cont in listfilledorders:
            self.dxthread.send_privat('closeContract', symbol=self.symbol, contractId=cont['contractId'], ordType='MARKET')

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

    def message_condOrderStatus(self, data):
        pass

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
        self.fundingcount += 1
        self.fundingmined += data['payout']
        self.pnl = data['pnl']

        self.intimer.pnlStartTime = time.time()
        self.dxthread.send_privat('cancelAllOrders', symbol=self.symbol)
        self.dxthread.send_privat('getTraderStatus', symbol=self.symbol)
        self.listOrders.clear()
        self.lock.release()

    def message_position(self, data):
        pass

app = QApplication([])
win = MainWindow()
sys.exit(app.exec_())
