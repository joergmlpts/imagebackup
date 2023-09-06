#!/usr/bin/env python3

import io, struct
from dataclasses import dataclass
from typing import Callable, List, Optional

from .imagebackup import ImageBackup, ImageBackupException, WrongImageFile, \
                         reportSize

from tqdm import tqdm # install with "pip install tqdm"; on Ubuntu install with "sudo apt install python3-tqdm"


class NtfsCloneException(ImageBackupException):
    """
    This exception is raised for issues encountered when reading ntfsclone
    images.
    """
    def __init__(self, s: str):
        super().__init__(s)

@dataclass
class ClusterRange:
    "Cluster ranges are used for indexing."

    used  : bool
    "Are the clusters in this range used or unused?"

    start : int
    "Starting cluster number."

    size  : int
    "Number of consecutive clusters in this range."

    offset: int
    """
    For used clusters, the offset into the image file for cluster `start`,
    -1 for unused clusters.
    """

    def end(self) -> int:
        "Returns the cluster after the last one in this cluster range."
        return self.start + self.size


class ClusterIndex:
    """
    This class implements the lookup of its offset in the image file for a
    cluster number. Cluster ranges are stored in an array. Binary search in
    this array is used to look up a cluster's offset in the image file.

    :param cluster_size: cluster size (block size)
    :type cluster_size: int
    """

    def __init__(self, cluster_size: int):
        self.cluster_size = cluster_size
        self.cluster_ranges: List[ClusterRange] = []

    def append(self, range: ClusterRange) -> None:
        """
        Insert a cluster range into the index.

        :param range: cluster range
        :type range: ClusterRange
        """
        if self.cluster_ranges:
            assert range.start == self.cluster_ranges[-1].end()
        self.cluster_ranges.append(range)

    def offset(self, cluster: int) -> Optional[int]:
        """
        Return the offset for given cluster in the image file if
        the cluster is used. For unused clusters, None is returned.

        :param cluster: cluster number
        :type cluster: int
        :returns: offset of cluster in image file if the cluster is in use, *None* otherwise.
        """
        # Binary search in cluster ranges.
        l = 0
        r = len(self.cluster_ranges)
        while l < r:
            m = (l + r) // 2
            if cluster < self.cluster_ranges[m].start:
                r = m
            else:
                l = m
                if cluster < self.cluster_ranges[m].end():
                    break
        cr = self.cluster_ranges[l]
        assert cluster >= cr.start and cluster < cr.end()
        # Return offset or None.
        if cr.used:
            return cr.offset + (cluster - cr.start) * (self.cluster_size + 1)
        return None

    def __len__(self) -> int:
        return len(self.cluster_ranges)


