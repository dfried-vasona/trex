#!/router/bin/python

__copyright__ = "Copyright 2014"

"""
Name:
     trex_general_test.py


Description:

    This script creates the functionality to test the performance of the T-Rex traffic generator
    The tested scenario is a T-Rex TG directly connected to a Cisco router.

::

    Topology:

       -------                         --------
      |       | Tx---1gig/10gig----Rx |        |
      | T-Rex |                       | router |
      |       | Rx---1gig/10gig----Tx |        |
       -------                         --------

"""
from nose.plugins import Plugin
from nose.plugins.skip import SkipTest
import trex
import misc_methods
import sys
import os
# from CPlatformUnderTest import *
from CPlatform import *
import termstyle
import threading
from tests_exceptions import *
from platform_cmd_link import *
import unittest


class CTRexScenario():
    modes            = set() # list of modes of this setup: loopback, virtual etc.
    server_logs      = False
    is_test_list     = False
    is_init          = False
    trex_crashed     = False
    configuration    = None
    trex             = None
    router           = None
    router_cfg       = None
    daemon_log_lines = 0
    setup_name       = None
    setup_dir        = None
    router_image     = None
    trex_version     = None
    scripts_path     = None
    report_dir       = 'reports'
    # logger         = None

#scenario = CTRexScenario()

def setUpModule(module):
#   print ("") # this is to get a newline after the dots
#   print ("setup_module before anything in this file")
#   # ff = CTRexScenario()
#   scenario.configuration = misc_methods.load_complete_config_file('config/config.yaml')
#   scenario.trex          = trex.CTRexRunner(scenario.configuration[0], None)
#   scenario.router        = CPlatform(scenario.configuration[1], False, scenario.configuration[2])
#   scenario.router.platform.preCheck()
#   print "Done instantiating trex scenario!"
    pass

def tearDownModule(module):
#   print ("") # this is to get a newline after the dots
#   scenario.router.platform.postCheck()
#   print ("teardown_module after anything in this file")
    pass



