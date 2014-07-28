
import re
import wx
from socket import *
from threading import Thread
from wx.lib.pubsub import Publisher
from matplotlib.figure import Figure
import pylab
from matplotlib.backends.backend_wxagg import \
    FigureCanvasWxAgg as FigCanvas, \
    NavigationToolbar2WxAgg as NavigationToolbar
import numpy as np
from matplotlib.lines import Line2D

class MessageSet:
  def __init__(self):
    self.messages = []
  def add(self, payload):
    self.messages.append(payload)
  def dump(self):
    for message in self.messages:
      message.dump()

class Message:
  def __init__(self, type, fields):
    self.type = type
    self.payload = {}
    for field in fields:
      kv = field.split("=")
      # we don't handle the 'name' key properly yet
      if len(kv) == 2:
        self.payload[kv[0]] = kv[1]
      else:
        self.payload['name'] = self.payload['name'] + " " + kv[0]
    # self.dump()
  def dump(self):
    print "type: %s" % self.type
    for key in self.payload:
      print "   %s = %s" % (key, self.payload[key])

class SocketThread(Thread):
  """ Socket worker thread, so we don't block the UI """

  def __init__(self):
    """ Initialize socket thread class """
    Thread.__init__(self)
    self.stream = ''
    self.block = {}
    self.got_sob = False
    self.got_eob = False
    self.start()

  def run(self):
    """ Run socket thread """
    client = socket(AF_INET, SOCK_STREAM)
    print "Connecting..."
    client.connect_ex(('localhost', 26600))
    print "Connected!"
    while True:
      chunk = client.recv(1024)
      self.stream = self.stream + chunk
      lines = self.stream.splitlines(1)
      self.stream = ''
      for line in lines:
        if line.endswith('\n'):
          line = line.rstrip()
          if line == '>>>':
            """ Beginning of block marker """
            self.got_sob = True
            self.block = MessageSet()
          elif line == '<<<':
            """ End of block marker """
            wx.CallAfter(self.postData, self.block)
            self.block = MessageSet()
            self.got_eob = True
          elif self.got_sob:
            """ Handle info lines """
            # print line
            fields = line.split("|")
            handlers = { "new": self.handle_new,
                         "update": self.handle_update,
                         "old": self.handle_old }
            if fields[0] in handlers:
              self.block.add(handlers[fields[0]](fields[1:]))
        else:
          """ This should always be the last line """
          self.stream = line
    close(client)
    wx.CallAfter(Publisher().sendMessage, "update", "Socket thread finished")

  def handle_new(self, fields):
    return Message("new", fields)

  def handle_update(self, fields):
    return Message("update", fields)

  def handle_old(self, fields):
    return Message("old", fields)

  def postData(self, data):
    Publisher().sendMessage("update", data)
    
