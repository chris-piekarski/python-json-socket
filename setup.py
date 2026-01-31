#!/usr/bin/env python

from setuptools import setup, Extension
import pathlib
import re


def _read_version():
    version_file = pathlib.Path(__file__).parent / "jsocket" / "_version.py"
    content = version_file.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]', content, re.M)
    if not match:
        raise RuntimeError("Unable to find __version__ in jsocket/_version.py")
    return match.group(1)


def _read_long_description():
    readme = pathlib.Path(__file__).parent / "README.md"
    return readme.read_text(encoding="utf-8")

setup(name='jsocket',
      version=_read_version(),
      description='Python JSON Server & Client',
      long_description=_read_long_description(),
      long_description_content_type='text/markdown',
      author='Christopher Piekarski',
      author_email='chris@cpiekarski.com',
      maintainer='Christopher Piekarski',
      maintainer_email='chris@cpiekarski.com',
      license='OSI Approved Apache Software License',
      keywords=['json','socket','server','client'],
      packages=['jsocket'],
      provides=['jsocket'],
      python_requires='>=3.8',
      license_files=['LICENSE'],
      classifiers=[
                   'Intended Audience :: Developers',
                   'Programming Language :: Python :: 3.9',
                   'Operating System :: OS Independent',
                   'Development Status :: 5 - Production/Stable',
                   'Topic :: System :: Networking',
                   'Topic :: Software Development :: Libraries :: Application Frameworks',
                   'Topic :: System :: Distributed Computing',
                   'Topic :: System :: Hardware :: Symmetric Multi-processing',
                   ],
      url='https://cpiekarski.com/2012/01/25/python-json-client-server-redux/'
     )
