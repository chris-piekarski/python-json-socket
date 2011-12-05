#!/usr/bin/env python

from distutils.core import setup

setup(name='JsonSocket',
      version='1.3',
      description='Python JSON Server & Client',
      author='Christopher Piekarski',
      author_email='polo1065@gmail.com',
      keywords=['json','socket','server','client'],
      classifiers=[
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: Apache Software License',
                   'Programming Language :: Python :: 2.7',
                   'Operating System :: OS Independent',
                   ],
      url='http://cpiekarski.com/2011/05/09/super-easy-python-json-client-server/',
      py_modules=['jsonSocket', 'threadedServer','customServer'],
     )