class CTRexGeneral_Test(unittest.TestCase):
    """This class defines the general testcase of the T-Rex traffic generator"""
    def __init__ (self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        # Point test object to scenario global object
        self.configuration         = CTRexScenario.configuration
        self.benchmark             = CTRexScenario.benchmark
        self.trex                  = CTRexScenario.trex
        self.trex_crashed          = CTRexScenario.trex_crashed
        self.modes                 = CTRexScenario.modes
        self.skipping              = False
        self.fail_reasons          = []
        if not hasattr(self, 'unsupported_modes'):
            self.unsupported_modes   = []
        self.is_loopback           = True if 'loopback' in self.modes else False
        self.is_virt_nics          = True if 'virt_nics' in self.modes else False
        self.is_VM                 = True if 'VM' in self.modes else False

        if not CTRexScenario.is_init:
            CTRexScenario.trex_version = self.trex.get_trex_version()
            if not self.is_loopback:
                # initilize the scenario based on received configuration, once per entire testing session
                CTRexScenario.router = CPlatform(CTRexScenario.router_cfg['silent_mode'])
                device_cfg           = CDeviceCfg()
                device_cfg.set_platform_config(CTRexScenario.router_cfg['config_dict'])
                device_cfg.set_tftp_config(CTRexScenario.router_cfg['tftp_config_dict'])
                CTRexScenario.router.load_platform_data_from_file(device_cfg)
                CTRexScenario.router.launch_connection(device_cfg)
                running_image = CTRexScenario.router.get_running_image_details()['image']
                print 'Current router image: %s' % running_image
                if CTRexScenario.router_cfg['forceImageReload']:
                    needed_image = device_cfg.get_image_name()
                    if not CTRexScenario.router.is_image_matches(needed_image):
                        print 'Setting router image: %s' % needed_image
                        CTRexScenario.router.config_tftp_server(device_cfg)
                        CTRexScenario.router.load_platform_image(needed_image)
                        CTRexScenario.router.set_boot_image(needed_image)
                        CTRexScenario.router.reload_platform(device_cfg)
                        CTRexScenario.router.launch_connection(device_cfg)
                        running_image = CTRexScenario.router.get_running_image_details()['image'] # verify image
                        if not CTRexScenario.router.is_image_matches(needed_image):
                            self.fail('Unable to set router image: %s, current image is: %s' % (needed_image, running_image))
                    else:
                        print 'Matches needed image: %s' % needed_image
                CTRexScenario.router_image = running_image

                    
            if self.modes:
                print termstyle.green('\t!!!\tRunning with modes: %s, not suitable tests will be skipped.\t!!!' % list(self.modes))

            CTRexScenario.is_init = True
            print termstyle.green("Done instantiating T-Rex scenario!\n")

#           raise RuntimeError('CTRexScenario class is not initialized!')
        self.router = CTRexScenario.router



#   def assert_dict_eq (self, dict, key, val, error=''):
#           v1 = int(dict[key]))
#           self.assertEqual(v1, int(val), error)
#
#   def assert_dict_gt (self, d, key, val, error=''):
#           v1 = int(dict[key])
#           self.assert_gt(v1, int(val), error)

    def assertEqual(self, v1, v2, s):
        if v1 != v2:
            error='ERROR '+str(v1)+' !=  '+str(v2)+ '   '+s;
            self.fail(error)

    def assert_gt(self, v1, v2, s):
        if not v1 > v2:
            error='ERROR {big} <  {small}      {str}'.format(big = v1, small = v2, str = s)
            self.fail(error)

    def check_results_eq (self,res,name,val):
        if res is None:
            self.fail('TRex results cannot be None !')
            return

        if name not in res:
            self.fail('TRex results does not include key %s' % name)
            return

        if res[name] != float(val):
            self.fail('TRex results[%s]==%f and not as expected %f ' % (name, res[name], val))

    def check_CPU_benchmark (self, trex_res, err = 10, minimal_cpu = 30, maximal_cpu = 85):
            #cpu_util = float(trex_res.get_last_value("trex-global.data.m_cpu_util"))
            cpu_util = sum([float(x) for x in trex_res.get_value_list("trex-global.data.m_cpu_util")[-4:-1]]) / 3 # mean of 3 values before last
            
            if not self.is_virt_nics:
                if cpu_util > maximal_cpu:
                    self.fail("CPU is too high (%s%%), probably queue full." % cpu_util )
                if cpu_util < minimal_cpu:
                    self.fail("CPU is too low (%s%%), can't verify performance in such low CPU%%." % cpu_util )

            cores = self.get_benchmark_param('cores')
            trex_tx_bps  = trex_res.get_last_value("trex-global.data.m_total_tx_bytes")
            test_norm_cpu = 100.0*(trex_tx_bps/(cores*cpu_util))/1e6

            print "TRex CPU utilization: %g%%, norm_cpu is : %d Mb/core" % (round(cpu_util), int(test_norm_cpu))

            #expected_norm_cpu = self.get_benchmark_param('cpu_to_core_ratio')

            #calc_error_precent = abs(100.0*(test_norm_cpu/expected_norm_cpu)-100.0)

#           if calc_error_precent > err:
#               msg ='Normalized bandwidth to CPU utilization ratio is %2.0f Mb/core expected %2.0f Mb/core more than %2.0f %% - ERROR' % (test_norm_cpu, expected_norm_cpu, err)
#               raise AbnormalResultError(msg)
#           else:
#               msg ='Normalized bandwidth to CPU utilization ratio is %2.0f Mb/core expected %2.0f Mb/core less than %2.0f %% - OK' % (test_norm_cpu, expected_norm_cpu, err)
#               print msg


    def check_results_gt (self, res, name, val):
        if res is None:
            self.fail('TRex results canot be None !')
            return

        if name not in res:
            self.fail('TRex results does not include key %s' % name)
            return

        if res[name]< float(val):
            self.fail('TRex results[%s]<%f and not as expected greater than %f ' % (name, res[name], val))

    def check_for_trex_crash(self):
        pass

    def get_benchmark_param (self, param, sub_param = None, test_name = None):
        if not test_name:
            test_name = self.get_name()
        if test_name not in self.benchmark:
            self.skip('No data in benchmark.yaml for test: %s, param: %s. Skipping.' % (test_name, param))
        if sub_param:
            return self.benchmark[test_name][param].get(sub_param)
        else:
            return self.benchmark[test_name].get(param)

    def check_general_scenario_results (self, trex_res, check_latency = True):
        
        try:
            # check if test is valid
            if not trex_res.is_done_warmup():
                self.fail('T-Rex did not reach warm-up situtaion. Results are not valid.')

            # check T-Rex number of drops
            trex_tx_pckt    = trex_res.get_last_value("trex-global.data.m_total_tx_pkts")
            trex_drops      = trex_res.get_total_drops()
            trex_drop_rate  = trex_res.get_drop_rate()
            if ( trex_drops > 0.001 * trex_tx_pckt) and (trex_drop_rate > 0.0):     # deliberately mask kickoff drops when T-Rex first initiated
                self.fail('Number of packet drops larger than 0.1% of all traffic')

            # check queue full, queue drop, allocation error
            m_total_alloc_error = trex_res.get_last_value("trex-global.data.m_total_alloc_error")
            m_total_queue_full = trex_res.get_last_value("trex-global.data.m_total_queue_full")
            m_total_queue_drop = trex_res.get_last_value("trex-global.data.m_total_queue_drop")
            self.assert_gt( 999, m_total_alloc_error, 'Got allocation errors. (%s), please review multiplier and templates configuration.' % m_total_alloc_error)
            self.assert_gt( max(9999, trex_tx_pckt / 1000 ), m_total_queue_full, 'Too much queue_full (%s), please review multiplier.' % m_total_queue_full)
            self.assert_gt( 999, m_total_queue_drop, 'Too much queue_drop (%s), please review multiplier.' % m_total_queue_drop)

            # # check T-Rex expected counters
            #trex_exp_rate = trex_res.get_expected_tx_rate().get('m_tx_expected_bps')
            #assert trex_exp_rate is not None
            #trex_exp_gbps = trex_exp_rate/(10**9)

            if check_latency:
                # check that max latency does not exceed 1 msec in regular setup or 100ms in VM
                allowed_latency = 9999999 if self.is_VM else 1000
                if max(trex_res.get_max_latency().values()) > allowed_latency:
                    self.fail('LatencyError: Maximal latency exceeds %s (usec)' % allowed_latency)
    
                # check that avg latency does not exceed 1 msec in regular setup or 3ms in VM
                allowed_latency = 9999999 if self.is_VM else 1000
                if max(trex_res.get_avg_latency().values()) > allowed_latency:
                    self.fail('LatencyError: Average latency exceeds %s (usec)' % allowed_latency)

            if not self.is_loopback:
                # check router number of drops --> deliberately masked- need to be figured out!!!!!
                pkt_drop_stats = self.router.get_drop_stats()
#               assert pkt_drop_stats['total_drops'] < 20

                # check for trex-router packet consistency
                # TODO: check if it's ok
                print 'router drop stats: %s' % pkt_drop_stats
                print 'TRex drop stats: %s' % trex_drops
                #self.assertEqual(pkt_drop_stats, trex_drops, "TRex's and router's drop stats don't match.")

        except KeyError as e:
            self.fail(e)
            #assert False

        # except AssertionError as e:
        #     e.args += ('T-Rex has crashed!') 
        #     raise

    # We encountered error, don't fail the test immediately
    def fail(self, reason = 'Unknown error'):
        print 'Error: %s' % reason
        self.fail_reasons.append(reason)

    # skip running of the test, counts as 'passed' but prints 'skipped'
    def skip(self, message = 'Unknown reason'):
        print 'Skip: %s' % message
        self.skipping = True
        raise SkipTest(message)

    # get name of currently running test
    def get_name(self):
        return self._testMethodName

    def setUp(self):
        test_setup_modes_conflict = self.modes & set(self.unsupported_modes)
        if test_setup_modes_conflict:
            self.skip("The test can't run with following modes of given setup: %s " % test_setup_modes_conflict)
        if not self.trex.is_idle():
            print 'Warning: TRex is not idle at setUp, trying to stop it.'
            self.trex.force_kill(confirm = False)
        if not self.is_loopback:
            print ''
            self.router.load_clean_config()
            self.router.clear_counters()
            self.router.clear_packet_drop_stats()

    ########################################################################
    ####                DO NOT ADD TESTS TO THIS FILE                   ####
    ####    Added tests here will held once for EVERY test sub-class    ####
    ########################################################################

    # masked example to such test. uncomment to watch how it affects #
#   def test_isInitialized(self):
#       assert CTRexScenario.is_init == True
    def tearDown(self):
        if not self.trex.is_idle():
            print 'Warning: TRex is not idle at tearDown, trying to stop it.'
            self.trex.force_kill(confirm = False)
        if not self.skipping:
            # print server logs of test run
            if CTRexScenario.server_logs:
                try:
                    print termstyle.green('\n>>>>>>>>>>>>>>> Daemon log <<<<<<<<<<<<<<<')
                    daemon_log = self.trex.get_trex_daemon_log()
                    log_size = len(daemon_log)
                    print ''.join(daemon_log[CTRexScenario.daemon_log_lines:])
                    CTRexScenario.daemon_log_lines = log_size
                except Exception as e:
                    print "Can't get TRex daemon log:", e
                try:
                    print termstyle.green('>>>>>>>>>>>>>>>> Trex log <<<<<<<<<<<<<<<<')
                    print ''.join(self.trex.get_trex_log())
                except Exception as e:
                    print "Can't get TRex log:", e
            if len(self.fail_reasons):
                raise Exception('The test is failed, reasons:\n%s' % '\n'.join(self.fail_reasons))

    def check_for_trex_crash(self):
        pass
