# -*- coding: utf-8 -*-
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
