import argparse, io, os, struct, sys
from typing import Callable

from .imagebackup import ImageBackupException, ImageBackup
from .ntfsclone import NtfsClone
from .partclone import PartClone
from .partimage import PartImage
from .fuse import runFuse, isEmptyDirectory
from .utilities import uncompress, isRegularFile


###########################################################################
#                               readImage                                 #
###########################################################################

def readImage(f: io.BufferedReader, block_index_size: int, sequential: bool,
              fn: Callable[[io.BufferedIOBase], ImageBackup]) -> ImageBackup:
    """
    Read an image file, uncompress compressed files if possible, check the
    first bytes of the file to determine correct format.

    :param file: A binary file opened for reading.
    :type file: io.BufferedIOBase
    :param name: The file name of the file we are reading.
    :type name: str
    :param block_index_size: is a parameter for the index; defaults to 1024 bits.
    :type block_index_size: int
    :param sequential: Whether or not the image is to be read sequentially. If so, this function will try to support compressed files; otherwise it will suggest a command to uncompress the image file.
    :type sequential: bool
    :param fn: A function that we call to read the backup image. The function takes a single argument, an open file, and returns an object derived from *ImageBackup*.
    :type fn: Callable[[io.BufferedIOBase],imagebackup.imagebackup.ImageBackup]
    :raises imagebackup.imagebackup.ImageBackupException: Image not supported.
    :returns: A *PartImage*, *PartClone*, or *NtfsClone* instance.
    """

    file, filename, compression = uncompress(f, errorOut=not sequential)

    magic_len = max(len(ImageBackup.NTFSCLONE), len(ImageBackup.PARTCLONE),
                    len(ImageBackup.PARTIMAGE))
    magic     = file.peek(magic_len)

    if magic[:len(ImageBackup.PARTCLONE)] == ImageBackup.PARTCLONE:
        return PartClone(file, filename, block_index_size)
    if magic[:len(ImageBackup.NTFSCLONE)] == ImageBackup.NTFSCLONE:
        return NtfsClone(file, filename)
    if magic[:len(ImageBackup.PARTIMAGE)] == ImageBackup.PARTIMAGE:
        return PartImage(file, filename, block_index_size)

    return fn(file)


###########################################################################
#                                utility                                  #
###########################################################################

def utility(fn: Callable[[io.BufferedIOBase],ImageBackup],
            args: argparse.Namespace) -> None:
    """
    This function implements the common code of utilities vpartclone
    and vntfsclone.

    :param fn: A function that we call to read the backup image. The function takes a single argument, an open file, and returns a *PartClone* or *NtfsClone* instance.
    :type fn: Callable[[io.BufferedIOBase],imagebackup.imagebackup.ImageBackup]

    :param args: Command-line arguments passed to *vpartclone* or *vntfsclone*.
    :type args: argparse.Namespace
    """

    try:

        image = readImage(args.image, args.index_size,
                          args.mountpoint is None, fn)

        if args.verbose:
            print(image)
            print()

        if args.mountpoint is not None:

            image.buildBlockIndex(progress_bar=not args.quiet)

            try:

                runFuse(image, args.mountpoint, args.debug_fuse)

            except Exception as e:
                print(file=sys.stderr)
                print(f'FUSE file system errored out with: "{e}".',
                      file=sys.stderr)
                sys.exit(1)

        elif args.crc_check:
            if isinstance(image, NtfsClone):
                print(f"Reading entire image '{args.image.name}'...")
            else:
                print(f"Verifying all checksums of image '{args.image.name}'"
                      "...")
            image.blockReader(progress_bar=not args.quiet, verify_crc=True)

    except ImageBackupException as e:
        print(file=sys.stderr)
        print('Error:', e, file=sys.stderr)
        sys.exit(1)


###########################################################################
#                 Main Program for Utility vntfsclone                     #
###########################################################################

