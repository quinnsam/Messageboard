#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import time
import datetime
import json
import threading
import socket
import requests
import Adafruit_CharLCD as LCD
from slackclient import SlackClient
from sys import exit

try:
    with open('/home/pi/Documents/projects/Messageboard/msg_conf.json') as data_file:
        config = json.load(data_file)
except:
    print 'ERROR: Could not load config file'
    exit(-1)

# Get bot's ID from config file
BOT_ID = config['BOT_ID']

# constants
AT_BOT = "<@" + BOT_ID + ">"
AT_BOT_IFTTT = "<@" + BOT_ID + "|messageboard>"
EXAMPLE_COMMAND = "write"

# instantiate Slack clients
slack_client = SlackClient(config['SLACK_BOT_TOKEN'])

####################
# BeagleBone Black configuration:
#lcd_rs        = 'P8_8'
#lcd_en        = 'P8_10'
#lcd_d4        = 'P8_18'
#lcd_d5        = 'P8_16'
#lcd_d6        = 'P8_14'
#lcd_d7        = 'P8_12'
#lcd_backlight = 'P8_7'


# Raspberry Pi pin configuration:
lcd_rs        = 27  # Note this might need to be changed to 21 for older revision Pi's.
lcd_en        = 22
lcd_d4        = 25
lcd_d5        = 24
lcd_d6        = 23
lcd_d7        = 18
lcd_backlight = 4

# Define LCD column and row size for 20x4 LCD.
lcd_columns = 20
lcd_rows    = 4

# Gloabals
curr_message = ''

# Initialize the LCD using the pins above.
lcd = LCD.Adafruit_CharLCD(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7,
                           lcd_columns, lcd_rows, lcd_backlight)
# Turn on the Backligt
lcd.set_backlight(0)

# Clear the display
lcd.clear()

def worker_wait(td):
    #print td
    time.sleep(td)
    if os.path.isfile(config['tmp_msg']):
        with open(config['tmp_msg']) as tmp_file_fd:
            tmp_file = json.load(tmp_file_fd)
        handle_command(tmp_file['command'],tmp_file['channel'])

def get_weather():
    url = config['weather_url']

    try:
        r = requests.get(url)
    except:
        return ''

    city = r.json()['current_observation']['display_location']['city']
    temp = r.json()['current_observation']['temp_f']
    humidity = r.json()['current_observation']['relative_humidity']
    weather = r.json()['current_observation']['weather']

    return '%s Weather:; %s; Temp:%sF Hum:%s' % (city, weather, temp, humidity)



def write_to_board(msg):
    global curr_message
    #print "msg - %s" % msg
    if 'EV Charge' in msg or 'Cancelled' in msg:
        return 0

    curr_message = msg
    lcd.clear()

    msg = msg.replace('write ','',1)
    msg = msg.replace('curr_weather', get_weather(), 1)
    msg = msg.replace("Event starting now\n&gt;&gt;&gt;\n",'Sam is in a meeting; ')
    if 'Sam is in a meeting' in msg:
        # start with msg in format ('Sam is in a meeting; *RSVP Required - FAC *\n<!date^1492210800^{date_short}|Apr 14> from <!date^1492210800^{time}| 4:00pm> to <!date^1492215300^{time}| 5:15pm>')
        mt = msg.split('\n')[1] # get only the second part of the meeting with the date objects, format (<!date^1492210800^{date_short}|Apr 14> from <!date^1492210800^{time}| 4:00pm> to <!date^1492215300^{time}| 5:15pm>)
        msg = msg.split('\n')[0] # set msg to only the begining (Sam is in a meeting; *RSVP Required - FAC *)
        ma = re.findall('\<\!date\^[0-9]*\^', mt) # create a list formated like ([u'<!date^1492210800^', u'<!date^1492210800^', u'<!date^1492215300^'])
        ms = datetime.datetime.fromtimestamp(float(ma[1].strip('<!date^'))) # get meeting start in Unix timestamp format
        me = datetime.datetime.fromtimestamp(float(ma[-1].strip('<!date^'))) # get meeting end in Unix timestamp format
        td = me - datetime.datetime.now() # get timedelta from now to wait in secconds.
        if td.seconds > 0:
            # Start wait thread.
            thread = threading.Thread(target=worker_wait,args=(td.seconds,))
            thread.start()
        # add a newline between from and to
        msg = msg + '; From: %s; To: %s' % (ms.strftime('%H:%M'), me.strftime('%H:%M'))
    msg = msg.replace('\n', '; ')
    msg = msg.split('; ')
    ret = 'Sure I will write that to the board now: ```'
    #print msg
    if len(msg) > 4:
        return 'Currently not supported more than 4 lines'
    else:
	for i in xrange(0, len(msg)):
	    lcd.set_cursor(0,i)
	    lcd.message(msg[i][:20])
	    ret = ret + msg[i][:20] + "\n"

    return ret + '```'


