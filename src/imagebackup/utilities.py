import bz2, gzip, io, lzma, os, stat, struct
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import zstandard # install with "pip install zstandard"
import lz4.frame # install with "pip install lz4"; on Ubuntu install with "sudo apt install python3-lz4"

from .imagebackup import ImageBackupException as UtilityException


#######################################################################
#         Magic Numbers for Supported Compression Algorithms          #
#######################################################################

GZIP  = 0x8b1f
BZIP2 = 0x5a42
ZSTD  = 0xb528
XZ    = 0x37fd
LZMA  = 0x005d
LZ4   = 0x2204


#######################################################################
#                         Limit to Open Files                         #
#######################################################################

MAX_OPEN_SPLIT_FILES = 48
"""
During the virtual concatenation of split files, we will not leave more
than this many files open at any time. This limit is relevant for random
access to split files; during sequential access we open them just one at
a time.
"""

#######################################################################
#                           class SplitFile                           #
#######################################################################

@dataclass
class SplitFile:
    """
    This class represents an individual split file. Class `ConcatFiles'
    stores an array of `SplitFiles`.
    """

    offset  : int
    "Offset into the unsplit virtual file where this individual file starts."

    size    : int
    "Number of bytes in this file."

    filename: str
    "Name of this individual file."

    file    : Optional[io.BufferedReader]
    "Open file or `None`; split files are opened and closed on demand."

    def end(self) -> int:
        """
        :returns: offset of first byte of next single individual file.
        """
        return self.offset + self.size


#######################################################################
#                              class LRU                              #
#######################################################################

class LRU:
    """
    This LRU keeps track of open files. Not more than *max_open* files
    will be open at any time. When a new file is opened, this class closes
    the least recently used file.

    :param max_open: The max number of open files.
    :type max_open: int
    """

    def __init__(self, max_open):
        self.max_open = max_open
        self.lru : Dict[int, SplitFile] = {}

    def insert(self, idx: int, sf: SplitFile) -> None:
        """
        Split file *sf* at index *idx* is being used. Append it to lru. If it
        is already in lru, delete it first. It must become the most recently
        used entry.

        :param idx: Index of split file *sf*.
        :type idx: int
        :param sf: Split file *sf*.
        :type sf: SplitFile
        """
        if idx in self.lru:
            del self.lru[idx]
        self.lru[idx] = sf
        if len(self.lru) > self.max_open:
            sf = self.lru.pop(next(iter(self.lru)))
            if sf.file is not None:
                sf.file.close()
                sf.file = None

    def remove(self, idx) -> None:
        """
        Remove split file at index *idx* from lru. Close file if it is not
        already closed.

        :param idx: Index of split file *sf*.
        :type idx: int
        """
        if idx in self.lru:
            sf = self.lru.pop(idx)
            if sf.file is not None:
                sf.file.close()
                sf.file = None


#######################################################################
#                         class ConcatFiles                           #
#######################################################################

