#!/usr/bin/env python
import sys
import unittest
import re
import os
import ConfigParser
from setuptools import setup, Command


def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


class SQLiteTest(Command):
    """
    Run the tests on SQLite
    """
    description = "Run tests on SQLite"

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        os.environ['TRYTOND_DATABASE_URI'] = 'sqlite://'
        os.environ['DB_NAME'] = ':memory:'

        from tests import suite
        test_result = unittest.TextTestRunner(verbosity=3).run(suite())

        if test_result.wasSuccessful():
            sys.exit(0)
        sys.exit(-1)


config = ConfigParser.ConfigParser()
config.readfp(open('tryton.cfg'))
info = dict(config.items('tryton'))
for key in ('depends', 'extras_depend', 'xml'):
    if key in info:
        info[key] = info[key].strip().splitlines()
major_version, minor_version, _ = info.get('version', '0.0.1').split('.', 2)
major_version = int(major_version)
minor_version = int(minor_version)

MODULE2PREFIX = {
    'product_notebook': 'fio',
}

requires = []
for dep in info.get('depends', []):
    if not re.match(r'(ir|res|webdav)(\W|$)', dep):
        requires.append(
            '%s_%s >= %s.%s, < %s.%s' % (
                MODULE2PREFIX.get(dep, 'trytond'), dep,
                major_version, minor_version, major_version,
                minor_version + 1
            )
        )
requires.append(
    'trytond >= %s.%s, < %s.%s' %
    (major_version, minor_version, major_version, minor_version + 1)
)

setup(
    name='trytond_nereid_catalog',
    version=info.get('version'),
    description="Nereid Catalog",
    author="Fulfil.IO Inc.",
    author_email='support@fulfil.io',
    url='https://www.fulfil.io',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Plugins',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Framework :: Tryton',
        'Topic :: Office/Business',
    ],
    packages=[
        'trytond.modules.nereid_catalog',
        'trytond.modules.nereid_catalog.tests',
    ],
    package_dir={
        'trytond.modules.nereid_catalog': '.',
        'trytond.modules.nereid_catalog.tests': 'tests',
    },
    package_data={
        'trytond.modules.nereid_catalog':
            info.get('xml', [])
            + ['tryton.cfg', 'locale/*.po', 'tests/*.rst', 'view/*.xml']
            + ['i18n/*.pot', 'i18n/pt_BR/LC_MESSAGES/*'],
    },
    license='BSD',
    install_requires=requires,
    zip_safe=False,
    entry_points="""
    [trytond.modules]
    nereid_catalog = trytond.modules.nereid_catalog
    """,
    test_suite='tests.suite',
    test_loader='trytond.test_loader:Loader',
    cmdclass={
        'test': SQLiteTest,
    },
)
