#!/usr/bin/env python3

import argparse
import asyncio
import configparser
import datetime
import email.message
import functools
import logging
import operator
import os
import platform
import smtplib
import sys


class BackupFailedException(Exception):
    pass


class Host:
    def __init__(self, name, config):
        self.name = name
        self.config = config

        # Status
        self.completed = False
        self.failed = False

        # Output from commands
        self.output = []

        # Initialize host from configuration if provided
        if not self.config.has_section('host'):
            self.config.add_section('host')

        # Configuration
        self.store_dir = self.config['host']['store_dir']
        self.host_dir = os.path.join(self.store_dir, name)
        self.subvol_dir = os.path.join(self.host_dir, 'latest')
        self.keep = int(self.config.get('host', 'keep', fallback=-1))
        self.user = self.config['host'].get('user', 'root')
        self.email = self.config['host'].get('email', None)
        self.report = self.config['host'].get('report', 'never')

    async def backup(self):
        if not os.path.exists(self.host_dir):
            logger.info('{}: Creating host directory'.format(self.name))
            if not args.dry_run:
                os.makedirs(self.host_dir)

        if not os.path.exists(self.subvol_dir):
            if not await self._create_subvolume(self.subvol_dir):
                raise BackupFailedException()

        if not await self._sync_new_data():
            raise BackupFailedException()

        todays_date = datetime.datetime.now().date().strftime('%F')
        if os.path.exists(os.path.join(self.host_dir, todays_date)):
            # There is a snapshot for today, removing it and creating a new one
            if not await self._delete_subvolume(todays_date):
                raise BackupFailedException()

        if not await self._create_snapshot(todays_date):
            raise BackupFailedException()

        self.completed = True

    async def prune_snapshots(self):
        if self.keep == -1:
            logger.warning('{}: Not pruning snapshots since keep is not set'.format(self.name))
            return

        if not os.path.exists(self.host_dir):
            logger.info('{}: Not pruning snapshots - none exists'.format(self.name))
            return

        snapshots = sorted([snap for snap in os.listdir(self.host_dir) if not snap == 'latest'], reverse=True)
        while len(snapshots) > self.keep:
            snapshot = snapshots.pop()
            await self._delete_subvolume(snapshot)

    def send_report(self):
        if self.report == 'never':
            return

        if self.report == 'error' and self._backup_successful():
            return

        if self.email == None or len(self.email) == 0:
            logger.error('{}: Not sending backup report since email configuration is missing or empty'.format(self.name))
            return

        logger.info('{}: Sending backup report to {}'.format(self.name, self.email))

        if self._backup_successful():
            status = 'SUCCESS'
        else:
            status = 'FAILURE'

        timestamp = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()

        content = []
        content.append('Backup report')
        content.append('')
        content.append('Host: {}'.format(platform.node()))
        content.append('Node: {}'.format(self.name))
        content.append('Date: {}'.format(timestamp))
        content.append('Status: {}'.format(status))

        if args.dry_run:
            content.append('')
            content.append('Backup performed in dry-run mode')
            content.append('No data was stored')

        if len(self.output) > 0:
            content.append('')
            content.append('Output:')
            content += self.output

        content.append('')
        content.append('/Your friendly backup robot')

        message = email.message.EmailMessage()
        message['Subject'] = 'Backup report for {}: {}'.format(self.name, status)
        message['From'] = 'Backup Robot <backup@example.com>'
        message['To'] = self.email
        message['Reply-To'] = 'Backup Operators <administrator@example.com>'
        message.set_content('\n'.join(content))

        logger.debug('The following message will be sent to {}:'.format(self.email))
        for line in message.as_string().rstrip().split('\n'):
            logger.debug(line)

        try:
            with smtplib.SMTP('localhost') as smtp:
                smtp.send_message(message)
        except:
            logger.error('{}: Sending backup report to {} failed'.format(self.name, self.email))

    async def _create_snapshot(self, snapshot):
        logger.info('{}: Creating snapshot {}'.format(self.name, snapshot))
        if args.dry_run:
            logger.info('{}: Creating snapshot {} skipped with -n'.format(self.name, snapshot))
            return True
        return_code = await self._run_command('/bin/btrfs subvol snapshot -r {} {}'.format(self.subvol_dir, os.path.join(self.host_dir, snapshot)))
        if return_code != 0:
            logger.error('{}: Creating snapshot {} failed'.format(self.name, snapshot))
            return False
        else:
            return True

    async def _create_subvolume(self, subvolume):
        logger.info('{}: Creating subvolume {}'.format(self.name, subvolume))
        if args.no_act:
            logger.info('{}: Creating subvolume {}, skipped due to -n'.format(self.name, subvolume))
            return True

        return_code = await self._run_command('/bin/btrfs subvol create {}'.format(subvolume))
        if return_code != 0:
            logger.error('{}: Creating subvolume {} failed'.format(self.name, subvolume))
            return False
        else:
            return True

    async def _delete_subvolume(self, subvolume):
        logger.info('{}: Removing subvolume {}'.format(self.name, subvolume))
        return_code = await self._run_command('/bin/btrfs subvol delete {}'.format(os.path.join(self.host_dir, subvolume)))
        if return_code != 0:
            logger.error('{}: Removing subvolume {} failed'.format(self.name, subvolume))
            return False
        else:
            return True

    async def _sync_new_data(self):
        logger.info('{}: Syncing new data from remote host'.format(self.name))
        return_code = await self._run_command(self._make_rsync_command())
        if return_code not in (0, 24):
            logger.error('{}: Syncing new data from remote host failed'.format(self.name))
            return False
        else:
            return True

    def _make_rsync_command(self):
        rsync_command = '/usr/bin/rsync -a --acls --xattrs --whole-file --numeric-ids --delete --delete-excluded --human-readable --inplace '
        if self.config.has_option('host', 'include'):
            includes = ' --include ' + ' --include '.join(self.config.get('host', 'include').split(','))
            rsync_command = rsync_command + includes
        if self.config.has_option('host', 'exclude'):
            excludes = ' --exclude ' + ' --exclude '.join(self.config.get('host', 'exclude').split(','))
            rsync_command = rsync_command + excludes
        return '{} {}@{}:/ {}'.format(rsync_command, self.user, self.name, self.subvol_dir)

    async def _run_command(self, command):
        logger.debug('{}: Running command: {}'.format(self.name, command))

        if args.dry_run:
            return 0

        process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        logger.debug('{}: Command status code: {}'.format(self.name, process.returncode))

        if len(stdout) > 0:
            for line in str(stdout, 'utf-8').rstrip().split('\n'):
                self.output.append(line)
                logger.debug('{}: Output: {}'.format(self.name, line))

        if len(stderr) > 0:
            for line in str(stderr, 'utf-8').rstrip().split('\n'):
                self.output.append(line)
                logger.error('{}: Error: {}'.format(self.name, line))

        return process.returncode

    def _backup_successful(self):
        return self.completed == True and self.failed == False


