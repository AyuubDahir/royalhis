

// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Custom Account Receivable Summary"] = {
	"filters": [
		{
			"fieldname":"company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company")
		},
		{
			"fieldname":"report_date",
			"label": __("Posting Date"),
			"fieldtype": "Date",
			"default": frappe.datetime.get_today(),
			"hidden": 0,
		},
		{
			"fieldname":"ageing_based_on",
			"label": __("Ageing Based On"),
			"fieldtype": "Select",
			"options": 'Posting Date\nDue Date',
			"default": "Due Date",
			"hidden": 1,
			
		},
		{
			"fieldname":"range1",
			"label": __("Ageing Range 1"),
			"fieldtype": "Int",
			"default": "30",
			"reqd": 1,
			"hidden": 1
		},
		{
			"fieldname":"range2",
			"label": __("Ageing Range 2"),
			"fieldtype": "Int",
			"default": "60",
			"reqd": 1,
			"hidden": 1
		},
		{
			"fieldname":"range3",
			"label": __("Ageing Range 3"),
			"fieldtype": "Int",
			"default": "90",
			"reqd": 1,
			"hidden": 1
		},
		{
			"fieldname":"range4",
			"label": __("Ageing Range 4"),
			"fieldtype": "Int",
			"default": "120",
			"reqd": 1,
			"hidden": 1
		},
		{
			"fieldname":"finance_book",
			"label": __("Finance Book"),
			"fieldtype": "Link",
			"options": "Finance Book",
			"hidden": 1
		},
		{
			"fieldname":"cost_center",
			"label": __("Cost Center"),
			"fieldtype": "Link",
			"hidden": 0,
			"options": "Cost Center",
			get_query: () => {
				var company = frappe.query_report.get_filter_value('company');
				return {
					filters: {
						'company': company
					}
				}
			}
		},
		{
			"fieldname":"customer",
			"label": __("Customer"),
			"fieldtype": "Link",
			"options": "Customer"
		},
		{
			"fieldname":"customer_group",
			"label": __("Debtor"),
			"fieldtype": "Link",
			"options": "Customer Group",
			// "hidden":1
		},
		{
			"fieldname":"based_by",
			"label": __("By"),
			"fieldtype": "Select",
			"options": ["Patient" , "Debtor"],
			// "hidden":1
		},
		{
			"fieldname":"payment_terms_template",
			"label": __("Payment Terms Template"),
			"fieldtype": "Link",
			"hidden": 1,
			"options": "Payment Terms Template"
		},
		{
			"fieldname":"territory",
			"label": __("Territory"),
			"fieldtype": "Link",
			"hidden": 1,
			"options": "Territory"
		},
		{
			"fieldname":"sales_partner",
			"label": __("Sales Partner"),
			"fieldtype": "Link",
			"hidden": 1,
			"options": "Sales Partner"
		},
		{
			"fieldname":"sales_person",
			"label": __("Sales Person"),
			"fieldtype": "Link",
			"hidden": 1,
			"options": "Sales Person"
		},
		{
			"fieldname":"based_on_payment_terms",
			"label": __("Based On Payment Terms"),
			"fieldtype": "Check",
			"hidden": 1,
		},
		{
			"fieldname":"show_future_payments",
			"label": __("Show Future Payments"),
			"fieldtype": "Check",
			"hidden": 1,
		},
		{
			"fieldname": "party_account",
			"label": __("Receivable Account"),
			"fieldtype": "Link",
			"options": "Account",
			"hidden" : 1,
			get_query: () => {
				var company = frappe.query_report.get_filter_value('company');
				return {
					filters: {
						'company': company,
						'account_type': 'Receivable',
						'is_group': 0
					}
				};
			}
		},
		{
			"fieldname":"show_gl_balance",
			"label": __("Show GL Balance"),
			"fieldtype": "Check",
			"hidden": 1
		},
		{
			"fieldname": "page_length",
			"label": __('Page Size'),
			"fieldtype": "Select",
			"options": ["20", "50", "100", "200"],
			"default": "20"
		},
		{
			"fieldname": "start",
			"label": __('Start'),
			"fieldtype": "Int",
			"default": 0,
			"hidden": 1
		}
	],

	onload: function(report) {
		// Add navigation buttons
		report.page.add_inner_button(__('Previous Page'), function() {
			const filters = report.get_values();
			const start = parseInt(filters.start || 0);
			const page_length = parseInt(filters.page_length || 20);
			
			if (start >= page_length) {
				frappe.query_report.set_filter_value('start', start - page_length);
				frappe.query_report.refresh();
			} else {
				frappe.msgprint(__('You are on the first page'));
			}
		});
		
		report.page.add_inner_button(__('Next Page'), function() {
			const filters = report.get_values();
			const start = parseInt(filters.start || 0);
			const page_length = parseInt(filters.page_length || 20);
			
			// Get total count from the response in __frappe_request_cache__
			// Get pagination info from custom_info (5th element in the response array)
			let total_count = 0;
			let current_page = 1;
			let page_count = 1;
			
			if (frappe.query_report.report_settings && frappe.query_report.report_settings.custom_info) {
				total_count = frappe.query_report.report_settings.custom_info.total_count || 0;
				current_page = frappe.query_report.report_settings.custom_info.current_page || 1;
				page_count = frappe.query_report.report_settings.custom_info.page_count || 1;
			}
			
			if (start + page_length < total_count) {
				frappe.query_report.set_filter_value('start', start + page_length);
				frappe.query_report.refresh();
			} else {
				frappe.msgprint(__('You are on the last page'));
			}
		});
		
		// Reset pagination when filters change
		report.page.add_menu_item(__('Reset Pagination'), function() {
			frappe.query_report.set_filter_value('start', 0);
			frappe.query_report.refresh();
		});
		
		// Add pagination info display
		// Create or get pagination info element
		let $pagination_info = $('#pagination-info');
		if (!$pagination_info.length) {
			$pagination_info = $('<div id="pagination-info" style="margin-left: 10px; display: inline-block; color: #6c7680;"></div>');
			report.page.page_form.append($pagination_info);
		}
		
		// Update pagination info on report refresh
		report.page.wrapper.on('show', function() {
			setTimeout(function() {
				const filters = frappe.query_report.get_values();
				const start = parseInt(filters.start || 0);
				const page_length = parseInt(filters.page_length || 20);
				
				// Get pagination info from custom_info
				let total_count = 0;
				let current_page = 1;
				let total_pages = 1;
				
				if (frappe.query_report.report_settings && frappe.query_report.report_settings.custom_info) {
					total_count = frappe.query_report.report_settings.custom_info.total_count || 0;
					current_page = frappe.query_report.report_settings.custom_info.current_page || 1;
					total_pages = frappe.query_report.report_settings.custom_info.page_count || 1;
				} else {
					// Fallback to calculated values
					current_page = Math.floor(start / page_length) + 1;
				}
				
				if (total_count > 0) {
					$pagination_info.html(`Showing page ${current_page} of ${total_pages} (${total_count} records)`);
					$pagination_info.show();
				} else {
					$pagination_info.html('No records found');
					$pagination_info.show();
				}
			}, 300); // Short delay to ensure report data is loaded
		});
	}
}

erpnext.utils.add_dimensions('Account Receivable Summary', 9);
