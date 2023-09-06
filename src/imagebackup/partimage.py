import datetime, io, os, struct, time, uuid
from typing import Callable, List, Optional, Tuple, Union

from tqdm import tqdm # install with "pip install tqdm"; on Ubuntu install with "sudo apt install python3-tqdm"

from .imagebackup import ImageBackupException, WrongImageFile, ImageBackup, \
                         crc32, BITS_SET


#######################################################################
#                              Exception                              #
#######################################################################

class PartImageException(ImageBackupException):
    """
    This exception is raised for any issues encountered
    with the partimage image.
    """
    def __init__(self, s: str):
        super().__init__(s)


#######################################################################
#                              32-bit CRC                             #
#######################################################################

def crcUpdate(buffer: bytes, crc: int) -> int:
    """
    Compute crc32 for the given buffer.

    :param buffer: buffer to compute crc32 for.
    :type buffer: bytes
    :param crc: seed to start crc32 computation from
    :type crc: int
    :returns: 32-bit crc
    """
    return crc32(buffer, crc ^ 0xffffffff) ^ 0xffffffff


#######################################################################
#                                Base                                 #
#######################################################################

class Base:

    HEADER_SIZE          = 16388 # headers incl 4-byte checksum
    NAME                 = 'Base'
    DONT_DUMP: List[str] = []
    DUMP_HEX : List[str] = []
    LF                   = '\n'

    def parseStrings(self, cur: int, buffer: bytes,
                     name_size_list: List[Tuple[str, int]]) -> int:
        """
        Parse strings starting at index `cur` in `buffer'. The `name_size_list`
        provides the attribute name and length of each string. Returns updated
        index that immediately follows the parsed strings.
        """
        for name, size in name_size_list:
            assert cur + size <= len(buffer)
            if (idx := buffer[cur:cur+size].find(0)) == -1:
                idx = size
            setattr(self, name, str(buffer[cur:cur+idx], 'utf-8'))
            cur += size
        return cur

    def format_attrvalue(self, attr: str, value) -> str:
        """
        Format value of a member variable for printing

        Parameters
        ----------
        attr  : str
        The name of a member variable.

        value : object
        The value of member variable `attr`.

        Returns
        -------
        str
        Value of member variable formatted for printing in a table. The
        formatting depends on the value's type and - in derived classes -
        may also depend on the member variable name.
        """
        if isinstance(value, uuid.UUID):
            return str(value).upper()
        if isinstance(value, str):
            return f'"{value}"'
        if attr in self.DUMP_HEX:
            if isinstance(value, tuple) or isinstance(value, bytes):
                if max(value) <= 255:
                    return ' '.join([f'{v:02x}' for v in value])
                else:
                    return ', '.join([f'0x{v:x}' for v in value])
            return f'{value}' if value < 10 else f'0x{value:x}'
        return f'{value}'

    def __str__(self) -> str:
        """
        Build a table of all member variables and their values.

        Build a table of all member variables and their values. Ignore member
        variables listed in DONT_DUMP.
        """
        result = self.NAME + self.LF + '-' * len(self.NAME)
        maxlen = max(len(k) for k in self.__dict__) if self.__dict__ else 0
        for key, value in self.__dict__.items():
            if key in self.DONT_DUMP:
                continue
            result += self.LF + key + ' ' * (maxlen - len(key)) + \
                      ': ' + self.format_attrvalue(key, value)
        return result


#######################################################################
#                             VolumeHeader                            #
#######################################################################

