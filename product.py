#This file is part of Tryton/Nereid.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
"Products catalogue display"
from collections import deque

from nereid import render_template, cache, redirect, jsonify
from nereid.globals import session, request, current_app
from nereid.helpers import slugify, key_from_list, login_required, url_for, \
    Pagination
from werkzeug.exceptions import NotFound, abort

from trytond.model import ModelView, ModelSQL, fields
from trytond.pyson import Eval, Not, Bool
from trytond.transaction import Transaction

DEFAULT_DOMAIN = [('displayed_on_eshop', '=', True)]
DEFAULT_STATE = {'invisible': Not(Bool(Eval('displayed_on_eshop')))}
DEFAULT_STATE2 = {
    'invisible': Not(Bool(Eval('displayed_on_eshop'))),
    'required': Bool(Eval('displayed_on_eshop')),
    }


class Product(ModelSQL, ModelView):
    "Product extension for Nereid"
    _name = "product.product"

    #: Decides the number of products that would be remebered. Remember that
    #: increasing this number would increase the payload of the session
    recent_list_size = 5

    uri = fields.Char('URI', select=True, on_change_with=['name', 'uri'],
        states=DEFAULT_STATE2)
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?')

    thumbnail = fields.Many2One('nereid.static.file', 'Thumbnail', 
        states=DEFAULT_STATE)
    images = fields.Many2Many('product.product-nereid.static.file',
            'product', 'image', 'Image Gallery', states=DEFAULT_STATE)
    up_sells = fields.Many2Many('product.product-product.product',
            'product', 'up_sell', 'Up-Sells', states=DEFAULT_STATE)
    cross_sells = fields.Many2Many('product.product-product.product',
            'product', 'cross_sell', 'Cross-Sells', states=DEFAULT_STATE)

    additional_categories = fields.Many2Many(
            'product.product-product.category', 'product', 'category',
            'Additional Categories')
    wishlist = fields.Many2Many('product.product-party.address',
            'product', 'address', 'Wishlist')

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
        """Renders the template for a signle product.

        :param uri: URI of the product
        """
        allowed_categories = [c.id for c in request.nereid_website.categories]
        excl_products = [p.id for p in request.nereid_website.exclude_products]
        product_ids = self.search(
            DEFAULT_DOMAIN + [
                ('uri', '=', uri), 
                ('category', 'in', allowed_categories),
                ('id', 'not in', excl_products)
                ]
            )
        if not product_ids:
            return NotFound('Product Not Found')
        # if only one product is found then it is rendered and 
        # if more than one are found then the first one is rendered
        product = self.browse(product_ids[0])
        self._add_to_recent_list(product_ids[0])
        return render_template('product.jinja', product=product)

    def _add_to_recent_list(self, product_id):
        """Adds the given product ID to the list of recently viewed products
        By default the list size is 5. To change this you can inherit
        product.product and set recent_list_size attribute to an non negative
        integer value

        for faster and easier access the products are stored with the ids alone
        this behaviour can be modified by subclassing.

        The deque object cannot be saved directly in the cache as its not
        serialisable

        :param product_id: the product id to prepend to the list
        """
        cache_key = 'product.product._add_to_recent_products' + session.sid
        recent_products = deque(
            cache.get(cache_key) or [], self.recent_list_size)
        if product_id not in recent_products:
            recent_products.appendleft(product_id)
            cache.set(cache_key, list(recent_products), 10 * 24 * 60 * 60)

    def render_list(self, page=1):
        """
        Renders the list of all products which are displayed_on_shop=True
        """
        allowed_categories = [c.id for c in request.nereid_website.categories]
        excl_products = [p.id for p in request.nereid_website.exclude_products]
        products = Pagination(self,
            DEFAULT_DOMAIN + [
                ('category', 'in', allowed_categories),
                ('id', 'not in', excl_products)
                ], page, self.per_page)
        return render_template(request.nereid_website.category_template.name, 
            products = products)

    def sale_price(self, product, quantity=0):
        """Return the Sales Price. 
        A wrapper designed to work as a context variable in templating

        The price is calcualetd from the pricelist associated with the current
        user. The user in the case of guest user is logged in user. In the 
        event that the logged in user does not have a pricelist set against 
        the user, the guest user's pricelist is chosen.

        Finally if neither the guest user, nor the regsitered user has a 
        pricelist set against them then the list price is displayed as the 
        price of the product

        :param product: ID of product
        :param quantity: Quantity
        """
        currency_obj = self.pool.get('currency.currency')
        price_list = request.nereid_user.party.sale_price_list.id if \
            request.nereid_user.party.sale_price_list else None

        # If the regsitered user does not have a pricelist try for
        # the pricelist of guest user
        if not request.is_guest_user and price_list is None:
            address_obj = self.pool.get('party.address')
            guest_user = address_obj.browse(current_app.guest_user)
            price_list = guest_user.party.sale_price_list.id if \
                guest_user.party.sale_price_list else None

        # Neither users have a pricelist
        if price_list is None:
            product_obj = self.pool.get('product.product')
            product_record = product_obj.browse(product)
            price = product_record.list_price

        # Build a Cache key to store in cache
        cache_key = key_from_list([
            Transaction().cursor.dbname,
            Transaction().user,
            request.nereid_user.party.id,
            price_list, product, quantity,
            request.nereid_currency.id,
            'product.product.sale_price',
            ])
        rv = cache.get(cache_key)
        if rv is None:
            # There is a valid pricelist, now get the price
            with Transaction().set_context(
                    customer = request.nereid_user.party.id, 
                    price_list = price_list):
                price = self.get_sale_price([product], quantity)[product]

            # Now convert the price to the session currency
            rv = currency_obj.compute(
                request.nereid_website.company.currency.id,     # From
                price, request.nereid_currency.id)
            cache.set(cache_key, rv, 60 * 5)
        return rv

    @login_required
    def add_to_wishlist(self):
        """Add the product to wishlist
        """
        user = request.nereid_user
        product = request.args.get('product')
        self.write(product, {'wishlist': [('add', user.id)]})
        return True

    def quick_search(self):
        """A quick and dirty search which searches through the product.product
        for an insensitive like and returns a pagination object the same.
        """
        page = int(request.args.get('page', 1))
        query = request.args.get('q', '')
        allowed_categories = request.nereid_website.get_categories()
        excl_products = request.nereid_website.get_exclude_products()
        products = Pagination(self,
            DEFAULT_DOMAIN + [
                ('category', 'in', allowed_categories),
                ('id', 'not in', excl_products),
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

Product()


class ProductsImages(ModelSQL):
    "Images for Product"
    _name = 'product.product-nereid.static.file'
    _table = 'product_file_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product', 
        ondelete='CASCADE', select=1, required=True)
    image = fields.Many2One(
        'nereid.static.file', 'Image', 
        ondelete='CASCADE', select=1, required=True)

ProductsImages()


class ProductCategories(ModelSQL):
    "Additional Categories for Product"
    _name = 'product.product-product.category'
    _table = 'product_category_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product', 
        ondelete='CASCADE', select=1, required=True)
    category = fields.Many2One(
        'product.category', 'Category', 
        ondelete='CASCADE', select=1, required=True)