class ConcatFiles(io.BufferedReader):
    """
    This class is instantiated with a file whose name ends in 'aa' and it
    concatenates split binary files.

    :param file: A binary file opened for reading.
    :type file: io.BufferedReader
    """

    def __init__(self, file: io.BufferedReader):
        assert file.name.endswith('aa')
        self.sequential = True
        self.cur = SplitFile(0, os.fstat(file.fileno()).st_size,
                             file.name, file)
        self.cur_offset = self.cur_idx = 0
        self.split_files = [self.cur]
        self.lru = LRU(MAX_OPEN_SPLIT_FILES)
        self.lru.insert(self.cur_idx, self.cur)

        basename = file.name[:-2]
        idx = 0
        # sequence: aa, ab, ac, ..., yy, yz, zaaa, zaab, ...
        YZ   = 649
        ZAAA = 439400
        a = ord('a')
        while True:
            idx += 1 if idx != YZ else ZAAA - YZ
            if idx < ZAAA:
                i, j = divmod(idx, 26)
                fname = basename + chr(a+i) + chr(a+j)
            else:
                k, l = divmod(idx, 26)
                j, k = divmod(k, 26)
                i, j = divmod(j, 26)
                fname = basename + chr(a+i) + chr(a+j) + chr(a+k) + chr(a+l)
            if not os.path.exists(fname):
                break
            self.split_files.append(SplitFile(self.split_files[-1].end(),
                                              os.stat(fname).st_size,
                                              fname, None))
        self.filename = basename + ('a?' if len(self.split_files) <= 26 else
                                '??' if len(self.split_files) < 649 else '*')

    def byOffset(self, offset: int) -> None:
        """
        Look up a single individual file by `offset`.

        This method performs a binary search and calls method *newFile* to
        update members *cur_idx*, *cur*, and *cur_offset*.

        :param offset: Index into the large unsplit file.
        :type offset: int
        """
        l = 0
        r = len(self.split_files)
        while l < r:
            m = (l + r) // 2
            if offset < self.split_files[m].offset:
                r = m
            else:
                l = m
                if offset < self.split_files[m].end():
                    break
        assert self.split_files[l].offset <= offset and \
               offset < self.split_files[l].end()
        if self.cur_idx != l:
            self.newFile(l)

    def newFile(self, idx: int):
        """
        Set a new single individual file as the active one.

        This method modifies members *cur_idx*, *cur*, and *cur_offset*.

        :param idx: Index into member *split_files*.
        :type idx: int
        """
        assert idx >= 0 and idx < len(self.split_files)
        self.cur_idx = idx
        self.cur = self.split_files[self.cur_idx]
        self.lru.insert(self.cur_idx, self.cur)
        if self.cur.file is None:
            self.cur.file = open(self.cur.filename, 'rb')
            self.cur_offset = 0
        else:
            self.cur_offset = self.cur.file.tell()

    @property
    def name(self) -> str:
        """
        Return file name that is currently active.

        :returns: file name.
        """
        return self.filename

    @property
    def mode(self) -> str:
        """
        Return the mode the file has been opened with.

        :returns: string 'rb'
        """
        assert self.cur.file is not None
        return self.cur.file.mode

    def fileno(self) -> int:
        """
        Return file descriptor that is currently active.

        :returns: integer file descriptor
        """
        assert self.cur.file is not None
        return self.cur.file.fileno()

    def peek(self, size: int = 1) -> bytes:
        """
        Peek into file. Returns data in buffer that has not yet been
        returned with *read*.

        :returns: bytes of unread data
        """
        assert size >= 0
        assert self.cur.file is not None
        return self.cur.file.peek(size)

    def read(self, size: Optional[int] = None) -> bytes:
        """
        Read *size* bytes from file. When *size* is *None*, read all the
        rest of the file.

        :returns: *size* bytes or fewer if *size* bytes would read beyond end-of-file.
        """
        if size is None:
            size = self.split_files[-1].end() - self.tell()
        result = bytes()
        while len(result) < size:
            sz = size - len(result)
            if self.cur_offset + sz <= self.cur.size:
                self.cur_offset += sz
                assert self.cur.file is not None
                result += self.cur.file.read(sz)
            else:
                assert self.cur.file is not None
                sz = self.cur.size - self.cur_offset
                result += self.cur.file.read(sz)
                self.cur_offset += sz
                if self.cur_idx < len(self.split_files) - 1:
                    if self.sequential:
                        self.cur.file.close()
                        self.cur.file = None
                        self.lru.remove(self.cur_idx)
                    self.newFile(self.cur_idx + 1)
                    if self.cur_offset != 0:
                        self.cur_offset = 0
                        assert self.cur.file is not None
                        self.cur.file.seek(0)
                else:
                    return result
        return result

    def seekable(self) -> bool:
        """
        Is this stream seekable?

        :returns: *True*
        """
        return True

    def seek(self, pos: int, whence: int = os.SEEK_SET) -> int:
        """
        Seek to position in file.

        :returns: new position in file.
        """
        assert whence in [os.SEEK_SET, os.SEEK_CUR, os.SEEK_END]
        if whence == os.SEEK_CUR:
            pos += self.tell()
        elif whence == os.SEEK_END:
            pos += self.split_files[-1].end()
        assert pos >= 0 and pos <= self.split_files[-1].end()
        if pos < self.cur.offset or pos >= self.cur.end():
            if pos != 0:
                self.sequential = False
            self.byOffset(pos)
        if pos != self.cur.offset + self.cur_offset:
            self.cur_offset = pos - self.cur.offset
            assert self.cur.file is not None
            self.cur.file.seek(self.cur_offset)
        return self.tell()

    def tell(self) -> int:
        """
        Return current position in file.

        :returns: position in file.
        """
        return self.cur.offset + self.cur_offset

    def close(self) -> None:
        "Close all individual files."
        for sf in self.split_files:
            if sf.file is not None:
                sf.file.close()
                sf.file = None