class VolumeHeader(Base):
    """
    Volume Header, the first 512 bytes of a partimage file.

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :param filename: The open file's name.
    :type filename: str
    :raises imagebackup.imagebackup.WrongImageFile: if the image file is not a partclone image.
    :raises imagebackup.partimage.PartImageException: if the image file is truncated.
    """
    HEADER_SIZE      = 512
    NAME             = 'Volume Header'
    DUMP_HEX         = ['identifier']

    def __init__(self, file: io.BufferedIOBase, filename: str):
        buffer = file.read(self.HEADER_SIZE)
        if len(buffer) < self.HEADER_SIZE:
            raise PartImageException(f"File '{filename}' truncated; "
                                     f"only {len(buffer)} of "
                                     f"{self.HEADER_SIZE} bytes read.")
        self.version = ''
        if buffer[:32] != ImageBackup.PARTIMAGE + bytes(16):
            raise WrongImageFile(f"Not a partimage file: '{filename}'.", buffer)
        cur = self.parseStrings(32, buffer, [('version', 64)])
        self.volume, self.identifier = struct.unpack('<LQ', buffer[cur:cur+12])

    def getVolumeNo(self) -> int:
        "Volume number, zero-based, for images spread over multiple volumes."
        return self.volume

    def getIdentifier(self) -> int:
        "Number to uniquely identify an image spread over multiple volumes."
        return self.identifier

    def getVersion(self) -> str:
        "Partimage version that wrote this image, e.g. '0.6.1'."
        return self.version


#######################################################################
#                        Header Base Class                            #
#######################################################################

class Header(Base):
    """
    Base of MainHeader, LocalHeader, and InfoHeader.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    HEADER_SIZE = 16388    # main, local, and info headers w/ 4-byte checksum
    NAME        = 'Header' # to be overridden by derived classes

    def __init__(self, kind: str, buffer: bytes) -> None:
        cksum = struct.unpack('<l', buffer[self.HEADER_SIZE-4:
                                           self.HEADER_SIZE])[0]
        if (cksum2 := sum(b if b <= 127 else b - 256
                          for b in buffer[:self.HEADER_SIZE-4])) != cksum:
            raise PartImageException(f"{kind} header checksum mismatch "
                                     f"({self.HEADER_SIZE-4} bytes): "
                                     f"{cksum:08x} != {cksum2:08x}.")


#######################################################################
#                             MainHeader                              #
#######################################################################

class MainHeader(Header):
    """
    Builds a Main Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.MainHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'Main Header'

    def __init__(self, buffer: bytes):
        super().__init__('Main', buffer)
        self.filesystem = self.description = self.device = ''
        strings = [('filesystem', 512), ('description', 4096),
                   ('device', 512), ('firstpath', 4095), ('sysname', 65),
                   ('nodename', 65), ('release', 65), ('version', 65),
                   ('machine', 65)]
        cur = self.parseStrings(0, buffer, strings)

        self.compression, self.flags = struct.unpack('<2L', buffer[cur:cur+8])
        cur += 8

        date_time = struct.unpack('<11L', buffer[cur:cur+44])
        cur += 44
        self.datetime = datetime.datetime(date_time[5]+1900, date_time[4]+1,
                                          date_time[3], date_time[2],
                                          date_time[1], date_time[0])

        self.part_size = struct.unpack('<Q', buffer[cur:cur+8])[0]
        cur += 8

        cur = self.parseStrings(cur, buffer, [('hostname', 128),
                                              ('version', 64)])

        self.mbr_count, self.mbr_size, self.encrypt_algo = \
            struct.unpack('<3L', buffer[cur:cur+12])

    def getFilesystem(self) -> str:
        "Return the file system that was saved, e.g. 'fat32' or 'ext2'."
        return self.filesystem

    def getPartitionSize(self) -> int:
        "Return the size of the partitioon in bytes."
        return self.part_size

    def getDescription(self) -> str:
        """
        Return a descripton for the backup image. Empty unless user provided
        one to partimage when the image was written.
        """
        return self.description

    def getDevice(self) -> str:
        "Return the device that was written, e.g. '/dev/sda1'."
        return self.device

    def getDateTime(self) -> datetime.datetime:
        "Return date & time the image was written."
        return self.datetime


#######################################################################
#                            LocalHeader                              #
#######################################################################

