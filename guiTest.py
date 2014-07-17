#!/usr/bin/python
# -*- coding: utf-8 -*-
import os,sys,math
import datetime as dt
import platform

# when we run from Notepad++, the working directory is wrong - fix it here
currentPath = os.path.dirname(os.path.abspath(__file__))
os.chdir(currentPath)

from sample import *
from Tkinter import *

#==============================================================================

RIGHT_SIDE = 800
BOTTOM_SIDE = 800
ZERO_LINE = BOTTOM_SIDE / 2
SCALE_FACTOR = 2
FRAMERATE = 25
FRAME_DELAY = (1000 / FRAMERATE) - 5  # allow for loop overhead & window redraw

STOP_PAUSE = FRAME_DELAY * 2
QUIT_PAUSE = FRAME_DELAY * 3

class SampleDisplayer:
	def __init__(self):
		self.module = CurrentModule()

		self.master = Tk()
		self.master.title("Firefox OS Current Usage")

		self.master.protocol("WM_DELETE_WINDOW", self.handleCloseButton)

		self.scaleCanvas = Canvas(self.master, width=100, height=BOTTOM_SIDE)
		self.scaleCanvas.pack(side=LEFT, anchor=NW)

		self.canvasFrame = Frame(self.master)
		self.canvasFrame.pack(side=LEFT)
		self.canvasScroll = Scrollbar(self.canvasFrame, orient=HORIZONTAL)
		self.canvasScroll.pack(side=BOTTOM, fill=X)
		self.mainCanvas = Canvas(self.canvasFrame, width=RIGHT_SIDE, height=BOTTOM_SIDE, xscrollincrement=1)
		self.mainCanvas.pack(side=TOP)
		self.mainCanvas.config(xscrollcommand=self.canvasScroll.set)
		self.canvasScroll.config(command=self.mainCanvas.xview)
		self.mainCanvas.config(scrollregion=(0, 0, 0, BOTTOM_SIDE))

		BUTTON_COUNT = 5
		LINE_COUNT = (BOTTOM_SIDE / 16) - (BUTTON_COUNT * 2)
		self.frameWidget = Frame(self.master)
		self.frameWidget.pack(side=LEFT, anchor=NW)
		self.voltageString = StringVar()
		self.voltageString.set("Voltage\n0.00 V")
		self.voltageWidget = Label(self.frameWidget, textvariable=self.voltageString)
		self.voltageWidget.pack(side=TOP)
		self.logWidget = Listbox(self.frameWidget, width=10, height=LINE_COUNT)
		self.logWidget.pack(side=TOP)
		self.startButton = Button(self.frameWidget, text="Start", command=self.startRunning)
		self.startButton.pack(side=TOP, fill=X)
		self.stopButton = Button(self.frameWidget, text="Stop", command=self.stopRunning)
		self.stopButton.pack(side=TOP, fill=X)
		self.connectBatteryButton = Button(self.frameWidget, text="Connect", command=self.connectBattery)
		self.connectBatteryButton.pack(side=TOP, fill=X)
		self.disconnectBatteryButton = Button(self.frameWidget, text="Disconnect", command=self.disconnectBattery)
		self.disconnectBatteryButton.pack(side=TOP, fill=X)

		if platform.system() == "Windows":
			self.serialPortName = "COM7"
		else:
			self.serialPortName = "/dev/ttyACM0"
		self.drawScaleCanvas()
		self.drawInitialMainCanvas()
		self.xPosition = 0
		self.module.startRunning(self.serialPortName)
		sample = self.module.getSample()
		current = sample.getCurrent()
		self.yPosition = ZERO_LINE - (current / SCALE_FACTOR)
		self.previousCurrent = 0
		self.running = False
		self.lastLine = None
		self.samples = []
		self.startTimestamp = dt.datetime.utcnow()

	def handleCloseButton(self):
		self.stopRunning()
		self.mainCanvas.after(QUIT_PAUSE, self.quit)

	def quit(self):
		self.module.stopRunning()
		self.master.destroy()
		self.master.quit()

	def connectBattery(self):
		self.module.connectBattery()

	def disconnectBattery(self):
		self.module.disconnectBattery()

	def drawCurrentLine(self):
		startTime = unix_time_millis(dt.datetime.utcnow())

		# auto-scroll the canvas one pixel
		if self.xPosition > RIGHT_SIDE:
			scrollPair = self.canvasScroll.get()
			scrollPos = scrollPair[1]
			# only auto-scroll if the scroll bar is hard-right...
			if scrollPos > 0.98:
				self.mainCanvas.xview_scroll(1, "units")

		# extract a sample from the usb ammeter, and scale it to the screen
		sample = self.module.getSample()
		if sample is None:
			print 'Sync error'
			return

