# -*- coding: utf-8 -*-
#   Main prog to manage calendar / holidays
#   Part of Domoticz plugin: iCal
#   Color keyword  https://www.w3.org/TR/SVG/types.html#ColorKeywords
#   Geotool https://nominatim.openstreetmap.org/reverse.php?format=json&lat=xx.xxxxxx&lon=yy.yyyyyy
#

from datetime import datetime, timedelta, date
import time
import requests
import subprocess
import icalendar
import holidays
import urllib.request
import urllib.parse
import pytz
from  colour import Color
from dateutil.rrule import *
#
import os
import sys
import json
#
# Translation
# lang to translate
langto = 'en'
try:
    from googletrans import Translator
    langto = ''
except:
    # module translate not there, we fall back to "en" by default
    langto = 'en'
#
# command line arguments
#
args=sys.argv[1].split(',')
#
port=args[0]
icountry = args[1]
iprovince = args[2]
istate = args[3]
hwid = args[4]
url = args[5]
folder= args[6]
defaultToBlank= args[7]
# if valuedevice 999 or 888 we refresh all , if  3  we refresh atwork, if  1  we refresh holidays else nothing
valuedevice= int(args[8])
# Domoticz ID of plugin devices else 0
hwid1 = int(args[9])
hwid2 = int(args[10])
hwid3 = int(args[11])
hwid4 = int(args[12])
hwid5 = int(args[13])
# debug level
infolevel = int(args[14])
domip = str(args[15])
domport = str(args[16])
# lat/long from Domoticz settings, used to find country (used for language)
location= args[17]
#
interactive=sys.argv[2]
#
#variables
data = ''
ifile = str(folder) + str(hwid) + 'iCal.ics'
devices = {}
allowedcmd = []
today = datetime.now()
params = {}
schedules = {}
domvars = {}
lat = 0
lon = 0
postcr = {}
codevil = 0
addhol = 0
#lang dict key:value e.g. 'Hello'|;|'Bonjour'
lang_xx={}
# name of the atwork switch
atworkdevicename = ''
idx = ''
lastonatwork = datetime.now() + timedelta(days=365*100)
atworkdict = {}
# number of uservariables
varnumber = 0
# number of uservariables created
testvar = 0
# test atwork modification
modatwork = 0
year1 = None
#
# capture output
#
if interactive != 'yes':
    backup_stdout=sys.stdout
    backup_stderr=sys.stderr
    sys.stdout =open(str(folder) + str(hwid) +'output.txt','w',encoding='utf-8')
    sys.stderr =open(str(folder) + str(hwid) +'output.err','w',encoding='utf-8')
#
# functions
#
# print Error
def genError(proc,msg):

    print(msg)
    sendStatus(proc,msg)
    print ('Error :', sys.exc_info()[0], sys.exc_info()[1], sys.exc_info()[2])

    return

# send data to plugin.py listener
def send_data(data):

    url = 'http://' +domip+':'+str(port)

    try:
        send=requests.post(url, data=data.encode('utf-8'), headers={'Content-type': 'text/plain; charset=utf-8'})
    except:
        genError('send_data',_('Error sending data'))
        print(str(data))
        raise

    return

# ask plugin.py to create devices
def creDev():

    data = '{"initdevices":{"create":"yes","lang":"'+langto+'"}}'
    send_data(str(data))

    return

# send status to plugin.py
def sendStatus(step,status):

    data = '{"status":{"step":"'+step+'","msg":"'+status+'"}}'
    send_data(str(data))

    return

# send code village for French location
def sendCodevillage():

    data = '{"codevillage":{"code":"'+str(codevil)+'"}}'
    send_data(str(data))

    return

#
#we load  lang  dict: en;xx
def loadLang():
    global lang_xx

    lang_file = folder +'en_' + langto + '.lng'

    try:
        with open(lang_file,  'r' , encoding='utf-8') as fp:
            for line in fp:
                key, val = line.split('|;|')
                key = (str(key)[0].upper()+str(key).lower()[1:]).rstrip('\r\n')
                val = (str(val)[0].upper()+str(val).lower()[1:]).rstrip('\r\n')
                if langto != 'en':
                    lang_xx[key] = val.rstrip('\r\n')
                else:
                    lang_xx[key] = key.rstrip('\r\n')
    except:
        genError('loadLang',_('Error to load language file'))

    return

#we translate the text
def trText(data,lang,origlang):

    #print('we translate {} from {} to {}'.format(data,origlang,lang))
    translator = Translator()
    translation = translator.translate(data,dest=lang,src=origlang).text
    #print('traduction: {} '.format(translation))

    return translation

# load text to translate from en to langto
def loadTexttotranslate():
    global lang_xx

    lang_file=folder+'en_en.lng'	

    try:
        with open(lang_file, 'r' , encoding='utf-8') as fp:
            for line in fp:
                if line.startswith('#--'):
                    next
                else:
                    key, val = line.split('|;|')
                    key=str(key)[0].upper()+key.lower()[1:]
                    try:
                        val=trText(key,langto,'en')
                        lang_xx[key] = val
                    except:
                        genError('loadTexttotranslate',_('Error to translate : {}').format(val))
    except:
        genError('loadTexttotranslate',_('Error to read lang file to translate : {}').format(lang_file))
            
    return

