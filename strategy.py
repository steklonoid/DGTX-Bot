import random
import time
import math


# = order type
INSIDE = 0
OUTSIDE = 1
# = order status
OPENING = 0
ACTIVE = 1
CLOSING = 2

MAXORDERDIST = 5

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


class LM_1():

    parameters = {'symbol': 'BTCUSD-PERP',
                  'exDist':5,
                  'numconts': 0,
                  'dist1': 0,
                  'dist2': 0,
                  'dist3': 0,
                  'dist4': 0,
                  'dist5': 0,
                  'dist1_k': 0.0,
                  'dist2_k': 0.0,
                  'dist3_k': 0.0,
                  'dist4_k': 0.0,
                  'dist5_k': 0.0,
                  'delayaftermined': 0,
                  'bandelay': 0.0,
                  'flRace': False}
    marketinfo = {'BTCUSD-PERP': {'avarage_volatility_128': 0}, 'ETHUSD-PERP': {'avarage_volatility_128': 0}}

    current_cellprice = 0  # текущая тик-цена
    last_cellprice = 0  # прошлая тик-цена
    current_maxbid = 0  # текущая нижняя граница стакана цен
    last_maxbid = 0  # прошлая нижняя граница стакана цен
    current_minask = 0  # текущая верхняя граница стакана цен
    last_minask = 0  # прошлая верхняя граница стакана цен
    spotPx = 0  # текущая spot-цена

    listOrders = []  # список активных ордеров
    listContracts = []  # список открытых контрактов

    banStartTime = 0
    pnlStartTime = 0
    leverage = 0  # текущее плечо

    flRace = False

    def __init__(self, dgtxsendq):
        self.dgtxsendq = dgtxsendq

    def startrace(self):
        self.last_cellprice = 0
        self.flRace = True

    def stoprace(self):
        self.flRace = False
        data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
        self.dgtxsendq.put(data)
        data = {'id': 11, 'method': 'closePosition',
                'params': {'symbol': self.parameters.get('symbol'), 'ordType': 'MARKET'}}
        self.dgtxsendq.put(data)

    def setmarketinfo(self, marketinfo):
        self.marketinfo[marketinfo['symbol']]['avarage_volatility_128'] = marketinfo['market_volatility_128']

    def returnid(self):
        id = str(round(time.time()) * 1000000 + random.randrange(1000000))
        return id

    def changemarketsituation(self):

        def checkLimits():
            t = time.time()
            if t - self.banStartTime <= self.parameters['bandelay']:
                return False
            if t - self.pnlStartTime <= self.parameters['delayaftermined']:
                return False
            return self.flRace

        distlist = {}
        if self.current_cellprice != 0:
            for spotdist in range(-MAXORDERDIST, MAXORDERDIST + 1):
                price = self.current_cellprice + spotdist * self.parameters['exDist']
                if price < self.current_maxbid:
                    bonddist = (self.current_maxbid - price) // self.parameters['exDist']
                elif price > self.current_minask:
                    bonddist = (price - self.current_minask) // self.parameters['exDist']
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
                    data = {'id': 6, 'method': 'cancelOrder', 'params': {'symbol': self.parameters.get('symbol'), 'clOrdId':order.clOrdId}}
                    self.dgtxsendq.put(data)
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
                    data = {'id': 5, 'method': 'placeOrder', 'params': {'clOrdId': id,
                                                                        'symbol':self.parameters.get('symbol'),
                                                                        'ordType':'LIMIT',
                                                                        'timeInForce':'GTC',
                                                                        'side':side,
                                                                        'px':dist,
                                                                        'qty':distlist[dist]}}
                    self.dgtxsendq.put(data)
                    self.listOrders.append(Order(
                        clOrdId=id,
                        origClOrdId=id,
                        orderSide=side,
                        orderType='LIMIT',
                        px=dist,
                        qty=distlist[dist],
                        leverage=self.leverage,
                        paidPx=0,
                        type=INSIDE,
                        status=OPENING))

    def message_orderbook_5(self, data):
        self.current_maxbid = data.get('bids')[0][0]
        self.current_minask = data.get('asks')[0][0]
        if (self.current_maxbid != self.last_maxbid) or (self.current_minask != self.last_minask):
            self.changemarketsituation()
        self.last_maxbid = self.current_maxbid
        self.last_minask = self.current_minask

    def message_index(self, data):
        self.spotPx = data['spotPx']
        self.current_cellprice = math.floor(self.spotPx / self.parameters['exDist']) * self.parameters['exDist']
        if self.current_cellprice != self.last_cellprice:
            self.changemarketsituation()
        self.last_cellprice = self.current_cellprice

    def message_orderStatus(self, data):
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

    def message_orderFilled(self, data):
        listfilledorders = [x for x in data['contracts'] if x['qty'] != 0]
        if len(listfilledorders) != 0:
            self.banStartTime = time.time()
            data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
            self.dgtxsendq.put(data)
            self.listOrders.clear()
            # self.info['contractcount'] += len(listfilledorders)

        for cont in listfilledorders:
            data = {'id': 10, 'method': 'closeContract', 'params': {'symbol': self.parameters.get('symbol'),
                                                                    'contractId': cont['contractId'],
                                                                    'ordType': 'MARKET'}}
            self.dgtxsendq.put(data)


    def message_orderCancelled(self, data):
        # если статус отмена
        if data['orderStatus'] == 'CANCELLED':
            listtoremove = [x['origClOrdId'] for x in data['orders']]
            lo = list(self.listOrders)
            for order in lo:
                if order.origClOrdId in listtoremove:
                    self.listOrders.remove(order)

    def message_contractClosed(self, data):
        pass

    def message_leverage(self, data):
        self.leverage = data['leverage']

    def message_funding(self):
        self.pnlStartTime = time.time()
        self.listOrders.clear()
        data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
        self.dgtxsendq.put(data)
        dgtxdata = {'id': 5, 'method': 'getTraderStatus', 'params': {'symbol': self.parameters['symbol']}}
        self.dgtxsendq.put(dgtxdata)


