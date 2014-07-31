
import re
import wx
import os
from socket import *

import matplotlib
matplotlib.use('WXAgg')

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
      elif 'name' in self.payload:
        self.payload['name'] = self.payload['name'] + " " + kv[0]
    # self.dump()
  def dump(self):
    print "type: %s" % self.type
    for key in self.payload:
      print "   %s = %s" % (key, self.payload[key])

class ConnectionStatus:
  def __init__(self, text):
    self.text = text
    self.dump()
  def dump(self):
    print "connection status: '%s'" % self.text

class SocketThread(Thread):
  """ Socket worker thread, so we don't block the UI """

  def __init__(self, host, port):
    """ Initialize socket thread class """
    Thread.__init__(self)
    self.stream = ''
    self.block = {}
    self.got_sob = False
    self.got_eob = False
    self.host = host
    self.port = port
    self.keep_going = True
    Publisher().subscribe(self.wrap_up, "exit")
    self.start()

  def wrap_up(self, msg):
    print ">>> EXIT <<<"
    self.keep_going = False

  def run(self):
    """ Run socket thread """
    client = socket(AF_INET, SOCK_STREAM)
    hostport = "%s:%d" % (self.host, self.port)
    self.post_connection_status(ConnectionStatus("Connecting to %s..." % hostport))
    rv = client.connect_ex((self.host, self.port))
    if rv != 0:
      self.post_connection_status(ConnectionStatus("Connection to %s failed (%s)" % (hostport, os.strerror(rv))))
      return False
    self.post_connection_status(ConnectionStatus("Connected to %s" % hostport))

    while self.keep_going:
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
            self.post_data(self.block)
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
    socket.close(client)
    self.post_connection_status(ConnectionStatus("Connection to %s closed" % hostport))

  def handle_new(self, fields):
    return Message("new", fields)

  def handle_update(self, fields):
    return Message("update", fields)

  def handle_old(self, fields):
    return Message("old", fields)

  def post_data(self, data):
    wx.CallAfter(Publisher().sendMessage, "update", data)

  def post_connection_status(self, data):
    wx.CallAfter(Publisher().sendMessage, "connection", data)

