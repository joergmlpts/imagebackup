import io
from dataclasses import dataclass
from typing import Callable, List, Optional


#######################################################################
#                              Exceptions                             #
#######################################################################

class ImageBackupException(Exception):
    """
    This exception is raised for any issues encountered
    with reading the backup image.
    """
    def __init__(self, msg: str):
        super().__init__(msg)


#######################################################################
#                              32-bit CRC                             #
#######################################################################

CRC32_SEED = 0xffffffff

try:
    from imagebackup.crc import crc32 as external_crc32

    def crc32(buffer: bytes, seed = CRC32_SEED) -> int:
        """
        Compute crc32 for the given buffer.

        :param buffer: buffer to compute crc32 for.
        :type buffer: bytes
        :param seed: seed to start crc32 computation from, default *0xffffffff*.
        :type seed: int
        :returns: 32-bit crc
        """
        return external_crc32(buffer, seed)

except ImportError:

    def crc(byte: int) -> int:
        "Computes the CRC32_TABLE cached values."
        crc = byte
        for j in range(8):
            crc = (crc >> 1) ^ 0xedb88320 if crc & 1 else crc >> 1
        return crc

    CRC32_TABLE = [crc(i) for i in range(256)]

    del crc

    def crc32(buffer: bytes, seed = CRC32_SEED) -> int:
        """
        Compute crc32 for the given buffer.

        :param buffer: buffer to compute crc32 for.
        :type buffer: bytes
        :param seed: seed to start crc32 computation from, default *0xffffffff*.
        :type seed: int
        :returns: 32-bit crc
        """
        crc = seed
        for b in buffer:
            crc = (crc >> 8) ^ CRC32_TABLE[(crc ^ b) & 0xff]
        return crc


#######################################################################
#                          Numbers of Bits Set                        #
#######################################################################

BITS_SET = [bin(i).count('1') for i in range(256)]
"""The number of bits set for each byte."""


#########################################################################
#                              BlockOffset                              #
#########################################################################

@dataclass
class BlockOffset:
    """
    This class is used in an index to compute the offset in the image
    file for a given block. This is used for image backups based on
    bitmaps.
    """

    file_offset : int
    "offset into image file"
    cksum_offset: int
    ">= 0 and < ImageBackup.checksum_blocks"


#######################################################################
#                              ImageBackup                            #
#######################################################################