# find translation, first letter capitalize
# if no translation, put __ on head/end
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

#
# we create en_xx.lng : xx = country_code , this file contains all translations (work offline & we do not have to do it again)
#
def creLang():

    lang_file = folder +'en_' + langto + '.lng'

    try:
        with open(lang_file,  'w' , encoding='utf-8') as fp:
            for key, val in lang_xx.items():
                value = key + '|;|' + val + '\n'
                fp.write(value)
    except:
        genError('creLang',_('Error to create lang file translated : {}').format(lang_file))

    return

# retreive postcode / country code from geo data
# https://nominatim.openstreetmap.org/reverse.php?format=json&lat=xx.xxxxxx&lon=yy.yyyyyy
def geoData(lat,lon):

    data =''
    params = {'format':'json','lat':'' + str(lat) + '', 'lon':'' + str(lon) + ''}    
    url = 'https://nominatim.openstreetmap.org/reverse.php?'
    #
    try:
        params = urllib.parse.urlencode(params,doseq=True)
        req=urllib.request.Request(url + params,headers=\
        {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'})
        html=urllib.request.urlopen(req, timeout=5)
        Response=html.read()  
        encoding = html.info().get_content_charset('utf-8')
        data=json.loads(Response.decode(encoding))
        print ('Request from openstreetmap to :' + str(params) + '  with encoding : ' + str(encoding))    
    except:
        genError('geoData',_('Error to execute Geo Data query'))

    return data

# generate uservariables
def initVar():
    global lat,lon,postcr,langto, varnumber

    # HWID|iCal|sync: how often we update from iCal in minutes
    varname = str(hwid) + '|iCal|' + 'sync'
    value = '60'
    varnumber += 1
    creVar(varname,value)

    # HWID|iCal|cmd:  allowed cmd    
    varname = str(hwid) + '|iCal|' + 'cmd'
    value = 'switch,push,level,rgb'
    varnumber += 1
    creVar(varname,value)

    # HWID|iCal|tz: TimeZone in Olson from local TZ
    varname = str(hwid) + '|iCal|' + 'tz'
    value = 'tz'
    varnumber += 1
    creVar(varname,value)

    # HWID|iCal|postcode: Postal code from lat/long
    varname = str(hwid) + '|iCal|' + 'postalcode'
    value = 'pc'
    varnumber += 1
    creVar(varname,value)

    # HWID|iCal|village: village name from lat/long
    varname = str(hwid) + '|iCal|' + 'village'
    value = 'vi'
    varnumber += 1
    creVar(varname,value)

    # HWID|iCal|countrycode: country code from lat/long
    varname = str(hwid) + '|iCal|' + 'country'
    value = 'cc'
    varnumber += 1
    if not creVar(varname,value):
        langto = 'en'

    if langto == 'fr':
        # HWID|iCal|codevillage: village code from village
        varname = str(hwid) + '|iCal|' + 'codevillage'
        varnumber += 1
        value = 'vc'
        if creVar(varname,value):
            sendCodevillage() 

    return

# Create uservariable 
#/json.htm?type=command&param=saveuservariable&vname=uservariablename&vtype=uservariabletype&vvalue=uservariablevalue
def creVar(varname,value):
    global lat,lon,postcr,langto, codevil, testvar

    vildata = {}

    if varname in domvars:
        print(_('the uservariable exist: {} --> {}').format(varname,domvars[varname]['Value']))
        testvar += 1
        if varname == str(hwid) + '|iCal|' + 'codevillage':
            codevil = domvars[varname]['Value']
    else:
        if value == 'tz':
            localtz = time.tzname[0].split(',')
            for name in pytz.all_timezones:
                timezone = pytz.timezone(name)                
                if not hasattr(timezone, '_tzinfos'):
                    continue#skip, if some timezone doesn't have info
                # go thru localtz and see if  name in timezone
                for city in localtz:
                    if city in str(timezone):
                        print(city,timezone)
                        value = str(timezone)
                    break
        elif value == 'pc' or value == 'cc' or value == 'vi' or value == 'vc': 
            if lat == 0:
                lat,lon = location.split(';')
            if not postcr:
                postcr=geoData(lat,lon)
            if value == 'pc':
                value = postcr['address']['postcode']
            elif value == 'cc':
                value = postcr['address']['country_code']
                if value == 'cn':
                    value = 'zh-cn'
                if langto !='en':
                    langto = value
            elif value == 'vi':
                if 'village' in postcr['address']:
                    value = postcr['address']['village']
                elif 'city' in postcr['address']:
                    value = postcr['address']['city']
                else:
                    value = "*unknown*"
            elif value == 'vc' and langto == 'fr':
                # we need to find the village code linked to the name (can do the search also by postal code)
                url = 'http://www.meteofrance.com/mf3-rpc-portlet/rest/lieu/facet/pluie/search/input=' + postcr['address']['village']
                vildata = queryData(url)
                if vildata:
                    # we need first rec only to find the code, else info not available
                    if (vildata[0]['slug']).lower() == (postcr['address']['village']).lower():                    
                        value = vildata[0]['id']
                        codevil = value

        params ={
                    'type':'command',
                    'param':'saveuservariable',
                    'vname':'' +   str(varname) + '', 
                    'vtype':'2',
                    'vvalue':'' + str(value) + ''
                }
        if not exeDomoticz(params):
            genError ('creVar',_('Erreur to execute create user variable'))
            return False
        else:
            if data['status'] != 'OK':
                genError('creVar',_('Domoticz not return OK for create uservariable'))
                return False
    
    return True

# Holidays initialization
def initHolidays():
    global plugin_holidays

    actualyear = int(datetime.now().strftime("%Y"))

    try:
        plugin_holidays = getattr(holidays,icountry)        
    except:
        #probably country not managed, so we create base one
        plugin_holidays = getattr(holidays,'HolidayBase') 
        genError('initHolidays',_('country not managed in Holidays: {} , we create base one').format(icountry))

    plugin_holidays = plugin_holidays(state=istate,prov=iprovince, years = actualyear)

    # if end of year, we generate for y+1
    if (datetime.now().strftime("%m")) == '12':
        year1 =  int((datetime.now() + timedelta(days=60)).strftime("%Y"))
        date(year1, 1, 1) in plugin_holidays
    
    return

# Add custom holidays from ics file
def addHolidays(summary,startdt,enddt):
    global plugin_holidays
    
    addhol  = 0
    nbrdays = 0

    if not summary:
        summary = '**holiday**'
    # we need to know how many days we add startdt & enddt    
    delta = enddt - startdt
    nbrdays = delta.days    
    if nbrdays == 0:
        nbrdays = 1
    if enddt.strftime('%H%M') != '0000':        
        print(_('Warning --- partial day for holidays : start {} end : {}').format(startdt,enddt))
        sendStatus('addHolidays',_('Warning --- partial day for holidays : start {} end : {}').format(startdt,enddt))
    
    while addhol < nbrdays:
        print(_('we add day {} to holidays').format((startdt + timedelta(days=addhol)).strftime('%Y-%m-%d')))
        addday = {(startdt + timedelta(days=addhol)).strftime('%Y-%m-%d') : str(summary)+':'+ str("{0:0=4d}".format(int(startdt.strftime('%m%d'))))} 
        plugin_holidays.append(addday)
        addhol += 1
 
    return

# Holidays to send to plugin.py
def genHolidays():
    global data

    data = '{"holidays":{'
    level = 0
    
    for date, name in sorted(plugin_holidays.items()):
        #print(date, name)
        level += 1
        data = data + '"' + str(level * 10) + '":{"date":"' + str(date) + '","name":"' + str(name) + '"},'
   
    if level == 0:
        data = data + '"00":{"date":"0","name":"0"}}}'
    else: 
        data = data[0:data.rfind(',')] + '}}'

    if infolevel > 1:
        sendStatus('genHolidays',_('End of : {}').format('holidays generation'))

    print(_('Number of days generated : {}').format(level))

    return

# Generate cmd to devices
def progCmd(desc, start, end):
    global params

    cmd = -1
    endcmd = -1
    level = -1 
    hue = 0
    color = ''
    scope = -1
    atwork = False

    try:
        # User entry.. so we need to be sure correct syntax and can contains no defined numbers of ':' 
        devname,typecmd,value,*scopedict = desc[5:].rstrip('\r\n').split(':')
    except:
        genError('progCmd',_('Error in cmd syntax : {}').format(desc))
        return

    # if scope = 0, we will not generate end schedule
    if scopedict:
        if scopedict[0] == '0':
            scope = 0
        else:
            genError('progCmd',_('Error in cmd syntax : {}').format(desc))
            return

    typecmd = typecmd.lower()

    # if device name not found , exit
    if not devname.lower() in devices:
        genError('progCmd',_('unknown device : {}').format(devname))
        return
    else:
        idx = devices[devname.lower()]['idx']
        status = devices[devname.lower()]['Status']
        if (devices[devname.lower()]['Name']).lower() == atworkdevicename.lower():
            atwork = True

    # if typecmd = switch   we do On or Off, end say to Toggle 
    # if typecmd = Level    we do Setlevel % , end say to put 0/Off
    # if typecmd = rgb      we put light to corresponding color/On, end say to put it Off 
    # if typecmd = push     we simulate push button, only for start, can be On or Off

    if typecmd in allowedcmd:
        # generate the cmd to execute
        if typecmd == 'switch' or typecmd == 'push':
            if value.lower() == 'on':
                cmd,endcmd = 0,1
            elif value.lower() == 'off':
                cmd,endcmd = 1,0
            else:
                typecmd = '*error*'
                print(_('Error on value for switch/push : {}').format(str(value)))
            if typecmd == 'push':
                scope = 0
        elif typecmd == 'level':
            if int(value) > 0:
                cmd = 0
                endcmd = 1
                level = int(value)
            else:
                typecmd = '*error*'
                print(_('Error on value for level : {}').format(str(value)))
        elif typecmd == 'rgb':
            # we need to calculate hue = int(c.hue * 360 ), rgb * 255
            level = 100
            endcmd = 1
            cmd = 0
            # we take color and translate if needed
            colname=str(value).lower().rstrip('\r\n')
            if langto != 'en':
                colname=trText(colname,'en',langto)            
            try:
                col=Color(colname)
                hue = int(col.hue * 360)
                r = int(col.rgb[0] * 255)
                g = int(col.rgb[1] * 255)
                b = int(col.rgb[2] * 255)
                rgb=(r,g,b)
                print(' Color : ' + colname + ' RGB Value : ' + str(rgb) + ' Hue : ' + str(hue))
                color='{"b":'+ str(b) +',"cw":0,"g":'+ str(g) +',"m":3,"r":'+ str(r) +',"t":0,"ww":0}'
            except:
                genError('progCmd',_('unknown color : {}').format(colname))
                return

        print('cmd:'+str(cmd)+' level:'+str(level) +' hue:'+str(hue)+' scope:'+str(scope) + ' atWork:' + str(atwork))
        print(_('Actual status for {} is: {}').format(devname,status))

        # execute / schedule the cmd
        if start.strftime("%Y%m%d %H%M") < today.strftime("%Y%m%d %H%M"):
            print(_('we execute cmd now and schedule end'))
            # we execute cmd now and schedule end, end at first
            if typecmd == 'switch' or typecmd == 'rgb' or typecmd == 'push' or typecmd == 'level':
                # end only if scope <> 0
                if int(scope) != 0:            
                    # end at first                
                    if genTimer(end,endcmd,idx,level,hue,color,atwork):
                        if ('**stop**' not in params):
                            if not exeDomoticz(params):
                                print(_('Error to execute add timer for end: {}').format(end.strftime("%Y%m%d %H%M")))
                            else:
                                if data['status'] != 'OK':
                                    print(_('Error to create timer for end : {}').format(end.strftime("%Y%m%d %H%M")))
                        else:
                            print(_('Nothing to do for this schedule: {}').format(str(end)))
                    else:
                        print(_('Error to create add timer for end: {}').format(end.strftime("%Y%m%d %H%M")))
                else:
                    print(_('End schedule not created, scope = {}').format(str(scope)))
                # now always
                if cmd == 0: 
                    cmd = 'On' 
                else: 
                    cmd = 'Off'
                if status != 'Off':
                    status = 'On'                    
                # test device status before send cmd, if same, nothing to do except for level
                if (status != cmd) or (typecmd == 'level'):
                    if typecmd == 'switch' or typecmd == 'push':
                        #/json.htm?type=command&param=switchlight&idx=272&switchcmd=Off&level=0&passcode=
                        params = {'type':'command','param':'switchlight','idx':''+str(idx)+'','switchcmd':''+cmd+'','level':'0','passcode':''}
                        if not exeDomoticz(params):
                            print(_('Error to execute command : {}').format(params))
                        else:
                            if data['status'] != 'OK':
                                print(_('Domoticz status not OK for {} command: {}').format('switch',str(idx)))
                    elif typecmd == 'rgb':
                        #/json.htm?type=command&param=setcolbrightnessvalue&idx=1054&hue=274&brightness=100&iswhite=false
                        params = {'type':'command','param':'setcolbrightnessvalue','idx':''+str(idx)+'','hue':''+str(hue)+'','brightness':'100','iswhite':'false'}
                        if not exeDomoticz(params):
                            print(_('Error to execute command : {}').format(params))
                        else:
                            if data['status'] != 'OK':
                                print(_('Domoticz status not OK for {} command: {}').format('rgb',str(idx)))
                    elif typecmd == 'level':
                        #/json.htm?type=command&param=switchlight&idx=1048&switchcmd=Set Level&level=42
                        params = {'type':'command','param':'switchlight','idx':''+str(idx)+'','switchcmd':'Set Level','level':''+str(level)+''}
                        if not exeDomoticz(params):
                            print(_('Error to execute command : {}').format(params))
                        else:
                            if data['status'] != 'OK':
                                print(_('Domoticz status not OK for {} command: {}').format('level',str(idx)))
                else:
                    print(_('Nothing to do now'))
            else:
                print(_('Typecmd not managed here (execute / schedule the cmd) : {}').format(typecmd))
        else:
            print(_('we schedule from start to end'))
            # we schedule from start to end, end at first
            if typecmd == 'switch' or typecmd == 'rgb' or typecmd == 'level' or typecmd == 'push':
                # end only if scope <> 0
                if int(scope) != 0:            
                    # end at first
                    if genTimer(end,endcmd,idx,level,hue,color,atwork):
                        if '**stop**' not in params:
                            if not exeDomoticz(params):
                                print(_('Error to execute add timer for end: {}').format(end.strftime("%Y%m%d %H%M")))
                            else:
                                if data['status'] != 'OK':
                                    print(_('Error to create timer for end : {}').format(end.strftime("%Y%m%d %H%M")))
                        else:
                            print(_('Nothing to do for this schedule: {}').format(str(end)))
                    else:
                        print(_('Error to create add timer for end: {}').format(end.strftime("%Y%m%d %H%M")))
                else:
                    print(_('End schedule not created, scope = {}').format(str(scope)))
                # gen start 
                if genTimer(start,cmd,idx,level,hue,color,atwork):
                    if '**stop**' not in params:
                        if not exeDomoticz(params):
                            print(_('Error to execute add timer for start: {}').format(start.strftime("%Y%m%d %H%M")))
                        else:
                            if data['status'] != 'OK':
                                print(_('Error to create timer for start : {}').format(start.strftime("%Y%m%d %H%M")))
                    else:
                            print(_('Nothing to do for this schedule: {}').format(str(start)))
                else:
                    print(_('Error to create add timer for start: {}').format(start.strftime("%Y%m%d %H%M")))
            else:
                print(_('Typecmd not managed here (we schedule from start to end) : {}').format(typecmd))
    else:
        print(_('Unknown command type : {}').format(typecmd))

    return

# generate schedules to devices, only fixed date/time (type 5)
#/json.htm?active=true&command=0&date=05/11/2018&days=0&hour=0&hue=0&idx=1054&level=100&min=0&param=addtimer&randomness=false&timertype=5&type=command
#/json.htm?active=true&color={"m":3,"t":0,"r":255,"g":26,"b":20,"cw":0,"ww":0}&command=0&date=2018-05-12&days=0&hour=13&idx=1054&level=100&min=58\
#&param=addtimer&randomness=false&timertype=5&type=command
def genTimer(datecmd,cmd,idx,level,hue,color,atwork):
    global params, lastonatwork, modatwork

    day = str(datecmd.strftime("%Y-%m-%d"))
    hour = datecmd.strftime("%H")
    min = datecmd.strftime("%M")
    newsched = True
    actualdata = ''
    olddata = ''
    ndx = 0

    if atwork:
        # if the cmd is Off and the date we want to schedule is bigger or equal than the last On, nothing to do
        if cmd == 1: 
            if datecmd.strftime("%Y-%m-%d %H:%M:00") >= lastonatwork.strftime("%Y-%m-%d %H:%M:00"):
                newsched = False
            modatwork += 1
        elif cmd == 0:
            if datecmd.strftime("%Y-%m-%d %H:%M:00") <= lastonatwork.strftime("%Y-%m-%d %H:%M:00"):                
                lastonatwork = datecmd
            modatwork -= 1
    else:
        # search if timer exist only if we do not manage atwork    
        for ndx in schedules:        
            if str(schedules[ndx]['DeviceRowID']) == str(idx):            
                if str(schedules[ndx]['ScheduleDate']) == str(datecmd.strftime("%Y-%m-%d %H:%M:00")) and str(schedules[ndx]['TimerType']) == '5':
                    newsched = False
                    break
    
    # if timer does not exist we create new one else we need to update it except for atwork ( param=updatetimer&idx=timerID )
    if newsched:
        nidx = idx
        nparam = 'addtimer'        
    else:
        if not atwork:
            # idx need to be TimerID (ndx)
            nidx = ndx
            nparam = 'updatetimer'
            # used to test if we will do same thing
            actualdata = str(idx) + day + hour + ':'+ min +str(cmd) +str(color)
            if infolevel > 1:
                print('actual : ' + actualdata)
            olddata = str(schedules[ndx]['DeviceRowID']) + str(schedules[ndx]['Date']) + str(schedules[ndx]['Time']) + str(schedules[ndx]['TimerCmd']) + str(schedules[ndx]['Color'])
            if infolevel > 1:
                print('old    : ' + olddata)

    # we create new one or update existing one only if not same data
    if newsched or actualdata != olddata:
        params =    {
                    'type':'command',
                    'param':''+nparam+'',
                    'idx':'' + str(nidx) + '',
                    'active':'true',
                    'timertype':'5',
                    'date':''+day+'',
                    'hour':''+hour+'',
                    'min':''+min+'',
                    'randomness':'false',
                    'command':''+ str(cmd) + '',
                    'days':'0',
                    'level':''+ str(level) +'', 
                    'color':''+str(color)+''
                    }
    else:
        params = {'**stop**'}

    return params

# Create devices dict from Domoticz by name
# if name not unique this can made trouble
#/json.htm?type=devices&filter=all&used=true&order=Name
def devDomoticz():
    global devices

    params = {'type':'devices','filter':'all','used':'true', 'order':'Name'}
    if exeDomoticz(params):
        if data['status'] == 'OK':
            result=data['result']
            for item in result:
                name = item['Name'].lower()
                devices[name] = item
        else:
            print(_('Domoticz do not send OK message for: {} ??').format('devices'))
    else:
        print(_('Error retreive dict data from Domoticz : {}').format('devices'))

    return

# Crate uservariables dict from Domoticz
#json.htm?type=command&param=getuservariables
def varDomoticz():
    global domvars, allowedcmd

    domvars = {}
    params = {'type':'command','param':'getuservariables'}
    if exeDomoticz(params):
       if data['status'] == 'OK':
            if 'result' in data:
                result=data['result']
                for item in result:
                    var = item['Name']
                    domvars[var] = item
       else:
            print(_('Domoticz do not send OK message for: {} ??').format('variables'))
    else:
        print(_('Error retreive dict data from Domoticz : {}').format('uservariables'))
        return False

    name = str(hwid) + '|iCal|' + 'cmd'
    if name in domvars:
        allowedcmd = domvars[name]['Value']
        allowedcmd = allowedcmd.lower()
        allowedcmd = allowedcmd.split(',')    
        print(allowedcmd)
    else:
        print(_('No uservariable : {}').format(name))

    return True

# Create schedules dict from Domoticz
#/json.htm?type=schedules&filter=device
def schDomoticz():
    global schedules    

    params = {'type':'schedules','filter':'device'}
    if exeDomoticz(params):
        if data['status'] == 'OK':
            result=data['result']
            for item in result:
                timerid = item['TimerID']
                schedules[timerid] = item
        else:
            print(_('Domoticz do not send OK message for: {} ??').format('timers'))
    else:
        print(_('Error retreive dict data from Domoticz : {}').format('timers'))

    return

# execute json request to Domoticz
def exeDomoticz(params):
    global data

    try:
        params = urllib.parse.urlencode(params,doseq=True)
        html=urllib.request.urlopen('http://'+domip +':'+ domport + '/json.htm?'+ params, timeout=5)        
        Response=html.read()  
        encoding = html.info().get_content_charset('utf-8')
        data=json.loads(Response.decode(encoding))
        print(_('Request Domoticz to : {} used encoding is : {}').format(str(params),str(encoding)))
    except:
        genError('exeDomoticz',_('Error sending command to Domoticz : {}').format(str(params)))
        return False

    return True

# we load AtWork sched in dict for sorting
def mgrWork(startdt,enddt):
    global atworkdict

    if atworkdevicename:
        print(_('we manage AtWork switch : {}').format(atworkdevicename))
        key = enddt.strftime("%Y%m%d %H%M") + '-' + startdt.strftime("%Y%m%d %H%M")
        atworkdict[key] = {'enddt':enddt,'startdt':startdt}
    else:
        print(_('We do not find atwork device'))
        if infolevel > 1:
            sendStatus('mgrWork',_('We do not find atwork device'))

    return

# we execute all tasks for atwork switch after we have parsed iCal file
def genWork():

    oldsched = False
    description = ''
    sortedkey = []
    idx = devices[atworkdevicename]['idx']

    print("-----------------atWrk--------------------------")

    if atworkdict:
        # we remove first all schedules before create /json.htm?type=command&param=cleartimers&idx=DeviceRowID
        params = {'type':'command','param':'cleartimers','idx':'' + str(idx)}
        if not exeDomoticz(params):
            print(_('Error to remove timers from atwork'))
            if infolevel > 1:
                sendStatus('genWork',_('Error to remove timers from atwork'))
        else:
            # we generate  cmd for atwork
            description = '#cmd#' + atworkdevicename + ':switch:On'
            # we sort the dict from bigger to smaller
            sortedkey = sorted(atworkdict, reverse=True)
            for key in range(len(sortedkey)):            
                # we read the dict in sorted order and execute cmd
                progCmd(description, atworkdict[sortedkey[key]]['startdt'],atworkdict[sortedkey[key]]['enddt'])
                # if start date <= now we stop
                if atworkdict[sortedkey[key]]['startdt'].strftime("%Y%m%d %H%M") <= today.strftime("%Y%m%d %H%M"):
                    break
    else:
        # we look at old timers to see if we need to remove them
        # test implemented cause we have all in memory, so we can avoid not necessary db query
        # search if any timer exist
        for ndx in schedules:        
            if str(schedules[ndx]['DeviceRowID']) == str(idx):                    
                oldsched =True
                break
        if oldsched:
            # we remove existing schedules  /json.htm?type=command&param=cleartimers&idx=DeviceRowID
            params = {'type':'command','param':'cleartimers','idx':'' + str(idx)}
            if not exeDomoticz(params):
                print(_('Error to remove timers from atwork'))
                if infolevel > 1:
                    sendStatus('genWork',_('Error to remove timers from atwork')) 

    # we put device Off 
    if infolevel > 1:
        print('laston : ' + lastonatwork.strftime("%Y%m%d %H%M") +' today : ' +today.strftime("%Y%m%d %H%M") +' modatwork : '+str(modatwork )) 

    if (lastonatwork.strftime("%Y%m%d %H%M") > today.strftime("%Y%m%d %H%M")) and (modatwork == 0): 
        if devices[atworkdevicename]['Status'] != 'Off':
            params = {'type':'command','param':'switchlight','idx':''+str(idx)+'','switchcmd':'Off','level':'0','passcode':''}
            if not exeDomoticz(params):
                print(_('Error to execute command : {}').format(params))
            else:
                if data['status'] != 'OK':
                    print(_('Domoticz status not OK for {} command: {}').format('switch',str(idx)))

    if infolevel > 1:
        sendStatus('genWork',_('End of : {}').format('at work'))
    print("-----------------End atWrk----------------------")

    return


# retreive ics file from Web or local (others)
def getiCal():

    print (ifile)

    # we made a copy of the file first
    if os.path.exists(ifile) and os.path.getsize(ifile) > 0:
        if os.path.exists(ifile+'.bkp'):
            os.remove(ifile+'.bkp')
            os.rename(ifile, ifile+'.bkp')
        else:
            os.rename(ifile, ifile+'.bkp')

    # generate new one
    if url.startswith('http'):
        print(_('web process to generate iCal.ics file'))
        try:
            icalf = requests.get(url)  
            with open(ifile, 'wb') as f:
                f.write(icalf.content)
        except:
            genError('getiCal',_('Error to save iCal.ics'))
            return False
    else:
        print(_('shell process to generate iCal.ics file'))
        # launch the cmd
        try:
            subprocess.check_call(url, shell=True, timeout=2)
        except subprocess.CalledProcessError as e:
            print(_('ERROR to start subprocess'))
            print(str(e.returncode))
            print(str(e.cmd))
            print(str(e.output))
            return False

    if infolevel > 1:
        print(_('command to execute : {}').format(url))

    return True

# Create list for occcurence (rrule)   
def getRecurrences(rulename, start, today, addtonow, excludedate):    
    """ Find all reoccuring events """

    datetomanage = []
    print(_('Rule name  : {}').format(rulename))
    print(_('Start date : {}').format(start))
    print(_('Today      : {}').format(today))
    print(_('Today + xxx: {}').format(addtonow))

    rules = rruleset()
    first_rule = rrulestr(rulename, dtstart=start)    
    rules.rrule(first_rule)

    print(_('First date : {}').format(rules[0]))
      
    for items in excludedate:
        try:
            rules.exdate(items)
            print(_('Date to exclude : {}').format(items))
        except AttributeError:
            pass

    for d in rules.between(today, addtonow):
          datetomanage.append(d)

    return datetomanage
#
# test implemented to manage 'All day' check in calendar, in this way, time is nul
# convert to TZ
def convDate(cdate):
    try:
        if (cdate.time()):
            cdate=cdate.astimezone(TZ)
    except:
        cdate=datetime.combine(cdate, datetime.min.time())
        cdate=TZ.localize(cdate)
        cdate=cdate.astimezone(TZ)
        pass

    return cdate
#
# Process ics file, we parse all events. 
# Need to convert TZ as we consider all is on UTC: if not the case need to be adapted
def processiCal():    
    global TZ, today

    if os.path.exists(ifile):  
        icalfile = open(ifile, 'rb')
    else:
        genError('processiCal',_('iCal file do not exist : {}').format(os.path.basename(ifile)))
        return

    gcal = icalendar.Calendar.from_ical(icalfile.read())
    today = datetime.now()    

    #Try to get TZ
    tz=gcal.get('X-WR-TIMEZONE')
    if tz:
        print(_('TimeZone from X-WR-TIMEZONE : {}').format(tz))
    else:
        tz=domvars[str(hwid) + '|iCal|' + 'tz']['Value']
        print(_('TimeZone from Uservariables : {}').format(tz))

    TZ=pytz.timezone(tz)
    today=TZ.localize(today)
    today=today.astimezone(TZ) 

    # Read all events
    print("-----------------iCal---------------------------")
    for component in gcal.walk():
        if component.name == "VTIMEZONE" and not tz:
            TZ=component.get('TZID')
            print(_('TimeZone from TZID : {}').format(TZ))
        elif component.name == "VEVENT":
            datetomanage = [] 
            summary = component.get('summary')
            description = component.get('description')
            # Outlook fix for description in case nothing on it
            if description is None:
                description = ''
            #retreive start & end date
            startdt = component.get('dtstart').dt
            enddt = component.get('dtend').dt
            #some work on date
            startdt = convDate(startdt)
            enddt   = convDate(enddt)
            # dates to exclude
            exdate = component.get('exdate')
            # event duration
            delta = enddt - startdt
            # test if some rrule date has been modified manually
            recurrence = component.get('recurrence-id')
            if recurrence:
                print('**************')
                print(_('WARNING : occurence has been modified, result could be unpredictable'))
                print(startdt, enddt)
                print('**************')
            # manage rrule
            if component.get('rrule'):
                """
                Manage rules
                """
                # create date list to exclude (if any)
                excludedate  = []
                if exdate:
                    if isinstance(exdate,list):
                        for items in exdate:
                            for edate in items.dts:
                                edate.dt = convDate(edate.dt)
                                excludedate.append(edate.dt)
                    else:                            
                        excludedate.append(exdate.dts[0].dt)
                # we manage only occurence from today to today + 90 days
                addtonow = today + timedelta(days=90)
                # obtain rule name and generate managed date list
                rulename = component.get('rrule').to_ical().decode('utf-8')
                datetomanage=getRecurrences(rulename, startdt, today, addtonow, excludedate)
                # create list from received occurence
                datetomanage_calc = []
                for items in datetomanage:
                    """
                    Create end dates from startdt
                    """
                    enddatedate = items + delta
                    datetomanage_calc.append({'startdt':items ,'enddt':enddatedate })
                datetomanage = datetomanage_calc                
            else:
                # no rrule
                datetomanage = [{'startdt':startdt ,'enddt':enddt }]
            #
            # test if startdate < enddate  (-1): can occur from rrule
            if len(datetomanage) > 1:
                if datetomanage[1]['startdt'] < datetomanage[0]['enddt']:
                    print(_('WARNING :  start date overlap end date, result unpredictable'))
            #
            # Main loop for dates
            for items in datetomanage:

                startdt = items['startdt']
                enddt   = items['enddt']

                # we do something only if date-time > today (#wrk# need to be the last if,  due to defaultToBlank)
                # if begin with '###' we bypass
                # for #hol# this need to be full day
                if (enddt.strftime("%Y%m%d %H%M") > today.strftime("%Y%m%d %H%M")) and not (description.startswith('###')):

                    if description.startswith('#cmd#'):
                        print(_('Command detected : {} ').format(description))
                        progCmd(description, startdt, enddt)

                    elif (description.startswith('#hol#')) and (hwid1 !=0 or valuedevice == 999):
                        print(_('Holidays detected : {} ').format(description))
                        addHolidays(summary,startdt,enddt)

                    elif ((description.startswith('#wrk#')) or (defaultToBlank == 'Yes')) and (hwid3 !=0 or valuedevice == 999):
                        print(_('Atwork detected : {}  and defaultToBlank is: {}').format(description,defaultToBlank))
                        mgrWork(startdt,enddt)                   

    print("-----------------End iCal-----------------------")
    icalfile.close()

    return

# we compare old and new ical file to see if need to do something
# in predicate we put the filter, line that contains time stamp
#
def predicate(line):
    ''' you can add other general checks in here '''
    if line.startswith('DTSTAMP'):
        return False # ignore it
    return True

def diffCal():

    try:
        with open(ifile) as f1, open(ifile+'.bkp') as f2:
            f1 = filter(predicate, f1)
            f2 = filter(predicate, f2)
            if (all(x == y for x, y in zip(f1, f2))):
                return False
            else:
                return True
    except:
        genError('diffCal',_('Error in diff iCal, first time execution this can be normal, we continue anyway'))        
        return False

    return True

# find device name
def findName(hwid,unit):

    Name = ''
    for key,val in devices.items():        
        if 'HardwareID' in val:
            if  str(val['HardwareID'] )== str(hwid) and str(val['Unit']) == str(unit):
                Name=key
                break

    return Name

# retreive json data from url
def queryData(url):

    data = {}    
    try:
        req=urllib.request.Request(url,headers=\
        {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'})
        html=urllib.request.urlopen(req, timeout=5)
        Response=html.read()  
        encoding = html.info().get_content_charset('utf-8')
        data=json.loads(Response.decode(encoding))        
    except:
        genError('queryData',_('Error to execute query'))
        return False

    return data
#
# main logic
#
if __name__ == '__main__':
    print("-----------------Main---------------------------")
    #
    #init uservariables    
    if not varDomoticz():
        genError('main',_('error to generate uservariables dict'))
        sys.exit('fatal error')
    #
    #we load language if it's there
    if (str(hwid) + '|iCal|' + 'country') in domvars and langto != 'en':
        langto=domvars[str(hwid) + '|iCal|' + 'country']['Value']
        loadLang()
    # if variable not exist, this will create it    
    initVar()
    #we re load uservariables in case of
    if testvar != varnumber:
        if not varDomoticz():
            genError('main',_('error to generate uservariables dict'))
            sys.exit('fatal error')
    #do the translation
    if langto != 'en':
        try:
            langto=domvars[str(hwid) + '|iCal|' + 'country']['Value']
            filetoload = folder +'en_' + langto + '.lng'
            if not os.path.exists(filetoload):        
                # load en_en.lng file to translate and translate to langto
                loadTexttotranslate()
                # we save the translation to file for futur use & avoid http call
                creLang()
                # init lang dict
                loadLang()
            else:
                print(_('we re-use existing file : {}').format(filetoload))
        except: 
            genError('main',_('error in translation'))
            pass
    # init lang dict
    if not lang_xx:
        loadLang()
    #
    if sys.platform.startswith('win32'):
        print(_('we work on windows'))
    else:
        print(_('we do not work on windows'))
    #
    if valuedevice > 0:
        # we have translation, we say domoticz to create plugin devices if not there
        if valuedevice == 999:
            creDev()
        # init holidays   
        if hwid1 !=0 or valuedevice == 999:
            initHolidays()
        # we create dict for schedules/timers
        schDomoticz()
        # we create dict for all devices
        devDomoticz() 
        # find name of atwork device
        if valuedevice == 3 or valuedevice > 777:             
            atworkdevicename=findName(hwid,3)
            print(_('Device name for Atwork : {}').format(atworkdevicename))
        if valuedevice < 5 or valuedevice > 777:             
            # create ics file & parse ics file
            if getiCal():
                if diffCal() or (valuedevice == 1) or (valuedevice > 777):      
                    processiCal()
                    # test if some work to do for atwork
                    if atworkdevicename:
                        genWork()
                else:
                    print(_('Nothing new in iCal'))
                    if infolevel > 1:
                        sendStatus('main',_('Nothing new in iCal'))
            else:
                print(_('No iCal file'))
                if infolevel > 1:
                    sendStatus('main',_('No iCal file'))
        # generate holidays
        if (valuedevice == 1) or (valuedevice > 777 and hwid1 != 0) or (valuedevice==999):
            print("-----------------Holidays-----------------------")
            # create data for holidays selector switch
            genHolidays()
            # send data to plugin.py
            send_data(str(data))
            print(_('we send holidays data'))
            print("-----------------End Holidays-------------------")
    else:
        print(_('nothing to do for valuedevice : ' + str(valuedevice)))

    if infolevel > 1:
        sendStatus('main',_('End of : {}').format('main procedure'))

    print("-----------------End Main-----------------------")