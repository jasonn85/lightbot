Lightbot
========

## [rtmbot](https://github.com/slackhq/python-rtmbot) Slack plugin for controlling Philips Hue lights

# Features

## Light commands

## NPS score triggers

# Setup

## Installing rtmbot

## Configuration options

### CHANNELS
### USERS
### WOOTRIC_BOT
### LIGHTS
### WIGWAG_GROUPS
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

### Colors
Options for colors accept strings in any of the following formats:
* [CSS3 color name](http://www.w3.org/TR/css3-color/#svg-color), such as "purple" or "sandybrown"
* Hex color codes, including "#FFFFFF" "#FFF" "123456"
* RGB colors as numbers 0-255
* RGB colors as percents, 0%-100%
* XY chromaticity values as specified in the [Philips Hue spec](https://www.developers.meethue.com/documentation/core-concepts)
