#!/usr/bin/env python
# Copyright (c) 2010 Greggory Hernandez

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys, os, time, atexit
from signal import SIGTERM
import pyinotify
import sys, os
import datetime
import subprocess
import shlex
import re
import time
from types import *
from string import Template
from yaml import load, dump # load is for read yaml, dump is for writing
try:
    from yaml import CLoader as Loader
    from yaml import CDumper as Dumper
except ImportError:
    from yaml import Loader, Dumper


RECENTLY_UPDATED_FOLDERS = {}

_prefix = '/usr/xbmc'
def _stdlog(message, dest = 'stderr'): 
 output = "%s: %s" % (datetime.datetime.now(), message, )
 if dest == 'stderr': sys.stderr.write(output)
 elif dest == 'stdout': sys.stdout.write(output)

class Daemon:
    """
    A generic daemon class

    Usage: subclass the Daemon class and override the run method
    """
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile

    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced Programming in the
        UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try:
            pid = os.fork()
            if pid > 0:
                #exit first parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #1 failed: %d (%s) " % (e.errno, e.strerror))
            #_stdlog("fork #1 failed: %d (%s) " % (e.errno, e.strerror))
            sys.exit(1)

        # decouple from parent environment
        os.chdir("/")
        os.setsid()
        os.umask(0)

        # do second fork
        try:
            pid = os.fork()
            if pid > 0:
                # exit from second parent
                sys.exit(0)
        except OSError, e:
            sys.stderr.write("fork #2 failed: %d (%s) " % (e.errno, e.strerror))
            #_stdlog("fork #2 failed: %d (%s) " % (e.errno, e.strerror))
            sys.exit(1)

        #redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())

        #write pid file
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile, 'w+').write("%s\n" % pid)

    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if pid:
            message = "pidfile %s already exists. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            #_stdlog(message % self.pidfile)
            sys.exit(1)

        # Start the Daemon
        self.daemonize()
        self.run()

    def stop(self):
        """
        Stop the daemon
        """
        # get the pid from the pidfile
        try:
            pf = file(self.pidfile, 'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None

        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)
            #_stdlog(message % self.pidfile)
            return # not an error in a restart

        # Try killing the daemon process
        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                #_stdlog(str(err))
                sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """

class EventHandler(pyinotify.ProcessEvent):
    def __init__(self, command, recursive, mask, parent, prefix, root):
        pyinotify.ProcessEvent.__init__(self)
        self.command = command     #the command to be run
        self.recursive = recursive #watch recursively?
        self.mask = mask           #the watch mask
        self.parent = parent       #should be calling instance of WatcherDaemon
        self.prefix = prefix       #prefix to handle recursively watching new dirs
        self.root = root           #root of watch (actually used to calculate subdirs)
        self.move_map = {}
        
    def runCommand(self, event, ignore_cookie=True):
        t = Template(self.command)
        
        #build the dest_file
        dfile = event.name
        if self.prefix != "":
            dfile = self.prefix + '/' + dfile
        elif self.root != "":
            dfile = re.sub('^'+re.escape(self.root+os.sep),'',event.path) + os.sep + dfile

        #find the src_path if it exists
        src_path = ''
        if not ignore_cookie and hasattr(event, 'cookie') and event.cookie in self.move_map:
            src_path = self.move_map[event.cookie]
            del self.move_map[event.cookie]
            
        #run substitutions on the command
        command = t.safe_substitute({
                'watched': event.path,
                'filename': event.pathname,
                'dest_file': dfile,
                'tflags': event.maskname,
                'nflags': event.mask,
                'src_path': src_path
                })
        
        # get the directory from command
        directory = os.path.dirname(' '.join(command.split()[2:-1]))

        # Update the dictionary with ctime + 60
        print("Set an update time on '%s' for 60 seconds from now" % (directory, ))
        RECENTLY_UPDATED_FOLDERS[directory] = time.time() + 60

        #try the command
        try:
            print("COMMAND: [%s]" % command);
            subprocess.call(shlex.split(command))
        except OSError, err:
            print "Failed to run command '%s' %s" % (command, str(err))
            #_stdlog("Failed to run command '%s' %s" % (command, str(err), 'stdlog'))
        
        #handle recursive watching of directories
        if self.recursive and os.path.isdir(event.pathname):
            prefix = event.name
            if self.prefix != "":
                prefix = self.prefix + '/' + prefix
            self.parent.addWatch(self.mask, 
                                 event.pathname, 
                                 True, 
                                 self.command, 
                                 prefix)

    def process_IN_ACCESS(self, event):
        print "Access: ", event.pathname
        #_stdlog('Access: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_ATTRIB(self, event):
        print "Attrib: ", event.pathname
        #_stdlog('Attrib: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_CLOSE_WRITE(self, event):
        print "Close write: ", event.pathname
        #_stdlog('Close write: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_CLOSE_NOWRITE(self, event):
        print "Close nowrite: ", event.pathname
	#_stdlog('Close nowrite: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_CREATE(self, event):
        print "Creating: ", event.pathname
	_stdlog('Creating: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_DELETE(self, event):
        print "Deleteing: ", event.pathname
	_stdlog('Deleting: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_MODIFY(self, event):
        print "Modify: ", event.pathname
	#_stdlog('Modify: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_MOVE_SELF(self, event):
        print "Move self: ", event.pathname
	#_stdlog('Move self: '+event.pathname, 'stdlog')
        self.runCommand(event)

    def process_IN_MOVED_FROM(self, event):
        print "Moved from: ", event.pathname
	#_stdlog('Moved from: '+event.pathname, 'stdlog')
        self.move_map[event.cookie] = event.pathname
        self.runCommand(event)

    def process_IN_MOVED_TO(self, event):
        print "Moved to: ", event.pathname
	#_stdlog('Moved to: '+event.pathname, 'stdlog')
        self.runCommand(event, False)

    def process_IN_OPEN(self, event):
        print "Opened: ", event.pathname
	#_stdlog('Opened: '+event.pathname, 'stdlog')
        self.runCommand(event)

class WatcherDaemon(Daemon):
    def run(self):
        print datetime.datetime.today()

        dir = self._loadWatcherDirectory()
        jobs_file = file(dir + '/jobs.yml', 'r')
        self.wdds = []
        self.notifiers = []

        # parse jobs.yml and add_watch/notifier for each entry
        print jobs_file
        #_stdlog(jobs_file, 'stdlog')
        jobs = load(jobs_file, Loader=Loader)
        if jobs is not None:
            for job in jobs.iteritems():
                sys.stdout.write(job[0] + "\n")
                #_stdlog(job[0], 'stdlog')
                # get the basic config info
                mask = self._parseMask(job[1]['events'])
                folder = job[1]['watch']
                recursive = job[1]['recursive']
                command = job[1]['command']

                self.addWatch(mask, folder, recursive, command)

        # now we need to start ALL the notifiers.
        # TODO: load test this ... is having a thread for each a problem?
        #for notifier in self.notifiers:
        #    notifier.start()
            
    def addWatch(self, mask, folder, recursive, command, prefix=""):
        wm = pyinotify.WatchManager()
        handler = EventHandler(command, recursive, mask, self, prefix, folder)
        
        self.wdds.append(wm.add_watch(folder, mask, rec=recursive))
        # BUT we need a new ThreadNotifier so I can specify a different
        # EventHandler instance for each job
        # this means that each job has its own thread as well (I think)
        n = pyinotify.ThreadedNotifier(wm, handler)
        self.notifiers.append(pyinotify.ThreadedNotifier(wm, handler))
        
        n.start()

    def _loadWatcherDirectory(self):
        #home = os.path.expanduser('~')
        watcher_dir = _prefix + '/.watcher'
        jobs_file = watcher_dir + '/jobs.yml'

        if not os.path.isdir(watcher_dir):
            # create directory
            os.mkdir(watcher_dir)

        if not os.path.isfile(jobs_file):
            # create jobs.yml
            f = open(jobs_file, 'w')
            f.close()

        return watcher_dir

    def _parseMask(self, masks):
        ret = False;

        for mask in masks:
            if 'access' == mask:
                ret = self._addMask(pyinotify.IN_ACCESS, ret)
            elif 'atrribute_change' == mask:
                ret = self._addMask(pyinotify.IN_ATTRIB, ret)
            elif 'write_close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_WRITE, ret)
            elif 'nowrite_close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_NOWRITE, ret)
            elif 'create' == mask:
                ret = self._addMask(pyinotify.IN_CREATE, ret)
            elif 'delete' == mask:
                ret = self._addMask(pyinotify.IN_DELETE, ret)
            elif 'self_delete' == mask:
                ret = self._addMask(pyinotify.IN_DELETE_SELF, ret)
            elif 'modify' == mask:
                ret = self._addMask(pyinotify.IN_MODIFY, ret)
            elif 'self_move' == mask:
                ret = self._addMask(pyinotify.IN_MOVE_SELF, ret)
            elif 'move_from' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_FROM, ret)
            elif 'move_to' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_TO, ret)
            elif 'open' == mask:
                ret = self._addMask(pyinotify.IN_OPEN, ret)
            elif 'all' == mask:
                m = pyinotify.IN_ACCESS | pyinotify.IN_ATTRIB | pyinotify.IN_CLOSE_WRITE | \
                    pyinotify.IN_CLOSE_NOWRITE | pyinotify.IN_CREATE | pyinotify.IN_DELETE | \
                    pyinotify.IN_DELETE_SELF | pyinotify.IN_MODIFY | pyinotify.IN_MOVE_SELF | \
                    pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO | pyinotify.IN_OPEN
                ret = self._addMask(m, ret)
            elif 'move' == mask:
                ret = self._addMask(pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO, ret)
            elif 'close' == mask:
                ret = self._addMask(pyinotify.IN_CLOSE_WRITE | pyinotify.IN_CLOSE_NOWRITE, ret)

        return ret

    def _addMask(self, new_option, current_options):

        if not current_options:
            return new_option
        else:
            return current_options | new_option


class UpdateLibrary(Daemon):

    def run(self):

        while True:
            remove_folders = []

            print("Checking for recently updated folders...")
            print(RECENTLY_UPDATED_FOLDERS)

            # Check for recent updates
            for folder, ctime in RECENTLY_UPDATED_FOLDERS.iteritems():
                if ctime > time.time():
                    print("At this point we should update '%s'" % (folder, ))
                    remove_folders.append(folder)

            for folder in remove_folders:
                del RECENTLY_UPDATED_FOLDERS[folder]

            time.sleep(60)



if __name__ == "__main__":
    #log = '/var/xbmc/log/watcher'
    log = _prefix+'/log/watcher'
    # create the log
    f = open(log, 'a+')
    f.close()
    #_stdlog("LOL")  

    # Since different threads are handled for each individual event, it's best
    # just to use a global variable for the udpated folders
    

    try:
        # TODO: make stdout and stderr neutral location
        daemon = WatcherDaemon(_prefix+'/watcher.pid', stdout=log, stderr=log)
        update_library_daemon = UpdateLibrary(_prefix+'/recently_updated.pid', stdout=log, stderr=log)

        if len(sys.argv) == 2:
            if 'start' == sys.argv[1]:
                f = open(log, 'a+')
                f.close()
                daemon.start()
                update_library_daemon.start()

            elif 'stop' == sys.argv[1]:
                #os.remove(log)
                daemon.stop()
                update_library_daemon.stop()

            elif 'restart' == sys.argv[1]:
                daemon.restart()
                update_library_daemon.restart()

            elif 'debug' == sys.argv[1]:
                daemon.run()
                update_library_daemon.run()

            else:
                print "Unkown Command"
                sys.exit(2)
            sys.exit(0)
        else:
            print "Usage: %s start|stop|restart" % sys.argv[0]
            sys.exit(2)
    except Exception, e:
        print e
        #os.remove(log)
        raise