#######################################################################
#                              ReadZstd                               #
#######################################################################

class ReadZstd(io.BufferedReader):
    """
    This class is instantiated with a zstd-compressed file. This class adds
    method `peek` to an instance of `zstandard.ZstdDecompressor.stream_reader`.
    `stream_reader` does all the heavy lifting.

    :param file: A binary file opened for reading.
    :type file: io.BufferedReader
    """

    def __init__(self, file: io.BufferedReader):
        self.file = file
        self.buffer = bytes()
        self.ctx = zstandard.ZstdDecompressor()
        self.stream_reader = self.ctx.stream_reader(self.file,
                                                    read_across_frames=True)

    @property
    def name(self) -> str:
        """
        Return file name that we are reading from.

        :returns: file name.
        """
        return self.file.name

    @property
    def mode(self) -> str:
        """
        Return the mode the file has been opened with.

        :returns: string 'rb'
        """
        return self.stream_reader.mode

    def fileno(self) -> int:
        """
        Return file descriptor of the compressed file.

        :returns: integer file descriptor
        """
        return self.stream_reader.fileno()

    def peek(self, size: int = 1) -> bytes:
        """
        Peek into file. Return data in buffer that has not yet been
        returned with *read*. The next *read* will return this data.

        :returns: bytes of unread data
        """
        if  size > len(self.buffer):
            self.buffer += self.stream_reader.read(size - len(self.buffer))
        return self.buffer[:size]

    def read(self, size: Optional[int] = None) -> bytes:
        """
        Read *size* bytes from file. When *size* is *None*, read all the
        rest of the file.

        :returns: *size* bytes or fewer if *size* bytes would read beyond end-of-file.
        """

        if size is None:
            result = self.buffer + self.stream_reader.read()
            self.buffer = bytes()
            return result

        if size > len(self.buffer):
            self.buffer += self.stream_reader.read(size - len(self.buffer))

        result = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return result

    def seekable(self) -> bool:
        """
        Is this stream seekable?

        :returns: *True*
        """
        return self.stream_reader.seekable()

    def seek(self, pos: int, whence: int = os.SEEK_SET) -> int:
        """
        Seek to position in file.

        :returns: new position in file.
        """
        self.buffer = bytes()
        return self.stream_reader.seek(pos, whence)

    def tell(self) -> int:
        """
        Return current position in file.

        :returns: position in file.
        """
        return self.stream_reader.tell() - len(self.buffer)

    def close(self) -> None:
        "Close file."
        self.stream_reader.close()


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
    out_name = os.path.split(filename)[1]
    if '.'+compression in out_name:
        out_name = out_name.replace('.'+compression, '')
    elif len(compression) > 2 and '.'+compression[:-1] in out_name:
        out_name = out_name.replace('.'+compression[:-1], '')
    if out_name[-1] == '?':
        out_name = out_name[:-2]
    elif out_name[-1] == '*':
        out_name = out_name[:-1]
    if out_name[-1] == '.':
        out_name = out_name[:-1]
    if out_name == filename or not (out_name.endswith('.img') or
       out_name.endswith('-img')) or os.path.exists(out_name):
        if os.path.exists(out_name + '.img'):
            i = 1
            while os.path.exists(out_name + f'_{i}.img'):
                i += 1
            out_name = out_name + f'_{i}.img'
        else:
            out_name += '.img'

    # Suggest concatenation for split files.
    if filename[-1] in ['?', '*']:
        n1 = filename
        if compression == 'gz':
            return f"Files '{n1}' are gzip-compressed; run 'cat {n1} | " \
                   f"gunzip > {out_name}' and try again with '{out_name}'."
        if compression == 'bz2':
            return f"Files '{n1}' are bzip2-compressed; run 'cat {n1} | " \
                   f"bunzip2 > {out_name}' and try again with '{out_name}'."
        return f"Files '{n1}' are {compression}-compressed; run 'cat {n1} | " \
               f"zstd -d --format={compression} -o {out_name} -' and " \
               f"try again with '{out_name}'."

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
#                    isRegularFile & isSplitFile                      #
#######################################################################

