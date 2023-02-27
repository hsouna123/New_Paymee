import logging
import json
import urllib.request
import urllib.parse
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PaymentAcquirerPaymee(models.Model):
    _inherit = 'payment.acquirer'

    provider = fields.Selection(selection_add=[('paymee', 'Paymee')], tracking=True, ondelete={'paymee': 'set default'})
    paymee_api_key = fields.Char('Paymee API Key')
    paymee_base_url = fields.Char('Paymee Base URL')

    def paymee_form_generate_values(self, values):
        self.ensure_one()
        base_url = self.paymee_base_url or self.get_base_url()
        paymee_tx_values = dict(values)
        paymee_tx_values.update({
            'paymee_api_key': self.paymee_api_key,
            'base_url': base_url,
            'reference': values['reference'] or '',
            'amount': int(values['amount'] * 100),
            'customer_email': values.get('partner_email', ''),
            'currency': values['currency'].name,
            'return_url': '%s/payment/paymee/return' % base_url,
            'cancel_url': '%s/payment/paymee/cancel' % base_url,
            'error_url': '%s/payment/paymee/error' % base_url,
        })
        return paymee_tx_values


class PaymentTransactionPaymee(models.Model):
    _inherit = 'payment.transaction'

    paymee_tx_id = fields.Char('Paymee Transaction ID')

    def _paymee_form_get_tx_from_data(self, data):
        reference = data.get('reference')
        tx_id = data.get('paymee_tx_id')
        if not reference or not tx_id:
            error_msg = _('Paymee: received data with missing reference (%s) or paymee_tx_id (%s)') % (reference, tx_id)
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        txs = self.env['payment.transaction'].search([('reference', '=', reference)])
        if not txs or len(txs) > 1:
            error_msg = _('Paymee: received data for reference %s') % (reference)
            if not txs:
                error_msg += _('; no transaction found')
            else:
                error_msg += _('; multiple transactions found')
            _logger.error(error_msg)
            raise ValidationError(error_msg)
        return txs[0]

    def _paymee_form_get_invalid_parameters(self, tx, data):
        invalid_parameters = []
        if tx.acquirer_reference and tx.acquirer_reference != data.get('paymee_tx_id'):
            invalid_parameters.append(('Transaction Id', data.get('paymee_tx_id'), tx.acquirer_reference))
        return invalid_parameters

    def _paymee_form_validate(self, data):
        status = data.get('status')
        res = {
            'acquirer_reference': data.get('paymee_tx_id'),
            'date': fields.datetime.now(),
        }
        if status == 'PAID':
            res.update(state='done')
        elif status in ['PENDING', 'REVERSED', 'REFUNDED']:
            res.update(state='pending')
        elif status in ['CANCELLED', 'ERROR']:
            res.update(state='cancel')
        return self.write(res)
