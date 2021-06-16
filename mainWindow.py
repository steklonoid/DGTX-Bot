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
        mainwindow.setWindowIcon(QIcon("./images/main_icon.png"))
        self.centralwidget = QWidget(mainwindow)
        self.centralwidget.setObjectName("centralwidget")
        mainwindow.setCentralWidget(self.centralwidget)

        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setContentsMargins(1, 1, 1, 1)
        self.gridLayout.setObjectName("gridLayout")

        l1 = QLabel('Bot')
        l1.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.gridLayout.addWidget(l1)

        self.statusbar = QStatusBar(mainwindow)
        self.statusbar.setObjectName("statusbar")
        mainwindow.setStatusBar(self.statusbar)
