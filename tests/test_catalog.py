# -*- coding: utf-8 -*-
'''
    Catalog test suite

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
import json
import unittest
from decimal import Decimal

from lxml import objectify

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT, \
    test_view, test_depends
from nereid.testing import NereidTestCase
from trytond.transaction import Transaction


class TestCatalog(NereidTestCase):
    """
    Test Catalog
    """

    def _create_product_category(self, name, **values):
        """
        Creates a product category

        Name is mandatory while other value may be provided as keyword
        arguments

        :param name: Name of the product category
        """
        category_obj = POOL.get('product.category')

        values['name'] = name
        return category_obj.create(values)

    def _create_product(self, name, uom=u'Unit', **values):
        """
        Create a product and return its ID

        Additional arguments may be provided as keyword arguments

        :param name: Name of the product
        :param uom: Note it is the name of UOM (not symbol or code)
        """
        product_obj = POOL.get('product.product')
        uom_obj = POOL.get('product.uom')

        values['name'] = name
        values['default_uom'], = uom_obj.search([('name', '=', uom)], limit=1)

        return product_obj.create(values)

    def setup_defaults(self):
        """
        Setup the defaults
        """
        usd = self.currency_obj.create({
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        })
        company_id = self.company_obj.create({
            'name': 'Openlabs',
            'currency': usd
        })
        guest_user = self.nereid_user_obj.create({
            'name': 'Guest User',
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'password': 'password',
            'company': company_id,
        })
        self.registered_user_id = self.nereid_user_obj.create({
            'name': 'Registered User',
            'display_name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': company_id,
        })

        # Create product categories
        category = self._create_product_category(
            'Category', uri='category'
        )
        category2 = self._create_product_category(
            'Category 2', uri='category2'
        )
        category3 = self._create_product_category(
            'Category 3', uri='category3'
        )

        # Create website
        url_map_id, = self.url_map_obj.search([], limit=1)
        en_us, = self.language_obj.search([('code', '=', 'en_US')])
        self.nereid_website_obj.create({
            'name': 'localhost',
            'url_map': url_map_id,
            'company': company_id,
            'application_user': USER,
            'default_language': en_us,
            'guest_user': guest_user,
            'categories': [('set', [category, category2])],
            'currencies': [('set', [usd])],
        })

        # Create Sample products
        self._create_product(
            'product 1',
            category=category,
            type='goods',
            list_price=Decimal('10'),
            cost_price=Decimal('5'),
            uri='product-1',
        )
        self._create_product(
            'product 2',
            category=category2,
            type='goods',
            list_price=Decimal('20'),
            cost_price=Decimal('5'),
            uri='product-2',
        )
        self._create_product(
            'product 3',
            category=category3,
            type='goods',
            list_price=Decimal('30'),
            cost_price=Decimal('5'),
            uri='product-3',
        )
        self._create_product(
            'product 4',
            category=category,
            displayed_on_eshop=False,
            type='goods',
            list_price=Decimal('30'),
            cost_price=Decimal('5'),
            uri='product-4',
        )

    def setUp(self):
        trytond.tests.test_tryton.install_module('nereid_catalog')
        self.currency_obj = POOL.get('currency.currency')
        self.site_obj = POOL.get('nereid.website')
        self.product_obj = POOL.get('product.product')
        self.company_obj = POOL.get('company.company')
        self.nereid_user_obj = POOL.get('nereid.user')
        self.url_map_obj = POOL.get('nereid.url_map')
        self.language_obj = POOL.get('ir.lang')
        self.nereid_website_obj = POOL.get('nereid.website')

        self.templates = {
            'localhost/home.jinja':
                '{{request.nereid_website.get_currencies()}}',
            'localhost/login.jinja':
                '{{ login_form.errors }} {{get_flashed_messages()}}',
            'localhost/product-list.jinja':
                '{% for product in products %}|{{ product.name }}|{% endfor %}',
            'localhost/category.jinja':
                '{% for product in products %}|{{ product.name }}|{% endfor %}',
            'localhost/category-list.jinja':
                '{%- for category in categories %}'
                '|{{ category.name }}|'
                '{%- endfor %}',
            'localhost/search-results.jinja':
                '{% for product in products %}|{{ product.name }}|{% endfor %}',
            'localhost/product.jinja': '{{ product.sale_price(product.id) }}',
            'localhost/wishlist.jinja':
                '{% for product in products %}|{{ product.uri }}|{% endfor %}',
        }

    def get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

    def test_0005_test_view(self):
        """
        Test the views
        """
        test_view('nereid_catalog')

    def test_0007_test_depends(self):
        '''
        Test Depends
        '''
        test_depends()

    def test_0010_get_price(self):
        """
        The price returned must be the list price of the product, no matter
        the quantity
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/product/product-1')
                self.assertEqual(rv.data, '10')

    def test_0020_list_view(self):
        """
        Call the render list method to get list of all products
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/products')
                self.assertEqual(rv.data, '|product 1||product 2|')

    def test_0030_category(self):
        """
        Check the category pages
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
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
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/catalog')
                self.assertEqual(rv.data, '|Category||Category 2|')

    def test_0040_quick_search(self):
        """
        Check if quick search works
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/search?q=product')
                self.assertEqual(rv.data, '|product 1||product 2|')

    def test_0050_product_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/sitemaps/product-index.xml')
                xml = objectify.fromstring(rv.data)
                self.assertTrue(xml.tag.endswith('sitemapindex'))
                self.assertEqual(len(xml.getchildren()), 1)

                self.assertEqual(
                    xml.sitemap.loc.pyval.split('localhost', 1)[-1],
                    '/en_US/sitemaps/product-1.xml'
                )

                rv = c.get('/en_US/sitemaps/product-1.xml')
                xml = objectify.fromstring(rv.data)
                self.assertTrue(xml.tag.endswith('urlset'))
                self.assertEqual(len(xml.getchildren()), 2)

    def test_0060_category_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
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
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
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
        """Ensure only displayed_on_eshop products are displayed on the site
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/en_US/product/product-4')
                self.assertEqual(rv.status_code, 404)

    def test_0090_add_to_wishlist(self):
        '''Test adding products to wishlist
        '''
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
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
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
