# -*- coding: utf-8 -*-
'''
    product

    Products catalogue display

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from collections import deque

from nereid import render_template, cache, flash, redirect, abort
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, key_from_list, login_required, url_for
from nereid import jsonify
from nereid.contrib.pagination import Pagination
from nereid.contrib.sitemap import SitemapIndex, SitemapSection
from werkzeug.exceptions import NotFound
from flask.ext.babel import format_currency

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool, PoolMeta

from .i18n import _

__all__ = ['Product', 'BrowseNode', 'ProductBrowseNode', 'ProductsImageSet',
           'ProductUser', 'ProductsRelated', 'ProductCategory', 'WebSite',
           'NereidUser', 'WebsiteCategory', 'WebsiteBrowseNode']
__metaclass__ = PoolMeta

DEFAULT_STATE = {'invisible': Not(Bool(Eval('displayed_on_eshop')))}
DEFAULT_STATE2 = {
    'invisible': Not(Bool(Eval('displayed_on_eshop'))),
    'required': Bool(Eval('displayed_on_eshop')),
}


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

    wishlist = fields.Many2Many(
        'product.product-nereid.user', 'product', 'user', 'Wishlist'
    )

    browse_nodes = fields.Many2Many(
        'product.product-product.browse_node',
        'product', 'browse_node', 'Browse Nodes'
    )
    #TODO: Create a functional many2many field for the sites

    @classmethod
    def __setup__(cls):
        super(Product, cls).__setup__()
        cls._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        cls.per_page = 9

    @staticmethod
    def default_displayed_on_eshop():
        return True

    def on_change_with_uri(self):
        """
        If the URI is empty, slugify template name into URI
        """
        if not self.uri:
            return slugify(self.template.name)
        return self.uri

    @classmethod
    def render(cls, uri):
        """Renders the template for a single product.

        :param uri: URI of the product
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
    @login_required
    def add_to_wishlist(cls):
        """
        Add the product to wishlist

        .. versionchanged::2.6.0.1

            Only POST method can now be used to add products to wishlist.
        """
        cls.write(
            [cls(request.form.get('product', type=int))],
            {'wishlist': [('add', [request.nereid_user.id])]}
        )
        if request.is_xhr:
            return 'OK'
        flash(_("The product has been added to wishlist"))
        return redirect(url_for('nereid.user.render_wishlist'))

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


class BrowseNode(ModelSQL, ModelView):
    """
    Browse nodes are similar to categories to which products belong but with
    the difference that a product may belong to several browse nodes (product
    can only belong to one category).

    The limitation that a product can belong only to one category originates
    in the early design decisions of Tryton, where a category of a product
    could determine the expense, revenue or even taxation related accounts of
    the products under it.

    The word `Browse Node` was inspired by the design of Amazon's catalog. The
    entire hierarchy of products that we see on amazon are infact browse nodes.

    Browse nodes are meant to be seen more like tags of a product, and each
    tag is part of a hierarchy. This gives users the option to infact even use
    browse nodes in-lieu of categories.
    """
    __name__ = "product.browse_node"

    name = fields.Char('Name', required=True, translate=True)
    uri = fields.Char(
        'URI', depends=['displayed_on_eshop'], states=DEFAULT_STATE2
    )
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?')
    code = fields.Char('Code')
    description = fields.Text("Description")
    products = fields.Many2Many(
        'product.product-product.browse_node',
        'browse_node', 'product', 'Products'
    )

    # Fields for hierarchy
    parent = fields.Many2One(
        'product.browse_node', 'Parent', select=True,
        left="left", right="right", ondelete="RESTRICT"
    )
    children = fields.One2Many('product.browse_node', 'parent', 'Children')
    left = fields.Integer("Left", select=True)
    right = fields.Integer("Right", select=True)

    #: The `nereid.website`s in which this browse node is a root node.
    sites = fields.Many2Many(
        'nereid.website-product.browse_node',
        'browse_node', 'website', 'Root node in Sites',
        states=DEFAULT_STATE
    )

    #: Products displayed per page when paginated.
    products_per_page = 20

    @classmethod
    def __setup__(cls):
        super(BrowseNode, cls).__setup__()
        cls._sql_constraints += [
            ('uri', 'UNIQUE(uri)', 'URI of Browse Node must be unique.')
        ]
        cls._constraints += [
            ('check_recursion', 'recursive_nodes'),
        ]
        cls._error_messages.update({
            'recursive_nodes': 'You cannot create recursive browse nodes!',
        })
        cls._buttons.update({
            'update_uri': {}
        })

    @staticmethod
    def default_left():
        return 0

    @staticmethod
    def default_right():
        return 0

    def get_rec_name(self, name=None):
        if self.parent:
            return self.parent.rec_name + ' / ' + self.name
        return self.name

    @classmethod
    @ModelView.button
    def update_uri(cls, browse_nodes):
        """
        Update the uri of the browse node from the rec_name.
        """
        for browse_node in browse_nodes:
            cls.write([browse_node], {'uri': slugify(browse_node.rec_name)})

    @classmethod
    def render(cls, uri, page=1):
        """
        Renders a page of products in a browse node. The products displayed
        are not just the products of this browse node, but also those of the
        descendants of the browse node. This is achieved through the MPTT
        implementation.

        :param uri: uri of the browse node to be shown
        :param page: page of the products to be displayed
        """
        Product = Pool().get('product.product')

        browse_nodes = cls.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
        ], limit=1)
        if not browse_nodes:
            return abort(404)

        # TODO: Improve this implementation with the capability to define the
        # depth to which descendants must be shown. The selection of products
        # can also be improved with the help of a join and selecting from the
        # relationship table rather than by first chosing the browse nodes,
        # and then the products (as done here)
        browse_node, = browse_nodes
        browse_nodes = cls.search([
            ('left', '>=', browse_node.left),
            ('right', '<=', browse_node.right),
        ])
        products = Pagination(Product, [
            ('displayed_on_eshop', '=', True),
            ('browse_nodes', 'in', map(int, browse_nodes)),
        ], page=page, per_page=cls.products_per_page)
        return render_template(
            'browse-node.jinja', browse_node=browse_node, products=products
        )

    @classmethod
    def render_list(cls, page=1):
        """
        Renders the list of all browse nodes which are displayed_on_shop=True
        """
        browse_nodes = Pagination(cls, [
            ('displayed_on_eshop', '=', True),
        ], page, cls.products_per_page)
        return render_template(
            'browse-node-list.jinja', browse_nodes=browse_nodes
        )


class ProductBrowseNode(ModelSQL):
    "Product BrowseNode Relation"
    __name__ = 'product.product-product.browse_node'
    _table = 'product_browse_node_rel'

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    browse_node = fields.Many2One(
        'product.browse_node', 'Browse Node',
        ondelete='CASCADE', select=True, required=True)


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


class ProductUser(ModelSQL):
    "Product Wishlist"
    __name__ = 'product.product-nereid.user'
    _table = 'product_user_rel'

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    user = fields.Many2One(
        'nereid.user', 'User',
        ondelete='CASCADE', select=True, required=True)


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
        Product = Pool().get('product.product')

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
        products = Pagination(Product, [
            ('displayed_on_eshop', '=', True),
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
            ('parent', '=', False),
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
    Extend site to add templates for product listing and
    category listing
    """
    __name__ = 'nereid.website'

    categories = fields.Many2Many(
        'nereid.website-product.category',
        'website', 'category', 'Categories Displayed on E-Shop',
        domain=[('displayed_on_eshop', '=', True)]
    )

    #: The root browse nodes are the main nodes from which the site navigation
    #: should begin. For example, the top navigation on the e-commerce site
    #: could be these root browse nodes and the menu could expand to the
    #: children. While the utilisation of this field depends on how your
    #: website and the template decides to use it, the concept aims to be a
    #: reference to identify the organisation of the catalog for a specific
    #: website.
    browse_nodes = fields.Many2Many(
        'nereid.website-product.browse_node',
        'website', 'browse_node', 'Root Browse Nodes',
        domain=[('displayed_on_eshop', '=', True)]
    )

    featured_products_node = fields.Many2One(
        'product.browse_node', 'Featured Products Node'
    )
    latest_products_node = fields.Many2One(
        'product.browse_node', 'Latest Products Node'
    )
    upcoming_products_node = fields.Many2One(
        'product.browse_node', 'Upcoming Products Node'
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


class NereidUser:
    """Extend User to have product wishlist"""
    __name__ = 'nereid.user'

    wishlist = fields.Many2Many(
        'product.product-nereid.user', 'user', 'product', 'Wishlist'
    )

    @classmethod
    @login_required
    def render_wishlist(cls):
        """
        Render a template with the items in wishlist
        """
        return render_template(
            'wishlist.jinja', products=request.nereid_user.wishlist
        )


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


class WebsiteBrowseNode(ModelSQL):
    "Root Browse Nodes on a Website"
    __name__ = 'nereid.website-product.browse_node'
    _table = 'website_browse_node_rel'

    website = fields.Many2One(
        'nereid.website', 'Website',
        ondelete='CASCADE', select=True, required=True)
    browse_node = fields.Many2One(
        'product.browse_node', 'Browse Node',
        ondelete='CASCADE', select=True, required=True)