def vntfsclone():
    """
    Implements vntfsclone command; processes command-line argumments,
    reads image and mounts it as virtual partition.
    """

    parser = argparse.ArgumentParser(prog='vntfsclone',
                                     description='Mount ntfsclone image '
                                     'backup as virtual partition.')
    parser.add_argument('image', type=argparse.FileType('rb'),
                        help='partclone image to read')
    parser.add_argument('-m', '--mountpoint', type=isEmptyDirectory,
                        help='mount point for virtual partition; '
                        'an empty directory')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='dump header and bitmap info')
    parser.add_argument('-c', '--crc_check', action='store_true',
                        help='read the entire image (slow!)')
    parser.add_argument('-d', '--debug_fuse', action='store_true',
                        help='enable FUSE filesystem debug messages')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress progress bar when indexing')
    args = parser.parse_args()
    args.index_size = ImageBackup.BLOCK_OFFSET_SIZE
    utility(lambda f:NtfsClone(f, args.image.name), args)


###########################################################################
#                 Main Program for Utility vpartclone                     #
###########################################################################

def vpartclone():
    """
    Implements vpartclone command; processes command-line argumments,
    reads image and mounts it as virtual partition.
    """

    parser = argparse.ArgumentParser(prog='vpartclone',
                                     description='Mount partclone image '
                                     'backup as virtual partition.')
    parser.add_argument('image', type=argparse.FileType('rb'),
                        help='partclone image to read')
    parser.add_argument('-m', '--mountpoint', type=isEmptyDirectory,
                        help='mount point for virtual partition; '
                        'an empty directory')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='dump header and bitmap info')
    parser.add_argument('-d', '--debug_fuse', action='store_true',
                        help='enable FUSE filesystem debug messages')
    parser.add_argument('-c', '--crc_check', action='store_true',
                        help='verify all checksums in image (slow!)')
    parser.add_argument('-i', '--index_size', type=indexSizeType,
                        help='Size parameter for building bitmap index; leave '
                        'unchanged unless memory usage too high. Increase '
                        'size to reduce memory usage by doubling or '
                        'quadrupling number '
                       f'repeatedly (default {ImageBackup.BLOCK_OFFSET_SIZE}).',
                        default=ImageBackup.BLOCK_OFFSET_SIZE)
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress progress bar in crc check')
    args = parser.parse_args()
    utility(lambda f:PartClone(f, args.image.name, args.index_size), args)


###########################################################################
#                 Main Program for Utility vpartimage                     #
###########################################################################

def vpartimage():
    """
    Implements vpartimage command; processes command-line argumments,
    reads image and mounts it as virtual partition.
    """

    parser = argparse.ArgumentParser(prog='vpartimage',
                                     description='Mount partimage image '
                                     'backup as virtual partition.')
    parser.add_argument('image', type=argparse.FileType('rb'),
                        help='partclone image to read')
    parser.add_argument('-m', '--mountpoint', type=isEmptyDirectory,
                        help='mount point for virtual partition; '
                        'an empty directory')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='dump header and bitmap info')
    parser.add_argument('-d', '--debug_fuse', action='store_true',
                        help='enable FUSE filesystem debug messages')
    parser.add_argument('-c', '--crc_check', action='store_true',
                        help='verify all checksums in image (slow!)')
    parser.add_argument('-i', '--index_size', type=indexSizeType,
                        help='Size parameter for building bitmap index; leave '
                        'unchanged unless memory usage too high. Increase '
                        'size to reduce memory usage by doubling or '
                        'quadrupling number '
                       f'repeatedly (default {ImageBackup.BLOCK_OFFSET_SIZE}).',
                        default=ImageBackup.BLOCK_OFFSET_SIZE)
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress progress bar in crc check')
    args = parser.parse_args()
    utility(lambda f:PartImage(f, args.image.name, args.index_size), args)


###########################################################################
#                             indexSizeType                               #
###########################################################################

def indexSizeType(arg: str) -> int:
    """
    Is argument an acceptable argument for vpartclone's option --index_size?

    :param arg: string passed by user to *-i/--index_size* option.
    :type arg: str
    :returns: the index size as an *int*.
    :raises argparse.ArgumentTypeError: if the argument is an invalid index size.
    """
    try:
        iarg = int(arg)
    except:
        raise argparse.ArgumentTypeError(f"'{arg}' is not an integer")

    if iarg < 1000:
        raise argparse.ArgumentTypeError(f"'{arg}' is too small, "
                                         "should be >= 1000")
    if iarg % 8 != 0:
        raise argparse.ArgumentTypeError(f"'{arg}' is not a multiple of 8")
    return iarg
