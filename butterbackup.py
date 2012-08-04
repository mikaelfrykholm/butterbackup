#!/usr/bin/env python3
import os
import sys
from subprocess import Popen, PIPE
import shlex
import datetime

def backup_host(host, base_dir, fp):
    dest_dir = os.path.join(base_dir, host, "latest")
    if not os.path.exists(base_dir):
        print("New host",host,".")
        run("btrfs subvol create %s"% os.path.join(base_dir, host)) 
        os.makedirs(dest_dir)
    command = ("rsync -a --numeric-ids --delete --delete-excluded --human-readable --inplace ")
    excludes = fp.readline()[:-1]
    (stdout,stderr) = run(command + excludes + " root@%s:/ "%(host) + dest_dir)
    if stdout:
        print(stdout)
    if stderr:
        print(stdout)
    run("btrfs subvol snapshot %s %s"%(os.path.join(base_dir, host),os.path.join(base_dir, host, datetime.datetime.now().date().strftime("%F"))))
    
def run(cmd):
    (stdout, stderr) = Popen(shlex.split(cmd), stdout=PIPE).communicate()
    if stdout:
        stdout = stdout.decode('utf-8')
    if stderr:
        stderr = stderr.decode('utf-8')   
    return(stdout, stderr)

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("You need to be root. Otherwise all permissions will be lost.")
        sys.exit(-1)
    base_path="/etc/butterbackup"
    dest_dir="/mnt/data2"
    if not os.path.exists(base_path):
        print("No hosts to backup, please place them in",base_path)
        sys-exit(-1)
    hosts = os.listdir(base_path)
    for host in hosts:
        fp = open(os.path.join(base_path, host),"r")
        backup_host(host, dest_dir, fp)
    sys.exit(0)
