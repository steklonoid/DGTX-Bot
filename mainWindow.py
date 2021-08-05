from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton, QLabel, QLineEdit


class UiMainWindow(object):

    def __init__(self):
        self.buttonlist = []
        self.numcontbuttonlist = []

    def setupui(self, mainwindow):
        mainwindow.setObjectName("MainWindow")
        mainwindow.setWindowTitle('DLM Bot v ' + mainwindow.version)
        mainwindow.resize(320, 120)

        self.centralwidget = QWidget(mainwindow)
        self.centralwidget.setObjectName("centralwidget")
        mainwindow.setCentralWidget(self.centralwidget)

        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setContentsMargins(1, 1, 1, 1)
        self.gridLayout.setObjectName("gridLayout")

        self.pb_enter = QPushButton()
        self.pb_enter.setText('вход не выполнен')
        self.pb_enter.setStyleSheet("color:rgb(255, 96, 96); font: bold 12px;border: none")
        self.pb_enter.setCursor(Qt.PointingHandCursor)
        self.gridLayout.addWidget(self.pb_enter, 0, 0, 1, 1)
        self.pb_enter.clicked.connect(self.buttonLogin_clicked)

        self.l_DGTX = QLabel('Нет соединения с DGTX')
        self.l_DGTX.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(self.l_DGTX, 1, 0, 1, 1)

        self.l_core = QLabel('Нет соединения с ядром')
        self.l_core.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(self.l_core, 2, 0, 1, 1)

        self.l_info = QLabel()
        self.l_info.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(self.l_info, 3, 0, 1, 2)

        self.l_serveraddress = QLabel(mainwindow.serveraddress)
        self.gridLayout.addWidget(self.l_serveraddress, 4, 0, 1, 1)
        self.l_serverport = QLabel(mainwindow.serverport)
        self.gridLayout.addWidget(self.l_serverport, 4, 1, 1, 1)
        self.pb_start = QPushButton()
        self.pb_start.setText('START')
        self.gridLayout.addWidget(self.pb_start, 5, 0, 1, 1)
        self.pb_start.clicked.connect(self.pb_start_clicked)
