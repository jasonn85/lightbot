import time
import re
import random
from copy import deepcopy
from json import dumps
from math import ceil

from rtmbot.core import Plugin
from phue import Bridge
from webcolors import name_to_rgb, hex_to_rgb, rgb_percent_to_rgb

DEFAULT_WIGWAG_COLOR = [0.1576, 0.2368]
DEFAULT_WHIRL_COLOR = [0.1576, 0.2368]
DEFAULT_SLOW_PULSE_COLOR = [0.7, 0.2986]

outputs = []


class LightBot(Plugin):
    allowed_light_control_channel_i_ds = []
    allowed_light_control_user_i_ds = []

    # Which lights should be targeted if no light specifying parameter is provided?
    all_lights = [0]

    def __init__(self, name=None, slack_client=None, plugin_config=None):
        super(LightBot, self).__init__(name=name, slack_client=slack_client, plugin_config=plugin_config)

        bridge_address = plugin_config.get('HUE_BRIDGE_ADDRESS', None)

        self.allowed_light_control_channel_ids = plugin_config.get('CHANNELS', None)
        self.allowed_light_control_user_ids = plugin_config.get('USERS', None)
        self.wootric_bot_id = plugin_config.get('WOOTRIC_BOT', None)
        self.wigwag_color = self.xy_from_color_string(plugin_config.get('WIGWAG_COLOR', str(DEFAULT_WIGWAG_COLOR)))
        self.whirl_color = self.xy_from_color_string(plugin_config.get('WHIRL_COLOR', str(DEFAULT_WHIRL_COLOR)))
        self.slow_pulse_color = self.xy_from_color_string(
            plugin_config.get('SLOW_PULSE_COLOR', str(DEFAULT_SLOW_PULSE_COLOR)))
        self.slow_pulse_lights = plugin_config.get('SLOW_PULSE_LIGHTS', None)

        config_lights = plugin_config.get('LIGHTS', None)

        if config_lights is not None:
            self.all_lights = config_lights

        if not bridge_address:
            raise ValueError("Please add HUE_BRIDGE_ADDRESS under LightBot in your config file.")

        self.bridge = Bridge(bridge_address)
        self.bridge.connect()

        if self.debug:
            print dumps(self.bridge.get_api())

        lights_on_bridge = self.bridge.lights

        if self.all_lights == [0]:
            # The magic 0 light ID does not work for most light settings we will use
            self.all_lights = []
            for light in lights_on_bridge:
                self.all_lights.append(light.light_id)

        config_wig_wag_groups = plugin_config.get('WIGWAG_GROUPS', None)
        if config_wig_wag_groups is not None and len(config_wig_wag_groups) == 2 \
                and len(config_wig_wag_groups[0]) > 0 and len(config_wig_wag_groups[1]):
            self.wigwag_groups = config_wig_wag_groups
        else:
            self.wigwag_groups = None

        if self.slow_pulse_lights is None:
            self.slow_pulse_lights = self.all_lights

        if self.wigwag_groups is None:
            # We do not have configuration-specified wig wag groups.  Use all odd and even lights.
            even_lights = []
            odd_lights = []

            for light in lights_on_bridge:
                if light.light_id % 2 == 0:
                    even_lights.append(light.light_id)
                else:
                    odd_lights.append(light.light_id)

            self.wigwag_groups = [odd_lights, even_lights]

    def process_message(self, data):
        print dumps(data)

        is_wootric_bot = ('subtype' in data and data['subtype'] == 'bot_message'
                          and 'bot_id' in data and data['bot_id'] == self.wootric_bot_id)
        user_impersonating_bot = self.debug and 'user' in data and data['user'] in self.allowed_light_control_user_ids

        light_control_regex = r"(?i)^lights?\s+(\S+.*)$"

        # Direct light control
        if self.message_allows_light_control(data):
            # Match any command beginning with "lights" and containing any other command(s)
            pattern = re.compile(light_control_regex)
            match = pattern.match(data['text'])

            if match is not None:
                light_command = match.group(1)

                if light_command is not None:
                    self.process_lights_command(light_command, data)

        # NPS scores
        if is_wootric_bot or user_impersonating_bot:
            pattern = re.compile(r"New NPS rating:\s+(\d+)")

            if user_impersonating_bot:
                match = pattern.match(data['text'])
            elif is_wootric_bot and 'attachments' in data:
                match = pattern.match(data['attachments'][0]['text'])
            else:
                match = None

            if match is not None:
                nps_score = match.group(1)

                if npsScore is not None:
                    self.process_nps_score(nps_score)

    def process_lights_command(self, args, data=None):
        pattern = re.compile(r"(?i)^((\d+\s+)+)?([#\S]+.*%?)$")
        match = pattern.match(args)

        if match is not None and match.group(1) is not None:
            target_lights = match.group(1).split()
        else:
            target_lights = self.all_lights

        command = match.group(3)

        if 'debug' in command.lower():
            self.handle_debug_command(args, data)
            return

        if command.lower() == 'whirl':
            self.blue_whirl()
            return

        if command.lower() == 'wigwag':
            self.wigwag()
            return

        if command.lower() == 'pulsate':
            self.pulsate()
            return

        if command.lower() == 'on':
            self.lights_on_or_off(True, target_lights)
            return
        elif command.lower() == 'off':
            self.lights_on_or_off(False, target_lights)
            return

        if command.lower() == 'dance party':
            self.danceParty(target_lights)
            return

        # Check for a color
        try:
            xy = self.xy_from_color_string(command)

            if xy is not None:
                self.color_change(xy, target_lights)
                return
        except ValueError:
            pass

        # Check for brightness
        pattern = re.compile(r"(?i)^bri(ghtness)?\s+(\d+(%?|(\.\d+)?))$")
        match = pattern.match(command)

        if match is not None:
            brightness = match.group(2)

            if brightness is not None:
                self.brightness_change(brightness, target_lights)
                return

        # Check for a scene after updating Hue API
        scene_id = self.scene_id_matching_string(command)

        if scene_id is not None:
            self.bridge.activate_scene(0, scene_id)
            return

    def handle_debug_command(self, command, incoming_data=None):
        if command == 'debug rules':
            data_type = 'rules'
            data = self.bridge.request('GET', '/api/' + self.bridge.username + '/rules')
        elif command == 'debug schedules':
            data_type = 'schedules'
            data = self.bridge.get_schedule()
        elif command == 'debug lights':
            data_type = 'lights'
            data = self.bridge.get_light()
        elif command == 'debug sensors':
            data_type = 'sensors'
            data = self.bridge.get_sensor()
        else:
            data_type = 'bridge objects of all types'
            data = self.bridge.get_api()

        pretty_data_string = dumps(data, sort_keys=True, indent=4, separators=(',',':'))

        message_attachments = [{
            'fallback': '%d %s:' % (len(data), data_type),
            'title': '%d %s:' % (len(data), data_type),
            'text': pretty_data_string
        }]

        self.slack_client.api_call('chat.postMessage', as_user=True, channel=incoming_data['channel'],
                                   attachments=message_attachments, type='message')

    def scene_id_matching_string(self, scene_name):
        name = scene_name.lower()

        for scene_id, scene in self.bridge.get_scene().iteritems():
            if scene['name'].lower() == name:
                return scene_id

        return None

    # Disables all enabled schedules for the time period specified
    def disable_schedules_for_time(self, seconds):
        if seconds < 1:
            seconds = 1

        seconds = int(ceil(seconds))
        minutes = seconds / 60
        seconds %= 60
        hours = minutes / 60
        minutes %= 60

        time_string = 'PT%02d:%02d:%02d' % (hours, minutes, seconds)

        all_schedules = self.bridge.get_schedule()

        for schedule_id, schedule in all_schedules.iteritems():
            if schedule['status'] == 'enabled':
                reenable_schedule_schedule = {
                    'name': 'temporarilyDisableSchedule%s' % str(schedule_id),
                    'time': time_string,
                    'command': {
                        'method': 'PUT',
                        'address': '/api/' + self.bridge.username + '/schedules/' + str(schedule_id),
                        'body': {'status': 'enabled'}
                    }
                }

                result = self.bridge.request('PUT', '/api/' + self.bridge.username + '/schedules/' + str(schedule_id),
                                             dumps({'status': 'disabled'}))
                self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules',
                                    dumps(reenable_schedule_schedule))

                print result

    # Accepts colors in the format of a color name, XY values, RGB values, or hex RGB code.
    # Returns [X,Y] for use in the Philips Hue API.
    def xy_from_color_string(self, string):
        # Our regex patterns
        hex_pattern = re.compile(r"^#?(([A-Fa-f\d]{3}){1,2})$")
        xy_pattern = re.compile(r"^[[({]?\s*(\d+(\.\d+)?)[,\s]+(\d+(\.\d+)?)\s*[])}]?\s*$")
        rgb_integer_pattern = re.compile(r"^[[({]?\s*(\d+)[,\s]+(\d+(\.\d+)?)[,\s]+(\d+)\s*[])}]?\s*$")
        rgb_percent_pattern = re.compile(r"^[[({]?\s*(\d+)%[,\s]+(\d+)%[,\s]+(\d+)%\s*[])}]?\s*$")

        rgb = None
        xy = None

        try:
            rgb = name_to_rgb(string)
        except ValueError:
            pass

        if rgb is None:
            # No name matched
            match = hex_pattern.match(string)

            if match is not None:
                try:
                    rgb = hex_to_rgb("#" + match.group(1))
                except ValueError:
                    pass
            else:
                # No name, no hex
                match = rgb_percent_pattern.match(string)
                r = None
                g = None
                b = None

                if match is not None:
                    r = int(match.group(1)) * 255 / 100
                    g = int(match.group(2)) * 255 / 100
                    b = int(match.group(3)) * 255 / 100

                else:
                    # No name, no hex, no RGB percent
                    match = rgb_integer_pattern.match(string)

                    if match is not None:
                        r = int(match.group(1))
                        g = int(match.group(2))
                        b = int(match.group(4))

                if r is not None and g is not None and b is not None:
                    rgb = [r, g, b]
                else:
                    # No name, no hex, no RGB percent, no RGB integers
                    match = xy_pattern.match(string)

                    if match is not None:
                        xy = [float(match.group(1)), float(match.group(3))]

        if xy is None and rgb is not None:
            # We have RGB.  Convert to XY for Philips-ness.
            xy = self.rgb_to_xy(rgb)

        return xy

    @staticmethod
    def rgb_to_xy(rgb):
        # Some magic number witchcraft to go from rgb 255 to Philips XY
        # from http://www.developers.meethue.com/documentation/color-conversions-rgb-xy
        red = rgb[0] / 255.0
        green = rgb[1] / 255.0
        blue = rgb[2] / 255.0

        red = ((red + 0.055) / (1.0 + 0.055) ** 2.4) if (red > 0.04045) else (red / 12.92)
        green = ((green + 0.055) / (1.0 + 0.055) ** 2.4) if (green > 0.04045) else (green / 12.92)
        blue = ((blue + 0.055) / (1.0 + 0.055) ** 2.4) if (blue > 0.04045) else (blue / 12.92)

        x = red * 0.664511 + green * 0.154324 + blue * 0.162028
        y = red * 0.283881 + green * 0.668433 + blue * 0.047685
        z = red * 0.000088 + green * 0.072310 + blue * 0.986039

        return [x / (x+y+z), y / (x+y+z)]

    def color_change(self, xy, lights):
        for light in lights:
            self.bridge.set_light(int(light), {'on': True, 'xy': xy})

    def brightness_change(self, brightness, lights):
        if '%' in brightness:
            brightness = brightness.strip('%')
            brightness = float(brightness) / 100.0
            brightness = int(brightness * 255.0)
        else:
            brightness = float(brightness)

            if brightness == 1:
                brightness = 255
            elif 0.0 < brightness < 1.0:
                brightness = int(brightness * 255)

        for light in lights:
            self.bridge.set_light(int(light), {'on': True, 'bri': brightness})

    def message_allows_light_control(self, data):
        # Is this person in one of our full control channels?
        if 'channel' in data and data['channel'] in self.allowed_light_control_channel_ids:
            return True
        if 'user' in data and data['user'] in self.allowed_light_control_user_ids:
            return True
        return False

    def process_nps_score(self, score):
        if score == '10':
            self.blue_whirl()
        elif score == '9':
            self.wigwag()
        elif score == '0':
            self.pulsate()

    def lights_on_or_off(self, off_or_on, lights):
        for light in lights:
            self.bridge.set_light(int(light), {'on': off_or_on})

    def dance_party(self, lights):
        starting_status = {}
        flash_count = 66
        delay_between_flashes = 0.15
        total_duration = flash_count * delay_between_flashes

        self.disable_schedules_for_time(total_duration)

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                starting_status[light] = self.restorable_state_for_light(state)

        for i in lights:
            self.bridge.set_light(int(i), {'on': True})

        for loop_index in range(0,flash_count):
            for i in lights:
                xy = [random.uniform(0.0, 1.0), random.uniform(0.0, 1.0)]
                self.bridge.set_light(int(i), {'bri': 250, 'xy': xy, 'transitionTime': 0, 'alert': 'select'})

                time.sleep(delay_between_flashes)

        for light in lights:
            self.bridge.set_light(int(light), starting_status[light])

    @staticmethod
    def restorable_state_for_light(light_object):
        state = {'bri': light_object['bri'], 'on': light_object['on']}

        if light_object['colormode'] == 'hs':
            state['hue'] = light_object['hue']
            state['sat'] = light_object['sat']
        elif light_object['colormode'] == 'ct':
            state['ct'] = light_object['ct']
        else:
            state['xy'] = light_object['xy']

        return state

    def wigwag(self):
        starting_status = {}
        all_wigwag_lights = self.wigwag_groups[0] + self.wigwag_groups[1]
        transition_time = 5
        in_one_second = 'PT00:00:01'
        repeat_count = 5
        seconds_between_phases = 1
        every_two_seconds = 'R%02d/PT00:00:02' % repeat_count
        total_duration = repeat_count * seconds_between_phases * 2
        after_its_over = 'PT00:00:%02d' % total_duration

        self.disable_schedules_for_time(total_duration)

        for light_id in all_wigwag_lights:
            state = self.bridge.get_light(int(light_id))['state']

            if state is not None:
                starting_status[light_id] = self.restorable_state_for_light(state)

            if not state['on']:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % light_id, in_one_second, light_id, {'on': True})

        # Ensure all lights will be on
        for light_id in all_wigwag_lights:
            if not self.bridge.lights_by_id[light_id].on:
                self.bridge.create_schedule('turn%dOnBeforeWigwag' % light_id, in_one_second, light_id, {'on': True})

        # First phase
        for light_id in self.wigwag_groups[0]:
            self.bridge.create_schedule('wigwag-1-%d' % light_id, every_two_seconds, light_id, {
                'xy': self.wigwag_color, 'bri': 154, 'transitiontime': transition_time
            })
        for light_id in self.wigwag_groups[1]:
            self.bridge.create_schedule('wigwag-1-%d' % light_id, every_two_seconds, light_id, {
                'xy': self.wigwag_color, 'bri': 0, 'transitiontime': transition_time
            })

        # Delay before setting second phase
        time.sleep(seconds_between_phases)

        # Second phase
        for light_id in self.wigwag_groups[0]:
            self.bridge.create_schedule('wigwag-2-%d' % light_id, everyTwoSeconds, light_id, {
                'xy': self.wigwag_color, 'bri': 0, 'transitiontime': transitionTime
            })
        for light_id in self.wigwag_groups[1]:
            self.bridge.create_schedule('wigwag-2-%d' % light_id, everyTwoSeconds, light_id, {
                'xy': self.wigwag_color, 'bri': 154, 'transitiontime': transitionTime
            })

        # Restore original state
        for light_id in all_wigwag_lights:
            result = self.bridge.create_schedule('wigwag-3-%d' % light_id, after_its_over, light_id,
                                                 starting_status[light_id])

            if self.debug:
                print "Setting light %d to restore state to:\n" % light_id
                print starting_status[light_id]
                print result

        if self.debug:
            print self.bridge.get_schedule()

    def delete_all_sensors_with_name_begining(self, name_prefix):
        all_sensors = self.bridge.get_sensor()

        for sensor_id, sensor in all_sensors.iteritems():
            if name_prefix in sensor['name']:
                result = self.bridge.request('DELETE', '/api/' + self.bridge.username + '/sensors/' + str(sensor_id))
                print result

    def delete_all_schedules_with_name_begining(self, name_prefix):
        all_schedules = self.bridge.request('GET', '/api/' + self.bridge.username + '/schedules')

        for schedule_id, schedule in all_schedules.iteritems():
            if name_prefix in schedule['name']:
                self.bridge.request('DELETE', '/api/' + self.bridge.username + '/schedules/' + str(schedule_id))

    def delete_all_rules_with_name_begining(self, name_prefix):
        all_rules = self.bridge.request('GET', '/api/' + self.bridge.username + '/rules')

        for rule_id, rule in all_rules.iteritems():
            if name_prefix in rule['name']:
                self.bridge.request('DELETE', '/api/' + self.bridge.username + '/rules/' + str(rule_id))

    def pulsate(self):
        lights = self.all_lights
        starting_status = {}

        # More than seven lights would require multiple rules in the Bridge since we are limited to 8 actions per rule.
        # This would be relatively straight forward to solve but is not worth the effort at the moment.
        if len(lights) > 6:
            print '%d lights are specified to pulsate.' % len(lights)\
                 + 'Only pulsating up to 6 is currently supported.' \
                 + 'List will be truncated to 6.'
            lights = lights[:6]

        pulse_bri = 88
        original_fade_duration_deciseconds = 50
        original_fade_schedule_time = 'PT00:00:%02d' % (original_fade_duration_deciseconds / 10)
        half_pulse_duration_deciseconds = 20
        half_pulse_schedule_time = 'PT00:00:%02d' % (half_pulse_duration_deciseconds / 10)
        pulse_count = 5

        total_duration_seconds = pulse_count * half_pulse_duration_deciseconds * 2 / 10
        total_duration_minutes = total_duration_seconds / 60
        total_duration_seconds %= 60
        total_duration_schedule_time = 'PT00:%02d:%02d' % (total_duration_minutes, total_duration_seconds)

        self.delete_all_sensors_with_name_begining('Pulsation')
        self.delete_all_schedules_with_name_begining('Pulsation')
        self.delete_all_rules_with_name_begining('Pulsation')
        self.disable_schedules_for_time(total_duration_seconds)

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                restorable_state = self.restorable_state_for_light(state)
                restorable_state['transitiontime'] = 20
                starting_status[light] = restorable_state

        lights_up_state = {
            'bri': pulse_bri,
            'xy': self.slow_pulse_color,
            'transitiontime': half_pulse_duration_deciseconds
        }

        lights_down_state = {
            'bri': 0,
            'xy': self.slow_pulse_color,
            'transitiontime': half_pulse_duration_deciseconds
        }

        pulsation_status_sensor = {
            'name': 'PulsationStatusSensor',
            'uniqueid': 'PulsationStatusSensor',
            'type': 'CLIPGenericStatus',
            'swversion': '1.0',
            'state': {
                'status': 0
            },
            'manufacturername': 'jasonneel',
            'modelid': 'PulsationStatusSensor'
        }

        # Create the sensors used for status (replacing it if it already exists with the same uniqueid)
        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/sensors', dumps(pulsation_status_sensor))
        status_sensor_id = result[0]['success']['id']
        pulsation_state_address = '/sensors/' + str(status_sensor_id) + '/state'

        # Schedules
        going_up_schedule = {
            'name': 'Pulsation going up',
            'time': half_pulse_schedule_time,
            'autodelete': False,
            'status': 'disabled',
            'command': {
                'address': '/api/' + self.bridge.username + pulsation_state_address,
                'method': 'PUT',
                'body': {
                    'status': 2
                }
            }
        }

        going_down_schedule = {
            'name': 'Pulsation going down',
            'time': half_pulse_schedule_time,
            'autodelete': False,
            'status': 'disabled',
            'command': {
                'address': '/api/' + self.bridge.username + pulsation_state_address,
                'method': 'PUT',
                'body': {
                    'status': 1
                }
            }
        }

        going_up_result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules',
                                              dumps(going_up_schedule))
        going_up_schedule_id = going_up_result[0]['success']['id']
        going_down_result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules',
                                                dumps(going_down_schedule))
        going_down_schedule_id = going_down_result[0]['success']['id']

        # Create the two rules for going up and down
        start_going_up_rule = {
            'name': 'Pulsation at bottom',
            'conditions': [
                {
                    'address': pulsation_state_address + '/status',
                    'operator': 'eq',
                    'value': '1'
                },
                {
                    'address': pulsation_state_address + '/lastupdated',
                    'operator': 'dx'
                }
            ],
            'actions': [
                {
                    'address': '/schedules/' + str(going_up_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'enabled'}
                },
                {
                    'address': '/schedules/' + str(going_down_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                }
            ]
        }

        start_going_down_rule = {
            'name': 'Pulsation at top',
            'conditions': [
                {
                    'address': pulsation_state_address + '/status',
                    'operator': 'eq',
                    'value': '2'
                },
                {
                    'address': pulsation_state_address + '/lastupdated',
                    'operator': 'dx'
                }
            ],
            'actions': [
                {
                    'address': '/schedules/' + str(going_up_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address': '/schedules/' + str(going_down_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'enabled'}
                }
            ]
        }

        original_light_state_rule = {
            'name': 'Pulsation restore state',
            'conditions': [
                {
                    'address': pulsation_state_address + '/status',
                    'operator': 'eq',
                    'value': '3'
                },
                {
                    'address': pulsation_state_address + '/lastupdated',
                    'operator': 'dx'
                }
            ],
            'actions': []
        }

        # Add actions to both rules to bring each light up and down as the sensor state changes
        for light_id in lights:
            light_address = '/lights/' + str(light_id) + '/state'
            start_going_up_rule['actions'].append({
                'address': light_address,
                'method': 'PUT',
                'body': lights_up_state
            })
            start_going_down_rule['actions'].append({
                'address': light_address,
                'method': 'PUT',
                'body': lights_down_state
            })
            original_light_state_rule['actions'].append({
                'address': light_address,
                'method': 'PUT',
                'body': starting_status[light_id]
            })

        going_up_result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules',
                                              dumps(start_going_up_rule))
        going_up_rule_id = going_up_result[0]['success']['id']
        going_down_result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules',
                                                dumps(start_going_down_rule))
        going_down_rule_id = going_down_result[0]['success']['id']
        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules',
                                     dumps(original_light_state_rule))

        cleanup_rule = {
            'name': 'Pulsation clean up',
            'conditions': [
                {
                    'address': pulsation_state_address + '/status',
                    'operator': 'eq',
                    'value': '3'
                },
                {
                    'address': pulsation_state_address + '/lastupdated',
                    'operator': 'dx'
                }
            ],
            'actions': [
                {
                    'address': '/rules/' + str(going_up_rule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address': '/rules/' + str(going_down_rule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address': '/schedules/' + str(going_up_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                },
                {
                    'address': '/schedules/' + str(going_down_schedule_id),
                    'method': 'PUT',
                    'body': {'status': 'disabled'}
                }
            ]
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/rules', dumps(cleanup_rule))

        # The schedule that stops the constant
        cleanup_schedule = {
            'name': 'Pulsation clean up',
            'time': total_duration_schedule_time,
            'command': {
                'address': '/api/' + self.bridge.username + pulsation_state_address,
                'method': 'PUT',
                'body': {
                    'status': 3
                }
            }
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(cleanup_schedule))

        # First fade them all down to nothing
        lights_totally_off = {
            'bri': 0,
            'transitiontime': original_fade_duration_deciseconds
        }
        for light_id in lights:
            light = self.bridge.lights_by_id[light_id]
            result = self.bridge.request('PUT', '/api/' + self.bridge.username + '/lights/' + str(light_id) + '/state',
                                         dumps(lights_totally_off))
            print result

        # Start the pulsation once that is done
        begin_schedule = {
            'name': 'Pulsation begin',
            'time': original_fade_schedule_time,
            'command': {
                'address': '/api/' + self.bridge.username + pulsation_state_address,
                'method': 'PUT',
                'body': {
                    'status': 1
                }
            }
        }

        result = self.bridge.request('POST', '/api/' + self.bridge.username + '/schedules', dumps(begin_schedule))

    def blue_whirl(self):
        lights = self.all_lights
        starting_status = {}

        for light in lights:
            state = self.bridge.get_light(int(light))['state']

            if state is not None:
                starting_status[light] = self.restorable_state_for_light(state)

        step_time = 0.075
        time_between_whirls = 0.5
        transition_time = 1
        whirl_count = 10

        total_seconds = ((step_time * 4) + time_between_whirls) * whirl_count
        finished_timestamp = 'PT00:00:%02d' % total_seconds

        self.disable_schedules_for_time(total_seconds)

        # Return to original state after we're done
        for light_id in lights:
            self.bridge.create_schedule('restore%dAfterWhirl' % light_id, finished_timestamp, light_id,
                                        starting_status[light_id])

        # Build our 'off' states to go with the on state
        off_states = {}

        for light_id, status in starting_status.iteritems():
            state = deepcopy(status)
            del state['on']
            if not status['on']:
                state['bri'] = 1

            off_states[light_id] = state

        for i in range(0,whirl_count):
            on_state = {'xy': self.whirl_color, 'bri': 255, 'transitiontime': transition_time}

            if i == 0:
                # The first time through, we need to make sure we set 'on' to True if necessary
                on_state['on'] = True

            self.bridge.set_light(3, on_state)
            time.sleep(step_time)
            self.bridge.set_light(4, on_state)
            time.sleep(step_time)
            self.bridge.set_light(3, off_states[3])
            self.bridge.set_light(5, on_state)
            time.sleep(step_time)
            self.bridge.set_light(4, off_states[4])
            time.sleep(step_time)
            self.bridge.set_light(5, off_states[5])
            time.sleep(time_between_whirls)
