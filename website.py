# -*- coding: utf-8 -*-
from trytond.pool import Pool, PoolMeta
from nereid import request, route, render_template
from nereid.contrib.pagination import Pagination

__all__ = ['WebSite']
__metaclass__ = PoolMeta


class WebSite:
    __name__ = 'nereid.website'

    @classmethod
    @route('/search')
    def quick_search(cls):
        """A quick and dirty search which searches through the product.product
        for an insensitive like and returns a pagination object the same.
        """
        Product = Pool().get('product.product')

        page = request.args.get('page', 1, type=int)
        query = request.args.get('q', '')
        products = Pagination(Product, [
            ('displayed_on_eshop', '=', True),
            ('template.active', '=', True),
            ('name', 'ilike', '%' + query + '%'),
        ], page, Product.per_page)
        return render_template('search-results.jinja', products=products)
