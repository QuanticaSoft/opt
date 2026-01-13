#!/usr/bin/perl
use strict;
use warnings;

system("/usr/bin/perl /opt/gyros/agent/heartbeat.pl &");
system("/usr/bin/perl /opt/gyros/agent/usb-monitor.pl &");

sleep while 1;