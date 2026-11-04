"""Read-only MQTT listener for the rc.2 acceptance (runs in WSL with paho-mqtt).

Reads one JSON line {"host","port","user","pw"} from stdin (never from a file or the command line), subscribes
to <prefix>/# for N seconds and prints, per message: seconds since start, R (retained) or -, topic, size and
the payload. The payload is printed whole (up to 6000 characters) for the topics the acceptance parses
(fw/availability, fw/heartbeat, fw/state/heating, fw/telemetry/tuning), else its first 300 characters.
It never publishes. Usage: python mqtt_listen_rc2.py <seconds> [prefix]
"""
import json
import sys
import time

import paho.mqtt.client as mqtt

FULL = ('/fw/availability', '/fw/heartbeat', '/fw/state/heating', '/fw/telemetry/tuning')
c = json.loads(sys.stdin.readline())
secs = int(sys.argv[1]) if len(sys.argv) > 1 else 60
prefix = sys.argv[2] if len(sys.argv) > 2 else 'ib-therm'
start = time.time()
cl = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='ot-acceptance-readonly-%d' % int(start))
cl.username_pw_set(c['user'], c['pw'])
del c['pw']


def on_connect(client, userdata, flags, rc, properties=None):
    print('connected', rc, flush=True)
    client.subscribe(prefix + '/#', qos=0)


def on_message(client, userdata, m):
    p = m.payload.decode('utf-8', 'replace').replace('\r', ' ').replace('\n', ' ')
    limit = 6000 if m.topic.endswith(FULL) else 300
    print('%6.1f %s %s %dB %s' % (time.time() - start, 'R' if m.retain else '-', m.topic, len(m.payload), p[:limit]),
          flush=True)


cl.on_connect = on_connect
cl.on_message = on_message
cl.connect(c['host'], int(c['port']), 30)
cl.loop_start()
time.sleep(secs)
cl.loop_stop()
cl.disconnect()
