Welcome to imagebackup's documentation!
=======================================

At a low level, **imagebackup** provides Python code to read the building
blocks - headers, bitmaps, and blocks - of
`partclone <https://partclone.org/>`_, `partimage <https://www.partimage.org/>`_ and `ntfsclone <https://linux.die.net/man/8/ntfsclone>`_ backup images. These
components may be used in other Python projects. They are described in the
:ref:`api` section.

At a higher level, :ref:`utility` based on this low-level code are
also included. Their features are as follows:

* They read partclone, partimage and ntfsclone images, verify checksums and
  dump headers.

* They mount partclone, partimage and ntfsclone images - the backups of
  partitions - as virtual partitions.

These virtual partitions have the contents of the partition. They are created
without allocating additional disk space. Just like a restored partition, for
example, a virtual partition can be subjected to a file system consistency
check (`fsck`).

The virtual partitions can be mounted as file systems. This is done with the
help of a loop device and allows you to inspect the contents. Individual
files and directories can be copied from image backups.

This virtual partition is read-only and cannot be written to.

Check out the :doc:`usage` section for further information, including
the :ref:`installation` of the project.

Contents
--------

.. toctree::

   usage
   api
