# -*- coding: utf-8 -*-
#           iCal Python Plugin for Domoticz
#
#           Dev. Platform : Win10 x64 & Py 3.5.3 x86
#
#           Author:     zak45, 2018
#           1.0.0:  initial release
#
# execute Domoticz command from personnal calendar 
# generate holidays / seasons / work time from online or local personnal calendar 
# Calendar data are loaded from ics format
#

# Below is what will be displayed in Domoticz GUI under HW
#
"""
<plugin key="iCal" name="iCal Calendar tool for Domoticz" author="zak45" version="1.0.0" wikilink="https://www.domoticz.com/wiki/plugins/iCal.html" externallink="">
    <description>
        <h2>iCal Multi Purpose Python Plugin for Domoticz</h2><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li>iCalendar integration: work with Google Calendar / Outlook.com / local : any ics file </li>
            <li>Generate Holidays : customizable by adding day from your calendar</li>
            <li>Generate At work switch : to help on custom scenario</li>
            <li>Can execute Domoticz command on device : switch / push / rgb / level</li>
        </ul>
    </description>
    <params>        
        <param field="Address" label="IP Address" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Domoticz Port" width="80px" required="true" default="8080"/>
        <param field="Mode1" label="Listener Port" width="80px" required="true" default="9003"/>        
        <param field="Mode2" label="Country,Province" width="200px" required="true" default="France"/>
        <param field="Mode4" label="State" width="80px" required="false" default=""/>
        <param field="Mode5" label="ics data gather command (HTTP or Shell)" width="400px" default=""/>
        <param field="Mode3" label="Default to AtWork" width="75px">
            <options>
                <option label="True" value="Yes"/>
                <option label="False" value="No"  default="True" />
            </options>
        </param>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="Medium" value="Medium"/>
                <option label="False" value="Normal"  default="True" />
            </options>
        </param>
    </params>
</plugin>
"""
#
# Main Import
import Domoticz
import subprocess
import time
from datetime import datetime
#
import socket
import urllib.request
import urllib.parse
import json
from urllib.error import URLError, HTTPError
#
# Required for import: path is OS dependent
# Python framework in Domoticz do not include OS dependent path
#
import site
import sys
import os
path=''
path=site.getsitepackages()
for i in path:    
    sys.path.append(i)
#
#
infolevel = 0
httpServerConn = None
HttpConnections = {}
httpClient = None
data = None
domvars = {}
# syncro , in minutes
sync = 60
bypass = True
bypassrain = True
#
key = 0
val=''
langto = 'en'
lang_xx={}
valuedevice = 0
pluie = ''
#
cleanUpvariables = False
cleanUpfiles = False
#
usedport=False
#
# find translation, first letter capitalize
# if no translation, put __ on start/end
def _(data):

	if langto=='en':
		return data

	origdata = data
	data =data[0].upper()+data.lower()[1:]
	
	if data in lang_xx:
		data = lang_xx[data][0].upper()+lang_xx[data][1:]
	else:
		if type(data) is str:
			data = '__'+origdata+'__'
		else:
			data = origdata

	return data

# Domoticz call back functions
#
# Executed once at HW creation/ update. Can create up to 255 devices.
def onStart():
    global infolevel, httpServerConn, sync, langto, usedport

    if Parameters["Mode6"] == "Debug":
        Domoticz.Debugging(1)
        infolevel = 3
    elif Parameters["Mode6"] == "Medium":
        infolevel = 2
    else:
        infolevel = 1

    DumpConfigToLog()
    Domoticz.Heartbeat(30)

    varDomoticz()    
    #    
    name = str(Parameters['HardwareID']) + '|iCal|' + 'sync'
    if (name) in domvars:
        sync = int(domvars[name]['Value'])
    name = str(Parameters['HardwareID']) + '|iCal|' + 'country'
    if (name) in domvars:
        langto = domvars[name]['Value']
    #
    loadLang()
    #
    if isOpen(Parameters['Address'],Parameters["Mode1"]):
        usedport=True
        Domoticz.Error(_('Port already in use'))
    else:
        httpServerConn = Domoticz.Connection(Name="iCalWebServer", Transport="TCP/IP", Protocol="HTTP", Port=Parameters["Mode1"])
        httpServerConn.Listen()
        Domoticz.Log(_("Listen on iCalWebserver - Port: {}").format(Parameters['Mode1']))
        # initialisation 
        if (len(Devices) == 0):
            startShell('init')
        else:
            startShell('resume')
        #
        if infolevel > 1:
            Domoticz.Log(_("Initialisation finished, will sync iCal every : {} minutes").format(str(sync)))
            Domoticz.Log(_('Hardware ID: {} ').format(str(Parameters['HardwareID'])))
    #
    Domoticz.Log(_('Information level: {}').format(str(infolevel))) 
    #
    return True

