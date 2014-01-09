# -*- coding: utf-8 -*-
'''
    product

    Products catalogue display

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from collections import deque

from nereid import render_template, cache
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, key_from_list, url_for
from nereid import jsonify
from nereid.contrib.pagination import Pagination
from nereid.contrib.sitemap import SitemapIndex, SitemapSection
from werkzeug.exceptions import NotFound
from flask.ext.babel import format_currency

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta


__all__ = [
    'Product', 'ProductsImageSet', 'ProductsRelated', 'ProductCategory',
    'WebSite', 'WebsiteCategory', 'ProductTemplate',
]
__metaclass__ = PoolMeta

DEFAULT_STATE = {'invisible': Not(Bool(Eval('displayed_on_eshop')))}
DEFAULT_STATE2 = {
    'invisible': Not(Bool(Eval('displayed_on_eshop'))),
    'required': Bool(Eval('displayed_on_eshop')),
}


class ProductTemplate:
    __name__ = "product.template"

    products_displayed_on_eshop = fields.Function(
        fields.One2Many('product.product', None, 'Products (Disp. on eShop)'),
        'get_products_displayed_on_eshop'
    )

    def get_products_displayed_on_eshop(self, name=None):
        """
        Return the variants that are displayed on eshop
        """
        Product = Pool().get('product.product')

        return map(
            int,
            Product.search([
                ('template', '=', self.id),
                ('displayed_on_eshop', '=', True),
            ])
        )


class Product:
    "Product extension for Nereid"
    __name__ = "product.product"

    #: Decides the number of products that would be remebered.
    recent_list_size = 5

    #: The list of fields allowed to be sent back on a JSON response from the
    #: application. This is validated before any product info is built
    #:
    #: The `name`, `sale_price`, `id` and `uri` are sent by default
    #:
    #: .. versionadded:: 0.3
    json_allowed_fields = set(['rec_name', 'sale_price', 'id', 'uri'])

    uri = fields.Char(
        'URI', select=True, on_change_with=['template', 'uri'],
        states=DEFAULT_STATE2
    )
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?', select=True)

    image_sets = fields.One2Many(
        'product.product.imageset', 'product',
        'Image Sets', states=DEFAULT_STATE
    )
    up_sells = fields.Many2Many(
        'product.product-product.product',
        'product', 'up_sell', 'Up-Sells', states=DEFAULT_STATE
    )
    cross_sells = fields.Many2Many(
        'product.product-product.product',
        'product', 'cross_sell', 'Cross-Sells', states=DEFAULT_STATE
    )

    @classmethod
    def __setup__(cls):
        super(Product, cls).__setup__()
        cls._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        cls.per_page = 9

    @staticmethod
    def default_displayed_on_eshop():
        return False

    def on_change_with_uri(self):
        """
        If the URI is empty, slugify template name into URI
        """
        if not self.uri:
            return slugify(self.template.name)
        return self.uri

    @classmethod
    def render(cls, uri, path=None):
        """Renders the template for a single product.

        :param uri: URI of the product
        :param path: Ignored parameter. This is used in
                     cases where SEO friendly URL like
                     product/category/sub-cat/sub-sub-cat/product-uri
                     are generated
        """
        categories = request.nereid_website.get_categories() + [None]
        products = cls.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
            ('category', 'in', categories),
        ], limit=1)
        if not products:
            return NotFound('Product Not Found')

        cls._add_to_recent_list(int(products[0]))
        return render_template('product.jinja', product=products[0])

    @classmethod
    def recent_products(cls):
        """
        GET
        ---

        Return a list of recently visited products in JSON

        POST
        ----

        Add the product to the recent list manually. This method is required
        if the product page is cached, or is served by a Caching Middleware
        like Varnish which may clear the session before sending the request to
        Nereid.

        Just as with GET the response is the AJAX of recent products
        """
        if request.method == 'POST':
            cls._add_to_recent_list(request.form.get('product_id', type=int))

        fields = set(request.args.getlist('fields')) or cls.json_allowed_fields
        fields = fields & cls.json_allowed_fields

        if 'sale_price' in fields:
            fields.remove('sale_price')

        response = []
        if hasattr(session, 'sid'):
            products = cls.browse(session.get('recent-products', []))
            for product in products:
                product_val = {}
                for field in fields:
                    product_val[field] = getattr(product, field)
                product_val['sale_price'] = format_currency(
                    product.sale_price(),
                    request.nereid_currency.code
                )
                response.append(product_val)

        return jsonify(products=response)

    @classmethod
    def _add_to_recent_list(cls, product_id):
        """Adds the given product ID to the list of recently viewed products
        By default the list size is 5. To change this you can inherit
        product.product and set :attr:`recent_list_size` attribute to a
        non negative integer value

        For faster and easier access the products are stored with the ids alone
        this behaviour can be modified by subclassing.

        The deque object cannot be saved directly in the cache as its not
        serialisable. Hence a conversion to list is made on the fly

        .. versionchanged:: 0.3
            If there is no session for the user this function returns an empty
            list. This ensures that the code is consistent with iterators that
            may use the returned value

        :param product_id: the product id to prepend to the list
        """
        if not hasattr(session, 'sid'):
            current_app.logger.warning(
                "No session. Not saving to browsing history"
            )
            return []

        recent_products = deque(
            session.setdefault('recent-products', []), cls.recent_list_size
        )
        # XXX: If a product is already in the recently viewed list, but it
        # would be nice to remember the recent_products list in the order of
        # visits.
        if product_id not in recent_products:
            recent_products.appendleft(product_id)
            session['recent-products'] = list(recent_products)
        return recent_products

    @classmethod
    def render_list(cls, page=1):
        """
        Renders the list of all products which are displayed_on_shop=True

        .. tip::

            The implementation uses offset for pagination and could be
            extremely resource intensive on databases. Hence you might want to
            either have an alternate cache/search server based pagination or
            limit the pagination to a maximum page number.

            The base implementation does NOT limit this and could hence result
            in poor performance

        :param page: The page in pagination to be displayed
        """
        categories = request.nereid_website.get_categories() + [None]
        products = Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories),
        ], page, cls.per_page)
        return render_template('product-list.jinja', products=products)

    def sale_price(self, quantity=0):
        """Return the Sales Price.
        A wrapper designed to work as a context variable in templating

        The price is calculated from the pricelist associated with the current
        user. The user in the case of guest user is logged in user. In the
        event that the logged in user does not have a pricelist set against
        the user, the guest user's pricelist is chosen.

        Finally if neither the guest user, nor the regsitered user has a
        pricelist set against them then the list price is displayed as the
        price of the product

        :param quantity: Quantity
        """
        return self.list_price

    @classmethod
    def quick_search(cls):
        """A quick and dirty search which searches through the product.product
        for an insensitive like and returns a pagination object the same.
        """
        page = request.args.get('page', 1, type=int)
        query = request.args.get('q', '')
        categories = request.nereid_website.get_categories() + [None]
        products = Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories),
            ('name', 'ilike', '%' + query + '%'),
        ], page, cls.per_page)
        return render_template('search-results.jinja', products=products)

    @classmethod
    def sitemap_index(cls):
        """
        Returns a Sitemap Index Page
        """
        categories = request.nereid_website.get_categories() + [None]
        index = SitemapIndex(cls, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories)
        ])
        return index.render()

    @classmethod
    def sitemap(cls, page):
        categories = request.nereid_website.get_categories() + [None]
        sitemap_section = SitemapSection(
            cls, [
                ('displayed_on_eshop', '=', True),
                ('category', 'in', categories)
            ], page
        )
        sitemap_section.changefreq = 'daily'
        return sitemap_section.render()

    def get_absolute_url(self, **kwargs):
        """
        Return the URL of the current product.

        This method works only under a nereid request context
        """
        return url_for('product.product.render', uri=self.uri, **kwargs)

    def _json(self):
        """
        Return a JSON serializable dictionary of the product
        """
        response = {
            'template': {
                'name': self.template.rec_name,
                'id': self.template.id,
                'list_price': self.list_price,
            },
            'code': self.code,
            'description': self.description,
        }
        if self.category:
            response['category'] = self.category._json()
        return response


class ProductsImageSet(ModelSQL, ModelView):
    "Images for Product"
    __name__ = 'product.product.imageset'

    name = fields.Char("Name", required=True)
    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True)
    thumbnail_image = fields.Many2One(
        'nereid.static.file', 'Thumbnail Image',
        ondelete='CASCADE', select=True)
    medium_image = fields.Many2One(
        'nereid.static.file', 'Medium Image',
        ondelete='CASCADE', select=True)
    large_image = fields.Many2One(
        'nereid.static.file', 'Large Image',
        ondelete='CASCADE', select=True)


class ProductsRelated(ModelSQL):
    "Related Product"
    __name__ = 'product.product-product.product'
    _table = 'product_product_rel'

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    up_sell = fields.Many2One(
        'product.product', 'Up-sell Product',
        ondelete='CASCADE', select=True)
    cross_sell = fields.Many2One(
        'product.product', 'Cross-sell Product',
        ondelete='CASCADE', select=True)


class ProductCategory:
    "Product Category extension for Nereid"
    __name__ = "product.category"

    uri = fields.Char(
        'URI', select=True,
        on_change_with=['name', 'uri', 'parent'], states=DEFAULT_STATE2
    )
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?')
    description = fields.Text('Description')
    image = fields.Many2One(
        'nereid.static.file', 'Image',
        states=DEFAULT_STATE
    )
    image_preview = fields.Function(
        fields.Binary('Image Preview'), 'get_image_preview'
    )
    sites = fields.Many2Many(
        'nereid.website-product.category',
        'category', 'website', 'Sites', states=DEFAULT_STATE
    )

    @classmethod
    def __setup__(cls):
        super(ProductCategory, cls).__setup__()
        cls._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        cls.per_page = 9

    @staticmethod
    def default_displayed_on_eshop():
        return True

    def get_image_preview(self, name=None):
        if self.image:
            return self.image.file_binary
        return None

    def on_change_with_uri(self):
        """Slugifies the full name of a category to
        make the uri on change of product name.
        Slugification will occur only if there is no uri filled from before.
        """
        if self.name and not self.uri:
            full_name = (self.parent and self.parent.rec_name or '') \
                + self.name
            return slugify(full_name)
        return self.uri

    @classmethod
    @ModelView.button
    def update_uri(cls, categories):
        """Update the uri of the category from the complete name.
        """
        for category in categories:
            cls.write([category], {'uri': slugify(category.rec_name)})

    @classmethod
    def render(cls, uri, page=1):
        """
        Renders the template 'category.jinja' with the category and the
        products of the category paginated in the context

        :param uri: URI of the product category
        :param page: Integer value of the page
        """
        ProductTemplate = Pool().get('product.template')

        categories = cls.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
            ('sites', '=', request.nereid_website.id)
        ])
        if not categories:
            return NotFound('Product Category Not Found')

        # if only one category is found then it is rendered and
        # if more than one are found then the first one is rendered
        category = categories[0]
        products = Pagination(ProductTemplate, [
            ('products.displayed_on_eshop', '=', True),
            ('category', '=', category.id),
        ], page=page, per_page=cls.per_page)
        return render_template(
            'category.jinja', category=category, products=products
        )

    @classmethod
    def render_list(cls, page=1):
        """
        Renders the list of all categories which are displayed_on_shop=True
        paginated.

        :param page: Integer ID of the page
        """
        categories = Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id),
        ], page, cls.per_page)
        return render_template('category-list.jinja', categories=categories)

    @classmethod
    def get_categories(cls, page=1):
        """Return list of categories
        """
        return Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id)
        ], page, cls.per_page)

    @classmethod
    def get_root_categories(cls, page=1):
        """Return list of Root Categories."""
        return Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id),
            ('parent', '=', None),
        ], page, cls.per_page)

    @classmethod
    def context_processor(cls):
        """This function will be called by nereid to update
        the template context. Must return a dictionary that the context
        will be updated with.

        This function is registered with nereid.template.context_processor
        in xml code
        """
        return {
            'all_categories': cls.get_categories,
            'root_categories': cls.get_root_categories,
        }

    @classmethod
    def sitemap_index(cls):
        index = SitemapIndex(cls, [
            ('displayed_on_eshop', '=', True),
            ('id', 'in', request.nereid_website.get_categories())
        ])
        return index.render()

    @classmethod
    def sitemap(cls, page):
        sitemap_section = SitemapSection(
            cls, [
                ('displayed_on_eshop', '=', True),
                ('id', 'in', request.nereid_website.get_categories())
            ], page
        )
        sitemap_section.changefreq = 'daily'
        return sitemap_section.render()

    def get_absolute_url(self, **kwargs):
        return url_for(
            'product.category.render', uri=self.uri, **kwargs
        )

    def _json(self):
        """
        Return a JSON serializable dictionary of the category
        """
        return {
            'name': self.name,
            'id': self.id,
            'rec_name': self.rec_name,
        }


class WebSite:
    """
    Add categories for products
    """
    __name__ = 'nereid.website'

    categories = fields.Many2Many(
        'nereid.website-product.category',
        'website', 'category', 'Categories Displayed on E-Shop',
        domain=[('displayed_on_eshop', '=', True)]
    )

    def get_categories(self):
        """Returns the IDS of the categories
        """
        cache_key = key_from_list([
            Transaction().cursor.dbname,
            Transaction().user,
            'nereid.website.get_categories',
            self.id,
        ])
        rv = cache.get(cache_key)
        if rv is None:
            rv = map(int, self.categories)
            cache.set(cache_key, rv, 60 * 60)
        return rv


class WebsiteCategory(ModelSQL):
    "Categories to be displayed on a website"
    __name__ = 'nereid.website-product.category'
    _table = 'website_category_rel'

    website = fields.Many2One(
        'nereid.website', 'Website',
        ondelete='CASCADE', select=True, required=True)
    category = fields.Many2One(
        'product.category', 'Category',
        ondelete='CASCADE', select=True, required=True)