class GraphFrame(wx.Frame):
  """ The main frame of the application
  """
  title = 'Firefox OS per-process USS'
  host = 'localhost'
  port = 26600

  def __init__(self):
    # first we need to call the base class initializer
    wx.Frame.__init__(self, None, -1, self.title)

    # the following dictionaries are keyed by PID
    self.data = {}        # all of the data to be plotted
    self.plot_starts = {} # process-started markers
    self.plot_stops = {}  # process-stopped/killed markers
    self.plot_data = {}   # record of existing plots
    self.x = 0

    self.create_menu()
    self.create_status_bar()

    panel = wx.Panel(self, -1)

    self.dpi = 100
    self.fig = Figure((3.0, 3.0), dpi = self.dpi)
    axes = self.fig.add_subplot(111)

    #
    box = axes.get_position()
    axes.set_position([box.x0, box.y0, box.width * 0.9, box.height])
    # self.axes.legend(loc = 'center left', fontsize = 8, bbox_to_anchor = (1, 0.5))
    # self.axes.set_axis_bgcolor('black')

    axes.grid(True, color = 'gray')
    axes.set_xlabel('Time (seconds)')
    axes.set_ylabel('Memory (MB)')
    axes.set_title('Process USS (MB) vs Time (seconds)', size = 10)
    pylab.setp(axes.get_xticklabels(), fontsize = 8)
    pylab.setp(axes.get_yticklabels(), fontsize = 8)
    pylab.setp(axes.get_xticklabels(), visible = True)
    self.axes = axes

    self.canvas = FigCanvas(panel, -1, self.fig)
    self.canvas.callbacks.connect('pick_event', self.on_pick)

    self.vbox = wx.BoxSizer(wx.VERTICAL)
    self.vbox.Add(self.canvas, 1, flag = wx.LEFT | wx.TOP | wx.GROW)
    panel.SetSizer(self.vbox)
    self.vbox.Fit(self)

    Publisher().subscribe(self.update, "update")
    Publisher().subscribe(self.connection, "connection")

    SocketThread(self.host, self.port)

  def create_menu(self):
    self.menubar = wx.MenuBar()

    file = wx.Menu()
    save = file.Append(-1, "&Save plot...\tCtrl+S", "Save plot to file")
    self.Bind(wx.EVT_MENU, self.on_file_save, save)
    file.AppendSeparator()
    connect = file.Append(-1, "&Connect...\tCtrl+C", "Connection to a procserver")
    connect.Enable(False) # for now
    self.Bind(wx.EVT_MENU, self.on_file_connect, connect)
    disconnect = file.Append(-1, "&Disconnect\tCtrl+D", "Disconnect from a procserver")
    disconnect.Enable(False) # for now
    self.Bind(wx.EVT_MENU, self.on_file_disconnect, disconnect)
    file.AppendSeparator()
    exit = file.Append(-1, "E&xit", "Exit")
    self.Bind(wx.EVT_MENU, self.on_file_exit, exit)

    self.menubar.Append(file, "&File")
    self.SetMenuBar(self.menubar)

  def on_file_connect(self, event):
    print "File > Connect..."

  def on_file_disconnect(self, event):
    print "File > Disconnect"

  def on_file_save(self, event):
      file_choices = "PNG (*.png)|*.png"
      dlg = wx.FileDialog(self,
                          message = "Save plot as...",
                          defaultDir = os.getcwd(),
                          defaultFile = "plot.png",
                          wildcard = file_choices,
                          style = wx.SAVE)

      if dlg.ShowModal() == wx.ID_OK:
        path = dlg.GetPath()
        self.canvas.print_figure(path, dpi = self.dpi)
        self.flash_help_message("Saved to %s" % path)

  def on_file_exit(self, event):
    self.Destroy()

  def create_status_bar(self):
    statusbar = self.CreateStatusBar()
    statusbar.SetFieldsCount(2)
    self.statusbar = statusbar

  def flash_help_message(self, help, flash_length_ms = 1500):
    self.statusbar.SetStatusText(help, 0)
    self.timeroff = wx.Timer(self)
    self.Bind(wx.EVT_TIMER, self.on_help_message_expire, self.timeroff)
    self.timeroff.Start(flash_length_ms, oneShot = True)

  def on_help_message_expire(self, event):
    self.statusbar.SetStatusText('', 0)

  def on_pick(self, event):
    artist = event.artist
    if hasattr(event, 'ind'):
      i = event.ind[(len(event.ind) - 1) / 2] # pick the middle value
      x, y = artist.get_data()
      x = x[i]
      y = y[i]
      print "pick: (%u, %f)" % (x, y)
      if isinstance(artist, Line2D):
        if event.mouseevent.button == 1:
          if artist.get_linewidth() == 1:
            artist.set_linewidth(3)
          else:
            artist.set_linewidth(1)
        if event.mouseevent.button == 2:
          axes = artist.get_axes()
          axes.text(x + 0.5, y + 0.5, "%.3f MB" % y, color = 'black', fontsize = 10)
          axes.plot(x, y, color = 'white', marker = 's')
      self.redraw_plot()

  def redraw_plot(self):
    """ Draw the plot using all current data, settings """
    xmin = 0
    # xmax = len(self.data)
    xmax = self.x * 1.01
    if xmax < 50:
      xmax = 50
    ymin = 0
    self.axes.set_xbound(lower = xmin, upper = xmax)
    # self.plot_data[0].set_xdata(np.arange(len(self.data)))
    ymax = 0
    need_legend = False
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
        width = plot.get_linewidth()
        if width == 1:
          plot.set_label('')
        else:
          need_legend = True
          plot.set_label('%s (%s)' % (plot.name, plot.pid))
        if pid in self.plot_starts:
          self.plot_starts[pid].set_linewidth(width)
        if pid in self.plot_stops:
          self.plot_stops[pid].set_linewidth(width)
      # self.plot(np.array(np.arange(len(self.data)), self.data[pid]["uss"]), label = str(pid))
    if need_legend:
      # Apparently setting loc = 'best' causes matplotlib to eat up 100% CPU :(
      # For now, keep this to the left edge where the oldest data is.
      # self.legend = self.axes.legend(fontsize = 10, loc = 'center left')
      self.legend = self.axes.legend(fontsize = 10, loc = 'center left', bbox_to_anchor = (1, 0.5))
    else:
      try:
        self.legend.set_visible(False)
      except:
        pass
    self.axes.set_ybound(lower = ymin, upper = ymax)
    # print "redraw: (%u, %u)-(%u, %u)" % (xmin, ymin, xmax, ymax)
    self.canvas.draw()

  def handle_new(self, pid, msg):
    """ Handle new process """
    if pid not in self.data:
      uss = float(msg.payload['uss']) / (1024 * 1024) # megabytes
      self.data[pid] = { "uss": [uss], "xstart": self.x }
      plot = self.axes.plot(self.data[pid]['uss'], linewidth = 1, picker = 4)[0]
      plot.pid = pid
      if "name" in msg.payload:
        name = msg.payload['name']
        plot.name = name
        print "[new pid %u uss %.3f name '%s']" % (pid, uss, name)
      else:
        print "[new pid %u uss %.3f]" % (pid, uss)
      self.plot_starts[pid] = self.axes.plot(self.x, uss, plot.get_color() + 'o')[0]
      self.plot_data[pid] = plot

  def handle_update(self, pid, msg):
    """ Update an existing process, possibly including a rename """
    if pid in self.data:
      uss = float(msg.payload['uss']) / (1024 * 1024) # megabytes
      self.data[pid]['uss'][-1] = uss
      # print "[update pid %u uss %.3f --> length %u]" % (pid, uss, len(self.data[pid]['uss']))
      if "name" in msg.payload:
        print "[pid new name '%s']" % msg.payload['name']
        self.plot_data[pid].name = msg.payload['name']

  def handle_old(self, pid, msg):
    """ Handle the death of a process """
    if pid not in self.plot_stops:
      # print "[old pid %u]" % pid
      self.data[pid]['uss'].pop()
      if pid in self.data:
        self.plot_stops[pid] = self.axes.plot(self.x - 1, self.data[pid]['uss'][-1], self.plot_data[pid].get_color() + 'x')[0]
        self.axes.text(self.x - 1, self.data[pid]['uss'][-1], "%s" % self.plot_data[pid].name, color = 'black', fontsize = 10)
      else:
        self.plot_stops[pid] = True

  def handle_messages(self, batch):
    """ Generic process message dispatch """
    self.x = self.x + 1
    for pid in self.data:
      # for now, pre-duplicate all of the last data points
      if pid not in self.plot_stops:
        self.data[pid]['uss'].append(self.data[pid]['uss'][-1])
    for msg in batch.messages:
      handlers = { "new": self.handle_new,
                   "update": self.handle_update,
                   "old": self.handle_old }
      if "pid" in msg.payload and msg.type in handlers:
        handlers[msg.type](int(msg.payload['pid']), msg)
    self.redraw_plot()

  def update(self, msg):
    """ Handle 'update' messages """
    t = msg.data
    if isinstance(t, MessageSet):
      self.handle_messages(t)
    else:
      print "unhandled update type"

  def connection(self, msg):
    """ Handle 'connection' status messages """
    t = msg.data
    if isinstance(t, ConnectionStatus):
      try:
        self.statusbar.SetStatusText(t.text, 1)
      except:
        pass
    else:
      print "unhandled connection status message"

if __name__ == '__main__':
  app = wx.PySimpleApp()
  app.frame = GraphFrame()
  app.frame.Show()
  app.MainLoop()
  Publisher().sendMessage("exit")
