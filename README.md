# vntfsclone, vpartclone & partimage - Mount Image Backups as Virtual Partitions

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

A virtual partition is read-only and cannot be written to.

## Usage

`vpartclone`, `vpartimage` and `vntfsclone` are command-line scripts with
several options.
They are typically  called with a single-file, uncompressed and unencrypted
partclone or ntfsclone image and the `-m` or `--mountpoint` option:

```
$ mkdir -p ~/mnt; vpartclone nvme0n1p3.img -m ~/mnt

Virtual partition provided as '/home/user/mnt/nvme0n1p3'.

The file system of this virtual partition can be checked with this command:
   ntfsfix --no-action /home/user/mnt/nvme0n1p3

This virtual partition can be mounted as a read-only filesystem at '/home/user/mnt' with this command:
   sudo mount -t ntfs /home/user/mnt/nvme0n1p3 /home/user/mnt -o loop,ro

Forking subprocess to enter event-loop. When done unmount '/home/user/mnt' to quit this event-loop and its subprocess:
   sudo umount /home/user/mnt; umount /home/user/mnt
```

An empty directory `mnt` is created in the home directory and `mnt` is passed to
`vpartclone` with the `-m` or `--mountpoint` option. `vpartclone` will mount the
virtual partition to that mount point. We can check it with the usual
commands:

```
$ ls -lh ~/mnt
total 0
-r--r----- 1 user user 476G Aug 13 13:19 nvme0n1p3
```

This virtual partition looks like a big file. It does not actually allocate
any disk space, though. Note that the virtual partition is write-protected.
It cannot be modified in any way.

We can try to dump its contents:

```
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
```

This dump absolutely looks like an NTFS partition.

`vpartclone` suggested two commands when it mounted the virtual partition, a
`fsck` command and a mount command for that virtual partition. We will run the
`fsck` command first:

```
$ ntfsfix --no-action /home/user/mnt/nvme0n1p3
Mounting volume... OK
Processing of $MFT and $MFTMirr completed successfully.
Checking the alternate boot sector... BAD
Error: Failed to fix the alternate boot sector
```

Even the `ntfsfix` command accepts this virtual partition as a real partition.

Finally, we mount the virtual partition. Note that we mount it over `~/mnt`.
When we are done, we have to unmount `~/mnt` twice, once with `sudo` for the 
NTFS partition and then a second time as regular user to unmount the virtual
partition.

```
$ sudo mount -t ntfs /home/user/mnt/nvme0n1p3 /home/user/mnt -o loop,ro
[sudo] password for user:
```

There is no message and the NTFS file system of the partition is mounted:

```
$ mount | tail -2
vpartclone on /home/user/mnt type fuse (rw,nosuid,nodev,relatime,user_id=1000,group_id=1000,default_permissions,allow_other)
/home/user/mnt/nvme0n1p3 on /home/user/mnt type fuseblk (ro,relatime,user_id=0,group_id=0,allow_other,blksize=4096)
```

Finally, we can access the NTFS file system:
```
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
```

At this point we can copy files and directories from the virtual partition.

When we are done, we unmount the NTFS partition with sudo:

```
sudo umount ~/mnt
```

and unmount the virtual partition as a regular user:

```
umount ~/mnt
```


## Command-line arguments

Besides the `-m/--mountpoint` options, there are several other options. This
section introduces them all.

```
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
```

### image file

An image written by `partclone` is the only argument needed. For virtual
partitions, this image file must be a regular file. Split files must be
contatenated into a single file and compressed files must be uncompressed.

### verbose

The `-v/--verbose` options cause the header and bitmap information to be dumped.

### mountpoint

The argument of the `-m/--mountpoint` option is an empty directory where the
virtual partition will be created.

### debug_fuse

The `-d/--debug_fuse` option enables debug messages of the filesystem in
userspace (FUSE) code that is invoked for the virtual partition. This option
will cause fuse to run in the foreground. Use another window to unmount the
virtual partition.

### crc_check

The `-c/--crc_check` option requests that all checksums for data blocks be
checked. Enabling this adds a lengthy pass through an entire image file before
creating the virtual partition.

### index_size

The `-i/--index_size` option is available to reduce the memory consumption of
`vpartclone` at the expense of runtime if necessary.

When the virtual partition is active, `vpartclone` must read blocks
from the image file in an any order. Image files are not organized to alow to
quickly look up the location of a given data block in the image file. A bitmap
allows to determine in constant time whether a block is in the image file. If a
block is in the image file, the total number of bits set from the
beginning of that bitmap needs to be counted to determine the location of the
block's data in the image.

The bitmap can be millions, even tens or hundreds of millions of bytes in size.
To avoid counting the bits set in the bitmap from the beginning for each 
block, an index has been implemented. The bitmap is indexed so that for
each block access, only bits in a small range need to be counted. The
`index_size` option specifies the size of this range. It defaults to 1024
bits, which is 128 bytes of the bitmap.

If `vpartclone` ever runs out of memory, this default value can be doubled or
quadrupled. This may double or quadruple the time for each block access but
will reduce the memory usage by the factor of two or four.

Only `vpartclone` has this option. ntfsclone images do not contain bitmaps
and `vntfsclone` does not need this option.

### quiet

The `-q/--quiet` option suppresses the progress bar that is shown whenever the
entire image file is read. The entire file is read when `vntfsclone` builds
an index for a virtual partition. The entire file is also read when
`vpartclone` verifies checksums.


## Installation

This code requires Python 3.8 or later and the additional packages `tqdm`,
`pyfuse3`, `pyzstd`, and `lz4`.

On Ubuntu Linux - and perhaps other Debian-based distributions - these
dependencies can be installed with:

```
sudo apt install -y python3-pip git pkg-config libfuse3-dev python3-tqdm python3-pyfuse3 python3-lz4
pip3 install git+https://github.com/joergmlpts/imagebackup
```

On Fedora Linux - and other Red Hat distributions - the dependencies can be
installed with:

```
sudo dnf install gcc fuse3-devel python3-tqdm python3-pip python3-devel
pip3 install git+https://github.com/joergmlpts/imagebackup
```

On other platforms `pip` will install the dependencies:

```
pip install git+https://github.com/joergmlpts/imagebackup
```

where `tqdm` should install without issues but `pyfuse3`, when installed with
`pip`, needs the development package for `fuse3`. This package is called
`libfuse3-dev` or `fuse3-devel` and it must be installed before `pip` is
invoked as seen above for Ubuntu and Fedora. The chapter
[Pyfuse3 Installation](http://www.rath.org/pyfuse3-docs/install.html)
has more information about the installation of `pyfuse3`.

Please note that this utility relies on the filesystem in userspace (FUSE)
functionality. It will not run on Windows and any other platform that does not
have FUSE.

## Python API

Partclone and partimage images consist of three components, a header (4
headers in partimage), a bitmap and blocks of data. A description of the
[partclone file format](https://github.com/Thomas-Tsai/partclone/blob/master/IMAGE_FORMATS.md)
is available. This package has classes to read and process these three
components.

Ntfsclone images do not contain a bitmap. They consist of a header and blocks
of used blocks and counts of unused blocks of data.

### Classes PartClone, PartImage and NtfsClone

Classes `PartClone`, `PartImage` and `NtfsClone` are instantiated with an open
file and its filename. They read the header and bitmap of a partclone or
partimage image. If the file does not contain a supported image, they raise
exception `ImageBackupException`.

```
from imagebackup.imagebackup import ImageBackupException
from imagebackup.ntfsclone import NtfsClone
from imagebackup.partclone import PartClone
from imagebackup.partimage import PartImage

with open('sda1.img', 'rb') as file:

    try:

        image = PartClone(file, 'sda1.img')

        print(image)

    except ImageBackupException as e:
        print('Failed to read image:', e)
```

If the image file can be opened, the header is printed like this:

```
Partclone Header
================
partclone version 0.3.24
fs type           BTRFS
fs total size     274,994,298,880 (256.1 GB)
fs total blocks   16,784,320
fs used blocks    968,580 (14.8 GB)     used block count based on super-block
fs_used_bitmap    1,168,685 (17.8 GB)   used block count based on bitmap
fs block size     16384
image version     2
cpu bits          64
checksum mode     CRC32
checksum size     4
checksum blocks   64
checksum reseed   True
bitmap mode       BIT
header_crc32      0xae9d1efd
bitmap            2,098,040 bytes (2.0 MB)
bitmap_crc32      0x6dbca530
blocks_section    at 2,098,154 in img file
block_offset_size 1024
block_offsets     0 instances
```

The image can also be read from a pipe, a regular file is not necessary.

`partclone` and `partimage` images contain a bitmap, `ntfsclone` images do not.
The bitmap represents each block with one bit and indicates whether the block
is in use or not. Only if a block is in use its data is saved to the image file.
There is not much besides the actual bitmap, just a checksum. The members
`block_offset_size` and `block_offsets` have not been read from the image file.
They implement indexing which allows us to read data blocks from the image
quickly and in an arbitray order.

### Reading Blocks

Once the header and bitmap have been read, we can read all used blocks from the
partition. Method `blockReader` reads all used blocks in sequence:

```
image.blockReader(progress_bar: bool = True, verify_crc: bool = False,
                  fn: Optional[Callable[[int,bytes],None]] = None) -> None:
```

By default, `blockReader` shows a progress bar as it reads all the data from
the image. Parameter `progress_bar` can be set to `False` to suppress the
progress bar.

By default, `blockReader` does not verify checksums for the blocks. Parameter
`verity_crc` can be set to `True` to cause `blockReader` to verify checksums.

Parameter `fn` is `None` by default. A function can be passed which will be
called with the offset into the partition and the data for each block. This
function can be used to restore a partition:

```
with open('/dev/sda1', 'rb+') as f_out:

    def write_block(offset: int, block: bytes) -> None:
        f_out.seek(offset)
        f_out.write(block)

    image.blockReader(fn=write_block)
```

The function is only called for used blocks. Unused blocks are not even stored
in the image file. However, since `blockReader` calls the function strictly in
ascending order of the offset, unused blocks can be written as well. The
following code fills them with `0xdeadbeef`, a pattern that is easily
recognized in hex dumps:

```
with open('sda1.vol', 'wb') as f_out:
    block_size  = image.blockSize()
    last_offset = 0
    empty_block = bytes([0xde, 0xad, 0xbe, 0xef] * (block_size // 4))

    def write_unused(offset: int) -> None:
        global last_offset
        while last_offset < offset:
            f_out.write(empty_block)
            last_offset += block_size

    def write_block(offset: int, block: bytes) -> None:
        global last_offset
        write_unused(offset)
        f_out.write(block)
        last_offset = offset + len(block)

    image.blockReader(fn=write_block)
    write_unused(image.totalBlocks() * block_size)
```

Note that `write_block` does not call `f_out.seek` anymore. In this scenario
the output file is written sequentially.

### Class BlockIO

There are situations where the blocks in an image file need to be read in
random order. Class `BlockIO` allows random access to arbitrary ranges of bytes.

The image file cannot be read sequentially in this scenario. It has to be a
regular file; a pipe or compresed files will not work.

```
from imagebackup.blockio import BlockIO

blockio = BlockIO(image)

# read 42 bytes at offset 100000 and dump them in hex
print(' '.join(f'{b:02x}' for b in blockio.read_data(offset=100000, size=42)))
```