class ImageBackup:
    """
    Base class of *PartClone*, *PartImage*, and *NtfsCLone*. This base class
    stores the file, file name and bitmap and provides an index based on the
    bitmap.

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase

    :param filename: The open file's name.
    :type filename: str
    """

    PARTCLONE = b'partclone-image'
    PARTIMAGE = b'PaRtImAgE-VoLuMe' + bytes(16)
    NTFSCLONE = b'\0ntfsclone-image'

    BLOCK_OFFSET_SIZE = 1024
    "Allocate an index for every 128 bytes; a reasonable default for indexing."

    def __init__(self, file: io.BufferedIOBase, filename: str,
                 block_offset_size: int):
        self.file = file
        self.filename = filename
        self.bitmap = bytes()
        self.checksum_size = 0
        self.checksum_blocks = 0
        self.block_offset_size = block_offset_size
        self.block_offsets: List[BlockOffset] = []

    def getFile(self) -> io.BufferedIOBase:
        """
        Return open binary file.

        :returns: open binary file.
        """
        return self.file

    def getFilename(self) -> str:
        """
        Return name of open binary file.

        :returns: name of open binary file.
        """
        return self.filename

    def updateFile(self, file: io.BufferedIOBase, filename: str):
        """
        Update file and filename.

        :param file: Binary file opened for input.
        :type file: io.BufferedIOBase

        :param filename: The open file's name.
        :type filename: str
        """
        if file != self.file:
            self.file.close()
        self.file = file
        self.filename = filename

    def getTool(self) -> str:
        """
        Return tool for image backups.

        :returns: string *'ntfsclone'*, *'partclone'*, or *'partimage'*.
        """
        return 'n/a'

    def fsType(self) -> str:
        """
        Return file system type.

        :returns: an upper-case string like *'NTFS'* or *'BTRFS'*.
        """
        return ''

    def blockSize(self) -> int:
        """
        Return file system's block size.

        :returns: size of file system block in bytes.
        """
        return -1

    def totalSize(self) -> int:
        """
        Return file system's total size in bytes.

        :returns: file system's total size in bytes.
        """
        return -1

    def totalBlocks(self) -> int:
        """
        Return file system's total number of blocks.

        :returns: file system's total number of blocks.
        """
        return -1

    def usedBlocks(self) -> int:
        """
        Return file system's number of blocks in use.

        :returns: file system's number of blocks in use.
        """
        return -1

    def bitMap(self) -> Optional[bytes]:
        """
        Return the bitmap for image files that have bitmaps, *None* otherwise.

        :returns: bitmap or *None*.
        """
        return self.bitmap

    def blocksSectionOffset(self) -> int:
        """
        Return offset of Blocks section in image file.

        :returns: the offset of the very first in-use block in the image file.
        """
        return -1

    def blockInUse(self, block_no: int) -> bool:
        """
        Returns *True* if *block_no* is in use, *False* otherwise.

        :param block_no: block number
        :type block_no: int
        :returns: *True* if *block_no* is in use, *False* otherwise.
        :raises imagebackup.imagebackup.ImageBackupException: if the block number is out of range.
        """
        if block_no < 0 or block_no // 8 >= len(self.bitmap):
            raise ImageBackupException(f"Block {block_no} is out of range.")
        return bool(self.bitmap[block_no // 8] & (1 << (block_no & 7)))

    def buildBlockIndex(self, progress_bar: bool = True) -> None:
        """
        Builds an index of available blocks. This is done unless the image is
        going to be read only sequentially.

        :param progress_bar: ignored as we are builing the index from bitmap.
        :type progress_bar: bool = True
        """
        if self.block_offsets:
            return
        file_offset = self.blocksSectionOffset()
        block_size = self.blockSize()
        blocks_chksum = 0
        block_offset = BlockOffset(file_offset, 0)
        for idx1 in range(0, len(self.bitmap), self.block_offset_size // 8):
            if file_offset != block_offset.file_offset:
                block_offset = BlockOffset(file_offset, blocks_chksum)
            self.block_offsets.append(block_offset)
            idx2 = min(idx1+self.block_offset_size // 8, len(self.bitmap))
            inuse_blocks = sum(BITS_SET[b] for b in self.bitmap[idx1:idx2]
                               if b != 0)
            blocks_chksum += inuse_blocks
            file_offset += block_size * inuse_blocks
            if self.checksum_blocks:
                if blocks_chksum >= self.checksum_blocks:
                    file_offset += self.checksum_size * (blocks_chksum //
                                                         self.checksum_blocks)
                    blocks_chksum %= self.checksum_blocks

    def getBlockOffset(self, block_no: int) -> Optional[int]:
        """
        Return offset of block in image file or None if block is not in use.

        :param block_no: block number
        :type block_no: int
        :returns: offset of block in image file if the block is in use, *None* otherwise.
        :raises imagebackup.imagebackup.ImageBackupException: if the block number is out of range.
        """

        if not self.blockInUse(block_no):
            return None

        if not self.block_offsets:
            self.buildBlockIndex()

        block_size       = self.blockSize()
        block_offset_idx = block_no // self.block_offset_size
        block_offset     = self.block_offsets[block_offset_idx]

        bm_idx1          = block_offset_idx * (self.block_offset_size // 8)
        bm_idx2          = block_no // 8

        file_offset      = block_offset.file_offset
        blocks_cksum     = block_offset.cksum_offset

        inuse_blocks = sum(BITS_SET[b] for b in
                           self.bitmap[bm_idx1:bm_idx2] if b != 0) + \
                       BITS_SET[self.bitmap[bm_idx2] & ((1 << (block_no%8))-1)]
        blocks_cksum += inuse_blocks
        file_offset += block_size * inuse_blocks
        if self.checksum_blocks:
            if blocks_cksum >= self.checksum_blocks:
                file_offset += self.checksum_size * (blocks_cksum //
                                                     self.checksum_blocks)
        return file_offset


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
        """
        return None


def reportSize(size: int) -> str:
    """
    Report size in appropriate unit (B, KB, MB, GB, TB, ...).

    :param size: Size in bytes to be reported.
    :type size: int
    :returns: size as string notation with appropriate unit.
    """
    units = [ 'B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB' ]
    for k in range(len(units)-1, -1, -1):
        if k == 0:
            return f'{size} {units[k]}'
        sz_unit = 1 << (k * 10)
        if size >= sz_unit:
            return f'{size/sz_unit:.1f} {units[k]}'
    assert False
