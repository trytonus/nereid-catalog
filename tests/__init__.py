# -*- coding: utf-8 -*-
'''
    Nereid catalog Test Suite
    
    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
    
'''
import unittest2 as unittest
from test_catalog import TestCatalog

def suite():
    "Catalog test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog)
        )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
