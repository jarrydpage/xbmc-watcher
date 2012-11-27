#!/usr/bin/perl
use strict;
use warnings;
use POSIX qw(strftime);

my ($lu, $lc, $dir, $log);

my $args = join(' ', @ARGV);

$dir = '/usr/xbmc';
$lu = $dir.'/.library_update';
$lc = $dir.'/.library_clean';
$log = $dir.'/log/libupdate';

#sub _ctime { my $ns = `date +%N`; chomp($ns); my $out = strftime("%Y-%m-%d %H:%M:%S", localtime(time)).".$ns"; return $out; }
sub _ctime {
my ($nano, $input) = @_;
my $ctime = (defined $input ? $input : time);
my $ns = `date +%N`;
chomp($ns);
return strftime("%Y-%m-%d %H:%M:%S", localtime($ctime)).($nano ? "" : ".$ns");
}

my $lu_t = time+60;
my $lc_t = time+600;

if (-e $lu) {
open LIB_UPDATE, '<', $lu;
my $lu_v = <LIB_UPDATE>;
$lu_t = (time >= $lu_v ? $lu_t : $lu_v) + 1;
}
if (-e $lc) {
open LIB_CLEAN, '<', $lc;
my $lc_v = <LIB_CLEAN>;
$lc_t = (time >= $lc_v ? $lc_t : $lc_v)+1;
}

open LOG, '>>', $log;
open LIB_UPDATE, '>', $lu;
open LIB_CLEAN, '>', $lc;
print LIB_UPDATE $lu_t;
print LIB_CLEAN $lc_t;
print LOG _ctime()." filesystem change: $args. Update @ "._ctime(1, $lu_t).", Clean @ "._ctime(1, $lc_t)."\n";

close LIB_UPDATE;
close LIB_CLEAN;
close LOG;
