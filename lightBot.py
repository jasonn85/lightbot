from rtmbot.core import Plugin
from phue import Bridge
import time
import re
import random
from webcolors import name_to_rgb

outputs = []

zingleXY = [0.1576, 0.2368]
darkXY = [0.139, 0.081]

# Which lights should be targeted if no light specifying parameter is provided?
allLights = [0]

class LightBot(Plugin):

    allowedLightControlChannelIDs = []
    allowedLightControlUserIDs = []

    looping = False

    def __init__(self, name=None, slack_client=None, plugin_config=None):
        super( LightBot, self ).__init__(name=name, slack_client=slack_client, plugin_config=plugin_config)

        bridgeAddress = plugin_config.get('HUE_BRIDGE_ADDRESS', None)

        self.allowedLightControlChannelIDs = plugin_config.get('CHANNELS')
        self.allowedLightControlUserIDs = plugin_config.get('USERS')
        self.wootricBotID = plugin_config.get('WOOTRIC_BOT')

        if not bridgeAddress:
            raise ValueError("Please add HUE_BRIDGE_ADDRESS under LightBot in your config file.")

        self.bridge = Bridge(bridgeAddress)
        self.bridge.connect()

        if self.debug:
            print self.bridge.get_api()

    def process_message(self, data): 

        print data

        isWootricBot = 'subtype' in data and data['subtype'] == 'bot_message' and 'bot_id' in data and data['bot_id'] == self.wootricBotID
        userImpersonatingBot = self.debug and 'user' in data and data['user'] in self.allowedLightControlUserIDs

        lightControlRegex = r"(?i)^lights?\s+(\w+.*)$"

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

        pattern = re.compile(r"(?i)^((\d+\s+)+)?([\w]+[\s\w.]*%?)$")
        match = pattern.match(args)

        try:
            targetLights = match.group(1).split()
        except:
            targetLights = allLights

        command = match.group(3)

        if command.lower() == 'test':
            self.statusChangeTest(targetLights)
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

        if command.lower() == 'loop start':
            self.startColorLoop(targetLights)
            return
        elif command.lower() == 'loop stop':
            self.stopColorLoop(targetLights)
            return

        # Check for a color
        try:
            rgb = name_to_rgb(command)
            if rgb is not None:
                self.colorChange(rgb, targetLights)
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

    def colorChange(self, rgb, lights):
        # Some magic number witchcraft to go from rgb 255 to Philips XY from http://www.developers.meethue.com/documentation/color-conversions-rgb-xy
        red = rgb[0] / 255.0
        green = rgb[1] / 255.0
        blue = rgb[2] / 255.0

        red = ((red + 0.055) / (1.0 + 0.055)**2.4) if (red > 0.04045) else (red / 12.92)
        green = ((green + 0.055) / (1.0 + 0.055)**2.4) if (green > 0.04045) else (green / 12.92)
        blue = ((blue + 0.055) / (1.0 + 0.055)**2.4) if (blue > 0.04045) else (blue / 12.92)

        X = red * 0.664511 + green * 0.154324 + blue * 0.162028
        Y = red * 0.283881 + green * 0.668433 + blue * 0.047685
        Z = red * 0.000088 + green * 0.072310 + blue * 0.986039

        xy = [ X / (X + Y + Z), Y / (X + Y + Z) ]

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

    def statusChangeTest(self, lights):
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(light)['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state

            self.bridge.set_light(light, {'xy': darkXY, 'on': True, 'bri': 255})

        time.sleep(2.0)

        for light in lights:
            self.bridge.set_light(light, startingStatus[light])


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

    def wigwag(self):
        lights = allLights
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state

        self.stopColorLoop(lights)

        stepTime = 0.5
        transitionTime = 5

        for i in range(0,10):
            self.bridge.set_light(3, {'xy': zingleXY, 'bri': 154, 'on': True, 'transitiontime': transitionTime})
            self.bridge.set_light(5, {'xy': zingleXY, 'bri': 154, 'on': True, 'transitiontime': transitionTime})
            self.bridge.set_light(4, {'xy': darkXY, 'bri': 0,'on': True, 'transitiontime': transitionTime})
            time.sleep(stepTime)
            self.bridge.set_light(4, {'xy': zingleXY, 'bri': 154, 'on': True, 'transitiontime': transitionTime})
            self.bridge.set_light(3, {'xy': darkXY, 'bri': 0, 'on': True, 'transitiontime': transitionTime})
            self.bridge.set_light(5, {'xy': darkXY, 'bri': 0, 'on': True, 'transitiontime': transitionTime})
            time.sleep(stepTime)

        for light in lights:
            self.bridge.set_light(int(light), startingStatus[light])

    def lowRedPulse(self):
        lights = allLights
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state

        darkRedXY = [0.7,0.2986]
        pulseBri = 88
        pulseTime = 20

        self.stopColorLoop(lights)

        # Fake lights down to 0 from their current color (if they are on)
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
        lights = allLights
        startingStatus = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']
            del state['alert']

            if state is not None:
                startingStatus[light] = state


        stepTime = 0.025
        transitionTime = 1

        self.stopColorLoop(lights)

        for i in range(0,10):
            self.bridge.set_light(3, {'xy': zingleXY, 'on' : True, 'bri':255, 'transitiontime': transitionTime})
            time.sleep(stepTime)
            self.bridge.set_light(4, {'xy': zingleXY, 'on': True, 'bri': 255, 'transitiontime': transitionTime})
            time.sleep(stepTime)
            self.bridge.set_light(3, startingStatus[3])
            self.bridge.set_light(5, {'xy': zingleXY, 'on': True, 'bri':255, 'transitiontime': transitionTime})
            time.sleep(stepTime)
            self.bridge.set_light(4, startingStatus[4])
            time.sleep(stepTime)
            self.bridge.set_light(5, startingStatus[5])
            time.sleep(0.25)

        # Return to original state
        for light in lights:
            self.bridge.set_light(int(light), startingStatus[light])