#!/usr/bin/python
 
#@author Silver Moon
#@email m00n.silv3r@gmail.com
 
import wx
import socket
import thread
 
#A class which will open a window , it is a wx.Frame type of window
class WhoisForm(wx.Frame):
    def __init__(self, parent):
         
        #Call the parent constructor
        wx.Frame.__init__(self, parent, -1 , size=(500,350), title="Whois Utility")
         
        #Create some components like the GUI
        self.InitComponents()
    #End
     
    def InitComponents(self):
        #Now onto other GUI creation
        panel = wx.Panel(self, -1)
         
        #This sizer shall contain the individual controls
        fgs = wx.FlexGridSizer(3, 2, 9, 25)    
         
        #Create some static text controls
        server = wx.StaticText(panel, -1, 'Enter Hostname')
        result = wx.StaticText(panel, -1, 'Whois Result')
         
        #Create some text boxes and buttons , remember they all belong to the panel
        self.txtServer = wx.TextCtrl(panel, -1)
                 
        btnWhois = wx.Button(panel ,  20 , "Whois")
        self.Bind(wx.EVT_BUTTON, self.OnButtonWhois, btnWhois)
        btnWhois.SetToolTipString("Click to get whois information for the domain name.")
        self.button_whois = btnWhois
         
        self.txtResult = wx.TextCtrl(panel, -1, style=wx.TE_MULTILINE)
         
        #Add the input field and submit button to a Box Sizer since the must stay together
        space = wx.BoxSizer()
        #Text field should be expandable
        space.Add(self.txtServer , 1 , wx.RIGHT , 10)
        #Button should not expand and stay to right
        space.Add(btnWhois , 0 , wx.ALIGN_RIGHT)
         
        #Create a list to add these controls to the sizer :)
        mybag = [
                    (server) , (space ,1 , wx.EXPAND) , \
                    (result) , (self.txtResult , 1 , wx.EXPAND), \
                ]
         
        fgs.AddMany(mybag)
         
        #Define the parts that grow and shrink on resizing
        fgs.AddGrowableRow(1, 1)
        fgs.AddGrowableCol(1, 1)
        box = wx.BoxSizer()
        box.Add(fgs, 1 , wx.EXPAND | wx.ALL , 20)
        panel.SetSizer(box)
         
        sizer = wx.BoxSizer()
        sizer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(sizer)
         
        wx.CallAfter(self.Layout)
    #End
     
    def get_focus(self) :
        self.button_whois.SetFocus()
     
    #Event handler for the button
    def OnButtonWhois(self , evt):
        #Start a worker thread so that GUI is not kept busy , like the button being pressed
        thread.start_new_thread(self.worker_thread , ())
    #End
     
    def worker_thread(self) :
        #Get the domain name from the input control
        domain = self.txtServer.GetValue()
        if domain == '':
            wx.MessageBox('Please Enter the domain name','Error')
            return
         
        #Get the whois data
        whois_data = self.perform_whois(domain)
         
        #Fill the result box
        r = self.txtResult
        r.SetValue('')
        r.AppendText(whois_data)
     
    #Function to perform the whois on a domain name
    def perform_whois(self , domain):
         
        #remove http and www
        domain = domain.replace('http://','')
        domain = domain.replace('www.','')
         
        #get the extension , .com , .org , .edu
        ext = domain[-3:]
         
        #If top level domain .com .org .net
        if(ext == 'com' or ext == 'org' or ext == 'net'):
            whois = 'whois.internic.net'
            s = socket.socket(socket.AF_INET , socket.SOCK_STREAM)
            s.connect((whois , 43))
            s.send(domain + '\r\n')
            msg = ''
            while len(msg) < 10000:
                chunk = s.recv(100)
                if(chunk == ''):
                    break
                msg = msg + chunk
             
            #Now scan the reply for the whois server
            lines = msg.splitlines()
            for line in lines:
                if ':' in line:
                    words = line.split(':')
                    if 'whois.' in words[1] and 'Whois' in words[0]:
                        whois = words[1].strip()
                        break;
         
        #Or Country level - contact whois.iana.org to find the whois server of a particular TLD
        else:
            #Break again like , co.uk to uk
            ext = domain.split('.')[-1]
             
            #This will tell the whois server for the particular country
            whois = 'whois.iana.org'
            s = socket.socket(socket.AF_INET , socket.SOCK_STREAM)
            s.connect((whois , 43))
            s.send(ext + '\r\n')
             
            #Receive some reply
            msg = ''
            while len(msg) < 10000:
                chunk = s.recv(100)
                if(chunk == ''):
                    break
                msg = msg + chunk
             
            #Now search the reply for a whois server
            lines = msg.splitlines()
            for line in lines:
                if ':' in line:
                    words = line.split(':')
                    if 'whois.' in words[1] and 'Whois Server (port 43)' in words[0]:
                        whois = words[1].strip()
                        break;
         
        #Now contact the final whois server
        s = socket.socket(socket.AF_INET , socket.SOCK_STREAM)
        s.connect((whois , 43))
        s.send(domain + '\r\n\r\n')
        msg = ''
         
        #Receive the reply
        while len(msg) < 10000:
            chunk = s.recv(100)
            if(chunk == ''):
                break
            msg = msg + chunk
         
        #Return the reply
        return msg
         
    #End
#End
 
#Create an application
app = wx.App()
 
#Create the windows :)
window = WhoisForm(None)
window.Show()
window.get_focus()
 
#Start application event loop
app.MainLoop()
