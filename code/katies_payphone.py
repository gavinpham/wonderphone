 #!/usr/bin/env python3

# Original script by Edward Li 
# Edited and repurposed by Gavin Pham
# Updated May 13, 2018

import time, os, sys, subprocess, signal, logging, math
import RPi.GPIO as GPIO
from os import listdir, remove
from os.path import isfile, join

GPIO.setmode(GPIO.BCM)

logger = logging.getLogger('logwonderphone')
handler = logging.FileHandler('/home/pi/Desktop/wonderphone.log')
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# read SPI data from MCP3008 chip, 8 possible adc's (0 thru 7)
def readadc(adcnum, clockpin, mosipin, misopin, cspin):
	if ((adcnum > 7) or (adcnum < 0)):
		return -1
	GPIO.output(cspin, True)
	
	GPIO.output(clockpin, False)  # start clock low
	GPIO.output(cspin, False)     # bring CS low
	
	commandout = adcnum
	commandout |= 0x18  # start bit + single-ended bit
	commandout <<= 3    # we only need to send 5 bits here
	for i in range(5):
		if (commandout & 0x80):
			GPIO.output(mosipin, True)
		else:
			GPIO.output(mosipin, False)
		commandout <<= 1
		GPIO.output(clockpin, True)
		GPIO.output(clockpin, False)
	
	adcout = 0
	# read in one empty bit, one null bit and 10 ADC bits
	for i in range(12):
		GPIO.output(clockpin, True)
		GPIO.output(clockpin, False)
		adcout <<= 1
		if (GPIO.input(misopin)):
			adcout |= 0x1
	
	GPIO.output(cspin, True)
	
	adcout >>= 1       # first bit is 'null' so drop it
	return adcout

# pins connected from the SPI port on the ADC to the Cobbler
SPICLK 	= 18
SPIMISO = 23
SPIMOSI = 24
SPICS 	= 25
GPIO.setwarnings(False)
GPIO.setup(SPIMOSI, GPIO.OUT)
GPIO.setup(SPIMISO, GPIO.IN)
GPIO.setup(SPICLK, GPIO.OUT)
GPIO.setup(SPICS, GPIO.OUT)


