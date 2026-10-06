// Copyright (c) 2025, abdulloh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kassa", {
    refresh: function(frm) {
        // Linked document button
        if (frm.doc.docstatus == 1 && frm.doc.linked_entry) {
            frm.add_custom_button(frm.doc.linked_entry, function() {
                frappe.set_route("Form", frm.doc.linked_doctype, frm.doc.linked_entry);
            }, __("Связанный документ"));
        }

        // Set expense account query
        frm.set_query("expense_account", function() {
            return {
                filters: {
                    company: frm.doc.company,
                    root_type: "Expense",
                    is_group: 0
                }
            };
        });

        // Set mode_of_payment query
        frm.trigger("set_mode_of_payment_query");

        // Update balance on refresh
        if (frm.doc.mode_of_payment && frm.doc.company) {
            frm.trigger("update_balance");
        }

        // Update balance_to on refresh for transfer
        if (frm.doc.mode_of_payment_to && frm.doc.company) {
            frm.trigger("update_balance_to");
        }

        // Set mode_of_payment_to query
        frm.trigger("set_mode_of_payment_to_query");

        // Update balance label based on transaction type
        frm.trigger("update_balance_label");
        frm.trigger("update_party_type_options");

        // Update sub-account options on load
        if (frm.doc.expense_account) {
            frm.trigger("update_sub_account_options");
        }
    },

    company: function(frm) {
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account", "");
        frm.set_value("balance", 0);
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
    },

    mode_of_payment: function(frm) {
        if (frm.doc.mode_of_payment && frm.doc.company) {
            frappe.call({
                method: "armada.armada_custom_app.doctype.kassa.kassa.get_cash_account_with_currency",
                args: {
                    mode_of_payment: frm.doc.mode_of_payment,
                    company: frm.doc.company
                },
                callback: function(r) {
                    if (r.message && r.message.account) {
                        frm.set_value("cash_account", r.message.account);
                        frm.set_value("cash_account_currency", r.message.currency);
                        frm.trigger("update_balance");
                        frm.trigger("validate_currency");
                    } else {
                        frappe.msgprint(__("Для данного способа оплаты не настроен счет кассы для компании {0}", [frm.doc.company]));
                        frm.set_value("cash_account", "");
                        frm.set_value("cash_account_currency", "");
                        frm.set_value("balance", 0);
                    }
                }
            });
        } else {
            frm.set_value("cash_account", "");
            frm.set_value("cash_account_currency", "");
            frm.set_value("balance", 0);
        }

        // Clear mode_of_payment_to when mode_of_payment changes (for transfer)
        if (frm.doc.transaction_type === "Перемещения") {
            frm.set_value("mode_of_payment_to", "");
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
            frm.trigger("set_mode_of_payment_to_query");
        }
    },

    update_balance: function(frm) {
        if (frm.doc.cash_account && frm.doc.company) {
            frappe.call({
                method: "armada.armada_custom_app.doctype.kassa.kassa.get_account_balance",
                args: {
                    account: frm.doc.cash_account,
                    company: frm.doc.company
                },
                callback: function(r) {
                    frm.set_value("balance", r.message || 0);
                }
            });
        }
    },

    transaction_type: function(frm) {
        // Clear party fields
        frm.set_value("party_type", "");
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
        frm.set_value("party_name", "");
        frm.set_value("expense_account_name", "");

        // Clear payment and transfer fields
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account", "");
        frm.set_value("balance", 0);
        frm.set_value("mode_of_payment_to", "");
        frm.set_value("cash_account_to", "");
        frm.set_value("balance_to", 0);

        // Set queries
        frm.trigger("set_mode_of_payment_query");
        frm.trigger("set_mode_of_payment_to_query");
        frm.trigger("update_party_type_options");

        // For Перемещения, set default company if not set
        if (frm.doc.transaction_type === "Перемещения" && !frm.doc.company) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Global Defaults",
                    fieldname: "default_company"
                },
                callback: function(r) {
                    if (r.message && r.message.default_company) {
                        frm.set_value("company", r.message.default_company);
                    }
                }
            });
        }

        // Update balance label
        frm.trigger("update_balance_label");
    },

    mode_of_payment_to: function(frm) {
        if (frm.doc.mode_of_payment_to && frm.doc.company) {
            frappe.call({
                method: "armada.armada_custom_app.doctype.kassa.kassa.get_cash_account",
                args: {
                    mode_of_payment: frm.doc.mode_of_payment_to,
                    company: frm.doc.company
                },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("cash_account_to", r.message);
                        frm.trigger("update_balance_to");
                    } else {
                        frappe.msgprint(__("Для данного способа оплаты не настроен счет кассы для компании {0}", [frm.doc.company]));
                        frm.set_value("cash_account_to", "");
                        frm.set_value("balance_to", 0);
                    }
                }
            });
        } else {
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
        }
    },

    update_balance_to: function(frm) {
        if (frm.doc.cash_account_to && frm.doc.company) {
            frappe.call({
                method: "armada.armada_custom_app.doctype.kassa.kassa.get_account_balance",
                args: {
                    account: frm.doc.cash_account_to,
                    company: frm.doc.company
                },
                callback: function(r) {
                    frm.set_value("balance_to", r.message || 0);
                }
            });
        }
    },

    set_mode_of_payment_query: function(frm) {
        frm.set_query("mode_of_payment", function() {
            return {};
        });
    },

    set_mode_of_payment_to_query: function(frm) {
        frm.set_query("mode_of_payment_to", function() {
            let filters = {};

            if (frm.doc.mode_of_payment) {
                filters.name = ["!=", frm.doc.mode_of_payment];
            }

            return { filters: filters };
        });
    },

    update_balance_label: function(frm) {
        if (frm.doc.transaction_type === "Перемещения") {
            frm.set_df_property("balance", "label", "Остаток (откуда)");
        } else {
            frm.set_df_property("balance", "label", "Остаток");
        }
        frm.refresh_field("balance");
    },

    update_party_type_options: function(frm) {
        let options = ["", "Customer", "Supplier", "Shareholder", "Employee", "Расходы"];

        if (frm.doc.transaction_type !== "Приход") {
            options.push("Дивиденд");
        }

        frm.set_df_property("party_type", "options", options.join("\n"));
        frm.refresh_field("party_type");

        if (frm.doc.docstatus === 0 && frm.doc.transaction_type === "Приход" && frm.doc.party_type === "Дивиденд") {
            frm.set_value("party_type", "");
            frappe.msgprint(__("Тип контрагента Дивиденд разрешен только для операции Расход."));
        }
    },

    party_type: function(frm) {
        frm.trigger("validate_dividend_transaction");
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
        frm.set_value("party_name", "");
        frm.set_value("expense_account_name", "");

        if (frm.doc.party_type === "Расходы") {
            frm.set_df_property("expense_account", "reqd", 1);
            frm.set_df_property("party", "reqd", 0);
        } else if (frm.doc.party_type === "Дивиденд") {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 0);
        } else if (frm.doc.party_type) {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 1);
        } else {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 0);
        }

        frm.refresh_fields();
    },

    party: function(frm) {
        if (frm.doc.party && frm.doc.party_type) {
            let name_field = get_party_name_field(frm.doc.party_type);
            if (name_field) {
                frappe.db.get_value(frm.doc.party_type, frm.doc.party, name_field, function(r) {
                    if (r && r[name_field]) {
                        frm.set_value("party_name", r[name_field]);
                    }
                });
            }

            if (in_list(["Customer", "Supplier"], frm.doc.party_type)) {
                frappe.call({
                    method: "armada.armada_custom_app.doctype.kassa.kassa.get_party_currency",
                    args: {
                        party_type: frm.doc.party_type,
                        party: frm.doc.party,
                        company: frm.doc.company
                    },
                    callback: function(r) {
                        if (r.message) {
                            frm.set_value("party_currency", r.message);
                            frm.trigger("validate_currency");
                        }
                    }
                });
            }
        } else {
            frm.set_value("party_name", "");
            frm.set_value("party_currency", "");
        }
    },

    expense_account: function(frm) {
        if (frm.doc.expense_account) {
            frappe.db.get_value("Account", frm.doc.expense_account, "account_name", function(r) {
                if (r && r.account_name) {
                    frm.set_value("expense_account_name", r.account_name);
                }
            });
            // Fetch and set sub-account options
            frm.trigger("update_sub_account_options");
        } else {
            frm.set_value("expense_account_name", "");
            frm.set_df_property("custom_sub_account_name", "options", [""]);
            frm.set_value("custom_sub_account_name", "");
        }
    },

    update_sub_account_options: function(frm) {
        if (frm.doc.expense_account) {
            frappe.call({
                method: "frappe.client.get_value",
                args: {
                    doctype: "Account Name Mapping",
                    filters: { account: frm.doc.expense_account },
                    fieldname: "name"
                },
                callback: function(r) {
                    if (r.message && r.message.name) {
                        frappe.model.with_doc("Account Name Mapping", r.message.name, function() {
                            let mapping_doc = frappe.get_doc("Account Name Mapping", r.message.name);
                            let options = [""];
                            if (mapping_doc.mapping_items) {
                                mapping_doc.mapping_items.forEach(function(item) {
                                    options.push(item.sub_name);
                                });
                            }
                            frm.set_df_property("custom_sub_account_name", "options", options);
                            frm.refresh_field("custom_sub_account_name");
                        });
                    } else {
                        frm.set_df_property("custom_sub_account_name", "options", [""]);
                        frm.refresh_field("custom_sub_account_name");
                        frm.set_value("custom_sub_account_name", "");
                    }
                }
            });
        }
    },

    validate_currency: function(frm) {
        if (frm.doc.cash_account_currency && frm.doc.party_currency) {
            if (frm.doc.cash_account_currency !== frm.doc.party_currency) {
                frappe.validated = false;
                frappe.msgprint({
                    title: __("Ошибка валюты"),
                    indicator: "red",
                    message: __("Валюта кассы ({0}) не совпадает с валютой контрагента ({1}). Выберите соответствующий способ оплаты.",
                        [frm.doc.cash_account_currency, frm.doc.party_currency])
                });
            }
        }
    },

    validate_dividend_transaction: function(frm) {
        if (frm.doc.transaction_type === "Приход" && frm.doc.party_type === "Дивиденд") {
            frappe.validated = false;
            frappe.msgprint({
                title: __("Неверная комбинация"),
                indicator: "red",
                message: __("Тип контрагента Дивиденд разрешен только для операции Расход.")
            });
            if (frm.doc.docstatus === 0) {
                frm.set_value("party_type", "");
            }
        }
    },

    validate: function(frm) {
        frm.trigger("validate_dividend_transaction");
    }
});