# executed each time we click on device thru domoticz GUI
def onCommand(Unit, Command, Level, Hue):    

    Domoticz.Log(_("onCommand called for Unit {} : Parameter  {}  , Level: {}").format(str(Unit), str(Command),str(Level)))

    Command = Command.strip()

    if Command == 'Set Level':
        UpdateDevice(Unit,2,str(Level))            
    elif Command == 'Off':
        if Unit == 4:
            UpdateDevice(Unit,0,'Pause')
        else:
            UpdateDevice(Unit,0,'Off')        
    elif Command == 'On':
        if Unit == 4:
            if not usedport:
                UpdateDevice(Unit,1,'Resume')
                delFiles()
                startShell('oncmd')
                if ( 5 in Devices ):
                    calcisRain()
            else:
                Domoticz.Error(_('Port already in use'))
        else:
            UpdateDevice(Unit,1,'On')        
    else:
        # unknown 
        Domoticz.Error(_('Unknown key...!!! ???'))

    return

# execution depend of Domoticz.Heartbeat(x) x in seconds
# we will gather iCal data every sync minutes
def onHeartbeat():
    global bypass, bypassrain, valuedevice

    now = datetime.now()
    seconds_since_midnight = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds()
    minutes_since_midnight = int(seconds_since_midnight / 60)

    if not usedport:

        if (len(Devices) == 0) and valuedevice != 999:
            Domoticz.Log(_('----- iCal Plugin information ---------'))
            Domoticz.Log(_('No devices in plugin system....'))
            if not cleanUpfiles or not cleanUpvariables:
                Domoticz.Log(_('We proceed to the clean up....'))
                # re create uservariables dict
                varDomoticz()
                # del uservariables
                delVariables()
                # del files
                delFiles()
            Domoticz.Log(_('plugin can be removed now .. or update HW to re-create them'))
            Domoticz.Log(_('----- end iCal Plugin information -----'))
            return

        else:

            if ( 4 in Devices ) and (Devices[4].nValue == 1):
                # main device to refresh
                if (((minutes_since_midnight % int(sync)) == 0) and bypass):
                    valuedevice = 3
                    startShell()
                    bypass = False
                else:
                    bypass = True
                UpdateDevice(4,1,_('executing, sync every {} minutes ').format(str(sync)))
                # refresh holidays twice / day 00 and 1200        
                if ( 1 in Devices ):
                    if (((datetime.now()).strftime("%H%M") == '0000' or (datetime.now()).strftime("%H%M") == '1200') and bypass):
                        valuedevice = 1
                        startShell()
                        UpdateDevice(4,1,_('executing, updating Holidays ....'))
            else:
                if ( 4 in Devices ) and (Devices[4].nValue == 0):
                    if infolevel > 1:
                        Domoticz.Log(_('Plugin is on off/pause, nothing to do'))

            # refresh israin every 15 minutes        
            if ( 5 in Devices ):
                # if ((((minutes_since_midnight % 15) == 0)) and bypassrain):
                    valuedevice = 5
                    calcisRain()
                    UpdateDevice(4,1,_('executing, updating isRain ......'))
                    bypassrain = False
                # else:
                #     bypassrain = True

    else:
        Domoticz.Error(_('Port already in use'))

    return

