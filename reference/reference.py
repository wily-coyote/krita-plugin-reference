#!/usr/bin/env python3
import sys
import math
import os.path
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QImage, QPainter, QColor, QCursor, QPen
from PyQt5.QtWidgets import QWidget, QApplication
from krita import *

def trueLength(size):
	return math.sqrt(pow(size.x(), 2) + pow(size.y(), 2));

class ReferenceExtension(Extension):

	def __init__(self, parent):
		#This is initialising the parent, always  important when subclassing.
		super().__init__(parent)

	def setup(self):
		pass

	def createActions(self, window):
		pass

# And add the extension to Krita's list of extensions:
Krita.instance().addExtension(ReferenceExtension(Krita.instance()))

class ReferenceViewer(QWidget):
	colorPicked = pyqtSignal(QColor)
	imageChanged = pyqtSignal(bool)
	sliderReset = pyqtSignal(float)
	triggerDistance = 10

	def __init__(self, parent=None, flags=None):
		super().__init__(parent)
		self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
		self.setCursor(QCursor(Qt.CrossCursor))
		self.setAcceptDrops(True)

		self.image = QImage()
		self.zoom = 1.0
		self.initialZoom = 1.0
		self.oldZoom = None

		self.origin = QPoint(0, 0)
		self.oldOrigin = None

		self.pressedPoint = None
		self.moving = False
		self.currentColor = None
		self.picking = None

	def getCurrentColor(self, event):
		if not self.image.isNull():
			pos = (event.pos() - self.origin) / self.zoom
			return self.image.pixelColor(pos)

		return None

	def setImage(self, image=QImage()):
		self.image = image
		self.imageChanged.emit(not self.image.isNull())
		self.resetView()

	def resetSlider(self):
		self.sliderReset.emit(float(self.zoom/self.initialZoom))

	def resetView(self):
		if self.image.isNull():
			self.update()
			return
		self.initialZoom = min(self.size().width() / self.image.size().width(),
						self.size().height() / self.image.size().height())
		self.minimumZoom = self.initialZoom*0.25 # Scaling with really small sizes slows down Krita
		self.zoom = self.initialZoom
		overflow = self.size() - (self.image.size() * self.zoom)
		self.origin = QPoint(int(overflow.width() / 2), int(overflow.height() / 2))
		self.resetSlider()
		self.update()

	def paintEvent(self, event):
		if self.image.isNull():
			return

		painter = QPainter(self)
		painter.setRenderHint(QPainter.Antialiasing)

		rect = QRect(-self.origin / self.zoom, self.size() / self.zoom)
		cropped = self.image.copy(rect)
		image = cropped.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
		painter.drawImage(0, 0, image)

		if self.picking is not None:
			painter.setPen(QPen(QColor(255, 255, 255, 128), 3.0))
			painter.drawEllipse(self.picking, self.triggerDistance, self.triggerDistance)
			painter.fillRect(0, 0, self.size().width(), 20, self.currentColor)

	def mousePressEvent(self, event):
		self.pressedPoint = event.pos()
		self.oldOrigin = self.origin
		self.oldZoom = self.zoom
		if self.picking is not None:
			self.colorPicked.emit(self.currentColor)
		self.update()

	def mouseReleaseEvent(self, event):
		self.pressedPoint = None
		self.moving = False
		self.update()

	def clampZoom(self, value):
		return max(self.minimumZoom, value)

	def mouseMoveEvent(self, event):
		if self.pressedPoint is not None:
			self.moving = True
			if event.modifiers() & Qt.AltModifier:
				self.currentColor = self.getCurrentColor(event)
				self.picking = event.pos()
			else:
				self.picking = None
			if self.moving and self.picking is None:
				if QApplication.keyboardModifiers() & Qt.ControlModifier:
					zoomDelta = self.pressedPoint.y() - event.pos().y()
					centerPos = (self.pressedPoint - self.oldOrigin) / self.oldZoom
					self.zoom = self.clampZoom(self.oldZoom + (zoomDelta / 100) * self.oldZoom)
					self.origin = self.pressedPoint - (centerPos * self.zoom)
					self.resetSlider()
				else:
					self.origin = self.oldOrigin - self.pressedPoint + event.pos()
			self.update()

	def wheelEvent(self, event):
		centerPos = (event.pos() - self.origin) / self.zoom
		self.zoom = self.clampZoom(self.zoom + (event.angleDelta().y() / 500) * self.zoom)
		self.resetSlider()
		self.origin = event.pos() - (centerPos * self.zoom)
		self.update()

	def resizeEvent(self, event):
		self.resetView()

	def sizeHint(self):
		return QSize(256, 256)

	def dragEnterEvent(self, event):
		if event.mimeData().hasUrls():
			event.acceptProposedAction()
		pass

	def dropEvent(self, event):
		# https://wiki.qt.io/Drag_and_Drop_of_files
		urls = event.mimeData().urls()
		path = urls[0]
		if path.isLocalFile():
			path = path.toLocalFile() # list of QUrls
			event.acceptProposedAction()
			self.setImage(QImage(path))
		pass

	def changeZoom(self, newZoom, absolute=False, emit=False):
		thisCenter = (QPoint(self.size().width(),self.size().height())/2.0)
		centerPos = (thisCenter - self.origin) / self.zoom
		if absolute is True:
			self.zoom = max(.25, newZoom)
		else:
			self.zoom = self.clampZoom(self.initialZoom*newZoom)
		self.origin = thisCenter - (centerPos * self.zoom)
		if emit is True:
			self.resetSlider()
		self.update()


