# -*- coding: utf-8 -*-
'''
    product

    Products catalogue display

    :copyright: (c) 2010-2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from collections import deque

from nereid import render_template, cache, route
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, key_from_list, url_for
from nereid import jsonify, Markup, context_processor
from nereid.contrib.pagination import Pagination
from nereid.contrib.sitemap import SitemapIndex, SitemapSection
from werkzeug.exceptions import NotFound
from flask.ext.babel import format_currency

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta
from trytond import backend

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
    description = fields.Text("Description")
    image_sets = fields.One2Many(
        'product.product.imageset', 'template', 'Images',
    )
    default_image_set = fields.Many2One(
        'product.product.imageset', 'Default Image Set', readonly=True
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
        'URI', select=True, states=DEFAULT_STATE2
    )
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?', select=True)

    image_sets = fields.One2Many(
        'product.product.imageset', 'product',
        'Image Sets', states={
            'invisible': Bool(Eval('use_template_images')),
        }
    )
    up_sells = fields.Many2Many(
        'product.product-product.product',
        'product', 'up_sell', 'Up-Sells', states=DEFAULT_STATE
    )
    cross_sells = fields.Many2Many(
        'product.product-product.product',
        'product', 'cross_sell', 'Cross-Sells', states=DEFAULT_STATE
    )
    default_image = fields.Function(
        fields.Many2One('nereid.static.file', 'Image'), 'get_default_image',
    )
    default_image_set = fields.Many2One(
        'product.product.imageset', 'Default Image Set', readonly=True,
    )
    use_template_description = fields.Boolean("Use template's description")
    use_template_images = fields.Boolean("Use template's images")

    def get_default_image(self, name):
        """
        Returns default product image if any.
        """
        images = self.get_images()
        return images[0].id if images else None

    @classmethod
    def __setup__(cls):
        super(Product, cls).__setup__()
        cls._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        cls.description.states['invisible'] = Bool(
            Eval('use_template_description')
        )
        cls.per_page = 9

    @staticmethod
    def default_displayed_on_eshop():
        return False

    @fields.depends('template', 'uri')
    def on_change_with_uri(self):
        """
        If the URI is empty, slugify template name into URI
        """
        if not self.uri:
            return slugify(self.template.name)
        return self.uri

    @staticmethod
    def default_use_template_description():
        return True

    @staticmethod
    def default_use_template_images():
        return True

    @classmethod
    @route('/product/<uri>')
    @route('/product/<path:path>/<uri>')
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
            ('template.active', '=', True),
        ], limit=1)
        if not products:
            return NotFound('Product Not Found')

        cls._add_to_recent_list(int(products[0]))
        return render_template('product.jinja', product=products[0])

    @classmethod
    @route('/products/+recent', methods=['GET', 'POST'])
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
    @route('/products')
    @route('/products/<int:page>')
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
            ('template.active', '=', True),
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
    @route('/search')
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
            ('template.active', '=', True),
            ('name', 'ilike', '%' + query + '%'),
        ], page, cls.per_page)
        return render_template('search-results.jinja', products=products)

    @classmethod
    @route('/sitemaps/product-index.xml')
    def sitemap_index(cls):
        """
        Returns a Sitemap Index Page
        """
        categories = request.nereid_website.get_categories() + [None]
        index = SitemapIndex(cls, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories),
            ('template.active', '=', True),
        ])
        return index.render()

    @classmethod
    @route('/sitemaps/product-<int:page>.xml')
    def sitemap(cls, page):
        categories = request.nereid_website.get_categories() + [None]
        sitemap_section = SitemapSection(
            cls, [
                ('displayed_on_eshop', '=', True),
                ('category', 'in', categories),
                ('template.active', '=', True),
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

    def get_description(self):
        """
        Get description of product.

        If the product is set to use the template's description, then
        the template description is sent back.

        The returned value is a `~jinja2.Markup` object which makes it
        HTML safe and can be used directly in templates. It is recommended
        to use this method instead of trying to wrap this logic in the
        templates.
        """
        if self.use_template_description:
            return Markup(self.template.description)
        return Markup(self.description)

    def get_images(self):
        """
        Get images of product variant.

        If the product is set to use the template's images, then
        the template images is sent back.
        """
        if self.use_template_images:
            return map(lambda x: x.image, self.template.image_sets)
        return map(lambda x: x.image, self.image_sets)


class ProductsImageSet(ModelSQL, ModelView):
    "Images for Product"
    __name__ = 'product.product.imageset'

    name = fields.Char("Name", required=True)
    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True)
    template = fields.Many2One(
        'product.template', 'Template',
        ondelete='CASCADE', select=True)
    image = fields.Many2One(
        'nereid.static.file', 'Image',
        ondelete='CASCADE', select=True, required=True
    )
    image_preview = fields.Function(
        fields.Binary('Image Preview'), 'get_image_preview'
    )

    @property
    def large(self):
        """
        Return large image
        """
        return self.resize(1024, 1024)

    @property
    def medium(self):
        """
        Return medium image
        """
        return self.resize(500, 500)

    @property
    def thumbnail(self):
        """
        Return thumbnail image
        """
        return self.resize(100, 100)

    def resize(self, width, height):
        """
        Return image with user specified dimensions
        """
        return self.image.transform_command().resize(width, height)

    def get_image_preview(self, name=None):
        return self.image.file_binary if self.image else None

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor

        table = TableHandler(cursor, cls, module_name)
        if not table.column_exist('image'):
            table.column_rename('large_image', 'image')

        super(ProductsImageSet, cls).__register__(module_name)

    @classmethod
    def __setup__(cls):
        super(ProductsImageSet, cls).__setup__()
        cls._buttons.update({
            'set_default': {},
        })

    @classmethod
    @ModelView.button
    def set_default(cls, image_sets):
        """
        Sets the image set as default image set
        """
        Product = Pool().get('product.product')
        ProductTemplate = Pool().get('product.template')

        for image_set in image_sets:
            if image_set.product:
                Product.write([image_set.product], {
                    'default_image_set': image_set.id,
                })
            elif image_set.template:
                ProductTemplate.write([image_set.template], {
                    'default_image_set': image_set.id,
                })


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
        'URI', select=True, states=DEFAULT_STATE2
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
    sequence = fields.Integer('Sequence')

    @classmethod
    def __setup__(cls):
        super(ProductCategory, cls).__setup__()
        cls._order.insert(0, ('sequence', 'ASC'))
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

    @fields.depends('name', 'uri', 'parent')
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
    @route('/category/<uri>')
    @route('/category/<uri>/<int:page>')
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
    @route('/catalog')
    @route('/catalog/<int:page>')
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
    @context_processor('all_categories')
    def get_categories(cls, page=1):
        """Return list of categories
        """
        return Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id)
        ], page, cls.per_page)

    @classmethod
    @context_processor('root_categories')
    def get_root_categories(cls, page=1):
        """Return list of Root Categories."""
        return Pagination(cls, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id),
            ('parent', '=', None),
        ], page, cls.per_page)

    @classmethod
    @route('/sitemaps/category-index.xml')
    def sitemap_index(cls):
        index = SitemapIndex(cls, [
            ('displayed_on_eshop', '=', True),
            ('id', 'in', request.nereid_website.get_categories())
        ])
        return index.render()

    @classmethod
    @route('/sitemaps/category-<int:page>.xml')
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

    @staticmethod
    def default_sequence():
        return 10


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
    root_navigation_model = fields.Selection(
        'get_root_navigation_model', 'Root Navigation Model', select=True,
        help="The model with which the root navigation should be built"
    )
    root_category = fields.Many2One(
        "product.category", 'Root Category', select=True, states={
            "required": Eval('root_navigation_model') == 'product.category',
            "invisible": Eval('root_navigation_model') != 'product.category',
        }
    )

    @classmethod
    def get_root_navigation_model(cls):
        "Downstream modules can override the method and add entries to this"
        return [
            (None, ''),
            ('product.category', 'Product Category'),
        ]

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