class NtfsClone(ImageBackup):
    """
    "This Class reads and processes an ntfsclone image file. The constructor
    reads the header and raises exceptions if the file is not an ntfsclone file.

    :param file: Binary file opened for input.
    :type file: io.BufferedIOBase
    :param filename: The open file's name.
    :type filename: str
    :raises imagebackup.imagebackup.WrongImageFile: if the file is not an ntfsclone image.
    :raises imagebackup.ntfsclone.NtfsCloneException: if the file is too short or the major version number differs.
    """

    HEADER_SIZE = 50
    MAGIC_SIZE  = len(ImageBackup.NTFSCLONE)
    VER_MAJOR   = 10
    VER_MINOR   = 1

    def __init__(self, file: io.BufferedIOBase, filename: str):
        super().__init__(file, filename, ImageBackup.BLOCK_OFFSET_SIZE)

        self.buffer = file.read(self.HEADER_SIZE)

        if len(self.buffer) < self.HEADER_SIZE:
            raise NtfsCloneException(f'Failed to read 50-byte header.')

        if self.buffer[:self.MAGIC_SIZE] != ImageBackup.NTFSCLONE:
            raise WrongImageFile(f'Not an ntfsclone image.', self.buffer)

        self.major_ver, self.minor_ver, self.cluster_size, self.device_size, \
            self.nr_clusters, self.inuse, self.offset_to_image_data = \
                struct.unpack('<2BL3QL', self.buffer[self.MAGIC_SIZE:])

        # Reject different major version, warn if different minor version.
        if self.major_ver != self.VER_MAJOR:
            raise NtfsCloneException(f'Major version {self.major_ver} not '
                                 f'supported; {self.VER_MAJOR} supported.')
        if self.minor_ver != self.VER_MINOR:
            print(f'Warning: minor version {self.minor_ver} not supported; '
                  f'parsing as {self.VER_MAJOR}.{self.VER_MINOR} image file.')

        self.cluster_index = ClusterIndex(self.cluster_size)

        # Skip (usually 6 bytes) to offset_to_image_data.
        file.read(self.offset_to_image_data - self.HEADER_SIZE)

    def bitMap(self) -> Optional[bytes]:
        """
        Return the bitmap for image files that have bitmaps, *None* otherwise.

        :returns: *None*.
        """
        return None

    def buildBlockIndex(self, progress_bar: bool = True) -> None:
        """
        Populates index *self.cluster_index* which is required for
        member function getBlockOffset(). This indexing is done unless
        the image is going to be read only sequentially.

        :param progress_bar: whether to show a progress bar. ntfsclone images do not contain bitmaps. The entire image file needs to be read to index the blocks.
        :type progress_bar: bool = True
        """
        if len(self.cluster_index):
            return
        self.file.seek(self.offset_to_image_data)
        cur_range = ClusterRange(False, 0, 0, -1)
        offset    = self.offset_to_image_data
        with tqdm(total=self.usedBlocks(), unit=' used blocks',
                  unit_scale=True, disable=not progress_bar) as progress:
            cluster_no = blocks_read = prev_blocks_read = 0
            while True:
                cmd = self.file.read(1)
                if len(cmd) == 0:
                    break
                offset += 1

                if cmd[0] == 0:
                    # Cluster is unused. Read # of consecutive unused clusters.
                    count = struct.unpack('<Q', self.file.read(8))[0]
                    offset += 8
                    if cluster_no:
                        self.cluster_index.append(cur_range)
                    cur_range = ClusterRange(False, cluster_no, count, -1)
                    cluster_no += count
                elif cmd[0] == 1:
                    assert offset == self.file.tell()
                    if cluster_no > self.nr_clusters:
                        raise NtfsCloneException('Error: Image file corrupted '
                                                 f'(cluster={cluster_no}).')
                    # read cluster_no at index cluster_no
                    self.file.read(self.cluster_size)
                    if cur_range.used:
                        assert cluster_no == cur_range.end()
                        cur_range.size += 1
                    else:
                        if cluster_no:
                            self.cluster_index.append(cur_range)
                        cur_range = ClusterRange(True, cluster_no, 1, offset)
                    offset += self.cluster_size
                    cluster_no += 1
                    blocks_read += 1
                    if blocks_read % 4096 == 0:
                        progress.update(blocks_read - prev_blocks_read)
                        prev_blocks_read = blocks_read
                else:
                    raise NtfsCloneException('Image file corrupted '
                                             f'(sync={cmd[0]}).')
            self.cluster_index.append(cur_range)
            progress.update(blocks_read - prev_blocks_read)
            prev_blocks_read = blocks_read

    def getBlockOffset(self, block_no: int) -> Optional[int]:
        """
        Return offset of block in image file or *None* if block is not in use.

        :param block_no: block number
        :type block_no: int
        :returns: offset of block in image file if the block is in use, *None* otherwise.
        :raises imagebackup.ntfsclone.NtfsCloneException: if the block number is out of range.
        """

        if block_no < 0 or block_no > self.nr_clusters:
            raise NtfsCloneException(f'Cluster {block_no} out of range.')

        if len(self.cluster_index) == 0:
            self.buildBlockIndex()

        return self.cluster_index.offset(block_no)

    def blockInUse(self, block_no: int) -> bool:
        """
        Returns *True* if *block_no* is in use, *False* otherwise.

        :param block_no: block number
        :type block_no: int
        :returns: *True* if *block_no* is in use, *False* otherwise.
        :raises imagebackup.ntfsclone.NtfsCloneException: if the block number is out of range.
        """
        return self.getBlockOffset(block_no) is not None

    def getTool(self) -> str:
        """
        Return tool for image backups.

        :returns: string *'ntfsclone'*.
        """
        return 'ntfsclone'

    def fsType(self) -> str:
        """
        Return file system type.

        :returns: string *'NTFS'*.
        """
        return 'NTFS'

    def totalBlocks(self) -> int:
        """
        Return file system's total number of blocks.

        :returns: file system's total number of blocks.
        """
        return self.nr_clusters

    def usedBlocks(self) -> int:
        """
        Return file system's number of blocks in use.

        :returns: file system's number of blocks in use.
        """
        return self.inuse

    def blockSize(self) -> int:
        """
        Return file system's block size.

        :returns: size of file system block in bytes.
        """
        return self.cluster_size

    def totalSize(self) -> int:
        """
        Return file system's total size in bytes.

        :returns: file system's total size in bytes.
        """
        return self.device_size

    def blockReader(self, progress_bar: bool = True, verify_crc: bool = False,
                    fn: Optional[Callable[[int,bytes],None]] = None) -> None:
        """
        Reads all used blocks. If **fn** is not *None* it will be called for
        each block.

        :param progress_bar: Whether or not to show progress bar while reading blocks; *True* by default.
        :type progress_bar: bool = True

        :param verify_crc: Whether or not to compute and verify checksums while reading blocks; *False* by default. Ignored as *ntfsclone* images don't contain checksums.
        :type verify_crc: bool = False

        :param fn: An optional function that is called with two parameters, the offset into the partition and the data for each block. *None* by default.
        :type fn: Optional[Callable[[int,bytes],None]] = None
        :raises imagebackup.ntfsclone.NtfsCloneException: if the image file is corrupted.
        """
        with tqdm(total=self.usedBlocks(), unit=' used blocks',
                  unit_scale=True, disable=not progress_bar) as progress:
            cluster = blocks_read = prev_blocks_read = 0

            while True:
                cmd = self.file.read(1)
                if len(cmd) == 0:
                    break

                if cmd[0] == 0:
                    # Cluster is unused. Read # of consecutive unused clusters.
                    count = struct.unpack('<Q', self.file.read(8))[0]
                    cluster += count
                elif cmd[0] == 1:
                    if cluster > self.nr_clusters:
                        raise NtfsCloneException('Image file corrupted '
                                                 f'(cluster={cluster}).')
                    block = self.file.read(self.cluster_size)
                    if fn is not None:
                        fn(cluster * self.cluster_size, block)
                    cluster += 1

                    blocks_read += 1
                    if blocks_read % 4096 == 0:
                        progress.update(blocks_read - prev_blocks_read)
                        prev_blocks_read = blocks_read
                else:
                    raise NtfsCloneException('Image file corrupted '
                                             f'(sync={cmd[0]}).')
            progress.update(blocks_read - prev_blocks_read)
            prev_blocks_read = blocks_read

    def __str__(self) -> str:
        return 'NtfsClone Header\n================\n' \
               f'major_ver           : {self.major_ver}\n' \
               f'minor_ver           : {self.minor_ver}\n' \
               f'cluster_size        : {self.cluster_size:,}\n' \
               f'device_size         : {self.device_size:,} ' \
               f'({reportSize(self.device_size)})\n' \
               f'nr_clusters         : {self.nr_clusters:,}\n' \
               f'inuse               : {self.inuse:,} ' \
               f'({reportSize(self.inuse * self.cluster_size)})\n' \
               f'offset_to_image_data: {self.offset_to_image_data}'

