Lightbot
========

## [rtmbot](https://github.com/slackhq/python-rtmbot) Slack plugin for controlling Philips Hue lights

# Features

## Light commands

## NPS score triggers

# Setup

## Installing rtmbot

## Configuration options

### Colors
Options for colors accept strings in any of the following formats:
* [CSS3 color name](http://www.w3.org/TR/css3-color/#svg-color), such as "purple" or "sandybrown"
* Hex color codes, including "#FFFFFF" "#FFF" "123456"
* RGB colors as numbers 0-255
* RGB colors as percents, 0%-100%
* XY chromaticity values as specified in the [Philips Hue spec](https://www.developers.meethue.com/documentation/core-concepts)
### CHANNELS
### USERS
### WOOTRIC_BOT
### LIGHTS
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
