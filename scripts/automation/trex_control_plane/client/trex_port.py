
from collections import namedtuple, OrderedDict
from common.trex_types import *
from common import trex_stats
from client_utils import packet_builder
StreamOnPort = namedtuple('StreamOnPort', ['compiled_stream', 'metadata'])

########## utlity ############
def mult_to_factor (mult, max_bps, max_pps, line_util):
    if mult['type'] == 'raw':
        return mult['value']

    if mult['type'] == 'bps':
        return mult['value'] / max_bps

    if mult['type'] == 'pps':
        return mult['value'] / max_pps

    if mult['type'] == 'percentage':
        return mult['value'] / line_util


# describes a single port
class Port(object):
    STATE_DOWN       = 0
    STATE_IDLE       = 1
    STATE_STREAMS    = 2
    STATE_TX         = 3
    STATE_PAUSE      = 4
    PortState = namedtuple('PortState', ['state_id', 'state_name'])
    STATES_MAP = {STATE_DOWN: "DOWN",
                  STATE_IDLE: "IDLE",
                  STATE_STREAMS: "IDLE",
                  STATE_TX: "ACTIVE",
                  STATE_PAUSE: "PAUSE"}


    def __init__ (self, port_id, speed, driver, user, comm_link, session_id):
        self.port_id = port_id
        self.state = self.STATE_IDLE
        self.handler = None
        self.comm_link = comm_link
        self.transmit = comm_link.transmit
        self.transmit_batch = comm_link.transmit_batch
        self.user = user
        self.driver = driver
        self.speed = speed
        self.streams = {}
        self.profile = None
        self.session_id = session_id
        self.loaded_stream_pack = None

        self.port_stats = trex_stats.CPortStats(self)


    def err(self, msg):
        return RC_ERR("port {0} : {1}".format(self.port_id, msg))

    def ok(self, data = "ACK"):
        return RC_OK(data)

    def get_speed_bps (self):
        return (self.speed * 1000 * 1000 * 1000)

    # take the port
    def acquire(self, force = False):
        params = {"port_id":     self.port_id,
                  "user":        self.user,
                  "session_id":  self.session_id,
                  "force":       force}

        command = RpcCmdData("acquire", params)
        rc = self.transmit(command.method, command.params)
        if rc.good():
            self.handler = rc.data()
            return self.ok()
        else:
            return self.err(rc.err())

    # release the port
    def release(self):
        params = {"port_id": self.port_id,
                  "handler": self.handler}

        command = RpcCmdData("release", params)
        rc = self.transmit(command.method, command.params)
        self.handler = None

        if rc.good():
            return self.ok()
        else:
            return self.err(rc.err())

    def is_acquired(self):
        return (self.handler != None)

    def is_active(self):
        return(self.state == self.STATE_TX ) or (self.state == self.STATE_PAUSE)

    def is_transmitting (self):
        return (self.state == self.STATE_TX)

    def is_paused (self):
        return (self.state == self.STATE_PAUSE)


    def sync(self):
        params = {"port_id": self.port_id}

        command = RpcCmdData("get_port_status", params)
        rc = self.transmit(command.method, command.params)
        if rc.bad():
            return self.err(rc.err())

        # sync the port
        port_state = rc.data()['state']

        if port_state == "DOWN":
            self.state = self.STATE_DOWN
        elif port_state == "IDLE":
            self.state = self.STATE_IDLE
        elif port_state == "STREAMS":
            self.state = self.STATE_STREAMS
        elif port_state == "TX":
            self.state = self.STATE_TX
        elif port_state == "PAUSE":
            self.state = self.STATE_PAUSE
        else:
            raise Exception("port {0}: bad state received from server '{1}'".format(self.port_id, port_state))

        # TODO: handle syncing the streams into stream_db

        return self.ok()


    # return TRUE if write commands
    def is_port_writable (self):
        # operations on port can be done on state idle or state streams
        return ((self.state == self.STATE_IDLE) or (self.state == self.STATE_STREAMS))

    # add stream to the port
    def add_stream (self, stream_id, stream_obj):

        if not self.is_port_writable():
            return self.err("Please stop port before attempting to add streams")


        params = {"handler": self.handler,
                  "port_id": self.port_id,
                  "stream_id": stream_id,
                  "stream": stream_obj}

        rc = self.transmit("add_stream", params)
        if rc.bad():
            return self.err(rc.err())

        # add the stream
        self.streams[stream_id] = StreamOnPort(stream_obj, Port._generate_stream_metadata(stream_id, stream_obj))

        # the only valid state now
        self.state = self.STATE_STREAMS

        return self.ok()

    # add multiple streams
    def add_streams (self, LoadedStreamList_obj):
        batch = []

        self.loaded_stream_pack = LoadedStreamList_obj
        compiled_stream_list = LoadedStreamList_obj.compiled

        for stream_pack in compiled_stream_list:
            params = {"handler": self.handler,
                      "port_id": self.port_id,
                      "stream_id": stream_pack.stream_id,
                      "stream": stream_pack.stream}

            cmd = RpcCmdData('add_stream', params)
            batch.append(cmd)

        rc = self.transmit_batch(batch)
        if rc.bad():
            return self.err(rc.err())

        # validate that every action succeeded

        # add the stream
        for stream_pack in compiled_stream_list:
            self.streams[stream_pack.stream_id] = StreamOnPort(stream_pack.stream,
                                                               Port._generate_stream_metadata(stream_pack.stream_id,
                                                                                              stream_pack.stream))

        # the only valid state now
        self.state = self.STATE_STREAMS

        return self.ok()

    # remove stream from port
    def remove_stream (self, stream_id):

        if not stream_id in self.streams:
            return self.err("stream {0} does not exists".format(stream_id))

        params = {"handler": self.handler,
                  "port_id": self.port_id,
                  "stream_id": stream_id}


        rc = self.transmit("remove_stream", params)
        if rc.bad():
            return self.err(rc.err())

        self.streams[stream_id] = None

        self.state = self.STATE_STREAMS if (len(self.streams) > 0) else self.STATE_IDLE

        return self.ok()

    # remove all the streams
    def remove_all_streams (self):

        params = {"handler": self.handler,
                  "port_id": self.port_id}

        rc = self.transmit("remove_all_streams", params)
        if rc.bad():
            return self.err(rc.err())

        self.streams = {}

        self.state = self.STATE_IDLE

        return self.ok()

    # get a specific stream
    def get_stream (self, stream_id):
        if stream_id in self.streams:
            return self.streams[stream_id]
        else:
            return None

    def get_all_streams (self):
        return self.streams

    # start traffic
    def start (self, mul, duration):
        if self.state == self.STATE_DOWN:
            return self.err("Unable to start traffic - port is down")

        if self.state == self.STATE_IDLE:
            return self.err("Unable to start traffic - no streams attached to port")

        if self.state == self.STATE_TX:
            return self.err("Unable to start traffic - port is already transmitting")

        params = {"handler": self.handler,
                  "port_id": self.port_id,
                  "mul": mul,
                  "duration": duration}

        rc = self.transmit("start_traffic", params)
        if rc.bad():
            return self.err(rc.err())

        self.state = self.STATE_TX

        return self.ok()

    # stop traffic
    # with force ignores the cached state and sends the command
    def stop (self, force = False):

        if (not force) and (self.state != self.STATE_TX) and (self.state != self.STATE_PAUSE):
            return self.err("port is not transmitting")

        params = {"handler": self.handler,
                  "port_id": self.port_id}

        rc = self.transmit("stop_traffic", params)
        if rc.bad():
            return self.err(rc.err())

        # only valid state after stop
        self.state = self.STATE_STREAMS

        return self.ok()

    def pause (self):

        if (self.state != self.STATE_TX) :
            return self.err("port is not transmitting")

        params = {"handler": self.handler,
                  "port_id": self.port_id}

        rc  = self.transmit("pause_traffic", params)
        if rc.bad():
            return self.err(rc.err())

        # only valid state after stop
        self.state = self.STATE_PAUSE

        return self.ok()


    def resume (self):

        if (self.state != self.STATE_PAUSE) :
            return self.err("port is not in pause mode")

        params = {"handler": self.handler,
                  "port_id": self.port_id}

        rc = self.transmit("resume_traffic", params)
        if rc.bad():
            return self.err(rc.err())

        # only valid state after stop
        self.state = self.STATE_TX

        return self.ok()


    def update (self, mul):
        if (self.state != self.STATE_TX) :
            return self.err("port is not transmitting")

        params = {"handler": self.handler,
                  "port_id": self.port_id,
                  "mul": mul}

        rc = self.transmit("update_traffic", params)
        if rc.bad():
            return self.err(rc.err())

        return self.ok()


    def validate (self):

        if (self.state == self.STATE_DOWN):
            return self.err("port is down")

        if (self.state == self.STATE_IDLE):
            return self.err("no streams attached to port")

        params = {"handler": self.handler,
                  "port_id": self.port_id}

        rc = self.transmit("validate", params)
        if rc.bad():
            return self.err(rc.err())

        self.profile = rc.data()

        return self.ok()

    def get_profile (self):
        return self.profile


    def print_profile (self, mult, duration):
        if not self.get_profile():
            return

        rate = self.get_profile()['rate']
        graph = self.get_profile()['graph']

        print format_text("Profile Map Per Port\n", 'underline', 'bold')

        factor = mult_to_factor(mult, rate['max_bps'], rate['max_pps'], rate['max_line_util'])

        print "Profile max BPS    (base / req):   {:^12} / {:^12}".format(format_num(rate['max_bps'], suffix = "bps"),
                                                                          format_num(rate['max_bps'] * factor, suffix = "bps"))

        print "Profile max PPS    (base / req):   {:^12} / {:^12}".format(format_num(rate['max_pps'], suffix = "pps"),
                                                                          format_num(rate['max_pps'] * factor, suffix = "pps"),)

        print "Profile line util. (base / req):   {:^12} / {:^12}".format(format_percentage(rate['max_line_util'] * 100),
                                                                          format_percentage(rate['max_line_util'] * factor * 100))


        # duration
        exp_time_base_sec = graph['expected_duration'] / (1000 * 1000)
        exp_time_factor_sec = exp_time_base_sec / factor

        # user configured a duration
        if duration > 0:
            if exp_time_factor_sec > 0:
                exp_time_factor_sec = min(exp_time_factor_sec, duration)
            else:
                exp_time_factor_sec = duration


        print "Duration           (base / req):   {:^12} / {:^12}".format(format_time(exp_time_base_sec),
                                                                          format_time(exp_time_factor_sec))
        print "\n"


    def get_port_state_name(self):
        return self.STATES_MAP.get(self.state, "Unknown")

    ################# stats handler ######################
    def generate_port_stats(self):
        return self.port_stats.generate_stats()

    def generate_port_status(self):
        return {"type": self.driver,
                "maximum": "{speed} Gb/s".format(speed=self.speed),
                "status": self.get_port_state_name()
                }

    def clear_stats(self):
        return self.port_stats.clear_stats()

    def invalidate_stats(self):
        return self.port_stats.invalidate()

    ################# stream printout ######################
    def generate_loaded_streams_sum(self, stream_id_list):
        if self.state == self.STATE_DOWN or self.state == self.STATE_STREAMS:
            return {}
        elif self.loaded_stream_pack is None:
            # avoid crashing when sync with remote server isn't operational
            # TODO: MAKE SURE TO HANDLE THIS CASE FOR BETTER UX
            return {}
        streams_data = {}

        if not stream_id_list:
            # if no mask has been provided, apply to all streams on port
            stream_id_list = self.streams.keys()


        streams_data = {stream_id: self.streams[stream_id].metadata.get('stream_sum', ["N/A"] * 6)
                        for stream_id in stream_id_list
                        if stream_id in self.streams}


        return {"referring_file" : self.loaded_stream_pack.name,
                "streams" : streams_data}

    @staticmethod
    def _generate_stream_metadata(stream_id, compiled_stream_obj):
        meta_dict = {}
        # create packet stream description
        pkt_bld_obj = packet_builder.CTRexPktBuilder()
        pkt_bld_obj.load_from_stream_obj(compiled_stream_obj)
        # generate stream summary based on that

        next_stream = "None" if compiled_stream_obj['next_stream_id']==-1 else compiled_stream_obj['next_stream_id']

        meta_dict['stream_sum'] = OrderedDict([("id", stream_id),
                                               ("packet_type", "/".join(pkt_bld_obj.get_packet_layers())),
                                               ("length", pkt_bld_obj.get_packet_length()),
                                               ("mode", compiled_stream_obj['mode']['type']),
                                               ("rate_pps", compiled_stream_obj['mode']['pps']),
                                               ("next_stream", next_stream)
                                               ])
        return meta_dict

    ################# events handler ######################
    def async_event_port_stopped (self):
        self.state = self.STATE_STREAMS


    def async_event_port_started (self):
        self.state = self.STATE_TX


    def async_event_port_paused (self):
        self.state = self.STATE_PAUSE


    def async_event_port_resumed (self):
        self.state = self.STATE_TX

    def async_event_forced_acquired (self):
        self.handler = None

