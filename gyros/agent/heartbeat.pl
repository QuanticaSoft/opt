#!/usr/bin/perl
use strict;
use warnings;
use IO::Socket::INET;
use POSIX qw(strftime);

sub read_config {
    my %cfg;
    open my $fh, "<", "/opt/gyros/agent/config.conf"
        or die "No puedo abrir config.conf";
    while (<$fh>) {
        chomp;
        next if /^#/ || /^\s*$/;
        my ($k, $v) = split /=/, $_, 2;
        $cfg{$k} = $v;
    }
    close $fh;
    return %cfg;
}

my %cfg = read_config();

my $AGENT_ID     = $cfg{AGENT_ID};
my $BACKEND_HOST = $cfg{BACKEND_HOST};
my $BACKEND_PORT = $cfg{BACKEND_PORT};
my $INTERVAL     = $cfg{HEARTBEAT_INTERVAL} || 30;

while (1) {

    my $time = strftime("%Y-%m-%d %H:%M:%S", localtime);

    my $json = qq|{
"agent_id":"$AGENT_ID",
"event":"heartbeat",
"status":"on_line",
"lastSeen":"$time"
}|;   # ← ← ← ESTE ; ES CRÍTICO

    my $sock = IO::Socket::INET->new(
        PeerAddr => $BACKEND_HOST,
        PeerPort => $BACKEND_PORT,
        Proto    => 'tcp',
        Timeout  => 5
    );

    if ($sock) {
        print $sock "$json\n";
        close $sock;
    }

    sleep $INTERVAL;
}