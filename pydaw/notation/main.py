
from pydaw.notation.qt_compat import QApplication
from pydaw.notation.gui.main_window import MainWindow
import sys

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())
