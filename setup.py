#!/usr/bin/env python

from setuptools import setup, Extension

setup(name='jsocket',
      version='1.6.1',
      description='Python JSON Server & Client',
      author='Christopher Piekarski',
      author_email='chris@cpiekarski.com',
      maintainer='Christopher Piekarski',
      maintainer_email='chris@cpiekarski.com',
      license='OSI Approved Apache Software License',
      keywords=['json','socket','server','client'],
      packages=['jsocket'],
      provides=['jsocket'],
      python_requires='==2.7.*',
      classifiers=[
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: Apache Software License',
                   'Programming Language :: Python :: 2.7',
                   'Operating System :: OS Independent',
                   'Development Status :: 5 - Production/Stable',
                   'Topic :: System :: Networking',
                   'Topic :: Software Development :: Libraries :: Application Frameworks',
                   'Topic :: System :: Distributed Computing',
                   'Topic :: System :: Hardware :: Symmetric Multi-processing',
                   ],
      url='http://cpiekarski.com/2011/05/09/super-easy-python-json-client-server/'
     )