# Process incoming data from the subprocess which manage calendar / holidays
def onMessage(Connection, Data):

    if infolevel > 1:
        Domoticz.Log(_("onMessage called for connection: {}:{}").format(Connection.Address,Connection.Port))

    # we send back message
    if "Verb" in Data:
            strVerb = Data["Verb"]
            LogMessage(strVerb+" request received.")
            data = "<!DOCTYPE html><html><head></head><body><h3>iCal response OK!</h3><body></html>"            
            if (strVerb == "GET"):
                httpClient.Send({"Status":"200 OK", "Headers": {"Connection": "keep-alive", "Accept": "Content-Type: text/html; charset=UTF-8"}, "Data": data})
            elif (strVerb == "POST"):
                httpClient.Send({"Status":"200 OK", "Headers": {"Connection": "keep-alive", "Accept": "Content-Type: text/html; charset=UTF-8"}, "Data": data})
            else:
                Domoticz.Error(_("Unknown verb in request: {}").format(strVerb))

    # work on received data
    if "Data" in Data:
        receiveddata = str(Data['Data'])
        if infolevel > 2:
            Domoticz.Log("data:" + receiveddata)
        decodedata=Data['Data'].decode('utf-8','replace')
        if infolevel > 2:
            Domoticz.Log(decodedata)
        if process_data(decodedata):
            if infolevel > 1:
                Domoticz.Log(_('data process OK'))
        else:                    
            Domoticz.Error(_('Error to process data'))
       
    return

# executed when receive connection from remote process
def onConnect(Connection, Status, Description):
    global HttpConnections, httpClient

    if (Status == 0):
        if infolevel > 1:
            Domoticz.Log(_("Connected successfully to {}:{}").format(Connection.Address,Connection.Port))

    else:
        Domoticz.Log(_("Failed to connect ({}) to: {}:{} with error: {}").format(str(Status),Connection.Address,Connection.Port,Description))
        Domoticz.Log(str(Connection))
    if (Connection != httpClient):
            HttpConnections[Connection.Name] = Connection
            httpClient = Connection

    return

# executed when closing connection from remote process
def onDisconnect(Connection):

    if infolevel > 1:
        Domoticz.Log(_("onDisconnect called for connection '{}'").format(Connection.Name))
        Domoticz.Log(_("Server Connections: "))
        for x in HttpConnections:
            Domoticz.Log("--> "+str(x)+"'.")
    if Connection.Name in HttpConnections:
        del HttpConnections[Connection.Name]

    return

# executed once when stop/reload plugin
def onStop():
    
    Domoticz.Log(_("onStop called"))
    if HttpConnections:
        httpServerConn.Disconnect()

    return

# executed once when device is removed by some external way to the plugin (GUI, API ...)
def onDeviceRemoved(Unit):
    global valuedevice

    Domoticz.Log(_("onDeviceRemoved  call for device: {}").format(str(Unit)))
    valuedevice -= Unit

    return

# main loop to know what to do with received data from other process
def process_data(recdata):

    try:
        recdata_json = json.loads(recdata)
    except:
        Domoticz.Error(_('Error on json from Received Data: {}').format(str(recdata)))
        return False

    if infolevel > 1:
        Domoticz.Log(_('processing data : {}').format(recdata))

    if "holidays" in recdata_json:
        data = recdata_json['holidays']
        if ( 1 in Devices ):
            if not procHolidays(data):
                return False
    elif "initdevices" in recdata_json:
        data = recdata_json['initdevices']
        Domoticz.Log(str(data))
        if not createDevices(data):
            return False
    elif "status" in recdata_json:
        data = recdata_json['status']
        if not procStatus(data):
            return False
    elif "codevillage" in recdata_json:
            data = recdata_json['codevillage']            
            if  (str(Parameters['HardwareID']) + '|iCal|' + 'codevillage') not in domvars or \
                domvars[str(Parameters['HardwareID']) + '|iCal|' + 'codevillage']['Value'] != data['code']:
                Domoticz.Log(_('we re generate domvars '))
                if not varDomoticz():
                        return False
    else:
        Domoticz.Error(_('we do not know what to do of received data'))

    return True

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
        Domoticz.Debug("Device DeviceID : " + str(Devices[x].DeviceID))
    return

