#!/usr/bin/env python3
import argparse, bz2, gzip, io, lzma, os, struct, sys
from typing import Callable

import pyzstd    # install with "pip install pystd"
import lz4.frame # install with "pip install lz4"; on Ubuntu install with "sudo apt install python3-lz4"

from .imagebackup import ImageBackupException, WrongImageFile, ImageBackup
from .ntfsclone import NtfsClone
from .partclone import PartClone
from .partimage import PartImage
from .fuse import runFuse, isEmptyDirectory, isRegularFile


def compressedMsg(filename: str, compression: str) -> str:
    """
    Formats the error message for compressed images encountered when reading
    image. Suggests appropiate command to uncompress them.

    :param filename: File name of the compressed image.
    :type progress_bar: str

    :param compression: 'gz', 'bz2', 'zstd', 'xz', 'lzma', and 'lz4' are supported.
    :type progress_bar: str

    :returns: A formatted error message.
    """

    # Suggest an output file name that does not already exist.
    out_name = os.path.split(filename)[1].replace('.'+compression, '')
    if out_name == filename or not out_name.endswith('.img') or \
       os.path.exists(out_name):
        if os.path.exists(out_name + '.img'):
            i = 1
            while os.path.exists(out_name + f'_{i}.img'):
                i += 1
            out_name = out_name + f'_{i}.img'
        else:
            out_name += '.img'

    if compression == 'gz':
        msg = "File '{n1}' is gzip-compressed; run 'gunzip < {n1} > {n2}' " \
              "and try again with '{n2}'."
    elif compression == 'bz2':
        msg = "File '{n1}' is bzip2-compressed; run 'bunzip2 < {n1} > {n2}' " \
              "and try again with '{n2}'."
    else:
        msg = "File '{n1}' is {c}-compressed; run 'zstd -d " \
              "--format={c} -o {n2} {n1}' and try again with '{n2}'."

    return msg.format(msg, n1=filename, n2=out_name, c=compression)


def readImage(file: io.BufferedIOBase, name: str, block_index_size: int,
              sequential: bool,
              fn: Callable[[io.BufferedIOBase], ImageBackup]) -> ImageBackup:
    """
    Read an image file, catch *WrongImageFile* exceptions and try to resolve
    them. This function opens, for instance, an image file for partclone,
    catches an exception, and ultimately opens it for ntfsclone.
    If the image is to be read sequentially, it also silently re-opens it
    to undo gzip-, bz2-, and zstd- compression.

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
    try:
        return fn(file)
    except WrongImageFile as e:
        magic = e.getMagic()
        if magic[:len(ImageBackup.NTFSCLONE)] == ImageBackup.NTFSCLONE:
            if isRegularFile(file):
                file.seek(0)
                return readImage(file, name, block_index_size, sequential,
                                 lambda f:NtfsClone(f, name))
            else:
                raise e
        elif magic[:len(ImageBackup.PARTCLONE)] == ImageBackup.PARTCLONE:
            if isRegularFile(file):
                file.seek(0)
                return readImage(file, name, block_index_size, sequential,
                                 lambda f:PartClone(f, name, block_index_size))
            else:
                raise e
        elif magic[:len(ImageBackup.PARTIMAGE)] == ImageBackup.PARTIMAGE:
            if isRegularFile(file):
                file.seek(0)
                return readImage(file, name, block_index_size, sequential,
                                 lambda f:PartImage(f, name, block_index_size))
            else:
                raise e
        elif len(magic) >= 2:
            # Uncompress on the fly if we are only going to read
            # the image sequentially.
            word = struct.unpack('<H', magic[:2])[0]
            if word == ImageBackup.GZIP:
                if not sequential:
                    raise WrongImageFile(compressedMsg(name, 'gz'), magic)
                file.seek(0)
                gzip_file = gzip.open(filename=file, mode='rb')
                return readImage(gzip_file, name, block_index_size,
                                 sequential, fn)
            elif word == ImageBackup.BZIP2:
                if not sequential:
                    raise WrongImageFile(compressedMsg(name, 'bz2'), magic)
                file.seek(0)
                bz2_file = bz2.open(filename=file, mode='rb')
                return readImage(bz2_file, name, block_index_size,
                                 sequential, fn)
            elif word == ImageBackup.ZSTD:
                if not sequential:
                    raise WrongImageFile(compressedMsg(name, 'zstd'), magic)
                file.seek(0)
                zstd_file = pyzstd.ZstdFile(filename=name, mode='rb')
                return readImage(zstd_file, name, block_index_size,
                                 sequential, fn)
            elif word in [ImageBackup.XZ, ImageBackup.LZMA]:
                if not sequential:
                    c = 'xz' if word == ImageBackup.XZ else 'lzma'
                    raise WrongImageFile(compressedMsg(name, c), magic)
                file.seek(0)
                lzma_file = lzma.open(filename=name, mode='rb')
                return readImage(lzma_file, name, block_index_size,
                                 sequential, fn)
            elif word == ImageBackup.LZ4:
                if not sequential:
                    raise WrongImageFile(compressedMsg(name, 'lz4'), magic)
                file.seek(0)
                lz4_file = lz4.frame.open(filename=name, mode='rb')
                return readImage(lz4_file, name, block_index_size,
                                 sequential, fn)
            else:
                raise e
        else:
            raise e

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

        image = readImage(args.image, args.image.name, args.index_size,
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
