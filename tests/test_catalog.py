# -*- coding: utf-8 -*-
import json
import unittest
from decimal import Decimal
from lxml import objectify
from nereid import render_template
import trytond.tests.test_tryton
from trytond.tests.test_tryton import (
    POOL, USER, DB_NAME, CONTEXT, ModuleTestCase
)
from nereid.testing import NereidTestCase
from trytond.transaction import Transaction
from trytond.config import config

config.set('database', 'path', '/tmp/')


class TestViewsDepends(ModuleTestCase):
    """
    Test Catalog
    """

    module = 'nereid_catalog'


class TestCatalog(NereidTestCase):
    """
    Test Catalog
    """

    def _create_product_category(self, name):
        """
        Creates a product category

        :param name: Name of the product category
        """
        Category = POOL.get('product.category')

        return Category.create([{'name': name}])

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
        self.category, = self._create_product_category('Category')
        self.category2, = self._create_product_category('Category 2')
        self.category3, = self._create_product_category('Category 3')

        # Create website
        en_us, = self.Language.search([('code', '=', 'en_US')])

        self.locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us.id,
            'currency': usd.id,
        }])
        self.NereidWebsite.create([{
            'name': 'localhost',
            'company': company.id,
            'application_user': USER,
            'default_locale': self.locale_en_us.id,
            'currencies': [('add', [usd.id])],
        }])

    def create_test_products(self):
        # Create product templates with products
        self._create_product_template(
            'product 1',
            [{
                'category': self.category,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
            }],
            uri='product-1',
        )
        self._create_product_template(
            'product 2',
            [{
                'category': self.category2,
                'type': 'goods',
                'list_price': Decimal('20'),
                'cost_price': Decimal('5'),
            }],
            uri='product-2',
        )
        self._create_product_template(
            'product 3',
            [{
                'category': self.category3,
                'type': 'goods',
                'list_price': Decimal('30'),
                'cost_price': Decimal('5'),
            }],
            uri='product-3',
        )
        self._create_product_template(
            'product 4',
            [{
                'category': self.category,
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
        self.Language = POOL.get('ir.lang')
        self.NereidWebsite = POOL.get('nereid.website')
        self.Party = POOL.get('party.party')
        self.Locale = POOL.get('nereid.website.locale')
        self.Category = POOL.get('product.category')

        self.templates = {
            'home.jinja':
                '''
                {{request.nereid_website.get_currencies()}}
                {% for image in product.images %}
                {{ image.name }}
                {% endfor %}
                ''',
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
        }

    def get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

    def test_0010_get_price(self):
        """
        The price returned must be the list price of the product, no matter
        the quantity
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
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
            self.create_test_products()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/products')
                self.assertEqual(rv.data, '|product 1||product 2||product 3|')

    def test_0030_quick_search(self):
        """
        Check if quick search works
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/search?q=product')
                self.assertEqual(rv.data, '|product 1||product 2||product 3|')

    def test_0040_product_sitemap_index(self):
        """
        Assert that the sitemap index returns 1 result
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
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
                self.assertEqual(len(xml.getchildren()), 3)

    def test_0060_get_recent_products(self):
        """
        Get the recent products list
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
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

    def test_0070_displayed_on_eshop(self):
        """Ensure only displayed_on_eshop products are displayed on the site
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/product/product-4')
                self.assertEqual(rv.status_code, 404)

    def test_0080_render_product_by_category(self):
        """Render product using user friendly paths.
        """
        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()
            app = self.get_app()

            with app.test_client() as c:
                rv = c.get('/product/category/sub-category/product-1')
                self.assertEqual(rv.status_code, 200)

    def test_0090_products_displayed_on_eshop(self):
        """
        Test for the products_displayed_on_eshop function fields
        """
        ProductTemplate = POOL.get('product.template')
        Uom = POOL.get('product.uom')

        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()

            unit, = Uom.search([('name', '=', u'Unit')])

            # Create templates with 2 displayed on eshop and 1 not
            template1, = ProductTemplate.create([{
                'name': 'Product Template 1',
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': unit,
                'products': [(
                    'create', [
                        {
                            'uri': 'product-1-variant-1',
                            'displayed_on_eshop': True,
                        }, {
                            'uri': 'product-1-variant-2',
                            'displayed_on_eshop': True,
                        }, {
                            'uri': 'product-1-variant-3',
                            'displayed_on_eshop': False,
                        },
                    ]
                )]
            }])

            self.assertEqual(len(template1.products_displayed_on_eshop), 2)
            self.assertEqual(len(template1.products), 3)

    def test_0100_product_images(self):
        """
        Test for adding product images
        """
        Product = POOL.get('product.product')
        StaticFolder = POOL.get("nereid.static.folder")
        StaticFile = POOL.get("nereid.static.file")
        Media = POOL.get('product.media')

        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()
            self.create_test_products()

            folder, = StaticFolder.create([{
                'name': 'Test'
            }])
            file_buffer = buffer('test-content')
            file, = StaticFile.create([{
                'name': 'test.png',
                'folder': folder.id,
                'file_binary': file_buffer
            }])

            product, = Product.search([], limit=1)

            Media.create([{
                'product': product.id,
                'template': product.template.id,
                'static_file': file.id,
            }])

            app = self.get_app()
            with app.test_request_context('/'):
                home_template = render_template('home.jinja', product=product)
                self.assertTrue(file.name in home_template)


def suite():
    "Catalog test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestViewsDepends),
        unittest.TestLoader().loadTestsFromTestCase(TestCatalog),
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
