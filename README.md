butterbackup
============

Butterbackup is a backup system which stores snapshots in btrfs on a central server. A web gui allows for simple restore of files. 

For now it is rather crude. To get started backing up some manual work is needed.
Create /etc/butterbackup
# echo "--exclude /tmp --exclude /proc --exclude /sys --exclude /dev" > /etc/butterbackup/machine1.example.com
# cp /etc/butterbackup/machine1.example.com /etc/butterbackup/machine2.example.com
# ssh-copy-id root@machine1.example.com
# ssh-copy-id root@machine1.example.com
# mkdir /mnt/data2
# mkfs.btrfs /dev/sdb1
# mount /dev/sdb1 /mnt/data2  #hardcoded for now