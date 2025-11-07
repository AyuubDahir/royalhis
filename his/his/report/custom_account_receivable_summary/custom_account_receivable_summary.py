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
		# Import time for performance logging only
		import time
		start_time = time.time()
		
		# Basic setup
		self.party_type = args.get("party_type")
		self.party_naming_by = frappe.db.get_value(
			args.get("naming_by")[0], None, args.get("naming_by")[1]
		)
		self.get_columns()
		
		# Get pagination parameters
		self.page_length = 20  # Default page size
		if hasattr(self.filters, 'page_length') and self.filters.page_length:
			self.page_length = int(self.filters.page_length)
		
		self.start = 0
		if hasattr(self.filters, 'start') and self.filters.start:
			self.start = int(self.filters.start)

		# Get data with pagination support
		self.get_data(args)
		
		result = []
		if hasattr(self.filters, 'based_by') and self.filters.based_by == "Debtor":
			# Optimized grouping using defaultdict for better performance
			from collections import defaultdict
			
			# Use dictionary aggregation instead of groupby for better performance
			aggregated = defaultdict(float)
			for row in self.data:
				if 'customer_group' in row and row['customer_group']:
					aggregated[row['customer_group']] += row.get('outstanding', 0)
			
			# Create the result list in one go
			result = [
				{"customer_group": key, 
				"receipt": f"<button style='padding:3px;margin:-5px' class='btn btn-primary' onClick='receipt(\"\", \"\", \"{key}\")'>Receipt</button>", 
				"outstanding": value} 
				for key, value in aggregated.items()
			]
			
			# Sort once at the end
			result.sort(key=lambda x: x["customer_group"])
			
			# Apply pagination to grouped data
			total_count = len(result)
			result = result[self.start:self.start + self.page_length]
			
			# Add pagination info to the result
			frappe.response["total_count"] = total_count
			frappe.response["page_count"] = total_count // self.page_length + (1 if total_count % self.page_length else 0)
		else:
			result = self.data
			
		# Log performance metrics
		exec_time = round(time.time() - start_time, 2)
		if exec_time > 1.0:  # Only log if it took more than 1 second
			frappe.log_error(f"Custom AR Summary took {exec_time}s to execute", "Performance Log")
		
		return self.columns, result

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
		
		# Run base report logic with optimized query
		self.receivables = ReceivablePayableReport(self.filters).run(args)[1]
		self.get_party_total(args)
		
		# Get count for pagination
		total_parties = sum(1 for _, party_dict in iteritems(self.party_total) 
						if round(party_dict.outstanding, 10) != 0)
		
		# Store total count for pagination
		frappe.response["total_count"] = total_parties
		frappe.response["page_count"] = total_parties // (self.page_length or 20) + \
								(1 if total_parties % (self.page_length or 20) else 0)

		# Get all parties for efficient batch fetching
		parties = list(self.party_total.keys())
		
		# Early exit if no data
		if not parties:
			return

		# 🚀 OPTIMIZED: Batch fetch responsible persons with IN clause
		responsible_records = frappe.get_all(
			"Customer Credit Limit", 
			fields=["parent", "responsible"],
			filters={"parent": ["in", parties]}
		)
		responsible_map = frappe._dict({
			r.parent: r.responsible for r in responsible_records
		})

		# 🚀 OPTIMIZED: Batch fetch patient info with IN clause
		patient_records = frappe.get_all(
			"Patient", 
			fields=["customer", "mobile_no", "name"],
			filters={"customer": ["in", parties]}
		)
		patient_info_map = frappe._dict({
			r.customer: {"mobile_no": r.mobile_no, "name": r.name}
			for r in patient_records
		})

		# Optional: batch fetch customer names with filtered query
		party_name_map = {}
		if self.party_naming_by == "Naming Series":
			customer_records = frappe.get_all(
				"Customer", 
				fields=["name", "customer_name"],
				filters={"name": ["in", parties]}
			)
			party_name_map = frappe._dict({
				r.name: r.customer_name for r in customer_records
			})

		# ✅ Advanced payments - Using our custom implementation to avoid SQL errors
		party_advance_amount = get_customer_advance_amount(
			self.party_type,
			self.filters.report_date,
			cint(self.filters.show_future_payments) if hasattr(self.filters, 'show_future_payments') else 0,
			self.filters.company,
		) or {}

		# ✅ GL balance map - load only if needed
		gl_balance_map = {}
		if self.filters.show_gl_balance:
			gl_balance_map = get_gl_balance(self.filters.report_date)
		
		# Use list comprehension first to filter data
		eligible_parties = [(party, party_dict) for party, party_dict in iteritems(self.party_total) 
							if round(party_dict.outstanding, 10) != 0]
		
		# Sort if needed
		eligible_parties.sort(key=lambda x: x[0])  # Sort by party name for consistent results
		
		# Apply pagination to the eligible parties list
		start = getattr(self, 'start', 0)
		page_length = getattr(self, 'page_length', 20)
		eligible_parties_paged = eligible_parties[start:start+page_length]
		
		# Pre-allocate memory for results
		self.data = [None] * len(eligible_parties_paged)
		
		# Process only paginated data
		for i, (party, party_dict) in enumerate(eligible_parties_paged):
			# Create row with only necessary fields
			row = frappe._dict({
				"party": party,
				"party_name": party_name_map.get(party) if self.party_naming_by == "Naming Series" else None,
				"resonsible": responsible_map.get(party),
				"mobile_no": patient_info_map.get(party, {}).get("mobile_no"),
				"patient": patient_info_map.get(party, {}).get("name"),
				"receipt": f"<button style='padding:3px;margin:-5px' class='btn btn-primary' onClick='receipt(\"{party}\", \"{party_dict.outstanding}\")'>Receipt</button>",
				"statement": f"<button style='padding:3px;margin:-5px' class='btn btn-primary' onClick='statement(\"{party}\")'>Statements</button>",
				"advance": party_advance_amount.get(party, 0)
			})
			
			# Update with party dict values in one go
			row.update(party_dict)

			# Conditionally add GL balance info
			if self.filters.show_gl_balance:
				row.gl_balance = gl_balance_map.get(party)
				row.diff = flt(row.outstanding) - flt(row.gl_balance)

			# Direct assignment to pre-allocated list is faster than append
			self.data[i] = row


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
	# Optimize query with index hints but no caching
	result = frappe.db.sql("""
		SELECT 
			party, SUM(debit - credit) as balance
		FROM `tabGL Entry` USE INDEX (posting_date)
		WHERE 
			posting_date <= %s 
			AND is_cancelled = 0
			AND party IS NOT NULL
		GROUP BY party
		HAVING balance != 0
	""", report_date, as_list=1)
	
	return frappe._dict(result)

def get_customer_advance_amount(party_type, report_date, show_future_payments=False, company=None):
	"""
	Optimized implementation to get advance payment amounts specifically for Customers only.
	Uses optimized queries for better performance without caching.
	"""
	# Early exit for non-customer party types
	if party_type != "Customer":
		return {}
	
	# Optimized query with index hints and no subqueries
	order_list = frappe.db.sql("""
		SELECT
			pe.party, sum(pe.unallocated_amount) as amount
		FROM `tabPayment Entry` pe USE INDEX (posting_date, company)
		WHERE
			pe.party_type = %(party_type)s
			AND pe.docstatus = 1
			AND pe.company = %(company)s
			AND pe.posting_date <= %(report_date)s
			AND pe.unallocated_amount > 0
		GROUP BY pe.party
		HAVING amount > 0
	""", {
		'party_type': party_type,
		'company': company,
		'report_date': report_date
	}, as_dict=1)

	# Process results efficiently with a dict comprehension
	party_advance_amount = frappe._dict({
		d.party: d.amount for d in order_list if d.amount > 0
	})
			
	return party_advance_amount
