"""Master data for the Ombak Metal Works demo. Every step is idempotent: safe to run again."""

import frappe
from frappe.utils import add_years, get_first_day, getdate, nowdate

COMPANY = "Ombak Metal Works Sdn Bhd"
ABBR = "OMW"
DEMO_PASSWORD = "Ombak@2026"  # local demo only, documented in the README

# workstation: (labour MYR/h, machine and power MYR/h, operation it performs)
WORKSTATIONS = {
	"Laser Cutting": (40, 140, "Laser Cutting"),
	"CNC Press Brake": (40, 80, "Press Brake Bending"),
	"Welding Bay": (55, 40, "Welding"),
	"Powder Coating": (45, 65, "Powder Coating"),
}

# code: (name, uom, valuation rate MYR, needs incoming inspection)
RAW_MATERIALS = {
	"RM-MS-PL3": ("MS Plate 3mm 4x8ft", "Sheet", 420, True),
	"RM-MS-PL5": ("MS Plate 5mm 4x8ft", "Sheet", 690, True),
	"RM-GI-SH12": ("GI Sheet 1.2mm 4x8ft", "Sheet", 165, True),
	"RM-GI-SH20": ("GI Sheet 2.0mm 4x8ft", "Sheet", 260, True),
	"RM-ANG-50": ("Angle Bar 50x50x5mm 6m", "Bar", 95, False),
	"RM-FLT-40": ("Flat Bar 40x6mm 6m", "Bar", 48, False),
	"RM-RHS-50": ("RHS 50x50x3mm 6m", "Bar", 140, False),
	"RM-WW-08": ("Welding Wire ER70S-6 0.8mm", "Kg", 9.5, False),
	"RM-PP-GRY": ("Powder Paint RAL7035 Light Grey", "Kg", 28, False),
	"RM-BN-M10": ("Bolt and Nut Set M10", "Nos", 0.85, False),
}

# code: (name, selling rate MYR, [(raw material, qty per unit)], [(workstation, minutes per unit)])
FINISHED_GOODS = {
	"FG-CT-300": (
		"Cable Tray 300mm x 2.4m",
		85,
		[("RM-GI-SH12", 0.25), ("RM-BN-M10", 4)],
		[("Laser Cutting", 6), ("CNC Press Brake", 8)],
	),
	"FG-MG-1200": (
		"Machine Guard Panel 1200x1000",
		520,
		[("RM-MS-PL3", 0.4), ("RM-FLT-40", 0.7), ("RM-WW-08", 0.2), ("RM-PP-GRY", 0.6)],
		[("Laser Cutting", 12), ("CNC Press Brake", 10), ("Welding Bay", 25), ("Powder Coating", 15)],
	),
	"FG-WB-150": (
		"Wall Bracket 150mm",
		18,
		[("RM-MS-PL5", 0.03), ("RM-BN-M10", 2), ("RM-PP-GRY", 0.05)],
		[("Laser Cutting", 2), ("CNC Press Brake", 3), ("Powder Coating", 2)],
	),
	"FG-PR-UP3": (
		"Pallet Rack Upright 3m",
		310,
		[("RM-GI-SH20", 0.5), ("RM-BN-M10", 6), ("RM-PP-GRY", 0.4)],
		[("Laser Cutting", 10), ("CNC Press Brake", 12), ("Welding Bay", 8), ("Powder Coating", 10)],
	),
	"FG-EBF-1000": (
		"Equipment Base Frame 1000x800",
		1450,
		[("RM-RHS-50", 1.2), ("RM-ANG-50", 0.5), ("RM-MS-PL5", 0.1), ("RM-WW-08", 0.6), ("RM-PP-GRY", 0.8)],
		[("Laser Cutting", 15), ("Welding Bay", 60), ("Powder Coating", 20)],
	),
}

