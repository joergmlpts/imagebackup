Usage
=====

At a low level, **imagebackup** provides Python code to read the building
blocks - headers, bitmaps, and blocks - of
`partclone <https://partclone.org/>`_,
`partimage <https://www.partimage.org/>`_ and
`ntfsclone <https://linux.die.net/man/8/ntfsclone>`_ backup images. These
components may be used in other Python projects. They are described in the
:ref:`api` section.

At a higher level, :ref:`utility` based on this low-level code are
also included. Their features are as follows:

* They read partclone, partimage and ntfsclone images, verify checksums and
  dump headers.

* They mount a partclone, partimage  or ntfsclone image - the backup of a
  partition - as a virtual partition.

These virtual partitions have the contents of the partition. They are created
without allocating additional disk space. Just like a restored partition, for
example, a virtual partition can be subjected to a file system consistency
check (`fsck`).

The virtual partition can be mounted as a file system. This is done with the
help of a loop device and allows you to inspect the contents. Individual
files and directories can be copied from image backups.

A virtual partition is read-only and cannot be written to.

.. _installation:

Installation
------------

To use imagebackup, install it using pip. Imagebackup has four depencencies,
the packages tqdm, pyfuse3, pyzstd, and lz4.

On Ubuntu Linux - and perhaps other Debian-based distributions - these
dependencies can be installed with:

.. code-block:: console

   $ sudo apt install -y python3-pip libfuse3-dev python3-tqdm python3-pyfuse3 python3-lz4
   $ pip3 install imagebackup

On other platforms, install package ``libfuse3-dev`` or ``fuse3-devel`` with
the distribution's package manager before installing imagebackup. This will
allow pip to install imagebackup's dependency ``pyfuse3`` successfully.

After ``libfuse3-dev`` (Debian, Ubuntu, ...) or ``fuse3-devel`` (Red Hat,
Fedora, ...) has been installed, invoke pip3 or pip to install imagebackup:

.. code-block:: console

   $ pip install imagebackup


.. _utility:

Utilities vpartclone, vpartimage and vntfsclone
-----------------------------------------------

Utilities to mount partclone, partimage and ntfsclone image backups as virtual
partitions are included in imagebackup. These utilities can be called as
commands``vpartclone``, ``vpartimage`` and ``vntfsclone``

.. code-block:: console

   $ vpartclone -h
   $ vpartimage -h
   $ vntfsclone -h

The utilities have several options. They are typically called with a
single-file, uncompressed and unencrypted partclone or ntfsclone image and the
``-m`` or ``--mountpoint`` option:

.. code-block:: console

   $ mkdir -p ~/mnt; vpartclone nvme0n1p3.img -m ~/mnt

   Virtual partition provided as '/home/user/mnt/nvme0n1p3'.

   The file system of this virtual partition can be checked with this command:
      ntfsfix --no-action /home/user/mnt/nvme0n1p3

   This virtual partition can be mounted as a read-only filesystem at '/home/user/mnt' with this command:
      sudo mount -t ntfs /home/user/mnt/nvme0n1p3 /home/user/mnt -o loop,ro

   Forking subprocess to enter event-loop. When done unmount '/home/user/mnt' to
   quit this event-loop and its subprocess:
      sudo umount /home/user/mnt; umount /home/user/mnt

An empty directory ``mnt`` is created in the home directory and ``mnt`` is
passed to the utilty with the ``-m`` or ``--mountpoint`` option. The utility
will mount the virtual partition to that mount point. We can check it with the
usual commands:

.. code-block:: console

   $ ls -lh ~/mnt
   total 0
   -r--r----- 1 user user 476G Aug 13 13:19 nvme0n1p3

This virtual partition looks like a big file. It does not actually allocate
any disk space, though. Note that the virtual partition is write-protected.
It cannot be modified in any way.

We can try to dump its contents:

