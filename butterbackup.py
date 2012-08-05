#!/usr/bin/env python3
import os
import sys
from subprocess import check_call, CalledProcessError
import shlex
import datetime
class BackupRunner():
    def __init__(self, config_dir, dest_dir):
        self.config_dir = config_dir
        self.dest_dir = dest_dir
        if not os.path.exists(self.config_dir):
            print("No config found", self.config_dir)
            sys-exit(-1)

    def run(self):
        self.hosts = os.listdir(self.config_dir)
        for host in self.hosts:
            fp = open(os.path.join(self.config_dir, host),"r")
            self.backup_host(host, fp)
            fp.close()

    def backup_host(self, host, host_config):
        host_dir = os.path.join(self.dest_dir, host)
        subvol_dir = os.path.join(host_dir, "latest")
        if not os.path.exists(host_dir):
            print("New host",host,".")
            os.makedir(host_dir)
        if not os.path.exists(subvol_dir):
            try:
                check_call(shlex.split("btrfs subvol create %s"% subvol_dir))
            except CalledProcessError as ex:
                print("Failed to create subvol! Aborting backup.")
                return() 
            
        command = ("rsync -a --acls --xattrs --whole-file --numeric-ids --delete --delete-excluded --human-readable --inplace ")
        excludes = host_config.readline()[:-1]
        try:
            check_call(shlex.split(command + excludes + " root@%s:/ "%(host) + subvol_dir))
        except CalledProcessError as ex:
            if ex.returncode not in (12, 30, 255):
                print("Rsync did not transfer anything from %s, skipping snapshot."%host)
                return()
        todays_date = datetime.datetime.now().date().strftime("%F")
        if os.path.exists(os.path.join(host_dir, todays_date)):
            #There is a snapshot for today, removing it and creating a new one
            try:
                check_call(shlex.split("btrfs subvol delete %s"%(os.path.join(host_dir, todays_date))))
            except CalledProcessError as ex: 
                pass    
        try:
            check_call(shlex.split("btrfs subvol snapshot -r %s %s"%(subvol_dir,os.path.join(host_dir, todays_date))))
        except CalledProcessError as ex: 
            pass

if __name__ == "__main__":
    if os.geteuid() != 0:
        print("You need to be root. Otherwise all permissions will be lost.")
        sys.exit(-1)
    br = BackupRunner("/etc/butterbackup", "/mnt/data2")
    br.run()
    sys.exit(0)
