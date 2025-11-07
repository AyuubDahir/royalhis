# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors and contributors
# For license information, please see license.txt


import frappe
from frappe import _, scrub
from frappe.utils import cint, flt
from six import iteritems

from erpnext.accounts.party import get_partywise_advanced_payment_amount
from erpnext.accounts.report.accounts_receivable.accounts_receivable import ReceivablePayableReport
from itertools import groupby


def execute(filters=None):
	args = {
		"party_type": "Customer",
		"naming_by": ["Selling Settings", "cust_master_name"],
	}

	return AccountReceivableSummary(filters).run(args)


class AccountReceivableSummary(ReceivablePayableReport):
	def run(self, args):
		self.party_type = args.get("party_type")
		self.party_naming_by = frappe.db.get_value(
			args.get("naming_by")[0], None, args.get("naming_by")[1]
		)
		self.get_columns()
		self.get_data(args)
		result = []
		if self.filters.based_by == "Debtor":
			sorted_data = sorted(self.data, key=lambda x: x['customer_group'])

			# Group the sorted data by the 'customer_group' key
			grouped_data = groupby(sorted_data, key=lambda x: x['customer_group'])

			# Aggregate balances for each group
			result = [{"customer_group": key , "receipt" : f"""<button style='padding: 3px; margin:-5px' class= 'btn btn-primary' onClick='receipt("" , "" , "{key}")'>Receipt</button>""", "outstanding": sum(item['outstanding']  for item in group)} for key, group in grouped_data]
		else:
			result = self.data
		return self.columns,result

	# def get_data(self, args):
	# 	self.data = []

	# 	self.receivables = ReceivablePayableReport(self.filters).run(args)[1]
		

	# 	self.get_party_total(args)

	# 	party_advance_amount = (
	# 		get_partywise_advanced_payment_amount(
	# 			self.party_type,
	# 			self.filters.report_date,
	# 			self.filters.show_future_payments,
	# 			self.filters.company,
	# 		)
	# 		or {}
	# 	)

	# 	if self.filters.show_gl_balance:
	# 		gl_balance_map = get_gl_balance(self.filters.report_date)

	# 	for party, party_dict in iteritems(self.party_total):
	# 		# frappe.errprint(party_dict)
	# 		if party_dict.outstanding == 0:
	# 			continue

	# 		row = frappe._dict()

	# 		row.party = party
	# 		if self.party_naming_by == "Naming Series":
	# 			row.party_name = frappe.get_cached_value(
	# 				self.party_type, party, scrub(self.party_type) + "_name"
	# 			)
	# 		row.resonsible =frappe.db.get_value("Customer Credit Limit",{"parent":party},"responsible")
	# 		row.resonsible_date =frappe.db.get_value("Customer Credit Limit",{"parent":party},"date")
	# 		row.mobile_no = frappe.db.get_value("Patient",{"customer" : party},"mobile_no")
	# 		row.receipt	  =f"""<button style='padding: 3px; margin:-5px' class= 'btn btn-primary' onClick='receipt("{party}" , "{party_dict.outstanding}")'>Receipt</button>"""
	# 		row.statement =f"""<button style='padding: 3px; margin:-5px' class= 'btn btn-primary' onClick='statement("{party}")'>Statements</button>"""
	# 		row.update(party_dict)

	# 		# Advance against party
	# 		row.advance = party_advance_amount.get(party, 0)

	# 		# In AR/AP, advance shown in paid columns,
	# 		# but in summary report advance shown in separate column
	# 		row.paid 

	# 		if self.filters.show_gl_balance:
	# 			row.gl_balance = gl_balance_map.get(party)
	# 			row.diff = flt(row.outstanding) - flt(row.gl_balance)

	# 		self.data.append(row)

	def get_data(self, args):
		self.data = []

		# Run base report logic
		self.receivables = ReceivablePayableReport(self.filters).run(args)[1]

		self.get_party_total(args)

		# 🔄 Batch fetch responsible persons
		responsible_map = frappe._dict({
			r.parent: r.responsible
			for r in frappe.get_all("Customer Credit Limit", fields=["parent", "responsible"])
		})

		# 🔄 Batch fetch mobile numbers
		patient_info_map = frappe._dict({
			r.customer: {"mobile_no": r.mobile_no, "name": r.name}
			for r in frappe.get_all("Patient", fields=["customer", "mobile_no", "name"])
		})

		# 🔄 Optional: batch fetch customer names if using naming series
		if self.party_naming_by == "Naming Series":
			party_name_map = frappe._dict({
				r.name: r.customer_name
				for r in frappe.get_all("Customer", fields=["name", "customer_name"])
			})

		# ✅ Advanced payments - Using our custom implementation to avoid SQL errors
		party_advance_amount = get_customer_advance_amount(
			self.party_type,
			self.filters.report_date,
			cint(self.filters.show_future_payments) if hasattr(self.filters, 'show_future_payments') else 0,
			self.filters.company,
		) or {}

		# ✅ GL balance map
		if self.filters.show_gl_balance:
			gl_balance_map = get_gl_balance(self.filters.report_date)

		for party, party_dict in iteritems(self.party_total):
			if round(party_dict.outstanding, 10) == 0:
				continue

			row = frappe._dict()
			row.party = party

			# ✅ Faster: use pre-fetched customer name
			if self.party_naming_by == "Naming Series":
				row.party_name = party_name_map.get(party)

			# ✅ Use batched values
			row.resonsible = responsible_map.get(party)
			# row.mobile_no = patient_info_map.get(party)
			row.mobile_no = patient_info_map.get(party, {}).get("mobile_no")
			row.patient = patient_info_map.get(party, {}).get("name")

			# Inline buttons
			row.receipt	  =f"""<button style='padding: 3px; margin:-5px' class= 'btn btn-primary' onClick='receipt("{party}" , "{party_dict.outstanding}")'>Receipt</button>"""
			row.statement =f"""<button style='padding: 3px; margin:-5px' class= 'btn btn-primary' onClick='statement("{party}")'>Statements</button>"""

			row.update(party_dict)
			row.advance = party_advance_amount.get(party, 0)
			_ = row.paid  # dummy read

			if self.filters.show_gl_balance:
				row.gl_balance = gl_balance_map.get(party)
				row.diff = flt(row.outstanding) - flt(row.gl_balance)

			self.data.append(row)


	def get_party_total(self, args):
		self.party_total = frappe._dict()

		for d in self.receivables:
			self.init_party_total(d)

			# Add all amount columns
			for k in list(self.party_total[d.party]):
				if k not in ["currency", "sales_person"]:

					self.party_total[d.party][k] += d.get(k, 0.0)

			# set territory, customer_group, sales person etc
			self.set_party_details(d)

	def init_party_total(self, row):
		self.party_total.setdefault(
			row.party,
			frappe._dict(
				{
					"invoiced": 0.0,
					"paid": 0.0,
					"credit_note": 0.0,
					"outstanding": 0.0,
					
					"range1": 0.0,
					"range2": 0.0,
					"range3": 0.0,
					"range4": 0.0,
					"range5": 0.0,
					"total_due": 0.0,
					"sales_person": [],
				}
			),
		)

	def set_party_details(self, row):
		self.party_total[row.party].currency = row.currency

		for key in ("territory", "customer_group", "supplier_group"):
			if row.get(key):
				self.party_total[row.party][key] = row.get(key)

		if row.sales_person:
			self.party_total[row.party].sales_person.append(row.sales_person)

	def get_columns(self):
		self.columns = []
		self.add_column(
			label=_("Customer ID"),
			fieldname="party",
			fieldtype="Link",
			options=self.party_type,
			width=180,
		)

		if self.party_naming_by == "Naming Series":
			self.add_column(_("{0} Name").format(self.party_type), fieldname="party_name", fieldtype="Data" , width = 200)
		self.add_column(_("Patient ID"), fieldname="patient", fieldtype="Data")
		self.add_column(_("Mobile No"), fieldname="mobile_no", fieldtype="Data")
		self.add_column(
				label=_("Customer Group"),
				fieldname="customer_group",
				fieldtype="Link",
				options="Customer Group",
				width = 150
			)
		self.add_column(_("Responsible"), fieldname="resonsible", fieldtype="Data")
		# self.add_column(_("Responsible Date"), fieldname="resonsible_date", fieldtype="Data")
		
		
		credit_debit_label = "Return" if self.party_type == "Customer" else "Debit Note"

		# self.add_column(_("Advance A mount"), fieldname="advance")
		# self.add_column(_("Invoiced Amount"), fieldname="invoiced")
		# self.add_column(_("Paid Amount"), fieldname="paid")
		# self.add_column(_(credit_debit_label), fieldname="credit_note")
		self.add_column(_("Balance"), fieldname="outstanding")
		self.add_column(_("Receipt"), fieldname="receipt" , fieldtype="Data")
		self.add_column(_("Print Statement"), fieldname="statement" , fieldtype="Data")

		if self.filters.show_gl_balance:
			self.add_column(_("GL Balance"), fieldname="gl_balance")
			self.add_column(_("Difference"), fieldname="diff")

		# self.setup_ageing_columns()

		if self.party_type == "Customer":
			# self.add_column(
			# 	label=_("Territory"), fieldname="territory", fieldtype="Link", options="Territory"
			# )
			# self.add_column(
			# 	label=_("Customer Group"),
			# 	fieldname="customer_group",
			# 	fieldtype="Link",
			# 	options="Customer Group",
			# )
			if self.filters.show_sales_person:
				self.add_column(label=_("Sales Person"), fieldname="sales_person", fieldtype="Data")
		else:
			self.add_column(
				label=_("Supplier Group"),
				fieldname="supplier_group",
				fieldtype="Link",
				options="Supplier Group",
			)

		# self.add_column(
		# 	label=_("Currency"), fieldname="currency", fieldtype="Link", options="Currency", width=80
		# )

	def setup_ageing_columns(self):
		for i, label in enumerate(
			[
				"0-{range1}".format(range1=self.filters["range1"]),
				"{range1}-{range2}".format(
					range1=cint(self.filters["range1"]) + 1, range2=self.filters["range2"]
				),
				"{range2}-{range3}".format(
					range2=cint(self.filters["range2"]) + 1, range3=self.filters["range3"]
				),
				"{range3}-{range4}".format(
					range3=cint(self.filters["range3"]) + 1, range4=self.filters["range4"]
				),
				"{range4}-{above}".format(range4=cint(self.filters["range4"]) + 1, above=_("Above")),
			]
		):
			self.add_column(label=label, fieldname="range" + str(i + 1))

		# Add column for total due amount
		self.add_column(label="Total Amount Due", fieldname="total_due")