function get_party_name_field(party_type) {
    const name_fields = {
        "Customer": "customer_name",
        "Supplier": "supplier_name",
        "Shareholder": "title",
        "Employee": "employee_name"
    };
    return name_fields[party_type] || null;
}


// ── Инвойсларга тақсимлаш (Customer / Приход) ─────────────────────────────────
frappe.ui.form.on("Kassa", {
    refresh: function(frm) {
        if (frm.doc.docstatus !== 0 || !frm.events.can_pick_invoices(frm)) return;
        frm.add_custom_button(__("Инвойс танлаш"), () => frm.events.pick_invoices(frm));
    },

    party: function(frm) {
        frm.clear_table("invoices");
        frm.refresh_field("invoices");
    },

    transaction_type: function(frm) {
        frm.clear_table("invoices");
        frm.refresh_field("invoices");
    },

    can_pick_invoices: function(frm) {
        return frm.doc.transaction_type === "Приход" && frm.doc.party_type === "Customer" && !!frm.doc.party;
    },

    pick_invoices: function(frm) {
        if (!frm.doc.amount) {
            frappe.msgprint(__("Аввал суммани киритинг"));
            return;
        }
        frappe.call({
            method: "armada.armada_custom_app.doctype.kassa.kassa.get_open_invoices",
            args: { customer: frm.doc.party, company: frm.doc.company },
            freeze: true,
            callback: function(r) {
                const invoices = r.message || [];
                if (!invoices.length) {
                    frappe.msgprint(__("Бу мижозда очиқ инвойс йўқ"));
                    return;
                }
                frm.events.show_invoice_dialog(frm, invoices);
            }
        });
    },

    show_invoice_dialog: function(frm, invoices) {
        const esc = frappe.utils.escape_html;
        const total = flt(frm.doc.amount);
        const chosen = {};  // invoice name -> allocated amount
        (frm.doc.invoices || []).forEach(row => { chosen[row.sales_invoice] = flt(row.allocated_amount); });

        const d = new frappe.ui.Dialog({
            title: __("Инвойс танлаш — {0}", [frm.doc.party_name || frm.doc.party]),
            size: "extra-large",
            fields: [
                { fieldname: "search", fieldtype: "Data", label: __("Қидирув (товар, изоҳ, сана)") },
                { fieldname: "summary", fieldtype: "HTML" },
                { fieldname: "list", fieldtype: "HTML" },
            ],
            primary_action_label: __("Қўллаш"),
            primary_action: function() {
                const picked = invoices.filter(i => flt(chosen[i.name]) > 0);
                const sum = picked.reduce((a, i) => a + flt(chosen[i.name]), 0);
                if (sum > total + 0.005) {
                    frappe.msgprint(__("Тақсимланган сумма кассадаги суммадан ошиб кетди"));
                    return;
                }
                frm.clear_table("invoices");
                picked.forEach(i => {
                    const row = frm.add_child("invoices");
                    row.sales_invoice = i.name;
                    row.posting_date = i.posting_date;
                    row.items_summary = i.items_summary;
                    row.komment = i.komment;
                    row.grand_total = i.grand_total;
                    row.outstanding_amount = i.outstanding_amount;
                    row.allocated_amount = flt(chosen[i.name]);
                });
                frm.refresh_field("invoices");
                frm.dirty();
                d.hide();
            },
        });

        const $list = d.fields_dict.list.$wrapper;
        const $summary = d.fields_dict.summary.$wrapper;

        const allocatedSum = () => Object.values(chosen).reduce((a, v) => a + flt(v), 0);
        const updateSummary = () => {
            const left = total - allocatedSum();
            $summary.html(`<div class="text-muted" style="margin-bottom:6px">
                ${__("Касса суммаси")}: <b>${format_currency(total)}</b> &nbsp;|&nbsp;
                ${__("Тақсимланди")}: <b>${format_currency(allocatedSum())}</b> &nbsp;|&nbsp;
                ${__("Қолди (аванс)")}: <b style="color:${left < -0.005 ? "#c62828" : "inherit"}">${format_currency(left)}</b>
            </div>`);
        };

        const render = () => {
            const q = (d.get_value("search") || "").toLowerCase().trim();
            const rows = invoices.filter(i =>
                !q || [i.items_summary, i.komment, i.posting_date, i.name].join(" ").toLowerCase().includes(q));
            $list.html(`
                <div style="max-height:55vh; overflow:auto">
                <table class="table table-bordered table-sm" style="font-size:12px">
                    <thead><tr>
                        <th style="width:30px"></th><th>${__("Сана")}</th><th>${__("Товарлар")}</th>
                        <th>${__("Изоҳ")}</th><th class="text-right">${__("Қолдиқ")}</th>
                        <th style="width:110px">${__("Тўланаётган")}</th><th>${__("Инвойс")}</th>
                    </tr></thead>
                    <tbody>${rows.map(i => `
                        <tr data-name="${esc(i.name)}">
                            <td><input type="checkbox" class="pick" ${chosen[i.name] ? "checked" : ""}></td>
                            <td>${esc(i.posting_date)}</td>
                            <td>${esc(i.items_summary)}</td>
                            <td>${esc(i.komment)}</td>
                            <td class="text-right">${format_currency(i.outstanding_amount, i.currency)}</td>
                            <td><input type="number" step="0.01" class="form-control input-xs amt" value="${chosen[i.name] || ""}"></td>
                            <td class="text-muted">${esc(i.name)}</td>
                        </tr>`).join("")}
                    </tbody>
                </table></div>`);
            updateSummary();
        };

        const byName = name => invoices.find(i => i.name === name);

        $list.on("change", ".pick", function() {
            const $tr = $(this).closest("tr");
            const inv = byName($tr.data("name"));
            if (this.checked) {
                const left = total - allocatedSum();
                chosen[inv.name] = Math.max(0, Math.min(flt(inv.outstanding_amount), left));
                $tr.find(".amt").val(chosen[inv.name] || "");
            } else {
                delete chosen[inv.name];
                $tr.find(".amt").val("");
            }
            updateSummary();
        });

        $list.on("input", ".amt", function() {
            const $tr = $(this).closest("tr");
            const inv = byName($tr.data("name"));
            let v = flt($(this).val());
            if (v > flt(inv.outstanding_amount)) {
                v = flt(inv.outstanding_amount);
                $(this).val(v);
            }
            if (v > 0) {
                chosen[inv.name] = v;
                $tr.find(".pick").prop("checked", true);
            } else {
                delete chosen[inv.name];
                $tr.find(".pick").prop("checked", false);
            }
            updateSummary();
        });

        d.fields_dict.search.df.onchange = render;
        d.fields_dict.search.$input.on("input", frappe.utils.debounce(render, 200));
        d.show();
        render();
    },
});


