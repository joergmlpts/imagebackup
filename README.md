# vntfsclone, vpartclone & vpartimage - Mount Image Backups as Virtual Partitions

At a low level, this package provides Python code to read the building blocks -
headers, bitmaps, and blocks - of [partclone](https://partclone.org/),
[partimage](https://www.partimage.org/) and
[ntfsclone](https://linux.die.net/man/8/ntfsclone) backup
images. These components may be used in other Python projects. Refer to the
[API documentation](https://imagebackup.readthedocs.io/en/latest/api.html)
for a comprehensive description of these components.

## Virtual Partitions

At a higher level, two command-line utilities based on this low-level code are
also included. Its features are as follows:
* They read partclone, partimage and ntfsclone images, verify checksums and
  dump headers.
* They mount partclone, partimage and ntfsclone images - the backup of a
  partition - as virtual partitions.

These virtual partitions have the contents of the partition. They are created
without allocating additional disk space. Just like a restored partition, for
example, a virtual partition can be subjected to a file system consistency
check (`fsck`).

A virtual partition can be mounted as a file system. This is done with the
help of a loop device and allows you to inspect the contents. Individual
files and directories can be copied from image backups.

# Full Documentation

Our documentation is at [imagebackup.readthedocs.org](https://imagebackup.readthedocs.org).

- [Utilities](https://imagebackup.readthedocs.io/en/latest/usage.html#utilities-vpartclone-vpartimage-and-vntfsclone)
- [Installation](https://imagebackup.readthedocs.io/en/latest/usage.html#installation)
- [API Introduction](https://imagebackup.readthedocs.io/en/latest/api.html)
- [API Reference](https://imagebackup.readthedocs.io/en/latest/api.html#detailed-api-documentation)
