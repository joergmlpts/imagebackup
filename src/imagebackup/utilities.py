import bz2, gzip, io, lzma, os, stat, struct
from typing import Callable, List, Optional, Tuple

import pyzstd    # install with "pip install pystd"
import lz4.frame # install with "pip install lz4"; on Ubuntu install with "sudo apt install python3-lz4"

from .imagebackup import ImageBackup, ImageBackupException


#######################################################################
#                            compressedMsg                            #
#######################################################################

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


#######################################################################
#                            isRegularFile                            #
#######################################################################

def isRegularFile(file: io.BufferedIOBase) -> bool:
    """
    Is the open file a regular file and not for instance a pipe?

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :returns: *True* if *file* is a regular file, *False* otherwise.
    """
    return bool(os.fstat(file.fileno()).st_mode & stat.S_IFREG)


#######################################################################
#                              kindOfFile                             #
#######################################################################

def kindOfFile(file: io.BufferedIOBase) -> str:
    """
    Return the kind of the open file, e.g. 'regular file', 'pipe', ...

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :returns: string 'regular file', 'pipe', ...
    """
    fstat = os.fstat(file.fileno())
    if fstat.st_mode & stat.S_IFREG:
        return 'regular file'
    if fstat.st_mode & stat.S_IFBLK:
        return 'block device'
    if fstat.st_mode & stat.S_IFSOCK:
        return 'socket'
    if fstat.st_mode & stat.S_IFCHR:
        return 'character device'
    if fstat.st_mode & stat.S_IFIFO:
        return 'pipe'
    return 'something else'


#######################################################################
#                              uncompress                             #
#######################################################################

def uncompress(file: io.BufferedReader, errorOut: bool = False) \
               -> Tuple[io.BufferedIOBase, str, str]:
    """
    Undo compression if "file" is a compressed file. Return a triple consisting
    of possibly a new file to read uncompressed data from, the file name,
    and the compression used.

    :param file: A binary file opened for reading.
    :type file: io.BufferedReader
    :param errorOut: if *True* do not uncompress but raise exception
    :type errorOut: bool
    :raises imagebackup.partimage.ImageBackupException: when file connot be uncompressed or *errorOut* is set.
    :returns: A triple consisting of opened file, file name, and compression.
    """
    filename = file.name
    magic = file.peek(2)
    if len(magic) >= 2:
        word = struct.unpack('<H', magic[:2])[0]
        if word == ImageBackup.GZIP:
            if errorOut:
                raise ImageBackupException(compressedMsg(filename, 'gz'))
            return gzip.open(filename=file, mode='rb'), filename, 'gzip'
        if word == ImageBackup.BZIP2:
            if errorOut:
                raise ImageBackupException(compressedMsg(filename, 'bz2'))
            return bz2.open(filename=file, mode='rb'), filename, 'bzip2'
        if word == ImageBackup.ZSTD:
            if not errorOut and isRegularFile(file):
                file.close()
                return pyzstd.ZstdFile(filename=filename, mode='rb'), \
                       filename, 'zstd'
            else:
                raise ImageBackupException(compressedMsg(filename, 'zstd'))
        elif word in [ImageBackup.XZ, ImageBackup.LZMA]:
            if not errorOut and isRegularFile(file):
                file.close()
                return lzma.open(filename=filename, mode='rb'), \
                       filename, 'xz' if word == ImageBackup.XZ else 'lzma'
            else:
                raise ImageBackupException(compressedMsg(filename, 'lzma'))
        elif word == ImageBackup.LZ4:
            if not errorOut and isRegularFile(file):
                file.close()
                return lz4.frame.open(filename=filename, mode='rb'), \
                       filename, 'lz4'
            else:
                raise ImageBackupException(compressedMsg(filename, 'lz4'))
    return file, filename, ''