# customer: (territory, shipping address: line 1, city, state, postcode, country)
CUSTOMERS = {
	"Tanjung Electrical Contractors Sdn Bhd": (
		"Johor", ("Lot 12, Jalan Industri 3", "Johor Bahru", "Johor", "81100", "Malaysia"),
	),
	"Kulai Food Processing Sdn Bhd": (
		"Johor", ("No. 8, Jalan Kilang 5", "Kulai", "Johor", "81000", "Malaysia"),
	),
	"Seri Alam Logistics Sdn Bhd": (
		"Johor", ("Lot 40, Jalan Gudang 2", "Pasir Gudang", "Johor", "81700", "Malaysia"),
	),
	"Mutiara Automation Sdn Bhd": (
		"Selangor", ("No. 15, Jalan Perusahaan 7", "Shah Alam", "Selangor", "40150", "Malaysia"),
	),
	"Harbourline Packaging Pte Ltd": (
		"Singapore", ("21 Industrial Avenue 6", "Singapore", "", "637021", "Singapore"),
	),
}  # fmt: skip

SUPPLIERS = {
	"Lintang Steel Supply Sdn Bhd": "Raw Material",
	"Wirafast Industrial Supplies Sdn Bhd": "Hardware",
	"Chromacoat Powder Coatings Sdn Bhd": "Raw Material",
}

# template: [(parameter, numeric, min, max, text value)]
QI_TEMPLATES = {
	"Incoming Steel": [
		("Thickness Deviation (mm)", 1, -0.2, 0.2, None),
		("Surface Condition", 0, None, None, "No rust, no dents"),
	],
	"Final Inspection": [
		("Dimension Deviation (mm)", 1, -1.0, 1.0, None),
		("Coating Thickness (micron)", 1, 60, 120, None),
		("Visual Check", 0, None, None, "No scratches, no weld spatter"),
	],
}

# code: (category, description)
DEFECT_REASONS = {
	"BURR": ("Cutting", "Burr or sharp edge left after laser cutting"),
	"HOLE-POS": ("Cutting", "Hole position outside drawing tolerance"),
	"DIM-OOT": ("Forming", "Bend angle or dimension out of tolerance"),
	"WELD-POR": ("Welding", "Weld porosity or pinholes"),
	"WELD-DIST": ("Welding", "Distortion after welding"),
	"COAT-PEEL": ("Coating", "Powder coat peeling or poor adhesion"),
	"COAT-THIN": ("Coating", "Coating thickness below specification"),
	"SCRATCH": ("Handling", "Scratch or dent during handling"),
	"MAT-DEF": ("Material", "Material defect: rust pitting or lamination"),
}

USERS = {
	"lim.weijie@ombakmetal.example": (
		"Lim Wei Jie",
		["Manufacturing Manager", "Manufacturing User", "Stock User", "Quality Manager"],
	),
	"siti.aminah@ombakmetal.example": ("Siti Aminah", ["Manufacturing User", "Stock User"]),
}


def setup_masters():
	_complete_setup_wizard()
	_fiscal_years()
	_holiday_list()
	_warehouses()
	_settings()
	_workstations_and_operations()
	_territories()
	_qi_templates()
	_items()
	_boms()
	_parties()
	_transport()
	_users()
	_defect_reasons()
	frappe.db.commit()


def _ensure(doctype, name, values, submit=False):
	"""Insert the document unless a record with this name already exists."""
	if frappe.db.exists(doctype, name):
		return frappe.get_doc(doctype, name)
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc


def _complete_setup_wizard():
	if frappe.is_setup_complete():
		return
	from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

	year_start = get_first_day(nowdate()).replace(month=1)
	result = setup_complete(
		{
			"language": "English",
			"country": "Malaysia",
			"timezone": "Asia/Kuala_Lumpur",
			"currency": "MYR",
			"full_name": "Ombak Admin",
			"email": "admin@ombakmetal.example",
			"password": DEMO_PASSWORD,
			"company_name": COMPANY,
			"company_abbr": ABBR,
			"chart_of_accounts": "Standard",
			"fy_start_date": str(year_start),
			"fy_end_date": str(year_start.replace(month=12, day=31)),
			"enable_telemetry": 0,
		}
	)
	if not frappe.is_setup_complete():
		frappe.throw(f"Setup wizard failed: {result}")


