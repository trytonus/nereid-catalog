# -*- coding: utf-8 -*-
'''

    nereid_catalog

    :copyright: (c) 2010-2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool
from product import (
    Product, ProductsRelated, ProductTemplate, ProductMedia, ProductCategory
)
from website import WebSite


def register():
    Pool.register(
        Product,
        ProductTemplate,
        ProductCategory,
        ProductMedia,
        ProductsRelated,
        WebSite,
        module='nereid_catalog', type_='model'
    )