#			done = False
#			count = 0
#			while not done:
#				print 'lost sync, resyncing'
#				done = self.module.resyncPacket()
#				count = count + 1
#				if count > 10:
#					done = True
#			sample = self.module.getSample()
#			if sample is None:
#				print 'Unrecoverable sync error'
#				return

		millivolts = sample.getVoltage()
		voltage = millivolts / 1000.0
		voltageString = "Voltage\n{:3.2f} V".format(voltage)
		self.voltageString.set(voltageString)
		self.samples.append(sample)
		current = sample.getCurrent() / 10.0
		newYPosition = ZERO_LINE - (current / SCALE_FACTOR)

		# log the current sample
		self.logWidget.insert(END, str(current) + " mA")
		self.logWidget.see(END)

		# we want horizontal lines each 100 mA
		if (self.xPosition % RIGHT_SIDE) == 0:
			for index in range(-7, 8):
				lineY = ZERO_LINE - (index * (100 / SCALE_FACTOR));
				self.mainCanvas.create_line(RIGHT_SIDE, lineY, self.xPosition + RIGHT_SIDE, lineY, fill="grey")

		# we want vertical lines every second
		if (self.xPosition % FRAMERATE) == 0:
			if (self.xPosition % (FRAMERATE * 10)) == 0:
				color = "dark grey"
			else:
				color = "grey"
			if self.lastLine != None:
				self.mainCanvas.tag_lower(self.lastLine)
			self.lastLine = self.mainCanvas.create_line(self.xPosition, 0, self.xPosition, BOTTOM_SIDE, fill=color)

		# we want time labels every 10 seconds
		if (self.xPosition % (FRAMERATE * 10)) == 0:
			label = str(self.xPosition / FRAMERATE)
			xPos = self.xPosition
			if xPos == 0:
				xPos = 5
			# we have this nonsense with lastLine so the last seconds text label will be above the next line
			self.mainCanvas.create_text(xPos, BOTTOM_SIDE - 10, text=label, fill="blue")

		# draw the current line(s)
		if current < 0:
			if self.previousCurrent > 0:
				self.mainCanvas.create_line(self.xPosition, self.yPosition, self.xPosition, ZERO_LINE, fill="black")
				self.mainCanvas.create_line(self.xPosition, ZERO_LINE, self.xPosition + 1, newYPosition, fill="red")
			else:
				self.mainCanvas.create_line(self.xPosition, self.yPosition, self.xPosition + 1, newYPosition, fill="red")
		else:
			if self.previousCurrent < 0:
				self.mainCanvas.create_line(self.xPosition, self.yPosition, self.xPosition, ZERO_LINE, fill="red")
				self.mainCanvas.create_line(self.xPosition, ZERO_LINE, self.xPosition + 1, newYPosition, fill="black")
			else:
				self.mainCanvas.create_line(self.xPosition, self.yPosition, self.xPosition + 1, newYPosition, fill="black")

		# update continuous values, and compute the 10 Hz delay
		self.xPosition = self.xPosition + 1
		self.mainCanvas.config(scrollregion=(0, 0, self.xPosition, BOTTOM_SIDE))
		self.yPosition = newYPosition
		self.previousCurrent = current
		drawTime = int(unix_time_millis(dt.datetime.utcnow()) - startTime)
		waitTime = max(FRAME_DELAY - drawTime, 1)
		if self.running:
			self.mainCanvas.after(waitTime, self.drawCurrentLine)

	# draw the scale lines & text down the left side of the window
	def drawScaleCanvas(self):
		self.scaleCanvas.create_line(99, 0, 99, BOTTOM_SIDE)
		for index in range(-7, 8):
			current = index * 100
			yPosition = (ZERO_LINE - 3) - (index * 50)
			label = str(current) + ' mA'
			self.scaleCanvas.create_text(10, yPosition, text=label, anchor=SW)
			self.scaleCanvas.create_line(0, yPosition + 5, 99, yPosition + 5)
		self.scaleCanvas.create_text(90, BOTTOM_SIDE - 2, text="seconds:", anchor=SE, fill="blue")
		self.scaleCanvas.create_line(0, BOTTOM_SIDE - 1, 99, BOTTOM_SIDE - 1)

	# we need to fill in the left side of the canvas which isn't really used
	def drawInitialMainCanvas(self):
		for index in range(-7, 8):
			newY = ZERO_LINE - (index * 50);
			self.mainCanvas.create_line(0, newY, RIGHT_SIDE, newY, fill="grey")

	def startRunning(self):
		self.running = True
		# self.module.startRunning()
		self.drawCurrentLine()

	def stopRunning(self):
		# make sure the last drawCurrentLine event happens before we kill the serial port
		# self.mainCanvas.after(STOP_PAUSE, self.stopModule)
		self.running = False

	def stopModule(self):
		self.module.stopRunning()

#===========================================================

displayer = SampleDisplayer()
displayer.startRunning()
mainloop()
