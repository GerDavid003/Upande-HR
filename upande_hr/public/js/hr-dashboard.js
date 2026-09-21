(function () {
	"use strict";

	var PAGE_LENGTH = 50;
	var state = { start: 0, filters: {} };

	function esc(value) {
		if (value === null || value === undefined) return "";
		return String(value)
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;");
	}

	function dash(value) {
		return value ? esc(value) : "–";
	}

	function formatDate(value) {
		if (!value) return "–";
		var d = new Date(value);
		if (isNaN(d.getTime())) return esc(value);
		return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
	}

	function statusPill(status) {
		var cls = "status-" + String(status || "").toLowerCase();
		return '<span class="pill ' + cls + '">' + esc(status) + "</span>";
	}

	function apiCall(method, params) {
		var query = Object.keys(params || {})
			.filter(function (k) { return params[k] !== undefined && params[k] !== null && params[k] !== ""; })
			.map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); })
			.join("&");
		var url = "/api/method/upande_hr.api.hr_dashboard." + method + (query ? "?" + query : "");
		return fetch(url, { headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" } })
			.then(function (res) {
				if (!res.ok) throw new Error("Request failed: " + res.status);
				return res.json();
			})
			.then(function (body) { return body.message; });
	}

	function populateSelect(select, options, placeholder) {
		var current = select.value;
		select.innerHTML = "";
		var placeholderOpt = document.createElement("option");
		placeholderOpt.value = "";
		placeholderOpt.textContent = placeholder;
		select.appendChild(placeholderOpt);
		options.forEach(function (opt) {
			var el = document.createElement("option");
			el.value = opt;
			el.textContent = opt;
			select.appendChild(el);
		});
		if (options.indexOf(current) !== -1) select.value = current;
	}

	function renderKPIs(kpis) {
		var genderLabel = (kpis.gender_breakdown || [])
			.map(function (row) { return esc(row.gender) + " " + row.count; })
			.join(" · ") || "–";
		var grid = document.getElementById("kpi-grid");
		grid.innerHTML = [
			['Total Employees', kpis.total],
			['Active', kpis.active],
			['Left / Inactive', kpis.left_or_inactive],
			['Gender Split', genderLabel],
		].map(function (pair) {
			return '<div class="kpi"><div class="kpi__label">' + esc(pair[0]) +
				'</div><div class="kpi__value">' + pair[1] + "</div></div>";
		}).join("");
	}

	function renderRow(emp) {
		return "<tr>" +
			"<td>" + dash(emp.employee_number) + "</td>" +
			'<td><a class="rowlink" target="_blank" rel="noopener" href="/app/employee/' +
				encodeURIComponent(emp.name) + '">' + esc(emp.employee_name) + "</a></td>" +
			"<td>" + dash(emp.gender) + "</td>" +
			"<td>" + dash(emp.employee_category) + "</td>" +
			"<td>" + dash(emp.employment_type) + "</td>" +
			"<td>" + dash(emp.designation) + "</td>" +
			"<td>" + dash(emp.department) + "</td>" +
			"<td>" + dash(emp.custom_farm) + "</td>" +
			"<td>" + formatDate(emp.date_of_joining) + "</td>" +
			"<td>" + statusPill(emp.status) + "</td>" +
			"<td>" + dash(emp.company) + "</td>" +
			"<td>" + dash(emp.shift) + "</td>" +
			"<td>" + dash(emp.week_off) + "</td>" +
			"<td>" + dash(emp.national_id) + "</td>" +
			"<td>" + dash(emp.tax_id) + "</td>" +
			"<td>" + dash(emp.sha_no) + "</td>" +
			"<td>" + dash(emp.nssf_no) + "</td>" +
			"</tr>";
	}

	function renderTable(data) {
		var tbody = document.getElementById("roster-tbody");
		var empty = document.getElementById("roster-empty");
		if (!data.employees.length) {
			tbody.innerHTML = "";
			empty.style.display = "block";
		} else {
			empty.style.display = "none";
			tbody.innerHTML = data.employees.map(renderRow).join("");
		}
		document.getElementById("page-sub").textContent = data.total.toLocaleString() + " employees";
		var from = data.total === 0 ? 0 : state.start + 1;
		var to = Math.min(state.start + PAGE_LENGTH, data.total);
		document.getElementById("pagination-label").textContent = from + "–" + to + " of " + data.total.toLocaleString();
		document.getElementById("pagination-prev").disabled = state.start === 0;
		document.getElementById("pagination-next").disabled = to >= data.total;
	}

	function loadData() {
		var params = Object.assign({ start: state.start, page_length: PAGE_LENGTH }, state.filters);
		apiCall("get_dashboard_data", params).then(function (data) {
			renderKPIs(data.kpis);
			renderTable(data);
		});
	}

	function debounce(fn, wait) {
		var timer;
		return function () {
			var args = arguments;
			clearTimeout(timer);
			timer = setTimeout(function () { fn.apply(null, args); }, wait);
		};
	}

	function onFilterChange() {
		state.start = 0;
		state.filters = {
			company: document.getElementById("filter-company").value,
			department: document.getElementById("filter-department").value,
			employee_category: document.getElementById("filter-category").value,
			status: document.getElementById("filter-status").value,
			search: document.getElementById("filter-search").value,
		};
		loadData();
	}

	document.addEventListener("DOMContentLoaded", function () {
		var grid = document.getElementById("kpi-grid");
		if (!grid) return; // access-denied state has no dashboard DOM

		apiCall("get_filter_options", {}).then(function (options) {
			populateSelect(document.getElementById("filter-company"), options.companies, "All companies");
			populateSelect(document.getElementById("filter-department"), options.departments, "All departments");
			populateSelect(document.getElementById("filter-category"), options.employee_categories, "All categories");
			populateSelect(document.getElementById("filter-status"), options.statuses, "All statuses");
			loadData();
		});

		["filter-company", "filter-department", "filter-category"].forEach(function (id) {
			document.getElementById(id).addEventListener("change", onFilterChange);
		});
		document.getElementById("filter-status").addEventListener("change", onFilterChange);
		document.getElementById("filter-search").addEventListener("input", debounce(onFilterChange, 300));

		document.getElementById("pagination-prev").addEventListener("click", function () {
			state.start = Math.max(0, state.start - PAGE_LENGTH);
			loadData();
		});
		document.getElementById("pagination-next").addEventListener("click", function () {
			state.start = state.start + PAGE_LENGTH;
			loadData();
		});

		var emailEl = document.getElementById("topbar-user");
		var avatarEl = document.getElementById("topbar-avatar");
		if (emailEl && avatarEl) {
			var email = emailEl.textContent.trim();
			var initials = email.split("@")[0].split(/[._-]/).map(function (p) { return p[0] || ""; }).slice(0, 2).join("").toUpperCase();
			avatarEl.textContent = initials;
		}
	});
})();