class GraphFrame(wx.Frame):
  """ The main frame of the application
  """
  title = 'b2g per-process USS'
    
  def onPick(self, event):
    artist = event.artist
    i = event.ind[(len(event.ind) - 1) / 2] # pick the middle value
    x, y = artist.get_data()
    x = x[i]
    y = y[i]
    print "pick: (%u, %f)" % (x, y)
    if isinstance(artist, Line2D):
      if artist.get_linewidth() == 1:
        artist.set_linewidth(3)
        artist.set_label('%s (%s)' % (artist.name, artist.pid))
        axes = artist.get_axes()
        axes.text(x * 1.05, y * 1.05, "%.3f MB" % y, color = 'white')
        axes.plot(x, y, color = 'white', marker = 's')
      else:
        artist.set_linewidth(1)
    self.redrawPlot()

  def __init__(self):
    self.data = {}
    self.data_stops = {}
    self.x = 0

    wx.Frame.__init__(self, None, -1, self.title)
    panel = wx.Panel(self, -1)

    self.dpi = 100
    self.fig = Figure((3.0, 3.0), dpi = self.dpi)
    self.axes = self.fig.add_subplot(111)
    self.axes.set_axis_bgcolor('black')
    self.axes.set_xlabel('time (seconds)')
    self.axes.set_ylabel('memory (MB)')
    self.axes.set_title('b2g parent process USS (MiB) vs time (seconds)', size = 10)
    pylab.setp(self.axes.get_xticklabels(), fontsize = 8)
    pylab.setp(self.axes.get_yticklabels(), fontsize = 8)
    # self.plot_data = self.axes.plot(self.data, linewidth = 1, color = (1, 1, 0))[0]
    self.plot_data = {}

    self.canvas = FigCanvas(panel, -1, self.fig)
    self.canvas.callbacks.connect('pick_event', self.onPick)

    self.vbox = wx.BoxSizer(wx.VERTICAL)
    self.vbox.Add(self.canvas, 1, flag = wx.LEFT | wx.TOP | wx.GROW)
    panel.SetSizer(self.vbox)
    self.vbox.Fit(self)

    Publisher().subscribe(self.update, "update")

    SocketThread()

  def redrawPlot(self):
    xmin = 0
    # xmax = len(self.data)
    xmax = self.x
    if xmax < 50:
      xmax = 50
    ymin = 0
    self.axes.set_xbound(lower = xmin, upper = xmax)
    self.axes.grid(True, color = 'gray')
    pylab.setp(self.axes.get_xticklabels(), visible = True)
    # self.plot_data[0].set_xdata(np.arange(len(self.data)))
    ymax = 0
    for pid in self.data:
      # self.plot_data[0].set_ydata(np.array(self.data[pid]["uss"]))
      # print "pid=%u --> xdata.len=%u, ydata.len=%u" % (pid, len(np.arange(self.data[pid]['xmin'], self.data[pid]['xmax'] + 1)), len(np.array(self.data[pid]['uss'])))
      if pid in self.plot_data:
        plot = self.plot_data[pid]
        plot.set_xdata(np.arange(self.data[pid]['xstart'], self.data[pid]['xstart'] + len(self.data[pid]['uss'])))
        plot.set_ydata(np.array(self.data[pid]['uss']))
        yussmax = round(max(self.data[pid]['uss']), 0) + 1
        if yussmax > ymax:
          ymax = yussmax
      # self.plot(np.array(np.arange(len(self.data)), self.data[pid]["uss"]), label = str(pid))
    self.axes.set_ybound(lower = ymin, upper = ymax)
    print "redraw: (%u, %u)-(%u, %u)" % (xmin, ymin, xmax, ymax)
    self.axes.legend(loc = 'upper right', fontsize = 8)
    self.canvas.draw()

  def handle_new(self, pid, msg):
    if pid not in self.data:
      uss = float(msg.payload['uss']) / (1024 * 1024) # megabytes
      print "[new pid %u uss %.3f]" % (pid, uss)
      self.data[pid] = { "uss": [uss], "xstart": self.x }
      plot = self.axes.plot(self.data[pid]['uss'], linewidth = 1, picker = 5)[0]
      plot.pid = pid
      if "name" in msg.payload:
        plot.name = msg.payload['name']
      self.plot_data[pid] = plot

  def handle_update(self, pid, msg):
    if pid in self.data:
      uss = float(msg.payload['uss']) / (1024 * 1024) # megabytes
      self.data[pid]['uss'][-1] = uss
      print "[update pid %u uss %.3f --> length %u]" % (pid, uss, len(self.data[pid]['uss']))

  def handle_old(self, pid, msg):
    if pid not in self.data_stops:
      print "[old pid %u]" % pid
      self.data_stops[pid] = True
      self.data[pid]['uss'].pop()
      if pid in self.data:
        self.axes.plot(self.x - 1, self.data[pid]['uss'][-1], self.plot_data[pid].get_color() + 'x')

  def handle_messages(self, batch):
    self.x = self.x + 1
    for pid in self.data:
      # for now, pre-duplicate all of the last data points
      self.data[pid]['uss'].append(self.data[pid]['uss'][-1])
    for msg in batch.messages:
      handlers = { "new": self.handle_new,
                   "update": self.handle_update,
                   "old": self.handle_old }
      if "pid" in msg.payload and msg.type in handlers:
        handlers[msg.type](int(msg.payload['pid']), msg)
    self.redrawPlot()

  def update(self, msg):
    t = msg.data
    if isinstance(t, MessageSet):
      self.handle_messages(t)
    else:
      print "unhandled update type"

if __name__ == '__main__':
  app = wx.PySimpleApp()
  app.frame = GraphFrame()
  app.frame.Show()
  app.MainLoop()
