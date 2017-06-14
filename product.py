# -*- coding: utf-8 -*-
from collections import deque

from nereid import render_template, route
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, url_for
from nereid import jsonify, Markup, current_locale
from nereid.contrib.pagination import Pagination
from nereid.contrib.sitemap import SitemapIndex, SitemapSection
from werkzeug.exceptions import NotFound
from flask.ext.babel import format_currency

from trytond.model import ModelSQL, ModelView, fields
from trytond.pyson import Eval, Not, Bool
from trytond.pool import Pool, PoolMeta
from sql import Null

__all__ = [
    'Product', 'ProductsRelated', 'ProductTemplate',
    'ProductMedia', 'ProductCategory'
]

DEFAULT_STATE = {'invisible': Not(Bool(Eval('displayed_on_eshop')))}
DEFAULT_STATE2 = {
    'invisible': Not(Bool(Eval('displayed_on_eshop'))),
    'required': Bool(Eval('displayed_on_eshop')),
}


class ProductMedia(ModelSQL, ModelView):
    "Product Media"
    __name__ = "product.media"

    sequence = fields.Integer("Sequence", required=True, select=True)
    static_file = fields.Many2One(
        "nereid.static.file", "Static File", required=True, select=True)
    product = fields.Many2One("product.product", "Product", select=True)
    template = fields.Many2One("product.template", "Template", select=True)
    url = fields.Function(fields.Char("URL"), "get_url")

    def get_url(self, name):
        return self.static_file.url

    @classmethod
    def __setup__(cls):
        super(ProductMedia, cls).__setup__()

        cls._order.insert(0, ('sequence', 'ASC'))

    @staticmethod
    def default_sequence():
        return 10


class ProductTemplate:
    __metaclass__ = PoolMeta
    __name__ = "product.template"

    products_displayed_on_eshop = fields.Function(
        fields.One2Many('product.product', None, 'Products (Disp. on eShop)'),
        'get_products_displayed_on_eshop'
    )

    long_description = fields.Text('Long Description')

    description = fields.Text("Description")
    media = fields.One2Many("product.media", "template", "Media")
    images = fields.Function(
        fields.One2Many('nereid.static.file', None, 'Images'),
        getter='get_template_images'
    )

    def get_template_images(self, name=None):
        """
        Getter for `images` function field
        """
        template_images = []
        for media in self.media:
            if media.static_file.mimetype and \
                    'image' in media.static_file.mimetype:
                template_images.append(media.static_file.id)
        return template_images

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
    __metaclass__ = PoolMeta
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
    long_description = fields.Text('Long Description')
    media = fields.One2Many("product.media", "product", "Media")
    images = fields.Function(
        fields.One2Many('nereid.static.file', None, 'Images'),
        getter='get_product_images'
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
    use_template_description = fields.Boolean("Use template's description")

    @classmethod
    def view_attributes(cls):
        return super(Product, cls).view_attributes() + [
            ('//page[@id="desc"]', 'states', {
                'invisible': Bool(Eval('use_template_description'))
            }), ('//page[@id="ecomm_det"]', 'states', {
                'invisible': Not(Bool(Eval('displayed_on_eshop')))
            }), ('//page[@id="related_products"]', 'states', {
                'invisible': Not(Bool(Eval('displayed_on_eshop')))
            })]

    @classmethod
    def copy(cls, products, default=None):
        """Duplicate products
        """
        if default is None:
            default = {}
        default = default.copy()

        duplicate_products = []
        for index, product in enumerate(products, start=1):
            if product.displayed_on_eshop:
                default['uri'] = "%s-copy-%d" % (product.uri, index)

            duplicate_products.extend(
                super(Product, cls).copy([product], default)
            )

        return duplicate_products

    @classmethod
    def validate(cls, products):
        super(Product, cls).validate(products)
        cls.check_uri_uniqueness(products)

    def get_default_image(self, name):
        """
        Returns default product image if any.
        """
        images = self.images or self.template.images
        return images[0].id if images else None

    @classmethod
    def __setup__(cls):
        super(Product, cls).__setup__()
        cls.description.states['invisible'] = Bool(
            Eval('use_template_description')
        )
        cls._error_messages.update({
            'unique_uri': ('URI of Product must be Unique'),
        })
        cls.per_page = 12

    @staticmethod
    def default_displayed_on_eshop():
        return False

    @fields.depends('template', 'uri')
    def on_change_with_uri(self):
        """
        If the URI is empty, slugify template name into URI
        """
        if not self.uri and self.template:
            return slugify(self.template.name)
        return self.uri

    @staticmethod
    def default_use_template_description():
        return True

    @classmethod
    def check_uri_uniqueness(cls, products):
        """
        Ensure uniqueness of products uri.
        """
        query = ['OR']
        for product in products:
            # Do not check for unique uri if product is marked as
            # not displayed on eshop
            if not product.displayed_on_eshop:
                continue

            arg = [
                'AND', [
                    ('id', '!=', product.id)
                ], [
                    ('uri', 'ilike', product.uri)
                ]
            ]
            query.append(arg)
        if query != ['OR'] and cls.search(query):
            cls.raise_user_error('unique_uri')

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
        products = cls.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
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
                    current_locale.currency.code
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

        products = Pagination(cls, [
            ('displayed_on_eshop', '=', True),
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
    @route('/sitemaps/product-index.xml')
    def sitemap_index(cls):
        """
        Returns a Sitemap Index Page
        """
        index = SitemapIndex(cls, [
            ('displayed_on_eshop', '=', True),
            ('template.active', '=', True),
        ])
        return index.render()

    @classmethod
    @route('/sitemaps/product-<int:page>.xml')
    def sitemap(cls, page):
        sitemap_section = SitemapSection(
            cls, [
                ('displayed_on_eshop', '=', True),
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
        return response

    def get_long_description(self):
        """
        Get long description of product.

        If the product is set to use the template's long description, then
        the template long description is sent back.

        The returned value is a `~jinja2.Markup` object which makes it
        HTML safe and can be used directly in templates. It is recommended
        to use this method instead of trying to wrap this logic in the
        templates.
        """
        if self.use_template_description:
            description = self.template.long_description
        else:
            description = self.long_description

        return Markup(description or '')

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
            description = self.template.description
        else:
            description = self.description
        return Markup(description or '')

    def get_product_images(self, name=None):
        """
        Getter for `images` function field
        """
        product_images = []
        for media in self.media:
            if not media.static_file.mimetype:
                continue
            if 'image' in media.static_file.mimetype:
                product_images.append(media.static_file.id)
        return product_images

    def get_images(self):
        """
        Get images of product variant.
        Fallback to template's images if there are no images
        for product.
        """
        if self.images:
            return self.images
        return self.template.images


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
    __metaclass__ = PoolMeta
    __name__ = 'product.category'

    @staticmethod
    def order_rec_name(tables):
        table, _ = tables[None]
        return [table.parent == Null, table.parent, table.name]

    @classmethod
    def __setup__(cls):
        super(ProductCategory, cls).__setup__()
        cls.rec_name.string = "Parent/name"