.. code-block:: console

   $ xxd -g1 ~/mnt/nvme0n1p3 | head
   00000000: eb 52 90 4e 54 46 53 20 20 20 20 00 02 08 00 00  .R.NTFS    .....
   00000010: 00 00 00 00 00 f8 00 00 3f 00 ff 00 00 a8 08 00  ........?.......
   00000020: 00 00 00 00 80 00 80 00 8e b2 72 3b 00 00 00 00  ..........r;....
   00000030: 00 00 0c 00 00 00 00 00 02 00 00 00 00 00 00 00  ................
   00000040: f6 00 00 00 01 00 00 00 96 7d 93 64 be 93 64 78  .........}.d..dx
   00000050: 00 00 00 00 fa 33 c0 8e d0 bc 00 7c fb 68 c0 07  .....3.....|.h..
   00000060: 1f 1e 68 66 00 cb 88 16 0e 00 66 81 3e 03 00 4e  ..hf......f.>..N
   00000070: 54 46 53 75 15 b4 41 bb aa 55 cd 13 72 0c 81 fb  TFSu..A..U..r...
   00000080: 55 aa 75 06 f7 c1 01 00 75 03 e9 dd 00 1e 83 ec  U.u.....u.......
   00000090: 18 68 1a 00 b4 48 8a 16 0e 00 8b f4 16 1f cd 13  .h...H..........

This dump absolutely looks like an NTFS partition.

*vpartclone* suggested two commands when it mounted the virtual partition, a
``fsck`` command and a mount command for that virtual partition. We will run
the ``fsck`` command first:

.. code-block:: console

   $ ntfsfix --no-action /home/user/mnt/nvme0n1p3
   Mounting volume... OK
   Processing of $MFT and $MFTMirr completed successfully.
   Checking the alternate boot sector... BAD
   Error: Failed to fix the alternate boot sector

Even the ``ntfsfix`` command accepts this virtual partition as a real partition.

Finally, we mount the virtual partition. Note that we mount it over ``~/mnt``.
When we are done, we have to unmount ``~/mnt`` twice, once with ``sudo`` for
the  NTFS partition and then a second time as regular user to unmount the
virtual partition.

.. code-block:: console

   $ sudo mount -t ntfs /home/user/mnt/nvme0n1p3 /home/user/mnt -o loop,ro
   [sudo] password for user:

There is no message and the NTFS file system of the partition is mounted:

.. code-block:: console

   $ mount | tail -2
   vpartclone on /home/user/mnt type fuse (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000,default_permissions,allow_other)
   /home/user/mnt/nvme0n1p3 on /home/user/mnt type fuseblk (ro,relatime,user_id=0,group_id=0,allow_other,blksize=4096)

Finally, we can access the NTFS file system:

.. code-block:: console

   $ ls ~/mnt/Windows/
   appcompat         csup.txt                    GameBarPresenceWriter   lsasetup.log         Provisioning       SoftwareDistribution   UUS
   apppatch          Cursors                     Globalization           Media                regedit.exe        Speech                 Vss
   AppReadiness      debug                       Help                    mib.bin              Registration       Speech_OneCore         WaaS
   AsPEToolVer.txt   diagerr.xml                 HelpPane.exe            Microsoft.NET        rescache           splwow64.exe           Web
   assembly          diagnostics                 hh.exe                  Migration            Resources          System                 WindowsShell.Manifest
   ASUS              DiagTrack                   IdentityCRL             ModemLogs            SchCache           System32               winhlp32.exe
   ASUS_IMAGE.Ver    diagwrn.xml                 IME                     notepad.exe          schemas            SystemApps             win.ini
   bcastdvr          DigitalLocker               ImmersiveControlPanel   OCR                  security           system.ini             WinSxS
   bfsvc.exe        'Downloaded Program Files'   INF                     OEM                  ServiceProfiles    SystemResources        WMSysPr9.prx
   Boot              DtcInstall.log              InputMethod            'Offline Web Pages'   ServiceState       SystemTemp             write.exe
   bootstat.dat      ELAMBKUP                    Installer               Panther              servicing          SysWOW64               WUModels
   Branding          en-US                       Inst_AsModelCopy.log    Performance          Setup              TAPI
   BrowserCore       es-ES                       L2Schemas               PFRO.log             setupact.log       Tasks
   CbsTemp           explorer.exe                LanguageOverlayCache    PLA                  setuperr.log       Temp
   comsetup.log      Firmware                    LiveKernelReports       PolicyDefinitions    ShellComponents    tracing
   Containers        Fonts                       Log                     Prefetch             ShellExperiences   twain_32
   Core.xml          fr-FR                       Logs                    PrintDialog          SKB                twain_32.dll

