#!/usr/bin/python

# Dienstprogramm fuer den PiRover zur Ausfuehrung auf der Raspberry Pi.
#
# Autor: Alexander Graeb <mail@hpvag.de>
#
# Benoetigte Pakete unter Raspbian (moeglicherweise sind nicht alle diese Pakete notwendig):
# * python-gi
# * gstreamer-tools
# * gstreamer1.0-tools
# * python-gst-1.0
# * gstreamer1.0-omx
# * gstreamer1.0-videosource
# * gstreamer1.0-plugins-good
# * gstreamer1.0-plugins-bad
# * gstreamer1.0-alsa
#
# Bugs:
#  * Alle Client-Verbindungen muessen erste geschlossen werden, damit das Programm vollstaendig terminiert.

### Konfigurationskonstanten. ###

LISTEN_ADDRESS = ""
LISTEN_PORT = 1987

# Zeichenfolge, welche zur Authentifizierung des Clients dient.
SECRET = "uMieY6ophu[a"

### Programm startet hier.
import SocketServer
import time
import md5
import signal
import thread
import sys
import socket
import gi

gi.require_version('Gst', '1.0')

from gi.repository import Gst, GObject, GLib

##### Fuer Techcammod
import RPi.GPIO as IO

cur_UpDown = 0 # Aktuelle Tastenstellung fuer linke (-1), rechte (1) oder keine (0) der beiden Tasten.
cur_LeftRight = 0 # Aktuelle Tastenstellung fuer nach oben (-1), nach unten (1) oder keine (0) der beiden Tasten.

# Konfiguration fuer die Pinbelegung (nach BCM-Belegung).
LEFT_FOR = 24
LEFT_REV = 25
RIGHT_FOR = 27
RIGHT_REV = 12

class ClientHandler(SocketServer.BaseRequestHandler):
	cc = 0

	def handle(self):
		print "Client connected from %s." % (self.client_address[0])

		client_authed = False

		while True:
			# Warte darauf, dass Client das Zauberwort sagt.
			data = self.request.recv(1024)

			if not data:
				break

			print "Received data from client: %s" % (data)

			# Begruesse Client und sende Salz fuer den Authentifizierungs-Hash mit.
			authsalt = str(time.time())

			if (data == 'Hello PiRover!\n'):
				self.request.send("PiRover 1.0 here! %s\n" % (authsalt))
			else:
				break

			if (ClientHandler.cc != 0):
				self.request.send("Client already connected!\n")
				break

			# Warte darauf, dass sich Client authentifiziert.
			data = self.request.recv(1024)

			if not data:
				break

			print "Received data from client: %s" % (data)

			if (data == (md5.new(SECRET + authsalt).hexdigest() + "\n")):
				print "Client auth ok!"
				self.request.send("OK\n");
				ClientHandler.cc += 1 # Erst nachdem sich client erfolgreich authentifiziert hat, wird er gezaehlt.
				client_authed = True
			else:
				print "Auth failed!"
				break

			# GStreamer-Pipeline starten.
			udp_video_sink.set_property("host", self.client_address[0])
			udp_audio_sink.set_property("host", self.client_address[0])
			video_pipeline.set_state(Gst.State.PLAYING)
			audio_pipeline.set_state(Gst.State.PLAYING)

			data = self.request.recv(1024)
			self.request.settimeout(2) # recv()-Aufruf blockiert maximal 2 Sekunden.

			while (data):
				print "Received data from client: %s" % (data)
				try:
					data = self.request.recv(1024)
				except socket.timeout:
					print "Timeout!"
					update_output(0, 0)

				# Kommandos vom Client auswerten. (Manchmal mehrere Kommandos in einem einzelnen Datenpaket.)
				for command in data.splitlines(True):
					# Kommandos vom Client auswerten.
					if (command == "UP pressed\n"):
						update_output(vertical = 1)
					elif (command == "DOWN pressed\n"):
						update_output(vertical = -1)
					elif ((command == "UP released\n") or (command == "DOWN released\n")):
						update_output(vertical = 0)
					elif (command == "LEFT pressed\n"):
						update_output(horizontal = -1)
					elif (command == "RIGHT pressed\n"):
						update_output(horizontal = 1)
					elif ((command == "LEFT released\n") or (command == "RIGHT released\n")):
						update_output(horizontal = 0)
					#elif (command == "Keep alive\n"):
					#	pass
					#else:
					#	update_output(0, 0)

		# GStreamer-Pipeline wieder schliessen.
		video_pipeline.set_state(Gst.State.NULL)
		audio_pipeline.set_state(Gst.State.NULL)

		update_output(0, 0)

		print "Connection to client %s closed." % self.client_address[0]

		if client_authed:
			ClientHandler.cc -= 1

