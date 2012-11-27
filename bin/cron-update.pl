#!/usr/bin/perl

use strict;
use warnings;
use POSIX qw(strftime);

sub _ctime { my $ns = `date +%N`; chomp($ns); my $out = strftime("%Y-%m-%d %H:%M:%S", localtime(time)).".$ns"; return $out; }

my ($lu, $lc, $curl, $dir, $log);
my ($lut, $lct);

$dir = '/usr/xbmc';
$lu = $dir.'/.library_update';
$lc = $dir.'/.library_clean';
$log = $dir.'/log/libupdate';

if (-e $lu) {
open(LIB_UPDATE, '<', $lu);
open LOG, '>>', $log;
$lut = <LIB_UPDATE>;
if (time > $lut)
{
	my $out = `curl -s --user xbmc:xbmc --data-binary '{ "jsonrpc": "2.0", "method": "VideoLibrary.Scan", "id": "xbmc" }' -H "content-type: application/json;" http://htpc.network:8080/jsonrpc`;
	system('rm -rf '.$lu);
	print LOG _ctime()." -- Updating XBMC library --\n";
	print LOG _ctime()." JSON response: $out\n";
}
close(LIB_UPDATE);
close LOG;
}

if (-e $lc) {
open(LIB_CLEAN, '<', $lc);
open LOG, '>>', $log;
$lct = <LIB_CLEAN>;
if (time > $lct)
{
	my $out = `curl -s --user xbmc:xbmc --data-binary '{ "jsonrpc": "2.0", "method": "VideoLibrary.Clean", "id": "xbmc" }' -H "content-type: application/json;" http://htpc.network:8080/jsonrpc`;
	system('rm -rf '.$lc);
	print LOG _ctime()." -- Cleaning XBMC library --\n";
	print LOG _ctime()." JSON response: $out\n";
}
close(LIB_CLEAN);
close LOG;
}