ProductCategories()


class ProductAddress(ModelSQL):
    "Product Wishlist"
    _name = 'product.product-party.address'
    _table = 'product_address_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product', 
        ondelete='CASCADE', select=1, required=True)
    address = fields.Many2One(
        'party.address', 'Address', 
        ondelete='CASCADE', select=1, required=True)

ProductAddress()


class ProductsRelated(ModelSQL):
    "Related Product"
    _name = 'product.product-product.product'
    _table = 'product_product_rel'
    _description = __doc__

    product = fields.Many2One(
        'product.product', 'Product', 
        ondelete='CASCADE', select=1, required=True)
    up_sell = fields.Many2One(
        'product.product', 'Up-sell Product', 
        ondelete='CASCADE', select=1)
    cross_sell = fields.Many2One(
        'product.product', 'Cross-sell Product', 
        ondelete='CASCADE', select=1)

ProductsRelated()


class ProductCategory(ModelSQL, ModelView):
    "Product Category extension for Nereid"
    _name = "product.category"
    _inherit = 'product.category'

    uri = fields.Char('URI', select=True, 
            on_change_with=['name', 'uri', 'parent'], states=DEFAULT_STATE2)
    displayed_on_eshop = fields.Boolean('Displayed on E-Shop?')
    description = fields.Text('Description')
    image = fields.Many2One('nereid.static.file', 'Image', 
            states=DEFAULT_STATE)
    sites = fields.Many2Many('nereid.website-product.category',
            'category', 'website', 'Sites',  states=DEFAULT_STATE)

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
        product_obj = self.pool.get('product.product')
        category_ids = self.search(
            DEFAULT_DOMAIN + [
                ('uri', '=', uri),
                ('sites', '=', request.nereid_website.id)
                ]
            )
        if not category_ids:
            return NotFound('Product Category Not Found')

        # if only one product is found then it is rendered and 
        # if more than one are found then the first one is rendered
        category = self.browse(category_ids[0])
        excl_products = [p.id for p in request.nereid_website.exclude_products]
        products = Pagination(product_obj,
            DEFAULT_DOMAIN + [
                ('category', '=', category.id),
                ('id', 'not in', excl_products)
                ],
            page=page, per_page=self.per_page, error_out=False)
        return render_template('category.jinja', category=category, 
            products=products,)

    def render_list(self, page=1):
        """
        Renders the list of all categories which are displayed_on_shop=True
        """
        categories = Pagination(self,
            DEFAULT_DOMAIN + [('sites', '=', request.nereid_website.id)], 
            page, self.per_page)
        return render_template(
            request.nereid_website.category_template.name, 
            categories=categories)

    def get_categories(self, page=1):
        """Return list of categories
        """
        return Pagination(self,
            DEFAULT_DOMAIN + 
            [('sites', '=', request.nereid_website.id)],
            page, self.per_page)

    def get_root_categories(self, page=1):
        """Return list of Root Categories."""
        return Pagination(self,
            DEFAULT_DOMAIN + [
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
        domain=DEFAULT_DOMAIN)
    exclude_products = fields.Many2Many(
        'nereid.website-product.product',
        'website', 'product', 'Products Excluded from E-Shop',
        depends=['categories'], domain=[
            ('category', 'in', Eval('categories'))] + DEFAULT_DOMAIN)

    product_template = fields.Many2One(
       'nereid.template', 'Product List Template', required=True)
    category_template = fields.Many2One(
       'nereid.template', 'Prod. Category List Template', required=True)

    def get_categories(self):
        """Returns the IDS of the categories
        """
        cache_key = key_from_list([
            Transaction().cursor.dbname,
            Transaction().user,
            'nereid.website.get_categories'
            ])
        rv = cache.get(cache_key)
        if rv is None:
            rv = [x.id for x in request.nereid_website.categories]
            cache.set(cache_key, rv, 60 * 60)
        return rv

    def get_exclude_products(self):
        """Returns the ids of the excluded products
        """
        cache_key = key_from_list([
            Transaction().cursor.dbname,
            Transaction().user,
            'nereid.website.get_excluded_products'
            ])
        rv = cache.get(cache_key)
        if rv is None:
            rv = [x.id for x in request.nereid_website.exclude_products]
            cache.set(cache_key, rv, 60 * 60)
        return rv

WebSite()


class PartyAddress(ModelSQL, ModelView):
    """Extend Party Address to have product wishlist"""
    _name = 'party.address'

    wishlist = fields.Many2Many('product.product-party.address',
            'address', 'product', 'Wishlist')

    @login_required
    def render_wishlist(self):
        """Render a template with the items in wishlist
        """
        return render_template('wishlist.jinja', 
            products=request.nereid_user.wishlist)

PartyAddress()


class WebsiteProduct(ModelSQL):
    "Products to be displayed on a website"
    _name = 'nereid.website-product.product'
    _table = 'website_product_rel'
    _description = __doc__

    website = fields.Many2One(
        'nereid.website', 'Website', 
        ondelete='CASCADE', select=1, required=True)
    product = fields.Many2One(
        'product.product', 'Product', 
        ondelete='CASCADE', select=1, required=True)

WebsiteProduct()


class WebsiteCategory(ModelSQL):
    "Categories to be displayed on a website"
    _name = 'nereid.website-product.category'
    _table = 'website_category_rel'
    _description = __doc__

    website = fields.Many2One(
        'nereid.website', 'Website', 
        ondelete='CASCADE', select=1, required=True)
    category = fields.Many2One(
        'product.category', 'Category', 
        ondelete='CASCADE', select=1, required=True)

WebsiteCategory()
