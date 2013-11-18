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

    def _create_product_category(self, name, vlist):
        """
        Creates a product category

        Name is mandatory while other value may be provided as keyword
        arguments

        :param name: Name of the product category
        :param vlist: List of dictionaries of values to create
        """
        Category = POOL.get('product.category')

        for values in vlist:
            values['name'] = name
        return Category.create(vlist)

    def _create_product_template(
        self, name, vlist, uri, uom=u'Unit', displayed_on_eshop=True
    ):
        """
        Create a product template with products and return its ID

        :param name: Name of the product
        :param vlist: List of dictionaries of values to create
        :param uri: uri of product template
        :param uom: Note it is the name of UOM (not symbol or code)
        :param displayed_on_eshop: Boolean field to display product
                                   on shop or not
        """
        ProductTemplate = POOL.get('product.template')
        Uom = POOL.get('product.uom')

        for values in vlist:
            values['name'] = name
            values['default_uom'], = Uom.search([('name', '=', uom)], limit=1)
            values['products'] = [
                ('create', [{
                    'uri': uri,
                    'displayed_on_eshop': displayed_on_eshop,
                }])
            ]

        return ProductTemplate.create(vlist)

    def setup_defaults(self):
        """
        Setup the defaults
        """
        usd, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])
        party1, = self.Party.create([{
            'name': 'Openlabs',
        }])
        company, = self.Company.create([{
            'party': party1.id,
            'currency': usd.id
        }])
        party2, = self.Party.create([{
            'name': 'Guest User',
        }])
        guest_user, = self.NereidUser.create([{
            'party': party2.id,
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'password': 'password',
            'company': company.id,
        }])
        party3, = self.Party.create([{
            'name': 'Registered User',
        }])
        self.registered_user, = self.NereidUser.create([{
            'party': party3.id,
            'display_name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': company.id,
        }])

        # Create product categories
        category, = self._create_product_category(
            'Category', [{'uri': 'category'}]
        )
        category2, = self._create_product_category(
            'Category 2', [{'uri': 'category2'}]
        )
        category3, = self._create_product_category(
            'Category 3', [{'uri': 'category3'}]
        )

        # Create website
        url_map, = self.UrlMap.search([], limit=1)
        en_us, = self.Language.search([('code', '=', 'en_US')])

        self.locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us.id,
            'currency': usd.id,
        }])
        self.NereidWebsite.create([{
            'name': 'localhost',
            'url_map': url_map.id,
            'company': company.id,
            'application_user': USER,
            'default_locale': self.locale_en_us.id,
            'guest_user': guest_user,
            'categories': [('set', [category.id, category2.id])],
            'currencies': [('set', [usd.id])],
        }])

        # Create product templates with products
        self._create_product_template(
            'product 1',
            [{
                'category': category,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
            }],
            uri='product-1',
        )
        self._create_product_template(
            'product 2',
            [{
                'category': category2,
                'type': 'goods',
                'list_price': Decimal('20'),
                'cost_price': Decimal('5'),
            }],
            uri='product-2',
        )
        self._create_product_template(
            'product 3',
            [{
                'category': category3,
                'type': 'goods',
                'list_price': Decimal('30'),
                'cost_price': Decimal('5'),
            }],
            uri='product-3',
        )
        self._create_product_template(
            'product 4',
            [{
                'category': category,
                'type': 'goods',
                'list_price': Decimal('30'),
                'cost_price': Decimal('5'),
            }],
            uri='product-4',
            displayed_on_eshop=False
        )

    def setUp(self):
        """
        Set up data used in the tests.
        this method is called before each test execution.
        """
        trytond.tests.test_tryton.install_module('nereid_catalog')

        self.Currency = POOL.get('currency.currency')
        self.Site = POOL.get('nereid.website')
        self.Product = POOL.get('product.product')
        self.Company = POOL.get('company.company')
        self.NereidUser = POOL.get('nereid.user')
        self.UrlMap = POOL.get('nereid.url_map')
        self.Language = POOL.get('ir.lang')
        self.NereidWebsite = POOL.get('nereid.website')
        self.Party = POOL.get('party.party')
        self.Locale = POOL.get('nereid.website.locale')

        self.templates = {
            'home.jinja':
                '{{request.nereid_website.get_currencies()}}',
            'login.jinja':
                '{{ login_form.errors }} {{get_flashed_messages()}}',
            'product-list.jinja':
                '{% for product in products %}'
                '|{{ product.name }}|{% endfor %}',
            'category.jinja':
                '{% for product in products %}'
                '|{{ product.name }}|{% endfor %}',
            'category-list.jinja':
                '{%- for category in categories %}'
                '|{{ category.name }}|'
                '{%- endfor %}',
            'search-results.jinja':
                '{% for product in products %}'
                '|{{ product.name }}|{% endfor %}',
            'product.jinja': '{{ product.sale_price(product.id) }}',
            'wishlist.jinja':
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
                rv = c.get('/product/product-1')
                self.assertEqual(rv.data, '10')

    def test_0020_list_view(self):
        """
        Call the render list method to get list of all products
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/products')
                self.assertEqual(rv.data, '|product 1||product 2|')

    def test_0030_category(self):
        """
        Check the category pages
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/category/category')
                self.assertEqual(rv.data, '|product 1|')

                rv = c.get('/category/category2')
                self.assertEqual(rv.data, '|product 2|')

                rv = c.get('/category/category3')
                self.assertEqual(rv.status_code, 404)

    def test_0035_category_list(self):
        """
        Test the category list pages
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/catalog')
                self.assertEqual(rv.data, '|Category||Category 2|')

    def test_0040_quick_search(self):
        """
        Check if quick search works
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/search?q=product')
                self.assertEqual(rv.data, '|product 1||product 2|')

    def test_0050_product_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/sitemaps/product-index.xml')
                xml = objectify.fromstring(rv.data)
                self.assertTrue(xml.tag.endswith('sitemapindex'))
                self.assertEqual(len(xml.getchildren()), 1)

                self.assertEqual(
                    xml.sitemap.loc.pyval.split('localhost', 1)[-1],
                    '/sitemaps/product-1.xml'
                )

                rv = c.get('/sitemaps/product-1.xml')
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
                rv = c.get('/sitemaps/category-index.xml')
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
                rv = c.get('/products/+recent')
                self.assertEqual(json.loads(rv.data)['products'], [])

                rv = c.get('/product/product-1')
                rv = c.get('/products/+recent')
                self.assertEqual(len(json.loads(rv.data)['products']), 1)

                rv = c.post('/products/+recent', data={'product_id': 2})
                self.assertEqual(len(json.loads(rv.data)['products']), 2)
                rv = c.get('/products/+recent')
                self.assertEqual(len(json.loads(rv.data)['products']), 2)

    def test_0080_displayed_on_eshop(self):
        """Ensure only displayed_on_eshop products are displayed on the site
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/product/product-4')
                self.assertEqual(rv.status_code, 404)

    def test_0090_add_to_wishlist(self):
        '''Test adding products to wishlist
        '''
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            app = self.get_app()

            with app.test_client() as c:
                c.post('/login', data={
                    'email': 'email@example.com',
                    'password': 'password',
                })
                c.post(
                    '/products/add-to-wishlist',
                    data={'product': 1}
                )
                rv = c.get('/products/view-wishlist')
                self.assertEqual(rv.data, '|product-1|')

                c.post(
                    '/products/add-to-wishlist',
                    data={'product': 2}
                )
                rv = c.get('/products/view-wishlist')
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
