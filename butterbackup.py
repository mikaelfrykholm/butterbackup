#!/usr/bin/env python3
import os
import sys
from subprocess import check_call, CalledProcessError
import shlex
import datetime
import configparser

class Host():
    def __init__(self, name, config):
        self.name = name
        self.config = config 
        if not self.config.has_section('host'):
            self.config.add_section('host')
        self.store_dir = self.config['host']['store_dir']
        self.host_dir = os.path.join(self.store_dir, name)
        self.subvol_dir = os.path.join(self.host_dir, "latest")
        self.keep = int(self.config.get("host", "keep", fallback=-1))

    def backup(self):
        if not os.path.exists(self.host_dir):
            print("New host",host,".")
            os.makedir(self.host_dir)
        if not os.path.exists(self.subvol_dir):
            try:
                check_call(shlex.split("btrfs subvol create %s"% self.subvol_dir))
            except CalledProcessError as ex:
                print("Failed to create subvol! Aborting backup.")
                return() 
            
        command = ("rsync -a --acls --xattrs --whole-file --numeric-ids --delete --delete-excluded --human-readable --inplace ")
        excludes = " --exclude " + " --exclude ".join(self.config.get("host", "exclude").split(',')) #FIXME
        try:
            print(command + excludes + " root@%s:/ "%(self.name) + self.subvol_dir)
            check_call(shlex.split(command + excludes + " root@%s:/ "%(self.name) + self.subvol_dir))
        except CalledProcessError as ex:
            if ex.returncode not in (12, 30):
                print("Rsync did not transfer anything from %s, skipping snapshot."%self.name)
                return()
        todays_date = datetime.datetime.now().date().strftime("%F")
        if os.path.exists(os.path.join(self.host_dir, todays_date)):
            #There is a snapshot for today, removing it and creating a new one
            try:
                check_call(shlex.split("btrfs subvol delete %s"%(os.path.join(self.host_dir, todays_date))))
            except CalledProcessError as ex: 
                pass    
        try:
            check_call(shlex.split("btrfs subvol snapshot -r %s %s"%(self.subvol_dir,os.path.join(self.host_dir, todays_date))))
        except CalledProcessError as ex: 
            pass

    def prune_snapshots(self):
        if self.keep == -1:
            print("No keep specified for %s, keeping all"%self.name)
            return

        snaps = sorted([snap for snap in os.listdir(self.host_dir) if not snap == "latest" ], reverse=True)
        while len(snaps) > self.keep:
            snap = snaps.pop()
            try:
                check_call(shlex.split("btrfs subvol delete %s"%(os.path.join(self.host_dir, snap))))
            except CalledProcessError as ex: 
                pass    

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
            if host == 'default.cfg':
                continue
            try:
                config = configparser.ConfigParser(strict=False)
                config.read_file(open(os.path.join(self.config_dir, 'default.cfg'),'r'))
                config.read(os.path.join(self.config_dir, host))
            except BaseException as ex:
                print("Config error for %s. Skipping host."%host)
                continue
            h = Host(host, config)
            h.prune_snapshots()
            h.backup()
    
if __name__ == "__main__":
    if os.geteuid() != 0:
        print("You need to be root. Otherwise all permissions will be lost.")
        sys.exit(-1)
    br = BackupRunner("/etc/butterbackup", "/mnt/data2")
    br.run()
    sys.exit(0)
