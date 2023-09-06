import argparse, asyncio, errno, io, os, stat, traceback

import pyfuse3 # install with "pip install pyfuse3"; on Ubuntu use "sudo apt install python3-pyfuse3"
import pyfuse3_asyncio

from .imagebackup import ImageBackup, ImageBackupException
from .blockio import BlockIO


class ImageBackupFS(pyfuse3.Operations):
    """
    This class implements a FUSE filesystem on top of a backup image.

    A single read-only file is shown under the moint point. Its file
    is derived from the image filename.

    This file can be read and it refects the partition stored in the backup
    image. Unused (and hence not stored) blocks are returned as bytes of zeros.

    This file represents a partition which can be mounted with the loop option
    to inspect or save its contents. Remember to mount it read-only.

    :param image: *NtfsClone* or *PartClone* image
    :type image: imagebackup.imagebackup.ImageBackup
    :param debug: enable debug messages in FUSE file system, default *False*
    :type debug: bool
    """

    FILE_INODE = 2 # Sphinx chokes on "FILE_INODE = pyfuse3.ROOT_INODE + 1"

    def __init__(self, image: ImageBackup, debug: bool = False):
        super().__init__()
        filename = os.path.split(image.getFilename())[1]
        if filename.lower().endswith('.img'):
            filename = filename[:-4]
        self.fuse_filename = bytes(filename, 'utf-8')
        self.block_io = BlockIO(image)
        self.image_stat = os.fstat(image.getFile().fileno())
        self.debug = debug
        umask = os.umask(0o0750)
        os.umask(umask)
        self.dir_st_mode  = stat.S_IFDIR | (0o555 & (0o777 ^ umask))
        self.file_st_mode = stat.S_IFREG | (0o444 & (0o777 ^ umask))

        # Make sure file allows seek() and tell().
        assertRegularFile(image.getFile(), image.getFilename())

    async def getattr(self, inode: int, ctx=None):
        try:
            entry = pyfuse3.EntryAttributes()
            if inode == pyfuse3.ROOT_INODE:
                entry.st_mode = self.dir_st_mode
                entry.st_nlink = 2
                entry.st_size = 0
                entry.st_atime_ns = self.image_stat.st_atime_ns
                entry.st_ctime_ns = self.image_stat.st_ctime_ns
                entry.st_mtime_ns = self.image_stat.st_mtime_ns
            elif inode == self.FILE_INODE:
                entry.st_mode = self.file_st_mode
                entry.st_nlink = 1
                entry.st_size = self.block_io.getTotalSize()
                entry.st_atime_ns = self.image_stat.st_atime_ns
                entry.st_ctime_ns = self.image_stat.st_ctime_ns
                entry.st_mtime_ns = self.image_stat.st_mtime_ns
            else:
                raise pyfuse3.FUSEError(errno.ENOENT)
            entry.st_gid = os.getgid()
            entry.st_uid = os.getuid()
            entry.st_ino = inode
            return entry
        except Exception as e:
            print(f'getattr(inode={inode}) encountered: {e}.')
            raise pyfuse3.FUSEError(errno.ENOENT)

    async def lookup(self, parent_inode: int, name: bytes, ctx):
        if parent_inode != pyfuse3.ROOT_INODE or \
           name != self.fuse_filename:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return await self.getattr(self.FILE_INODE)

    async def opendir(self, inode: int, ctx):
        if inode != pyfuse3.ROOT_INODE:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return inode

    async def readdir(self, inode: int, start_id: int, token):
        try:
            assert inode == pyfuse3.ROOT_INODE
            # only one entry in directory
            if start_id == 0:
                pyfuse3.readdir_reply(token, self.fuse_filename,
                                      await self.getattr(self.FILE_INODE), 1)
            return
        except Exception as e:
            print(f'readdir(inode={inode}, start_id={start_id}, '
                  f'token={token}) encountered: {e}.')
            raise pyfuse3.FUSEError(errno.ENOENT)

    async def open(self, inode: int, flags: int, ctx):
        try:
            if inode != self.FILE_INODE:
                raise pyfuse3.FUSEError(errno.ENOENT)
            if flags & os.O_RDWR or flags & os.O_WRONLY:
                raise pyfuse3.FUSEError(errno.EROFS)
            return pyfuse3.FileInfo(fh=inode)
        except Exception as e:
            print(f'open(inode={inode}, flags=0x{flags:x}) '
                  f'encountered: {e}.')
            raise pyfuse3.FUSEError(errno.ENOENT)

    async def read(self, inode: int, offset: int, size: int):
        try:
            assert inode == self.FILE_INODE
            return self.block_io.read_data(offset, size)
        except Exception as e:
            print(f'read(inode={inode}, offset=0x{offset:x}, '
                  f'size=0x{size:x}) encountered: {e}.')
            if self.debug:
                print(traceback.format_exc())
            raise pyfuse3.FUSEError(errno.EIO)

    async def write(self, inode: int, offset: int, buffer: bytes):
        if len(buffer) != 0:
            raise pyfuse3.FUSEError(errno.EROFS)
        return 0