class LocalHeader(Header):
    """
    Builds a Local Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.LocalHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'Local Header'

    def __init__(self, buffer: bytes):
        super().__init__('Local', buffer)
        self.label = ''
        self.blockSize, self.usedBlocks, self.blockCount, self.bitmapSize, \
            self.badBlocks = struct.unpack('<5Q', buffer[:40])
        self.parseStrings(40, buffer, [('label', 64)])

    def getBlockSize(self) -> int:
        "Return size of one block in bytes, e.g. 512 or 8192."
        return self.blockSize

    def getUsedBlocks(self) -> int:
        "Return the number of blocks that were in use when the image was saved."
        return self.usedBlocks

    def getBlockCount(self) -> int:
        "Return the total number of blocks, used and unused blocks."
        return self.blockCount

    def getBitmapSize(self) -> int:
        "Return the size of the bitmap in bytes."
        return self.bitmapSize

    def getLabel(self) -> str:
        "Return the label of the file system. Empty unless it had a label."
        return self.label


#######################################################################
#                             InfoHeader                              #
#######################################################################

class InfoHeader(Header):
    """
    Base class for Info Headers.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.AfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'Info Header'

    def __init__(self, buffer: bytes):
        super().__init__('Info', buffer)

class AfsInfoHeader(InfoHeader):
    """
    Builds an AFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.AfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME     = 'AFS Info Header'
    DUMP_HEX = ['flags']

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'AFS Info', buffer)
        self.byteOrder, self.blockShift, self.blockPerGroup, \
            self.allocGrpShift, self.allocGroupCount, self.flags, \
            self.bootLoaderSize, self.bitmapStart = struct.unpack('<7LQ',
                                                                  buffer[:36])

class BefsInfoHeader(InfoHeader):
    """
    Builds a BEFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.BefsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME     = 'BEFS Info Header'
    DUMP_HEX = ['flags']

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'Befs Info', buffer)
        self.byteOrder, self.blockShift, self.blockPerGroup, \
            self.allocGrpShift, self.allocGroupCount, self.flags, \
            self.bootLoaderSize, self.bitmapStart = struct.unpack('<7LQ',
                                                                  buffer[:36])

class ExtInfoHeader(InfoHeader):
    """
    Builds an EXT2/3 Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.ExtInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME     = 'Ext2/3 Info Header'
    DUMP_HEX = [ 'featureCompat', 'featureIncompat', 'featureRoCompat' ]

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'Ext2/3 Info', buffer)
        self.groupsCount, self.totalBlocksCount, self.firstBlock, \
            self.blockSize, self.logicalBlocksPerExt2Block, \
            self.blocksPerGroup, self.featureCompat, self.featureIncompat, \
            self.featureRoCompat, self.revLevel = struct.unpack('<10L',
                                                                buffer[:40])
        self.uuid = uuid.UUID(bytes_le=buffer[40:56])
        self.descBlocks, self.descPerBlock = struct.unpack('<2L', buffer[56:64])

class FatInfoHeader(InfoHeader):
    """
    Builds a FAT Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.FatInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'FAT Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'FAT Info', buffer)
        self.totalSectorsCount, self.clustersCount, self.rootDirSectors, \
            self.rootEntriesCount, self.sectorsPerFAT, self.dataSectors, \
            self.fileSystem, self.usedClusters, self.damagedClusters, \
            self.freeClusters, self.bytesPerFatEntry, _, self.bytesPerSector, \
            self.reservedSectors, self.rootEntries, self.sectorsPerCluster, \
            self.numberOfFATs, self.fsInfoSector = struct.unpack('<12L3H2BH',
                                                                 buffer[:58])

class HfsInfoHeader(InfoHeader):
    """
    Builds an HFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.HfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'HFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'HFS Info', buffer)
        self.allocCount, self.bitmapSectLocation, self.freeAllocs, \
            self.firstAllocBlock, self.allocSize, \
            self.blocksPerAlloc = struct.unpack('<4Q2L', buffer[:40])

class HpfsInfoHeader(InfoHeader):
    """
    Builds an HPFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.HpfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'HPFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'HPFS Info', buffer)
        self.bitmapPointer, self.bitmapQuadBlocksCount, \
            self.hpfsVersion = struct.unpack('<2LB', buffer[:9])

