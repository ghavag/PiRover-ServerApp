# PiRover ServerApp

The PiRover is a rover (or robot) that can be controlled over wifi while transmitting video and audio. This is the daemon program which runs on a Raspberry Pi II.

## Files

__PiRover.py__ The actual daemon program.

__TestServer.py__ A fake daemon which lets you test the daemon program without a Raspberry Pi.

## Software dependencies

Applies to and tested under Raspbian GNU/Linux 9 (stretch).

* python-gi
* gstreamer-tools
* gstreamer1.0-tools
* python-gst-1.0
* gstreamer1.0-plugins-good
* gstreamer1.0-plugins-bad
* gstreamer1.0-alsa
