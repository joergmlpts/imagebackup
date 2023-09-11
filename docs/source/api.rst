.. _api:

API
===

*Partclone* and *partimage* images consist of three components, header (4
headers in partimage), bitmap and blocks of data. A description of the
`partclone image file format <https://github.com/Thomas-Tsai/partclone/blob/master/IMAGE_FORMATS.md>`_
is available. Package *imagebackup* provides classes to read and process these
three components.

*Ntfsclone* images do not contain a bitmap. They consist of a header and blocks
of used blocks and counts of unused blocks of data.


PartClone, PartImage and NtfsClone
----------------------------------

Classes *PartClone*, *PartImage*, and *NtfsClone* are instantiated with an open
binary file and its file name, they read the header and - in case of PartClone
and PartImage - also the bitmap of the image. If the file is not a supported
image, they raise exception *ImageBackupException*.

.. code-block::

   from imagebackup.imagebackup import ImageBackupException
   from imagebackup.partclone import PartClone
   from imagebackup.partimage import PartImage
   from imagebackup.ntfsclone import NtfsClone

   with open('sda1.img', 'rb') as file:

      try:

          image = PartClone(file, 'sda1.img')

          print(image)

      except ImageBackupException as e:
          print('Failed to read image:', e)

If the image file can be opened, the header is printed and looks like this:

.. code-block::

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

The header can also be read from a pipe, a regular file is not necessary.

The bitmap represents each block with one bit and indicates whether the block
is in use or not. Only if a block is in use its data is saved to the image file.
There is not much besides the actual bitmap, just a checksum. The members
`block_offset_size` and `block_offsets` have not been read from the image file.
They implement indexing which allows to read data blocks from the image quickly
and in an arbitray order.

Blocks
------

Once the header and bitmap have been read, we can read all used blocks from the
partition. Method *blockReader* reads all used blocks in sequence:

.. autofunction:: imagebackup.imagebackup.ImageBackup.blockReader
   :noindex:

Here are two examples for its parameter *fn*, the function which is called
with each block of data:

.. code-block::

   with open('/dev/sda1', 'rb+') as f_out:

       def write_block(offset: int, block: bytes) -> None:
           f_out.seek(offset)
           f_out.write(block)

       image.blockReader(fn=write_block)


The function is only called for used blocks. Unused blocks are not even stored
in the image file. However, since method *blockReader* calls the function
strictly in ascending order of the offset, unused blocks can be written as well.
The following code fills them with *0xdeadbeef*, a pattern that is easily
recognized in hex dumps:

.. code-block::

   with open('sda1.vol', 'wb') as f_out:
       block_size  = image.blockSize()
       empty_block = bytes([0xde, 0xad, 0xbe, 0xef] * (block_size // 4))
       last_offset = 0

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


Note that *write_block* does not call *f_out.seek* anymore. In this scenario
the output file is written sequentially.

BlockIO
-------

There are situations where the blocks in an image file need to be read in random
order. Class *BlockIO* allows random access to arbitrary ranges of bytes.

.. autoclass:: imagebackup.blockio.BlockIO
   :noindex:
   :members:

The image file will not be read sequentially in this scenario. It has to be a
regular file and must not be compressed.

.. code-block::

   from imagebackup.blockio import BlockIO

   blockio = BlockIO(image)

   # read 42 bytes at offset 100000 and dump them in hex
   print(' '.join(f'{b:02x}' for b in blockio.read_data(offset=100000, size=42)))

Opening Image Files
-------------------

Image files are usually compressed and may be split into smaller files
named *.aa*, *.ab*, ... This package contains functionality to detect and read
split and compressed image files. All common compression algorithms - *gzip*,
*bzip2*, *zstandard*, *lz4*, *lzma*, and *xz* - are supported.

.. autofunction:: imagebackup.utilities.uncompress
   :noindex:

The parameter *errorOut* can be *False* when the caller is going to read the
image sequentially. It must be *True* for random access since the *seek* method
is prohibitively slow for compressed files. Split files are fully supported for
random access.

Image files can also be opened in a generic manner where it either a
*partclone*, *partimage*, or *ntfsclone* image and the caller does not
need to know beforehand which kind it is.

.. autofunction:: imagebackup.main.readImage
   :noindex:

There is no need to call *uncompress*; function *readImage* calls *uncompress*
internally. This is an example for calling *readImage*:

.. code-block::

   from imagebackup.imagebackup import ImageBackup, ImageBackupException
   from imagebackup.ntfsclone import NtfsClone
   from imagebackup.main import readImage

   with open('sda1.img', 'rb') as file:

      try:

          image = readImage(f=file,
                            block_index_size=ImageBackup.BLOCK_OFFSET_SIZE,
                            sequential=True,
                            fn=lambda f:NtfsClone(f))
          print(image)

      except ImageBackupException as e:
          print('Failed to read image:', e)

This piece of code will not only read *ntfsclone* images but also *partclone*
and *partimage* files, even compressed and split ones.


Detailed API Documentation
==========================

Module imagebackup
------------------

.. automodule:: imagebackup.imagebackup
   :members:

Module ntfsclone
----------------

.. automodule:: imagebackup.ntfsclone
   :members:

Module partclone
----------------

.. automodule:: imagebackup.partclone
   :members:

Module partimage
----------------

.. automodule:: imagebackup.partimage
   :members:

Module blockio
--------------

.. automodule:: imagebackup.blockio
   :members:

Module fuse
-----------

.. automodule:: imagebackup.fuse
   :members:

Module utilities
----------------

.. automodule:: imagebackup.utilities
   :members:

Module main
-----------

.. automodule:: imagebackup.main
   :members:
