import uuid

from oscar.core.loading import get_model

from ecommerce.extensions.test import factories
from ecommerce.programs.constants import BENEFIT_MAP, BENEFIT_PROXY_CLASS_MAP
from ecommerce.programs.custom import class_path
from ecommerce.programs.forms import ProgramOfferForm
from ecommerce.tests.testcases import TestCase

Benefit = get_model('offer', 'Benefit')
ConditionalOffer = get_model('offer', 'ConditionalOffer')


class ProgramOfferFormTests(TestCase):
    def generate_data(self, **kwargs):
        data = {
            'program_uuid': uuid.uuid4(),
            'benefit_type': Benefit.PERCENTAGE,
            'benefit_value': 22,
        }
        data.update(**kwargs)
        return data

    def assert_program_offer_conditions(self, offer, program_uuid, expected_benefit_value, expected_benefit_type):
        """ Assert the given offer's parameters match the expected values. """
        self.assertEqual(offer.name, 'Discount for program {}'.format(program_uuid))
        self.assertEqual(offer.offer_type, ConditionalOffer.SITE)
        self.assertEqual(offer.status, ConditionalOffer.OPEN)
        self.assertEqual(offer.max_basket_applications, 1)
        self.assertEqual(offer.condition.program_uuid, program_uuid)
        self.assertEqual(offer.benefit.proxy_class, class_path(BENEFIT_MAP[expected_benefit_type]))
        self.assertEqual(offer.benefit.value, expected_benefit_value)

    def assert_form_errors(self, data, expected_errors):
        """ Assert that form validation fails with the expected errors. """
        form = ProgramOfferForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors, expected_errors)

    def test_init(self):
        """ The constructor should pull initial data from the passed-in instance. """
        program_offer = factories.ProgramOfferFactory()
        form = ProgramOfferForm(instance=program_offer)
        self.assertEqual(form['program_uuid'].value(), program_offer.condition.program_uuid.hex)
        self.assertEqual(form['benefit_type'].value(), BENEFIT_PROXY_CLASS_MAP[program_offer.benefit.proxy_class])
        self.assertEqual(form['benefit_value'].value(), program_offer.benefit.value)

    def test_clean_percentage(self):
        """ If a percentage benefit type is specified, the benefit value must never be greater than 100. """
        data = self.generate_data(benefit_type=Benefit.PERCENTAGE, benefit_value=101)
        self.assert_form_errors(data, {'benefit_value': ['Percentage discounts cannot be greater than 100%.']})

    def test_clean_with_missing_start_date(self):
        """ If an end date is specified, a start date must also be specified. """
        data = self.generate_data(end_datetime='2017-01-01 00:00:00')
        self.assert_form_errors(data,
                                {'start_datetime': ['A start date must be specified when specifying an end date.']})

    def test_clean_with_invalid_date_ordering(self):
        """ The start date must always occur before the end date. """
        data = self.generate_data(start_datetime='2017-01-02 00:00:00', end_datetime='2017-01-01 00:00:00')
        self.assert_form_errors(data, {'start_datetime': ['The start date must occur before the end date.']})

    def test_clean_with_conflicting_program_uuid(self):
        """ If an offer already exists for the given program, an error should be raised. """
        offer = factories.ProgramOfferFactory()
        data = self.generate_data(program_uuid=offer.condition.program_uuid)
        self.assert_form_errors(data, {'program_uuid': ['An offer already exists for this program.']})

    def test_save_create(self):
        """ A new ConditionalOffer, Benefit, and Condition should be created. """
        data = self.generate_data()
        form = ProgramOfferForm(data=data)
        form.is_valid()
        offer = form.save()
        self.assert_program_offer_conditions(offer, data['program_uuid'], data['benefit_value'], data['benefit_type'])

    def test_save_edit(self):
        """ Previously-created ConditionalOffer, Benefit, and Condition instances should be updated. """
        offer = factories.ProgramOfferFactory()
        data = self.generate_data(program_uuid=offer.condition.program_uuid, benefit_type=Benefit.FIXED)
        form = ProgramOfferForm(data=data, instance=offer)
        form.is_valid()
        form.save()

        offer.refresh_from_db()
        self.assert_program_offer_conditions(offer, data['program_uuid'], data['benefit_value'], data['benefit_type'])

    def test_save_without_commit(self):
        """ No data should be persisted to the database if the commit kwarg is set to False. """
        form = ProgramOfferForm(data=self.generate_data())
        form.is_valid()
        instance = form.save(commit=False)
        self.assertIsNone(instance.pk)
        self.assertFalse(hasattr(instance, 'benefit'))
        self.assertFalse(hasattr(instance, 'condition'))
