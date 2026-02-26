frappe.pages['armada-dashboard'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Armada Dashboard',
		single_column: true
	});

	// Hide default frappe page header
	$(wrapper).find('.page-head').hide();

	// Load Chart.js if not available, then initialize dashboard
	if (typeof Chart === 'undefined') {
		frappe.require('https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js', function() {
			new ArmadaDashboard(page);
		});
	} else {
		new ArmadaDashboard(page);
	}
}

class ArmadaDashboard {
	constructor(page) {
		this.page = page;
		this.wrapper = $(page.body);
		this.current_page = 'main';

		// Independent filters per page so that changing dates on one page
		// does NOT affect any other page.
		this.main_filters = {
			from_date: frappe.datetime.month_start(),
			to_date: frappe.datetime.get_today()
		};
		this.sales_filters = {
			from_date: frappe.datetime.month_start(),
			to_date: frappe.datetime.get_today()
		};
		this.cashflow_filters = {
			from_date: frappe.datetime.month_start(),
			to_date: frappe.datetime.get_today()
		};

		// Cached filter options (loaded once at startup)
		this._sales_filter_options = null;
		this._cashflow_filter_options = null;
		this._warehouse_filter_options = null;

		this.init();
	}

	init() {
		this.render_layout();
		this.setup_events();
		this._preload_filter_options();
		this.load_page('main');
	}

	render_layout() {
		this.wrapper.html(frappe.render_template('armada_dashboard'));
		this.init_theme();
	}

	init_theme() {
		const savedTheme = localStorage.getItem('armada_theme') || 'dark';
		if (savedTheme === 'dark') {
			this.wrapper.find('.armada-dashboard-container').addClass('dark-mode');
			$('body').addClass('armada-dark-mode-active');
			this.wrapper.find('#theme-icon').removeClass('fa-moon-o').addClass('fa-sun-o');
			this.is_dark_mode = true;
		} else {
			this.wrapper.find('.armada-dashboard-container').removeClass('dark-mode');
			$('body').removeClass('armada-dark-mode-active');
			this.wrapper.find('#theme-icon').removeClass('fa-sun-o').addClass('fa-moon-o');
			this.is_dark_mode = false;
		}
	}

	toggle_theme() {
		const container = this.wrapper.find('.armada-dashboard-container');
		const icon = this.wrapper.find('#theme-icon');
		
		if (this.is_dark_mode) {
			container.removeClass('dark-mode');
			$('body').removeClass('armada-dark-mode-active');
			icon.removeClass('fa-sun-o').addClass('fa-moon-o');
			localStorage.setItem('armada_theme', 'light');
			this.is_dark_mode = false;
		} else {
			container.addClass('dark-mode');
			$('body').addClass('armada-dark-mode-active');
			icon.removeClass('fa-moon-o').addClass('fa-sun-o');
			localStorage.setItem('armada_theme', 'dark');
			this.is_dark_mode = true;
		}
		
		// Reload charts with new theme colors
		this.reload_current_page();
	}

	setup_events() {
		let me = this;

		// Theme toggle
		this.wrapper.on('click', '#theme-toggle', function() {
			me.toggle_theme();
		});

		// Menu item click
		this.wrapper.on('click', '.menu-item', function() {
			let page = $(this).data('page');
			me.wrapper.find('.menu-item').removeClass('active');
			$(this).addClass('active');
			me.load_page(page);
		});

		// Sidebar toggle
		this.wrapper.on('click', '.sidebar-toggle', function() {
			me.wrapper.find('.armada-sidebar').toggleClass('collapsed');
			me.wrapper.find('.armada-main-content').toggleClass('expanded');
		});

		// Dark date range toggle
		this.wrapper.on('click', '.dark-date-range', function(e) {
			e.stopPropagation();
			const dropdown = $(this).siblings('.date-range-dropdown');
			$('.date-range-dropdown').not(dropdown).removeClass('show');
			dropdown.toggleClass('show');
		});

		// Apply date buttons
		this.wrapper.on('click', '#btn-apply-sales-date', function() {
			me.apply_page_date_range('sales');
		});

		this.wrapper.on('click', '#btn-apply-cashflow-date', function() {
			me.apply_page_date_range('cashflow');
		});

		// Close dropdowns on outside click
		$(document).on('click', function(e) {
			if (!$(e.target).closest('.date-range-item').length) {
				$('.date-range-dropdown').removeClass('show');
			}
			if (!$(e.target).closest('.multi-select-wrapper').length) {
				$('.multi-select-dropdown').removeClass('show');
			}
		});
	}

	_get_page_filters(page) {
		if (page === 'sales') return this.sales_filters;
		if (page === 'cashflow') return this.cashflow_filters;
		return this.main_filters;
	}