// ── Jadvaldagi "Инвойс" maydoni: bosilganda mijozning to'lanmagan invoyslari ─────
frappe.ui.form.on("Kassa", {
    refresh: function(frm) {
        frm.set_query("sales_invoice", "invoices", function() {
            return {
                query: "armada.armada_custom_app.doctype.kassa.kassa.invoice_query",
                filters: {
                    customer: frm.doc.party,
                    company: frm.doc.company,
                    exclude: (frm.doc.invoices || []).map(r => r.sales_invoice).filter(Boolean),
                },
            };
        });
    },
});

frappe.ui.form.on("Kassa Invoice", {
    sales_invoice: function(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.sales_invoice) return;
        frappe.call({
            method: "armada.armada_custom_app.doctype.kassa.kassa.get_invoice_row",
            args: { invoice: row.sales_invoice, customer: frm.doc.party, company: frm.doc.company },
            callback: function(r) {
                const inv = r.message;
                if (!inv) return;
                const others = (frm.doc.invoices || [])
                    .filter(x => x.name !== cdn)
                    .reduce((a, x) => a + flt(x.allocated_amount), 0);
                const left = Math.max(0, flt(frm.doc.amount) - others);
                frappe.model.set_value(cdt, cdn, {
                    posting_date: inv.posting_date,
                    items_summary: inv.items_summary,
                    komment: inv.komment,
                    grand_total: inv.grand_total,
                    outstanding_amount: inv.outstanding_amount,
                    allocated_amount: Math.min(flt(inv.outstanding_amount), left),
                });
            },
        });
    },
});
