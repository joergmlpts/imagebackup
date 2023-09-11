from distutils.core import setup, Extension

def long_description() -> str:
    "Return contents of README.md as long package description."
    with open('README.md', 'rt', encoding='utf-8') as f:
        return f.read()

setup(name='imagebackup',
      version='0.2.1',
      package_dir={'imagebackup': 'src/imagebackup'},
      packages=['imagebackup'],
      author='joergmlpts',
      author_email='joergmlpts@outlook.com',
      description='Python package for partclone, partimage and ntfsclone '
      'backup images & utility to mount image as a virtual partition.',
      readme="README.md",
      long_description=long_description(),
      long_description_content_type='text/markdown',
      url='https://github.com/joergmlpts/imagebackup',
      classifier=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Intended Audience :: End Users/Desktop',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: MIT License',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Programming Language :: Python :: 3',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3.8',
          'Programming Language :: Python :: 3.9',
          'Programming Language :: Python :: 3.10',
          'Programming Language :: Python :: 3.11',
          'Programming Language :: Python :: 3.12',
          'Programming Language :: Python :: 3.13',
          'Topic :: System :: Archiving :: Backup',
          'Topic :: Utilities'
      ],
      entry_points = {
              'console_scripts': [
                  'vpartclone=imagebackup.main:vpartclone',
                  'vntfsclone=imagebackup.main:vntfsclone',
                  'vpartimage=imagebackup.main:vpartimage',
              ],              
          },
      python_requires='>=3.8',
      install_requires=['lz4', 'tqdm', 'pyfuse3', 'zstandard'],
      ext_modules=[Extension('imagebackup.crc',
                             sources=['src/c/crc.c'], optional=True)]
      )