# Update Device into DB
def UpdateDevice(Unit, nValue, sValue):
    # Make sure that the Domoticz devices still exists (they can be deleted) before updating it 
    if (Unit in Devices):
        if (Devices[Unit].nValue != nValue) or (Devices[Unit].sValue != sValue):
            Devices[Unit].Update(nValue=nValue, sValue=str(sValue))
            if infolevel > 1:
                Domoticz.Log(_("we update {}:'{}' ({})").format(str(nValue),str(sValue),Devices[Unit].Name))
    return


#Command to initialize the subprocess managing calendar / holidays
def startShell(*args):
    global valuedevice

    # select comand to launch depend of OS
    if sys.platform.startswith('win32'):
        cmd = "iCal.cmd"
    else:
        cmd = "iCal.sh"

    hwid1 = 0
    hwid2 = 0
    hwid3 = 0
    hwid4 = 0  
    hwid5 = 0

    # retreive country and optional province
    country = ''
    province = '' 
    country = Parameters['Mode2'].split(',')[0]
    try:    
        province = Parameters['Mode2'].split(',')[1]
    except:
        province = ''
        pass

    # what to do ?
    if args:
        # onStart
        if ('init') in args:
            valuedevice = 999
        # onCommand
        elif ('oncmd') in args:
            valuedevice = 888
        elif ('resume') in args:
            valuedevice = 900
        # unknown
        else:
            valuedevice = 0
    else:
        if infolevel > 1:
            Domoticz.Log(_('we take valuedevice from others func : {}').format(str(valuedevice)))

    if ( 1 in Devices):
        hwid1=Devices[1].ID    
    if ( 2 in Devices):
        hwid2=Devices[2].ID    
    if ( 3 in Devices):
        hwid3=Devices[3].ID    
    if ( 4 in Devices):
        hwid4=Devices[4].ID    
    if ( 5 in Devices):
        hwid5=Devices[5].ID
    
    #Location need to be set
    if not Settings['Location']:
        Domoticz.Error(_('ERROR, location not defined'))
        return False

    if valuedevice > 0:
        cmdargs='"'+ Parameters['Mode1']                    +','+\
                '' + country + ''                           +','+\
                '' + province + ''                          +','+\
                '' + Parameters['Mode4'] + ''               +','+\
                    str(Parameters['HardwareID'])           +','+\
                '' + str(Parameters['Mode5']) + ''          +','+\
                '' + Parameters['HomeFolder'] + ''          +','+\
                '' + Parameters['Mode3'] + ''               +','+\
                    str(valuedevice)                        +','+\
                    str(hwid1)                              +','+\
                    str(hwid2)                              +','+\
                    str(hwid3)                              +','+\
                    str(hwid4)                              +','+\
                    str(hwid5)                              +','+\
                    str(infolevel)                          +','+\
                    str(Parameters['Address'])              +','+\
                    str(Parameters['Port'])                 +','+\
                '' + Settings['Location'] + ''              +'"'
        # now we can create the cmd
        command = '"' + Parameters['HomeFolder'] + cmd + '" ' + '"' + Parameters['HomeFolder'] + 'iCal.py" ' + cmdargs + ' no'
        if infolevel > 1:
            Domoticz.Log(_('command to execute : {}').format(command))

        # launch the cmd
        try:
            subprocess.check_call(command, shell=True, timeout=2)
        except subprocess.CalledProcessError as e:
            Domoticz.Error(_('ERROR to start subprocess'))
            Domoticz.Error(str(e.returncode))
            Domoticz.Error(str(e.cmd))
            Domoticz.Error(str(e.output))
            return False

    else:
        if infolevel > 1:
            Domoticz.Log(_('Nothing to do on subprocess, devices list : {}').format(str(Devices)))
        return False

    return True