def handle_command(command, channel):
    """
        Receives commands directed at the bot and determines if they
        are valid commands. If so, then acts on the commands. If not,
        returns back what it needs for clarification.
    """
    #print 'command = %s' % command
    if not 'Event starting now' in command:
        with open(config['tmp_msg'], 'w') as tmp_file:
            tmp_file.write('{ "command": "%s", "channel": "%s" }' % (command, channel))
            tmp_file.truncate()
    response = "Not sure what you mean. This is ment to be used by Sam only to send messages to work. Please do not mess with. Thank you! -Sam"
    if command.startswith(EXAMPLE_COMMAND):
        response = write_to_board(command)

    if response != 0:
        slack_client.api_call("chat.postMessage", channel=channel,
                          text=response, as_user=True)


def parse_slack_output(slack_rtm_output):
    """
        The Slack Real Time Messaging API is an events firehose.
        this parsing function returns None unless a message is
        directed at the Bot, based on its ID.
    """
    output_list = slack_rtm_output
    if output_list and len(output_list) > 0:
        for output in output_list:
            #print "output - %s" % output

            # Normal slack message parsing.
            if output and 'text' in output and AT_BOT in output['text']:
                #print '!!!!! Normal message parsing !!!!!'
                # return text after the @ mention, whitespace removed
                return output['text'].split(AT_BOT)[1].strip(), output['channel']

            # Normal slack message parsing if AT_BOT doesn't parse
            if output and 'text' in output and '@messageboard' in output['text']:
                #print '!!!!! Normal message parsing without AT_BOT !!!!!'
                # return text after the @ mention, whitespace removed
                return output['text'].split('@messageboard')[1].strip(), output['channel']

            # IFTTT message parsing.
            if output and 'username' in output and output['username'] == 'IFTTT' and AT_BOT in output['attachments'][0]['pretext']:
                #print '!!!!! IFTTT !!!!!'
                return output['attachments'][0]['pretext'].split(AT_BOT)[1].strip(), output['channel']

            # Calendar bot parsing.
            if output and 'username' in output and output['username'] == 'Cronofy Calendar API - Exchange':
                #print '!!!!! Calendar !!!!!'
                return 'write ' + output['text'].strip(), output['channel']
    return None, None


if __name__ == "__main__":
    led = False
    fail_count = 0
    upd_weather = 0
    # First start
    # if Crashed and still durring work hours.
    if os.path.isfile(config['tmp_msg']):
        if datetime.datetime.now().hour > 7 and datetime.datetime.now().hour < 18:
            if os.path.isfile(config['tmp_msg']):
                with open(config['tmp_msg']) as tmp_file_fd:
                    tmp_file = json.load(tmp_file_fd)
                handle_command(tmp_file['command'],tmp_file['channel'])

    # Post to the chat the local IP for maintence.
    ip = [(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]
    slack_client.api_call("chat.postMessage",channel=config['channel'], text=ip, as_user=True)


    READ_WEBSOCKET_DELAY = 1 # 1 second delay between reading from firehose
    if slack_client.rtm_connect():
        print("SlackBot connected and running!")
        while True:
            try:
                command, channel = parse_slack_output(slack_client.rtm_read())
                fail_count = 0
            except Exception as e:
                if fail_count > 5:
                    print type(e)
                    print e
                    sys.exit(1)
                fail_count = fail_count + 1

            if command and channel:
                handle_command(command, channel)
            time.sleep(READ_WEBSOCKET_DELAY)

            if datetime.datetime.now().hour > 17 or datetime.datetime.now().hour < 7:
                # Turn off the Backligt
                lcd.set_backlight(1)
                upd_weather = 0
            else:
                # Turn on the Backligt
                lcd.set_backlight(0)

                if datetime.datetime.now().hour > upd_weather and 'curr_weather' in curr_message:
                    upd_weather = datetime.datetime.now().hour
                    write_to_board(curr_message)

    else:
        print("Connection failed. Invalid Slack token or bot ID?")
