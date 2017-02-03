""" PayU payment processing. """
import logging

from decimal import Decimal
from hashlib import md5

from oscar.apps.payment.exceptions import GatewayError, TransactionDeclined
from oscar.core.loading import get_model
from ecommerce.core.url_utils import get_lms_url

# from ecommerce.core.constants import ISO_8601_FORMAT
from ecommerce.extensions.order.constants import PaymentEventTypeName
from ecommerce.extensions.payment.exceptions import InvalidSignatureError
from ecommerce.extensions.payment.processors import BasePaymentProcessor


logger = logging.getLogger(__name__)

PaymentEvent = get_model('order', 'PaymentEvent')
PaymentEventType = get_model('order', 'PaymentEventType')
ProductClass = get_model('catalogue', 'ProductClass')
Source = get_model('payment', 'Source')
SourceType = get_model('payment', 'SourceType')


class Payu(BasePaymentProcessor):
    """
    PayU payment processor (November 2016)

    For reference, see
    http://developers.payulatam.com/en/web_checkout/integration.html
    """

    NAME = 'payu'
    TRANSACTION_ACCEPTED = '4'
    TRANSACTION_DECLINED = '6'
    TRANSACTION_ERROR = '104'
    PAYMENT_FORM_SIGNATURE = 1
    CONFIRMATION_SIGNATURE = 2

    def __init__(self):
        """
        Constructs a new instance of the PayU processor.

        Raises:
            KeyError: If no settings configured for this payment processor
            AttributeError: If LANGUAGE_CODE setting is not set.
        """
        configuration = self.configuration
        self.payment_page_url = configuration['payment_page_url']
        self.merchant_id = configuration['merchant_id']
        self.account_id = configuration['account_id']
        self.api_key = configuration['api_key']
        self.tax = configuration['tax']
        self.tax_return_base = configuration['tax_return_base']

        try:
            self.test = configuration['test']
        except KeyError:
            # This is the case for production mode
            self.test = None

        self.response_url = configuration['response_url']
        self.confirmation_url = configuration['confirmation_url']

    @property
    def receipt_page_url(self):
        return get_lms_url(self.configuration['receipt_path'])

    @property
    def cancel_page_url(self):
        return get_lms_url(self.configuration['cancel_path'])

    @property
    def error_page_url(self):
        return get_lms_url(self.configuration['error_path'])

    def get_transaction_parameters(self, basket, request=None):
        """
        Generate a dictionary of signed parameters PayU requires to complete a transaction.

        Arguments:
            basket (Basket): The basket of products being purchased.

        Keyword Arguments:
            request (Request): A Request object which could be used to construct an absolute URL; not
                used by this method.

        Returns:
            dict: PayU-specific parameters required to complete a transaction, including a signature.
        """
        parameters = {
            'payment_page_url': self.payment_page_url,
            'merchantId': self.merchant_id,
            'accountId': self.account_id,
            'ApiKey': self.api_key,
            'referenceCode': basket.order_number,
            'tax': self.tax,
            'taxReturnBase': self.tax_return_base,
            'currency': basket.currency,
            'buyerEmail': basket.owner.email,
            'buyerFullName': basket.owner.full_name,
            'amount': str(basket.total_incl_tax),
            'responseUrl': self.response_url,
            'confirmationUrl': self.confirmation_url,
        }

        single_seat = self.get_single_seat(basket)

        if single_seat:
            parameters['description'] = single_seat.course_id

        if self.test:
            parameters['test'] = self.test

        parameters['referenceCode'] = basket.order_number
        parameters['signature'] = self._generate_signature(parameters, self.PAYMENT_FORM_SIGNATURE)

        return parameters

    @staticmethod
    def get_single_seat(basket):
        """
        Return the first product encountered in the basket with the product
        class of 'seat'.  Return None if no such products were found.
        """
        try:
            seat_class = ProductClass.objects.get(slug='seat')
        except ProductClass.DoesNotExist:
            # this occurs in test configurations where the seat product class is not in use
            return None

        for line in basket.lines.all():
            product = line.product
            if product.get_product_class() == seat_class:
                return product

        return None

    def handle_processor_response(self, response, basket=None):
        """
        Handle a response (i.e., "merchant notification") from PayU.

        This method does the following:
            1. Verify the validity of the response.
            2. Create PaymentEvents and Sources for successful payments.

        Arguments:
            response (dict): Dictionary of parameters received from the payment processor.

        Keyword Arguments:
            basket (Basket): Basket being purchased via the payment processor.

        Raises:
            TransactionDeclined: Indicates the payment was declined by the processor.
            GatewayError: Indicates a general error on the part of the processor.
            InvalidPayUDecision: Indicates an unknown decision value
        """

        # Validate the signature
        if not self.is_signature_valid(response):
            raise InvalidSignatureError

        # Raise an exception for payments that were not accepted. Consuming code should be responsible for handling
        # and logging the exception.
        transaction_state = response['state_pol']
        if transaction_state != self.TRANSACTION_ACCEPTED:
            exception = {
                self.TRANSACTION_DECLINED: TransactionDeclined,
                self.TRANSACTION_ERROR: GatewayError
            }.get(transaction_state, InvalidPayUDecision)

            raise exception

        # Create Source to track all transactions related to this processor and order
        source_type, __ = SourceType.objects.get_or_create(name=self.NAME)
        currency = response['currency']
        total = Decimal(response['value'])
        transaction_id = response['transaction_id']
        req_card_number = response['cc_number'] or ''

        source = Source(source_type=source_type,
                        currency=currency,
                        amount_allocated=total,
                        amount_debited=total,
                        reference=transaction_id,
                        label=req_card_number)

        # Create PaymentEvent to track
        event_type, __ = PaymentEventType.objects.get_or_create(name=PaymentEventTypeName.PAID)
        event = PaymentEvent(event_type=event_type, amount=total, reference=transaction_id, processor_name=self.NAME)

        return source, event

    def _generate_signature(self, parameters, signature_type):
        """
        Sign the contents of the provided transaction parameters dictionary.

        This allows PayU to verify that the transaction parameters have not been tampered with
        during transit.

        We also use this signature to verify that the signature we get back from PayU is valid for
        the parameters that they are giving to us.

        Arguments:
            parameters (dict): A dictionary of transaction parameters.

        Returns:
            unicode: the signature for the given parameters
        """

        # signatures to validate payment form
        if signature_type == self.PAYMENT_FORM_SIGNATURE:
            uncoded = "{api_key}~{merchant_id}~{reference_code}~{amount}~{currency}".format(
                api_key=self.api_key,
                merchant_id=self.merchant_id,
                reference_code=parameters['referenceCode'],
                amount=parameters['amount'],
                currency=parameters['currency'],
            )

        # PayU applies a logic to validate signatures on confirmation page:
        # If the second decimal of the value parameter is zero, e.g. 150.00
        # the parameter new_value to generate the signature should only have one decimal, as follows: 150.0
        # If the second decimal of the value parameter is different from zero, e.g. 150.26
        # the parameter new_value to generate the signature should have two decimals, as follows: 150.26
        # See http://developers.payulatam.com/en/web_checkout/integration.html
        # signatures to validate confirmation response
        if signature_type == self.CONFIRMATION_SIGNATURE:
            value = parameters['value']
            last_decimal = value[-1]
            if last_decimal == '0':
                new_value = value[:-1]
            else:
                new_value = value

            uncoded = "{api_key}~{merchant_id}~{reference_sale}~{new_value}~{currency}~{state_pol}".format(
                api_key=self.api_key,
                merchant_id=self.merchant_id,
                reference_sale=parameters['reference_sale'],
                new_value=new_value,
                currency=parameters['currency'],
                state_pol=parameters['state_pol'],
            )

        return md5(uncoded).hexdigest()

    def is_signature_valid(self, response):
        """Returns a boolean indicating if the response's signature (indicating potential tampering) is valid."""
        return response and (self._generate_signature(response, self.CONFIRMATION_SIGNATURE) == response.get('sign'))

    def issue_credit(self, source, amount, currency):
        """
        This method should be implemented in the future in order
        to accept payment refunds
        see http://developers.payulatam.com/en/api/refunds.html
        """

        logger.exception(
            'PayU processor can not issue credits or refunds',
        )

        raise NotImplementedError


class InvalidPayUDecision(GatewayError):
    """The decision returned by PayU was not recognized."""
    pass