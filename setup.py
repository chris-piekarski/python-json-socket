#!/usr/bin/env python

from distutils.core import setup

setup(name='jsocket',
      version='1.4',
      description='Python JSON Server & Client',
      author='Christopher Piekarski',
      author_email='chris@cpiekarski.com',
      maintainer='Christopher Piekarski',
      maintainer_email='chris@cpiekarski.com',
      license='OSI Approved Apache Software License',
      keywords=['json','socket','server','client'],
      packages=['jsocket'],
      provides=['jsocket'],
      classifiers=[
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: Apache Software License',
                   'Programming Language :: Python :: 2.7',
                   'Operating System :: OS Independent',
                   ],
      url='http://cpiekarski.com/2011/05/09/super-easy-python-json-client-server/'
     )