def mntType(fsType: str) -> str:
    """
    Return file-system type for the mount command. The empty string
    can be returned to indicate that the mount command should be called
    without the -t option.

    :param fsType: string obtained from method *imagebackup.imagebackup.fsType()*
    :type fsType: str
    :returns: string to use as *type* for the *mount* command. Empty string if mount needs to be called without the *-t* option.
    """
    return 'exfat' if fsType == 'EXFAT' else \
           'vfat' if 'FAT' in fsType else \
           '' if fsType == 'EXTFS' else \
           fsType.lower()

def fsckCmd(fsType: str) -> str:
    """
    Return fsck command to check this filesystem.

    :param fsType: string obtained from method *imagebackup.imagebackup.fsType()*
    :type fsType: str
    :returns: string that contains the command for a file system consistency check of a read-only partition.
    """
    return 'ntfsfix --no-action' if fsType == 'NTFS' else \
           'btrfsck --check --readonly'  if fsType == 'BTRFS' else \
           'fsck.exfat -n' if fsType == 'EXFAT' else \
           'fsck.fat -n' if 'FAT' in fsType else \
           'xfs_repair -f -n' if fsType == 'XFS' else \
           'e2fsck -f -n' if fsType == 'EXTFS' else \
          f'fsck.{fsType.lower()} -n'

def runFuse(image: ImageBackup, mountpoint: str, debug: bool = False) -> None:
    """
    Provide FUSE filesystem under given mountpoint. Generally, fork process
    and run the FUSE filesystem in the background process. If option `debug`
    is set, do not fork and run in the foreground writing debug messages.

    :param image: *NtfsClone* or *PartClone* image
    :type image: imagebackup.imagebackup.ImageBackup
    :param mountpoint: path to an empty directory
    :type mountpoint: str
    :param debug: enable debug messages in FUSE file system, default *False*
    :type debug: bool
    """
    isEmptyDirectory(mountpoint)
    fs = ImageBackupFS(image, debug)
    print()
    dir_name = os.path.abspath(mountpoint)
    file_name = os.path.join(dir_name, str(fs.fuse_filename, 'utf-8'))
    print(f"Virtual partition provided as '{file_name}'.")
    print()
    print(f"The file system of this virtual partition can be checked "
          "with this command:")
    print(f"   {fsckCmd(image.fsType())} {file_name}")
    print()
    print(f"This virtual partition can be mounted as a read-only filesystem "
          f"at '{dir_name}' with this command:")
    mnt_type = mntType(image.fsType())
    if mnt_type:
        mnt_type = '-t ' + mnt_type + ' '
    print(f"   sudo mount {mnt_type}{file_name} {dir_name} -o loop,ro")
    print()
    print(f"{'Entering' if debug else 'Forking subprocess to enter'} event-loop"
          f". When done unmount '{os.path.abspath(mountpoint)}' to quit this "
          f"event-loop{'' if debug else ' and its subprocess'}:")
    print(f"   sudo umount {dir_name}; umount {dir_name}")
    print()
    if debug or os.fork() == 0:
        fuse_options = set(pyfuse3.default_options)
        fuse_options.add(f'fsname=v{image.getTool()}')
        fuse_options.add('allow_other')
        if debug:
            fuse_options.add('debug')

        pyfuse3_asyncio.enable()
        pyfuse3.init(fs, mountpoint, fuse_options)

        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(pyfuse3.main())
        except Exception:
            pass

        loop.close()
        pyfuse3.close(unmount=True)

def isRegularFile(file: io.BufferedIOBase) -> bool:
    """
    Is the open file a regular file and not for instance a pipe?

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :returns: *True* if *file* is a regular file, *False* otherwise.
    """
    return bool(os.fstat(file.fileno()).st_mode & stat.S_IFREG)

def assertRegularFile(file: io.BufferedIOBase, filename: str) -> None:
    """
    Raise exception with appropriate message if `file` is not a regular file.

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :param filename: The open file's name.
    :type filename: str
    :returns: nothing
    :raises imagebackup.imagebackup.ImageBackupException: if the file is not a regular file.
    """
    image_stat = os.fstat(file.fileno())
    if not (image_stat.st_mode & (stat.S_IFREG|stat.S_IFBLK)):
        file_type = 'something else'
        if image_stat.st_mode & stat.S_IFSOCK:
            file_type = 'a socket'
        elif image_stat.st_mode & stat.S_IFCHR:
            file_type = 'a character device'
        elif image_stat.st_mode & stat.S_IFIFO:
            file_type = 'a fifo'
        raise ImageBackupException(
            f"Image file '{filename}' is {file_type}. In order "
            "to mount an image as a virtual partition, it must be a "
            "regular file.")

def isEmptyDirectory(path: str) -> str:
    """
    Is argument an empty directory?

    :param path: argument of command line option *-m/--mountpoint*
    :type path: str
    :returns: *path* if *path* is a directory in the file system and this directory is empty
    :raises argparse.ArgumentTypeError: if *path* is not a directory in the file system or it is a directory but the directory is not empty.
    """
    if os.path.isdir(path) and len(os.listdir(path)) == 0:
        return path
    raise argparse.ArgumentTypeError(f"'{path}' is not an empty directory")
