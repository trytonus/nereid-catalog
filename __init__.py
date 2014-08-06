# -*- coding: utf-8 -*-
'''

    nereid_catalog

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool
from product import (
    Product, ProductsImageSet, ProductsRelated, ProductCategory,
    WebSite, WebsiteCategory, ProductTemplate
)


def register():
    Pool.register(
        ProductsImageSet,
        Product,
        ProductTemplate,
        ProductsRelated,
        ProductCategory,
        WebSite,
        WebsiteCategory,
        module='nereid_catalog', type_='model')
