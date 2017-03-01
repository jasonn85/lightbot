from rtmbot.core import Plugin
from phue import Bridge
import time
import re
import random
from webcolors import name_to_rgb, hex_to_rgb, rgb_percent_to_rgb
from copy import deepcopy
from json import dumps

outputs = []

zingleXY = [0.1576, 0.2368]
darkXY = [0.139, 0.081]

class LightBot(Plugin):

    allowedLightControlChannelIDs = []
    allowedLightControlUserIDs = []

    # Which lights should be targeted if no light specifying parameter is provided?
    allLights = [0]

    wigwagGroups = None
    wigwagColors = [[0.1576, 0.2368], [0.139, 0.081]]

    looping = False

    def __init__(self, name=None, slack_client=None, plugin_config=None):
        super( LightBot, self ).__init__(name=name, slack_client=slack_client, plugin_config=plugin_config)

        bridgeAddress = plugin_config.get('HUE_BRIDGE_ADDRESS', None)

        self.allowedLightControlChannelIDs = plugin_config.get('CHANNELS', None)
        self.allowedLightControlUserIDs = plugin_config.get('USERS', None)
        self.wootricBotID = plugin_config.get('WOOTRIC_BOT', None)

        configLights = plugin_config.get('LIGHTS', None)

        if configLights is not None:
            self.allLights = configLights

        if not bridgeAddress:
            raise ValueError("Please add HUE_BRIDGE_ADDRESS under LightBot in your config file.")

        self.bridge = Bridge(bridgeAddress)
        self.bridge.connect()

        if self.debug:
            print self.bridge.get_api()

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

        print data

        isWootricBot = 'subtype' in data and data['subtype'] == 'bot_message' and 'bot_id' in data and data['bot_id'] == self.wootricBotID
        userImpersonatingBot = self.debug and 'user' in data and data['user'] in self.allowedLightControlUserIDs

        lightControlRegex = r"(?i)^lights?\s+(\S+.*)$"

        # Direct light control
        if self.messageAllowsLightControl(data):
            # Match any command beginning with "lights" and containing any other command(s)
            pattern = re.compile(lightControlRegex)
            match = pattern.match(data['text'])

            if match != None:
                lightCommand = match.group(1)

                if lightCommand != None:
                    self.processLightsCommand(lightCommand)

        # NPS scores
        if isWootricBot or userImpersonatingBot:
            pattern = re.compile(r"New NPS rating:\s+(\d+)")

            if userImpersonatingBot:
                match = pattern.match(data['text'])
            elif isWootricBot and 'attachments' in data:
                match = pattern.match(data['attachments'][0]['text'])

            if match != None:
                npsScore = match.group(1)

                if npsScore != None:
                    self.processNPSScore(npsScore)

    def processLightsCommand(self, args):

        pattern = re.compile(r"(?i)^((\d+\s+)+)?([#\S]+.*%?)$")
        match = pattern.match(args)

        try:
            targetLights = match.group(1).split()
        except:
            targetLights = self.allLights

        command = match.group(3)

        if command.lower() == 'whirl':
            self.blueWhirl()

        if command.lower() == 'wigwag':
            self.wigwag()

        if command.lower() == 'on':
            self.lightsOnOrOff(True, targetLights)
            return
        elif command.lower() == 'off':
            self.lightsOnOrOff(False, targetLights)
            return

        if command.lower() == 'dance party':
            self.danceParty(targetLights)
            return

        if command.lower() == 'loop start':
            self.startColorLoop(targetLights)
            return
        elif command.lower() == 'loop stop':
            self.stopColorLoop(targetLights)
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

        if sceneID != None:
            self.bridge.activate_scene(0, sceneID)
            return

    def sceneIDMatchingString(self, sceneName):
        name = sceneName.lower()

        for id, scene in self.bridge.get_scene().iteritems():
            if scene['name'].lower() == name:
                return id

        return None

    # Disables all enabled schedules for the time period specified
    def disableSchedulesForTime(self, seconds):
        if seconds < 1:
            seconds = 1

        minutes = seconds / 60
        seconds = seconds % 60
        hours = minutes / 60
        minutes = minutes % 60

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

    # Accepts colors in the format of a color name, XY values, RGB values, or hex RGB code.  Returns [X,Y] for use in the Philips Hue API
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
        # Some magic number witchcraft to go from rgb 255 to Philips XY from http://www.developers.meethue.com/documentation/color-conversions-rgb-xy
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

    def startColorLoop(self, lights):
        for i in lights:
            self.bridge.set_light(int(i), {'effect' : 'colorloop'})

    def stopColorLoop(self, lights):
        for i in lights:
            self.bridge.set_light(int(i), {'effect' : 'none'})

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
            self.lowRedPulse()

    def lightsOnOrOff(self, offOrOn, lights):
        for light in lights:
            self.bridge.set_light(int(light), {'on' : offOrOn})

    def danceParty(self, lights):
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state

        self.stopColorLoop(lights)

        for i in lights:
            self.bridge.set_light(int(i), {'on': True})

        for loopIndex in range(0,66):
            for i in lights:
                xy = [random.uniform(0.0, 1.0), random.uniform(0.0, 1.0)]
                self.bridge.set_light(int(i), {'bri': 250, 'xy':xy, 'transitionTime' : 0, 'alert': 'select'})

                time.sleep(0.15)

        for light in lights:
            self.bridge.set_light(int(light), startingStatus[light])

    def restorableStateForLight(self, lightObject):
        state = {'bri' : lightObject['bri'], 'on' : lightObject['on'], 'colormode' : lightObject['colormode'], 'effect' : lightObject['effect']}

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
        afterItsOver = 'PT00:00:%02d' % ((repeatCount) * secondsBetweenPhases * 2)

        for lightId in allWigwagLights:
            state = self.bridge.get_light(int(lightId))['state']

            if state is not None:
                startingStatus[lightId] = self.restorableStateForLight(state)

            if not state['on']:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % lightId, inOneSecond, lightId, {'on' : True})

        self.stopColorLoop(allWigwagLights)

        # Ensure all lights will be on
        for lightId in allWigwagLights:
            if not self.bridge.lights_by_id[lightId].on:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % lightId, inOneSecond, lightId, {'on' : True})

        # First phase
        for lightId in self.wigwagGroups[0]:
            self.bridge.create_schedule('wigwag-1-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColors[0], 'bri' : 154, 'transitiontime' : transitionTime})
        for lightId in self.wigwagGroups[1]:
            self.bridge.create_schedule('wigwag-1-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColors[1], 'bri' : 0, 'transitiontime' : transitionTime})

        # Delay before setting second phase
        time.sleep(secondsBetweenPhases)

        # Second phase
        for lightId in self.wigwagGroups[0]:
            self.bridge.create_schedule('wigwag-2-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColors[1], 'bri' : 0, 'transitiontime' : transitionTime})
        for lightId in self.wigwagGroups[1]:
            self.bridge.create_schedule('wigwag-2-%d' % lightId, everyTwoSeconds, lightId, {'xy' : self.wigwagColors[0], 'bri' : 154, 'transitiontime' : transitionTime})

        # Restore original state
        for lightId in allWigwagLights:
            result = self.bridge.create_schedule('wigwag-3-%d' % lightId, afterItsOver, lightId, startingStatus[lightId])

            if self.debug:
                print "Setting light %d to restore state to:\n" % lightId
                print startingStatus[lightId]
                print result

        if self.debug:
            print self.bridge.get_schedule()

    def lowRedPulse(self):
        lights = self.allLights
        startingStatus = {}

        if lights == [0]:
            # This is the magical 0 light ID, meaning all lights.  Record all lights
            lights = []
            for light in self.bridge.lights:
                lights.append(light.light_id)

        for light in lights:
            state = self.bridge.get_light(int(light))['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state

        darkRedXY = [0.7,0.2986]
        pulseBri = 88
        pulseTime = 20

        self.stopColorLoop(lights)

        # Fade lights down to 0 from their current color (if they are on)
        for light in lights:
            self.bridge.set_light(int(light), {'bri': 0, 'transitiontime': pulseTime})

        time.sleep(2.0)

        for i in range(0,5):

            for light in lights:
                self.bridge.set_light(int(light), {'bri': pulseBri, 'xy': darkRedXY, 'on': True, 'transitiontime': pulseTime})
            time.sleep(2.0)

            for light in lights:
                self.bridge.set_light(int(light), {'bri': 0, 'transitiontime': pulseTime})
            time.sleep(2.0)

        # Return to original state
        for light in lights:
            self.bridge.set_light(int(light), startingStatus[light])

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

        self.stopColorLoop(lights)

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
            onState = {'xy': zingleXY, 'bri':255, 'transitiontime': transitionTime}

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

