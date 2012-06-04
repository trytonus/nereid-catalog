# -*- coding: utf-8 -*-
'''
    Catalog test suite
    
    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details
    
'''
from decimal import Decimal
import json

import unittest2 as unittest
from lxml import objectify

from trytond.config import CONFIG
CONFIG.options['db_type'] = 'sqlite'
from trytond.modules import register_classes
register_classes()
from nereid.testing import testing_proxy, TestCase
from trytond.transaction import Transaction


class TestCatalog(TestCase):
    """Test Catalog"""

    @classmethod
    def setUpClass(cls):
        super(TestCatalog, cls).setUpClass()
        testing_proxy.install_module('nereid_catalog')
 
        with Transaction().start(testing_proxy.db_name, 1, None) as txn:
            company = testing_proxy.create_company('Test Company')
            cls.guest_user = testing_proxy.create_guest_user(company=company)
            cls.regd_user = testing_proxy.create_user_party('Registered User', 
                'email@example.com', 'password', company=company)

            testing_proxy.create_template(
                'category.jinja', 
                '{% for product in products %}|{{ product.name }}|{% endfor %}'
            )
            testing_proxy.create_template(
                'category-list.jinja',
                '{%- for category in categories %}'
                '|{{ category.name }}|'
                '{%- endfor %}'
            )
            testing_proxy.create_template(
                'search-results.jinja', 
                '{% for product in products %}|{{ product.name }}|{% endfor %}'
            )
            testing_proxy.create_template(
                'login.jinja', 
                '{{ login_form.errors }} {{get_flashed_messages()}}'
            )
            testing_proxy.create_template(
                'product-list.jinja',
                '{% for product in products %}|{{ product.name }}|{% endfor %}'
            )
            testing_proxy.create_template(
                'product.jinja', '{{ product.sale_price(product.id) }}'
            )
            wishlist_template = testing_proxy.create_template(
                'wishlist.jinja',
                '{% for product in products %}|{{ product.uri }}|{% endfor %}'
            )
            category = testing_proxy.create_product_category(
                'Category', uri='category'
            )
            category2 = testing_proxy.create_product_category(
                'Category 2', uri='category2'
            )
            category3 = testing_proxy.create_product_category(
                'Category 3', uri='category3'
            )

            currency_obj = testing_proxy.pool.get('currency.currency')
            usd, = currency_obj.search([('code', '=', 'USD')], limit=1)
            cls.site = testing_proxy.create_site(
                'localhost', 
                categories=[('set', [category, category2])],
                guest_user=cls.guest_user,
                application_user=1,
                currencies=[('set', [usd])]
            )

            testing_proxy.create_template(
                'home.jinja', 
                '{{request.nereid_website.get_currencies()}}',
                cls.site
            )
            cls.product = testing_proxy.create_product(
                'product 1', category,
                type = 'goods',
                list_price = Decimal('10'),
                cost_price = Decimal('5'),
                uri = 'product-1',
            )
            cls.product = testing_proxy.create_product(
                'product 2', category2,
                type = 'goods',
                list_price = Decimal('20'),
                cost_price = Decimal('5'),
                uri = 'product-2',
            )
            cls.product = testing_proxy.create_product(
                'product 3', category3,
                type = 'goods',
                list_price = Decimal('30'),
                cost_price = Decimal('5'),
                uri = 'product-3',
            )
            cls.product = testing_proxy.create_product(
                'product 4', category,
                displayed_on_eshop = False,
                type = 'goods',
                list_price = Decimal('30'),
                cost_price = Decimal('5'),
                uri = 'product-4',
            )
            txn.cursor.commit()

    def get_app(self, **options):
        app = testing_proxy.make_app(SITE='localhost', **options)
        return app

    def setUp(self):
        self.currency_obj = testing_proxy.pool.get('currency.currency')
        self.site_obj = testing_proxy.pool.get('nereid.website')
        self.product_obj = testing_proxy.pool.get('product.product')

    def test_0005_test_view(self):
        """
        Test the views
        """
        from trytond.tests import test_tryton
        test_tryton.POOL = testing_proxy.pool
        test_tryton.DB_NAME = testing_proxy.db_name
        test_tryton.test_view('nereid_catalog')

    def test_0007_test_depends(self):
        '''
        Test Depends
        '''
        from trytond.tests.test_tryton import test_depends
        test_depends()

    def test_0010_get_price(self):
        """
        The price returned must be the list price of the product, no matter
        the quantity
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/product/product-1')
            self.assertEqual(rv.data, '10')

    def test_0020_list_view(self):
        """
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/products')
            self.assertEqual(rv.data, '|product 1||product 2|')


    def test_0030_category(self):
        """
        Check the category pages
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/category/category')
            self.assertEqual(rv.data, '|product 1|')

            rv = c.get('/en_US/category/category2')
            self.assertEqual(rv.data, '|product 2|')

            rv = c.get('/en_US/category/category3')
            self.assertEqual(rv.status_code, 404)

    def test_0035_category_list(self):
        """
        Test the category list pages
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/catalog')
            self.assertEqual(rv.data, '|Category||Category 2|')

    def test_0040_quick_search(self):
        """
        Check if quick search works
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/search?q=product')
            self.assertEqual(rv.data, '|product 1||product 2|')

    def test_0050_product_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/sitemaps/product-index.xml')
            xml = objectify.fromstring(rv.data)
            self.assertTrue(xml.tag.endswith('sitemapindex'))
            self.assertEqual(len(xml.getchildren()), 1)

            rv = c.get(
                xml.sitemap.loc.pyval.split('localhost/', 1)[-1]
            )
            xml = objectify.fromstring(rv.data)
            self.assertTrue(xml.tag.endswith('urlset'))
            self.assertEqual(len(xml.getchildren()), 2)

    def test_0060_category_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/sitemaps/category-index.xml')
            xml = objectify.fromstring(rv.data)
            self.assertTrue(xml.tag.endswith('sitemapindex'))
            self.assertEqual(len(xml.getchildren()), 1)

            rv = c.get(
                xml.sitemap.loc.pyval.split('localhost/', 1)[-1]
            )
            xml = objectify.fromstring(rv.data)
            self.assertTrue(xml.tag.endswith('urlset'))
            self.assertEqual(len(xml.getchildren()), 2)

    def test_0070_get_recent_products(self):
        """
        Get the recent products list
        """
        app = self.get_app(
            CACHE_TYPE='werkzeug.contrib.cache.SimpleCache'
        )
        with app.test_client() as c:
            rv = c.get('/en_US/products/+recent')
            self.assertEqual(json.loads(rv.data)['products'], [])

            rv = c.get('/en_US/product/product-1')
            rv = c.get('/en_US/products/+recent')
            self.assertEqual(len(json.loads(rv.data)['products']), 1)

            rv = c.post('/en_US/products/+recent', data={'product_id': 2})
            self.assertEqual(len(json.loads(rv.data)['products']), 2)
            rv = c.get('/en_US/products/+recent')
            self.assertEqual(len(json.loads(rv.data)['products']), 2)

    def test_0080_displayed_on_eshop(self):
        app = self.get_app()
        with app.test_client() as c:
            rv = c.get('/en_US/product/product-4')
            self.assertEqual(rv.status_code, 404)

    def test_0090_add_to_wishlist(self):
        '''Test adding products to wishlist
        '''
        app = self.get_app()
        with app.test_client() as c:
            c.post('/en_US/login', data={
                'email': 'email@example.com',
                'password': 'password',
            })
            c.get('/en_US/products/add-to-wishlist?product=1')
            rv = c.get('/en_US/products/view-wishlist')
            self.assertEqual(rv.data, '|product-1|')

            c.get('/en_US/products/add-to-wishlist?product=2')
            rv = c.get('/en_US/products/view-wishlist')
            self.assertEqual(rv.data, '|product-1||product-2|')


def suite():
    "Catalog test suite"
    suite = unittest.TestSuite()
    suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog)
        )
    return suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