def DumpHTTPResponseToLog(httpDict):
    if isinstance(httpDict, dict):
        Domoticz.Log("HTTP Details ("+str(len(httpDict))+"):")
        for x in httpDict:
            if isinstance(httpDict[x], dict):
                Domoticz.Log("--->'"+x+" ("+str(len(httpDict[x]))+"):")
                for y in httpDict[x]:
                    Domoticz.Log("------->'" + y + "':'" + str(httpDict[x][y]) + "'")
            else:
                Domoticz.Log("--->'" + x + "':'" + str(httpDict[x]) + "'")
    return

def LogMessage(Message):
    if Parameters["Mode6"] != "Normal":
        Domoticz.Log(Message)
    elif Parameters["Mode6"] != "Debug":
        Domoticz.Debug(Message)
    else:
        f = open("http.html","w")
        f.write(Message)
        f.close()   

    return

# execute json request to Domoticz
def exeDomoticz(params):
    global data

    try:
        params = urllib.parse.urlencode(params)
        Domoticz.Log('http://' +str(Parameters['Address'])+':'+str(Parameters['Port']) + '/json.htm?'+ params)
        html=urllib.request.urlopen('http://' +str(Parameters['Address'])+':'+str(Parameters['Port']) + '/json.htm?'+ params, timeout=2)        
        Response=html.read()
        encoding = html.info().get_content_charset('utf-8')
        data=json.loads(Response.decode(encoding))
        if infolevel > 2:
            Domoticz.Log(_('Request from domoticz to : {} with encoding : {}').format(str(params),str(encoding)))
    except:
        Domoticz.Error(_('Error sending command to domoticz : {}').format(str(params)))
        return False

    return True

# init uservariables dict
#json.htm?type=command&param=getuservariables
def varDomoticz():
    global domvars

    params = {'type':'command','param':'getuservariables'}
    if exeDomoticz(params):
       if data['status'] == 'OK':
            if 'result' in data:
                result=data['result']
                for item in result:
                    var = item['Name']
                    domvars[var] = item
       else:
            Domoticz.Log(_('Domoticz do not send OK message for variables ?????'))
    else:
        Domoticz.Error(_('Erreur to execute get user variables'))
        return False

    return True

# we delete all uservariables related to this plugin - HW
#/json.htm?type=command&param=deleteuservariable&idx=IDX
def delVariables():
    global cleanUpvariables

    Domoticz.Log(_('we clean uservariables in database'))
    # retreive the IDX from each HWID
    for index, value in domvars.items():
        if str(domvars[index]['Name']).startswith(str(Parameters['HardwareID'])+'|iCal|'):
            IDX = domvars[index]['idx']
            params = {'type':'command','param':'deleteuservariable', 'idx':IDX}
            if exeDomoticz(params):
               if data['status'] == 'OK':
                    Domoticz.Log(_('we have deleted uservariable: {} with IDX {}'.format(index,IDX)))
               else:
                    Domoticz.Error(_('Domoticz do not send OK message for variables ?????'))
            else:
                Domoticz.Error(_('Erreur to execute del user variable : {}').format(IDX))

    cleanUpvariables = True

    return

# we erase all files related to this plugin HWID
def delFiles():
    global cleanUpfiles

    Domoticz.Log(_('we clean related files in plugin folder'))
    files=[
            Parameters['HomeFolder'] + str(Parameters['HardwareID'])+'iCal.ics', 
            Parameters['HomeFolder'] + str(Parameters['HardwareID'])+'output.txt', 
            Parameters['HomeFolder'] + str(Parameters['HardwareID'])+'output.err', 
            Parameters['HomeFolder'] + str(Parameters['HardwareID'])+'iCal.ics.bkp'
            ]

    try:
        for ifile in files:
            if os.path.exists(ifile):
                os.remove(ifile)
                Domoticz.Log(_('we have deleted this file: {}').format(ifile))
    except:
        Domoticz.Error(_('Error to delete this file: {}').format(ifile))
        pass

    cleanUpfiles = True
    
    return