class ReferenceDocker(DockWidget):
	zoomPresets = [
		"Reset view",
		25,
		33.33,
		50,
		66.66,
		75,
		100,
		200,
		300,
		400,
		600,
		800,
		1000,
		1200,
		1600,
		2000,
		2400,
		2800,
		3200,
	]

	def __init__(self):
		super().__init__()
		self.currentDir = Application.readSetting('referenceDocker', 'lastdir', '.')

		self.setWindowTitle("Reference Docker")

		widget = QWidget()
		layout = QVBoxLayout(widget)

		# image view
		self.viewer = ReferenceViewer()
		self.viewer.colorPicked.connect(self.changeColor)
		self.viewer.imageChanged.connect(self.enableControls)
		buttonLayout = QHBoxLayout(widget)
		zoomLayout = QHBoxLayout(widget)
		layout.addWidget(self.viewer)
		layout.setStretch(0, 1)

		# button row
		self.open = QAction(self)
		self.open.setToolTip("Open")
		self.open.setIcon(Krita.instance().icon("document-open"))
		self.open.triggered.connect(self.openImage)
		openButton = QToolButton()
		openButton.setDefaultAction(self.open)
		buttonLayout.addWidget(openButton)

		self.center = QAction(self)
		self.center.setToolTip("Reset view")
		self.center.setIcon(Krita.instance().icon("view-refresh"))
		self.center.triggered.connect(self.centerView)
		centerButton = QToolButton()
		centerButton.setDefaultAction(self.center)
		buttonLayout.addWidget(centerButton)

		buttonLayout.addStretch(1)

		self.close = QAction(self)
		self.close.setToolTip("Close image")
		self.close.setIcon(Krita.instance().icon("dialog-cancel"))
		self.close.triggered.connect(self.closeImage)
		closeButton = QToolButton()
		closeButton.setDefaultAction(self.close)
		buttonLayout.addWidget(closeButton)

		layout.addLayout(buttonLayout)

		# zoom row
		self.zoomSlider = QSlider(Qt.Horizontal, self)
		self.zoomSlider.setMinimum(0)
		self.zoomSlider.setMaximum(10000)
		self.zoomSlider.setValue(int(self.valueZoomToSlider(1.0)))
		self.zoomSlider.valueChanged.connect(lambda value: self.viewer.changeZoom(self.valueSliderToZoom(value)))
		self.viewer.sliderReset.connect(lambda value: self.zoomSlider.setValue(int(self.valueZoomToSlider(value))))

		self.zoomCombo = QComboBox(self)
		self.zoomCombo.addItems([ ("%.2f%%" % x if isinstance(x, (int, float)) else x) for x in self.zoomPresets])
		self.zoomCombo.setCurrentIndex(0)
		self.zoomCombo.currentIndexChanged.connect(self.setZoomPreset)

		zoomLayout.addWidget(self.zoomCombo)
		zoomLayout.addWidget(self.zoomSlider)
		zoomLayout.setStretch(1, 1)
		layout.addLayout(zoomLayout)

		self.setWidget(widget)
		self.enableControls(False)

		fileName = Application.readSetting('referenceDocker', 'lastref', None)
		if fileName is not None:
			self.viewer.setImage(QImage(fileName))
	@pyqtSlot(bool)
	def enableControls(self, isNotNull):
		self.center.setEnabled(isNotNull);
		self.close.setEnabled(isNotNull);
		self.zoomCombo.setEnabled(isNotNull);
		self.zoomSlider.setEnabled(isNotNull);

	@pyqtSlot(int)
	def setZoomPreset(self, index):
		newZoom = self.getZoomPreset(index)
		if newZoom is None:
			self.viewer.changeZoom(1.0, absolute=False, emit=True)
		else:
			self.viewer.changeZoom(newZoom, absolute=True, emit=True)

	def getZoomPreset(self, i):
		try:
			x = self.zoomPresets[i]
			if isinstance(x, (int, float)):
				return x/100.0
			return None
		except IndexError:
			return None

	def valueSliderToZoom(self, x):
		# min .25, max 32
		return math.pow(32/.25, x/10000.0)*.25

	def valueZoomToSlider(self, x):
		# thanks wfa
		return (10000.0*math.log(x/.25)) / math.log(32/.25)

	def centerView(self):
		self.viewer.resetView()
	
	def closeImage(self):
		self.viewer.setImage(QImage())
		Application.writeSetting('referenceDocker', 'lastref', None)

	def openImage(self):
		fileName, _filter = QtWidgets.QFileDialog.getOpenFileName(None, "Open an image", self.currentDir)
		if not fileName:
			return

		Application.writeSetting('referenceDocker', 'lastref', fileName)

		self.currentDir = os.path.dirname(fileName)
		Application.writeSetting('referenceDocker', 'lastdir', self.currentDir)

		self.viewer.setImage(QImage(fileName))

	@pyqtSlot(QColor)
	def changeColor(self, color):
		if (self.canvas()) is not None and self.canvas().view() is not None:
			_color = ManagedColor("RGBA", "U8", "")
			_color.setComponents([color.blueF(), color.greenF(), color.redF(), 1.0])
			self.canvas().view().setForeGroundColor(_color)

	def canvasChanged(self, canvas):
		pass

Krita.instance().addDockWidgetFactory(DockWidgetFactory("referenceDocker", DockWidgetFactoryBase.DockRight, ReferenceDocker))
