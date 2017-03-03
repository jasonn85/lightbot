Lightbot
========

## [rtmbot](https://github.com/slackhq/python-rtmbot) Slack plugin for controlling Philips Hue lights

# Features

## Light commands
All light commands take an optional list of light IDs to apply commands specifically to one or more lights.

### Lights on/off
`lights on`
`light 5 off`
### Brightness
Accepts percentages as either xx% or decimal.
`lights brightness 60%`
`light 3 bri 0.6`
### Colors
Colors can be [CSS3 color names](http://www.w3.org/TR/css3-color/#svg-color), RGB values 0-255, RGB percents, hex values, or XY chromaticity values.
`lights forestgreen`
`light 10 #FF0000`
`lights 1 2 3 (255, 255, 255)`
### Animations
`light 3 dance party`
`lights whirl`
`lights pulsate`
`lights wigwag`

## NPS score triggers
Lightbot currently supports NPS scores as reported by a [Wootric Slack bot](http://help.wootric.com/knowledge_base/topics/how-do-i-post-my-wootric-responses-to-slack).  This can be extended to include other sources of NPS scores in the future.

# Setup

## Installing rtmbot

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
### WOOTRIC_BOT
The bot ID of the Wootric NPS score bot.
### LIGHTS
The light IDs to be used for non-specific light chat commands.  Note that lights outside of this list can still be used manually, e.g. `light 3 red`.  Defaults to all lights on the Hue Bridge.
### Color Whirl Options
#### WHIRL_COLOR
The color to be used for the whirl effect.  Defaults to light blue.
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
### Slow Pulse Options
#### SLOW_PULSE_COLOR
The color to use for slow pulsation.  Defaults to dark red.
#### SLOW_PULSE_LIGHTS
The lights to use for slow pulsation.  Defaults to the LIGHTS option if it is the only value specified, otherwise all lights on the Hue bridge.
