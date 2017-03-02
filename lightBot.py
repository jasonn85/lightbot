import time
import re
import random
from copy import deepcopy
from json import dumps
from math import ceil

from rtmbot.core import Plugin
from phue import Bridge
from webcolors import name_to_rgb, hex_to_rgb, rgb_percent_to_rgb

outputs = []

class LightBot(Plugin):

    allowedLightControlChannelIDs = []
    allowedLightControlUserIDs = []

    # Which lights should be targeted if no light specifying parameter is provided?
    allLights = [0]

    wigwagGroups = None
    wigwagColor = [0.1576, 0.2368]
    whirlColor = [0.1576, 0.2368]
    slowPulseColor = [0.7, 0.2986]
    slowPulseLights = None  # All lights

    def __init__(self, name=None, slack_client=None, plugin_config=None):
        super( LightBot, self ).__init__(name=name, slack_client=slack_client, plugin_config=plugin_config)

        bridgeAddress = plugin_config.get('HUE_BRIDGE_ADDRESS', None)

        self.allowedLightControlChannelIDs = plugin_config.get('CHANNELS', None)
        self.allowedLightControlUserIDs = plugin_config.get('USERS', None)
        self.wootricBotID = plugin_config.get('WOOTRIC_BOT', None)
        self.wigwagColor = self.xyFromColorString(plugin_config.get('WIGWAG_COLOR', str(self.wigwagColor)))
        self.whirlColor = self.xyFromColorString(plugin_config.get('WHIRL_COLOR', str(self.whirlColor)))
        self.slowPulseColor = self.xyFromColorString(plugin_config.get('SLOW_PULSE_COLOR', str(self.slowPulseColor)))
        self.slowPulseLights = plugin_config.get('SLOW_PULSE_LIGHTS', None)

        configLights = plugin_config.get('LIGHTS', None)

        if configLights is not None:
            self.allLights = configLights

        if not bridgeAddress:
            raise ValueError("Please add HUE_BRIDGE_ADDRESS under LightBot in your config file.")

        self.bridge = Bridge(bridgeAddress)
        self.bridge.connect()

        if self.debug:
            print dumps(self.bridge.get_api())

        lightsOnBridge = self.bridge.lights

        if self.allLights == [0]:
            # The magic 0 light ID does not work for most light settings we will use
            self.allLights = []
            for light in lightsOnBridge:
                self.allLights.append(light.light_id)
        try:
            configWigWagGroups = plugin_config.get('WIGWAG_GROUPS', None)

            if len(configWigWagGroups) == 2 and len(configWigWagGroups[0]) > 0 and len(configWigWagGroups[1]):
                self.wigwagGroups = configWigWagGroups
        except:
            pass

        if self.slowPulseLights is None:
            self.slowPulseLights = self.allLights

        if self.wigwagGroups is None:
            # We do not have configuration-specified wig wag groups.  Use all odd and even lights.
            evenLights = []
            oddLights = []

            for light in lightsOnBridge:
                if light.light_id % 2 == 0:
                    evenLights.append(light.light_id)
                else:
                    oddLights.append(light.light_id)

            self.wigwagGroups = [oddLights, evenLights]

    def process_message(self, data):
        print dumps(data)

        isWootricBot = 'subtype' in data and data['subtype'] == 'bot_message' and 'bot_id' in data and data['bot_id'] == self.wootricBotID
        userImpersonatingBot = self.debug and 'user' in data and data['user'] in self.allowedLightControlUserIDs

        lightControlRegex = r"(?i)^lights?\s+(\S+.*)$"

        # Direct light control
        if self.messageAllowsLightControl(data):
            # Match any command beginning with "lights" and containing any other command(s)
            pattern = re.compile(lightControlRegex)
            match = pattern.match(data['text'])

            if match is not None:
                lightCommand = match.group(1)

                if lightCommand != None:
                    self.processLightsCommand(lightCommand, data)

        # NPS scores
        if isWootricBot or userImpersonatingBot:
            pattern = re.compile(r"New NPS rating:\s+(\d+)")

            if userImpersonatingBot:
                match = pattern.match(data['text'])
            elif isWootricBot and 'attachments' in data:
                match = pattern.match(data['attachments'][0]['text'])

            if match is not None:
                npsScore = match.group(1)

                if npsScore is not None:
                    self.processNPSScore(npsScore)

    def processLightsCommand(self, args, data=None):
        pattern = re.compile(r"(?i)^((\d+\s+)+)?([#\S]+.*%?)$")
        match = pattern.match(args)

        try:
            targetLights = match.group(1).split()
        except:
            targetLights = self.allLights

        command = match.group(3)

        if 'debug' in command.lower():
            self.handleDebugCommand(args, data)
            return

        if command.lower() == 'whirl':
            self.blueWhirl()
            return

        if command.lower() == 'wigwag':
            self.wigwag()
            return

        if command.lower() == 'pulsate':
            self.pulsate()
            return

        if command.lower() == 'on':
            self.lightsOnOrOff(True, targetLights)
            return
        elif command.lower() == 'off':
            self.lightsOnOrOff(False, targetLights)
            return

        if command.lower() == 'dance party':
            self.danceParty(targetLights)
            return

        # Check for a color
        try:
            xy = self.xyFromColorString(command)

            if xy is not None:
                self.colorChange(xy, targetLights)
                return
        except:
            pass

        # Check for brightness
        pattern = re.compile(r"(?i)^bri(ghtness)?\s+(\d+(%?|(\.\d+)?))$")
        match = pattern.match(command)

        if match is not None:
            brightness = match.group(2)

            if brightness is not None:
                self.brightnessChange(brightness, targetLights)
                return

        # Check for a scene after updating Hue API
        sceneID = self.sceneIDMatchingString(command)

        if sceneID is not None:
            self.bridge.activate_scene(0, sceneID)
            return

    def handleDebugCommand(self, command, incomingData=None):
        if command == 'debug rules':
            dataType = 'rules'
            data = self.bridge.request('GET', '/api/' + self.bridge.username + '/rules')
        elif command == 'debug schedules':
            dataType = 'schedules'
            data = self.bridge.get_schedule()
        elif command == 'debug lights':
            dataType = 'lights'
            data = self.bridge.get_light()
        elif command == 'debug sensors':
            dataType = 'sensors'
            data = self.bridge.get_sensor()
        else:
            dataType = 'bridge objects of all types'
            data = self.bridge.get_api()

        prettyDataString = dumps(data, sort_keys=True, indent=4, separators=(',',':'))

        messageAttachments = [{
            'fallback' : '%d %s:' % (len(data), dataType),
            'title' : '%d %s:' % (len(data), dataType),
            'text' : prettyDataString
        }]

        self.slack_client.api_call('chat.postMessage', as_user=True, channel=incomingData['channel'], attachments=messageAttachments, type='message')

    def sceneIDMatchingString(self, sceneName):
        name = sceneName.lower()

        for sceneID, scene in self.bridge.get_scene().iteritems():
            if scene['name'].lower() == name:
                return sceneID

        return None

    # Disables all enabled schedules for the time period specified
    def disableSchedulesForTime(self, seconds):
        if seconds < 1:
            seconds = 1

        seconds = int(ceil(seconds))
        minutes = seconds / 60
        seconds %= 60
        hours = minutes / 60
        minutes %= 60

        timeString = 'PT%02d:%02d:%02d' % (hours, minutes, seconds)

        allSchedules = self.bridge.get_schedule()

        for scheduleID, schedule in allSchedules.iteritems():
            if schedule['status'] == 'enabled':
                reenableScheduleSchedule = {
                    'name' : 'temporarilyDisableSchedule%s' % str(scheduleID),
                    'time' : timeString,
                    'command' : {
                        'method' : 'PUT', 'address' : '/api/' + self.bridge.username + '/schedules/' + str(scheduleID), 'body' : {'status' : 'enabled'}
                    }
                }

                result = self.bridge.request('PUT', '/api/' + self.bridge.username + '/schedules/' + str(scheduleID), dumps({'status' : 'disabled'}))
                self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(reenableScheduleSchedule))

                print result

    # Accepts colors in the format of a color name, XY values, RGB values, or hex RGB code.
    # Returns [X,Y] for use in the Philips Hue API.
    def xyFromColorString(self, string):
        # Our regex patterns
        hexPattern = re.compile(r"^#?(([A-Fa-f\d]{3}){1,2})$")
        xyPattern = re.compile(r"^[[({]?\s*(\d+(\.\d+)?)[,\s]+(\d+(\.\d+)?)\s*[])}]?\s*$")
        rgbIntegerPattern = re.compile(r"^[[({]?\s*(\d+)[,\s]+(\d+(\.\d+)?)[,\s]+(\d+)\s*[])}]?\s*$")
        rgbPercentPattern = re.compile(r"^[[({]?\s*(\d+)%[,\s]+(\d+)%[,\s]+(\d+)%\s*[])}]?\s*$")

        rgb = None
        xy = None

        try:
            rgb = name_to_rgb(string)
        except ValueError:
            pass

        if rgb is None:
            # No name matched
            match = hexPattern.match(string)

            if match is not None:
                try:
                    rgb = hex_to_rgb("#" + match.group(1))
                except ValueError:
                    pass
            else:
                # No name, no hex
                match = rgbPercentPattern.match(string)

                if match is not None:
                    r = int(match.group(1)) * 255 / 100
                    g = int(match.group(2)) * 255 / 100
                    b = int(match.group(3)) * 255 / 100

                else:
                    # No name, no hex, no RGB percent
                    match = rgbIntegerPattern.match(string)

                    if match is not None:
                        r = int(match.group(1))
                        g = int(match.group(2))
                        b = int(match.group(4))

                if match is not None:
                    rgb = [r, g, b]
                else:
                    # No name, no hex, no RGB percent, no RGB integers
                    match = xyPattern.match(string)

                    if match is not None:
                        xy = [float(match.group(1)), float(match.group(3))]

        if xy is None and rgb is not None:
            # We have RGB.  Convert to XY for Philips-ness.
            xy = self.rgbToXY(rgb)

        return xy

    def rgbToXY(self, rgb):
        # Some magic number witchcraft to go from rgb 255 to Philips XY
        # from http://www.developers.meethue.com/documentation/color-conversions-rgb-xy
        red = rgb[0] / 255.0
        green = rgb[1] / 255.0
        blue = rgb[2] / 255.0

        red = ((red + 0.055) / (1.0 + 0.055) ** 2.4) if (red > 0.04045) else (red / 12.92)
        green = ((green + 0.055) / (1.0 + 0.055) ** 2.4) if (green > 0.04045) else (green / 12.92)
        blue = ((blue + 0.055) / (1.0 + 0.055) ** 2.4) if (blue > 0.04045) else (blue / 12.92)

        X = red * 0.664511 + green * 0.154324 + blue * 0.162028
        Y = red * 0.283881 + green * 0.668433 + blue * 0.047685
        Z = red * 0.000088 + green * 0.072310 + blue * 0.986039

        return [X / (X + Y + Z), Y / (X + Y + Z)]

    def colorChange(self, xy, lights):
        for light in lights:
            self.bridge.set_light(int(light), {'on': True, 'xy': xy})

    def brightnessChange(self, brightness, lights):
        if '%' in brightness:
            brightness = brightness.strip('%')
            brightness = float(brightness) / 100.0
            brightness = int(brightness * 255.0)
        else:
            brightness = float(brightness)

            if brightness == 1:
                brightness = 255
            elif brightness > 0.0 and brightness < 1.0:
                brightness = int(brightness * 255)

        for light in lights:
            self.bridge.set_light(int(light), {'on': True, 'bri': brightness})

    def messageAllowsLightControl(self, data):
        # Is this person in one of our full control channels?
        if 'channel' in data and data['channel'] in self.allowedLightControlChannelIDs:
            return True
        if 'user' in data and data['user'] in self.allowedLightControlUserIDs:
            return True
        return False

    def processNPSScore(self, score):
        if score == '10':
            self.blueWhirl()
        elif score == '9':
            self.wigwag()
        elif score == '0':
            self.pulsate()

    def lightsOnOrOff(self, offOrOn, lights):
        for light in lights:
            self.bridge.set_light(int(light), {'on' : offOrOn})

    def danceParty(self, lights):
        startingStatus = {}
        flashCount = 66
        delayBetweenFlashes = 0.15
        totalDuration = flashCount * delayBetweenFlashes

        self.disableSchedulesForTime(totalDuration)

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                startingStatus[light] = self.restorableStateForLight(state)

        for i in lights:
            self.bridge.set_light(int(i), {'on': True})

        for loopIndex in range(0,flashCount):
            for i in lights:
                xy = [random.uniform(0.0, 1.0), random.uniform(0.0, 1.0)]
                self.bridge.set_light(int(i), {'bri': 250, 'xy':xy, 'transitionTime' : 0, 'alert': 'select'})

                time.sleep(delayBetweenFlashes)

        for light in lights:
            self.bridge.set_light(int(light), startingStatus[light])

    def restorableStateForLight(self, lightObject):
        state = {'bri' : lightObject['bri'], 'on' : lightObject['on']}

        if lightObject['colormode'] == 'hs':
            state['hue'] = lightObject['hue']
            state['sat'] = lightObject['sat']
        elif lightObject['colormode'] == 'ct':
            state['ct'] = lightObject['ct']
        else:
            state['xy'] = lightObject['xy']

        return state

    def wigwag(self):
        startingStatus = {}
        allWigwagLights = self.wigwagGroups[0] + self.wigwagGroups[1]
        transitionTime = 5
        inOneSecond = 'PT00:00:01'
        repeatCount = 5
        secondsBetweenPhases = 1
        everyTwoSeconds = 'R%02d/PT00:00:02' % repeatCount
        totalDuration = (repeatCount) * secondsBetweenPhases * 2
        afterItsOver = 'PT00:00:%02d' % totalDuration

        self.disableSchedulesForTime(totalDuration)

        for lightId in allWigwagLights:
            state = self.bridge.get_light(int(lightId))['state']

            if state is not None:
                startingStatus[lightId] = self.restorableStateForLight(state)

            if not state['on']:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % lightId, inOneSecond, lightId, {'on' : True})

        # Ensure all lights will be on
        for lightId in allWigwagLights:
            if not self.bridge.lights_by_id[lightId].on:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % lightId, inOneSecond, lightId, {'on' : True})

        # First phase
        for lightId in self.wigwagGroups[0]:
            self.bridge.create_schedule('wigwag-1-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColor, 'bri' : 154, 'transitiontime' : transitionTime})
        for lightId in self.wigwagGroups[1]:
            self.bridge.create_schedule('wigwag-1-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColor, 'bri' : 0, 'transitiontime' : transitionTime})

        # Delay before setting second phase
        time.sleep(secondsBetweenPhases)

        # Second phase
        for lightId in self.wigwagGroups[0]:
            self.bridge.create_schedule('wigwag-2-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColor, 'bri' : 0, 'transitiontime' : transitionTime})
        for lightId in self.wigwagGroups[1]:
            self.bridge.create_schedule('wigwag-2-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColor, 'bri' : 154, 'transitiontime' : transitionTime})

        # Restore original state
        for lightId in allWigwagLights:
            result = self.bridge.create_schedule('wigwag-3-%d' % lightId, afterItsOver, lightId, startingStatus[lightId])

            if self.debug:
                print "Setting light %d to restore state to:\n" % lightId
                print startingStatus[lightId]
                print result

        if self.debug:
            print self.bridge.get_schedule()

    def deleteAllSensorsWithNameBegining(self, namePrefix):
        allSensors = self.bridge.get_sensor()

        for sensorID, sensor in allSensors.iteritems():
            if namePrefix in sensor['name']:
                result = self.bridge.request('DELETE', '/api/' + self.bridge.username + '/sensors/' + str(sensorID))
                print result

    def deleteAllSchedulesWithNameBegining(self, namePrefix):
        allSchedules = self.bridge.request('GET', '/api/' + self.bridge.username + '/schedules')

        for scheduleID, schedule in allSchedules.iteritems():
            if namePrefix in schedule['name']:
                self.bridge.request('DELETE', '/api/' + self.bridge.username + '/schedules/' + str(scheduleID))

    def deleteAllRulesWithNameBegining(self, namePrefix):
        allRules = self.bridge.request('GET', '/api/' + self.bridge.username + '/rules')

        for ruleID, rule in allRules.iteritems():
            if namePrefix in rule['name']:
                self.bridge.request('DELETE', '/api/' + self.bridge.username + '/rules/' + str(ruleID))

    def pulsate(self):
        lights = self.allLights
        startingStatus = {}

        # More than seven lights would require multiple rules in the Bridge since we are limited to 8 actions per rule.
        # This would be relatively straight forward to solve but is not worth the effort at the moment.
        if len(lights) > 6:
            print '%d lights are specified to pulsate.  Only pulsating up to 6 is currently supported.  List will be truncated to 6.' % len(lights)
            lights = lights[:6]

        pulseBri = 88
        originalFadeDurationDeciseconds = 50
        originalFadeScheduleTime = 'PT00:00:%02d' % (originalFadeDurationDeciseconds / 10)
        halfPulseDurationDeciseconds = 20
        halfPulseScheduleTime = 'PT00:00:%02d' % (halfPulseDurationDeciseconds / 10)
        pulseCount = 5

        totalDurationSeconds = pulseCount * halfPulseDurationDeciseconds * 2 / 10
        totalDurationMinutes = totalDurationSeconds / 60
        totalDurationSeconds = totalDurationSeconds % 60
        totalDurationScheduleTime = 'PT00:%02d:%02d' % (totalDurationMinutes, totalDurationSeconds)

        self.deleteAllSensorsWithNameBegining('Pulsation')
        self.deleteAllSchedulesWithNameBegining('Pulsation')
        self.deleteAllRulesWithNameBegining('Pulsation')
        self.disableSchedulesForTime(totalDurationSeconds)

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                restorableState = self.restorableStateForLight(state)
                restorableState['transitiontime'] = 20
                startingStatus[light] = restorableState

        lightsUpState = {
            'bri' : pulseBri,
            'xy' : self.slowPulseColor,
            'transitiontime' : halfPulseDurationDeciseconds
        }

        lightsDownState = {
            'bri' : 0,
            'xy' : self.slowPulseColor,
            'transitiontime' : halfPulseDurationDeciseconds
        }

        pulsationStatusSensor = {
            'name' : 'PulsationStatusSensor',
            'uniqueid' : 'PulsationStatusSensor',
            'type' : 'CLIPGenericStatus',
            'swversion' : '1.0',
            'state' : {
                'status' : 0
            },
            'manufacturername' : 'jasonneel',
            'modelid' : 'PulsationStatusSensor'
        }

        # Create the sensors used for status (replacing it if it already exists with the same uniqueid)
        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/sensors', dumps(pulsationStatusSensor))
        statusSensorID = result[0]['success']['id']
        pulsationStateAddress = '/sensors/' + str(statusSensorID) + '/state'

        # Schedules
        goingUpSchedule = {
            'name' : 'Pulsation going up',
            'time' : halfPulseScheduleTime,
            'autodelete' : False,
            'status' : 'disabled',
            'command' : {
                'address' : '/api/' + self.bridge.username + pulsationStateAddress,
                'method' : 'PUT',
                'body' : {
                    'status' : 2
                }
            }
        }

        goingDownSchedule = {
            'name' : 'Pulsation going down',
            'time' : halfPulseScheduleTime,
            'autodelete' : False,
            'status' : 'disabled',
            'command' : {
                'address' : '/api/' + self.bridge.username + pulsationStateAddress,
                'method' : 'PUT',
                'body' : {
                    'status' : 1
                }
            }
        }

        goingUpResult = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(goingUpSchedule))
        goingUpScheduleID = goingUpResult[0]['success']['id']
        goingDownResult = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(goingDownSchedule))
        goingDownScheduleID = goingDownResult[0]['success']['id']

        # Create the two rules for going up and down
        startGoingUpRule = {
            'name' : 'Pulsation at bottom',
            'conditions' : [
                {
                    'address' : pulsationStateAddress + '/status',
                    'operator' : 'eq',
                    'value' : '1'
                },
                {
                    'address' : pulsationStateAddress + '/lastupdated',
                    'operator' : 'dx'
                }
            ],
            'actions' : [
                {
                    'address' : '/schedules/' + str(goingUpScheduleID),
                    'method' : 'PUT',
                    'body' : {'status' : 'enabled'}
                },
                {
                    'address' : '/schedules/' + str(goingDownScheduleID),
                    'method' : 'PUT',
                    'body' : {'status' : 'disabled'}
                }
            ]
        }

        startGoingDownRule = {
            'name' : 'Pulsation at top',
            'conditions' : [
                {
                    'address' : pulsationStateAddress + '/status',
                    'operator' : 'eq',
                    'value' : '2'
                },
                {
                    'address' : pulsationStateAddress + '/lastupdated',
                    'operator' : 'dx'
                }
            ],
            'actions' : [
                {
                    'address': '/schedules/' + str(goingUpScheduleID),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address': '/schedules/' + str(goingDownScheduleID),
                    'method': 'PUT',
                    'body': {'status': 'enabled'}
                }
            ]
        }

        originalLightStateRule = {
            'name': 'Pulsation restore state',
            'conditions': [
                {
                    'address': pulsationStateAddress + '/status',
                    'operator': 'eq',
                    'value': '3'
                },
                {
                    'address' : pulsationStateAddress + '/lastupdated',
                    'operator' : 'dx'
                }
            ],
            'actions': []
        }

        # Add actions to both rules to bring each light up and down as the sensor state changes
        for lightID in lights:
            lightAddress = '/lights/' + str(lightID) + '/state'
            startGoingUpRule['actions'].append({
                'address' : lightAddress,
                'method' : 'PUT',
                'body' : lightsUpState
            })
            startGoingDownRule['actions'].append({
                'address' : lightAddress,
                'method' : 'PUT',
                'body' : lightsDownState
            })
            originalLightStateRule['actions'].append({
                'address' : lightAddress,
                'method' : 'PUT',
                'body' : startingStatus[lightID]
            })

        goingUpResult = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules', dumps(startGoingUpRule))
        goingUpRuleID = goingUpResult[0]['success']['id']
        goingDownResult = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules', dumps(startGoingDownRule))
        goingDownRuleID = goingDownResult[0]['success']['id']
        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules', dumps(originalLightStateRule))

        cleanupRule = {
            'name' : 'Pulsation clean up',
            'conditions' : [
                {
                    'address': pulsationStateAddress + '/status',
                    'operator': 'eq',
                    'value': '3'
                },
                {
                    'address' : pulsationStateAddress + '/lastupdated',
                    'operator' : 'dx'
                }
            ],
            'actions' : [
                {
                    'address' : '/rules/' + str(goingUpRuleID),
                    'method' : 'PUT',
                    'body' : {'status' : 'disabled'}
                },
                {
                    'address' : '/rules/' + str(goingDownRuleID),
                    'method' : 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address' : '/schedules/' + str(goingUpScheduleID),
                    'method' : 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address' : '/schedules/' + str(goingDownScheduleID),
                    'method' : 'PUT',
                    'body': {'status': 'disabled'}
                }
            ]
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules', dumps(cleanupRule))

        # The schedule that stops the constant
        cleanupSchedule = {
            'name' : 'Pulsation clean up',
            'time' : totalDurationScheduleTime,
            'command' : {
                'address' : '/api/' + self.bridge.username + pulsationStateAddress,
                'method' : 'PUT',
                'body' : {
                    'status' : 3
                }
            }
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(cleanupSchedule))

        # First fade them all down to nothing
        lightsTotallyOff = {
            'bri' : 0,
            'transitiontime' : originalFadeDurationDeciseconds
        }
        for lightID in lights:
            light = self.bridge.lights_by_id[lightID]
            result = self.bridge.request('PUT', '/api/' + self.bridge.username + '/lights/' + str(lightID) + '/state', dumps(lightsTotallyOff))
            print result

        # Start the pulsation once that is done
        beginSchedule = {
            'name' : 'Pulsation begin',
            'time' : originalFadeScheduleTime,
            'command' : {
                'address' : '/api/' + self.bridge.username + pulsationStateAddress,
                'method' : 'PUT',
                'body' : {
                    'status' : 1
                }
            }
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(beginSchedule))

    def blueWhirl(self):
        lights = self.allLights
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                startingStatus[light] = self.restorableStateForLight(state)

        stepTime = 0.075
        timeBetweenWhirls = 0.5
        transitionTime = 1
        whirlCount = 10

        totalSeconds = ((stepTime * 4) + timeBetweenWhirls) * whirlCount
        finishedTimestamp = 'PT00:00:%02d' % totalSeconds

        self.disableSchedulesForTime(totalSeconds)

        # Return to original state after we're done
        for lightId in lights:
            self.bridge.create_schedule('restore%dAfterWhirl' % lightId, finishedTimestamp, lightId, startingStatus[lightId])

        # Build our 'off' states to go with the on state
        offStates = {}

        for lightId, status in startingStatus.iteritems():
            state = deepcopy(status)
            del state['on']
            if not status['on']:
                state['bri'] = 1

            offStates[lightId] = state

        for i in range(0,whirlCount):
            onState = {'xy': self.whirlColor, 'bri':255, 'transitiontime': transitionTime}

            if i == 0:
                # The first time through, we need to make sure we set 'on' to True if necessary
                onState['on'] = True

            self.bridge.set_light(3, onState)
            time.sleep(stepTime)
            self.bridge.set_light(4, onState)
            time.sleep(stepTime)
            self.bridge.set_light(3, offStates[3])
            self.bridge.set_light(5, onState)
            time.sleep(stepTime)
            self.bridge.set_light(4, offStates[4])
            time.sleep(stepTime)
            self.bridge.set_light(5, offStates[5])
            time.sleep(timeBetweenWhirls)