def _fiscal_years():
	# The wizard creates this year; the demo month can fall in last year when run in January.
	start = getdate(add_years(get_first_day(nowdate()).replace(month=1), -1))
	if not frappe.db.exists("Fiscal Year", {"year_start_date": start}):
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"year": str(start.year),
				"year_start_date": start,
				"year_end_date": start.replace(month=12, day=31),
			}
		).insert(ignore_permissions=True)


def _holiday_list():
	name = "Ombak Factory Calendar"
	if not frappe.db.exists("Holiday List", name):
		today = getdate(nowdate())
		doc = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": today.replace(year=today.year - 1, month=1, day=1),
				"to_date": today.replace(year=today.year + 1, month=12, day=31),
				"weekly_off": "Sunday",
			}
		)
		doc.get_weekly_off_dates()
		doc.insert(ignore_permissions=True)
	frappe.db.set_value("Company", COMPANY, "default_holiday_list", name)


def _warehouses():
	for wh in ("Raw Material", "Rejected"):
		_ensure(
			"Warehouse",
			f"{wh} - {ABBR}",
			{"warehouse_name": wh, "company": COMPANY, "parent_warehouse": f"All Warehouses - {ABBR}"},
		)


def _settings():
	frappe.db.set_single_value(
		"Manufacturing Settings",
		{
			"default_wip_warehouse": f"Work In Progress - {ABBR}",
			"default_fg_warehouse": f"Finished Goods - {ABBR}",
			"default_scrap_warehouse": f"Rejected - {ABBR}",
			"backflush_raw_materials_based_on": "BOM",
		},
	)
	frappe.db.set_single_value("Stock Settings", "default_warehouse", f"Raw Material - {ABBR}")
	# workstation costs are absorbed into finished-goods valuation on the Manufacture entry
	frappe.db.set_value(
		"Company", COMPANY, "default_operating_cost_account", f"Expenses Included In Valuation - {ABBR}"
	)


def _workstations_and_operations():
	for component in ("Labour", "Machine and Power"):
		_ensure("Workstation Operating Component", component, {"component_name": component})
	for ws, (labour, machine, operation) in WORKSTATIONS.items():
		_ensure(
			"Workstation",
			ws,
			{
				"workstation_name": ws,
				"holiday_list": "Ombak Factory Calendar",
				# 8 h a day with a lunch break
				"working_hours": [
					{"start_time": "08:00:00", "end_time": "12:00:00", "enabled": 1},
					{"start_time": "13:00:00", "end_time": "17:00:00", "enabled": 1},
				],
				"workstation_costs": [
					{"operating_component": "Labour", "operating_cost": labour},
					{"operating_component": "Machine and Power", "operating_cost": machine},
				],
			},
		)
		_ensure("Operation", operation, {"name": operation, "workstation": ws})


def _territories():
	for t in ("Johor", "Selangor", "Singapore"):
		_ensure("Territory", t, {"territory_name": t, "parent_territory": "All Territories"})


def _qi_templates():
	for template, params in QI_TEMPLATES.items():
		for p, *_ in params:
			_ensure("Quality Inspection Parameter", p, {"parameter": p})
		_ensure(
			"Quality Inspection Template",
			template,
			{
				"quality_inspection_template_name": template,
				"item_quality_inspection_parameter": [
					{"specification": p, "numeric": num, "min_value": lo, "max_value": hi, "value": text}
					for p, num, lo, hi, text in params
				],
			},
		)