	_preload_filter_options() {
		let me = this;
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_sales_filter_options',
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me._sales_filter_options = r.message;
					if (me.current_page === 'sales') {
						me._apply_sales_filter_options();
					}
				}
			}
		});
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_cashflow_filter_options',
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me._cashflow_filter_options = r.message;
					if (me.current_page === 'cashflow') {
						me._apply_cashflow_filter_options();
					}
				}
			}
		});
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_warehouse_filter_options',
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me._warehouse_filter_options = r.message;
					if (me.current_page === 'warehouse') {
						me._apply_warehouse_filter_options();
					}
				}
			}
		});
	}

	_apply_sales_filter_options() {
		if (this._sales_filter_options) {
			this._populate_multi_select('item_names', this._sales_filter_options.item_names || []);
			this._populate_multi_select('item_groups', this._sales_filter_options.item_groups || []);
			this._populate_multi_select('customers', this._sales_filter_options.customers || []);
		}
	}

	_apply_cashflow_filter_options() {
		if (this._cashflow_filter_options) {
			this._populate_multi_select('cf_payment_modes', this._cashflow_filter_options.payment_modes || []);
			this._populate_multi_select('cf_categories', this._cashflow_filter_options.categories || []);
			this._populate_multi_select('cf_counterparties', this._cashflow_filter_options.counterparties || []);
		}
	}

	_apply_warehouse_filter_options() {
		if (this._warehouse_filter_options) {
			this._populate_multi_select('wh_warehouses', this._warehouse_filter_options.warehouses || []);
			this._populate_multi_select('wh_item_groups', this._warehouse_filter_options.item_groups || []);
			this._populate_multi_select('wh_items', this._warehouse_filter_options.items || []);
		}
	}

	init_page_date_range(page) {
		const prefix = page === 'sales' ? 'sales' : 'cashflow';
		const filters = this._get_page_filters(page);
		this.wrapper.find(`#${prefix}-date-start`).val(filters.from_date);
		this.wrapper.find(`#${prefix}-date-end`).val(filters.to_date);
		this.update_page_date_display(page);
	}

	update_page_date_display(page) {
		const prefix = page === 'sales' ? 'sales' : 'cashflow';
		const filters = this._get_page_filters(page);
		const startFormatted = this.format_date_display_text(filters.from_date);
		const endFormatted = this.format_date_display_text(filters.to_date);
		this.wrapper.find(`#${prefix}-date-range .date-range-text`).text(`${startFormatted} - ${endFormatted}`);
	}

	format_date_display_text(dateStr) {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
		const day = date.getDate();
		const month = months[date.getMonth()];
		const year = date.getFullYear();
		return `${month} ${day}, ${year}`;
	}

	apply_page_date_range(page) {
		const prefix = page === 'sales' ? 'sales' : 'cashflow';
		const startInput = this.wrapper.find(`#${prefix}-date-start`).val();
		const endInput = this.wrapper.find(`#${prefix}-date-end`).val();
		
		if (startInput && endInput) {
			// Update ONLY the current page's filters — not other pages
			const filters = this._get_page_filters(page);
			filters.from_date = startInput;
			filters.to_date = endInput;
			this.update_page_date_display(page);
			$('.date-range-dropdown').removeClass('show');
			this.reload_current_page();
		}
	}

	reload_current_page() {
		this.load_page(this.current_page);
	}

	load_page(page_name) {
		this.current_page = page_name;
		
		switch(page_name) {
			case 'main':
				this.render_main_page();
				break;
			case 'sales':
				this.render_sales_page();
				break;
			case 'cashflow':
				this.render_cashflow_page();
				break;
			case 'counterparties':
				this.render_counterparties_page();
				break;
			case 'warehouse':
				this.render_warehouse_page();
				break;
		}
	}

	// ==================== MAIN PAGE ====================
	render_main_page() {
		$('#page-title').text('ГЛАВНЫЕ ПОКАЗАТЕЛИ ЗА ТЕКУЩИЙ МЕСЯЦ');
		
		let content = `
			<div class="main-page">
				<!-- KPI Cards -->
				<div class="kpi-cards-row">
					<div class="kpi-card">
						<div class="kpi-label">Сумма продажи</div>
						<div class="kpi-value" id="total-sales">$0</div>
						<div class="kpi-change negative" id="sales-change">↓ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Поступления от клиентов</div>
						<div class="kpi-value" id="customer-receipts">$0</div>
						<div class="kpi-change negative" id="receipts-change">↓ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Задолженность клиентов</div>
						<div class="kpi-value negative" id="customer-debt">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Задолженность поставщикам</div>
						<div class="kpi-value positive" id="supplier-debt">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Остаточная сумма кассы</div>
						<div class="kpi-value" id="cash-balance">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Рабочий капитал</div>
						<div class="kpi-value" id="working-capital">-</div>
					</div>
				</div>

				<!-- Charts Row -->
				<div class="charts-row">
					<div class="chart-container wide">
						<div class="chart-title">ПРОДАЖИ ЗА ТЕКУЩИЙ ГОД</div>
						<canvas id="yearly-sales-chart"></canvas>
					</div>
					<div class="chart-container narrow scrollable-card">
						<div class="chart-title">ПРОИЗВЕДЕНО ЗА ТЕКУЩИЙ МЕСЯЦ</div>
						<div class="data-table-wrapper" id="production-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>

				<!-- Turnover Chart -->
				<div class="charts-row">
					<div class="chart-container full">
						<div class="chart-title">ДИНАМИКА ОБОРОТА ЗА ТЕКУЩИЙ ГОД</div>
						<div class="chart-legend">
							<span class="legend-item"><span class="legend-color expense"></span>Расход</span>
							<span class="legend-item"><span class="legend-color income"></span>Приход</span>
						</div>
						<canvas id="turnover-chart"></canvas>
					</div>
				</div>
			</div>
		`;
		
		$('#page-content').html(content);
		this.load_main_data();
	}

	load_main_data() {
		let me = this;
		const filters = this.main_filters;

		// Load KPI data
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_main_kpis',
			args: {
				from_date: filters.from_date,
				to_date: filters.to_date
			},
			callback: function(r) {
				if (r.message) {
					me.update_main_kpis(r.message);
				}
			}
		});

		// Load yearly sales chart
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_yearly_sales',
			callback: function(r) {
				if (r.message) {
					me.render_yearly_sales_chart(r.message);
				}
			}
		});

		// Load turnover chart
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_turnover_data',
			callback: function(r) {
				if (r.message) {
					me.render_turnover_chart(r.message);
				}
			}
		});

		// Load production table
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_production_data',
			args: {
				from_date: filters.from_date,
				to_date: filters.to_date
			},
			callback: function(r) {
				if (r.message) {
					me.render_production_table(r.message);
				}
			}
		});
	}

	update_main_kpis(data) {
		$('#total-sales').text(this.format_currency(data.total_sales || 0));
		$('#sales-change').text(`↓ ${Math.abs(data.sales_change || 0).toFixed(1)}%`);
		$('#customer-receipts').text(this.format_currency(data.customer_receipts || 0));
		$('#receipts-change').text(`↓ ${Math.abs(data.receipts_change || 0).toFixed(1)}%`);
		$('#customer-debt').text(this.format_currency(data.customer_debt || 0));
		$('#supplier-debt').text(this.format_currency(data.supplier_debt || 0));
		$('#cash-balance').text(this.format_currency(data.cash_balance || 0));
		$('#working-capital').text(data.working_capital ? this.format_currency(data.working_capital) : '-');
	}

	getChartColors() {
		const isDark = this.is_dark_mode;
		return {
			gridColor: isDark ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)',
			textColor: isDark ? '#94a3b8' : '#64748b'
		};
	}

	render_yearly_sales_chart(data) {
		const ctx = document.getElementById('yearly-sales-chart');
		if (!ctx) return;

		const colors = this.getChartColors();

		new Chart(ctx, {
			type: 'line',
			data: {
				labels: data.labels,
				datasets: [{
					label: new Date().getFullYear(),
					data: data.values,
					borderColor: '#00d4ff',
					backgroundColor: 'rgba(0, 212, 255, 0.1)',
					tension: 0.4,
					fill: true,
					pointBackgroundColor: '#00d4ff',
					pointBorderColor: '#00d4ff',
					pointRadius: 4
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: true,
						position: 'top',
						align: 'end',
						labels: {
							color: '#00d4ff'
						}
					}
				},
				scales: {
					x: {
						grid: { color: colors.gridColor },
						ticks: { color: colors.textColor }
					},
					y: {
						grid: { color: colors.gridColor },
						ticks: { 
							color: colors.textColor,
							callback: function(value) {
								return '$' + Number(value / 1000).toLocaleString('ru-RU') + 'K';
							}
						}
					}
				}
			}
		});
	}

	render_turnover_chart(data) {
		const ctx = document.getElementById('turnover-chart');
		if (!ctx) return;

		const colors = this.getChartColors();

		new Chart(ctx, {
			type: 'bar',
			data: {
				labels: data.labels,
				datasets: [
					{
						label: 'Расход',
						data: data.expense,
						backgroundColor: '#ff4757'
					},
					{
						label: 'Приход',
						data: data.income,
						backgroundColor: '#2ed573'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: { display: false }
				},
				scales: {
					x: {
						grid: { color: colors.gridColor },
						ticks: { color: colors.textColor }
					},
					y: {
						grid: { color: colors.gridColor },
						ticks: { 
							color: colors.textColor,
							callback: function(value) {
								return '$' + Number(value / 1000).toLocaleString('ru-RU') + 'K';
							}
						}
					}
				}
			}
		});
	}

	render_production_table(data) {
		let html = `
			<table class="data-table">
				<thead>
					<tr>
						<th>Дата</th>
						<th>Наименование</th>
						<th>Единица</th>
						<th>Кол-во</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach(row => {
			let highlightClass = '';
			if (row.qty >= 100) {
				highlightClass = 'highlight-red';
			} else if (row.qty >= 10) {
				highlightClass = 'highlight';
			}
			html += `
				<tr>
					<td>${row.date}</td>
					<td>${row.item_name}</td>
					<td>${row.uom}</td>
					<td class="${highlightClass}">${row.qty}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
				<tfoot>
					<tr>
						<td colspan="3"><strong>Grand total</strong></td>
						<td><strong>${data.reduce((sum, r) => sum + r.qty, 0)}</strong></td>
					</tr>
				</tfoot>
			</table>
		`;
		
		$('#production-table').html(html);
	}

	// ==================== SALES PAGE ====================
	render_sales_page() {
		$('#page-title').text('ПОКАЗАТЕЛИ ПРОДАЖ');
		
		let content = `
			<div class="sales-page">
				<!-- Dark Filter Bar -->
				<div class="dark-filter-bar">
					<div class="filter-item multi-select-wrapper" data-filter="item_names">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Список наименований продуктов</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="item_groups">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Типаж</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="customers">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Список контрагентов</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item date-range-item">
						<div class="dark-date-range" id="sales-date-range">
							<span class="date-range-text"></span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="date-range-dropdown" id="sales-date-dropdown">
							<div class="date-inputs">
								<input type="date" id="sales-date-start" class="date-input-dark">
								<span class="date-separator">-</span>
								<input type="date" id="sales-date-end" class="date-input-dark">
							</div>
							<button class="btn-apply-date" id="btn-apply-sales-date">Применить</button>
						</div>
					</div>
				</div>

				<!-- KPI Cards -->
				<div class="kpi-cards-row">
					<div class="kpi-card">
						<div class="kpi-label">Количество проданных, шт.</div>
						<div class="kpi-value" id="sold-qty">0</div>
						<div class="kpi-change negative" id="sold-change">↓ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Сумма продажи</div>
						<div class="kpi-value" id="sales-amount">$0</div>
						<div class="kpi-change negative" id="sales-amount-change">↓ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Сумма себестоимости</div>
						<div class="kpi-value" id="cost-amount">-</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Общая маржа</div>
						<div class="kpi-value" id="total-margin">-</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Средняя цена</div>
						<div class="kpi-value" id="avg-price">$0</div>
						<div class="kpi-change positive" id="avg-price-change">↑ $0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Рентабельность</div>
						<div class="kpi-value" id="profitability">-</div>
					</div>
				</div>

				<!-- Charts Row -->
				<div class="charts-row">
					<div class="chart-container">
						<div class="chart-title">ГОДОВАЯ ДИНАМИКА ПРОДАЖ</div>
						<canvas id="sales-dynamics-chart"></canvas>
					</div>
					<div class="chart-container scrollable-card">
						<div class="chart-title">ДАННЫЕ ПО ПРОДАЖАМ</div>
						<div class="data-table-wrapper" id="sales-data-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>

				<!-- Product Ranking -->
				<div class="charts-row">
					<div class="chart-container full scrollable-card">
						<div class="chart-title">РЕЙТИНГ ПО ПРОДАЖАМ ПРОДУКТОВ</div>
						<div class="ranking-table-wrapper" id="product-ranking-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>
			</div>
		`;
		
		$('#page-content').html(content);
		this.init_page_date_range('sales');
		this._apply_sales_filter_options();
		this._bind_filter_events('sales');
		this.load_sales_data();
	}

	/* ── Multi-select filter helpers ──────────────────────────────── */

	_bind_filter_events(page) {
		let me = this;
		const filterBar = this.wrapper.find('.dark-filter-bar');
		if (!filterBar.length) return;

		// Toggle dropdown
		filterBar.on('click', '.multi-select-toggle', function(e) {
			e.stopPropagation();
			const dropdown = $(this).siblings('.multi-select-dropdown');
			$('.multi-select-dropdown').not(dropdown).removeClass('show');
			dropdown.toggleClass('show');
			if (dropdown.hasClass('show')) {
				dropdown.find('.ms-search').focus();
			}
		});

		// Search within dropdown
		filterBar.on('input', '.ms-search', function() {
			const query = $(this).val().toLowerCase();
			$(this).siblings('.ms-options').find('.ms-option').each(function() {
				const text = $(this).find('.ms-label').text().toLowerCase();
				$(this).toggle(text.includes(query));
			});
		});

		// Checkbox change → reload data for THIS page only
		filterBar.on('change', '.ms-option input[type="checkbox"]', function() {
			const wrapper = $(this).closest('.multi-select-wrapper');
			me._update_multi_select_display(wrapper);
			if (page === 'sales') {
				me.load_sales_data();
			} else if (page === 'cashflow') {
				me.load_cashflow_data();
			} else if (page === 'warehouse') {
				me.load_warehouse_data();
			}
		});

		// Prevent dropdown close when clicking inside
		filterBar.on('click', '.multi-select-dropdown', function(e) {
			e.stopPropagation();
		});

		// Clear button — uncheck all and reload
		filterBar.on('click', '.ms-clear', function(e) {
			e.stopPropagation();
			const wrapper = $(this).closest('.multi-select-wrapper');
			wrapper.find('.ms-option input[type="checkbox"]').prop('checked', false);
			me._update_multi_select_display(wrapper);
			if (page === 'sales') {
				me.load_sales_data();
			} else if (page === 'cashflow') {
				me.load_cashflow_data();
			} else if (page === 'warehouse') {
				me.load_warehouse_data();
			}
		});
	}

	_update_multi_select_display(wrapper) {
		const checked = wrapper.find('.ms-option input:checked');
		const placeholder = wrapper.find('.ms-placeholder');
		const count = wrapper.find('.ms-count');
		const clear = wrapper.find('.ms-clear');
		if (checked.length > 0) {
			placeholder.hide();
			count.text(checked.length + ' выбрано').show();
			clear.show();
		} else {
			placeholder.show();
			count.hide();
			clear.hide();
		}
	}

	_get_multi_select_values(filterName) {
		const wrapper = this.wrapper.find(`.multi-select-wrapper[data-filter="${filterName}"]`);
		const checked = wrapper.find('.ms-option input:checked');
		let values = [];
		checked.each(function() {
			values.push($(this).val());
		});
		return values;
	}

	_populate_multi_select(filterName, options) {
		const wrapper = this.wrapper.find(`.multi-select-wrapper[data-filter="${filterName}"]`);
		const container = wrapper.find('.ms-options');
		let html = '';
		options.forEach(function(opt) {
			const escaped = $('<span>').text(opt).html();
			html += `
				<label class="ms-option">
					<input type="checkbox" value="${escaped}">
					<span class="ms-label">${escaped}</span>
				</label>`;
		});
		container.html(html);
	}

	load_sales_data() {
		let me = this;
		const filters = this.sales_filters;
		const item_names = this._get_multi_select_values('item_names');
		const item_groups = this._get_multi_select_values('item_groups');
		const customers = this._get_multi_select_values('customers');

		const filter_args = {};
		if (item_names.length) filter_args.item_names = JSON.stringify(item_names);
		if (item_groups.length) filter_args.item_groups = JSON.stringify(item_groups);
		if (customers.length) filter_args.customers = JSON.stringify(customers);

		// Load sales KPIs
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_sales_kpis',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.update_sales_kpis(r.message);
				}
			}
		});

		// Load sales dynamics chart
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_sales_dynamics',
			args: Object.assign({}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_sales_dynamics_chart(r.message);
				}
			}
		});

		// Load product ranking
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_product_ranking',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_product_ranking(r.message);
				}
			}
		});

		// Load sales data table
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_sales_data',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_sales_data_table(r.message);
				}
			}
		});
	}

	update_sales_kpis(data) {
		$('#sold-qty').text(data.sold_qty || 0);
		$('#sold-change').text(`↓ ${Math.abs(data.sold_change || 0).toFixed(1)}%`);
		$('#sales-amount').text(this.format_currency(data.sales_amount || 0));
		$('#sales-amount-change').text(`↓ ${Math.abs(data.sales_amount_change || 0).toFixed(1)}%`);
		$('#cost-amount').text(data.cost_amount ? this.format_currency(data.cost_amount) : '-');
		$('#total-margin').text(data.total_margin ? this.format_currency(data.total_margin) : '-');
		$('#avg-price').text(this.format_currency(data.avg_price || 0));
		$('#profitability').text(data.profitability ? data.profitability + '%' : '-');
	}

	render_sales_dynamics_chart(data) {
		const ctx = document.getElementById('sales-dynamics-chart');
		if (!ctx) return;

		const colors = this.getChartColors();

		new Chart(ctx, {
			type: 'bar',
			data: {
				labels: data.labels,
				datasets: [{
					label: 'Продажи',
					data: data.values,
					backgroundColor: '#00d4ff'
				}]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: { display: false }
				},
				scales: {
					x: {
						grid: { color: colors.gridColor },
						ticks: { color: colors.textColor }
					},
					y: {
						grid: { color: colors.gridColor },
						ticks: { 
							color: colors.textColor,
							callback: function(value) {
								return '$' + Number(value / 1000).toLocaleString('ru-RU') + 'K';
							}
						}
					}
				}
			}
		});
	}

	render_product_ranking(data) {
		let html = `
			<table class="ranking-table">
				<thead>
					<tr>
						<th></th>
						<th>Наименование</th>
						<th>Кол-во, шт</th>
						<th>Сумма</th>
						<th>% Δ</th>
						<th>Сумма СС</th>
						<th>Маржа</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach((row, index) => {
			const barWidth = (row.amount / data[0].amount) * 100;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.item_name}</td>
					<td>
						<span class="bar-value">${row.qty}</span>
						<div class="bar-container">
							<div class="bar" style="width: ${barWidth}%"></div>
						</div>
					</td>
					<td>${this.format_currency(row.amount)}</td>
					<td class="${row.change >= 0 ? 'positive' : 'negative'}">${row.change}% ${row.change >= 0 ? '↑' : '↓'}</td>
					<td>${row.cost ? this.format_currency(row.cost) : '-'}</td>
					<td>${row.margin ? this.format_currency(row.margin) : '-'}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
			</table>
		`;
		
		$('#product-ranking-table').html(html);
	}

	render_sales_data_table(data) {
		let html = `
			<table class="data-table small">
				<thead>
					<tr>
						<th>Дата</th>
						<th>Наименование</th>
						<th>Контрагент</th>
						<th>Кол-во</th>
						<th>Сумма</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach(row => {
			html += `
				<tr>
					<td>${row.date}</td>
					<td>${row.item_name}</td>
					<td>${row.customer}</td>
					<td class="${row.qty > 5 ? 'highlight-yellow' : ''}">${row.qty}</td>
					<td class="${row.amount > 1000 ? 'highlight-red' : ''}">${this.format_currency(row.amount)}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
			</table>
		`;
		
		$('#sales-data-table').html(html);
	}

	// ==================== CASHFLOW PAGE ====================
	render_cashflow_page() {
		$('#page-title').text('ИНФОРМАЦИЯ ПО ДЕНЕЖНОМУ ОБОРОТУ');
		
		let content = `
			<div class="cashflow-page">
				<!-- Dark Filter Bar -->
				<div class="dark-filter-bar">
					<div class="filter-item multi-select-wrapper" data-filter="cf_payment_modes">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Тип расчёта</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="cf_categories">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Список категории</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="cf_counterparties">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Список контрагентов</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item date-range-item">
						<div class="dark-date-range" id="cashflow-date-range">
							<span class="date-range-text"></span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="date-range-dropdown" id="cashflow-date-dropdown">
							<div class="date-inputs">
								<input type="date" id="cashflow-date-start" class="date-input-dark">
								<span class="date-separator">-</span>
								<input type="date" id="cashflow-date-end" class="date-input-dark">
							</div>
							<button class="btn-apply-date" id="btn-apply-cashflow-date">Применить</button>
						</div>
					</div>
				</div>

				<!-- KPI Cards -->
				<div class="kpi-cards-row">
					<div class="kpi-card">
						<div class="kpi-label">Наличный приход</div>
						<div class="kpi-value positive" id="cash-income">$0</div>
						<div class="kpi-change positive" id="cash-income-change">↑ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Перечисление приход</div>
						<div class="kpi-value" id="transfer-income">-</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Наличный расход</div>
						<div class="kpi-value negative" id="cash-expense">$0</div>
						<div class="kpi-change negative" id="cash-expense-change">↓ 0%</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Перечисление расход</div>
						<div class="kpi-value" id="transfer-expense">-</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Текущий остаток наличные</div>
						<div class="kpi-value" id="current-cash">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Тек. остаток перечисление</div>
						<div class="kpi-value" id="current-transfer">$0</div>
					</div>
				</div>

				<!-- Charts Row -->
				<div class="charts-row two-columns">
					<div class="chart-container scrollable-card">
						<div class="chart-title">РЕЙТИНГ ПРИХОДОВ</div>
						<div class="ranking-table-wrapper" id="income-ranking-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
					<div class="chart-container">
						<div class="chart-title">ДИНАМИКА ПРИХОДА И РАСХОДА</div>
						<div class="chart-legend">
							<span class="legend-item"><span class="legend-color income"></span>Приход</span>
							<span class="legend-item"><span class="legend-color expense"></span>Расход</span>
						</div>
						<canvas id="income-expense-chart"></canvas>
					</div>
				</div>

				<!-- Bottom Row -->
				<div class="charts-row two-columns">
					<div class="chart-container scrollable-card">
						<div class="chart-title">РЕЙТИНГ РАСХОДОВ</div>
						<div class="ranking-table-wrapper" id="expense-ranking-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
					<div class="chart-container">
						<div class="chart-title">ДАННЫЕ ПО ОБОРОТУ</div>
						<div class="data-table-wrapper" id="turnover-data-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>
			</div>
		`;
		
		$('#page-content').html(content);
		this.init_page_date_range('cashflow');
		this._apply_cashflow_filter_options();
		this._bind_filter_events('cashflow');
		this.load_cashflow_data();
	}

	load_cashflow_data() {
		let me = this;
		const filters = this.cashflow_filters;
		const payment_modes = this._get_multi_select_values('cf_payment_modes');
		const categories = this._get_multi_select_values('cf_categories');
		const counterparties = this._get_multi_select_values('cf_counterparties');

		const filter_args = {};
		if (payment_modes.length) filter_args.payment_modes = JSON.stringify(payment_modes);
		if (categories.length) filter_args.categories = JSON.stringify(categories);
		if (counterparties.length) filter_args.counterparties = JSON.stringify(counterparties);

		// Load cashflow KPIs
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_cashflow_kpis',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.update_cashflow_kpis(r.message);
				}
			}
		});

		// Load income/expense chart
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_income_expense_data',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_income_expense_chart(r.message);
				}
			}
		});

		// Load income ranking
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_income_ranking',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_income_ranking(r.message);
				}
			}
		});

		// Load expense ranking
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_expense_ranking',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_expense_ranking(r.message);
				}
			}
		});

		// Load turnover data
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_turnover_summary',
			args: Object.assign({
				from_date: filters.from_date,
				to_date: filters.to_date
			}, filter_args),
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_turnover_summary(r.message);
				}
			}
		});
	}

	update_cashflow_kpis(data) {
		$('#cash-income').text(this.format_currency(data.cash_income || 0));
		$('#cash-income-change').text(`↑ ${Math.abs(data.cash_income_change || 0).toFixed(1)}%`);
		$('#transfer-income').text(data.transfer_income ? this.format_currency(data.transfer_income) : '-');
		$('#cash-expense').text(this.format_currency(data.cash_expense || 0));
		$('#cash-expense-change').text(`↓ ${Math.abs(data.cash_expense_change || 0).toFixed(1)}%`);
		$('#transfer-expense').text(data.transfer_expense ? this.format_currency(data.transfer_expense) : '-');
		$('#current-cash').text(this.format_currency(data.current_cash || 0));
		$('#current-transfer').text(this.format_currency(data.current_transfer || 0));
	}

	render_income_expense_chart(data) {
		const ctx = document.getElementById('income-expense-chart');
		if (!ctx) return;

		const colors = this.getChartColors();

		new Chart(ctx, {
			type: 'bar',
			data: {
				labels: data.labels,
				datasets: [
					{
						label: 'Приход',
						data: data.income,
						backgroundColor: '#2ed573'
					},
					{
						label: 'Расход',
						data: data.expense,
						backgroundColor: '#ff4757'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: { display: false }
				},
				scales: {
					x: {
						grid: { color: colors.gridColor },
						ticks: { color: colors.textColor }
					},
					y: {
						grid: { color: colors.gridColor },
						ticks: { 
							color: colors.textColor,
							callback: function(value) {
								return Number(value / 1000).toLocaleString('ru-RU') + 'K';
							}
						}
					}
				}
			}
		});
	}

	render_income_ranking(data) {
		let total = data.reduce((sum, r) => sum + r.amount, 0);
		let html = `
			<table class="ranking-table compact">
				<thead>
					<tr>
						<th></th>
						<th>Контрагент</th>
						<th>Сумма</th>
						<th>% Δ</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach((row, index) => {
			const barWidth = (row.amount / data[0].amount) * 100;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.party}</td>
					<td>
						${this.format_currency(row.amount)}
						<div class="bar-container small">
							<div class="bar income" style="width: ${barWidth}%"></div>
						</div>
					</td>
					<td class="${row.change >= 0 ? 'positive' : 'negative'}">${row.change}% ${row.change >= 0 ? '↑' : '↓'}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
				<tfoot>
					<tr>
						<td></td>
						<td><strong>Grand total</strong></td>
						<td><strong>${this.format_currency(total)}</strong></td>
						<td></td>
					</tr>
				</tfoot>
			</table>
		`;
		
		$('#income-ranking-table').html(html);
	}

	render_expense_ranking(data) {
		let total = data.reduce((sum, r) => sum + r.amount, 0);
		let html = `
			<table class="ranking-table compact">
				<thead>
					<tr>
						<th></th>
						<th>Категория</th>
						<th>Сумма</th>
						<th>% Δ</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach((row, index) => {
			const barWidth = (row.amount / data[0].amount) * 100;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.category}</td>
					<td>
						${this.format_currency(row.amount)}
						<div class="bar-container small">
							<div class="bar expense" style="width: ${barWidth}%"></div>
						</div>
					</td>
					<td class="${row.change >= 0 ? 'positive' : 'negative'}">${row.change}% ${row.change >= 0 ? '↑' : '↓'}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
				<tfoot>
					<tr>
						<td></td>
						<td><strong>Grand total</strong></td>
						<td><strong>${this.format_currency(total)}</strong></td>
						<td></td>
					</tr>
				</tfoot>
			</table>
		`;
		
		$('#expense-ranking-table').html(html);
	}

	render_turnover_summary(data) {
		let html = `
			<table class="data-table summary">
				<thead>
					<tr>
						<th>Тип расчёта</th>
						<th>Расход</th>
						<th>Оборот / Сумма<br>Приход</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach(row => {
			html += `
				<tr>
					<td>${row.payment_type}</td>
					<td>${this.format_currency(row.expense)}</td>
					<td>${this.format_currency(row.income)}</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
			</table>
		`;
		
		$('#turnover-data-table').html(html);
	}

	// ==================== COUNTERPARTIES PAGE ====================
	render_counterparties_page() {
		$('#page-title').text('ТЕКУЩАЯ ЗАДОЛЖЕННОСТЬ КОНТРАГЕНТОВ');
		
		let content = `
			<div class="counterparties-page">
				<!-- KPI Cards -->
				<div class="kpi-cards-row">
					<div class="kpi-card wide">
						<div class="kpi-label">Задолженность клиентов</div>
						<div class="kpi-value negative" id="total-customer-debt">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Количество клиентов</div>
						<div class="kpi-value" id="customer-count">0</div>
					</div>
					<div class="kpi-card wide">
						<div class="kpi-label">Задолженность поставщикам</div>
						<div class="kpi-value positive" id="total-supplier-debt">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Количество поставщиков</div>
						<div class="kpi-value" id="supplier-count">0</div>
					</div>
				</div>

				<!-- Debt Tables -->
				<div class="charts-row two-columns">
					<div class="chart-container scrollable-card">
						<div class="chart-title">ЗАДОЛЖЕННОСТЬ КЛИЕНТОВ</div>
						<div class="debt-table-wrapper" id="customer-debt-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
					<div class="chart-container scrollable-card">
						<div class="chart-title">ЗАДОЛЖЕННОСТЬ ПОСТАВЩИКАМ</div>
						<div class="debt-table-wrapper" id="supplier-debt-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>
			</div>
		`;
		
		$('#page-content').html(content);
		this.load_counterparties_data();
	}

	load_counterparties_data() {
		let me = this;

		// Load counterparties KPIs
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_counterparties_kpis',
			callback: function(r) {
				if (r.message) {
					me.update_counterparties_kpis(r.message);
				}
			}
		});

		// Load customer debts
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_customer_debts',
			callback: function(r) {
				if (r.message) {
					me.render_customer_debts(r.message);
				}
			}
		});

		// Load supplier debts
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_supplier_debts',
			callback: function(r) {
				if (r.message) {
					me.render_supplier_debts(r.message);
				}
			}
		});
	}

	update_counterparties_kpis(data) {
		$('#total-customer-debt').text(this.format_currency(data.customer_debt || 0));
		$('#customer-count').text(data.customer_count || 0);
		$('#total-supplier-debt').text(this.format_currency(data.supplier_debt || 0));
		$('#supplier-count').text(data.supplier_count || 0);
	}

	render_customer_debts(data) {
		let total = data.reduce((sum, r) => sum + Math.abs(r.amount), 0);
		let maxAmount = Math.max(...data.map(r => Math.abs(r.amount)));
		
		let html = `
			<table class="debt-table">
				<thead>
					<tr>
						<th></th>
						<th>Контрагенты</th>
						<th>Сумма задолженность</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach((row, index) => {
			const barWidth = (Math.abs(row.amount) / maxAmount) * 100;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.customer}</td>
					<td>
						${this.format_currency(row.amount)}
						<div class="bar-container">
							<div class="bar customer-debt" style="width: ${barWidth}%"></div>
						</div>
					</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
				<tfoot>
					<tr>
						<td></td>
						<td><strong>Grand total</strong></td>
						<td><strong>${this.format_currency(-total)}</strong></td>
					</tr>
				</tfoot>
			</table>
		`;
		
		$('#customer-debt-table').html(html);
	}

	render_supplier_debts(data) {
		let total = data.reduce((sum, r) => sum + r.amount, 0);
		let maxAmount = Math.max(...data.map(r => r.amount));
		
		let html = `
			<table class="debt-table">
				<thead>
					<tr>
						<th></th>
						<th>Контрагенты</th>
						<th>Сумма задолженность</th>
					</tr>
				</thead>
				<tbody>
		`;
		
		data.forEach((row, index) => {
			const barWidth = (row.amount / maxAmount) * 100;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.supplier}</td>
					<td>
						${this.format_currency(row.amount)}
						<div class="bar-container">
							<div class="bar supplier-debt" style="width: ${barWidth}%"></div>
						</div>
					</td>
				</tr>
			`;
		});
		
		html += `
				</tbody>
				<tfoot>
					<tr>
						<td></td>
						<td><strong>Grand total</strong></td>
						<td><strong>${this.format_currency(total)}</strong></td>
					</tr>
				</tfoot>
			</table>
		`;
		
		$('#supplier-debt-table').html(html);
	}

	// ==================== WAREHOUSE (СКЛАД) PAGE ====================
	render_warehouse_page() {
		$('#page-title').text('ОСТАТКИ НА СКЛАДАХ');

		let content = `
			<div class="warehouse-page">
				<!-- Dark Filter Bar -->
				<div class="dark-filter-bar">
					<div class="filter-item multi-select-wrapper" data-filter="wh_warehouses">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Склад</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="wh_item_groups">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Тип товара</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<div class="ms-options"></div>
						</div>
					</div>
					<div class="filter-item multi-select-wrapper" data-filter="wh_items">
						<div class="multi-select-toggle dark-select">
							<span class="ms-placeholder">Наименование товара</span>
							<span class="ms-count" style="display:none"></span>
							<span class="ms-clear" style="display:none">clear</span>
							<i class="fa fa-chevron-down"></i>
						</div>
						<div class="multi-select-dropdown">
							<input type="text" class="ms-search" placeholder="Поиск...">
							<div class="ms-options"></div>
						</div>
					</div>
				</div>

				<!-- KPI Cards -->
				<div class="kpi-cards-row">
					<div class="kpi-card">
						<div class="kpi-label">Общее кол-во</div>
						<div class="kpi-value" id="wh-total-qty">0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Общая стоимость</div>
						<div class="kpi-value" id="wh-total-value">$0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Кол-во складов</div>
						<div class="kpi-value" id="wh-warehouse-count">0</div>
					</div>
					<div class="kpi-card">
						<div class="kpi-label">Кол-во наименований</div>
						<div class="kpi-value" id="wh-item-count">0</div>
					</div>
				</div>

				<!-- Tables Row -->
				<div class="charts-row two-columns">
					<div class="chart-container scrollable-card">
						<div class="chart-title">ОСТАТОК ПО СКЛАДАМ</div>
						<div class="ranking-table-wrapper" id="warehouse-summary-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
					<div class="chart-container scrollable-card">
						<div class="chart-title">ДЕТАЛЬНЫЕ ДАННЫЕ ПО СКЛАДУ</div>
						<div class="data-table-wrapper" id="warehouse-stock-table">
							<!-- Table will be rendered here -->
						</div>
					</div>
				</div>
			</div>
		`;

		$('#page-content').html(content);
		this._apply_warehouse_filter_options();
		this._bind_filter_events('warehouse');
		this.load_warehouse_data();
	}

	load_warehouse_data() {
		let me = this;
		const warehouses = this._get_multi_select_values('wh_warehouses');
		const item_groups = this._get_multi_select_values('wh_item_groups');
		const items = this._get_multi_select_values('wh_items');

		const filter_args = {};
		if (warehouses.length) filter_args.warehouses = JSON.stringify(warehouses);
		if (item_groups.length) filter_args.item_groups = JSON.stringify(item_groups);
		if (items.length) filter_args.items = JSON.stringify(items);

		// Load warehouse KPIs
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_warehouse_kpis',
			args: filter_args,
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.update_warehouse_kpis(r.message);
				}
			}
		});

		// Load warehouse summary
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_warehouse_summary',
			args: filter_args,
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_warehouse_summary(r.message);
				}
			}
		});

		// Load detailed stock data
		frappe.call({
			method: 'armada.armada_custom_app.api.dashboard.get_warehouse_stock_data',
			args: filter_args,
			freeze: false,
			callback: function(r) {
				if (r.message) {
					me.render_warehouse_stock_table(r.message);
				}
			}
		});
	}

	update_warehouse_kpis(data) {
		$('#wh-total-qty').text(Number(data.total_qty || 0).toLocaleString('ru-RU'));
		$('#wh-total-value').text(this.format_currency(data.total_value || 0));
		$('#wh-warehouse-count').text(data.warehouse_count || 0);
		$('#wh-item-count').text(data.item_count || 0);
	}

	render_warehouse_summary(data) {
		if (!data.length) {
			$('#warehouse-summary-table').html('<p style="color:#94a3b8;text-align:center;padding:20px;">Нет данных</p>');
			return;
		}

		let maxValue = Math.max(...data.map(r => r.total_value));
		let totalQty = data.reduce((sum, r) => sum + r.total_qty, 0);
		let totalValue = data.reduce((sum, r) => sum + r.total_value, 0);

		let html = `
			<table class="ranking-table compact">
				<thead>
					<tr>
						<th></th>
						<th>Склад</th>
						<th>Кол-во</th>
						<th>Стоимость</th>
						<th>Наименований</th>
					</tr>
				</thead>
				<tbody>
		`;

		data.forEach((row, index) => {
			const barWidth = maxValue > 0 ? (row.total_value / maxValue) * 100 : 0;
			html += `
				<tr>
					<td>${index + 1}.</td>
					<td>${row.warehouse}</td>
					<td>${Number(row.total_qty).toLocaleString('ru-RU')}</td>
					<td>
						${this.format_currency(row.total_value)}
						<div class="bar-container small">
							<div class="bar income" style="width: ${barWidth}%"></div>
						</div>
					</td>
					<td>${row.item_count}</td>
				</tr>
			`;
		});

		html += `
				</tbody>
				<tfoot>
					<tr>
						<td></td>
						<td><strong>Итого</strong></td>
						<td><strong>${Number(totalQty).toLocaleString('ru-RU')}</strong></td>
						<td><strong>${this.format_currency(totalValue)}</strong></td>
						<td></td>
					</tr>
				</tfoot>
			</table>
		`;

		$('#warehouse-summary-table').html(html);
	}

	render_warehouse_stock_table(data) {
		if (!data.length) {
			$('#warehouse-stock-table').html('<p style="color:#94a3b8;text-align:center;padding:20px;">Нет данных</p>');
			return;
		}

		let html = `
			<table class="data-table small">
				<thead>
					<tr>
						<th>Наименование</th>
						<th>Тип</th>
						<th>Склад</th>
						<th>Кол-во</th>
						<th>Цена</th>
						<th>Стоимость</th>
					</tr>
				</thead>
				<tbody>
		`;

		data.forEach(row => {
			html += `
				<tr>
					<td>${row.item_name}</td>
					<td>${row.item_group}</td>
					<td>${row.warehouse}</td>
					<td>${Number(row.actual_qty).toLocaleString('ru-RU')}</td>
					<td>${this.format_currency(row.valuation_rate)}</td>
					<td>${this.format_currency(row.stock_value)}</td>
				</tr>
			`;
		});

		html += `
				</tbody>
			</table>
		`;

		$('#warehouse-stock-table').html(html);
	}

	// ==================== UTILITY METHODS ====================
	format_currency(value) {
		return '$' + Number(value).toLocaleString('ru-RU', {
			minimumFractionDigits: 0,
			maximumFractionDigits: 2
		});
	}
}