# Routine, um SIGTERM abzufangen.
def signal_handler(signum, frame):
	print 'Signal handler called with signal', signum
	thread.start_new_thread(shutdown_thread, ())

# Das ist, weil die shutdown()-Methode von einem anderen Thread aus gerufen werden muss. Sonst Deadlock.
def shutdown_thread():
	global server
	print "Shuting down server thread called!"
	server.shutdown()
	server.server_close()

def update_output(vertical=None, horizontal=None):
	global cur_UpDown, cur_LeftRight

	# Tasten-Update uebernehmen.
	if (horizontal is not None):
		cur_LeftRight = horizontal

	if (vertical is not None):
		cur_UpDown = vertical

	if (cur_UpDown == -1 and cur_LeftRight == 0):
		r_speed = 1
		l_speed = 1
	elif (cur_UpDown == 1 and cur_LeftRight == 0):
		r_speed = -1
		l_speed = -1
	elif (cur_UpDown == 0 and cur_LeftRight == -1):
		r_speed = 1
		l_speed = -1
	elif (cur_UpDown == 0 and cur_LeftRight == 1):
		r_speed = -1
		l_speed = 1
	elif (cur_UpDown == -1 and cur_LeftRight == -1):
		r_speed = 0
		l_speed = 1
	elif (cur_UpDown == -1 and cur_LeftRight == 1):
		r_speed = 1
		l_speed = 0
	elif (cur_UpDown == 1 and cur_LeftRight == -1):
		r_speed = 0
		l_speed = -1
	elif (cur_UpDown == 1 and cur_LeftRight == 1):
		r_speed = -1
		l_speed = 0
	else:
		r_speed = 0
		l_speed = 0

	# Fuer die Ansteuerung der rechten Achse.
	if (r_speed == 1):
		IO.output(RIGHT_FOR, IO.HIGH)
		IO.output(RIGHT_REV, IO.LOW)
	elif (r_speed == -1):
		IO.output(RIGHT_FOR, IO.LOW)
		IO.output(RIGHT_REV, IO.HIGH)
	else:
		IO.output(RIGHT_FOR, IO.LOW)
		IO.output(RIGHT_REV, IO.LOW)

	# Fuer die Ansteuerung der linken Achse.
	if (l_speed == 1):
		IO.output(LEFT_FOR, IO.HIGH)
		IO.output(LEFT_REV, IO.LOW)
	elif (l_speed == -1):
		IO.output(LEFT_FOR, IO.LOW)
		IO.output(LEFT_REV, IO.HIGH)
	else:
		IO.output(LEFT_FOR, IO.LOW)
		IO.output(LEFT_REV, IO.LOW)

	#print "=== Currend Speed ===\n\tl_speed=%d\n\tr_speed=%d" % (l_speed, r_speed)

### Einsprungspunkt fuer das Programm.
print "PiRover server started."

###### GPIO-Setup.
IO.setmode(IO.BCM) # Benutze GPIO-Nummerierung.
IO.setup(LEFT_FOR, IO.OUT)
IO.setup(LEFT_REV, IO.OUT)
IO.setup(RIGHT_FOR, IO.OUT)
IO.setup(RIGHT_REV, IO.OUT)

# Routine fuer das Signal SIGTERM mitteilen.
signal.signal(signal.SIGTERM, signal_handler)

# Und waehle diese Routine auch fuer SIGINT, also wenn das Programm ueber CTRL+C abgebrochen wurde.
signal.signal(signal.SIGINT, signal_handler)

###### GStreamer-Pipeline fuer Videouebertragung vorbereiten.
Gst.init(None)

# Video-Pipeline
video_pipeline = Gst.Pipeline.new("videopipeline")

