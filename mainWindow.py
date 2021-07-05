# модуль главного окна
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QGridLayout, QStatusBar, QLabel
from PyQt5.QtGui import QIcon

class UiMainWindow(object):
    def __init__(self):
        self.buttonlist = []
        self.numcontbuttonlist = []

    def setupui(self, mainwindow):
        mainwindow.setObjectName("MainWindow")
        mainwindow.setWindowTitle('DLM Bot v' + mainwindow.version)
        mainwindow.resize(320, 120)
        self.centralwidget = QWidget(mainwindow)
        self.centralwidget.setObjectName("centralwidget")
        mainwindow.setCentralWidget(self.centralwidget)

        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setContentsMargins(1, 1, 1, 1)
        self.gridLayout.setObjectName("gridLayout")

        self.l_DGTX = QLabel()
        self.l_DGTX.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(self.l_DGTX, 0, 0, 1, 1)

        self.l_core = QLabel()
        self.l_core.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(self.l_core, 1, 0, 1, 1)

