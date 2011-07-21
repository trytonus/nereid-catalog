# -*- coding: utf-8 -*-
"""
    testing

    Regsiter testing helpers

    :copyright: © 2011 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from nereid.testing import testing_proxy

@testing_proxy.register()
def create_product_category(self, name, **options):
    """Creates a product category
    """
    category_obj = self.pool.get('product.category')

    options.update({
        'name': name,
        })
    return category_obj.create(options)


@testing_proxy.register()
def create_product(self, name, category=None, uom='Unit', **options):
    """
    :param uom: Note it is the name of UOM (not symbol or code)
    """
    product_obj = self.pool.get('product.product')
    uom_obj = self.pool.get('product.uom')
    category_obj = self.pool.get('product.category')

    if category is None:
        category, = category_obj.search([], limit=1)

    options['name'] = name
    options['default_uom'], = uom_obj.search([('name', '=', uom)], limit=1)
    options['category'] = category

    try:
        account_obj = self.pool.get('account.account')
        account_journal_obj = self.pool.get('account.journal')
    except KeyError:
        # The account module is not installed
        pass
    else:
        stock_journal = account_journal_obj
        if 'account_expense' not in options:
            options['account_expense'], = account_obj.search([
                ('kind', '=', 'expense'), 
                ], limit=1)
        if 'account_revenue' not in options:
            options['account_revenue'], = account_obj.search([
                ('kind', '=', 'revenue'), 
                ], limit=1)
        #if 'account_journal_stock_input' not in options:
        #    options['account_journal_stock_input'] = stock_journal
        #if 'account_journal_stock_output' not in options:
        #    options['account_journal_stock_output'] = stock_journal

    return product_obj.create(options)