def isRegularFile(file: io.BufferedIOBase) -> bool:
    """
    Is the open file a regular file and not for instance a pipe?

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :returns: *True* if *file* is a regular file, *False* otherwise.
    """
    return bool(os.fstat(file.fileno()).st_mode & stat.S_IFREG)

def isSplitFile(name: str) -> bool:
    """
    Is the file a split file?

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :returns: *True* if *name* ends in `aa` and another file `ab` exists, *False* otherwise.
    """
    return name.endswith('aa') and os.path.exists(name[:-2] + 'ab')


#######################################################################
#                              uncompress                             #
#######################################################################

def uncompress(file: io.BufferedReader, errorOut: bool = False) \
               -> Tuple[io.BufferedIOBase, str, str]:
    """
    Handle compression if `file` is a compressed file. Return a triple
    consisting of possibly a new file to read uncompressed data from, the file
    name, and the compression used.

    This function also deals with split files. If it is called with a file
    whose name ends with 'aa' and there exists also a file that ends in 'ab',
    this function will virtually concatenate aa, ab, ... and uncompress the
    concatenated contents.

    :param file: A binary file opened for reading.
    :type file: io.BufferedReader
    :param errorOut: if *True* do not uncompress but raise exception.
    :type errorOut: bool
    :raises imagebackup.partimage.ImageBackupException: when file cannot be uncompressed or *errorOut* is set.
    :returns: A triple consisting of opened file, file name, and compression. The compression is represented as empty string for no compression, 'gz', 'bz2', 'zstd', 'xz', 'lzma', or 'lz4'. Split files are reported along with the compression, 'split' and 'zstd+split' are possible values.
    """
    split = ''
    if isSplitFile(file.name):
        file = ConcatFiles(file)
        split = '+split'
    filename = file.name

    magic = file.peek(2)
    if len(magic) >= 2:
        word = struct.unpack('<H', magic[:2])[0]
        if word == GZIP:
            if errorOut:
                raise UtilityException(compressedMsg(filename, 'gz'))
            return gzip.open(filename=file, mode='rb'), filename, 'gzip' + split
        if word == BZIP2:
            if errorOut:
                raise UtilityException(compressedMsg(filename, 'bz2'))
            return bz2.open(filename=file, mode='rb'), filename, 'bzip2' + split
        if word == ZSTD:
            if errorOut:
                raise UtilityException(compressedMsg(filename, 'zstd'))
            return ReadZstd(file), filename, 'zstd' + split
        if word in [XZ, LZMA]:
            if errorOut:
                raise UtilityException(compressedMsg(filename, 'lzma'))
            return lzma.LZMAFile(filename=file, mode='rb'), \
                   filename, ('xz' if word == XZ else 'lzma') + split
        if word == LZ4:
            if errorOut:
                raise UtilityException(compressedMsg(filename, 'lz4'))
            return lz4.frame.LZ4FrameFile(filename=file, mode='rb'), \
                   filename, 'lz4' + split
    return file, filename, 'split' if split else ''
