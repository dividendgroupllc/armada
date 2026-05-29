(function () {
    const BARCODE_PATTERN = /^ARM\d{10}$/;
    const PARENT_DOCTYPES = ["Sales Invoice", "Delivery Note", "Stock Entry"];
    const CHILD_DOCTYPES = ["Sales Invoice Item", "Delivery Note Item", "Stock Entry Detail"];
    const HANDLER_NAMESPACE = ".armada_item_code_barcode_scan";
    const STOCK_ENTRY_DETAILS_METHOD =
        "armada.armada_custom_app.barcode.get_stock_entry_barcode_item_details";
    const ITEM_CODE_COLUMNS = 3;
    const BARCODE_COLUMNS = 2;
    const STOCK_ENTRY_BARCODE_COLUMNS = 2;
    const STOCK_ENTRY_COLUMN_SIZES = {
        s_warehouse: 1,
        t_warehouse: 1,
        barcode: STOCK_ENTRY_BARCODE_COLUMNS,
        item_code: ITEM_CODE_COLUMNS,
        qty: 1,
        basic_rate: 1
    };

    function is_armada_barcode(value) {
        return BARCODE_PATTERN.test(String(value || "").trim());
    }

    function patch_stock_entry_none_qty_message() {
        if (!frappe || !frappe.msgprint || frappe.__armada_stock_entry_none_qty_msg_patched) return;

        const original_msgprint = frappe.msgprint;
        frappe.__armada_stock_entry_none_qty_msg_patched = true;

        frappe.msgprint = function (msg, title, is_minimizable) {
            if (should_suppress_stock_entry_none_qty_message(msg)) {
                return;
            }

            return original_msgprint.apply(this, arguments);
        };
    }

    function should_suppress_stock_entry_none_qty_message(msg) {
        if (!cur_frm || cur_frm.doctype !== "Stock Entry") return false;

        const messages = collect_message_text(msg);
        return messages.some(function (message) {
            return /Quantity for Item\s+(<[^>]+>)*None(<[^>]+>)*\s+cannot be zero/i.test(
                strip_html(String(message || ""))
            );
        });
    }

    function collect_message_text(msg) {
        if (!msg) return [];

        if (Array.isArray(msg)) {
            return msg.flatMap(function (message) {
                return collect_message_text(parse_message_json(message));
            });
        }

        msg = parse_message_json(msg);

        if ($.isPlainObject(msg)) {
            return collect_message_text(msg.message);
        }

        return [msg];
    }

    function parse_message_json(message) {
        if (typeof message !== "string") return message;

        try {
            return JSON.parse(message);
        } catch (e) {
            return message;
        }
    }

    function strip_html(message) {
        return $("<div>").html(message).text();
    }

    function patch_standard_stock_entry_barcode_handler() {
        if (
            !erpnext ||
            !erpnext.stock ||
            !erpnext.stock.utils ||
            !erpnext.stock.utils.set_item_details_using_barcode ||
            erpnext.stock.utils.__armada_stock_entry_barcode_patched
        ) {
            return;
        }

        const set_item_details_using_barcode = erpnext.stock.utils.set_item_details_using_barcode;
        erpnext.stock.utils.__armada_stock_entry_barcode_patched = true;

        erpnext.stock.utils.set_item_details_using_barcode = function (frm, child_row, callback) {
            if (
                frm &&
                frm.doctype === "Stock Entry" &&
                child_row &&
                child_row.doctype === "Stock Entry Detail" &&
                is_armada_barcode(child_row.barcode)
            ) {
                return Promise.resolve();
            }

            return set_item_details_using_barcode.apply(this, arguments);
        };
    }

    function patch_stock_entry_cscript_barcode_handler(frm) {
        if (!frm || frm.doctype !== "Stock Entry" || !frm.cscript || !frm.cscript.barcode) return;
        if (frm.cscript.__armada_stock_entry_barcode_patched) return;

        const standard_barcode_handler = frm.cscript.barcode;
        frm.cscript.__armada_stock_entry_barcode_patched = true;

        frm.cscript.barcode = function (doc, cdt, cdn) {
            const row = locals[cdt] && locals[cdt][cdn];
            if (cdt === "Stock Entry Detail" && row && is_armada_barcode(row.barcode)) {
                return Promise.resolve();
            }

            return standard_barcode_handler.apply(this, arguments);
        };
    }

    function get_items_grid(frm) {
        return frm.fields_dict.items && frm.fields_dict.items.grid;
    }

    function get_barcode_docfield(grid) {
        return grid && grid.docfields && grid.docfields.find(function (df) {
            return df.fieldname === "barcode";
        });
    }

    function get_item_code_docfield(grid) {
        return grid && grid.docfields && grid.docfields.find(function (df) {
            return df.fieldname === "item_code";
        });
    }

    function set_grid_column_size(df, columns) {
        if (!df) return;

        df.columns = columns;
        df.colsize = columns;
    }

    function is_stock_entry_grid(grid) {
        return grid && grid.frm && grid.frm.doctype === "Stock Entry";
    }

    function show_grid_list_column(df) {
        if (!df) return;

        df.hidden = 0;
        df.in_list_view = 1;
    }

    function make_field_read_only(df) {
        if (!df) return;

        df.read_only = 1;
    }

    function hide_grid_list_column(df) {
        if (!df) return;

        df.in_list_view = 0;
    }

    function find_field(fields, fieldname) {
        return fields && fields.find(function (df) {
            return df.fieldname === fieldname;
        });
    }

    function apply_stock_entry_column_sizes(fields) {
        if (!fields) return;

        Object.keys(STOCK_ENTRY_COLUMN_SIZES).forEach(function (fieldname) {
            set_grid_column_size(find_field(fields, fieldname), STOCK_ENTRY_COLUMN_SIZES[fieldname]);
        });
    }

    function move_field_after_item_code(fields, fieldname) {
        if (!fields) return;

        const field_index = fields.findIndex(function (df) {
            return df.fieldname === fieldname;
        });
        const item_code_index = fields.findIndex(function (df) {
            return df.fieldname === "item_code";
        });

        if (field_index === -1 || item_code_index === -1 || field_index === item_code_index + 1) {
            return;
        }

        const field = fields.splice(field_index, 1)[0];
        const target_index = fields.findIndex(function (df) {
            return df.fieldname === "item_code";
        });

        fields.splice(target_index + 1, 0, field);
    }

    function move_barcode_after_item_code(grid) {
        move_field_after_item_code(grid && grid.docfields, "barcode");
    }

    function place_fields_before_anchor(fields, ordered_fields, anchor_fieldname) {
        if (!fields) return;

        ordered_fields = ordered_fields.filter(Boolean);

        const fieldnames = ordered_fields.map(function (df) {
            return df.fieldname;
        });

        for (let i = fields.length - 1; i >= 0; i--) {
            if (fieldnames.includes(fields[i].fieldname)) {
                fields.splice(i, 1);
            }
        }

        const anchor_index = fields.findIndex(function (df) {
            return df.fieldname === anchor_fieldname;
        });
        const target_index = anchor_index === -1 ? fields.length : anchor_index;

        fields.splice.apply(fields, [target_index, 0].concat(ordered_fields));
    }

    function reset_grid_layout(grid, signature) {
        if (!grid || grid.__armada_grid_layout_signature === signature) return;

        grid.__armada_grid_layout_signature = signature;
        grid.visible_columns = [];

        if (grid.reset_grid && grid.wrapper) {
            grid.reset_grid();
        } else if (grid.debounced_refresh) {
            grid.debounced_refresh();
        }
    }

    function patch_user_defined_columns(grid) {
        if (!grid || grid.__armada_barcode_user_columns_patched) return;

        const setup_user_defined_columns = grid.setup_user_defined_columns;
        if (typeof setup_user_defined_columns !== "function") return;

        grid.__armada_barcode_user_columns_patched = true;
        grid.setup_user_defined_columns = function () {
            setup_user_defined_columns.apply(this, arguments);

            if (!this.user_defined_columns || !this.user_defined_columns.length) return;

            const barcode_df = get_barcode_docfield(this);
            if (!barcode_df) return;

            const barcode_columns = is_stock_entry_grid(this)
                ? STOCK_ENTRY_BARCODE_COLUMNS
                : BARCODE_COLUMNS;

            Object.assign(barcode_df, {
                hidden: 0,
                in_list_view: 1,
                columns: barcode_columns,
                colsize: barcode_columns
            });

            if (is_stock_entry_grid(this)) {
                const item_code_df = get_item_code_docfield(this);
                show_grid_list_column(item_code_df);
                set_grid_column_size(item_code_df, ITEM_CODE_COLUMNS);
                hide_grid_list_column(find_field(this.docfields, "is_finished_item"));
                hide_grid_list_column(find_field(this.user_defined_columns, "is_finished_item"));
                apply_stock_entry_column_sizes(this.docfields);
                apply_stock_entry_column_sizes(this.user_defined_columns);

                place_fields_before_anchor(this.user_defined_columns, [barcode_df, item_code_df], "qty");

                return;
            }

            set_grid_column_size(
                this.user_defined_columns.find(function (df) {
                    return df.fieldname === "item_code";
                }),
                ITEM_CODE_COLUMNS
            );

            if (!this.user_defined_columns.some(function (df) {
                return df.fieldname === "barcode";
            })) {
                const item_code_index = this.user_defined_columns.findIndex(function (df) {
                    return df.fieldname === "item_code";
                });

                this.user_defined_columns.splice(Math.max(item_code_index + 1, 0), 0, barcode_df);
            }

            move_field_after_item_code(this.user_defined_columns, "barcode");
        };
    }

    function configure_barcode_grid_column(frm) {
        const grid = get_items_grid(frm);
        const barcode_df = get_barcode_docfield(grid);
        if (!grid || !barcode_df) return;

        patch_user_defined_columns(grid);

        barcode_df.hidden = 0;
        barcode_df.in_list_view = 1;

        if (is_stock_entry_grid(grid)) {
            const item_code_df = get_item_code_docfield(grid);
            show_grid_list_column(item_code_df);
            set_grid_column_size(item_code_df, ITEM_CODE_COLUMNS);
            set_grid_column_size(barcode_df, STOCK_ENTRY_BARCODE_COLUMNS);
            hide_grid_list_column(find_field(grid.docfields, "is_finished_item"));
            apply_stock_entry_column_sizes(grid.docfields);
            place_fields_before_anchor(grid.docfields, [barcode_df, item_code_df], "qty");
        } else {
            set_grid_column_size(get_item_code_docfield(grid), ITEM_CODE_COLUMNS);
            set_grid_column_size(barcode_df, BARCODE_COLUMNS);
            move_barcode_after_item_code(grid);
        }


        if (grid.fields_map && grid.fields_map.barcode) {
            Object.assign(grid.fields_map.barcode, {
                hidden: 0,
                in_list_view: 1,
                columns: is_stock_entry_grid(grid) ? STOCK_ENTRY_BARCODE_COLUMNS : BARCODE_COLUMNS,
                colsize: is_stock_entry_grid(grid) ? STOCK_ENTRY_BARCODE_COLUMNS : BARCODE_COLUMNS
            });
        }

        if (is_stock_entry_grid(grid)) {
            show_grid_list_column(grid.fields_map && grid.fields_map.item_code);
            hide_grid_list_column(grid.fields_map && grid.fields_map.is_finished_item);
            apply_stock_entry_column_sizes(Object.values(grid.fields_map || {}));
        } else {
            set_grid_column_size(grid.fields_map && grid.fields_map.item_code, ITEM_CODE_COLUMNS);
        }

        reset_grid_layout(
            grid,
            is_stock_entry_grid(grid)
                ? "stock-entry-barcode-item-code-v3"
                : "transaction-barcode-grid-v3"
        );
    }

    function get_grid_row_from_input(frm, input) {
        const grid = get_items_grid(frm);
        if (!grid) return null;

        const row_name = $(input).closest(".grid-row").attr("data-name");
        return row_name ? grid.grid_rows_by_docname[row_name] : null;
    }

    function attach_item_code_input_handler(frm) {
        const grid = get_items_grid(frm);
        if (!grid || grid.__armada_item_code_barcode_scan_attached) return;

        grid.__armada_item_code_barcode_scan_attached = true;

        const selector = [
            '[data-fieldname="barcode"] input',
            'input[data-fieldname="barcode"]'
        ].join(",");

        $(grid.wrapper)
            .off(HANDLER_NAMESPACE)
            .on("keydown" + HANDLER_NAMESPACE, selector, function (event) {
                const value = String(this.value || "").trim();
                if (event.key !== "Enter" || !value) return;

                event.preventDefault();
                event.stopImmediatePropagation();
                this.value = "";

                if (is_armada_barcode(value)) {
                    resolve_barcode_input(frm, this, value);
                } else {
                    resolve_item_code_by_input(frm, this, value);
                }
            })
            .on("input" + HANDLER_NAMESPACE, selector, frappe.utils.debounce(function () {
                const barcode = String(this.value || "").trim();
                if (is_armada_barcode(barcode)) {
                    this.value = "";
                    resolve_barcode_input(frm, this, barcode);
                }
            }, 150));
    }

    function resolve_barcode_input(frm, input, barcode) {
        const grid_row = get_grid_row_from_input(frm, input);
        if (!grid_row || !grid_row.doc) return;

        resolve_item_barcode(frm, grid_row.doc.doctype, grid_row.doc.name, barcode);
    }

    function resolve_item_code_by_input(frm, input, item_code) {
        const grid_row = get_grid_row_from_input(frm, input);
        if (!grid_row || !grid_row.doc) return;

        resolve_item_by_item_code(frm, grid_row.doc.doctype, grid_row.doc.name, item_code);
    }

    function resolve_item_by_item_code(frm, cdt, cdn, item_code) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row) return;
        if (row.__armada_resolving_item_code === item_code) return;

        row.__armada_resolving_item_code = item_code;

        frappe.call({
            method: "armada.armada_custom_app.barcode.get_item_details_by_item_code_search",
            args: { item_code: item_code },
            callback: function (r) {
                if (!r.message || !r.message.item_code) {
                    frappe.msgprint(__("No Item found for item code {0}", [item_code]));
                    return;
                }
                apply_scanned_item(frm, cdt, cdn, r.message.barcode || "", r.message);
            },
            always: function () {
                row.__armada_resolving_item_code = null;
            }
        });
    }

    function resolve_item_barcode(frm, cdt, cdn, barcode) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row || !is_armada_barcode(barcode)) return;
        if (row.item_code && row.barcode === barcode) return;

        if (row.__armada_resolving_barcode === barcode) return;
        row.__armada_resolving_barcode = barcode;

        frappe.call({
            method: "erpnext.stock.utils.scan_barcode",
            args: {
                search_value: barcode
            },
            callback: function (r) {
                if (!r.message || !r.message.item_code) {
                    clear_unresolved_barcode(frm, cdt, cdn, barcode);
                    frappe.msgprint(__("No Item found for barcode {0}", [barcode]));
                    return;
                }

                apply_scanned_item(frm, cdt, cdn, barcode, r.message);
            },
            error: function () {
                clear_unresolved_barcode(frm, cdt, cdn, barcode);
            },
            always: function () {
                row.__armada_resolving_barcode = null;
            }
        });
    }

    function clear_unresolved_barcode(frm, cdt, cdn, barcode) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row) return;

        const updates = [];
        if (row.item_code === barcode) updates.push(["item_code", ""]);
        if (row.barcode === barcode) updates.push(["barcode", ""]);

        updates.reduce(function (chain, update) {
            return chain.then(function () {
                return frappe.model.set_value(cdt, cdn, update[0], update[1]);
            });
        }, Promise.resolve());
    }

    function apply_scanned_item(frm, cdt, cdn, barcode, data) {
        if (cdt === "Stock Entry Detail") {
            apply_scanned_stock_entry_item(frm, cdt, cdn, barcode, data);
            return;
        }

        const row = locals[cdt] && locals[cdt][cdn];
        if (row && frappe.meta.has_field(cdt, "barcode")) {
            row.barcode = data.barcode || barcode;
        }

        const fields = [];

        if (
            cdt === "Stock Entry Detail" &&
            frappe.meta.has_field(cdt, "qty") &&
            (!row || !row.qty)
        ) {
            fields.push(["qty", 1]);
        }

        fields.push(
            ["item_code", data.item_code],
            ["uom", data.uom]
        );

        const valid_fields = fields.filter(function (field) {
            return field[1] && frappe.meta.has_field(cdt, field[0]);
        });

        let chain = Promise.resolve();
        valid_fields.forEach(function (field) {
            chain = chain.then(function () {
                return frappe.model.set_value(cdt, cdn, field[0], field[1]);
            });
        });

        chain.then(function () {
            frm.refresh_field("items");
            prepare_next_barcode_row(frm, cdn);
        });
    }

    function apply_scanned_stock_entry_item(frm, cdt, cdn, barcode, data) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row) return;

        const qty = row.qty || 1;
        row.__armada_scanning_barcode = true;
        remove_all_empty_barcode_rows(frm);

        frappe.call({
            method: STOCK_ENTRY_DETAILS_METHOD,
            args: {
                item_code: data.item_code,
                barcode: data.barcode || barcode,
                company: frm.doc.company,
                purpose: frm.doc.purpose,
                warehouse: row.s_warehouse || row.t_warehouse || "",
                qty: qty,
                posting_date: frm.doc.posting_date,
                posting_time: frm.doc.posting_time
            },
            callback: function (r) {
                apply_stock_entry_details_to_row(cdt, cdn, data.barcode || barcode, data.item_code, qty, r.message || {});
                delete row.__armada_scanning_barcode;
                frm.refresh_field("items");
                prepare_next_barcode_row(frm, cdn);
            },
            error: function () {
                delete row.__armada_scanning_barcode;
                clear_unresolved_barcode(frm, cdt, cdn, barcode);
            }
        });
    }

    function apply_stock_entry_details_to_row(cdt, cdn, barcode, item_code, qty, details) {
        const row = locals[cdt] && locals[cdt][cdn];
        if (!row) return;

        Object.keys(details).forEach(function (fieldname) {
            if (
                frappe.meta.has_field(cdt, fieldname) &&
                details[fieldname] !== undefined &&
                details[fieldname] !== null
            ) {
                row[fieldname] = details[fieldname];
            }
        });

        row.barcode = barcode;
        row.item_code = item_code;
        row.qty = row.qty || qty || 1;
        row.transfer_qty = row.transfer_qty || row.qty;
    }

    function is_empty_barcode_row(row) {
        return row && !row.__armada_scanning_barcode && !row.barcode && !row.item_code;
    }

    function remove_all_empty_barcode_rows(frm) {
        const rows = frm.doc.items || [];
        for (let i = rows.length - 1; i >= 0; i--) {
            const row = rows[i];
            if (is_empty_barcode_row(row)) {
                rows.splice(i, 1);
                frappe.model.clear_doc(row.doctype, row.name);
            }
        }
        frm.refresh_field("items");
    }

    function remove_extra_empty_barcode_rows(frm) {
        const rows = frm.doc.items || [];
        const empty_rows = rows.filter(is_empty_barcode_row);
        if (empty_rows.length <= 1) return empty_rows[0] || null;

        const row_to_keep = empty_rows[empty_rows.length - 1];
        empty_rows.slice(0, -1).forEach(function (row) {
            const row_index = rows.findIndex(function (item) {
                return item.name === row.name;
            });
            if (row_index !== -1) {
                rows.splice(row_index, 1);
                frappe.model.clear_doc(row.doctype, row.name);
            }
        });

        return row_to_keep;
    }

    function ensure_empty_barcode_row(frm) {
        const grid = get_items_grid(frm);
        let empty_row = remove_extra_empty_barcode_rows(frm);
        if (!empty_row) {
            empty_row = grid && grid.add_new_row ? grid.add_new_row(null, null, false) : frm.add_child("items");
        }

        return empty_row;
    }

    function prepare_next_barcode_row(frm) {
        const next_row = ensure_empty_barcode_row(frm);
        frm.refresh_field("items");

        setTimeout(function () {
            focus_barcode_input(frm, next_row.name, 0);
        }, 25);
    }

    function focus_barcode_input(frm, row_name, attempt) {
        const grid = get_items_grid(frm);
        if (!grid || !row_name) return;

        const grid_row = grid.grid_rows_by_docname && grid.grid_rows_by_docname[row_name];
        if (grid_row) {
            if (grid_row.row && grid_row.row.length) {
                grid_row.row.get(0).scrollIntoView({ block: "nearest" });
            }

            if (grid_row.toggle_editable_row) {
                grid_row.toggle_editable_row(true);
            }

            const barcode_column = grid_row.columns && grid_row.columns.barcode;
            if (barcode_column) {
                if (grid_row.make_control && !barcode_column.field) {
                    grid_row.make_control(barcode_column);
                }

                if (barcode_column.field) {
                    const field = barcode_column.field;
                    if (field.refresh) {
                        field.refresh();
                    }
                    if (focus_input(field.$input)) return;
                    if (field.set_focus) {
                        field.set_focus();
                        if (focus_input(field.$input)) return;
                    }
                }
            }
        }

        const $input = $(grid.wrapper).find(
            '.grid-row[data-name="' + row_name + '"] [data-fieldname="barcode"] input,' +
                '.grid-row[data-name="' + row_name + '"] input[data-fieldname="barcode"]'
        );
        if (focus_input($input)) return;

        if (attempt < 10) {
            setTimeout(function () {
                focus_barcode_input(frm, row_name, attempt + 1);
            }, 75);
        }
    }

    function focus_input($input) {
        if (!$input || !$input.length) return false;

        const input = $input.filter(":visible").first().get(0) || $input.first().get(0);
        if (!input) return false;

        if (document.activeElement && document.activeElement !== input) {
            document.activeElement.blur();
        }

        input.focus();
        input.select();
        return document.activeElement === input;
    }

    function register_parent_handlers() {
        patch_stock_entry_none_qty_message();
        patch_standard_stock_entry_barcode_handler();

        PARENT_DOCTYPES.forEach(function (doctype) {
            frappe.ui.form.on(doctype, {
                setup: function (frm) {
                    patch_stock_entry_none_qty_message();
                    patch_standard_stock_entry_barcode_handler();
                    patch_stock_entry_cscript_barcode_handler(frm);
                    configure_barcode_grid_column(frm);
                    attach_item_code_input_handler(frm);
                },
                refresh: function (frm) {
                    patch_stock_entry_none_qty_message();
                    patch_standard_stock_entry_barcode_handler();
                    patch_stock_entry_cscript_barcode_handler(frm);
                    configure_barcode_grid_column(frm);
                    attach_item_code_input_handler(frm);
                },
                onload_post_render: function (frm) {
                    patch_stock_entry_none_qty_message();
                    patch_standard_stock_entry_barcode_handler();
                    patch_stock_entry_cscript_barcode_handler(frm);
                    configure_barcode_grid_column(frm);
                    attach_item_code_input_handler(frm);
                },
                validate: function (frm) {
                    if (frm.doctype === "Stock Entry") {
                        remove_all_empty_barcode_rows(frm);
                    }
                },
                items_on_form_rendered: configure_barcode_grid_column
            });
        });
    }

    function register_child_handlers() {
        CHILD_DOCTYPES.forEach(function (doctype) {
            frappe.ui.form.on(doctype, {
                item_code: function () {},
                barcode: function (frm, cdt, cdn) {
                    const row = locals[cdt] && locals[cdt][cdn];
                    if (!row || row.item_code) return;

                    if (is_armada_barcode(row.barcode)) {
                        const barcode = row.barcode;
                        if (cdt === "Stock Entry Detail") {
                            row.barcode = "";
                        }
                        if (row.__armada_resolving_barcode !== barcode) {
                            resolve_item_barcode(frm, cdt, cdn, barcode);
                        }
                    } else if (row.barcode && row.barcode.trim()) {
                        const item_code_input = row.barcode.trim();
                        row.barcode = "";
                        if (row.__armada_resolving_item_code !== item_code_input) {
                            resolve_item_by_item_code(frm, cdt, cdn, item_code_input);
                        }
                    }
                }
            });
        });
    }

    register_parent_handlers();
    register_child_handlers();
})();
