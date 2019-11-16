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
<plugin key="ics-calendar-plugin" name="Calendar (ICS) plugin for Domoticz" author="msalles" version="1.0.0" wikilink="" externallink="">
    <description>
        <h2>An ICS calendar plugin for Domoticz</h2><br/>
        <h3>Features</h3>
        <ul style="list-style-type:square">
            <li></li>
        </ul>
    </description>
    <params>
        <param field="Mode1" label="#1 personnal ICS link" width="300px" required="true" default=""/>
        <param field="Mode2" label="#2 personnal ICS link" width="300px" required="false" default=""/>
        <param field="Mode3" label="#1 professional ICS link" width="300px" required="false" default=""/>
        <param field="Mode4" label="#2 professional ICS link" width="300px" required="false" default=""/>
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
import datetime
import arrow
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
import ics
import sys
import os

def query_data(url):
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

def get_and_parse_cal (icsUrl, isPro):
    # Create Calendar from file :
    from urllib.request import urlopen 
    cal_content = urlopen(icsUrl).read().decode()
    print(cal_content)
    c = ics.Calendar(cal_content)
    now_events = c.timeline.now()
    now_doing = len(list(now_events)) > 0
    # is_now = False
    next_event = next(c.timeline.start_after(arrow.now()), None)
    return {
        "doing": list(c.timeline.now()),
        "at_work": isPro and now_doing,
        "lst_events_today": list(c.timeline.today(arrow.now())),
        "next_event": next_event
    }


def get_pluie (codeville):
    try:
        # request data from meteofrance 
        url = 'http://www.meteofrance.com/mf3-rpc-portlet/rest/pluie/' + codeville
        data=query_data(url)
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
        level = 0
        if (pluie.find('ions fortes') > -1):
            level = 4
        elif (pluie.find('ions mod') > -1):
            level = 3
        elif (pluie.find('ions faibles') > -1):
            level = 1
        else:
            level = 0

    return { "level": level, "text": pluie }

class BasePlugin:

    def onStart(self):
        Domoticz.Heartbeat(300)

        if Parameters["Mode6"] != "Normal":
            Domoticz.Debugging(1)

        if ('ICal'  not in Images): Domoticz.Image('ICal Icons.zip').Create()

        if (len(Devices) == 0):
            Domoticz.Device(Name="Will it rain ?",  Unit=1, TypeName="Alert", Used=1).Create()
            Domoticz.Device(Name="at_work",  Unit=2, TypeName="Switch", Used= 1).Create()
            Domoticz.Device(Name="Todo Today",  Unit=3, TypeName="Text", Used= 1).Create()
            Domoticz.Device(Name="Next event to come",  Unit=4, TypeName="Text", Used= 1).Create()

            logDebugMessage("Devices created.")

        return True


    def onCommand(self, Unit, Command, Level, Color):        
        return True

    def onHeartbeat(self):

        # Pluie :
        pluie = get_pluie('143100')
        Devices[1].Update(pluie['level'], pluie['text'])

        infos1 = { "doing": None, "at_work": False, "lst_events_today": [], "next_event": None } 
        infos2 = { "doing": None, "at_work": False, "lst_events_today": [], "next_event": None } 
        infos3 = { "doing": None, "at_work": False, "lst_events_today": [], "next_event": None } 
        infos4 = { "doing": None, "at_work": False, "lst_events_today": [], "next_event": None } 

        if (Parameters["Mode1"]):
            infos1 = get_and_parse_cal(Parameters["Mode1"], False)
        if (Parameters["Mode2"]):
            infos2 = get_and_parse_cal(Parameters["Mode2"], False)
        if (Parameters["Mode3"]):
            infos3 = get_and_parse_cal(Parameters["Mode3"], True)
        if (Parameters["Mode4"]):
            infos4 = get_and_parse_cal(Parameters["Mode4"], True)

        at_work = 1 if infos1['at_work'] or infos2['at_work'] or infos3['at_work'] or infos4['at_work'] else 0
        Devices[2].Update(at_work, str(at_work))

        todo = ""
        for event in infos1['lst_events_today']:
            todo += event.name + "\n"
        for event in infos2['lst_events_today']:
            todo += event.name + "\n"
        for event in infos3['lst_events_today']:
            todo += event.name + "\n"
        for event in infos4['lst_events_today']:
            todo += event.name + "\n"

        Devices[3].Update(0, str(todo))

        # Next event :
        val = ""
        if (infos1['next_event'] is not None):
            val = infos1['next_event'].name + "\n" + infos1['next_event'].description
        Devices[4].Update(0, str(val))



        return True

    def logErrorCode(self, jsonObject):
        return

    def onStop(self):
        logDebugMessage("onStop called")
        return True

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onDisconnect(Connection):
    global _plugin
    _plugin.onDisconnect(Connection)

def onCommand(Unit, Command, Level, Color):
    global _plugin
    _plugin.onCommand(Unit, Command, Level, Color)

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

def logDebugMessage(message):
    if (Parameters["Mode6"] == "Debug"):
        now = datetime.datetime.now()
        f = open(Parameters["HomeFolder"] + "ical-plugin.log", "a")
        f.write("DEBUG - " + now.isoformat() + " - " + message + "\r\n")
        f.close()
    Domoticz.Debug(message)

def logErrorMessage(message):
    if (Parameters["Mode6"] == "Debug"):
        now = datetime.datetime.now()
        f = open(Parameters["HomeFolder"] + "ical-plugin.log", "a")
        f.write("ERROR - " + now.isoformat() + " - " + message + "\r\n")
        f.close()
    Domoticz.Error(message)