# pins connected from various I/O to the Cobbler
PRESSED = 20
HOOK 	= 8
EXIT 	= 21
GPIO.setup(PRESSED, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
GPIO.setup(HOOK, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
GPIO.setup(EXIT, GPIO.IN, pull_up_down = GPIO.PUD_UP)

# DEBUG CONSTANTS
DEBUG_RAWADC 	= 0
DEBUG_PRESSED 	= 1
DEBUG_HOOK 		= 1
DEBUG_VERBOSE_OUTPUT = 1

# GLOBAL VARS
MENU = []
PLAYBACK_INDEX = 0
SHOULD_PLAY_GREETINGS = True

#------------------------------------------ UTILITY FUNCTIONS ------------------------------------------

# phoneIsOffHook: Return false if hung up, true if line is open.
def phoneIsOffHook():
	return GPIO.input(HOOK) == 1

# Play wav file on the attached system sound device
def play_wav(wav_filename):
	global p
	msg = "playing " + ", ".join(wav_filename)
	logger.debug(msg)
	p = subprocess.Popen(
		['aplay','-i','-D','plughw:1'] + wav_filename,
		stdin = subprocess.PIPE,
		stdout = subprocess.PIPE,
		stderr = subprocess.STDOUT,
		shell = False
	)

# record wav file on the attached system sound device
def record_wav(wav_filename):
	global r
	r = subprocess.Popen(
		['arecord','-f','cd','-d','30','-t','wav','-D','plughw:1','--max-file-time','30',wav_filename],
		stdin = subprocess.PIPE,
		stdout = subprocess.PIPE,
		stderr = subprocess.STDOUT,
		shell = False
	)
	print(r.stdout.read())

#soft_reset: return to the main menu
def soft_reset(channel): 
	global MENU
	global PLAYBACK_INDEX
	global SHOULD_PLAY_GREETINGS
	global IS_FIRST_PLAYBACK
	global p
	global r
	
	# Reset global vars
	MENU = []
	PLAYBACK_INDEX = 0
	IS_FIRST_PLAYBACK = True

	hookval = GPIO.input(HOOK) # check value of hook switch

	if DEBUG_HOOK:
		print(hookval, "Phone off hook.")
	if DEBUG_PRESSED:
		logger.debug("Main Menu.")

	try:
		if p.poll() == None:
			p.kill()
			print("MEF: ending current playback; returning to main menu")
	except NameError:
		print("MEF: error; p does not exist")

	if SHOULD_PLAY_GREETINGS:
		if DEBUG_VERBOSE_OUTPUT:
			print("Hello and welcome to the Wonderphone!")
		play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/greetings_message.wav"])
		p.wait()
		SHOULD_PLAY_GREETINGS = False
	if DEBUG_VERBOSE_OUTPUT:
		print("Main Menu. Press 1 to record a new message. Press 2 to playback messages.")
	play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/main_menu.wav"])

# restart: only triggered on full hang-up to refresh greeting message
def restart(channel):
	global SHOULD_PLAY_GREETINGS
	SHOULD_PLAY_GREETINGS = True
	soft_reset(channel)

def navigate_menu(last_key_pressed):
	global MENU
	global PLAYBACK_INDEX
	global IS_FIRST_PLAYBACK
	global p
	global r

	# End any current running audio, if any.
	try:
		if p.poll() == None:
			p.kill()
	except NameError:
		print("p doesn't exist")

	MENU.append(last_key_pressed)
	print("------------------------------------------") # Separator for output
	if DEBUG_PRESSED:
		print("Key pressed: " + last_key_pressed)

	recordings_list = os.listdir("/media/pi/WONDERPHONE/katies_recordings/")
	recordings_list.sort(reverse=True) #Sorts for chronological order
	print("recordings_list: ", recordings_list)

	unresolved_input = True
	while (unresolved_input):
		print("Current menu stack:", MENU)
		if MENU == ["1"]:
			if DEBUG_VERBOSE_OUTPUT:
				print("Record a message. You will have thirty seconds to record, so make it count! Start your message after the beep. *BEEP*")
			play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/new_recording_instructions.wav"])
			p.wait()
			savename = "/media/pi/WONDERPHONE/katies_recordings/recording_#_" + str(len(recordings_list) + 1) + ".wav"
			print("Recording Started.")
			record_wav(savename)
			if DEBUG_VERBOSE_OUTPUT:
				print("Recording Ended.")
			if DEBUG_VERBOSE_OUTPUT:
				print("To re-record your message, press 1. To review your message, press 2. To save your message, press #. To discard your message and return to the main menu, press 0.")
			play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/recording_ended.wav", "/media/pi/WONDERPHONE/katies_phone_prompts/post_recording_instructions.wav"])
			unresolved_input = False
		elif MENU == ["1", "1"]:
			# Delete the newest recorded file
			if os.path.isfile("/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[0]):
			    os.remove("/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[0])
			else:
			    print("Error: %s file not found" % myfile)
			MENU.pop()
		elif MENU == ["1","2"]:
			print("playing: " + recordings_list[0])
			play_wav(["/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[0]])
			p.wait()
			MENU.pop()
			if DEBUG_VERBOSE_OUTPUT:
				print("To re-record your message, press 1. To review your message, press 2. To save your message, press #. To discard your message and return to the main menu, press 0.")
			play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/post_recording_instructions.wav"])
			unresolved_input = False
		elif MENU == ["1","0"]:
			# Delete the newest recorded file
			if os.path.isfile("/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[0]):
			    os.remove("/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[0])
			else:
			    print("Error: %s file not found" % myfile)
			unresolved_input = False
			soft_reset(HOOK)
		elif MENU == ["1","#"]:
			if DEBUG_VERBOSE_OUTPUT:
				print("Message saved. Returning to Main Menu.")
			play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/recording_saved.wav"])
			p.wait()
			unresolved_input = False
			soft_reset(HOOK)
		elif MENU == ["2"]:
			if len(recordings_list) == 0:
				if DEBUG_VERBOSE_OUTPUT:
					print("There are no saved messages. Try and make one of your own!")
				play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/no_messages.wav"])
				p.wait()
				unresolved_input = False
				soft_reset(HOOK)
			else: 
				if IS_FIRST_PLAYBACK:
					if DEBUG_VERBOSE_OUTPUT:
						print("Playback messages. Messages will be played in chronological order.")
					play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/playback_introduction.wav"])
					p.wait()
					IS_FIRST_PLAYBACK = False
				print("Playback index: ")
				print(PLAYBACK_INDEX)
				if len(recordings_list) - 1 == PLAYBACK_INDEX:
					if DEBUG_VERBOSE_OUTPUT:
						print("Last message.")
					play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/last_message.wav"])
					p.wait()	
				play_wav(["/media/pi/WONDERPHONE/katies_recordings/" + recordings_list[PLAYBACK_INDEX]])
				p.wait()
				if len(recordings_list) - 1 == PLAYBACK_INDEX:
					if DEBUG_VERBOSE_OUTPUT:
						print("Press 1 to replay the message. Press 0 to return to return to the main menu.")
					play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/playback_last_message_instructions.wav"])
				else:
					if DEBUG_VERBOSE_OUTPUT:
						print("Press 1 to replay the message. Press 2 to continue to the next message. Press 0 to return to the main menu.")
					play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/playback_instructions.wav"])
			unresolved_input = False
		elif MENU == ["2","1"]:
			if DEBUG_VERBOSE_OUTPUT:
				print("Replay message.")
			play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/replay_message.wav"])
			p.wait()
			MENU.pop()
		elif MENU == ["2", "2"]:
			if PLAYBACK_INDEX > len(recordings_list): 
				if DEBUG_VERBOSE_OUTPUT:
					print("No messages left.")
				play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/no_messages_left.wav"])
				p.wait()
				unresolved_input = False
				soft_reset(HOOK)
			else:
				if DEBUG_VERBOSE_OUTPUT:
					print("Next message.")
				play_wav(["/media/pi/WONDERPHONE/katies_phone_prompts/next_message.wav"])
				p.wait()
				PLAYBACK_INDEX += 1
			MENU.pop()
		elif MENU == ["2", "0"]:
			unresolved_input = False
			soft_reset(HOOK)
		else:
			MENU.pop()
			unresolved_input = False

#------------------------------------------ KEYPAD ------------------------------------------

# determine what to do when a button is pressed
def button_handler(channel):
	global MENU
	if phoneIsOffHook():
		btnval = readadc(0, SPICLK, SPIMOSI, SPIMISO, SPICS) # check raw value of ADC
		if DEBUG_RAWADC:
			print ("btnval:", btnval)
		
		# Associate numeric press with ADC value
		# These are not perfect, imperfections due to connecting wires may be unstable and unreliable.
		if btnval > 960: # 1
			navigate_menu("1")
		if btnval > 870 and btnval < 910: # 2
			navigate_menu("2")
		if btnval > 760 and btnval < 810: # 3
			navigate_menu("3")
		if btnval > 700 and btnval < 750: # 4
			navigate_menu("4")
		if btnval > 650 and btnval < 670: # 5
			navigate_menu("5")
		if btnval > 580 and btnval < 610: # 6
			navigate_menu("6")
		if btnval > 540 and btnval < 570: # 7
			navigate_menu("7")
		if btnval > 500 and btnval < 525: # 8
			navigate_menu("8")
		if btnval > 470 and btnval < 490: # 9	
			navigate_menu("9")
		if btnval > 420 and btnval < 440: # 0
			navigate_menu("0")
		if btnval > 445 and btnval < 470: # star
			navigate_menu("*")
		if btnval > 390 and btnval < 420: # pound
			navigate_menu("#")


def main():
	try:
		restart(HOOK) # When the phone is picked up:
		logger.debug("---------PROGRAM START---------")
		print("Waiting for action...")
		GPIO.add_event_detect(PRESSED, GPIO.RISING, callback=button_handler, bouncetime=500) # look for button presses
		GPIO.add_event_detect(HOOK, GPIO.BOTH, callback=restart, bouncetime=3000) # look for phone on hook
		GPIO.wait_for_edge(EXIT, GPIO.RISING) # wait for exit button
		print("Quitting program.")
		logger.debug("----------PROGRAM END----------")
		try:
			if p.poll() == None: 	# If the process is still running... 
				p.kill()				# kill it
		except NameError:
			print ("p doesn't exist")
		try:
			if r.poll() == None:
				r.kill()
		except NameError:
			print ("r doesn't exist")
	except KeyboardInterrupt:
		try:
			if p.poll() == None:
				p.kill()
		except NameError:
			print ("p doesn't exist")
		try:
			if r.poll() == None:
				r.kill()
		except NameError:
			print ("r doesn't exist")
		GPIO.cleanup()		# clean up GPIO on CTRL+C exit
	sys.exit(0)				# system exit
	GPIO.cleanup()			# clean up GPIO on normal exit

if __name__ == "__main__":
	main()
