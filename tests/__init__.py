# -*- coding: utf-8 -*-
import unittest
import trytond.tests.test_tryton

from .test_catalog import TestViewsDepends, TestCatalog
from .test_product import TestProduct


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests([
        unittest.TestLoader().loadTestsFromTestCase(TestViewsDepends),
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog),
        unittest.TestLoader().loadTestsFromTestCase(TestProduct),
    ])

    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
