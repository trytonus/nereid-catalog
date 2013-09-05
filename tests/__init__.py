# -*- coding: utf-8 -*-
'''
    Nereid catalog Test Suite

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
'''
# flake8: noqa
import unittest
import trytond.tests.test_tryton

from .test_catalog import TestCatalog
from .test_product import TestProduct


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests([
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog),
        unittest.TestLoader().loadTestsFromTestCase(TestProduct),
    ])

    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
