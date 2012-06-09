# -*- coding: utf-8 -*-
'''
    product

    Products catalogue display

    :copyright: (c) 2010-2012 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from collections import deque

from nereid import render_template, cache, flash, redirect, abort
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, key_from_list, login_required, url_for, \
    jsonify
from nereid.contrib.pagination import Pagination
from nereid.contrib.sitemap import SitemapIndex, SitemapSection
from werkzeug.exceptions import NotFound
from flaskext.babel import format_currency

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction
from trytond.pool import Pool

from .i18n import _

DEFAULT_STATE = {'invisible': Not(Bool(Eval('displayed_on_eshop')))}
DEFAULT_STATE2 = {
    'invisible': Not(Bool(Eval('displayed_on_eshop'))),
    'required': Bool(Eval('displayed_on_eshop')),
    }


class Product(ModelSQL, ModelView):
    "Product extension for Nereid"
    _name = "product.product"

    uri = fields.Char('URI', select=True, on_change_with=['name', 'uri'],
        states=DEFAULT_STATE2)
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?', select=True)


    image_sets = fields.One2Many(
        'product.product.imageset', 'product',
        'Image Sets', states=DEFAULT_STATE
    )
    up_sells = fields.Many2Many('product.product-product.product',
        'product', 'up_sell', 'Up-Sells', states=DEFAULT_STATE)
    cross_sells = fields.Many2Many('product.product-product.product',
        'product', 'cross_sell', 'Cross-Sells', states=DEFAULT_STATE)

    wishlist = fields.Many2Many('product.product-nereid.user',
        'product', 'user', 'Wishlist')

    browse_nodes = fields.Many2Many(
        'product.product-product.browse_node',
        'product', 'browse_node', 'Browse Nodes'
    )
    #TODO: Create a functional many2many field for the sites 

    def __init__(self):
        super(Product, self).__init__()
        self._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        self.per_page = 9

    def default_displayed_on_eshop(self):
        return True

    def on_change_with_uri(self, vals):
        if vals.get('name'):
            if not vals.get('uri'):
                vals['uri'] = slugify(vals['name'])
            return vals['uri']
        else:
            return {}

    def render(self, uri):
        """Renders the template for a single product.

        :param uri: URI of the product
        """
        categories = request.nereid_website.get_categories() + [None]
        product_ids = self.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
            ('category', 'in', categories),
            ]
        )
        if not product_ids:
            return NotFound('Product Not Found')

        # if only one product is found then it is rendered and 
        # if more than one are found then the first one is rendered
        product = self.browse(product_ids[0])
        self._add_to_recent_list(product_ids[0])
        return render_template('product.jinja', product=product)

    #: Decides the number of products that would be remebered. 
    recent_list_size = 5

    #: The list of fields allowed to be sent back on a JSON response from the
    #: application. This is validated before any product info is built
    #:
    #: The `name`, `sale_price`, `id` and `uri` are sent by default
    #:
    #: .. versionadded:: 0.3
    json_allowed_fields = [
        'name', 'sale_price', 'id', 'uri'
    ]

    def recent_products(self):
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
            self._add_to_recent_list(request.form.get('product_id', type=int))

        fields = request.args.getlist('fields')
        if fields:
            allowed_fields = [
                f for f in fields if f in self.json_allowed_fields
            ]
        else:
            allowed_fields = self.json_allowed_fields[:]
        products = []

        if 'sale_price' in allowed_fields:
            allowed_fields.remove('sale_price')

        if hasattr(session, 'sid'):
            product_ids = session.get('recent-products', [])
            products = self.read(product_ids, allowed_fields)
            for product in products:
                product['sale_price'] = format_currency(
                        self.sale_price(product['id']),
                        request.nereid_currency.code
                )

        return jsonify(
            products = products
        )

    def _add_to_recent_list(self, product_id):
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
            session.setdefault('recent-products', []), self.recent_list_size
        )
        if product_id not in recent_products:
            recent_products.appendleft(product_id)
            session['recent-products'] = list(recent_products)
        return recent_products

    def render_list(self, page=1):
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
        products = Pagination(self, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories),
        ], page, self.per_page)
        return render_template('product-list.jinja', products=products)

    def sale_price(self, product, quantity=0):
        """Return the Sales Price.
        A wrapper designed to work as a context variable in templating

        The price is calculated from the pricelist associated with the current
        user. The user in the case of guest user is logged in user. In the
        event that the logged in user does not have a pricelist set against
        the user, the guest user's pricelist is chosen.

        Finally if neither the guest user, nor the regsitered user has a
        pricelist set against them then the list price is displayed as the
        price of the product

        :param product: ID of product
        :param quantity: Quantity
        """
        product = self.browse(product)
        return product.list_price

    @login_required
    def add_to_wishlist(self):
        """Add the product to wishlist
        """
        user = request.nereid_user
        product = request.args.get('product', type=int)
        self.write(product, {'wishlist': [('add', [user.id])]})
        flash(_("The product has been added to wishlist"))
        if request.is_xhr:
            return 'OK'
        return redirect(url_for('nereid.user.render_wishlist'))

    def quick_search(self):
        """A quick and dirty search which searches through the product.product
        for an insensitive like and returns a pagination object the same.
        """
        page = int(request.args.get('page', 1))
        query = request.args.get('q', '')
        categories = request.nereid_website.get_categories() + [None]
        products = Pagination(self, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories),
            ('name', 'ilike', '%' + query + '%'),
        ], page, self.per_page)
        return render_template('search-results.jinja', products = products)

    def context_processor(self):
        """This function will be called by nereid to update
        the template context. Must return a dictionary that the context
        will be updated with.

        This function is registered with nereid.template.context_processor
        in xml code
        """
        return {'get_sale_price': self.sale_price}

    def sitemap_index(self):
        categories = request.nereid_website.get_categories() + [None]
        index = SitemapIndex(self, [
            ('displayed_on_eshop', '=', True),
            ('category', 'in', categories)
            ]
        )
        return index.render()

    def sitemap(self, page):
        categories = request.nereid_website.get_categories() + [None]
        sitemap_section = SitemapSection(
            self, [
                ('displayed_on_eshop', '=', True),
                ('category', 'in', categories)
            ], page
        )
        sitemap_section.changefreq = 'daily'
        return sitemap_section.render()

    def get_absolute_url(self, product, **kwargs):
        return url_for(
            'product.product.render', uri=product.uri, **kwargs)

Product()


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
    _name = "product.browse_node"
    _description = "Browse nodes"

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

    def __init__(self):
        super(BrowseNode, self).__init__()
        self._sql_constraints += [
            ('uri', 'UNIQUE(uri)', 'URI of Browse Node must be unique.')
        ]
        self._constraints += [
            ('check_recursion', 'recursive_nodes'),
        ]
        self._error_messages.update({
            'recursive_nodes': 'You cannot create recursive browse nodes!',
        })

    def default_left(self):
        return 0

    def default_right(self):
        return 0

    def get_rec_name(self, ids, name):
        if not ids:
            return {}
        res = {}
        def _name(browse_node):
            if browse_node.id in res:
                return res[browse_node.id]
            elif browse_node.parent:
                return _name(browse_node.parent) + ' / ' + browse_node.name
            else:
                return browse_node.name
        for browse_node in self.browse(ids):
            res[browse_node.id] = _name(browse_node)
        return res

    def make_uri(self, name, parent):
        """Construct a URI and return it."""
        full_name = u''
        if parent:
            full_name += "%s-" % self.get_rec_name(
                [parent.id], None
            )[parent.id]
        full_name += name
        full_name.replace('/', '-')
        return slugify(full_name)

    def update_uri(self, ids):
        """Update the uri of the category from the complete name.
        """
        for browsenode in self.browse(ids):
            uri = self.make_uri(browsenode.name, browsenode.parent)
            self.write(browsenode.id, {'uri': uri})
        return True

    def render(self, uri, page=1):
        """
        Renders a page of products in a browse node. The products displayed 
        are not just the products of this browse node, but also those of the 
        descendants of the browse node. This is achieved through the MPTT
        implementation.

        :param uri: uri of the browse node to be shown
        :param page: page of the products to be displayed
        """
        product_obj = Pool().get('product.product')

        browse_node_ids = self.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
        ])
        if not browse_node_ids:
            return abort(404)

        # TODO: Improve this implementation with the capability to define the
        # depth to which descendants must be shown. The selection of products
        # can also be improved with the help of a join and selecting from the
        # relationship table rather than by first chosing the browse nodes, 
        # and then the products (as done here)
        browse_node = self.browse(browse_node_ids[0])
        browse_nodes = self.search([
            ('left', '>=', browse_node.left),
            ('right', '<=', browse_node.right),
        ])
        products = Pagination(product_obj, [
            ('displayed_on_eshop', '=', True),
            ('browse_nodes', 'in', browse_nodes),
        ], page=page, per_page=self.products_per_page)
        return render_template(
            'browse-node.jinja', browse_node=browse_node, products=products
        )

    def render_list(self, page=1):
        """
        Renders the list of all browse nodes which are displayed_on_shop=True
        """
        browse_nodes = Pagination(self, [
            ('displayed_on_eshop', '=', True),
        ], page, self.products_per_page)
        return render_template(
            'browse-node-list.jinja', browse_nodes=browse_nodes
        )

BrowseNode()


class ProductBrowseNode(ModelSQL):
    "Product BrowseNode Relation"
    _name = 'product.product-product.browse_node'
    _table = 'product_browse_node_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    browse_node = fields.Many2One(
        'product.browse_node', 'Browse Node',
        ondelete='CASCADE', select=True, required=True)

ProductBrowseNode()


class ProductsImageSet(ModelSQL, ModelView):
    "Images for Product"
    _name = 'product.product.imageset'
    _description = __doc__

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

ProductsImageSet()


class ProductUser(ModelSQL):
    "Product Wishlist"
    _name = 'product.product-nereid.user'
    _table = 'product_user_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    user = fields.Many2One(
        'nereid.user', 'User',
        ondelete='CASCADE', select=True, required=True)

ProductUser()


class ProductsRelated(ModelSQL):
    "Related Product"
    _name = 'product.product-product.product'
    _table = 'product_product_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product',
        ondelete='CASCADE', select=True, required=True)
    up_sell = fields.Many2One(
        'product.product', 'Up-sell Product',
        ondelete='CASCADE', select=True)
    cross_sell = fields.Many2One(
        'product.product', 'Cross-sell Product',
        ondelete='CASCADE', select=True)

ProductsRelated()


class ProductCategory(ModelSQL, ModelView):
    "Product Category extension for Nereid"
    _name = "product.category"
    _inherit = 'product.category'

    uri = fields.Char('URI', select=True,
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
        'category', 'website', 'Sites',  states=DEFAULT_STATE
    )

    def __init__(self):
        super(ProductCategory, self).__init__()
        self._rpc.update({
            'update_uri': True,
        })
        self._sql_constraints += [
            ('uri_uniq', 'UNIQUE(uri)', 'URI must be unique'),
        ]
        self.per_page = 9

    def default_displayed_on_eshop(self):
        return True

    def on_change_with_uri(self, vals):
        """Slugifies the full name of a category to
        make the uri on change of product name.
        Slugification will occur only if there is no uri filled from before.
        """
        if vals.get('name'):
            parent = None
            if not vals.get('uri'):
                if vals.get('parent'):
                    parent = self.browse(vals.get('parent'))
                vals['uri'] = self.make_uri(vals.get('name'), parent)
            return vals['uri']
        else:
            return {}

    def update_uri(self, ids):
        """Update the uri of the category from the complete name.
        """
        for category in self.browse(ids):
            uri = self.make_uri(category.name, category.parent)
            self.write(category.id, {'uri': uri})
        return True

    def render(self, uri, page=1):
        """
        Renders the template
        """
        product_obj = Pool().get('product.product')
        category_ids = self.search([
            ('displayed_on_eshop', '=', True),
            ('uri', '=', uri),
            ('sites', '=', request.nereid_website.id)
        ])
        if not category_ids:
            return NotFound('Product Category Not Found')

        # if only one product is found then it is rendered and 
        # if more than one are found then the first one is rendered
        category = self.browse(category_ids[0])
        products = Pagination(product_obj, [
            ('displayed_on_eshop', '=', True),
            ('category', '=', category.id),
        ], page=page, per_page=self.per_page)
        return render_template('category.jinja', category=category,
            products=products,)

    def render_list(self, page=1):
        """
        Renders the list of all categories which are displayed_on_shop=True
        """
        categories = Pagination(self, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id),
        ], page, self.per_page)
        return render_template('category-list.jinja', categories=categories)

    def get_categories(self, page=1):
        """Return list of categories
        """
        return Pagination(self, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id)
        ], page, self.per_page)

    def get_root_categories(self, page=1):
        """Return list of Root Categories."""
        return Pagination(self, [
            ('displayed_on_eshop', '=', True),
            ('sites', '=', request.nereid_website.id),
            ('parent', '=', False),
        ], page, self.per_page)

    def context_processor(self):
        """This function will be called by nereid to update
        the template context. Must return a dictionary that the context
        will be updated with.

        This function is registered with nereid.template.context_processor
        in xml code
        """
        return {
            'all_categories': self.get_categories,
            'root_categories': self.get_root_categories,
            }

    def make_uri(self, name, parent):
        """Construct a URI and return it."""
        full_name = u''
        if parent:
            full_name += "%s-" % self.get_rec_name([parent.id], None)[parent.id]
        full_name += name
        full_name.replace('/', '-')
        return slugify(full_name)

    def sitemap_index(self):
        index = SitemapIndex(self, [
            ('displayed_on_eshop', '=', True),
            ('id', 'in', request.nereid_website.get_categories())
            ]
        )
        return index.render()

    def sitemap(self, page):
        sitemap_section = SitemapSection(
            self, [
                ('displayed_on_eshop', '=', True),
                ('id', 'in', request.nereid_website.get_categories())
            ], page
        )
        sitemap_section.changefreq = 'daily'
        return sitemap_section.render()

    def get_absolute_url(self, category, **kwargs):
        return url_for(
            'product.category.render', uri=category.uri, **kwargs
        )

ProductCategory()


class WebSite(ModelSQL, ModelView):
    """
    Extend site to add templates for product listing and
    category listing
    """
    _name = 'nereid.website'

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
            request.nereid_website.id,
            ])
        rv = cache.get(cache_key)
        if rv is None:
            rv = [x.id for x in request.nereid_website.categories]
            cache.set(cache_key, rv, 60 * 60)
        return rv

WebSite()


class NereidUser(ModelSQL, ModelView):
    """Extend User to have product wishlist"""
    _name = 'nereid.user'

    wishlist = fields.Many2Many(
        'product.product-nereid.user', 'user', 'product', 'Wishlist'
    )

    @login_required
    def render_wishlist(self):
        """
        Render a template with the items in wishlist
        """
        return render_template(
            'wishlist.jinja', products=request.nereid_user.wishlist
        )

NereidUser()


class WebsiteCategory(ModelSQL):
    "Categories to be displayed on a website"
    _name = 'nereid.website-product.category'
    _table = 'website_category_rel'
    _description = __doc__

    website = fields.Many2One(
        'nereid.website', 'Website',
        ondelete='CASCADE', select=True, required=True)
    category = fields.Many2One(
        'product.category', 'Category',
        ondelete='CASCADE', select=True, required=True)

WebsiteCategory()


class WebsiteBrowseNode(ModelSQL):
    "Root Browse Nodes on a Website"
    _name = 'nereid.website-product.browse_node'
    _table = 'website_browse_node_rel'
    _description = __doc__

    website = fields.Many2One(
        'nereid.website', 'Website',
        ondelete='CASCADE', select=True, required=True)
    browse_node = fields.Many2One(
        'product.browse_node', 'Browse Node',
        ondelete='CASCADE', select=True, required=True)

WebsiteBrowseNode()
