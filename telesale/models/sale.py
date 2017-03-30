# -*- coding: utf-8 -*-
# © 2016 Comunitea - Javier Colmenero <javier@comunitea.com>
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html
from odoo import models, fields, api
import time
from datetime import date, timedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    chanel = fields.Selection([('erp', 'ERP'),
                               ('telesale', 'Telesale')],
                              string='Chanel',
                              default='erp',
                              readonly=True)

    @api.model
    def create_order_from_ui(self, orders):
        t_partner = self.env['res.partner']
        t_order = self.env['sale.order']
        t_order_line = self.env['sale.order.line']
        t_product = self.env['product.product']
        t_irvalue = self.env['ir.values']

        order_ids = []

        for rec in orders:
            order = rec['data']
            order_obj = False
            # if order['erp_id'] and order['erp_state'] != 'draft':

            #     self.cancel_sale_to_draft(cr, uid, order['erp_id'], context)
            #     order['erp_state'] = 'draft'

            partner_obj = t_partner.browse(order['partner_id'])
            warehouse_id = False
            domain = [('name', '=', 'warehouse_id'),
                      ('model', '=', 'sale.order')]
            default_value = t_irvalue.search(domain, limit=1)
            if default_value:
                warehouse_id = int(default_value.value_unpickle)
            else:
                warehouse_id = self._default_warehouse_id() and \
                    self._default_warehouse_id()[0].id or 1
            # TODO, BUSCAR VALORES POR DEFECTO WAREHOUSE ID SINO PONER EL DE LA
            # COMPAÑÍA
            vals = {
                # 'name': '/',
                'partner_id': partner_obj.id,
                'pricelist_id': partner_obj.property_product_pricelist.id,
                'partner_invoice_id': partner_obj.id,
                'partner_shipping_id': order.get('partner_shipping_id',
                                                 partner_obj.id),
                'chanel': 'telesale',
                'order_policy': 'picking',
                'date_order': time.strftime("%Y-%m-%d %H:%M:%S"),
                'requested_date': order['requested_date'] + " 19:00:00" or
                False,
                'note': order['note'],
                'warwhouse_id': warehouse_id,
                'client_order_ref': order.get('client_order_ref', False)
            }
            if order['erp_id'] and order['erp_state'] == 'draft':
                order_obj = t_order.browse(order['erp_id'])
                order_obj.write(vals)
            else:
                # vals['name'] = '/'
                order_obj = t_order.create(vals)

            order_ids.append(order_obj.id)

            order_lines = order['lines']

            if order['erp_id'] and order['erp_state'] == 'draft':
                domain = [('order_id', '=', order_obj.id)]
                line_objs = t_order_line.search(domain)
                line_objs.unlink()
            for line in order_lines:
                product_obj = t_product.browse(line['product_id'])
                product_uom_id = line.get('product_uom', False)
                product_uom_qty = line.get('qty', 0.0)
                vals = {
                    'order_id': order_obj.id,
                    'name': product_obj.name,
                    'product_id': product_obj.id,
                    'price_unit': line.get('price_unit', 0.0),
                    'product_uom': product_uom_id,
                    'product_uom_qty': product_uom_qty,
                    'tax_id': [(6, 0, line.get('tax_ids', False))],
                    'discount': line.get('discount', 0.0),
                }
                t_order_line.create(vals)
            if order['action_button'] == 'confirm':
                order_obj.action_button_confirm()
        return order_ids

    @api.model
    def confirm_order_background(self, order_id):
        # TODO DEPENDENCIA DEL MODULO PARA PONER EL HILO
        # self.action_button_confirm_thread(cr, uid, [order_id],
        #                                   context=context)
        self.browse(order_id).action_confirm()

    @api.model
    def cancel_order_from_ui(self, order_id):
        self.browse(order_id).action_cancel()

    @api.model
    def ts_onchange_partner_id(self, partner_id):
        res = {}
        order_t = self.env['sale.order']
        partner = self.env['res.partner'].browse(partner_id)

        order = order_t.new({'partner_id': partner_id,
                             'date_order': time.strftime("%Y-%m-%d"),
                             'pricelist_id':
                             partner.property_product_pricelist.id})
        order.onchange_partner_id()
        res.update({
            'pricelist_id': order.pricelist_id.id,
            'partner_shipping_id': order.partner_shipping_id.id,

        })
        return res


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.model
    def ts_product_id_change(self, product_id, partner_id):
        res = {}
        order_t = self.env['sale.order']
        partner = self.env['res.partner'].browse(partner_id)

        order = order_t.new({'partner_id': partner_id,
                             'date_order': time.strftime("%Y-%m-%d"),
                             'pricelist_id':
                             partner.property_product_pricelist.id})
        line = self.new({'order_id': order.id,
                         'product_id': product_id})
        line.product_id_change()
        res.update({
            'price_unit': line.price_unit,
            'product_uom': line.product_uom.id,
            'product_uom_qty': line.product_uom_qty,
            'tax_id': [x.id for x in line.tax_id]

        })
        return res

    @api.model
    def get_last_lines_by(self, period, client_id):
        """
        """
        cr = self._cr
        date_str = date.today()
        if period == "ult":
            sq = """ SELECT id
                     FROM sale_order_line sol
                     WHERE order_id in
                        (SELECT id
                         FROM sale_order WHERE
                         state in ('sale','done')
                         and partner_id = %s order by id desc limit 1)
                    ORDER BY id desc"""

        else:
            if period == "3month":
                date_str = date.today() - timedelta(90)
            elif period == "year":
                date_str = date.today() - timedelta(365)
            date_str = date_str.strftime("%Y-%m-%d %H:%M:%S")
            sq = """ SELECT * FROM
                        (SELECT distinct on (product_id) sol.id
                         FROM sale_order_line sol
                         INNER JOIN sale_order so ON so.id = sol.order_id
                         WHERE so.state in
                            ('sale','done')
                         AND so.partner_id = %s
                         AND so.date_order >= %s
                         ORDER BY product_id desc, id desc) AS sq
                    ORDER BY id desc"""

        if period != 'ult':
            cr.execute(sq, (client_id, date_str))
        else:
            cr.execute(sq, (client_id,))
        fetch = cr.fetchall()
        prod_ids = [x[0] for x in fetch]
        res = []
        for l in self.browse(prod_ids):
            dic = {
                'product_id': (l.product_id.id, l.product_id.name),
                'price_unit': l.product_id.list_price,
                'default_code': l.product_id.default_code
            }
            res.append(dic)
        return res