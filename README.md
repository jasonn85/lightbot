Lightbot
========

## [rtmbot](https://github.com/slackhq/python-rtmbot) Slack plugin for controlling Philips Hue lights
Control your lights and party like it's 1988 in IRC.

# Features

## Light commands
> All light commands will work on all configured lights unless specified in the command.

### Lights on/off
```
lights on
```
```
light 5 off
```
### Brightness
Accepts percentages as either xx% or decimal.
```
lights brightness 60%
```
```
light 3 bri 0.6
```
### Colors
Colors can be [CSS3 color names](http://www.w3.org/TR/css3-color/#svg-color), RGB values 0-255, RGB percents, hex values, or XY chromaticity values.
```
lights forestgreen
```
```
light 10 #FF0000
```
```
lights 1 2 3 (255, 255, 255)
```
```
lights [0.1576, 0.2368]
```
### Animations
```
light 3 dance party
```
```
lights whirl
```
```
lights pulsate
```
```
lights wigwag
```

## NPS score triggers
Lightbot currently supports NPS scores as reported by a [Wootric Slack bot](http://help.wootric.com/knowledge_base/topics/how-do-i-post-my-wootric-responses-to-slack).  This can be extended to include other sources of NPS scores in the future.

* **10** - whirl animation
* **9** - wigwag animation
* **0** - low pulsing

# Setup

## Installing rtmbot
1. Follow the [rtmbot instructions](https://github.com/slackhq/python-rtmbot) for installing and configuring a Slack bot on your system of choice.
2. Clone/download the lightbot plugin into the rtmbot plugins folder
3. Add the plugin to ACTIVE_PLUGINS.  For example, if you check the lightbot repository out inside of the plugins folder, the entry for lightbot in ACTIVE_PLUGINS would be `  - plugins.lightbot.lightBot.LightBot`.
4. Configure the lightbot, at least with HUE_BRIDGE_ADDRESS value.

## Dependencies
* **[rtmbot](https://github.com/slackhq/python-rtmbot)**
* **[phue](https://github.com/studioimaginaire/phue)** - unofficial Hue Python SDK
* **webcolors** - for color command processing

## Connecting to the Hue Bridge
Press the link button on your Hue Bridge just before starting the bot and connecting the lightbot for the first time.  If the button is not pressed, the bot will log an error and fail to connect to the lights.

## Configuration options

### Colors
Configuration options for colors accept strings in any of the following formats:
* [CSS3 color name](http://www.w3.org/TR/css3-color/#svg-color), such as "purple" or "sandybrown"
* Hex color codes, including "#FFFFFF" "#FFF" "123456"
* RGB colors as numbers 0-255
* RGB colors as percents, 0%-100%
* XY chromaticity values as specified in the [Philips Hue spec](https://www.developers.meethue.com/documentation/core-concepts)

### CHANNELS
Optional list of Slack channel IDs in which any user can control the lights.  Default allows light control from any channel the bot inhabits.

### USERS
Optional list of users that can directly send light commands and can use light commands from absolutely any channel.
```YAML
  USERS:
    - U1234567 # Jason
```

### WOOTRIC_BOT
The bot ID of the Wootric NPS score bot.
```YAML
  WOOTRIC_BOT: "B12AB34F"
```

### LIGHTS
The light IDs to be used for non-specific light chat commands.  Note that lights outside of this list can still be used manually, e.g. `light 3 red`.  Defaults to all lights on the Hue Bridge.
```YAML
  LIGHTS:
    - 1
    - 2
    - 3
```

### Color Whirl Options
#### WHIRL_COLOR
The color to be used for the whirl effect.  Defaults to light blue.
```YAML
  - WHIRL_COLOR: #FF0000
```
#### WHIRL_LIGHTS
The lights to be used for whirling.  Defaults to LIGHTS (in singular order) or all lights on the Hue Bridge.  This can be an array of light IDs or an array of arrays of light IDs for grouping.
```YAML
  - WHIRL_LIGHTS:
    - 1
	- 3
	- 4
```
```YAML
# Lights 1+2 and 3+4 will animate together as a group
  - WHIRL_LIGHTS:
    -
	  - 1
	  - 2
	-
	  - 3
	  - 4
```

### Wigwag Options
#### WIGWAG_GROUPS
Lights can be separated into two groups for wig wag animations:
```YAML
  - WIGWAG_GROUPS:
    -
	  - 1
	  - 3
	-
	  - 2
	  - 4
```

#### WIGWAG_COLOR
The color to use for wigwag animations.  See #Colors above for acceptable formats.  Defaults to a light blue.
```YAML
  - WIGWAG_COLOR: white
```

### Slow Pulse Options
#### SLOW_PULSE_COLOR
The color to use for slow pulsation.  Defaults to dark red.
```YAML
  - SLOW_PULSE_COLOR: #440000
```

#### SLOW_PULSE_LIGHTS
The lights to use for slow pulsation.  Defaults to the LIGHTS option if it is the only value specified, otherwise all lights on the Hue bridge.
```YAML
  - SLOW_PULSE_LIGHTS:
    - 5
	- 6
```
