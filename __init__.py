# -*- coding: utf-8 -*-
'''

    nereid_catalog

    :copyright: (c) 2010-2013 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool
from product import (
    Product, BrowseNode, ProductBrowseNode, ProductsImageSet,
    ProductUser, ProductsRelated, ProductCategory, WebSite, NereidUser,
    WebsiteCategory, WebsiteBrowseNode
)


def register():
    Pool.register(
        Product,
        BrowseNode,
        ProductBrowseNode,
        ProductsImageSet,
        ProductUser,
        ProductsRelated,
        ProductCategory,
        WebSite,
        NereidUser,
        WebsiteCategory,
        WebsiteBrowseNode,
        module='nereid_catalog', type_='model')
