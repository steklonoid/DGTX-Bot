from PyQt5.QtWidgets import QDialog, QSizePolicy, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox, QMessageBox
from PyQt5.QtCore import pyqtSlot, pyqtSignal, Qt
from PyQt5.QtGui import QFont


class LoginWindow(QDialog):
    userlogined = pyqtSignal()

    def __init__(self):
        QDialog.__init__(self)

    def setupUi(self):
        self.resize(320, 200)
        sizePolicy = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.sizePolicy().hasHeightForWidth())
        self.setWindowTitle("Ввод пароля")
        self.setSizePolicy(sizePolicy)

        vbox = QVBoxLayout(self)
        labelPassword = QLabel('Пароль')
        labelPassword.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        labelPassword.setFont(QFont("Helvetica", 16))
        vbox.addWidget(labelPassword)
        self.lineP = QLineEdit()
        self.lineP.setEchoMode(QLineEdit.Password)
        vbox.addWidget(self.lineP)

        buttonBox = QDialogButtonBox()
        buttonBox.setStandardButtons(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.buttonOkClicked)
        buttonBox.rejected.connect(self.buttonCancelClicked)
        vbox.addWidget(buttonBox)

    @pyqtSlot()
    def buttonOkClicked(self):
        flag = True
        if not self.lineP.text():
            flag = False
        if not flag:
            mess = QMessageBox()
            mess.setText('Пустой пароль')
            mess.setWindowTitle("Ошибка")
            mess.exec()
        else:
            self.psw = self.lineP.text()
            self.userlogined.emit()
            self.done(0)

    @pyqtSlot()
    def buttonCancelClicked(self):
        self.done(0)