# Data received from holidays: Selector switch re generation
def procHolidays(data):

    try:
        selectorname =''
        # we generate the dict with key as int for sort
        selector={int(key):value for key,value in data.items()} 
        sortedkey = sorted(selector)

        for key in range(len(sortedkey)):
            # acces key is now sortedkey[key]
            selectorname = selectorname + '|'+selector[sortedkey[key]]['name']
        
        # re generate selector switch      
        Options =   {   "LevelActions"  :"|"*len(sortedkey), 
                        "LevelNames"    :"Off"  + selectorname,
                        "LevelOffHidden":"True",
                        "SelectorStyle" :"1"
                        }
        if ( 1 in Devices ): 
            Devices[1].Update(nValue=Devices[1].nValue, sValue=str(Devices[1].sValue), Options=Options)            
    except:
        Domoticz.Error (_('Error to re create Holidays selector'))
        return False
    #
    # Schedules creation 
    #/json.htm?active=true&command=0&date=2018-05-13&days=0&hour=0&idx=1127&level=50&min=0&param=addtimer&randomness=false&timertype=5&type=command
    try:
        # we remove first all schedules before create /json.htm?type=command&param=cleartimers&idx=DeviceRowID
        idx = Devices[1].ID
        params = {'type':'command','param':'cleartimers','idx':'' + str(idx)}
        exeDomoticz(params)
        # create all schedules not on past
        updatetotoday = False
        for key in range(len(sortedkey)):
            # acces key is now sortedkey[key]
            day = selector[sortedkey[key]]['date']
            if  day < datetime.now().strftime("%Y-%m-%d"):
                continue
            if datetime.now().strftime("%Y-%m-%d") == day:
                updatetotoday = True
                leveltoday = str(sortedkey[key])
            level = sortedkey[key]        
            params =    {
                        'type':'command',
                        'param':'addtimer',
                        'idx':'' + str(idx) + '',
                        'active':'true',
                        'timertype':'5',
                        'date':''+day+'',
                        'hour':'00',
                        'min':'00',
                        'randomness':'false',
                        'command':'0',
                        'days':'0',
                        'level':''+ str(level)
                        }
            if infolevel > 2:
                Domoticz.Log('Param :' + str(params))
            exeDomoticz(params)
        # we put the selector to right value
        if updatetotoday:
            Devices[1].Update(nValue = 1, sValue = leveltoday)
        else:
            Devices[1].Update(nValue = 0, sValue = 'Off')
    except:
        Domoticz.Error(_('Error in schedules for Holidays'))
        return False

    return True

