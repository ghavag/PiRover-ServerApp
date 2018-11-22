#!/usr/bin/python

# Dienstprogramm fuer den PiRover zur Ausfuehrung auf der Raspberry Pi.
#
# Autor: Alexander Graeb <mail@hpvag.de>
#
# Bugs:
#  * Alle Client-Verbindungen muessen erste geschlossen werden, damit das Programm vollstaendig terminiert.

### Konfigurationskonstanten. ###

LISTEN_ADDRESS = ""
LISTEN_PORT = 1987
VIDEO_RECORD_LOCATION = "/home/pi/"

# Zeichenfolge, welche zur Authentifizierung des Clients dient.
SECRET = "uMieY6ophu[a"

### Programm startet hier.
import SocketServer
import time
import datetime
import md5
import signal
import thread
import sys
import socket
import gi
import re

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

			re_matches = re.findall(r"(Hello PiRover!)(?: Flags=([,\w]+))?", data)

			if (re_matches[0][0] == 'Hello PiRover!'):
				self.request.send("PiRover 1.0 here! %s\n" % (authsalt))
			else:
				break

			if (ClientHandler.cc != 0):
				self.request.send("Client already connected!\n")
				break

			# Flags auswerten. (Moeglicherweise mehr in der Zukunft.)
			if (re_matches[0][1] == 'VIDREC'):
				start_gst_record()
				print "Video wird aufgenommen!"

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
			start_gst_pipeline(self.client_address[0])

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
		stop_gst_pipeline()

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

def start_gst_record():
	global gst_pipeline, gst_rec_bin, rec_filesink, teev, teea
	rec_filesink.set_property("location", VIDEO_RECORD_LOCATION + "PiRover-Record-" + datetime.datetime.now().strftime("%d-%B-%Y-%H%M") + ".mkv")
	gst_pipeline.add(gst_rec_bin)
	teev.link(gst_rec_bin)
	teea.link(gst_rec_bin)

def stop_gst_record():
	global gst_pipeline, gst_rec_bin
	if (gst_pipeline.get_by_name("recpipeline") is not None):
		gst_pipeline.remove(gst_rec_bin)

def start_gst_pipeline(client_addr):
	global gst_pipeline, udp_video_sink, udp_audio_sink
	udp_video_sink.set_property("host", client_addr)
	udp_audio_sink.set_property("host", client_addr)
	gst_pipeline.set_state(Gst.State.PLAYING)

def stop_gst_pipeline():
	gst_pipeline.set_state(Gst.State.NULL)
	stop_gst_record()

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
gst_pipeline = Gst.Pipeline.new("gstpipeline")

## Video-Pipeline (H264)

# gst-launch-1.0 -v v4l2src ! video/x-raw,width=640,height=480 ! omxh264enc target-bitrate=8000000 control-rate=variable ! \
# h264parse config-interval=1 ! rtph264pay ! udpsink host=x.x.x.x port=x

#v4l2src = Gst.ElementFactory.make("v4l2src", "v4l2-source")
#caps = Gst.Caps.from_string("video/x-raw,width=640,height=480,framerate=15/1") # video/x-raw,width=960,height=720,framerate=10/1"

v4l2src = Gst.ElementFactory.make("v4l2src", "v4l2-source")
caps = Gst.Caps.from_string("video/x-raw,width=960,height=720,framerate=15/1") # video/x-raw,width=960,height=720,framerate=10/1"
filter = Gst.ElementFactory.make("capsfilter")
filter.set_property("caps", caps)
x264enc = Gst.ElementFactory.make("omxh264enc")
#x264enc.set_property("tune", "zerolatency")
#x264enc.set_property("byte-stream", "true")
x264enc.set_property("target-bitrate", 8000000)
x264enc.set_property("control-rate", "variable")
h264parse = Gst.ElementFactory.make("h264parse")
h264parse.set_property("config-interval", 1)
teev = Gst.ElementFactory.make("tee")
queuev1 = Gst.ElementFactory.make("queue")
rtph264pay = Gst.ElementFactory.make("rtph264pay")
udp_video_sink = Gst.ElementFactory.make("udpsink")
udp_video_sink.set_property("port", 5000)
udp_video_sink.set_property("max-lateness", 0)
#udp_video_sink = Gst.ElementFactory.make("fakesink")

gst_pipeline.add(v4l2src)
gst_pipeline.add(filter)
gst_pipeline.add(x264enc)
gst_pipeline.add(h264parse)
gst_pipeline.add(teev)
gst_pipeline.add(queuev1)
gst_pipeline.add(rtph264pay)
gst_pipeline.add(udp_video_sink)

v4l2src.link(filter)
filter.link(x264enc)
x264enc.link(h264parse)
h264parse.link(teev)
teev.link(queuev1)
queuev1.link(rtph264pay)
rtph264pay.link(udp_video_sink)

## Audio-Pipeline

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
teea = Gst.ElementFactory.make("tee")
queuea1 = Gst.ElementFactory.make("queue")
udp_audio_sink = Gst.ElementFactory.make("udpsink")
udp_audio_sink.set_property("port", 5001)
udp_audio_sink.set_property("max-lateness", 0)

gst_pipeline.add(alsasrc)
gst_pipeline.add(audioconvert)
gst_pipeline.add(audioresample)
gst_pipeline.add(audio_filter)
gst_pipeline.add(vorbisenc)
gst_pipeline.add(teea)
gst_pipeline.add(queuea1)
gst_pipeline.add(udp_audio_sink)

alsasrc.link(audioconvert)
audioconvert.link(audioresample)
audioresample.link(audio_filter)
audio_filter.link(vorbisenc)
#mulawenc.link(rtppcmupay)
#rtppcmupay.link(udp_audio_sink)
vorbisenc.link(teea)
teea.link(queuea1)
queuea1.link(udp_audio_sink)

## Aufnahme-Pipeline
gst_rec_bin = Gst.Bin.new("recpipeline")

rec_queuev = Gst.ElementFactory.make("queue")
rec_audio_caps = Gst.Caps.from_string("audio/x-vorbis")
rec_audio_filter = Gst.ElementFactory.make("capsfilter")
rec_audio_filter.set_property("caps", rec_audio_caps)
rec_queuea = Gst.ElementFactory.make("queue")
rec_muxer = Gst.ElementFactory.make("matroskamux")
rec_filesink = Gst.ElementFactory.make("filesink")

gst_rec_bin.add(rec_queuev)
gst_rec_bin.add(rec_audio_filter)
gst_rec_bin.add(rec_queuea)
gst_rec_bin.add(rec_muxer)
gst_rec_bin.add(rec_filesink)

rec_queuev.link(rec_muxer)
rec_queuea.link(rec_audio_filter)
rec_audio_filter.link(rec_muxer)
rec_muxer.link(rec_filesink)

rec_padv = rec_queuev.get_static_pad("sink")
rec_ghostpadv = Gst.GhostPad.new("rec video sink", rec_padv)
gst_rec_bin.add_pad(rec_ghostpadv)

rec_pada = rec_queuea.get_static_pad("sink")
rec_ghostpada = Gst.GhostPad.new("rec audio sink", rec_pada)
gst_rec_bin.add_pad(rec_ghostpada)

##### Ende des GStreamer-Pipeline-Setups

server = SocketServer.ThreadingTCPServer((LISTEN_ADDRESS, LISTEN_PORT), ClientHandler)
server.serve_forever()

###### Fuer Techcammod
IO.cleanup()

print "Server stopped!"