class LM_2():
    parameters = {'symbol': 'BTCUSD-PERP',
                  'exDist': 5,
                  'numconts': 0,
                  'maxorderdist':5,
                  'dist1_k': 0.0,
                  'dist2_k': 0.0,
                  'dist3_k': 0.0,
                  'dist4_k': 0.0,
                  'dist5_k': 0.0,
                  'delayaftermined': 0,
                  'bandelay': 0.0,
                  'flRace': False}
    marketinfo = {'BTCUSD-PERP': {'avarage_volatility_128': 0}, 'ETHUSD-PERP': {'avarage_volatility_128': 0}}

    current_cellprice = 0  # текущая тик-цена
    last_cellprice = 0  # прошлая тик-цена
    current_maxbid = 0  # текущая нижняя граница стакана цен
    last_maxbid = 0  # прошлая нижняя граница стакана цен
    current_minask = 0  # текущая верхняя граница стакана цен
    last_minask = 0  # прошлая верхняя граница стакана цен
    spotPx = 0  # текущая spot-цена

    listOrders = []  # список активных ордеров
    listContracts = []  # список открытых контрактов

    banStartTime = 0
    pnlStartTime = 0
    leverage = 0  # текущее плечо
    contractcount = 0

    flRace = False

    def __init__(self, dgtxsendq):
        self.dgtxsendq = dgtxsendq

    def startrace(self):
        self.pnlStartTime = time.time()
        self.last_cellprice = 0
        self.flRace = True
        self.contractcount = 0

    def stoprace(self):
        self.flRace = False
        data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
        self.dgtxsendq.put(data)
        data = {'id': 11, 'method': 'closePosition',
                'params': {'symbol': self.parameters.get('symbol'), 'ordType': 'MARKET'}}
        self.dgtxsendq.put(data)

    def setmarketinfo(self, marketinfo):
        self.marketinfo[marketinfo['symbol']]['avarage_volatility_128'] = marketinfo['market_volatility_128']

    def returnid(self):
        id = str(round(time.time()) * 1000000 + random.randrange(1000000))
        return id

    def changemarketsituation(self):

        def checkLimits():
            t = time.time()
            if t - self.banStartTime <= self.parameters['bandelay']:
                return False
            if t - self.pnlStartTime <= self.parameters['delayaftermined']:
                return False
            return self.flRace

        distlist = {}
        if self.current_cellprice != 0:
            for spotdist in range(-self.parameters['maxorderdist'], self.parameters['maxorderdist'] + 1):
                price = self.current_cellprice + spotdist * self.parameters['exDist']
                if price <= min(self.current_maxbid, self.current_cellprice):
                    bonddist = (self.current_maxbid - price) // self.parameters['exDist']
                elif price >= max(self.current_minask, self.current_cellprice):
                    bonddist = (price - self.current_minask) // self.parameters['exDist']
                else:
                    bonddist = 0
                bonddist = min(bonddist, 5)

                bondmod = 0
                av128 = self.marketinfo[self.parameters['symbol']]['avarage_volatility_128']
                numconts = self.parameters['numconts']
                if bonddist == 1 and av128 <= self.parameters['dist1_k']:
                    bondmod = numconts
                elif bonddist == 2 and av128 <= self.parameters['dist2_k']:
                    bondmod = numconts
                elif bonddist == 3 and av128 <= self.parameters['dist3_k']:
                    bondmod = numconts
                elif bonddist == 4 and av128 <= self.parameters['dist4_k']:
                    bondmod = numconts
                elif bonddist == 5 and av128 <= self.parameters['dist5_k']:
                    bondmod = numconts

                if bondmod != 0:
                    distlist[price] = bondmod
        # завершаем ордеры, которые находятся не в списке разрешенных дистанций
        for order in self.listOrders:
            if order.status == ACTIVE:
                if order.px not in distlist.keys():
                    data = {'id': 6, 'method': 'cancelOrder',
                            'params': {'symbol': self.parameters.get('symbol'), 'clOrdId': order.clOrdId}}
                    self.dgtxsendq.put(data)
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
                    data = {'id': 5, 'method': 'placeOrder', 'params': {'clOrdId': id,
                                                                        'symbol': self.parameters.get('symbol'),
                                                                        'ordType': 'LIMIT',
                                                                        'timeInForce': 'GTC',
                                                                        'side': side,
                                                                        'px': dist,
                                                                        'qty': distlist[dist]}}
                    self.dgtxsendq.put(data)
                    self.listOrders.append(Order(
                        clOrdId=id,
                        origClOrdId=id,
                        orderSide=side,
                        orderType='LIMIT',
                        px=dist,
                        qty=distlist[dist],
                        leverage=self.leverage,
                        paidPx=0,
                        type=INSIDE,
                        status=OPENING))

    def message_orderbook_5(self, data):
        self.current_maxbid = data.get('bids')[0][0]
        self.current_minask = data.get('asks')[0][0]
        if (self.current_maxbid != self.last_maxbid) or (self.current_minask != self.last_minask):
            self.changemarketsituation()
        self.last_maxbid = self.current_maxbid
        self.last_minask = self.current_minask

    def message_index(self, data):
        self.spotPx = data['spotPx']
        self.current_cellprice = math.floor(self.spotPx / self.parameters['exDist']) * self.parameters['exDist']
        if self.current_cellprice != self.last_cellprice:
            self.changemarketsituation()
        self.last_cellprice = self.current_cellprice

    def message_orderStatus(self, data):
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
                                             paidPx=data['paidPx'],
                                             type=OUTSIDE,
                                             status=ACTIVE))

    def message_orderFilled(self, data):
        listfilledorders = [x for x in data['contracts'] if x['qty'] != 0]
        if len(listfilledorders) != 0:
            self.banStartTime = time.time()
            data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
            self.dgtxsendq.put(data)
            self.listOrders.clear()
            data = {'id': 11, 'method': 'closePosition', 'params': {'symbol': self.parameters.get('symbol'), 'ordType': 'MARKET'}}
            self.dgtxsendq.put(data)
            self.contractcount += len(listfilledorders)


    def message_orderCancelled(self, data):
        # если статус отмена
        if data['orderStatus'] == 'CANCELLED':
            listtoremove = [x['origClOrdId'] for x in data['orders']]
            lo = list(self.listOrders)
            for order in lo:
                if order.origClOrdId in listtoremove:
                    self.listOrders.remove(order)

    def message_contractClosed(self, data):
        pass

    def message_leverage(self, data):
        self.leverage = data['leverage']

    def message_funding(self):
        self.pnlStartTime = time.time()
        self.listOrders.clear()
        data = {'id': 7, 'method': 'cancelAllOrders', 'params': {'symbol': self.parameters.get('symbol')}}
        self.dgtxsendq.put(data)
        dgtxdata = {'id': 5, 'method': 'getTraderStatus', 'params': {'symbol': self.parameters['symbol']}}
        self.dgtxsendq.put(dgtxdata)