# Wenn True, wird der JPEG-Encoder verwendet.
if False:
	v4l2src = Gst.ElementFactory.make("v4l2src", "v4l2-source")
	caps = Gst.Caps.from_string("video/x-raw,width=800,height=600,framerate=25/1")
	#caps = Gst.Caps.from_string("video/x-raw,width=640,height=480")
	filter = Gst.ElementFactory.make("capsfilter")
	filter.set_property("caps", caps)
	jpegenc = Gst.ElementFactory.make("jpegenc")
	rtpjpegpay = Gst.ElementFactory.make("rtpjpegpay")
	udp_video_sink = Gst.ElementFactory.make("udpsink")
	udp_video_sink.set_property("port", 5000)

	video_pipeline.add(v4l2src)
	video_pipeline.add(filter)
	video_pipeline.add(jpegenc)
	video_pipeline.add(rtpjpegpay)
	video_pipeline.add(udp_video_sink)

	v4l2src.link(filter)
	filter.link(jpegenc)
	jpegenc.link(rtpjpegpay)
	rtpjpegpay.link(udp_video_sink)
# Dies ist fuer die H264-Pipeline
else:
	# gst-launch-1.0 -v v4l2src ! video/x-raw,width=640,height=480 ! omxh264enc target-bitrate=8000000 control-rate=variable ! \
	# h264parse config-interval=1 ! rtph264pay ! udpsink host=x.x.x.x port=x
	v4l2src = Gst.ElementFactory.make("v4l2src", "v4l2-source")
	caps = Gst.Caps.from_string("video/x-raw,width=960,height=720,framerate=10/1")
	filter = Gst.ElementFactory.make("capsfilter")
	filter.set_property("caps", caps)
	omxh264enc = Gst.ElementFactory.make("omxh264enc")
	omxh264enc.set_property("target-bitrate", 8000000)
	omxh264enc.set_property("control-rate", "variable")
	h264parse = Gst.ElementFactory.make("h264parse")
	h264parse.set_property("config-interval", 1)
	rtph264pay = Gst.ElementFactory.make("rtph264pay")
	udp_video_sink = Gst.ElementFactory.make("udpsink")
	udp_video_sink.set_property("port", 5000)

	video_pipeline.add(v4l2src, filter, omxh264enc, h264parse, rtph264pay, udp_video_sink)

	v4l2src.link(filter)
	filter.link(omxh264enc)
	omxh264enc.link(h264parse)
	h264parse.link(rtph264pay)
	rtph264pay.link(udp_video_sink)

# Audio-Pipeline
audio_pipeline = Gst.Pipeline.new("audiopipeline")

# gst-launch-1.0 -v alsasrc device=hw:1,0 ! audioconvert ! audioresample ! audio/x-raw, rate=8000 ! vorbisenc ! udpsink host=192.168.2.116 port=5001
alsasrc = Gst.ElementFactory.make("alsasrc")
alsasrc.set_property("device", "hw:1,0")
audioconvert = Gst.ElementFactory.make("audioconvert")
audioresample = Gst.ElementFactory.make("audioresample")
audio_caps = Gst.Caps.from_string("audio/x-raw, rate=8000")
audio_filter = Gst.ElementFactory.make("capsfilter")
audio_filter.set_property("caps", audio_caps)
vorbisenc = Gst.ElementFactory.make("vorbisenc")
#rtppcmupay = Gst.ElementFactory.make("rtppcmupay")
udp_audio_sink = Gst.ElementFactory.make("udpsink")
udp_audio_sink.set_property("port", 5001)

audio_pipeline.add(alsasrc, audioconvert, audioresample, audio_filter, vorbisenc, udp_audio_sink)

alsasrc.link(audioconvert)
audioconvert.link(audioresample)
audioresample.link(audio_filter)
audio_filter.link(vorbisenc)
#mulawenc.link(rtppcmupay)
#rtppcmupay.link(udp_audio_sink)
vorbisenc.link(udp_audio_sink)

##### Ende des GStreamer-Pipeline-Setups

server = SocketServer.ThreadingTCPServer((LISTEN_ADDRESS, LISTEN_PORT), ClientHandler)
server.serve_forever()

###### Fuer Techcammod
IO.cleanup()

print "Server stopped!"