# create timers for Seasons
#/json.htm?active=true&command=0&days=128&hour=0&idx=1121&level=10&mday=21&min=0&month=3&param=addtimer&randomness=false&timertype=12&type=command
# Specific for RU / AU / NZ: seasons begin first day of month and different date for China
def procSeasons():

    i=1
    idx = Devices[2].ID
    if infolevel > 2:
        Domoticz.Log('Location Settings: ' + str(Settings["Location"]))
    Latitude = Settings["Location"].split(';')[0]
    # If latitude is positive, the position is on the northern hemisphere, if it is negative, it is on the southern hemisphere.
    if float(Latitude) > 0:
        hemisphere = 'north'
    else:
        hemisphere = 'south'
    if infolevel > 1:
        Domoticz.Log('Actual Latitude :' + str(Latitude) + ' on Hemisphere : ' + hemisphere)

    # we remove first all schedules before create /json.htm?type=command&param=cleartimers&idx=DeviceRowID    
    params = {'type':'command','param':'cleartimers','idx':'' + str(idx)}
    if infolevel > 2:
        Domoticz.Log('Param :' + str(params))
    exeDomoticz(params)

    # 4 seasons, fixed date yearly (not really true but we consider as), depend on hemisphere, we start on Spring
    while i < 5:
        level = i*10
        sday = '21'
        syear = datetime.now().strftime("%Y")
        month = datetime.now().strftime("%m")
        if i == 1:
            if hemisphere == 'north':
                smonth = '03'
            else:
                smonth = '09'
            if langto == 'ru' or langto == 'au' or langto == 'nz':
                sday = '01'
            elif langto == 'zh-cn':
                sday = '04'
                smonth = '02'
            else:
                sday = '20'
        elif i == 2:
            if hemisphere == 'north':
                smonth = '06'
            else:
                smonth = '12'
            if langto == 'ru' or langto == 'au' or langto == 'nz':
                sday = '01'
            elif langto == 'zh-cn':
                sday = '05'
                smonth = '05'
        elif i == 3:
            if hemisphere == 'north':
                smonth = '09'
            else:
                smonth = '03'
            if langto == 'ru' or langto == 'au' or langto == 'nz':
                sday = '01'
            elif langto == 'zh-cn':
                sday = '07'
                smonth = '08'
        elif i == 4:
            if hemisphere == 'north':
                smonth = '12'
            else:
                smonth = '06'
            if langto == 'ru' or langto == 'au' or langto == 'nz':
                sday = '01'
            elif langto == 'zh-cn':
                sday = '07'
                smonth = '11'
        #
        params = {
                    'type':'command',
                    'param':'addtimer',
                    'idx':'' + str(idx) + '',
                    'active':'true',
                    'timertype':'12',
                    'month':''+smonth+'',
                    'mday':''+sday+'',
                    'hour':'0',
                    'min':'0',
                    'randomness':'false',
                    'command':'0',
                    'days':'128',
                    'level':'' + str(level)
                }
        if infolevel > 2:
            Domoticz.Log('Param :' + str(params))
        exeDomoticz(params)
        i+=1

    # we put the selector to right value
    date = datetime.now()
    level = actualSeason(date, hemisphere)    
    Devices[2].Update(nValue = 1, sValue = level)

    return

# determine actual season, depend of hemisphere, return level for season selector switch
def actualSeason(date, hemisphere):
    ''' date is a datetime object
        hemisphere is either 'north' or 'south', dependent on long/lat.
    '''
    md = date.month * 100 + date.day

    if ((md > 320) and (md < 621)):
        Level = 0 #spring
    elif ((md > 620) and (md < 923)):
        Level = 1 #summer
    elif ((md > 922) and (md < 1223)):
        Level = 2 #autumn
    else:
        Level = 3 #winter

    if hemisphere != 'north':
        if Level < 2:
            Level += 2 
        else:
            Level -= 2

    Level = str( Level + 1 * 10 )

    if infolevel > 1:
        Domoticz.Log(_('Level for actual season : {}').format(str(Level)))

    return Level

#we load  lang  dict: en;xx
def loadLang():
    global lang_xx, langto   

    lang_file = Parameters['HomeFolder']+ 'en_' + langto + '.lng'
    if not os.path.exists(lang_file) and langto != 'en':
        langto = 'en'
        lang_file = Parameters['HomeFolder']+ 'en_' + langto + '.lng'
        Domoticz.Error(_('Lang file not exist, we try to fall back to "en" : {}').format(str(lang_file)))

    Domoticz.Log('lang file : ' + lang_file)
    
    try:
        with open(lang_file,  'r' , encoding='utf-8') as fp:
            for line in fp:
                if line.startswith('#--'):
                    next
                else:
                    key, val = line.split('|;|')
                    key = (str(key)[0].upper()+str(key).lower()[1:]).rstrip('\r\n')
                    if len(val) != 0:
                        val = (str(val)[0].upper()+str(val).lower()[1:]).rstrip('\r\n')
                    if langto == 'en':
                        lang_xx[key] = key.rstrip('\r\n')
                    else:
                        lang_xx[key] = val.rstrip('\r\n')
    except:
        Domoticz.Error(_('Lang file not exist or to process data from : {}').format(str(lang_file))) 

    return

