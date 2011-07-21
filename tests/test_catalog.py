#!/usr/bin/env python
#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from ast import literal_eval
import unittest2 as unittest

from trytond.config import CONFIG
CONFIG.options['db_type'] = 'sqlite'
from trytond.modules import register_classes
register_classes()

from nereid.testing import testing_proxy
from trytond.transaction import Transaction


class TestPrice(unittest.TestCase):
    """Test Price"""

    @classmethod
    def setUpClass(cls):
        testing_proxy.install_module('nereid_catalog')
        with Transaction().start(testing_proxy.db_name, 1, None) as txn:
            company = testing_proxy.create_company('Test Company')
            cls.guest_user = testing_proxy.create_guest_user()

            category_template = testing_proxy.create_template(
                'category-list.jinja', ' ')
            product_template = testing_proxy.create_template(
                'product-list.jinja', ' ')
            cls.site = testing_proxy.create_site('testsite.com', 
                category_template=category_template,
                product_template=product_template)

            testing_proxy.create_template(
                'home.jinja', 
                '{{request.nereid_website.get_currencies()}}',
                cls.site)
            txn.cursor.commit()

    def get_app(self):
        return testing_proxy.make_app(
            SITE='testsite.com', 
            GUEST_USER=self.guest_user)

    def setUp(self):
        self.currency_obj = testing_proxy.pool.get('currency.currency')
        self.site_obj = testing_proxy.pool.get('nereid.website')

    def test_0010_get_price(self):
        """Try getting the price without a pricelist
        It must return the list_price
        Expected: Empty list
        """
        pass

    def test_0020_get_price_guest(self):
        """Get the price for guest user with a pricelist
        defined
        """
        pass

    def test_0030_get_price_regd(self):
        """Get price for regsitered user without setting a pricelist
        for the regsitered user. The price should be that of the guest
        """
        pass

    def test_0040_get_price_regd2(self):
        """Get price for regsitered user with a new pricelist different
        from that of the guest user set against the registered user
        """
        pass

    def test_0050_get_quick_search(self):
        """Test the search feature by ensuring the right products are displayed
        """
        pass

def suite():
    "Catalog test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestPrice)
        )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