class JfsInfoHeader(InfoHeader):
    """
    Builds a JFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.JfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'JFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'JFS Info', buffer)
        self.officialBlocksCount, self.mappedBlocksByBitmap, \
            self.allocTreeMaxLevel = struct.unpack('<2QL', buffer[:20])

class NtfsInfoHeader(InfoHeader):
    """
    Builds a NTFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.NtfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME     = 'NTFS Info Header'
    DUMP_HEX = ['LCNOfMftDataAttrib']

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'NTFS Info', buffer)
        self.totalSectorsCount, self.LCNOfMftDataAttrib, self.FileRecordSize, \
            self.clusterSize, self.bytesPerSector, self.ntfsVersion, \
            self.sectorsPerCluster = struct.unpack('<2Q2L2HB', buffer[:29])

class ReiserInfoHeader(InfoHeader):
    """
    Builds a ReiserFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.ReiserInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'ReiserFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'ReiserFS Info', buffer)
        self.version, self.bitmapBlocksCount = struct.unpack('<2L', buffer[:8])

class UfsInfoHeader(InfoHeader):
    """
    Builds a UFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.UfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'UFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'UFS Info', buffer)
        self.cylinderGroupsCount, self.fs_fpg, self.fs_cgoffset, \
            self.fs_cgmask, self.fs_cblkno, self.fragsPerBlock, \
            self.cylinderGroupSize, self.basicBlockSize, \
            self.dataFrags = struct.unpack('<8LQ', buffer[:40])