# create devices once language file generated
def createDevices(data):
    global langto, valuedevice

    if data['create']=='yes':

        try:
            if data['lang']!='en':
                langto = data['lang']
                loadLang()
                if infolevel > 1:
                    Domoticz.Log(_('we reload language : {}').format(data['lang']))

            if (len(Devices) == 0):
    
                Options =   {   "LevelActions"  :"||||" , 
                                "LevelNames"    :"Off" ,
                                "LevelOffHidden":"false",
                                "SelectorStyle" :"1"
                             }        
                Domoticz.Device(Name=_("Holidays"),  Unit=1, TypeName="Selector Switch", Switchtype=18, Image=12, Options=Options, Used=1).Create()

                Options =   {   "LevelActions"  :"||||" , 
                                "LevelNames"    : "Off|"+_("spring")+"|"+_("summer")+"|"+_("autumn")+"|"+_("winter") ,
                                "LevelOffHidden":"true",
                                "SelectorStyle" :"0"
                             }        
                Domoticz.Device(Name=_("Seasons"),  Unit=2, TypeName="Selector Switch", Switchtype=18, Image=12, Options=Options, Used=1).Create()
                procSeasons()
        
                Domoticz.Device(Name=_("At Work"),  Unit=3, TypeName="Switch", Used=1, Image=9).Create()
                Domoticz.Device(Name=_("iCal Status"),  Unit=4, Type=17, Image=9, Switchtype=17, Used=1).Create()
        
                Domoticz.Log(_("Devices created."))
                valuedevice = 10
                if (4 in Devices):
                    UpdateDevice(4,1,'Init')

                if langto == 'fr':    
                    Domoticz.Device(Name="Prévision Pluie sur 1 heure",  Unit=5, TypeName="Alert", Used=1).Create()

            else:

                valuedevice = 0
                for key, val in Devices.items():
                    valuedevice += key 
        except:
            Domoticz.Error(_('Error to create devices'))
            return False

    return True

# we put status information from subprocess
def procStatus(data):

    step=data['step']
    msg=data['msg']

    try:
        UpdateDevice(4,1,'**' +step+ '-> msg:'+msg) 
    except:
        Domoticz.Error(_('Error to update status'))
        return False

    return True

# device specific to France : should it rain in the next hour ?
def calcisRain():
    global pluie
 
    # level if 4 : rain
    level = 1
    # we need the village code linked to the name
    name = str(Parameters['HardwareID']) + '|iCal|' + 'codevillage'

    Domoticz.Log("Name %s " % name)
    if (name) in domvars:
        codeville = domvars[name]['Value']
        Domoticz.Log("Code ville : " + codeville )
    else:
        Domoticz.Error(_('Not able to find codevillage'))
        return False

    try:
        # request data from meteofrance 
        url = 'http://www.meteofrance.com/mf3-rpc-portlet/rest/pluie/' + codeville
        Domoticz.Log("URL " + url)
        data=queryData(url)
    except:
        Domoticz.Error(_('Not able to query data from Meteo France'))
        return False

    # we format the received data
    pluie = ''
    if data:
        if data['niveauPluieText']:
            for index in range(len(data['niveauPluieText'])):
                if index == 0:
                    pluie = data['niveauPluieText'][0]
                else:                
                    pluie=pluie + ' , puis    : ' + data['niveauPluieText'][index] + '\n'
        else:
            pluie = 'aucun resultat'

        # if find ': Pr' into pluie ==> will rain !!, set level to  4
        level = pluie.find(': Pr')
        if level == -1:
            level = 1        
        else:
            level = 4

        # Update alert device
        if (5 in Devices):
            UpdateDevice(5,level,pluie)

    else:

        pluie = 'Error probleme sur json de meteofrance'
        return False

    if infolevel > 1:  
        Domoticz.Log('Prevision pluie :' + pluie)        

    return True

def queryData(url):

    try:
        req=urllib.request.Request(url,headers=\
        {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'})
        html=urllib.request.urlopen(req, timeout=2)
        Response=html.read()  
        encoding = html.info().get_content_charset('utf-8')
        data=json.loads(Response.decode(encoding))        
    except:
        Domoticz.Error(_('Error to execute query'))

    return data

def isOpen(ip,port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(1.0)
    try:
        s.connect((ip, int(port)))
        s.shutdown(2)
        return True
    except:
        return False