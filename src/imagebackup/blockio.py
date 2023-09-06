import io, math

from .imagebackup import ImageBackup, ImageBackupException


#########################################################################
# This class is called with read requests of disk data. It breaks these #
# requests down into reads of full blocks from the image file.          #
#########################################################################

class BlockIO:
    """
    This class fulfills read requests of disk data. It breaks these requests
    down into reads of full blocks from the image file.

    :param image: Binary file opened for input.
    :type image: imagebackup.imagebackup.ImageBackup
    :returns: nothing
    :raises imagebackup.imagebackup.ImageBackupException: if the file is not a regular file.
    """
    
    def __init__(self, image: ImageBackup):
        self.image        = image
        self.image_file   = image.getFile()
        self.block_size   = image.blockSize()
        self.total_blocks = (image.totalSize() + self.block_size - 1) // \
                                self.block_size
        self.total_size   = self.block_size * self.total_blocks
        self.empty_block  = bytes(self.block_size)
        self.image.buildBlockIndex()

    def read_data(self, offset: int, size: int) -> bytes:
        """
        Read *size* bytes at *offset*.

        :param offset: in partition to read bytes from.
        :type offset: int
        :param size: the number of bytes to read at *offset* in the partition.
        :type size: int
        :returns: no bytes if *offset* is negative, *size* bytes if entire range is within partition, fewer bytes otherwise.
        """
        if offset + size > self.total_size:
            size = max(0, self.total_size - offset)
        output = bytes()
        if size > 0:
            min_block = offset // self.block_size
            max_block = (offset + size - 1) // self.block_size
            for block_no in range(min_block, max_block + 1):
                idx1 = offset % self.block_size if block_no == min_block else 0
                idx2 = ((offset + size - 1) % self.block_size) + 1 \
                           if block_no == max_block else self.block_size

                image_file_offset = self.image.getBlockOffset(block_no)
                if image_file_offset is None:
                    block = self.empty_block
                else:
                    self.image_file.seek(image_file_offset)
                    block = self.image_file.read(self.block_size)
                    if len(block) != self.block_size:
                        ImageBackupException(f'Failed to read full block '
                                             'at {image_file_offset:,}.')

                # Append (a subrange of) block to output.
                output += block[idx1:idx2]
        return output

    def getTotalSize(self) -> int:
        """
        Return the total (used and unused blocks) size in bytes.

        :returns: size of partition.
        """
        return self.total_size