async def backup(host_name):
    config_file = os.path.join(args.configuration, host_name)

    if not os.path.exists(config_file):
        logger.error('{}: Skipping host due to missing configuration file'.format(host_name))
        raise BackupFailedException()

    try:
        host_config = configparser.ConfigParser(strict=False)

        # Load default host configuration
        with open(os.path.join(args.configuration, 'default.cfg'), 'r') as default_config:
            host_config.read_file(default_config)
        host_config.read(config_file)
    except configparser.Error:
        logger.error('{}: Skipping host due to configuration file error'.format(host_name))
        raise BackupFailedException()

    host = Host(host_name, host_config)
    try:
        await host.prune_snapshots()
        await host.backup()
    except BackupFailedException:
        host.failed = True
        raise
    finally:
        if args.send_reports:
            host.send_report()


async def worker(queue):
    failed_hosts = []

    while not queue.empty():
        host = await queue.get()

        try:
            await asyncio.create_task(backup(host))
        except BackupFailedException:
            failed_hosts.append(host)
            set_status(1)
        queue.task_done()

    return failed_hosts


async def main():
    if not os.path.exists(args.configuration):
        raise ValueError('No configuration directory found')

    if os.geteuid() != 0:
        raise Exception('Need to run as root or permissions will be lost')

    if len(args.hosts) > 0:
        hosts = args.hosts
    else:
        hosts = os.listdir(args.configuration)

    queue = asyncio.Queue()
    for host in hosts:
        if host == 'default.cfg' or host.startswith('.'):
            continue
        queue.put_nowait(host)

    workers = [asyncio.create_task(worker(queue)) for x in range(args.concurrency)]
    (failed, done) = await asyncio.gather(*workers, return_exceptions=True)
    await queue.join()
    failed_hosts = functools.reduce(operator.add, map(lambda task: task.result(), done),[])
    if len(failed_hosts) > 0:
        logger.error('Back up failed: {}'.format(', '.join(failed_hosts)))


def set_status(new_status):
    global status
    if status != new_status:
        status = new_status


def parse_command_line():
    def check_concurrency(value):
        try:
            as_integer = int(value)
            if as_integer < 1:
                raise ValueError()
            return as_integer
        except ValueError:
            raise argparse.ArgumentTypeError('should be a positive non-zero integer')

    parser = argparse.ArgumentParser(prog='butterbackup', description='Back up remote systems to local storage')
    parser.add_argument('--concurrency', default=1, type=check_concurrency, help='Concurrency level')
    parser.add_argument('--configuration', default='/etc/butterbackup', help='Configuration directory')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Run without performing any changes')
    parser.add_argument('--log-level', default='INFO', help='Log level')
    parser.add_argument('--send-reports', action='store_true', help='Send backup reports if configured')
    parser.add_argument('hosts', nargs='*', help='Lists of hosts to back up (default all)')
    return parser.parse_args()


def configure_logging():
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Console logging using variable log level
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(args.log_level)
    logger.addHandler(stream_handler)

    # File logging is always enabled
    file_handler = logging.FileHandler('/var/log/butterbackup/butterbackup.log')
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    logger.addHandler(file_handler)

    # This has to be set to the lowest possible level of any of its handlers
    logger.setLevel(logging.DEBUG)


if __name__ == '__main__':
    status = 0

    try:
        logger = logging.getLogger(__name__)
        args = parse_command_line()
        configure_logging()
        asyncio.run(main())
    except Exception as e:
        logging.exception(e)
        set_status(1)

    sys.exit(status)
