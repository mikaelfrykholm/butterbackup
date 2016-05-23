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
            print("New host",self.name,".")
            os.makedirs(self.host_dir)
        if not os.path.exists(self.subvol_dir):
            try:
                check_call(shlex.split("btrfs subvol create %s"% self.subvol_dir))
            except CalledProcessError as ex:
                print("Failed to create subvol! Aborting backup.")
                return() 
            
        command = ("rsync -a --acls --xattrs --whole-file --numeric-ids --delete --delete-excluded --human-readable --inplace ")
        if self.config.has_option("host", "include"):
            includes = " --include " + " --include ".join(self.config.get("host", "include").split(',')) #FIXME
            command = command + includes
        if self.config.has_option("host", "exclude"):
            excludes = " --exclude " + " --exclude ".join(self.config.get("host", "exclude").split(',')) #FIXME
            command = command + excludes
        try:
            print(command + " root@%s:/ "%(self.name) + self.subvol_dir)
            check_call(shlex.split(command + " root@%s:/ "%(self.name) + self.subvol_dir))
        except CalledProcessError as ex:
            if ex.returncode in (24,):
                pass
            else:
                print("Rsync error from %s, skipping snapshot. Rsync exit value=%s"%(self.name, ex.returncode))
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
        if not os.path.exists(self.host_dir):
            print("New host, no pruning needed")
            return
        snaps = sorted([snap for snap in os.listdir(self.host_dir) if not snap == "latest" ], reverse=True)
        while len(snaps) > self.keep:
            snap = snaps.pop()
            try:
                check_call(shlex.split("btrfs subvol delete %s"%(os.path.join(self.host_dir, snap))))
            except CalledProcessError as ex: 
                pass    

class BackupRunner():
    def __init__(self, config_dir):
        self.config_dir = config_dir
        if not os.path.exists(self.config_dir):
            print("No config found", self.config_dir)
            sys-exit(-1)

    def run(self, hostlist=None):
        self.hosts = hostlist or os.listdir(self.config_dir)

        for host in self.hosts:
            if host == 'default.cfg':
                continue
            try:
                configfile = os.path.join(self.config_dir, host)

                if not os.path.exists(configfile):
                    # Trigger logging in the except clause
                    raise BaseException()

                config = configparser.ConfigParser(strict=False)
                config.read_file(open(os.path.join(self.config_dir, 'default.cfg'),'r'))
                config.read(configfile)
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
    br = BackupRunner("/etc/butterbackup")

    hostlist = sys.argv[1:]
    br.run(hostlist=hostlist)

    sys.exit(0)