def _items():
	# sheets and bars are consumed in fractions after nesting/cutting
	for uom in ("Sheet", "Bar"):
		_ensure("UOM", uom, {"uom_name": uom, "must_be_whole_number": 0})
	for code, (name, uom, rate, inspect) in RAW_MATERIALS.items():
		_ensure(
			"Item",
			code,
			{
				"item_code": code,
				"item_name": name,
				"item_group": "Raw Material",
				"stock_uom": uom,
				"is_stock_item": 1,
				"is_purchase_item": 1,
				"valuation_rate": rate,
				"inspection_required_before_purchase": int(inspect),
				"quality_inspection_template": "Incoming Steel" if inspect else None,
				"item_defaults": [{"company": COMPANY, "default_warehouse": f"Raw Material - {ABBR}"}],
			},
		)
		_item_price(code, "Standard Buying", rate)

	for code, (name, rate, _bom, _ops) in FINISHED_GOODS.items():
		_ensure(
			"Item",
			code,
			{
				"item_code": code,
				"item_name": name,
				"item_group": "Products",
				"stock_uom": "Nos",
				"is_stock_item": 1,
				"is_sales_item": 1,
				"is_purchase_item": 0,
				"inspection_required_before_delivery": 1,
				"quality_inspection_template": "Final Inspection",
				"item_defaults": [{"company": COMPANY, "default_warehouse": f"Finished Goods - {ABBR}"}],
			},
		)
		_item_price(code, "Standard Selling", rate)


def _item_price(item_code, price_list, rate):
	# Item Price defaults valid_from to today, which leaves back-dated demo orders at zero value
	valid_from = getdate(add_years(get_first_day(nowdate()).replace(month=1), -1))
	name = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list})
	if not name:
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
				"valid_from": valid_from,
			}
		).insert(ignore_permissions=True)
	elif getdate(frappe.db.get_value("Item Price", name, "valid_from")) > valid_from:
		frappe.db.set_value("Item Price", name, "valid_from", valid_from)


def _boms():
	for code, (_name, _rate, materials, operations) in FINISHED_GOODS.items():
		if frappe.db.get_value("Item", code, "default_bom"):
			continue
		bom = frappe.get_doc(
			{
				"doctype": "BOM",
				"item": code,
				"quantity": 1,
				"company": COMPANY,
				"currency": "MYR",
				"rm_cost_as_per": "Valuation Rate",
				"with_operations": 1,
				"is_default": 1,
				"items": [{"item_code": rm, "qty": qty} for rm, qty in materials],
				"operations": [
					{"operation": WORKSTATIONS[ws][2], "workstation": ws, "time_in_mins": mins}
					for ws, mins in operations
				],
			}
		)
		bom.insert(ignore_permissions=True)
		bom.submit()


def _parties():
	for name, (territory, (line1, city, state, postcode, country)) in CUSTOMERS.items():
		_ensure(
			"Customer",
			name,
			{
				"customer_name": name,
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": territory,
			},
		)
		if not frappe.db.exists(
			"Dynamic Link", {"parenttype": "Address", "link_doctype": "Customer", "link_name": name}
		):
			frappe.get_doc(
				{
					"doctype": "Address",
					"address_title": name,
					"address_type": "Shipping",
					"address_line1": line1,
					"city": city,
					"state": state,
					"pincode": postcode,
					"country": country,
					"is_shipping_address": 1,
					"is_primary_address": 1,
					"links": [{"link_doctype": "Customer", "link_name": name}],
				}
			).insert(ignore_permissions=True)
	for name, group in SUPPLIERS.items():
		_ensure("Supplier", name, {"supplier_name": name, "supplier_group": group})


def _transport():
	if not frappe.db.exists("Driver", {"full_name": "Rahim bin Osman"}):
		frappe.get_doc(
			{"doctype": "Driver", "full_name": "Rahim bin Osman", "status": "Active", "cell_number": "012-000 0000"}
		).insert(ignore_permissions=True)
	_ensure(
		"Vehicle",
		"JTA 8821",
		{
			"license_plate": "JTA 8821",
			"make": "Isuzu",
			"model": "NPR 3-tonne lorry",
			"last_odometer": 84210,
			"fuel_type": "Diesel",
			"uom": "Litre",
		},
	)


def _users():
	for email, (full_name, roles) in USERS.items():
		if frappe.db.exists("User", email):
			continue
		first, last = full_name.split(" ", 1)
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": first,
				"last_name": last,
				"send_welcome_email": 0,
				"new_password": DEMO_PASSWORD,
			}
		)
		user.append_roles(*roles)
		user.insert(ignore_permissions=True)


def _defect_reasons():
	for code, (category, description) in DEFECT_REASONS.items():
		_ensure(
			"Defect Reason", code, {"reason_code": code, "category": category, "description": description}
		)
