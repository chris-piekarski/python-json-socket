#!/usr/bin/env python

from setuptools import setup, Extension

setup(name='jsocket',
      version='1.9.0',
      description='Python JSON Server & Client',
      author='Christopher Piekarski',
      author_email='chris@cpiekarski.com',
      maintainer='Christopher Piekarski',
      maintainer_email='chris@cpiekarski.com',
      license='OSI Approved Apache Software License',
      keywords=['json','socket','server','client'],
      packages=['jsocket'],
      provides=['jsocket'],
      python_requires='>=3.9',
      classifiers=[
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: Apache Software License',
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
