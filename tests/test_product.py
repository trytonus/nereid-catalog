# -*- coding: utf-8 -*-
import unittest
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, with_transaction
from nereid.testing import NereidTestCase
from trytond.exceptions import UserError


class TestProduct(NereidTestCase):
    """
    Test Product
    """

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
            'name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'password': 'password',
            'company': company.id,
        }])
        party3, = self.Party.create([{
            'name': 'Registered User',
        }])
        self.registered_user, = self.NereidUser.create([{
            'party': party3.id,
            'name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': company.id,
        }])

        self.category, = self.Category.create([{
            'name': 'CategoryA',
        }])

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
        self.Category = POOL.get('product.category')
        self.Template = POOL.get('product.template')
        self.Uom = POOL.get('product.uom')
        self.Locale = POOL.get('nereid.website.locale')

        self.templates = {
            'home.jinja':
                '{{current_website.get_currencies()}}',
            'login.jinja':
                '{{ login_form.errors }} {{get_flashed_messages()}}',
            'product-list.jinja': '{{ products|length}}',
            'product.jinja': '{{ product.template.name}}',
        }

    def get_template_source(self, name):
        """
        Return templates
        """
        return self.templates.get(name)

    @with_transaction()
    def test0010search_domain_conversion(self):
        '''
        Test the search domain conversion
        '''

        self.setup_defaults()
        uom, = self.Uom.search([], limit=1)
        values1 = {
            'name': 'Product-1',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'products': [
                ('create', [{
                    'uri': 'product-1',
                    'displayed_on_eshop': True
                }])
            ]

        }
        values2 = {
            'name': 'Product-2',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'products': [
                ('create', [{
                    'uri': 'product-2',
                    'displayed_on_eshop': True
                }])
            ]
        }
        template1, template2 = self.Template.create([values1, values2])
        app = self.get_app()

        with app.test_client() as c:
            # Render all products
            rv = c.get('/products')
            self.assertEqual(rv.data, '2')

            # Render product with uri
            rv = c.get('/product/product-1')
            self.assertEqual(rv.data, 'Product-1')

            rv = c.get('/product/product-2')
            self.assertEqual(rv.data, 'Product-2')

    @with_transaction()
    def test0020_inactive_template(self):
        '''
        Assert that the variants of inactive products are not displayed
        '''

        self.setup_defaults()
        uom, = self.Uom.search([], limit=1)
        values1 = {
            'name': 'Product-1',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'products': [
                ('create', [{
                    'uri': 'product-1',
                    'displayed_on_eshop': True
                }])
            ]

        }
        values2 = {
            'name': 'Product-2',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'products': [
                ('create', [{
                    'uri': 'product-2',
                    'displayed_on_eshop': True
                }])
            ]
        }
        template1, template2 = self.Template.create([values1, values2])
        app = self.get_app()

        with app.test_client() as c:
            # Render all products
            rv = c.get('/products')
            self.assertEqual(rv.data, '2')

            template1.active = False
            template1.save()

            rv = c.get('/products')
            self.assertEqual(rv.data, '1')

            # Render product with uri
            rv = c.get('/product/product-1')
            self.assertEqual(rv.status_code, 404)

            rv = c.get('/product/product-2')
            self.assertEqual(rv.data, 'Product-2')

    @with_transaction()
    def test0030_get_variant_description(self):
        """
        Test to get variant description.
        If use_template_description is false, show description
        of variant else show description of product template
        """
        self.setup_defaults()
        uom, = self.Uom.search([], limit=1)

        # creating product template
        product_template, = self.Template.create([{
            'name': 'test template',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'description': 'Description of template',
            'products': [('create', self.Template.default_products())],
        }])

        # setting use_template_description to false
        # and adding variant description
        product_variant, = product_template.products
        self.Product.write([product_variant], {
            'use_template_description': False,
            'description': 'Description of product',
        })

        self.assertEqual(
            product_variant.get_description(),
            'Description of product'
        )
        # setting use_template_description to true
        # description of variant should come from product template
        self.Product.write([product_variant], {
            'use_template_description': True,
        })

        self.assertEqual(
            product_variant.get_description(),
            'Description of template'
        )

    @with_transaction()
    def test0030_get_variant_images(self):
        """
        Test to get variant images.
        """
        Product = POOL.get('product.product')
        StaticFolder = POOL.get("nereid.static.folder")
        StaticFile = POOL.get("nereid.static.file")

        self.setup_defaults()

        folder, = StaticFolder.create([{
            'name': 'Test'
        }])
        file_buffer = buffer('test-content')
        file = StaticFile.create([{
            'name': 'test.png',
            'folder': folder.id,
            'file_binary': file_buffer
        }])[0]

        file1 = StaticFile.create([{
            'name': 'test1.png',
            'folder': folder.id,
            'file_binary': file_buffer
        }])[0]

        uom, = self.Uom.search([], limit=1)

        # creating product template
        product_template, = self.Template.create([{
            'name': 'test template',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'description': 'Description of template',
            'media': [('create', [{
                'static_file': file.id,
            }])],
            'products': [('create', self.Template.default_products())]
        }])

        product, = product_template.products

        # There are no images for product so, it should return images
        # from template
        self.assertEqual(product.get_images()[0].id, file.id)

        Product.write([product], {
            'media': [('create', [{
                'static_file': file1.id,
            }])]
        })
        # As the product now has images, this image should be returned
        self.assertEqual(product.get_images()[0].id, file1.id)

    @with_transaction()
    def test0040_test_uri_uniqueness(self):
        """
        Test that URIs are unique for Products
        """
        self.setup_defaults()

        uom, = self.Uom.search([], limit=1)

        # Creating Product Template
        product_template, = self.Template.create([{
            'name': 'Test Template',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'description': 'Template Description',
        }])

        product1 = self.Product.create([{
            'template': product_template.id,
            'displayed_on_eshop': True,
            'uri': 'test-product',
        }])
        self.assert_(product1)

        # Create new variants with the same URI
        # Assert if UserError is raised
        with self.assertRaises(UserError):
            product2 = self.Product.create([{  # noqa
                'template': product_template.id,
                'displayed_on_eshop': True,
                'uri': 'Test-Product',
            }])
        with self.assertRaises(UserError):
            product3 = self.Product.create([{  # noqa
                'template': product_template.id,
                'displayed_on_eshop': True,
                'uri': 'tesT-proDuct',
            }])
        # Check if we are not checking URI uniqueness if
        # product is marked as not displayed on eshop
        product4 = self.Product.create([{
            'template': product_template.id,
            'uri': 'Test-Product',
        }])
        self.assert_(product4)

        # Creating Product Template
        product_template_1, = self.Template.create([{
            'name': 'Test Template',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'description': 'Template Description',
        }])
        self.assert_(product_template_1)

        with self.assertRaises(UserError):
            self.Template.write([product_template_1], {
                'products': [('create', [{
                    'uri': 'product-1',
                    'displayed_on_eshop': True
                }, {
                    'uri': 'Product-1',
                    'displayed_on_eshop': True
                }])]
            })

    @with_transaction()
    def test0050_test_rec_name_sorting(self):
        """
        Test if rec_name field is sorted
        """
        ProductCategory = POOL.get('product.category')

        self.setup_defaults()

        product_category2, = ProductCategory.create([{
            'name': 'Personel',
        }])

        product_category1, = ProductCategory.create([{
            'name': 'Automobile',
        }])

        product_category3, = ProductCategory.create([{
            'name': 'Household',
        }])

        product_category4, = ProductCategory.create([{
            'name': 'Cars',
            'parent': product_category1.id
        }])

        product_category5, = ProductCategory.create([{
            'name': 'Watches',
        }])

        # With sorting
        categories = ProductCategory.search([], order=[('rec_name', 'ASC')])

        # Category first element is Automobile/car (child)
        self.assertEqual(categories[0], product_category4)

        # Category last element is Watches  (last created)
        self.assertEqual(categories[-1], product_category5)

        # Category Second element is Automobile (parent)
        self.assertEqual(categories[1], product_category1)

        # Own order
        categories = ProductCategory.search([])

        # Category first element is Automobile/car (child)
        self.assertEqual(categories[0], product_category1)

        # Category last element is Watches  (last created)
        self.assertEqual(categories[-1], product_category5)

        # Category Second element is Automobile (parent)
        self.assertEqual(categories[1], product_category4)

    @with_transaction()
    def test0060_copy_product(self):
        '''
        Test product copy
        '''

        self.setup_defaults()
        uom, = self.Uom.search([], limit=1)
        self.Template.create([{
            'name': 'Product-1',
            'categories': [('add', [self.category.id])],
            'type': 'goods',
            'list_price': Decimal('10'),
            'cost_price': Decimal('5'),
            'default_uom': uom.id,
            'products': [
                ('create', [{
                    'uri': 'product1',
                    'displayed_on_eshop': True
                }])
            ]
        }])

        product1, = self.Product.search([])

        product2, = self.Product.copy([product1])

        self.assertEqual(product2.uri, '%s-copy-1' % product1.uri)


def suite():
    "Test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestProduct)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
