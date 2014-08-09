# -*- coding: utf-8 -*-
"""
    test_product

    Test Product

    :copyright: (c) 2013-2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import unittest
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from nereid.testing import NereidTestCase
from trytond.transaction import Transaction


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

        self.category, = self.Category.create([{
            'name': 'CategoryA',
            'uri': 'category-1'
        }])

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
            'categories': [('add', [self.category.id])],
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
        self.UrlMap = POOL.get('nereid.url_map')
        self.Language = POOL.get('ir.lang')
        self.NereidWebsite = POOL.get('nereid.website')
        self.Party = POOL.get('party.party')
        self.Category = POOL.get('product.category')
        self.Template = POOL.get('product.template')
        self.Uom = POOL.get('product.uom')
        self.Locale = POOL.get('nereid.website.locale')

        self.templates = {
            'home.jinja':
                '{{request.nereid_website.get_currencies()}}',
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

    def test0010search_domain_conversion(self):
        '''
        Test the search domain conversion
        '''

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            values1 = {
                'name': 'Product-1',
                'category': self.category.id,
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
                'category': self.category.id,
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

    def test0020_inactive_template(self):
        '''
        Assert that the variants of inactive products are not displayed
        '''

        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)
            values1 = {
                'name': 'Product-1',
                'category': self.category.id,
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
                'category': self.category.id,
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

    def test0030_get_variant_description(self):
        """
        Test to get variant description.
        If use_template_description is false, show description
        of variant else show description of product template
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.setup_defaults()
            uom, = self.Uom.search([], limit=1)

            # creating product template
            product_template, = self.Template.create([{
                'name': 'test template',
                'category': self.category.id,
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

    def test0030_get_variant_images(self):
        """
        Test to get variant images.

        If boolean field use_template_images is true return images
        of product template else return images of variant
        """
        ProductImageSet = POOL.get('product.product.imageset')
        Product = POOL.get('product.product')
        StaticFolder = POOL.get("nereid.static.folder")
        StaticFile = POOL.get("nereid.static.file")

        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()

            folder, = StaticFolder.create([{
                'folder_name': 'Test'
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
                'category': self.category.id,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'description': 'Description of template',
                'products': [('create', self.Template.default_products())]
            }])

            image1, = ProductImageSet.create([{
                'name': 'template_image',
                'template': product_template,
                'image': file
            }])

            product, = product_template.products

            image2, = ProductImageSet.create([{
                'name': 'product_image',
                'product': product,
                'image': file1
            }])
            self.assertEqual(product.get_images()[0].id, image1.id)
            Product.write([product], {
                'use_template_images': False,
            })
            self.assertEqual(product.get_images()[0].id, image2.id)

    def test0040_get_default_image(self):
        """
        Test to get default image.

        If boolean field use_template_images is checked return
        template's first image else return variant's first image.

        If image does not exist in template and variant return None

        """
        ProductImageSet = POOL.get('product.product.imageset')
        Product = POOL.get('product.product')
        StaticFolder = POOL.get("nereid.static.folder")
        StaticFile = POOL.get("nereid.static.file")

        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()

            folder, = StaticFolder.create([{
                'folder_name': 'Test'
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
                'category': self.category.id,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'description': 'Description of template',
                'products': [('create', self.Template.default_products())]
            }])

            product, = product_template.products
            self.assertEqual(product.default_image, None)

            image1, = ProductImageSet.create([{
                'name': 'template_image',
                'template': product_template,
                'image': file
            }])

            image2, = ProductImageSet.create([{
                'name': 'product_image',
                'product': product,
                'image': file1
            }])

            self.assertEqual(product.default_image.id, image1.id)
            Product.write([product], {
                'use_template_images': False,
            })
            self.assertEqual(product.default_image.id, image2.id)

    def test0050_test_default_image_set(self):
        """
        Test to check default image set for product variants and
        templates.
        """
        ProductImageSet = POOL.get('product.product.imageset')
        Product = POOL.get('product.product')
        StaticFolder = POOL.get("nereid.static.folder")
        StaticFile = POOL.get("nereid.static.file")

        with Transaction().start(DB_NAME, USER, CONTEXT):
            self.setup_defaults()

            folder, = StaticFolder.create([{
                'folder_name': 'Test'
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

            # Creating Product Template
            product_template, = self.Template.create([{
                'name': 'Test Template',
                'category': self.category.id,
                'type': 'goods',
                'list_price': Decimal('10'),
                'cost_price': Decimal('5'),
                'default_uom': uom.id,
                'description': 'Template Description',
                'products': [('create', self.Template.default_products())]
            }])

            image_set1, = ProductImageSet.create([{
                'name': 'template_image',
                'template': product_template,
                'image': file
            }])

            product_variant, = product_template.products

            image_set2, = ProductImageSet.create([{
                'name': 'product_image',
                'product': product_variant,
                'image': file1
            }])
            Product.write([product_variant], {
                'use_template_images': False,
            })

            # Assert that there is no default image set for template
            self.assertIsNone(product_template.default_image_set)
            # Assert that there is no default image set for variant
            self.assertIsNone(product_variant.default_image_set)

            # Set image_set1 as default image set of product_template
            ProductImageSet.set_default([image_set1])
            # Assert if image_set1 is set as default image set of template
            self.assertEqual(product_template.default_image_set, image_set1)

            # Set image_set2 as default image set of product_variant
            ProductImageSet.set_default([image_set2])
            # Assert if image_set2 is set as default image set of variant
            self.assertEqual(product_variant.default_image_set, image_set2)


def suite():
    "Test suite"
    test_suite = unittest.TestSuite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestProduct)
    )
    return test_suite


if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