def get_gl_balance(report_date):
	return frappe._dict(
		frappe.db.get_all(
			"GL Entry",
			fields=["party", "sum(debit -  credit)"],
			filters={"posting_date": ("<=", report_date), "is_cancelled": 0},
			group_by="party",
			as_list=1,
		)
	)

def get_customer_advance_amount(party_type, report_date, show_future_payments=False, company=None):
	"""
	Custom implementation to get advance payment amounts specifically for Customers only.
	This avoids the SQL error by not referencing Purchase Invoice's customer field
	"""
	if party_type != "Customer":
		return {}
		
	party_advance_amount = {}
	
	order_list = frappe.db.sql("""
		SELECT
			pe.party, sum(pe.unallocated_amount) as amount
		FROM `tabPayment Entry` as pe
		WHERE
			pe.party_type = %(party_type)s
			AND pe.docstatus = 1
			AND pe.company = %(company)s
			AND pe.posting_date <= %(report_date)s
		GROUP BY pe.party
		HAVING amount > 0
	""", {
		'party_type': party_type,
		'company': company,
		'report_date': report_date
	}, as_dict=1)

	for d in order_list:
		party_advance_amount.setdefault(d.party, d.amount)

	# Add amounts from sales invoices with advances
	invoice_advance = frappe.db.sql("""
		SELECT
			customer as party, sum(advance_amount) as amount
		FROM `tabSales Invoice`
		WHERE
			docstatus = 1
			AND company = %(company)s
			AND posting_date <= %(report_date)s
			AND advance_amount > 0
		GROUP BY customer
		HAVING amount > 0
	""", {
		'company': company,
		'report_date': report_date
	}, as_dict=1)

	for d in invoice_advance:
		if d.party in party_advance_amount:
			party_advance_amount[d.party] += d.amount
		else:
			party_advance_amount[d.party] = d.amount
			
	return party_advance_amount