class XfsInfoHeader(InfoHeader):
    """
    Builds an XFS Info Header.

    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: imagebackup.partimage.XfsInfoHeader
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    NAME = 'XFS Info Header'

    def __init__(self, buffer: bytes):
        Header.__init__(self, 'XFS Info', buffer)
        self.AgCount, self.AgBlocksCount = struct.unpack('<2L', buffer[:8])

def buildInfoHeader(filesystem: str, buffer: bytes) -> InfoHeader:
    """
    Builds an info header for the given file system.

    :param filesystem: file system
    :type filesystem: str
    :param buffer: 16384 bytes of header plus 4 bytes CRC. 
    :type buffer: bytes
    :returns: derived class of *InfoHeader*
    :raises imagebackup.partimage.PartImageException: when CRC does not match.
    """
    if filesystem == 'afs':
        return AfsInfoHeader(buffer)
    elif filesystem == 'befs':
        return BefsInfoHeader(buffer)
    elif filesystem.startswith('fat'):
        return FatInfoHeader(buffer)
    elif filesystem.startswith('ext'):
        return ExtInfoHeader(buffer)
    elif filesystem.startswith('hfs'):
        return HfsInfoHeader(buffer)
    elif filesystem == 'hpfs':
        return HpfsInfoHeader(buffer)
    elif filesystem == 'jfs':
        return JfsInfoHeader(buffer)
    elif filesystem == 'ntfs':
        return NtfsInfoHeader(buffer)
    elif filesystem.startswith('reiserfs'):
        return ReiserInfoHeader(buffer)
    elif filesystem == 'ufs':
        return UfsInfoHeader(buffer)
    elif filesystem == 'xfs':
        return XfsInfoHeader(buffer)
    else:
        print(f"Warning: Info Header for filesystem '{filesystem}' "
              "not implemented.")
        return InfoHeader(buffer)


#######################################################################
#                              PartImage                              #
#######################################################################

class PartImage(ImageBackup):
    """
    This class reads the headers of a partimage image, checks for
    the supported version (version 2), compares the headers' crc32's and reads
    the bitmap.

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :param filename: The open file's name.
    :type filename: str
    :param block_offset_size: is a parameter for the index; defaults to 1024 bits.
    :type block_offset_size: int
    :raises imagebackup.imagebackup.WrongImageFile: if the image file is not a partclone image.
    :raises imagebackup.partimage.PartImageException: if the image file is truncated or either the version number or any of the checksums differ.
    """

    MAGIC_BEGIN        = b'MAGIC-BEGIN-'
    THRESHOLD          = len(MAGIC_BEGIN) + 16

    VOLUME_HEADER_SIZE = VolumeHeader.HEADER_SIZE
    READ_SIZE          = 1024
    HEADER_SIZE        = Header.HEADER_SIZE
    TAIL_SIZE          = 28

    # In the data blocks section we expect a check  of size CHECK_SIZE
    # every CHECK_FREQUENCY bytes that starts with CHECK_MAGIC.
    CHECK_FREQUENCY    = 65536
    CHECK_MAGIC        = b'CHK\x00'
    CHECK_SIZE         = 16

    def __init__(self, file: io.BufferedIOBase, filename: str,
                 block_offset_size: int = ImageBackup.BLOCK_OFFSET_SIZE):
        super().__init__(file, filename, block_offset_size)

        self.local            = bytes()
        self.bitmap           = bytes()
        self.info             = bytes()
        self.global_cksum     = 0
        self.segment          = ''
        self.dataBlocksOffset = -1
        self.address          = self.VOLUME_HEADER_SIZE
        self.max_block_range  = 0

        self.volume_header = VolumeHeader(file, filename)

        if self.volume_header.getVolumeNo() != 0:
            raise PartImageException(f"File '{self.filename}' is not the first "
                                     "volume of an image.")

        self.segment = 'MAIN-HEADER'
        self.buffer = self.file.read(self.HEADER_SIZE)
        if len(self.buffer) < self.HEADER_SIZE:
            raise PartImageException(f"File '{self.filename}' truncated; "
                                     f"only {len(self.buffer)} of "
                                     f"{self.HEADER_SIZE} read.")
        self.main_header = MainHeader(self.buffer)
        self.dispose_buffer(self.HEADER_SIZE)
        self.checksum_size = self.CHECK_SIZE

        while True:
            if (idx := self.buffer.find(self.MAGIC_BEGIN)) != -1:

                # Need more data to parse MAGIC-BEGIN?
                if idx > len(self.buffer) - self.THRESHOLD:
                    self.dispose_buffer(len(self.buffer) - idx)
                    self.buffer += self.file.read(self.READ_SIZE)
                    idx = 0

                # Parse MAGIC-BEGIN to the end.
                idx2 = idx + len(self.MAGIC_BEGIN)
                while idx2 < len(self.buffer) and \
                      (((ch := self.buffer[idx2]) >= ord('0') and \
                         ch <= ord('9')) or
                       (ch >= ord('A') and ch <= ord('Z'))):
                    idx2 += 1

                # More than one MAGIC-BEGIN parsed?
                if (idx3 := self.buffer[idx+len(self.MAGIC_BEGIN):
                                   idx2].find(self.MAGIC_BEGIN)) != -1:
                    idx2 = idx3 + idx + len(self.MAGIC_BEGIN)

                # Single MAGIC-BEGIN parsed.
                segment_name = str(self.buffer[idx:idx2], 'utf-8')
                self.dispose_buffer(idx2)

                if segment_name == 'MAGIC-BEGIN-BITMAP':
                    bm_size = self.local_header.getBitmapSize()
                    if len(self.buffer) < bm_size:
                        self.buffer += self.file.read(bm_size -
                                                      len(self.buffer))
                    if len(self.buffer) < bm_size:
                        raise PartImageException(f"End-of-file while reading "
                                                 "bitmap: read only "
                                                 f"{len(self.buffer):,} of "
                                                 f"{bm_size:,} bytes.")
                    self.bitmap = self.buffer[:bm_size]
                    self.dispose_buffer(bm_size)
                elif segment_name in ['MAGIC-BEGIN-LOCALHEADER',
                                      'MAGIC-BEGIN-INFO']:
                    header_size = self.HEADER_SIZE
                    if len(self.buffer) < header_size:
                        self.buffer += self.file.read(header_size -
                                                      len(self.buffer))
                    if segment_name == 'MAGIC-BEGIN-LOCALHEADER':
                        self.local_header = LocalHeader(self.buffer
                                                        [:header_size])
                        self.checksum_blocks = self.CHECK_FREQUENCY // \
                                               self.local_header.getBlockSize()
                    else:
                        fs = self.main_header.getFilesystem()
                        self.info_header = buildInfoHeader(fs, self.buffer
                                                           [:header_size])
                    self.dispose_buffer(header_size)
                elif segment_name == 'MAGIC-BEGIN-DATABLOCKS':
                    self.dataBlocksOffset = self.address
                    return
            else:

                self.dispose_buffer(len(self.buffer))
                self.buffer = self.file.read(self.READ_SIZE)
                if not self.buffer:
                    raise PartImageException("End-of-file while reading "
                                             "headers.")

    def usedBlocksRange(self, idx: int) -> Tuple[int, int]:
        """
        Returns a range of used blocks, a pair with the starting number and
        the number of consecutive used blocks. An initial starting
        number `idx` is provided by the caller. If that block is used, it will
        be returned along with the number of consecutive used blocks.

        When all used blocks have been exhausted, (-1, 0) will be returned.
        There is an upper bound to the number of consecutive blocks computed:
        no more than `max_block_range` will be returned in a single call. This
        exact upper bound is necessary for the CRC checks to work properly.
        """
        byte_idx, bit_idx = divmod(idx, 8)
        assert byte_idx < len(self.bitmap)
        byte = self.bitmap[byte_idx]
        start_idx = -1
        length = 0

        byte &= ((1 << bit_idx) - 1) ^ 255
        if byte:
            while bit_idx < 8:
                if (1 << bit_idx) & byte:
                    if length == 0:
                        start_idx = 8 * byte_idx + bit_idx
                        length = 1
                    else:
                        length += 1
                else:
                    if length != 0:
                        return start_idx, length
                bit_idx += 1

        byte_idx += 1
        bit_idx = 0
        if length == 0:
            while byte_idx < len(self.bitmap) and \
                  (byte := self.bitmap[byte_idx]) == 0:
                byte_idx += 1

            if byte_idx >= len(self.bitmap):
                return start_idx, length

            for bit_idx in range(8):
                if (1 << bit_idx) & byte:
                    if length == 0:
                        start_idx = 8 * byte_idx + bit_idx
                        length = 1
                    else:
                        length += 1
                else:
                    if length != 0:
                        return start_idx, length
            byte_idx += 1

        while byte_idx < len(self.bitmap) and \
              (byte := self.bitmap[byte_idx]) == 0xff:
            length += 8
            if length >= self.max_block_range:
                return start_idx, self.max_block_range
            byte_idx += 1

        if byte_idx >= len(self.bitmap):
            return start_idx, length

        for bit_idx in range(8):
            if (1 << bit_idx) & byte:
                length += 1
            else:
                break

        return start_idx, min(length, self.max_block_range)

    def blockReader(self, progress_bar: bool = True, verify_crc: bool = False,
                    fn: Optional[Callable[[int,bytes],None]] = None) -> None:
        """
        Reads all used blocks and verifies all checksums. If **fn** is not
        *None* it will be called for each block.

        :param progress_bar: Whether or not to show progress bar while reading blocks; *True* by default.
        :type progress_bar: bool = True

        :param verify_crc: Whether or not to compute and verify checksums while reading blocks; *False* by default.
        :type verify_crc: bool = False

        :param fn: An optional function that is called with two parameters, the offset into the partition and the data for each block. *None* by default.
        :type fn: Optional[Callable[[int,bytes],None]] = None
        :raises imagebackup.partimage.PartImageException: when the image is corrupted.
        """
        with tqdm(total=self.usedBlocks(), unit=' used blocks',
                  unit_scale=True, disable=not progress_bar) as progress:
            check_count = no_blocks = prev_no_blocks = crc = 0
            block_size  = self.local_header.getBlockSize()
            block_count = self.local_header.getBlockCount()

            self.max_block_range = (1 << 18) // block_size

            block_start = block_length = 0
            while (next_used := self.usedBlocksRange(block_start +
                                                     block_length))[1]:
                block_start, block_length = next_used

                for block_no in range(block_start, block_start + block_length):
                    if block_no == block_count:
                        break
                    no_blocks += 1
                    if no_blocks % 4096 == 0:
                        if no_blocks > prev_no_blocks:
                            progress.update(no_blocks - prev_no_blocks)
                            prev_no_blocks = no_blocks
                    check_count += block_size
                    crc_check = check_count >= self.CHECK_FREQUENCY
                    read_size = block_size + self.CHECK_SIZE if crc_check \
                                                             else block_size
                    if len(self.buffer) < block_size:
                        self.buffer += self.file.read(block_size -
                                                      len(self.buffer))
                    if len(self.buffer) < block_size:
                        self.openNextVolume(len(self.buffer), block_size)
                        self.buffer += self.file.read(block_size -
                                                      len(self.buffer))
                    if len(self.buffer) < block_size:
                        raise PartImageException("End-of-file reading block "
                                                 f"{block_no:,}: read only "
                                                 f"{len(self.buffer):,} of "
                                                 f"{block_size:,} bytes.")

                    # block is self.buffer[:block_size]
                    crc = crcUpdate(self.buffer[:block_size], crc)
                    if fn is not None:
                        fn(block_no, self.buffer[:block_size])
                    self.dispose_buffer(block_size)

                    if crc_check:
                        if len(self.buffer) < self.CHECK_SIZE:
                            self.buffer += self.file.read(self.CHECK_SIZE -
                                                          len(self.buffer))
                        if len(self.buffer) < self.CHECK_SIZE:
                            self.openNextVolume(len(self.buffer),
                                                self.CHECK_SIZE)
                            self.buffer += self.file.read(self.CHECK_SIZE -
                                                          len(self.buffer))
                        if len(self.buffer) < self.CHECK_SIZE:
                            raise PartImageException(
                                "End-of-file reading check: "
                                f"read only {len(self.buffer)}"
                                f" of {self.CHECK_SIZE} bytes.")
                        magic = self.buffer[:4]
                        if magic != self.CHECK_MAGIC:
                            raise PartImageException(
                                f"Check failed: expected CHK "
                                f"and CRC after block {block_no:,}.")
                        check_crc, check_pos = struct.unpack('<LQ',
                                                self.buffer[4:self.CHECK_SIZE])
                        self.dispose_buffer(self.CHECK_SIZE)

                        # The check below compares block_start and not block_no.
                        # In order to get this check right, we limit the number
                        # of consecutive used blocks to max_block_range.
                        if check_pos != block_start:
                            raise PartImageException(
                                f"Check failed: expected block"
                                f" {check_pos:,} computed {block_start:,}.")

                        if check_crc != crc:
                            raise PartImageException(
                                f"Check failed: expected CRC "
                                f"{check_crc:08x} computed {crc:08x}.")
                        check_count = 0
                        crc = 0

            if no_blocks > prev_no_blocks:
                progress.update(no_blocks - prev_no_blocks)

        if no_blocks != self.local_header.getUsedBlocks():
            raise PartImageException(f"Internal error: {no_blocks} used in "
                                     "bitmap; "
                                     f"{self.local_header.getUsedBlocks()} "
                                     "in header.")

        if len(self.buffer) < self.TAIL_SIZE:
            self.buffer += self.file.read(self.TAIL_SIZE - len(self.buffer))

        if self.buffer.startswith(b'MAGIC-BEGIN-TAIL'):
            self.dispose_buffer(16)
            crc, volume = struct.unpack('<QL', self.buffer[:12])
            if volume != (volNo := self.volume_header.getVolumeNo()):
                raise PartImageException(f'Volume mismatch: {volume} != '
                                         f'{volNo}.')
            if crc != (self.global_cksum % (1 << 64)):
                raise PartImageException('Global checksum mismatch for volume '
                                         f'{volume}: {crc:016x} != '
                                         f'{self.global_cksum:016x}.')
        else:
            raise PartImageException('Expected MAGIC-BEGIN-TAIL.')

    def openNextVolume(self, got_size: int, need_size: int) -> None:
        """
        partimage can write images to multiple volumes. This method is called
        upon prematurely encountered end-of-file and it tries to open the next
        volume.

        Multiple volumes are only supported when the file is read sequentially,
        is not compressed and the files names end with "000", "001", "002", ...

        :param got_size: Number of bytes that were read from the partimage file.
        :type got_size: int
        :param need_size: Number of bytes needed for a complete block or checksum.
        :type need_size: int
        :raises imagebackup.partimage.PartImageException: when the image is corrupted.
        """
        filename = self.getFilename()
        volumeNo = self.volume_header.getVolumeNo()
        if filename.endswith(f'.{volumeNo:03}'):
            filename = filename[:-3] + f'{volumeNo+1:03}'
            if os.path.exists(filename):
                f = open(filename, 'rb')
                volume = VolumeHeader(f, filename)
                if volume.getVolumeNo() == volumeNo + 1 and \
                   self.volume_header.getIdentifier() == volume.getIdentifier():
                    self.volume_header = volume
                    super().updateFile(f, filename)
                    return
        raise PartImageException(f"End-of-file reading '{self.getFilename()}': "
                                 f"read only {got_size} of {need_size} bytes.")

    def dispose_buffer(self, size: int) -> None:
        """
        Remove `size` bytes of `self.buffer`. Increase `self.address` by
        `size`, checksum the first `size` bytes of `self.buffer`.

        :param size: Number of bytes to remove from buffer.
        :type size: int
        :raises imagebackup.partimage.PartImageException: when the image is corrupted.
        """

        if size > len(self.buffer):
            raise PartImageException(f"File {self.getFilename()} is corrupted.")

        # Update address.
        self.address += size

        # Update global checksum.
        self.global_cksum += sum(self.buffer[:size])

        # Update buffer.
        self.buffer = self.buffer[size:]

    def getVolumeHeader(self) -> VolumeHeader:
        return self.volume_header

    def getMainHeader(self) -> MainHeader:
        return self.main_header

    def getLocalHeader(self) -> LocalHeader:
        return self.local_header

    def getInfoHeader(self) -> InfoHeader:
        return self.info_header

    def getTool(self) -> str:
        """
        Return tool for image backups.

        :returns: string *'partimage'*.
        """
        return 'partimage'

    def fsType(self) -> str:
        """
        Return file system type.

        :returns: an upper-case string like *'NTFS'* or *'BTRFS'*.
        """
        return self.main_header.getFilesystem().upper()

    def blockSize(self) -> int:
        """
        Return file system's block size.

        :returns: size of file system block in bytes.
        """
        return self.local_header.getBlockSize()

    def totalSize(self) -> int:
        """
        Return file system's total size in bytes.

        :returns: file system's total size in bytes.
        """
        return self.main_header.getPartitionSize()

    def totalBlocks(self) -> int:
        """
        Return file system's total number of blocks.

        :returns: file system's total number of blocks.
        """
        return self.local_header.getBlockCount()

    def usedBlocks(self) -> int:
        """
        Return file system's number of blocks in use.

        :returns: file system's number of blocks in use.
        """
        return self.local_header.getUsedBlocks()

    def blocksSectionOffset(self) -> int:
        """
        Return offset of Blocks section in image file.

        :returns: the offset of the very first in-use block in the image file.
        """
        return self.dataBlocksOffset

    def __str__(self) -> str:
        return 'PartImage\n=========\n' + str(self.volume_header) + '\n' + \
            str(self.main_header) +  '\n' + str(self.local_header) + '\n' + \
            str(self.info_header)
