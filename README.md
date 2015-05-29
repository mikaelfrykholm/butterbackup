butterbackup
============

Butterbackup is a backup system which stores snapshots in btrfs on a central server. A web gui allows for simple restore of files. 

For now it is rather crude. To get started backing up some manual work is needed.
<pre lang="bash"><code>
Create /etc/butterbackup
# cat > /etc/butterbackup/default.cfg
[DEFAULT]
exclude = /proc/, /sys, /tmp, /dev, /run
store_dir = /mnt/data
keep=10
(ctrl-d to exit)
# touch /etc/butterbackup/machine1.example.com
# touch /etc/butterbackup/machine2.example.com
# ssh-copy-id root@machine1.example.com
# ssh-copy-id root@machine2.example.com
# mkdir /mnt/data
# mkfs.btrfs /dev/sdb1
# mount /dev/sdb1 /mnt/data
</code></pre>

To override the default setting for a specific host do:
<pre lang="bash"><code>
cat > /etc/butterbackup/machine1.example.com
[host]
exclude = /proc/, /sys, /tmp, /dev, /run, /home/mikael/.gvfs, /.snapshots
keep=20
</code></pre>