At this point we can copy files and directories from the virtual partition.

When we are done, we unmount the NTFS partition with sudo:

.. code-block:: console

   sudo umount ~/mnt

and unmount the virtual partition as a regular user:

.. code-block:: console

   umount ~/mnt


Command-line arguments
----------------------

Besides the *-m/--mountpoint* options, there are several other options. This
section introduces them all.

.. code-block:: console

   usage: vpartclone [-h] [-m MOUNTPOINT] [-v] [-d] [-c] [-i INDEX_SIZE] image

   Mount partclone image backup as virtual partition.

   positional arguments:
     image                 partition image to read

   options:
     -h, --help            show this help message and exit
     -m MOUNTPOINT, --mountpoint MOUNTPOINT
                           mount point for virtual partition; an empty directory
     -v, --verbose         dump header and bitmap info
     -d, --debug_fuse      enable FUSE filesystem debug messages
     -c, --crc_check       verify all checksums in image (slow!)
     -i INDEX_SIZE, --index_size INDEX_SIZE
                           Size parameter for building bitmap index; leave
                           unchanged unless memory usage too high.
                           Increase size to reduce memory usage by doubling or
                           quadrupling the number repeatedly (default 1024).
     -q, --quiet           suppress progress bar in crc check

image
  An image file written by *partclone* is the only argument needed. For
  virtual partitions, this image file must be a regular file. Split files must
  be contatenated into a single file and compressed files must be uncompressed.

verbose
  The *-v/--verbose* options cause the header and bitmap information to be
  dumped.

mountpoint
  The argument of the *-m/--mountpoint* option is an empty directory where the
  virtual partition will be created.

debug_fuse
  The *-d/--debug_fuse* option enables debug messages of the filesystem in
  userspace (FUSE) code that is invoked for the virtual partition. This option
  will cause fuse to run in the foreground. Use another window to unmount the
  virtual partition.

crc_check
  The *-c/--crc_check* option requests that all checksums for data blocks be
  checked. Enabling this adds a lengthy pass through an entire image file before
  creating the virtual partition.

index_size
  The *-i/--index_size* option is available to reduce the memory consumption of
  *vpartclone* at the expense of runtime if necessary.

  When the virtual partition is active, *vpartclone* must read blocks
  from the image file in an any order. Image files are not organized to alow to
  quickly look up the location of a given data block in the image file. A bitmap
  allows to determine in constant time whether a block is in the image file. If
  a block is in the image file, the total number of bits set from the
  beginning of that bitmap needs to be counted to determine the location of the
  block's data in the image.

  The bitmap can be millions, even tens or hundreds of millions of bytes in
  size. To avoid counting the bits set in the bitmap from the beginning for
  each block, an index has been implemented. The bitmap is indexed so that for
  each block access, only bits in a small range need to be counted. The
  *index_size* option specifies the size of this range. It defaults to 1024
  bits, which is 128 bytes of the bitmap.

  If *vpartclone* ever runs out of memory, this default value can be doubled or
  quadrupled. This may double or quadruple the time for each block access but
  will reduce the memory usage by the factor of two or four.

  Only *vpartclone* has this option. ntfsclone images do not contain bitmaps
  and *vntfsclone* does not need this option.
  
quiet
  The *-q/--quiet* option suppresses the progress bar that is shown whenever the
  entire image file is read. The entire file is read when *vntfsclone* builds
  an index for a virtual partition. The entire file is also read when
  *vpartclone* verifies checksums.
